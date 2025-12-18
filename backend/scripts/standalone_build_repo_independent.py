"""
Completely standalone script to parse a repository, generate OpenSearch chunks with embeddings,
and create a knowledge graph. No dependencies on project structure.

Usage:
  python standalone_build_repo_independent.py \
    --repo-path /path/to/repo \
    --output-dir ./output \
    --opensearch-host localhost:9200 \
    --opensearch-index code_chunks \
    --openai-api-key sk-...

Requirements:
  pip install tree-sitter tree-sitter-python tree-sitter-java tree-sitter-javascript \
              openai opensearch-py networkx
"""

import argparse
import asyncio
import os
import re
import json
import pickle
from pathlib import Path
from typing import List, Dict, Any, Optional, Set
from datetime import datetime

# TreeSitter imports
try:
    from tree_sitter import Language, Parser
    import tree_sitter_python as tspython
    import tree_sitter_java as tsjava
    import tree_sitter_javascript as tsjavascript
    TREE_SITTER_AVAILABLE = True
except ImportError:
    TREE_SITTER_AVAILABLE = False
    print("⚠️ TreeSitter not available. Install: pip install tree-sitter tree-sitter-python tree-sitter-java tree-sitter-javascript")

# OpenAI for embeddings
try:
    from openai import AsyncOpenAI
    OPENAI_AVAILABLE = True
except ImportError:
    OPENAI_AVAILABLE = False
    print("⚠️ OpenAI not available. Install: pip install openai")

# OpenSearch
try:
    from opensearchpy import OpenSearch
    OPENSEARCH_AVAILABLE = True
except ImportError:
    OPENSEARCH_AVAILABLE = False
    print("⚠️ OpenSearch not available. Install: pip install opensearch-py")

# NetworkX for graph
try:
    import networkx as nx
    NETWORKX_AVAILABLE = True
except ImportError:
    NETWORKX_AVAILABLE = False
    print("⚠️ NetworkX not available. Install: pip install networkx")


class StandaloneParser:
    """Self-contained multi-language parser using TreeSitter."""
    
    def __init__(self):
        self.parsers = {}
        if TREE_SITTER_AVAILABLE:
            self._init_parsers()
    
    def _init_parsers(self):
        """Initialize TreeSitter parsers."""
        try:
            # Python
            python_lang = Language(tspython.language())
            parser = Parser()
            parser.set_language(python_lang)
            self.parsers['python'] = parser
        except Exception as e:
            print(f"⚠️ Failed to init Python parser: {e}")
        
        try:
            # Java
            java_lang = Language(tsjava.language())
            parser = Parser()
            parser.set_language(java_lang)
            self.parsers['java'] = parser
        except Exception as e:
            print(f"⚠️ Failed to init Java parser: {e}")
        
        try:
            # JavaScript/TypeScript
            js_lang = Language(tsjavascript.language())
            parser = Parser()
            parser.set_language(js_lang)
            self.parsers['javascript'] = parser
            self.parsers['typescript'] = parser
        except Exception as e:
            print(f"⚠️ Failed to init JS/TS parser: {e}")
    
    def detect_language(self, file_path: str) -> str:
        """Detect language from file extension."""
        ext_map = {
            '.java': 'java',
            '.py': 'python',
            '.js': 'javascript',
            '.jsx': 'javascript',
            '.ts': 'typescript',
            '.tsx': 'typescript',
        }
        return ext_map.get(Path(file_path).suffix.lower(), 'java')
    
    def parse_file(self, file_path: str) -> Optional[Dict[str, Any]]:
        """Parse a file and extract structure."""
        language = self.detect_language(file_path)
        
        if language not in self.parsers:
            return None
        
        try:
            with open(file_path, 'r', encoding='utf-8', errors='ignore') as f:
                content = f.read()
            
            parser = self.parsers[language]
            tree = parser.parse(bytes(content, 'utf8'))
            root = tree.root_node
            
            return {
                'language': language,
                'file_path': file_path,
                'functions': self._extract_functions(root, content, language),
                'classes': self._extract_classes(root, content, language),
                'imports': self._extract_imports(root, content, language),
            }
        except Exception as e:
            print(f"⚠️ Error parsing {file_path}: {e}")
            return None
    
    def _extract_functions(self, root, content: str, language: str) -> List[Dict[str, Any]]:
        """Extract function/method definitions."""
        functions = []
        # Simplified extraction - traverse AST for function nodes
        def traverse(node):
            if node.type == 'method_declaration' or node.type == 'function_definition':
                name_node = node.child_by_field_name('name')
                if name_node:
                    name = content[name_node.start_byte:name_node.end_byte]
                    functions.append({
                        'name': name,
                        'start_line': node.start_point[0] + 1,
                        'end_line': node.end_point[0] + 1,
                        'code': content[node.start_byte:node.end_byte]
                    })
            for child in node.children:
                traverse(child)
        
        traverse(root)
        return functions
    
    def _extract_classes(self, root, content: str, language: str) -> List[Dict[str, Any]]:
        """Extract class definitions."""
        classes = []
        def traverse(node):
            if node.type == 'class_declaration':
                name_node = node.child_by_field_name('name')
                if name_node:
                    name = content[name_node.start_byte:name_node.end_byte]
                    classes.append({
                        'name': name,
                        'start_line': node.start_point[0] + 1,
                        'end_line': node.end_point[0] + 1,
                    })
            for child in node.children:
                traverse(child)
        traverse(root)
        return classes
    
    def _extract_imports(self, root, content: str, language: str) -> List[str]:
        """Extract import statements."""
        imports = []
        def traverse(node):
            if node.type in ['import_declaration', 'import_statement']:
                import_text = content[node.start_byte:node.end_byte]
                imports.append(import_text.strip())
            for child in node.children:
                traverse(child)
        traverse(root)
        return imports


class StandaloneIndexer:
    """Self-contained indexer for generating chunks and embeddings."""
    
    def __init__(self, openai_api_key: Optional[str] = None, embedding_model: str = "text-embedding-3-small"):
        self.parser = StandaloneParser()
        self.embedding_client = None
        self.embedding_model = embedding_model
        
        if OPENAI_AVAILABLE and openai_api_key:
            self.embedding_client = AsyncOpenAI(api_key=openai_api_key)
    
    async def generate_embedding(self, text: str) -> Optional[List[float]]:
        """Generate embedding for text."""
        if not self.embedding_client:
            return None
        
        try:
            response = await self.embedding_client.embeddings.create(
                model=self.embedding_model,
                input=text
            )
            return response.data[0].embedding
        except Exception as e:
            print(f"⚠️ Error generating embedding: {e}")
            return None
    
    def find_code_files(self, repo_path: str) -> List[str]:
        """Find all code files in repository."""
        code_files = []
        repo = Path(repo_path)
        exclude_dirs = {'.git', 'node_modules', 'target', 'build', '__pycache__', '.venv'}
        
        for ext in ['*.java', '*.py', '*.js', '*.jsx', '*.ts', '*.tsx']:
            for file in repo.rglob(ext):
                if any(excluded in file.parts for excluded in exclude_dirs):
                    continue
                code_files.append(str(file))
        
        return code_files
    
    async def process_repository(self, repo_path: str) -> List[Dict[str, Any]]:
        """Process repository and generate chunks."""
        print(f"📁 Scanning repository: {repo_path}")
        code_files = self.find_code_files(repo_path)
        print(f"   Found {len(code_files)} code files")
        
        all_chunks = []
        
        for file_path in code_files:
            parsed = self.parser.parse_file(file_path)
            if not parsed:
                continue
            
            # Generate chunks for functions
            for func in parsed.get('functions', []):
                chunk = {
                    'type': 'method',
                    'fqn': f"{Path(file_path).stem}.{func['name']}",
                    'file_path': file_path,
                    'start_line': func['start_line'],
                    'end_line': func['end_line'],
                    'code': func['code'],
                    'summary': f"Method {func['name']}",
                    'language': parsed['language'],
                }
                
                # Generate embedding
                embedding = await self.generate_embedding(chunk['code'])
                if embedding:
                    chunk['embedding'] = embedding
                
                all_chunks.append(chunk)
            
            # Generate chunks for classes
            for cls in parsed.get('classes', []):
                chunk = {
                    'type': 'class',
                    'fqn': f"{Path(file_path).stem}.{cls['name']}",
                    'file_path': file_path,
                    'start_line': cls['start_line'],
                    'end_line': cls['end_line'],
                    'code': '',  # Could extract class body
                    'summary': f"Class {cls['name']}",
                    'language': parsed['language'],
                }
                
                embedding = await self.generate_embedding(chunk['summary'])
                if embedding:
                    chunk['embedding'] = embedding
                
                all_chunks.append(chunk)
        
        print(f"✅ Generated {len(all_chunks)} chunks")
        return all_chunks


class StandaloneOpenSearch:
    """Self-contained OpenSearch client."""
    
    def __init__(self, host: str, index: str, use_ssl: bool = False):
        self.host = host
        self.index = index
        self.client = None
        
        if OPENSEARCH_AVAILABLE:
            try:
                host_parts = host.split(':')
                hostname = host_parts[0]
                port = int(host_parts[1]) if len(host_parts) > 1 else 9200
                
                self.client = OpenSearch(
                    hosts=[{'host': hostname, 'port': port}],
                    use_ssl=use_ssl,
                    verify_certs=False,
                )
                print(f"✅ Connected to OpenSearch: {host}")
            except Exception as e:
                print(f"⚠️ Failed to connect to OpenSearch: {e}")
    
    async def ensure_index(self, embedding_dim: int = 1536):
        """Ensure index exists with proper mapping."""
        if not self.client:
            return False
        
        try:
            if self.client.indices.exists(index=self.index):
                print(f"✅ Index '{self.index}' exists")
                return True
            
            mapping = {
                "mappings": {
                    "properties": {
                        "chunk_id": {"type": "keyword"},
                        "type": {"type": "keyword"},
                        "fqn": {"type": "keyword"},
                        "file_path": {"type": "keyword"},
                        "code": {"type": "text"},
                        "summary": {"type": "text"},
                        "embedding": {
                            "type": "knn_vector",
                            "dimension": embedding_dim,
                        }
                    }
                }
            }
            
            self.client.indices.create(index=self.index, body=mapping)
            print(f"✅ Created index '{self.index}'")
            return True
        except Exception as e:
            print(f"❌ Error ensuring index: {e}")
            return False
    
    async def index_chunks(self, chunks: List[Dict[str, Any]]):
        """Index chunks to OpenSearch."""
        if not self.client:
            print("⚠️ OpenSearch not available, skipping indexing")
            return
        
        await self.ensure_index()
        
        for i, chunk in enumerate(chunks):
            if 'embedding' not in chunk:
                continue
            
            doc = {
                'chunk_id': i,
                'type': chunk['type'],
                'fqn': chunk['fqn'],
                'file_path': chunk['file_path'],
                'code': chunk['code'],
                'summary': chunk['summary'],
                'embedding': chunk['embedding'],
            }
            
            try:
                self.client.index(index=self.index, id=i, body=doc)
            except Exception as e:
                print(f"⚠️ Error indexing chunk {i}: {e}")
        
        print(f"✅ Indexed {len(chunks)} chunks to OpenSearch")


class StandaloneGraphBuilder:
    """Self-contained graph builder using NetworkX."""
    
    def __init__(self):
        self.graph = None
        if NETWORKX_AVAILABLE:
            self.graph = nx.MultiDiGraph()
            print("✅ NetworkX graph initialized")
    
    def build_graph(self, chunks: List[Dict[str, Any]]):
        """Build graph from chunks."""
        if not self.graph:
            print("⚠️ NetworkX not available")
            return
        
        # Add nodes
        for i, chunk in enumerate(chunks):
            node_id = f"chunk_{i}"
            self.graph.add_node(
                node_id,
                type=chunk['type'],
                fqn=chunk['fqn'],
                file_path=chunk['file_path'],
            )
        
        # Add edges based on file relationships (simplified)
        for i, chunk1 in enumerate(chunks):
            for j, chunk2 in enumerate(chunks):
                if i == j:
                    continue
                
                # Same file = related
                if chunk1['file_path'] == chunk2['file_path']:
                    self.graph.add_edge(
                        f"chunk_{i}",
                        f"chunk_{j}",
                        relationship='in_file'
                    )
        
        print(f"✅ Graph built: {self.graph.number_of_nodes()} nodes, {self.graph.number_of_edges()} edges")
    
    def save_graph(self, output_path: str):
        """Save graph to pickle file."""
        if not self.graph:
            return
        
        with open(output_path, 'wb') as f:
            pickle.dump(self.graph, f)
        print(f"✅ Graph saved to {output_path}")
    
    def get_stats(self) -> Dict[str, int]:
        """Get graph statistics."""
        if not self.graph:
            return {'nodes': 0, 'edges': 0}
        
        return {
            'nodes': self.graph.number_of_nodes(),
            'edges': self.graph.number_of_edges()
        }


async def main():
    parser = argparse.ArgumentParser(description="Standalone repository indexer")
    parser.add_argument("--repo-path", required=True, help="Repository path")
    parser.add_argument("--output-dir", default="./output", help="Output directory")
    parser.add_argument("--opensearch-host", help="OpenSearch host (e.g., localhost:9200)")
    parser.add_argument("--opensearch-index", default="code_chunks", help="OpenSearch index name")
    parser.add_argument("--openai-api-key", help="OpenAI API key for embeddings")
    parser.add_argument("--embedding-model", default="text-embedding-3-small", help="Embedding model")
    args = parser.parse_args()
    
    # Create output directory
    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    
    # Initialize components
    indexer = StandaloneIndexer(
        openai_api_key=args.openai_api_key,
        embedding_model=args.embedding_model
    )
    
    # Process repository
    chunks = await indexer.process_repository(args.repo_path)
    
    # Save chunks to JSON
    chunks_file = output_dir / "chunks.json"
    with open(chunks_file, 'w') as f:
        json.dump(chunks, f, indent=2)
    print(f"✅ Saved chunks to {chunks_file}")
    
    # Index to OpenSearch if configured
    if args.opensearch_host:
        opensearch = StandaloneOpenSearch(args.opensearch_host, args.opensearch_index)
        await opensearch.index_chunks(chunks)
    
    # Build graph
    graph_builder = StandaloneGraphBuilder()
    graph_builder.build_graph(chunks)
    
    # Save graph
    graph_file = output_dir / "graph.pkl"
    graph_builder.save_graph(str(graph_file))
    
    stats = graph_builder.get_stats()
    print(f"\n✅ Complete! Stats: {stats}")


if __name__ == "__main__":
    asyncio.run(main())

