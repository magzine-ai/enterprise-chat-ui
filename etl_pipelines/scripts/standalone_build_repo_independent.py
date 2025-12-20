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

# Advanced ETL features
try:
    from tqdm import tqdm
    TQDM_AVAILABLE = True
except ImportError:
    TQDM_AVAILABLE = False
    print("⚠️ tqdm not available. Install: pip install tqdm (for progress bars)")

try:
    from joblib import Parallel, delayed
    JOBLIB_AVAILABLE = True
except ImportError:
    JOBLIB_AVAILABLE = False
    print("⚠️ joblib not available. Install: pip install joblib (for parallel processing)")

try:
    from pydantic import BaseModel, Field, field_validator
    PYDANTIC_AVAILABLE = True
except ImportError:
    PYDANTIC_AVAILABLE = False
    print("⚠️ pydantic not available. Install: pip install pydantic (for data validation)")

try:
    import pandas as pd
    PANDAS_AVAILABLE = True
except ImportError:
    PANDAS_AVAILABLE = False
    print("⚠️ pandas not available. Install: pip install pandas (for statistics)")


# Pydantic models for data validation
if PYDANTIC_AVAILABLE:
    class CodeChunk(BaseModel):
        """Validated code chunk model."""
        type: str = Field(..., description="Chunk type (method, class, file)")
        fqn: str = Field(..., description="Fully qualified name")
        file_path: str = Field(..., description="File path")
        start_line: int = Field(..., ge=1, description="Start line number")
        end_line: int = Field(..., ge=1, description="End line number")
        code: str = Field(..., description="Code content")
        summary: Optional[str] = Field(None, description="Chunk summary")
        language: Optional[str] = Field(None, description="Programming language")
        embedding: Optional[List[float]] = Field(None, description="Embedding vector")
        
        @field_validator('end_line')
        @classmethod
        def end_after_start(cls, v, info):
            # Get start_line from the model data
            if hasattr(info, 'data') and 'start_line' in info.data:
                if v < info.data['start_line']:
                    raise ValueError('end_line must be >= start_line')
            return v
        
        class Config:
            extra = 'allow'  # Allow additional fields
else:
    # Fallback if pydantic not available
    class CodeChunk:
        def __init__(self, **kwargs):
            self.__dict__.update(kwargs)
        
        def dict(self):
            return self.__dict__


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
        chunk_overlap_size: int = 50,
        batch_size: int = 100,
        n_jobs: int = -1,
        checkpoint_file: Optional[str] = None
    ):
        self.parser = StandaloneParser()
        self.embedding_client = None
        self.embedding_model = embedding_model
        self.chunking_strategy = chunking_strategy
        self.max_chunk_size = max_chunk_size
        self.enforce_chunk_size = enforce_chunk_size
        self.chunk_overlap_size = chunk_overlap_size
        self.batch_size = batch_size
        self.n_jobs = n_jobs  # -1 means use all CPUs
        self.checkpoint_file = checkpoint_file
        
        if OPENAI_AVAILABLE and openai_api_key:
            self.embedding_client = AsyncOpenAI(api_key=openai_api_key)
    
    async def generate_embedding(self, text: str) -> Optional[List[float]]:
        """Generate embedding for a single text."""
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
    
    async def generate_embeddings_batch(self, texts: List[str]) -> List[Optional[List[float]]]:
        """Generate embeddings for a batch of texts (more efficient)."""
        if not self.embedding_client or not texts:
            return [None] * len(texts)
        
        all_embeddings = []
        
        # Process in batches to avoid rate limits
        for i in range(0, len(texts), self.batch_size):
            batch = texts[i:i + self.batch_size]
            try:
                response = await self.embedding_client.embeddings.create(
                    model=self.embedding_model,
                    input=batch
                )
                batch_embeddings = [item.embedding for item in response.data]
                all_embeddings.extend(batch_embeddings)
            except Exception as e:
                print(f"⚠️ Error generating batch embeddings: {e}")
                # Add None for failed batch
                all_embeddings.extend([None] * len(batch))
        
        return all_embeddings
    
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
    
    def _save_checkpoint(self, chunks: List[Dict[str, Any]], processed_files: Set[str], checkpoint_file: str):
        """Save processing checkpoint."""
        checkpoint = {
            'chunks': chunks,
            'processed_files': list(processed_files),
            'timestamp': datetime.now().isoformat(),
            'total_files': len(processed_files),
            'total_chunks': len(chunks)
        }
        with open(checkpoint_file, 'w') as f:
            json.dump(checkpoint, f, indent=2)
    
    def _load_checkpoint(self, checkpoint_file: str) -> tuple[List[Dict[str, Any]], Set[str]]:
        """Load processing checkpoint."""
        if not Path(checkpoint_file).exists():
            return [], set()
        
        try:
            with open(checkpoint_file, 'r') as f:
                checkpoint = json.load(f)
            return checkpoint.get('chunks', []), set(checkpoint.get('processed_files', []))
        except Exception as e:
            print(f"⚠️ Error loading checkpoint: {e}")
            return [], set()
    
    def _process_file_wrapper(self, file_path: str) -> List[Dict[str, Any]]:
        """Wrapper for parallel file processing."""
        # Create a new parser instance for each worker (parsers can't be pickled)
        parser = StandaloneParser()
        parsed = parser.parse_file(file_path)
        if not parsed:
            return []
        # Create a temporary indexer instance for chunk generation
        temp_indexer = StandaloneIndexer(
            chunking_strategy=self.chunking_strategy,
            max_chunk_size=self.max_chunk_size,
            enforce_chunk_size=self.enforce_chunk_size,
            chunk_overlap_size=self.chunk_overlap_size
        )
        return temp_indexer._generate_chunks_for_file(parsed, file_path)
    
    async def process_repository(self, repo_path: str) -> List[Dict[str, Any]]:
        """Process repository and generate chunks using configured strategy."""
        print(f"📁 Scanning repository: {repo_path}")
        print(f"   Strategy: {self.chunking_strategy}")
        print(f"   Max chunk size: {self.max_chunk_size}")
        print(f"   Enforce size: {self.enforce_chunk_size}")
        if JOBLIB_AVAILABLE:
            print(f"   Parallel processing: {self.n_jobs} jobs")
        
        code_files = self.find_code_files(repo_path)
        print(f"   Found {len(code_files)} code files")
        
        # Load checkpoint if available
        processed_files = set()
        all_chunks = []
        if self.checkpoint_file:
            all_chunks, processed_files = self._load_checkpoint(self.checkpoint_file)
            if processed_files:
                print(f"   Resuming from checkpoint: {len(processed_files)} files already processed")
                code_files = [f for f in code_files if f not in processed_files]
                print(f"   Remaining files: {len(code_files)}")
        
        # Process files (parallel if joblib available)
        # Note: For now, use sequential processing to avoid pickling issues with TreeSitter parsers
        # Parallel processing can be added later with proper serialization
        if False and JOBLIB_AVAILABLE and len(code_files) > 1:
            # Parallel processing (disabled due to pickling issues)
            file_chunks_list = Parallel(n_jobs=self.n_jobs)(
                delayed(self._process_file_wrapper)(file_path)
                for file_path in (tqdm(code_files, desc="Processing files") if TQDM_AVAILABLE else code_files)
            )
            # Flatten results
            for file_path, file_chunks in zip(code_files, file_chunks_list):
                all_chunks.extend(file_chunks)
                processed_files.add(file_path)
                # Save checkpoint periodically
                if self.checkpoint_file and len(processed_files) % 10 == 0:
                    self._save_checkpoint(all_chunks, processed_files, self.checkpoint_file)
        else:
            # Sequential processing with progress bar
            file_iter = tqdm(code_files, desc="Processing files") if TQDM_AVAILABLE else code_files
            for file_path in file_iter:
                parsed = self.parser.parse_file(file_path)
                if not parsed:
                    continue
                
                file_chunks = self._generate_chunks_for_file(parsed, file_path)
                all_chunks.extend(file_chunks)
                processed_files.add(file_path)
                
                # Save checkpoint periodically
                if self.checkpoint_file and len(processed_files) % 10 == 0:
                    self._save_checkpoint(all_chunks, processed_files, self.checkpoint_file)
        
        # Validate chunks with pydantic if available
        if PYDANTIC_AVAILABLE:
            print(f"📊 Validating {len(all_chunks)} chunks...")
            validated_chunks = []
            for chunk in (tqdm(all_chunks, desc="Validating chunks") if TQDM_AVAILABLE else all_chunks):
                try:
                    validated = CodeChunk(**chunk)
                    validated_chunks.append(validated.dict())
                except Exception as e:
                    print(f"⚠️ Validation error for chunk {chunk.get('fqn', 'unknown')}: {e}")
                    validated_chunks.append(chunk)  # Keep original if validation fails
            all_chunks = validated_chunks
        
        # Generate embeddings in batches
        if self.embedding_client:
            print(f"📊 Generating embeddings for {len(all_chunks)} chunks...")
            texts = [chunk.get('code') or chunk.get('summary', '') for chunk in all_chunks]
            embeddings = await self.generate_embeddings_batch(texts)
            
            # Add embeddings to chunks with progress bar
            embed_iter = tqdm(zip(all_chunks, embeddings), total=len(all_chunks), desc="Adding embeddings") if TQDM_AVAILABLE else zip(all_chunks, embeddings)
            for chunk, embedding in embed_iter:
                if embedding:
                    chunk['embedding'] = embedding
        
        # Generate statistics with pandas if available
        if PANDAS_AVAILABLE and all_chunks:
            print(f"\n📈 Statistics:")
            df = pd.DataFrame(all_chunks)
            print(f"   Total chunks: {len(df)}")
            print(f"   Chunks by type:\n{df['type'].value_counts().to_string()}")
            if 'code' in df.columns:
                code_lengths = df['code'].str.len()
                print(f"   Code size - min: {code_lengths.min()}, avg: {code_lengths.mean():.0f}, max: {code_lengths.max()}")
            if 'file_path' in df.columns:
                print(f"   Files processed: {df['file_path'].nunique()}")
        
        # Final checkpoint save
        if self.checkpoint_file:
            self._save_checkpoint(all_chunks, processed_files, self.checkpoint_file)
            print(f"✅ Checkpoint saved to {self.checkpoint_file}")
        
        print(f"✅ Generated {len(all_chunks)} chunks")
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
        """
        Create a class metadata chunk: signature + fields + static blocks + instance blocks.
        Does NOT include method bodies (those are in method chunks).
        """
        file_content = parsed.get('file_content', '')
        class_code = cls.get('code', '')
        lines = file_content.split('\n') if file_content else class_code.split('\n')
        start_line = cls.get('start_line', 1)
        
        # Extract class signature
        signature = class_code.split('{')[0] if '{' in class_code else class_code[:200]
        if '{' in class_code:
            signature += ' {'
        
        # Build class-level code parts
        class_level_parts = [signature]
        language = parsed.get('language', 'java')
        
        # Extract class-level code for Java
        if language == 'java' and file_content:
            # Extract static blocks
            static_pattern = r'static\s*\{[^{}]*(?:\{[^{}]*\}[^{}]*)*\}'
            for match in re.finditer(static_pattern, class_code, re.MULTILINE | re.DOTALL):
                static_code = match.group(0).strip()
                if static_code:
                    class_level_parts.append(static_code)
            
            # Extract instance initializer blocks (not static, not methods)
            instance_pattern = r'(?<!static\s)(?<!\)\s)\{[^{}]*(?:\{[^{}]*\}[^{}]*)*\}'
            for match in re.finditer(instance_pattern, class_code, re.MULTILINE):
                block_start = match.start()
                before_block = class_code[:block_start].rstrip()
                if not before_block.endswith(')') and not before_block.endswith(';'):
                    instance_code = match.group(0).strip()
                    if instance_code and instance_code != '{':
                        class_level_parts.append(instance_code)
            
            # Extract class fields (variable declarations)
            # Pattern: modifiers type name [= value];
            field_pattern = r'(?:public|private|protected|static|final|transient|volatile)\s+[\w<>,\s\[\]]+\s+\w+\s*(?:=\s*[^;{]+)?;'
            field_matches = list(re.finditer(field_pattern, class_code, re.MULTILINE))
            
            # Get method start lines to exclude fields inside methods
            method_starts = []
            for func in parsed.get('functions', []):
                if func.get('class_name') == cls.get('name'):
                    method_starts.append(func.get('start_line', 0))
            
            for match in field_matches:
                field_code = match.group(0).strip()
                field_line = start_line + class_code[:match.start()].count('\n')
                
                # Only include if it's before any method (class-level field)
                if not method_starts or field_line < min(method_starts) if method_starts else True:
                    class_level_parts.append(field_code)
        
        # Combine all parts
        class_metadata_code = '\n'.join(class_level_parts)
        
        # Enforce size limit if needed
        if self.enforce_chunk_size and len(class_metadata_code) > self.max_chunk_size:
            # Truncate but keep signature
            remaining_size = self.max_chunk_size - len(signature) - 50
            if remaining_size > 0:
                truncated = class_metadata_code[:self.max_chunk_size]
                class_metadata_code = truncated + "\n// ... (truncated)"
            else:
                class_metadata_code = signature  # Fallback to just signature if too large
        
        # Calculate end line
        code_lines = class_metadata_code.split('\n')
        end_line = start_line + len(code_lines) - 1
        
        return {
            'type': 'class',
            'fqn': f"{Path(file_path).stem}.{cls['name']}",
            'file_path': file_path,
            'start_line': start_line,
            'end_line': end_line,  # Updated to include class-level code
            'code': class_metadata_code,  # Signature + fields + static/instance blocks
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
    
    # Advanced ETL features
    parser.add_argument("--batch-size", type=int, default=100, help="Batch size for embedding generation (default: 100)")
    parser.add_argument("--n-jobs", type=int, default=-1, help="Number of parallel jobs for file processing (-1 = all CPUs, default: -1)")
    parser.add_argument("--checkpoint-file", help="Checkpoint file path for resuming interrupted processing (optional)")
    parser.add_argument("--resume", action="store_true", help="Resume from checkpoint if available")
    
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
    
    # Setup checkpoint file
    checkpoint_file = args.checkpoint_file
    if args.resume and not checkpoint_file:
        checkpoint_file = str(output_dir / "checkpoint.json")
    
    # Initialize components
    indexer = StandaloneIndexer(
        openai_api_key=args.openai_api_key,
        embedding_model=args.embedding_model,
        chunking_strategy=args.chunking_strategy,
        max_chunk_size=args.max_chunk_size,
        enforce_chunk_size=args.enforce_chunk_size,
        chunk_overlap_size=args.chunk_overlap_size,
        batch_size=args.batch_size,
        n_jobs=args.n_jobs,
        checkpoint_file=checkpoint_file
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

