"""
Completely standalone script to parse a repository, generate OpenSearch chunks with embeddings,
and create a knowledge graph. No dependencies on project structure.

Usage (Full Repository):
  python standalone_build_repo_independent.py \
    --repo-path /path/to/repo \
    --output-dir ./output \
    --opensearch-host localhost:9200 \
    --opensearch-index code_chunks \
    --openai-api-key sk-...

Usage (Single File - Generate Chunks as JSON):
  python standalone_build_repo_independent.py \
    --file /path/to/file.java \
    --output chunks.json \
    --chunking-strategy class_metadata

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
            # Support both old and new tree-sitter API
            try:
                # New API (tree-sitter >= 0.20.0): Parser(language)
                parser = Parser(python_lang)
            except TypeError:
                # Old API (tree-sitter < 0.20.0): parser.set_language(language)
                parser = Parser()
                parser.set_language(python_lang)
            self.parsers['python'] = parser
        except Exception as e:
            print(f"⚠️ Failed to init Python parser: {e}")
        
        try:
            # Java
            java_lang = Language(tsjava.language())
            # Support both old and new tree-sitter API
            try:
                # New API (tree-sitter >= 0.20.0): Parser(language)
                parser = Parser(java_lang)
            except TypeError:
                # Old API (tree-sitter < 0.20.0): parser.set_language(language)
                parser = Parser()
                parser.set_language(java_lang)
            self.parsers['java'] = parser
        except Exception as e:
            print(f"⚠️ Failed to init Java parser: {e}")
        
        try:
            # JavaScript/TypeScript
            js_lang = Language(tsjavascript.language())
            # Support both old and new tree-sitter API
            try:
                # New API (tree-sitter >= 0.20.0): Parser(language)
                parser = Parser(js_lang)
            except TypeError:
                # Old API (tree-sitter < 0.20.0): parser.set_language(language)
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
    
    def __init__(
        self,
        openai_api_key: Optional[str] = None,
        embedding_model: str = "text-embedding-3-small",
        chunking_strategy: str = "class_metadata",
        max_chunk_size: int = 1000,
        enforce_chunk_size: bool = True,
        chunk_overlap_size: int = 50
    ):
        self.parser = StandaloneParser()
        self.embedding_client = None
        self.embedding_model = embedding_model
        self.chunking_strategy = chunking_strategy
        self.max_chunk_size = max_chunk_size
        self.enforce_chunk_size = enforce_chunk_size
        self.chunk_overlap_size = chunk_overlap_size
        
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
        """Process repository and generate chunks using configured strategy."""
        print(f"📁 Scanning repository: {repo_path}")
        print(f"   Strategy: {self.chunking_strategy}")
        print(f"   Max chunk size: {self.max_chunk_size}")
        print(f"   Enforce size: {self.enforce_chunk_size}")
        
        code_files = self.find_code_files(repo_path)
        print(f"   Found {len(code_files)} code files")
        
        all_chunks = []
        
        for file_path in code_files:
            parsed = self.parser.parse_file(file_path)
            if not parsed:
                continue
            
            # Generate chunks based on strategy
            file_chunks = self._generate_chunks_for_file(parsed, file_path)
            all_chunks.extend(file_chunks)
        
        # Generate embeddings for all chunks
        print(f"📊 Generated {len(all_chunks)} chunks, generating embeddings...")
        for chunk in all_chunks:
            embedding = await self.generate_embedding(chunk.get('code') or chunk.get('summary', ''))
            if embedding:
                chunk['embedding'] = embedding
        
        print(f"✅ Generated {len(all_chunks)} chunks with embeddings")
        return all_chunks
    
    def _generate_chunks_for_file(self, parsed: Dict[str, Any], file_path: str) -> List[Dict[str, Any]]:
        """Generate chunks for a file based on configured strategy."""
        strategy = self.chunking_strategy
        
        if strategy == "method_only":
            return self._generate_chunks_method_only(parsed, file_path)
        elif strategy == "class_metadata":
            return self._generate_chunks_class_metadata(parsed, file_path)
        elif strategy == "recursive":
            return self._generate_chunks_recursive(parsed, file_path)
        elif strategy == "sliding_window":
            return self._generate_chunks_sliding_window(parsed, file_path)
        elif strategy == "hybrid":
            return self._generate_chunks_hybrid(parsed, file_path)
        else:
            print(f"⚠️ Unknown strategy '{strategy}', using 'class_metadata'")
            return self._generate_chunks_class_metadata(parsed, file_path)
    
    def _generate_chunks_method_only(self, parsed: Dict[str, Any], file_path: str) -> List[Dict[str, Any]]:
        """Strategy 1: Method-only chunks."""
        chunks = []
        for func in parsed.get('functions', []):
            code = func.get('code', '')
            if self.enforce_chunk_size and len(code) > self.max_chunk_size:
                # Split large methods
                method_chunks = self._split_large_code(code, func, file_path, 'method')
                chunks.extend(method_chunks)
            else:
                chunk = self._create_method_chunk(func, parsed, file_path)
                chunks.append(chunk)
        return chunks
    
    def _generate_chunks_class_metadata(self, parsed: Dict[str, Any], file_path: str) -> List[Dict[str, Any]]:
        """Strategy 2: Method chunks + class metadata (recommended)."""
        chunks = []
        
        # Method chunks
        for func in parsed.get('functions', []):
            code = func.get('code', '')
            if self.enforce_chunk_size and len(code) > self.max_chunk_size:
                method_chunks = self._split_large_code(code, func, file_path, 'method')
                chunks.extend(method_chunks)
            else:
                chunk = self._create_method_chunk(func, parsed, file_path)
                chunks.append(chunk)
        
        # Class metadata chunks (signature only, no full body)
        for cls in parsed.get('classes', []):
            chunk = self._create_class_metadata_chunk(cls, parsed, file_path)
            chunks.append(chunk)
        
        return chunks
    
    def _generate_chunks_recursive(self, parsed: Dict[str, Any], file_path: str) -> List[Dict[str, Any]]:
        """Strategy 3: Recursive splitting for large code."""
        chunks = []
        
        # Method chunks with recursive splitting
        for func in parsed.get('functions', []):
            code = func.get('code', '')
            if self.enforce_chunk_size and len(code) > self.max_chunk_size:
                method_chunks = self._recursive_split_code(code, func, file_path, 'method')
                chunks.extend(method_chunks)
            else:
                chunk = self._create_method_chunk(func, parsed, file_path)
                chunks.append(chunk)
        
        # Class chunks with recursive splitting
        for cls in parsed.get('classes', []):
            code = cls.get('code', '')
            if self.enforce_chunk_size and len(code) > self.max_chunk_size:
                class_chunks = self._recursive_split_code(code, cls, file_path, 'class')
                chunks.extend(class_chunks)
            else:
                chunk = self._create_class_metadata_chunk(cls, parsed, file_path)
                chunks.append(chunk)
        
        return chunks
    
    def _generate_chunks_sliding_window(self, parsed: Dict[str, Any], file_path: str) -> List[Dict[str, Any]]:
        """Strategy 4: Sliding window for large classes."""
        chunks = []
        
        # Method chunks
        for func in parsed.get('functions', []):
            code = func.get('code', '')
            if self.enforce_chunk_size and len(code) > self.max_chunk_size:
                method_chunks = self._split_large_code(code, func, file_path, 'method')
                chunks.extend(method_chunks)
            else:
                chunk = self._create_method_chunk(func, parsed, file_path)
                chunks.append(chunk)
        
        # Class chunks with sliding window
        for cls in parsed.get('classes', []):
            code = cls.get('code', '')
            if self.enforce_chunk_size and len(code) > self.max_chunk_size:
                window_chunks = self._create_sliding_windows(code, cls, file_path)
                chunks.extend(window_chunks)
            else:
                chunk = self._create_class_metadata_chunk(cls, parsed, file_path)
                chunks.append(chunk)
        
        return chunks
    
    def _generate_chunks_hybrid(self, parsed: Dict[str, Any], file_path: str) -> List[Dict[str, Any]]:
        """Strategy 5: Method + class metadata + file chunks (small files only)."""
        chunks = []
        
        # Method chunks
        for func in parsed.get('functions', []):
            code = func.get('code', '')
            if self.enforce_chunk_size and len(code) > self.max_chunk_size:
                method_chunks = self._split_large_code(code, func, file_path, 'method')
                chunks.extend(method_chunks)
            else:
                chunk = self._create_method_chunk(func, parsed, file_path)
                chunks.append(chunk)
        
        # Class metadata chunks
        for cls in parsed.get('classes', []):
            chunk = self._create_class_metadata_chunk(cls, parsed, file_path)
            chunks.append(chunk)
        
        # File chunk (only for small files)
        file_content = parsed.get('file_content', '')
        if file_content and len(file_content) <= self.max_chunk_size:
            chunk = {
                'type': 'file',
                'fqn': file_path,
                'file_path': file_path,
                'start_line': 1,
                'end_line': len(file_content.split('\n')),
                'code': file_content,
                'summary': f"File {Path(file_path).name}",
                'language': parsed.get('language', 'unknown'),
            }
            chunks.append(chunk)
        
        return chunks
    
    def _create_method_chunk(self, func: Dict[str, Any], parsed: Dict[str, Any], file_path: str) -> Dict[str, Any]:
        """Create a method chunk."""
        return {
            'type': 'method',
            'fqn': f"{Path(file_path).stem}.{func['name']}",
            'file_path': file_path,
            'start_line': func.get('start_line', 1),
            'end_line': func.get('end_line', 1),
            'code': func.get('code', ''),
            'summary': f"Method {func['name']}",
            'language': parsed.get('language', 'unknown'),
        }
    
    def _create_class_metadata_chunk(self, cls: Dict[str, Any], parsed: Dict[str, Any], file_path: str) -> Dict[str, Any]:
        """Create a class metadata chunk (signature only, no full body)."""
        # Extract only class signature, not full body
        class_code = cls.get('code', '')
        signature = class_code.split('{')[0] if '{' in class_code else class_code[:200]
        
        return {
            'type': 'class',
            'fqn': f"{Path(file_path).stem}.{cls['name']}",
            'file_path': file_path,
            'start_line': cls.get('start_line', 1),
            'end_line': cls.get('start_line', 1),  # Just signature line
            'code': signature,  # Only signature, not full body
            'summary': f"Class {cls['name']}",
            'language': parsed.get('language', 'unknown'),
        }
    
    def _split_large_code(self, code: str, entity: Dict[str, Any], file_path: str, entity_type: str) -> List[Dict[str, Any]]:
        """Split large code into smaller chunks."""
        chunks = []
        lines = code.split('\n')
        lines_per_chunk = self.max_chunk_size // 50  # Rough estimate
        
        for i in range(0, len(lines), lines_per_chunk):
            chunk_lines = lines[i:i + lines_per_chunk]
            chunk_code = '\n'.join(chunk_lines)
            chunk_start = entity.get('start_line', 1) + i
            chunk_end = entity.get('start_line', 1) + i + len(chunk_lines) - 1
            
            chunks.append({
                'type': entity_type,
                'fqn': f"{Path(file_path).stem}.{entity['name']}_part{i // lines_per_chunk}",
                'file_path': file_path,
                'start_line': chunk_start,
                'end_line': chunk_end,
                'code': chunk_code,
                'summary': f"{entity_type.title()} {entity['name']} (part {i // lines_per_chunk + 1})",
                'language': 'unknown',
            })
        
        return chunks
    
    def _recursive_split_code(self, code: str, entity: Dict[str, Any], file_path: str, entity_type: str) -> List[Dict[str, Any]]:
        """Recursively split code by logical blocks."""
        if len(code) <= self.max_chunk_size:
            return [{
                'type': entity_type,
                'fqn': f"{Path(file_path).stem}.{entity['name']}",
                'file_path': file_path,
                'start_line': entity.get('start_line', 1),
                'end_line': entity.get('end_line', 1),
                'code': code,
                'summary': f"{entity_type.title()} {entity['name']}",
                'language': 'unknown',
            }]
        
        # Try to split by logical blocks
        blocks = self._extract_logical_blocks(code)
        if len(blocks) > 1:
            chunks = []
            current_start = entity.get('start_line', 1)
            for block in blocks:
                block_code = '\n'.join(block)
                sub_chunks = self._recursive_split_code(block_code, entity, file_path, entity_type)
                chunks.extend(sub_chunks)
                current_start += len(block)
            return chunks
        
        # Fallback: split by lines
        return self._split_large_code(code, entity, file_path, entity_type)
    
    def _extract_logical_blocks(self, code: str) -> List[List[str]]:
        """Extract logical blocks (if/else, try/catch, loops) from code."""
        lines = code.split('\n')
        blocks = []
        current_block = []
        indent_level = 0
        in_block = False
        
        for line in lines:
            stripped = line.lstrip()
            current_indent = len(line) - len(stripped)
            
            if any(kw in stripped for kw in ['if (', 'else', 'try {', 'catch', 'for (', 'while (', 'switch']):
                if current_block and current_indent <= indent_level:
                    blocks.append(current_block)
                    current_block = [line]
                else:
                    current_block.append(line)
                in_block = True
                indent_level = current_indent
            elif in_block and current_indent <= indent_level and stripped.startswith('}'):
                current_block.append(line)
                blocks.append(current_block)
                current_block = []
                in_block = False
            else:
                current_block.append(line)
        
        if current_block:
            blocks.append(current_block)
        
        return blocks if blocks else [lines]
    
    def _create_sliding_windows(self, code: str, entity: Dict[str, Any], file_path: str) -> List[Dict[str, Any]]:
        """Create overlapping windows for large code blocks."""
        chunks = []
        lines = code.split('\n')
        window_size = self.max_chunk_size // 50
        overlap_lines = self.chunk_overlap_size // 50
        
        for i in range(0, len(lines), window_size - overlap_lines):
            window_lines = lines[i:min(i + window_size, len(lines))]
            window_code = '\n'.join(window_lines)
            window_start = entity.get('start_line', 1) + i
            window_end = entity.get('start_line', 1) + i + len(window_lines) - 1
            
            chunks.append({
                'type': 'class',
                'fqn': f"{Path(file_path).stem}.{entity['name']}_window{i // (window_size - overlap_lines)}",
                'file_path': file_path,
                'start_line': window_start,
                'end_line': window_end,
                'code': window_code,
                'summary': f"Class {entity['name']} (window {i // (window_size - overlap_lines) + 1})",
                'language': 'unknown',
            })
        
        return chunks


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


async def generate_chunks_for_file(
    file_path: str,
    output_path: str,
    chunking_strategy: str = "class_metadata",
    max_chunk_size: int = 1000,
    enforce_size: bool = True,
    chunk_overlap_size: int = 50
):
    """
    Generate chunks for a single file and save to JSON.
    
    Args:
        file_path: Path to the file to process
        output_path: Output JSON file path
        chunking_strategy: Chunking strategy to use
        max_chunk_size: Maximum chunk size in characters
        enforce_size: Whether to enforce chunk size limits
        chunk_overlap_size: Overlap size for sliding_window strategy
    """
    file_path_obj = Path(file_path)
    if not file_path_obj.exists():
        raise SystemExit(f"❌ File not found: {file_path}")
    
    print(f"📄 Processing file: {file_path}")
    print(f"   Strategy: {chunking_strategy}")
    print(f"   Max chunk size: {max_chunk_size}")
    print(f"   Enforce size: {enforce_size}")
    
    # Initialize indexer with specified strategy
    indexer = StandaloneIndexer(
        openai_api_key=None,  # Not needed for chunk generation
        embedding_model="text-embedding-3-small",
        chunking_strategy=chunking_strategy,
        max_chunk_size=max_chunk_size,
        enforce_chunk_size=enforce_size,
        chunk_overlap_size=chunk_overlap_size
    )
    
    # Parse file
    parsed = indexer.parser.parse_file(str(file_path))
    if not parsed:
        raise SystemExit(f"❌ Failed to parse file: {file_path}")
    
    # Read file content
    with open(file_path, 'r', encoding='utf-8', errors='ignore') as f:
        file_content = f.read()
    
    print(f"   File size: {len(file_content)} characters")
    print(f"   Language: {parsed.get('language', 'unknown')}")
    print(f"   Classes found: {len(parsed.get('classes', []))}")
    print(f"   Methods found: {len(parsed.get('functions', []))}")
    
    # Generate chunks for this file
    file_chunks = indexer._generate_chunks_for_file(parsed, str(file_path))
    
    print(f"✅ Generated {len(file_chunks)} chunks")
    
    # Prepare output data
    output_data = {
        "file_path": str(file_path),
        "language": parsed.get('language', 'unknown'),
        "chunking_strategy": chunking_strategy,
        "max_chunk_size": max_chunk_size,
        "enforce_size": enforce_size,
        "chunk_overlap_size": chunk_overlap_size,
        "total_chunks": len(file_chunks),
        "chunks": []
    }
    
    # Convert chunks to JSON-serializable format
    for chunk in file_chunks:
        chunk_data = {
            "type": chunk.get('type', 'unknown'),
            "fqn": chunk.get('fqn', ''),
            "file_path": chunk.get('file_path', str(file_path)),
            "start_line": chunk.get('start_line', 1),
            "end_line": chunk.get('end_line', 1),
            "code": chunk.get('code', ''),
            "summary": chunk.get('summary', ''),
            "code_size": len(chunk.get('code', '')),
            "language": chunk.get('language', parsed.get('language', 'unknown')),
        }
        
        output_data["chunks"].append(chunk_data)
    
    # Save to JSON file
    output_path_obj = Path(output_path)
    output_path_obj.parent.mkdir(parents=True, exist_ok=True)
    
    with open(output_path_obj, 'w', encoding='utf-8') as f:
        json.dump(output_data, f, indent=2, ensure_ascii=False)
    
    print(f"✅ Chunks saved to: {output_path}")
    print(f"   Total chunks: {len(file_chunks)}")
    
    # Print chunk statistics
    if file_chunks:
        chunk_types = {}
        for chunk in file_chunks:
            chunk_type = chunk.get('type', 'unknown')
            chunk_types[chunk_type] = chunk_types.get(chunk_type, 0) + 1
        print(f"   Chunk types: {chunk_types}")
        
        chunk_sizes = [len(c.get('code', '')) for c in file_chunks]
        avg_size = sum(chunk_sizes) / len(chunk_sizes)
        max_size = max(chunk_sizes)
        min_size = min(chunk_sizes)
        print(f"   Chunk sizes: min={min_size}, avg={avg_size:.0f}, max={max_size}")


async def main():
    parser = argparse.ArgumentParser(description="Standalone repository indexer or single file chunk generator")
    
    # Single file mode arguments
    parser.add_argument("--file", help="Path to a specific file to generate chunks for (single file mode)")
    parser.add_argument("--output", default="chunks.json", help="Output JSON file path for single file mode (default: chunks.json)")
    
    # Full repository mode arguments
    parser.add_argument("--repo-path", help="Repository path (required for full repository mode)")
    parser.add_argument("--output-dir", default="./output", help="Output directory (for full repository mode)")
    parser.add_argument("--opensearch-host", help="OpenSearch host (e.g., localhost:9200)")
    parser.add_argument("--opensearch-index", default="code_chunks", help="OpenSearch index name")
    parser.add_argument("--openai-api-key", help="OpenAI API key for embeddings")
    parser.add_argument("--embedding-model", default="text-embedding-3-small", help="Embedding model")
    
    # Common arguments
    parser.add_argument(
        "--chunking-strategy",
        default="class_metadata",
        choices=["method_only", "class_metadata", "recursive", "sliding_window", "hybrid"],
        help="Chunking strategy (default: class_metadata)"
    )
    parser.add_argument("--max-chunk-size", type=int, default=1000, help="Maximum chunk size in characters (default: 1000)")
    parser.add_argument("--enforce-chunk-size", action="store_true", default=True, help="Enforce chunk size limits (default: True)")
    parser.add_argument("--chunk-overlap-size", type=int, default=50, help="Overlap size for sliding_window strategy (default: 50)")
    
    args = parser.parse_args()
    
    # Single file mode
    if args.file:
        await generate_chunks_for_file(
            file_path=args.file,
            output_path=args.output,
            chunking_strategy=args.chunking_strategy,
            max_chunk_size=args.max_chunk_size,
            enforce_size=args.enforce_chunk_size,
            chunk_overlap_size=args.chunk_overlap_size
        )
        return
    
    # Full repository mode
    if not args.repo_path:
        raise SystemExit("❌ Either --file (single file mode) or --repo-path (full repository mode) is required.")
    
    # Create output directory
    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    
    # Initialize components
    indexer = StandaloneIndexer(
        openai_api_key=args.openai_api_key,
        embedding_model=args.embedding_model,
        chunking_strategy=args.chunking_strategy,
        max_chunk_size=args.max_chunk_size,
        enforce_chunk_size=args.enforce_chunk_size,
        chunk_overlap_size=args.chunk_overlap_size
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

