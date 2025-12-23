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
import hashlib
from pathlib import Path
from typing import List, Dict, Any, Optional, Set
from datetime import datetime
from concurrent.futures import ThreadPoolExecutor, as_completed

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

# Azure OpenAI Embeddings Service
try:
    from azure.identity import CertificateCredential
    from azure.core.exceptions import ClientAuthenticationError
    from langchain_openai import AzureOpenAIEmbeddings
    import configparser
    AZURE_EMBEDDINGS_AVAILABLE = True
except ImportError:
    AZURE_EMBEDDINGS_AVAILABLE = False
    print("⚠️ Azure embeddings not available. Install: pip install azure-identity langchain-openai")

# OpenSearch
try:
    from opensearchpy import OpenSearch, RequestsHttpConnection
    OPENSEARCH_AVAILABLE = True
except ImportError:
    OPENSEARCH_AVAILABLE = False
    print("⚠️ OpenSearch not available. Install: pip install opensearch-py")

# AWS Authentication for OpenSearch
try:
    from aws_requests_auth.aws_auth import AWSRequestsAuth
    from boto3 import session
    AWS_AUTH_AVAILABLE = True
except ImportError:
    AWS_AUTH_AVAILABLE = False
    print("⚠️ AWS authentication not available. Install: pip install aws-requests-auth boto3")

# NetworkX for graph
try:
    import networkx as nx
    NETWORKX_AVAILABLE = True
except ImportError:
    NETWORKX_AVAILABLE = False
    print("⚠️ NetworkX not available. Install: pip install networkx")

# TigerGraph for graph database (optional)
try:
    from pyTigerGraph import TigerGraphConnection
    TIGERGRAPH_AVAILABLE = True
except ImportError:
    TIGERGRAPH_AVAILABLE = False
    print("⚠️ TigerGraph not available. Install: pip install pyTigerGraph (optional)")

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


class EmbeddingService:
    """Azure OpenAI Embedding Service with certificate-based authentication."""
    
    def __init__(self, user_sid: str = "default_user", cert_path: Optional[str] = None, config_path: Optional[str] = None):
        """
        Initialize the embedding service.
        
        Args:
            user_sid: User session ID for multi-tenancy
            cert_path: Path to certificate file (optional, will try default locations)
            config_path: Path to config.ini file (optional, defaults to script directory)
        """
        self.config = self.load_config(config_path)
        self.user_sid = user_sid
        self.access_token = self.get_access_token(cert_path, config_path)
        if self.access_token:
            print(f"✅ EmbeddingService access token obtained")
        self.embeddings = self.create_embeddings_client()
    
    @staticmethod
    def load_config(config_path: Optional[str] = None):
        """Load configuration from config.ini file."""
        if config_path is None:
            current_dir = os.path.dirname(__file__)
            file_path = os.path.join(current_dir, 'config.ini')
        else:
            file_path = config_path
        
        print(f"Loading config from {file_path}")
        
        if not os.path.exists(file_path):
            raise FileNotFoundError(f"Config file not found: {file_path}")
        
        llm_config = configparser.ConfigParser()
        llm_config.read(file_path)
        return llm_config
    
    @staticmethod
    def get_access_token(cert_path: Optional[str] = None, config_path: Optional[str] = None):
        """Obtain access token using certificate-based authentication."""
        print("Obtaining access token.")
        config = EmbeddingService.load_config(config_path)
        current_dir = os.path.dirname(__file__)
        
        try:
            # Certificate path - use provided path or default location
            if cert_path is None:
                cert_path = os.path.join(current_dir, "..", "..", "discoveryeng.dev.azure.jpmchase.net.pem")
            
            # Try to find certificate if default path doesn't exist
            if not os.path.exists(cert_path):
                # Try alternative locations
                alt_paths = [
                    os.path.join(current_dir, "discoveryeng.dev.azure.jpmchase.net.pem"),
                    os.path.join(os.path.dirname(current_dir), "discoveryeng.dev.azure.jpmchase.net.pem"),
                ]
                for alt_path in alt_paths:
                    if os.path.exists(alt_path):
                        cert_path = alt_path
                        break
                else:
                    raise FileNotFoundError(f"Certificate file not found: {cert_path}")
            
            print(f"Certificate path: {cert_path}")
            
            credential = CertificateCredential(
                tenant_id=config['azure_openai']['azure_tenant_id'],
                client_id=config['azure_openai']['azure_client_id'],
                certificate_path=cert_path
            )
            
            access_token = credential.get_token("https://cognitiveservices.azure.com/.default").token
            return access_token
        except ClientAuthenticationError as e:
            error_msg = str(e) if hasattr(e, '__str__') else getattr(e, 'message', 'Unknown error')
            print(f"Authentication failed: {error_msg}")
            return None
        except Exception as e:
            print(f"An unexpected error occurred: {e}")
            return None
    
    def create_embeddings_client(self):
        """Create Azure OpenAI Embeddings client."""
        if not self.access_token:
            raise Exception("No access token available for Azure OpenAI Embeddings.")
        
        return AzureOpenAIEmbeddings(
            azure_endpoint="https://llm-multitenancy-exp.jpmchase.net/ver2/",
            openai_api_version="2024-10-21",
            openai_api_key="b3d265714de0417cbd8af5c26b6013b1",
            openai_api_type="azure",
            default_headers={
                "Authorization": f"Bearer {self.access_token}",
                "user_sid": self.user_sid
            }
        )
    
    @staticmethod
    def chunk_list(data, chunk_size):
        """Split a list into chunks of specified size."""
        for i in range(0, len(data), chunk_size):
            yield data[i:i + chunk_size]
    
    def embed_text(self, text: str) -> List[float]:
        """Embed a single string using AzureOpenAIEmbeddings."""
        return self.embeddings.embed_query(text)
    
    def embed_texts(self, texts: list) -> List[List[float]]:
        """Embed a list of strings using AzureOpenAIEmbeddings."""
        return self.embeddings.embed_documents(texts)


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
                'file_content': content,  # Store full content for later analysis
                'functions': self._extract_functions(root, content, language),
                'classes': self._extract_classes(root, content, language),
                'imports': self._extract_imports(root, content, language),
            }
        except Exception as e:
            print(f"⚠️ Error parsing {file_path}: {e}")
            return None
    
    def _extract_functions(self, root, content: str, language: str) -> List[Dict[str, Any]]:
        """Extract function/method definitions with calls."""
        functions = []
        # Simplified extraction - traverse AST for function nodes
        def traverse(node, parent_class: Optional[str] = None):
            if node.type == 'class_declaration':
                class_name_node = node.child_by_field_name('name')
                current_class = content[class_name_node.start_byte:class_name_node.end_byte] if class_name_node else None
                for child in node.children:
                    traverse(child, current_class)
            elif node.type == 'method_declaration' or node.type == 'function_definition':
                name_node = node.child_by_field_name('name')
                if name_node:
                    name = content[name_node.start_byte:name_node.end_byte]
                    method_code = content[node.start_byte:node.end_byte]
                    calls = self._extract_method_calls(method_code, language)
                    functions.append({
                        'name': name,
                        'class_name': parent_class,
                        'start_line': node.start_point[0] + 1,
                        'end_line': node.end_point[0] + 1,
                        'code': method_code,
                        'calls': calls
                    })
            else:
            for child in node.children:
                    traverse(child, parent_class)
        
        traverse(root)
        return functions
    
    def _extract_method_calls(self, code: str, language: str) -> List[str]:
        """Extract method calls from code."""
        calls = []
        if language == 'java':
            # Pattern: object.method() or Class.method() or method()
            call_patterns = [
                r'\b([a-zA-Z_][a-zA-Z0-9_]*)\s*\.\s*([a-zA-Z_][a-zA-Z0-9_]*)\s*\(',  # obj.method()
                r'\b([A-Z][a-zA-Z0-9_]*(?:\.[A-Z][a-zA-Z0-9_]*)*)\s*\.\s*([a-zA-Z_][a-zA-Z0-9_]*)\s*\(',  # Class.method()
                r'\b([a-zA-Z_][a-zA-Z0-9_]*)\s*\(',  # method() - standalone
            ]
            for pattern in call_patterns:
                matches = re.finditer(pattern, code)
                for match in matches:
                    if len(match.groups()) == 2:
                        # obj.method() or Class.method()
                        class_or_obj = match.group(1)
                        method = match.group(2)
                        call = f"{class_or_obj}.{method}"
                    else:
                        # method()
                        call = match.group(1)
                    
                    # Filter out common Java keywords and built-ins
                    if call and call not in ['if', 'for', 'while', 'switch', 'catch', 'try', 'new', 'return', 'throw']:
                        if call not in calls:
                            calls.append(call)
        elif language in ['python', 'javascript', 'typescript']:
            # Pattern: obj.method() or function()
            call_pattern = r'\b([a-zA-Z_][a-zA-Z0-9_]*(?:\.[a-zA-Z_][a-zA-Z0-9_]*)*)\s*\('
            matches = re.finditer(call_pattern, code)
            for match in matches:
                call = match.group(1)
                if call and call not in ['if', 'for', 'while', 'print', 'console', 'return']:
                    if call not in calls:
                        calls.append(call)
        return calls
    
    def _extract_classes(self, root, content: str, language: str) -> List[Dict[str, Any]]:
        """Extract class definitions with relationships."""
        classes = []
        def traverse(node):
            if node.type == 'class_declaration':
                name_node = node.child_by_field_name('name')
                if name_node:
                    name = content[name_node.start_byte:name_node.end_byte]
                    class_info = {
                        'name': name,
                        'start_line': node.start_point[0] + 1,
                        'end_line': node.end_point[0] + 1,
                        'code': content[node.start_byte:node.end_byte],
                        'extends': [],
                        'implements': [],
                        'references': []
                    }
                    
                    # Extract extends (superclass)
                    superclass_node = node.child_by_field_name('superclass')
                    if superclass_node:
                        extends_name = content[superclass_node.start_byte:superclass_node.end_byte].strip()
                        if extends_name:
                            class_info['extends'] = [extends_name]
                    
                    # Extract implements (interfaces)
                    interfaces_node = node.child_by_field_name('interfaces')
                    if interfaces_node:
                        for child in interfaces_node.children:
                            if child.type == 'type_identifier' or child.type == 'scoped_type_identifier':
                                impl_name = content[child.start_byte:child.end_byte].strip()
                                if impl_name:
                                    class_info['implements'].append(impl_name)
                    
                    # Extract type references from class body (for references relationship)
                    class_body = content[node.start_byte:node.end_byte]
                    references = self._extract_type_references(class_body, language)
                    class_info['references'] = references
                    
                    classes.append(class_info)
            for child in node.children:
                traverse(child)
        traverse(root)
        return classes
    
    def _extract_type_references(self, code: str, language: str) -> List[str]:
        """Extract type references from code (for references relationship)."""
        references = []
        if language == 'java':
            # Extract type identifiers (class names used in code)
            # Pattern: TypeName variableName or new TypeName()
            type_patterns = [
                r'\b([A-Z][a-zA-Z0-9_]*)\s+\w+\s*[=;,\[\]()]',  # Type variable
                r'new\s+([A-Z][a-zA-Z0-9_]*(?:\.[A-Z][a-zA-Z0-9_]*)*)\s*\(',  # new Type()
                r'([A-Z][a-zA-Z0-9_]*(?:\.[A-Z][a-zA-Z0-9_]*)*)\s*\.\s*\w+\s*\(',  # Type.method()
            ]
            for pattern in type_patterns:
                matches = re.finditer(pattern, code)
                for match in matches:
                    ref = match.group(1)
                    if ref and ref not in ['String', 'Integer', 'Long', 'Double', 'Float', 'Boolean', 'Byte', 'Short', 'Character']:
                        if ref not in references:
                            references.append(ref)
        return references
    
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
        checkpoint_file: Optional[str] = None,
        use_azure_embeddings: bool = False,
        user_sid: str = "default_user",
        azure_cert_path: Optional[str] = None,
        azure_config_path: Optional[str] = None
    ):
        self.parser = StandaloneParser()
        self.embedding_client = None
        self.azure_embedding_service = None
        self.embedding_model = embedding_model
        self.chunking_strategy = chunking_strategy
        self.max_chunk_size = max_chunk_size
        self.enforce_chunk_size = enforce_chunk_size
        self.chunk_overlap_size = chunk_overlap_size
        self.batch_size = batch_size
        self.n_jobs = n_jobs  # -1 means use all CPUs
        self.checkpoint_file = checkpoint_file
        self.use_azure_embeddings = use_azure_embeddings
        self.repo_path = None  # Will be set when processing starts
        self.module_map = {}  # Cache for module mapping (file_path -> module_name)
        
        # Initialize embedding service (Azure or OpenAI)
        if use_azure_embeddings and AZURE_EMBEDDINGS_AVAILABLE:
            try:
                self.azure_embedding_service = EmbeddingService(
                    user_sid=user_sid,
                    cert_path=azure_cert_path,
                    config_path=azure_config_path
                )
                print("✅ Using Azure OpenAI Embeddings service")
            except Exception as e:
                print(f"⚠️ Failed to initialize Azure Embeddings service: {e}")
                print("   Falling back to OpenAI if API key provided")
                use_azure_embeddings = False
        
        if not use_azure_embeddings and OPENAI_AVAILABLE and openai_api_key:
            self.embedding_client = AsyncOpenAI(api_key=openai_api_key)
            print("✅ Using OpenAI Embeddings service")
    
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
        if not texts:
            return [None] * len(texts)
        
        # Use Azure Embeddings if available
        if self.use_azure_embeddings and self.azure_embedding_service:
            try:
                # Azure embeddings service is synchronous, run in executor to avoid blocking
                import asyncio
                loop = asyncio.get_event_loop()
                # Process in batches to avoid memory issues
                all_embeddings = []
                
                # Create batches for progress tracking
                batches = list(self.azure_embedding_service.chunk_list(texts, self.batch_size))
                num_batches = len(batches)
                
                # Add progress bar for batch processing
                batch_iter = tqdm(batches, desc="Generating embeddings (Azure)", unit="batch", total=num_batches) if TQDM_AVAILABLE else batches
                
                for batch in batch_iter:
                    # Run synchronous embedding in executor
                    batch_embeddings = await loop.run_in_executor(
                        None, 
                        self.azure_embedding_service.embed_texts, 
                        batch
                    )
                    all_embeddings.extend(batch_embeddings)
                return all_embeddings
            except Exception as e:
                print(f"⚠️ Error generating Azure embeddings: {e}")
                return [None] * len(texts)
        
        # Fallback to OpenAI
        if not self.embedding_client:
            return [None] * len(texts)
        
        all_embeddings = []
        
        # Calculate number of batches for progress bar
        num_batches = (len(texts) + self.batch_size - 1) // self.batch_size
        
        # Create progress bar for batch processing
        batch_range = range(0, len(texts), self.batch_size)
        batch_iter = tqdm(batch_range, desc="Generating embeddings (OpenAI)", unit="batch", total=num_batches) if TQDM_AVAILABLE else batch_range
        
        # Process in batches to avoid rate limits
        for i in batch_iter:
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
    
    def _generate_chunk_id(self, chunk: Dict[str, Any]) -> str:
        """
        Generate a unique, deterministic chunk_id based on chunk attributes.
        Same chunk will always get the same ID.
        """
        # Create a unique identifier from chunk attributes
        unique_string = f"{chunk['file_path']}:{chunk['start_line']}:{chunk['end_line']}:{chunk['type']}:{chunk['fqn']}"
        
        # Generate hash for consistent, short ID
        chunk_id = hashlib.sha256(unique_string.encode()).hexdigest()[:16]  # 16-char hex ID
        
        return f"chunk_{chunk_id}"
    
    def _generate_chunk_content_id(self, chunk: Dict[str, Any]) -> str:
        """
        Generate a unique _id based on hash of entire chunk content.
        This is different from chunk_id which is based on location.
        """
        # Create a string representation of the entire chunk content
        content_string = f"{chunk.get('code', '')}{chunk.get('summary', '')}{chunk.get('fqn', '')}{chunk.get('type', '')}"
        
        # Generate hash of entire content
        content_hash = hashlib.sha256(content_string.encode()).hexdigest()
        
        return f"content_{content_hash}"
    
    def _get_filetype(self, file_path: str) -> str:
        """Extract file extension (filetype) from file path."""
        return Path(file_path).suffix.lower() or 'unknown'
    
    def _get_relative_path(self, file_path: str) -> str:
        """Convert absolute file path to relative path from repo root."""
        if not self.repo_path:
            # If repo_path not set, return original path
            return file_path
        
        try:
            file_path_obj = Path(file_path)
            repo_path_obj = Path(self.repo_path)
            
            # Get relative path
            try:
                relative_path = file_path_obj.relative_to(repo_path_obj)
                return str(relative_path)
            except ValueError:
                # File is not under repo_path, return original
                return file_path
        except Exception:
            return file_path
    
    def _get_module_for_file(self, file_path: str) -> Optional[str]:
        """
        Extract module name for Java files in multi-module Maven projects.
        Returns None if not a Java file or not in a multi-module project.
        """
        # Check cache first
        if file_path in self.module_map:
            return self.module_map[file_path]
        
        # Only process Java files
        if not file_path.endswith('.java'):
            self.module_map[file_path] = None
            return None
        
        if not self.repo_path:
            self.module_map[file_path] = None
            return None
        
        try:
            file_path_obj = Path(file_path)
            repo_path_obj = Path(self.repo_path)
            
            # Find pom.xml files to determine module structure
            # Look for pom.xml in parent directories
            current_dir = file_path_obj.parent
            while current_dir != repo_path_obj.parent:
                pom_file = current_dir / 'pom.xml'
                if pom_file.exists():
                    # Check if this pom.xml has a parent (indicating it's a module)
                    import xml.etree.ElementTree as ET
                    try:
                        tree = ET.parse(pom_file)
                        root = tree.getroot()
                        
                        # Remove namespace
                        for elem in root.iter():
                            if '}' in elem.tag:
                                elem.tag = elem.tag.split('}')[1]
                        
                        # Check if this is a module (has parent pom.xml)
                        parent = root.find('parent')
                        if parent is not None:
                            # This is a module, get its artifactId
                            artifact_id = root.find('artifactId')
                            if artifact_id is not None:
                                module_name = artifact_id.text
                                self.module_map[file_path] = module_name
                                return module_name
                    except Exception:
                        pass
                
                if current_dir == repo_path_obj:
                    break
                current_dir = current_dir.parent
            
            # Not in a module
            self.module_map[file_path] = None
            return None
        except Exception:
            self.module_map[file_path] = None
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
        # Store repo_path for relative path conversion and module extraction
        self.repo_path = repo_path
        self.module_map = {}  # Reset module cache
        
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
        if self.embedding_client or self.azure_embedding_service:
            embedding_service_name = "Azure" if self.azure_embedding_service else "OpenAI"
            print(f"📊 Generating embeddings for {len(all_chunks)} chunks using {embedding_service_name}...")
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
            # Get relative path
            relative_path = self._get_relative_path(file_path)
            
            chunk = {
                'type': 'file',
                'fqn': relative_path,
                'file_path': relative_path,  # Use relative path
                'start_line': 1,
                'end_line': len(file_content.split('\n')),
                'code': file_content,
                'summary': f"File {Path(file_path).name}",
                'language': parsed.get('language', 'unknown'),
                'filetype': self._get_filetype(file_path),
            }
            
            # Add module for Java files
            if parsed.get('language', 'unknown') == 'java':
                module = self._get_module_for_file(file_path)
                if module:
                    chunk['module'] = module
            
            # Generate unique chunk_id and _id
            chunk['chunk_id'] = self._generate_chunk_id(chunk)
            chunk['_id'] = self._generate_chunk_content_id(chunk)
            chunks.append(chunk)
        
        return chunks
    
    def _create_method_chunk(self, func: Dict[str, Any], parsed: Dict[str, Any], file_path: str) -> Dict[str, Any]:
        """Create a method chunk."""
        # Get relative path
        relative_path = self._get_relative_path(file_path)
        
        chunk = {
            'type': 'method',
            'fqn': f"{Path(file_path).stem}.{func['name']}",
            'file_path': relative_path,  # Use relative path
            'start_line': func.get('start_line', 1),
            'end_line': func.get('end_line', 1),
            'code': func.get('code', ''),
            'summary': f"Method {func['name']}",
            'language': parsed.get('language', 'unknown'),
            'filetype': self._get_filetype(file_path),
        }
        
        # Add module for Java files
        if parsed.get('language', 'unknown') == 'java':
            module = self._get_module_for_file(file_path)
            if module:
                chunk['module'] = module
        
        # Generate unique chunk_id and _id
        chunk['chunk_id'] = self._generate_chunk_id(chunk)
        chunk['_id'] = self._generate_chunk_content_id(chunk)
        
        return chunk
    
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
        
        # Get relative path
        relative_path = self._get_relative_path(file_path)
        
        chunk = {
            'type': 'class',
            'fqn': f"{Path(file_path).stem}.{cls['name']}",
            'file_path': relative_path,  # Use relative path
            'start_line': start_line,
            'end_line': end_line,  # Updated to include class-level code
            'code': class_metadata_code,  # Signature + fields + static/instance blocks
            'summary': f"Class {cls['name']}",
            'language': parsed.get('language', 'unknown'),
            'filetype': self._get_filetype(file_path),
        }
        
        # Add module for Java files
        if parsed.get('language', 'unknown') == 'java':
            module = self._get_module_for_file(file_path)
            if module:
                chunk['module'] = module
        
        # Generate unique chunk_id and _id
        chunk['chunk_id'] = self._generate_chunk_id(chunk)
        chunk['_id'] = self._generate_chunk_content_id(chunk)
        
        return chunk
    
    def _split_large_code(self, code: str, entity: Dict[str, Any], file_path: str, entity_type: str) -> List[Dict[str, Any]]:
        """Split large code into smaller chunks."""
        chunks = []
        lines = code.split('\n')
        lines_per_chunk = self.max_chunk_size // 50  # Rough estimate
        
        # Get relative path and filetype
        relative_path = self._get_relative_path(file_path)
        filetype = self._get_filetype(file_path)
        
        # Infer language from file extension
        language = 'unknown'
        if filetype == '.java':
            language = 'java'
        elif filetype == '.py':
            language = 'python'
        elif filetype in ['.js', '.jsx']:
            language = 'javascript'
        elif filetype in ['.ts', '.tsx']:
            language = 'typescript'
        
        for i in range(0, len(lines), lines_per_chunk):
            chunk_lines = lines[i:i + lines_per_chunk]
            chunk_code = '\n'.join(chunk_lines)
            chunk_start = entity.get('start_line', 1) + i
            chunk_end = entity.get('start_line', 1) + i + len(chunk_lines) - 1
            
            chunk = {
                'type': entity_type,
                'fqn': f"{Path(file_path).stem}.{entity['name']}_part{i // lines_per_chunk}",
                'file_path': relative_path,  # Use relative path
                'start_line': chunk_start,
                'end_line': chunk_end,
                'code': chunk_code,
                'summary': f"{entity_type.title()} {entity['name']} (part {i // lines_per_chunk + 1})",
                'language': language,
                'filetype': filetype,
            }
            
            # Add module for Java files
            if language == 'java':
                module = self._get_module_for_file(file_path)
                if module:
                    chunk['module'] = module
            
            # Generate unique chunk_id and _id
            chunk['chunk_id'] = self._generate_chunk_id(chunk)
            chunk['_id'] = self._generate_chunk_content_id(chunk)
            chunks.append(chunk)
        
        return chunks
    
    def _recursive_split_code(self, code: str, entity: Dict[str, Any], file_path: str, entity_type: str) -> List[Dict[str, Any]]:
        """Recursively split code by logical blocks."""
        # Get relative path and filetype
        relative_path = self._get_relative_path(file_path)
        filetype = self._get_filetype(file_path)
        
        # Infer language from file extension
        language = 'unknown'
        if filetype == '.java':
            language = 'java'
        elif filetype == '.py':
            language = 'python'
        elif filetype in ['.js', '.jsx']:
            language = 'javascript'
        elif filetype in ['.ts', '.tsx']:
            language = 'typescript'
        
        if len(code) <= self.max_chunk_size:
            chunk = {
                'type': entity_type,
                'fqn': f"{Path(file_path).stem}.{entity['name']}",
                'file_path': relative_path,  # Use relative path
                'start_line': entity.get('start_line', 1),
                'end_line': entity.get('end_line', 1),
                'code': code,
                'summary': f"{entity_type.title()} {entity['name']}",
                'language': language,
                'filetype': filetype,
            }
            
            # Add module for Java files
            if language == 'java':
                module = self._get_module_for_file(file_path)
                if module:
                    chunk['module'] = module
            
            # Generate unique chunk_id and _id
            chunk['chunk_id'] = self._generate_chunk_id(chunk)
            chunk['_id'] = self._generate_chunk_content_id(chunk)
            return [chunk]
        
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
        
        # Get relative path and filetype
        relative_path = self._get_relative_path(file_path)
        filetype = self._get_filetype(file_path)
        
        # Infer language from file extension
        language = 'unknown'
        if filetype == '.java':
            language = 'java'
        elif filetype == '.py':
            language = 'python'
        elif filetype in ['.js', '.jsx']:
            language = 'javascript'
        elif filetype in ['.ts', '.tsx']:
            language = 'typescript'
        
        for i in range(0, len(lines), window_size - overlap_lines):
            window_lines = lines[i:min(i + window_size, len(lines))]
            window_code = '\n'.join(window_lines)
            window_start = entity.get('start_line', 1) + i
            window_end = entity.get('start_line', 1) + i + len(window_lines) - 1
            
            chunk = {
                'type': 'class',
                'fqn': f"{Path(file_path).stem}.{entity['name']}_window{i // (window_size - overlap_lines)}",
                'file_path': relative_path,  # Use relative path
                'start_line': window_start,
                'end_line': window_end,
                'code': window_code,
                'summary': f"Class {entity['name']} (window {i // (window_size - overlap_lines) + 1})",
                'language': language,
                'filetype': filetype,
            }
            
            # Add module for Java files
            if language == 'java':
                module = self._get_module_for_file(file_path)
                if module:
                    chunk['module'] = module
            
            # Generate unique chunk_id and _id
            chunk['chunk_id'] = self._generate_chunk_id(chunk)
            chunk['_id'] = self._generate_chunk_content_id(chunk)
            chunks.append(chunk)
        
        return chunks


class StandaloneOpenSearch:
    """Self-contained OpenSearch client with AWS authentication support."""
    
    def __init__(
        self, 
        host: Optional[str] = None, 
        index: Optional[str] = None, 
        config_path: Optional[str] = None,
        use_aws_auth: bool = True,
        region: Optional[str] = None,
        use_ssl: bool = True,
        verify_certs: bool = True,
        application_name: Optional[str] = None,
        seal_id: Optional[str] = None
    ):
        """
        Initialize OpenSearch client and load configuration.
        
        Args:
            host: OpenSearch endpoint (optional if using config file)
            index: OpenSearch index name (optional if using config file)
            config_path: Path to config.ini file (optional)
            use_aws_auth: Use AWS authentication (default: True)
            region: AWS region (optional, will use config or default)
            use_ssl: Use SSL for connection (default: True)
            verify_certs: Verify SSL certificates (default: True)
            application_name: Application name (optional, will be extracted from pom.xml if not provided)
            seal_id: Seal ID (optional, will be extracted from pom.xml if not provided)
        """
        self.client = None
        self.application_name = application_name
        self.seal_id = seal_id
        
        # Store AWS auth configuration for token refresh
        self.use_aws_auth = use_aws_auth
        self.use_ssl = use_ssl
        self.verify_certs = verify_certs
        self.aws_session = None
        self.aws_host = None
        self.hostname = None
        self.port = None
        
        # Load config
        if config_path is None:
            current_dir = os.path.dirname(__file__)
            config_path = os.path.join(current_dir, "config.ini")
        
        if os.path.exists(config_path):
            self.config = configparser.ConfigParser()
            self.config.read(config_path)
            print(f"✅ Loaded config from {config_path}")
            print(f"   Sections found: {self.config.sections()}")
            
            # Extract OpenSearch config from config file
            if 'aws_info' in self.config:
                self.opensearch_endpoint = self.config['aws_info'].get('opensearch_endpoint', host or '')
                self.index_name = self.config['aws_info'].get('index_name', index or 'code_chunks')
                self.region = self.config['aws_info'].get('region', region or 'us-east-1')
            else:
                # Fallback to provided parameters
                self.opensearch_endpoint = host or ''
                self.index_name = index or 'code_chunks'
                self.region = region or 'us-east-1'
        else:
            # Use provided parameters
            self.opensearch_endpoint = host or ''
            self.index_name = index or 'code_chunks'
            self.region = region or 'us-east-1'
            self.config = None
        
        if not self.opensearch_endpoint:
            print("⚠️ OpenSearch endpoint not provided and not found in config")
            return
        
        if not OPENSEARCH_AVAILABLE:
            print("⚠️ OpenSearch not available")
            return
        
        try:
            if use_aws_auth and AWS_AUTH_AVAILABLE:
                # AWS Auth - store session for token refresh
                self.aws_session = session.Session()
                
                # Extract hostname from endpoint (remove protocol and port)
                self.aws_host = self.opensearch_endpoint.replace('https://', '').replace('http://', '').split(':')[0]
                
                # Determine port (default 443 for HTTPS)
                self.port = 443
                if ':' in self.opensearch_endpoint:
                    port_part = self.opensearch_endpoint.split(':')[-1].split('/')[0]
                    try:
                        self.port = int(port_part)
                    except ValueError:
                        self.port = 443
                
                self.hostname = self.aws_host
                
                # Initialize with fresh credentials
                self._refresh_aws_auth()
                
                print(f"✅ Connected to AWS OpenSearch: {self.opensearch_endpoint}")
            else:
                # Basic authentication (for local development)
                host_parts = self.opensearch_endpoint.replace('https://', '').replace('http://', '').split(':')
                self.hostname = host_parts[0]
                self.port = int(host_parts[1]) if len(host_parts) > 1 else 9200
                
                self.client = OpenSearch(
                    hosts=[{'host': self.hostname, 'port': self.port}],
                    use_ssl=use_ssl,
                    verify_certs=verify_certs,
                    connection_class=RequestsHttpConnection
                )
                print(f"✅ Connected to OpenSearch: {self.opensearch_endpoint}")
        except Exception as e:
            print(f"⚠️ Failed to connect to OpenSearch: {e}")
            import traceback
            print(traceback.format_exc())
    
    async def check_connectivity_and_list_indexes(self) -> bool:
        """
        Check OpenSearch connectivity and list all available indexes.
        
        Returns:
            bool: True if connection successful, False otherwise
        """
        if not self.client:
            print("⚠️ OpenSearch client not initialized")
            return False
        
        try:
            # Test connectivity with a simple cluster info call
            cluster_info = self.client.info()
            print(f"✅ OpenSearch connectivity verified")
            print(f"   Cluster: {cluster_info.get('cluster_name', 'unknown')}")
            print(f"   Version: {cluster_info.get('version', {}).get('number', 'unknown')}")
            
            # List all indexes
            indices = self.client.indices.get_alias(index="*")
            index_names = sorted(indices.keys())
            
            if index_names:
                # Show indexes in a single line
                indexes_str = ", ".join(index_names)
                print(f"   Available indexes ({len(index_names)}): {indexes_str}")
                
                # Highlight the target index if it exists
                if self.index_name in index_names:
                    print(f"   ✓ Target index '{self.index_name}' exists")
                else:
                    print(f"   ⚠ Target index '{self.index_name}' does not exist (will be created)")
            else:
                print(f"   No indexes found in cluster")
            
            return True
        except Exception as e:
            print(f"❌ Failed to connect to OpenSearch: {e}")
            import traceback
            print(traceback.format_exc())
            return False
    
    def _refresh_aws_auth(self):
        """Refresh AWS authentication credentials and update OpenSearch client."""
        if not self.use_aws_auth or not AWS_AUTH_AVAILABLE or not self.aws_session:
            return False
        
        try:
            # Get fresh credentials from session
            credentials = self.aws_session.get_credentials()
            
            if not credentials:
                print("⚠️ Failed to get AWS credentials for refresh")
                return False
            
            # Create new AWS auth with fresh credentials
            # AWSRequestsAuth expects individual credential components
            awsauth = AWSRequestsAuth(
                aws_access_key=credentials.access_key,
                aws_secret_access_key=credentials.secret_key,
                aws_token=credentials.token,
                aws_host=self.aws_host,
                aws_region=self.region,
                aws_service='es'
            )
            
            # Recreate OpenSearch client with fresh auth
            self.client = OpenSearch(
                hosts=[{'host': self.hostname, 'port': self.port}],
                http_auth=awsauth,
                use_ssl=self.use_ssl,
                verify_certs=self.verify_certs,
                connection_class=RequestsHttpConnection
            )
            
            return True
        except Exception as e:
            print(f"⚠️ Failed to refresh AWS authentication: {e}")
            return False
    
    async def ensure_index(self, embedding_dim: int = 1536):
        """Ensure index exists with proper mapping."""
        if not self.client:
            return False
        
        try:
            if self.client.indices.exists(index=self.index_name):
                print(f"✅ Index '{self.index_name}' exists")
                return True
            
            mapping = {
                "mappings": {
                    "properties": {
                        "chunk_id": {"type": "keyword"},
                        "type": {"type": "keyword"},
                        "fqn": {"type": "keyword"},
                        "file_path": {"type": "keyword"},  # Relative path
                        "filetype": {"type": "keyword"},  # File extension (.java, .py, etc.)
                        "module": {"type": "keyword"},  # Maven module (Java only, optional)
                        "code": {"type": "text"},
                        "summary": {"type": "text"},
                        "application_name": {"type": "keyword"},
                        "seal_id": {"type": "keyword"},
                        "embedding": {
                            "type": "knn_vector",
                            "dimension": embedding_dim,
                        }
                    }
                }
            }
            
            self.client.indices.create(index=self.index_name, body=mapping)
            print(f"✅ Created index '{self.index_name}'")
            return True
        except Exception as e:
            print(f"❌ Error ensuring index: {e}")
            return False
    
    def _prepare_bulk_body(self, batch_chunks: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """Prepare bulk request body for a batch of chunks."""
        bulk_body = []
        for chunk in batch_chunks:
            # Action metadata - use _id if available, otherwise chunk_id
            doc_id = chunk.get('_id', chunk['chunk_id'])
            bulk_body.append({
                "index": {
                    "_index": self.index_name,
                    "_id": doc_id
                }
            })
            
            # Document
            doc = {
                'chunk_id': chunk['chunk_id'],
                'type': chunk['type'],
                'fqn': chunk['fqn'],
                'file_path': chunk['file_path'],  # Already relative path
                'filetype': chunk.get('filetype', ''),
                'code': chunk['code'],
                'summary': chunk.get('summary', ''),
                'application_name': self.application_name or '',
                'seal_id': self.seal_id or '',
                'embedding': chunk['embedding'],
            }
            
            # Add module if present (Java files in multi-module Maven projects)
            if 'module' in chunk:
                doc['module'] = chunk['module']
            
            bulk_body.append(doc)
        return bulk_body
    
    def _index_batch(self, batch_chunks: List[Dict[str, Any]], batch_num: int) -> tuple[int, int, Optional[str]]:
        """
        Index a single batch using bulk API.
        
        Returns:
            tuple: (success_count, error_count, error_message)
        """
        bulk_body = self._prepare_bulk_body(batch_chunks)
        
        max_retries = 2
        retry_count = 0
        
        while retry_count <= max_retries:
            try:
                # Execute bulk request
                response = self.client.bulk(body=bulk_body)
                
                # Check for errors in response
                if response.get('errors'):
                    errors = [item for item in response['items'] if 'error' in item.get('index', {})]
                    error_count = len(errors)
                    success_count = len(batch_chunks) - error_count
                    
                    # Log first error if any
                    error_msg = None
                    if errors:
                        first_error = errors[0]['index'].get('error', {})
                        error_msg = f"Batch {batch_num}: {first_error.get('reason', 'Unknown error')}"
                    
                    return success_count, error_count, error_msg
                else:
                    # All successful
                    return len(batch_chunks), 0, None
                    
            except Exception as e:
                error_str = str(e)
                error_type = type(e).__name__
                
                # Check if it's a token expiration error
                is_token_error = (
                    '403' in error_str or 
                    'expired' in error_str.lower() or 
                    'AuthorizationException' in error_type or
                    'token' in error_str.lower() and 'expired' in error_str.lower()
                )
                
                if is_token_error and retry_count < max_retries and self.use_aws_auth:
                    # Token expired, refresh and retry
                    if self._refresh_aws_auth():
                        retry_count += 1
                        continue
                    else:
                        # Failed to refresh
                        return 0, len(batch_chunks), f"Batch {batch_num}: Failed to refresh AWS credentials"
                else:
                    # Not a token error or max retries reached
                    return 0, len(batch_chunks), f"Batch {batch_num}: {error_str}"
        
        return 0, len(batch_chunks), f"Batch {batch_num}: Max retries exceeded"
    
    async def index_chunks(self, chunks: List[Dict[str, Any]], batch_size: int = 100, max_workers: int = 4):
        """
        Index chunks to OpenSearch using bulk API with parallel batch processing.
        
        Args:
            chunks: List of chunks to index
            batch_size: Number of chunks per batch (default: 100)
            max_workers: Maximum number of parallel workers (default: 4)
        """
        if not self.client:
            print("⚠️ OpenSearch not available, skipping indexing")
            return
        
        await self.ensure_index()
        
        # Filter chunks that have required fields
        valid_chunks = [chunk for chunk in chunks if 'embedding' in chunk and 'chunk_id' in chunk]
        
        if not valid_chunks:
            print("⚠️ No valid chunks to index (missing embedding or chunk_id)")
            return
        
        print(f"📊 Indexing {len(valid_chunks)} chunks to OpenSearch using bulk API...")
        print(f"   Batch size: {batch_size}, Parallel workers: {max_workers}")
        
        # Create batches
        batches = [valid_chunks[i:i+batch_size] for i in range(0, len(valid_chunks), batch_size)]
        total_batches = len(batches)
        
        indexed_count = 0
        error_count = 0
        error_messages = []
        
        # Process batches in parallel
        if max_workers > 1 and total_batches > 1:
            # Parallel processing
            pbar = tqdm(total=total_batches, desc="Indexing batches", unit="batch") if TQDM_AVAILABLE else None
            
            with ThreadPoolExecutor(max_workers=max_workers) as executor:
                # Submit all batches
                future_to_batch = {
                    executor.submit(self._index_batch, batches[i], i+1): i 
                    for i in range(total_batches)
                }
                
                # Process completed batches
                for future in as_completed(future_to_batch):
                    batch_idx = future_to_batch[future]
                    try:
                        success, errors, error_msg = future.result()
                        indexed_count += success
                        error_count += errors
                        if error_msg:
                            error_messages.append(error_msg)
                    except Exception as e:
                        error_count += len(batches[batch_idx])
                        error_messages.append(f"Batch {batch_idx+1}: {str(e)}")
                    
                    # Update progress bar
                    if pbar:
                        pbar.update(1)
            
            if pbar:
                pbar.close()
        else:
            # Sequential processing (for small datasets or single worker)
            batch_iter = tqdm(batches, desc="Indexing batches", unit="batch") if TQDM_AVAILABLE else batches
            
            for batch_num, batch in enumerate(batch_iter, 1):
                success, errors, error_msg = self._index_batch(batch, batch_num)
                indexed_count += success
                error_count += errors
                if error_msg:
                    error_messages.append(error_msg)
        
        # Print summary
        print(f"✅ Indexed {indexed_count}/{len(valid_chunks)} chunks to OpenSearch" + (f" ({error_count} errors)" if error_count > 0 else ""))
        
        # Print error details if any
        if error_messages and len(error_messages) <= 10:
            for msg in error_messages:
                print(f"   ⚠️ {msg}")
        elif error_messages:
            print(f"   ⚠️ {len(error_messages)} batches had errors (showing first 10):")
            for msg in error_messages[:10]:
                print(f"   ⚠️ {msg}")


class ApplicationServiceExtractor:
    """Extract Application and Service information from repository structure and config files."""
    
    def __init__(self, repo_path: str):
        self.repo_path = Path(repo_path)
        self.application_data = None
        self.services = []
        self.deployment_units = []
    
    def extract(self) -> Dict[str, Any]:
        """Extract application, services, and deployment units."""
        # Try to extract from Maven pom.xml
        pom_files = list(self.repo_path.rglob('pom.xml'))
        if pom_files:
            return self._extract_from_maven(pom_files)
        
        # Try to extract from package.json (Node.js)
        package_files = list(self.repo_path.rglob('package.json'))
        if package_files:
            return self._extract_from_nodejs(package_files)
        
        # Fallback: infer from directory structure
        return self._extract_from_structure()
    
    def _extract_from_maven(self, pom_files: List[Path]) -> Dict[str, Any]:
        """Extract from Maven pom.xml files."""
        import xml.etree.ElementTree as ET
        
        root_pom = None
        for pom_file in pom_files:
            if 'parent' not in str(pom_file) and pom_file.parent == self.repo_path:
                root_pom = pom_file
                break
        
        if not root_pom and pom_files:
            root_pom = pom_files[0]
        
        if root_pom:
            try:
                tree = ET.parse(root_pom)
                root = tree.getroot()
                
                # Remove namespace
                for elem in root.iter():
                    if '}' in elem.tag:
                        elem.tag = elem.tag.split('}')[1]
                
                artifact_id = root.find('artifactId')
                name = root.find('name')
                packaging = root.find('packaging')
                
                app_name = artifact_id.text if artifact_id is not None else self.repo_path.name
                app_display_name = name.text if name is not None else app_name
                packaging_type = packaging.text if packaging is not None else 'jar'
                
                # Extract sealId from properties
                seal_id = None
                properties = root.find('properties')
                if properties is not None:
                    seal_id_elem = properties.find('sealId')
                    if seal_id_elem is not None:
                        seal_id = seal_id_elem.text
                
                # Extract modules if multi-module project
                modules = root.find('modules')
                services = []
                if modules is not None:
                    for module in modules.findall('module'):
                        module_name = module.text
                        module_path = self.repo_path / module_name
                        if module_path.exists():
                            services.append({
                                'name': module_name,
                                'path': str(module_path),
                                'type': 'maven-module'
                            })
                else:
                    # Single module - treat as one service
                    services.append({
                        'name': app_name,
                        'path': str(self.repo_path),
                        'type': 'maven-project'
                    })
                
                return {
                    'application': {
                        'name': app_name,
                        'display_name': app_display_name,
                        'type': 'java',
                        'build_system': 'maven',
                        'seal_id': seal_id
                    },
                    'services': services,
                    'deployment_units': [{
                        'name': f"{app_name}.{packaging_type}",
                        'type': packaging_type,
                        'service': services[0]['name'] if services else app_name
                    }]
                }
            except Exception as e:
                print(f"⚠️ Error parsing pom.xml: {e}")
        
        return self._extract_from_structure()
    
    def _extract_from_nodejs(self, package_files: List[Path]) -> Dict[str, Any]:
        """Extract from Node.js package.json files."""
        root_package = None
        for pkg_file in package_files:
            if pkg_file.parent == self.repo_path:
                root_package = pkg_file
                break
        
        if not root_package and package_files:
            root_package = package_files[0]
        
        if root_package:
            try:
                with open(root_package, 'r') as f:
                    package_data = json.load(f)
                
                app_name = package_data.get('name', self.repo_path.name)
                
                return {
                    'application': {
                        'name': app_name,
                        'display_name': package_data.get('description', app_name),
                        'type': 'nodejs',
                        'build_system': 'npm'
                    },
                    'services': [{
                        'name': app_name,
                        'path': str(self.repo_path),
                        'type': 'nodejs-service'
                    }],
                    'deployment_units': [{
                        'name': app_name,
                        'type': 'nodejs',
                        'service': app_name
                    }]
                }
            except Exception as e:
                print(f"⚠️ Error parsing package.json: {e}")
        
        return self._extract_from_structure()
    
    def _extract_from_structure(self) -> Dict[str, Any]:
        """Infer application and services from directory structure."""
        app_name = self.repo_path.name
        
        # Look for common service directories
        service_dirs = []
        for item in self.repo_path.iterdir():
            if item.is_dir() and not item.name.startswith('.') and item.name not in ['target', 'build', 'node_modules', '__pycache__']:
                # Check if it contains code files
                code_files = list(item.rglob('*.java')) + list(item.rglob('*.py')) + list(item.rglob('*.js'))
                if code_files:
                    service_dirs.append({
                        'name': item.name,
                        'path': str(item),
                        'type': 'inferred'
                    })
        
        if not service_dirs:
            # Single service application
            service_dirs.append({
                'name': app_name,
                'path': str(self.repo_path),
                'type': 'inferred'
            })
        
        return {
            'application': {
                'name': app_name,
                'display_name': app_name,
                'type': 'unknown',
                'build_system': 'unknown'
            },
            'services': service_dirs,
            'deployment_units': [{
                'name': f"{app_name}.unknown",
                'type': 'unknown',
                'service': service_dirs[0]['name'] if service_dirs else app_name
            }]
        }


class ConfigFileParser:
    """Parse configuration files to extract ConfigArtifacts and ConfigKeys."""
    
    def __init__(self, repo_path: str):
        self.repo_path = Path(repo_path)
        self.config_artifacts = []
        self.config_keys = []
    
    def extract(self) -> Dict[str, Any]:
        """Extract configuration artifacts and keys."""
        # Parse YAML files (application.yml, application-*.yml)
        yaml_files = list(self.repo_path.rglob('application*.yml')) + list(self.repo_path.rglob('application*.yaml'))
        for yaml_file in yaml_files:
            self._parse_yaml_file(yaml_file)
        
        # Parse properties files
        prop_files = list(self.repo_path.rglob('application*.properties'))
        for prop_file in prop_files:
            self._parse_properties_file(prop_file)
        
        # Parse .env files
        env_files = list(self.repo_path.rglob('.env*'))
        for env_file in env_files:
            self._parse_env_file(env_file)
        
        return {
            'config_artifacts': self.config_artifacts,
            'config_keys': self.config_keys
        }
    
    def _parse_yaml_file(self, file_path: Path):
        """Parse YAML configuration file."""
        try:
            import yaml
            with open(file_path, 'r') as f:
                data = yaml.safe_load(f)
            
            # Extract environment from filename
            env = 'default'
            if '-prod' in file_path.name or '-production' in file_path.name:
                env = 'production'
            elif '-dev' in file_path.name or '-development' in file_path.name:
                env = 'development'
            elif '-test' in file_path.name or '-testing' in file_path.name:
                env = 'test'
            
            artifact = {
                'name': file_path.name,
                'path': str(file_path),
                'type': 'yaml',
                'environment': env
            }
            self.config_artifacts.append(artifact)
            
            # Extract keys recursively
            self._extract_yaml_keys(data, artifact['name'], env, '')
        except ImportError:
            print("⚠️ PyYAML not available. Install: pip install pyyaml")
        except Exception as e:
            print(f"⚠️ Error parsing YAML file {file_path}: {e}")
    
    def _extract_yaml_keys(self, data: Any, artifact_name: str, env: str, prefix: str):
        """Recursively extract keys from YAML data."""
        if isinstance(data, dict):
            for key, value in data.items():
                full_key = f"{prefix}.{key}" if prefix else key
                if isinstance(value, (dict, list)):
                    self._extract_yaml_keys(value, artifact_name, env, full_key)
                else:
                    self.config_keys.append({
                        'key': full_key,
                        'value': str(value) if value is not None else '',
                        'artifact': artifact_name,
                        'environment': env
                    })
        elif isinstance(data, list):
            for i, item in enumerate(data):
                self._extract_yaml_keys(item, artifact_name, env, f"{prefix}[{i}]")
    
    def _parse_properties_file(self, file_path: Path):
        """Parse properties configuration file."""
        try:
            env = 'default'
            if '-prod' in file_path.name:
                env = 'production'
            elif '-dev' in file_path.name:
                env = 'development'
            
            artifact = {
                'name': file_path.name,
                'path': str(file_path),
                'type': 'properties',
                'environment': env
            }
            self.config_artifacts.append(artifact)
            
            with open(file_path, 'r') as f:
                for line in f:
                    line = line.strip()
                    if line and not line.startswith('#') and '=' in line:
                        key, value = line.split('=', 1)
                        self.config_keys.append({
                            'key': key.strip(),
                            'value': value.strip(),
                            'artifact': artifact['name'],
                            'environment': env
                        })
        except Exception as e:
            print(f"⚠️ Error parsing properties file {file_path}: {e}")
    
    def _parse_env_file(self, file_path: Path):
        """Parse .env file."""
        try:
            artifact = {
                'name': file_path.name,
                'path': str(file_path),
                'type': 'env',
                'environment': 'default'
            }
            self.config_artifacts.append(artifact)
            
            with open(file_path, 'r') as f:
                for line in f:
                    line = line.strip()
                    if line and not line.startswith('#') and '=' in line:
                        key, value = line.split('=', 1)
                        self.config_keys.append({
                            'key': key.strip(),
                            'value': value.strip(),
                            'artifact': artifact['name'],
                            'environment': 'default'
                        })
        except Exception as e:
            print(f"⚠️ Error parsing .env file {file_path}: {e}")


class StandaloneGraphBuilder:
    """Self-contained graph builder using NetworkX with rich schema."""
    
    def __init__(self, use_rich_graph: bool = True):
        self.graph = None
        self.use_rich_graph = use_rich_graph
        if NETWORKX_AVAILABLE:
            self.graph = nx.MultiDiGraph()
            print("✅ NetworkX graph initialized")
    
    def build_graph(
        self,
        chunks: List[Dict[str, Any]],
        application_data: Optional[Dict[str, Any]] = None,
        config_data: Optional[Dict[str, Any]] = None,
        external_resources: Optional[List[Dict[str, Any]]] = None,
        parsed_files: Optional[List[Dict[str, Any]]] = None
    ):
        """
        Build graph from chunks with rich schema support.
        
        Args:
            chunks: List of code chunks
            application_data: Application, service, and deployment unit data
            config_data: Configuration artifacts and keys
            external_resources: External resources (databases, messaging, etc.)
            parsed_files: Parsed file data with relationships
        """
        if not self.graph:
            print("⚠️ NetworkX not available")
            return
        
        if not self.use_rich_graph:
            # Fallback to simple graph
            self._build_simple_graph(chunks)
            return
        
        # Build rich graph
        print("📊 Building rich knowledge graph...")
        
        # 1. Add Application and Service nodes
        if application_data:
            self._add_application_nodes(application_data)
        
        # 2. Add File nodes
        file_nodes = self._add_file_nodes(chunks, parsed_files)
        
        # 3. Add Class nodes
        class_nodes = self._add_class_nodes(chunks, parsed_files)
        
        # 4. Add Method nodes
        method_nodes = self._add_method_nodes(chunks, parsed_files)
        
        # 5. Add Config nodes
        if config_data:
            self._add_config_nodes(config_data)
        
        # 6. Add External Resource nodes
        if external_resources:
            self._add_external_resource_nodes(external_resources)
        
        # 7. Add Environment nodes
        if config_data:
            self._add_environment_nodes(config_data)
        
        # 8. Add relationships
        self._add_relationships(
            chunks, application_data, config_data, external_resources,
            parsed_files, file_nodes, class_nodes, method_nodes
        )
        
        print(f"✅ Rich graph built: {self.graph.number_of_nodes()} nodes, {self.graph.number_of_edges()} edges")
    
    def _build_simple_graph(self, chunks: List[Dict[str, Any]]):
        """Build simple graph (backward compatibility)."""
        # Add nodes using chunk_id
        for chunk in chunks:
            if 'chunk_id' not in chunk:
                continue
            
            self.graph.add_node(
                chunk['chunk_id'],
                type=chunk['type'],
                fqn=chunk['fqn'],
                file_path=chunk['file_path'],
                start_line=chunk.get('start_line', 1),
                end_line=chunk.get('end_line', 1),
                language=chunk.get('language', 'unknown'),
            )
        
        # Add edges based on file relationships
        for chunk1 in chunks:
            if 'chunk_id' not in chunk1:
                continue
            for chunk2 in chunks:
                if 'chunk_id' not in chunk2 or chunk1['chunk_id'] == chunk2['chunk_id']:
                    continue
                
                if chunk1['file_path'] == chunk2['file_path']:
                    self.graph.add_edge(
                        chunk1['chunk_id'],
                        chunk2['chunk_id'],
                        relationship='IN_FILE'
                    )
    
    def _add_application_nodes(self, application_data: Dict[str, Any]):
        """Add Application and Service nodes."""
        app_info = application_data.get('application', {})
        app_id = f"app_{app_info.get('name', 'unknown')}"
        
        self.graph.add_node(
            app_id,
            entity_type='Application',
            name=app_info.get('name', 'unknown'),
            display_name=app_info.get('display_name', 'unknown'),
            type=app_info.get('type', 'unknown'),
            build_system=app_info.get('build_system', 'unknown')
        )
        
        # Add Services
        for service in application_data.get('services', []):
            service_id = f"service_{service.get('name', 'unknown')}"
            self.graph.add_node(
                service_id,
                entity_type='Service',
                name=service.get('name', 'unknown'),
                path=service.get('path', ''),
                type=service.get('type', 'unknown')
            )
            # Application OWNS Service
            self.graph.add_edge(app_id, service_id, relationship='OWNS')
        
        # Add DeploymentUnits
        for du in application_data.get('deployment_units', []):
            du_id = f"du_{du.get('name', 'unknown')}"
            self.graph.add_node(
                du_id,
                entity_type='DeploymentUnit',
                name=du.get('name', 'unknown'),
                type=du.get('type', 'unknown'),
                service=du.get('service', 'unknown')
            )
            # Application DEPLOYED_AS DeploymentUnit
            self.graph.add_edge(app_id, du_id, relationship='DEPLOYED_AS')
    
    def _add_file_nodes(self, chunks: List[Dict[str, Any]], parsed_files: Optional[List[Dict[str, Any]]]) -> Dict[str, str]:
        """Add File nodes and return mapping of file_path -> node_id."""
        file_nodes = {}
        seen_files = set()
        
        for chunk in chunks:
            file_path = chunk.get('file_path', '')
            if file_path and file_path not in seen_files:
                file_id = f"file_{hashlib.sha256(file_path.encode()).hexdigest()[:16]}"
                self.graph.add_node(
                    file_id,
                    entity_type='File',
                    file_path=file_path,
                    name=Path(file_path).name
                )
                file_nodes[file_path] = file_id
                seen_files.add(file_path)
        
        return file_nodes
    
    def _add_class_nodes(self, chunks: List[Dict[str, Any]], parsed_files: Optional[List[Dict[str, Any]]]) -> Dict[str, str]:
        """Add Class nodes and return mapping of class_name -> node_id."""
        class_nodes = {}
        seen_classes = set()
        
        # Get class info from parsed files
        class_info_map = {}
        if parsed_files:
            for parsed in parsed_files:
                for cls in parsed.get('classes', []):
                    class_name = cls.get('name', '')
                    file_path = parsed.get('file_path', '')
                    if class_name and file_path:
                        key = f"{file_path}::{class_name}"
                        if key not in class_info_map:
                            class_info_map[key] = cls
        
        # Add class nodes from chunks
        for chunk in chunks:
            if chunk.get('type') == 'class':
                fqn = chunk.get('fqn', '')
                file_path = chunk.get('file_path', '')
                class_name = fqn.split('.')[-1] if '.' in fqn else fqn
                
                key = f"{file_path}::{class_name}"
                if key not in seen_classes:
                    class_id = f"class_{hashlib.sha256(key.encode()).hexdigest()[:16]}"
                    class_info = class_info_map.get(key, {})
                    
                    self.graph.add_node(
                        class_id,
                        entity_type='JavaClass',
                        name=class_name,
                        fqn=fqn,
                        file_path=file_path,
                        start_line=chunk.get('start_line', 1),
                        end_line=chunk.get('end_line', 1),
                        language=chunk.get('language', 'unknown')
                    )
                    class_nodes[key] = class_id
                    seen_classes.add(key)
        
        return class_nodes
    
    def _add_method_nodes(self, chunks: List[Dict[str, Any]], parsed_files: Optional[List[Dict[str, Any]]]) -> Dict[str, str]:
        """Add Method nodes and return mapping of method_signature -> node_id."""
        method_nodes = {}
        seen_methods = set()
        
        # Get method info from parsed files
        method_info_map = {}
        if parsed_files:
            for parsed in parsed_files:
                for func in parsed.get('functions', []):
                    method_name = func.get('name', '')
                    class_name = func.get('class_name', '')
                    file_path = parsed.get('file_path', '')
                    if method_name and file_path:
                        key = f"{file_path}::{class_name}::{method_name}"
                        if key not in method_info_map:
                            method_info_map[key] = func
        
        # Add method nodes from chunks
        for chunk in chunks:
            if chunk.get('type') == 'method':
                fqn = chunk.get('fqn', '')
                file_path = chunk.get('file_path', '')
                method_name = fqn.split('.')[-1] if '.' in fqn else fqn
                class_name = '.'.join(fqn.split('.')[:-1]) if '.' in fqn else ''
                
                key = f"{file_path}::{class_name}::{method_name}"
                if key not in seen_methods:
                    method_id = f"method_{hashlib.sha256(key.encode()).hexdigest()[:16]}"
                    method_info = method_info_map.get(key, {})
                    
                    self.graph.add_node(
                        method_id,
                        entity_type='Method',
                        name=method_name,
                        fqn=fqn,
                        class_name=class_name,
                        file_path=file_path,
                        start_line=chunk.get('start_line', 1),
                        end_line=chunk.get('end_line', 1),
                        language=chunk.get('language', 'unknown')
                    )
                    method_nodes[key] = method_id
                    seen_methods.add(key)
        
        return method_nodes
    
    def _add_config_nodes(self, config_data: Dict[str, Any]):
        """Add ConfigArtifact and ConfigKey nodes."""
        # Add ConfigArtifacts
        for artifact in config_data.get('config_artifacts', []):
            artifact_id = f"config_{hashlib.sha256(artifact.get('path', '').encode()).hexdigest()[:16]}"
            self.graph.add_node(
                artifact_id,
                entity_type='ConfigArtifact',
                name=artifact.get('name', 'unknown'),
                path=artifact.get('path', ''),
                type=artifact.get('type', 'unknown'),
                environment=artifact.get('environment', 'default')
            )
        
        # Add ConfigKeys
        for key_data in config_data.get('config_keys', []):
            key_id = f"key_{hashlib.sha256(key_data.get('key', '').encode()).hexdigest()[:16]}"
            self.graph.add_node(
                key_id,
                entity_type='ConfigKey',
                key=key_data.get('key', 'unknown'),
                value=key_data.get('value', ''),
                artifact=key_data.get('artifact', ''),
                environment=key_data.get('environment', 'default')
            )
    
    def _add_external_resource_nodes(self, external_resources: List[Dict[str, Any]]):
        """Add ExternalResource nodes."""
        for resource in external_resources:
            resource_id = f"resource_{hashlib.sha256(resource.get('name', '').encode()).hexdigest()[:16]}"
            self.graph.add_node(
                resource_id,
                entity_type='ExternalResource',
                name=resource.get('name', 'unknown'),
                type=resource.get('type', 'unknown'),
                source=resource.get('source', '')
            )
    
    def _add_environment_nodes(self, config_data: Dict[str, Any]):
        """Add Environment nodes."""
        environments = set()
        for artifact in config_data.get('config_artifacts', []):
            env = artifact.get('environment', 'default')
            environments.add(env)
        
        for env in environments:
            env_id = f"env_{env}"
            self.graph.add_node(
                env_id,
                entity_type='Environment',
                name=env
            )
    
    def _add_relationships(
        self,
        chunks: List[Dict[str, Any]],
        application_data: Optional[Dict[str, Any]],
        config_data: Optional[Dict[str, Any]],
        external_resources: Optional[List[Dict[str, Any]]],
        parsed_files: Optional[List[Dict[str, Any]]],
        file_nodes: Dict[str, str],
        class_nodes: Dict[str, str],
        method_nodes: Dict[str, str]
    ):
        """Add all relationship edges."""
        # Service CONTAINS File
        if application_data:
            for service in application_data.get('services', []):
                service_id = f"service_{service.get('name', 'unknown')}"
                service_path = service.get('path', '')
                for file_path, file_id in file_nodes.items():
                    if file_path.startswith(service_path):
                        self.graph.add_edge(service_id, file_id, relationship='CONTAINS')
        
        # File DECLARES Class
        for file_path, file_id in file_nodes.items():
            for key, class_id in class_nodes.items():
                if key.startswith(file_path + "::"):
                    self.graph.add_edge(file_id, class_id, relationship='DECLARES')
        
        # Class DECLARES_METHOD Method
        for key, class_id in class_nodes.items():
            file_path, class_name = key.split("::", 1)
            for method_key, method_id in method_nodes.items():
                if method_key.startswith(f"{file_path}::{class_name}::"):
                    self.graph.add_edge(class_id, method_id, relationship='DECLARES_METHOD')
        
        # Class EXTENDS, IMPLEMENTS, REFERENCES
        if parsed_files:
            for parsed in parsed_files:
                for cls in parsed.get('classes', []):
                    class_name = cls.get('name', '')
                    file_path = parsed.get('file_path', '')
                    key = f"{file_path}::{class_name}"
                    class_id = class_nodes.get(key)
                    
                    if class_id:
                        # EXTENDS
                        for extends_name in cls.get('extends', []):
                            # Try to find target class
                            target_class_id = self._find_class_by_name(extends_name, class_nodes, parsed_files)
                            if target_class_id:
                                self.graph.add_edge(class_id, target_class_id, relationship='EXTENDS')
                        
                        # IMPLEMENTS
                        for impl_name in cls.get('implements', []):
                            target_class_id = self._find_class_by_name(impl_name, class_nodes, parsed_files)
                            if target_class_id:
                                self.graph.add_edge(class_id, target_class_id, relationship='IMPLEMENTS')
                        
                        # REFERENCES
                        for ref_name in cls.get('references', []):
                            target_class_id = self._find_class_by_name(ref_name, class_nodes, parsed_files)
                            if target_class_id and target_class_id != class_id:
                                self.graph.add_edge(class_id, target_class_id, relationship='REFERENCES')
        
        # Method CALLS Method
        if parsed_files:
            for parsed in parsed_files:
                for func in parsed.get('functions', []):
                    method_name = func.get('name', '')
                    class_name = func.get('class_name', '')
                    file_path = parsed.get('file_path', '')
                    key = f"{file_path}::{class_name}::{method_name}"
                    method_id = method_nodes.get(key)
                    
                    if method_id:
                        for call in func.get('calls', []):
                            # Try to find target method
                            target_method_id = self._find_method_by_call(call, method_nodes, parsed_files)
                            if target_method_id:
                                self.graph.add_edge(method_id, target_method_id, relationship='CALLS')
        
        # Method USES_RESOURCE ExternalResource
        # External resource extraction disabled - relationships can be added manually later
        # if external_resources and parsed_files:
        #     for resource in external_resources:
        #         resource_id = f"resource_{hashlib.sha256(resource.get('name', '').encode()).hexdigest()[:16]}"
        #         source_file = resource.get('source', '')
        #         for method_key, method_id in method_nodes.items():
        #             if method_key.startswith(source_file + "::"):
        #                 self.graph.add_edge(method_id, resource_id, relationship='USES_RESOURCE')
        
        # ConfigArtifact DEFINES_KEY ConfigKey
        if config_data:
            for artifact in config_data.get('config_artifacts', []):
                artifact_id = f"config_{hashlib.sha256(artifact.get('path', '').encode()).hexdigest()[:16]}"
                artifact_name = artifact.get('name', '')
                
                for key_data in config_data.get('config_keys', []):
                    if key_data.get('artifact') == artifact_name:
                        key_id = f"key_{hashlib.sha256(key_data.get('key', '').encode()).hexdigest()[:16]}"
                        self.graph.add_edge(artifact_id, key_id, relationship='DEFINES_KEY')
                        
                        # ConfigKey OVERRIDES_IN_ENV Environment
                        env = key_data.get('environment', 'default')
                        env_id = f"env_{env}"
                        if env_id in self.graph.nodes():
                            self.graph.add_edge(key_id, env_id, relationship='OVERRIDES_IN_ENV')
        
        # DeploymentUnit CONFIGURED_BY ConfigArtifact
        if application_data and config_data:
            for du in application_data.get('deployment_units', []):
                du_id = f"du_{du.get('name', 'unknown')}"
                # Link to main config artifact (simplified)
                for artifact in config_data.get('config_artifacts', []):
                    if 'application' in artifact.get('name', '').lower():
                        artifact_id = f"config_{hashlib.sha256(artifact.get('path', '').encode()).hexdigest()[:16]}"
                        self.graph.add_edge(du_id, artifact_id, relationship='CONFIGURED_BY')
                        break
        
        # Class/Method USES_CONFIG ConfigArtifact (simplified - based on file proximity)
        if config_data:
            for artifact in config_data.get('config_artifacts', []):
                artifact_id = f"config_{hashlib.sha256(artifact.get('path', '').encode()).hexdigest()[:16]}"
                artifact_path = Path(artifact.get('path', ''))
                
                # Link classes in same directory or parent
                for key, class_id in class_nodes.items():
                    file_path = key.split("::")[0]
                    if artifact_path.parent in Path(file_path).parents or artifact_path.parent == Path(file_path).parent:
                        self.graph.add_edge(class_id, artifact_id, relationship='USES_CONFIG')
                
                # Link methods similarly
                for method_key, method_id in method_nodes.items():
                    file_path = method_key.split("::")[0]
                    if artifact_path.parent in Path(file_path).parents or artifact_path.parent == Path(file_path).parent:
                        self.graph.add_edge(method_id, artifact_id, relationship='USES_CONFIG_METHOD')
        
        # Method REFERENCES_KEY ConfigKey (simplified - based on config key usage in code)
        if config_data and parsed_files:
            for key_data in config_data.get('config_keys', []):
                key_name = key_data.get('key', '').split('.')[-1]  # Last part of key
                key_id = f"key_{hashlib.sha256(key_data.get('key', '').encode()).hexdigest()[:16]}"
                
                # Search for key usage in method code
                for parsed in parsed_files:
                    for func in parsed.get('functions', []):
                        method_name = func.get('name', '')
                        class_name = func.get('class_name', '')
                        file_path = parsed.get('file_path', '')
                        key = f"{file_path}::{class_name}::{method_name}"
                        method_id = method_nodes.get(key)
                        
                        if method_id and key_name.lower() in func.get('code', '').lower():
                            self.graph.add_edge(method_id, key_id, relationship='REFERENCES_KEY')
    
    def _find_class_by_name(self, class_name: str, class_nodes: Dict[str, str], parsed_files: List[Dict[str, Any]]) -> Optional[str]:
        """Find class node ID by name."""
        # Try exact match first
        for key, class_id in class_nodes.items():
            if key.endswith(f"::{class_name}"):
                return class_id
        
        # Try partial match
        for key, class_id in class_nodes.items():
            if class_name in key:
                return class_id
        
        return None
    
    def _find_method_by_call(self, call: str, method_nodes: Dict[str, str], parsed_files: List[Dict[str, Any]]) -> Optional[str]:
        """Find method node ID by call signature."""
        # Extract method name from call (e.g., "obj.method" -> "method")
        method_name = call.split('.')[-1] if '.' in call else call
        
        # Try to find matching method
        for key, method_id in method_nodes.items():
            if key.endswith(f"::{method_name}"):
                return method_id
        
        return None
    
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
    
    def load_graph(self, graph_path: str) -> bool:
        """Load graph from pickle file."""
        if not NETWORKX_AVAILABLE:
            print("⚠️ NetworkX not available")
            return False
        
        try:
            with open(graph_path, 'rb') as f:
                self.graph = pickle.load(f)
            print(f"✅ Graph loaded from {graph_path}")
            print(f"   Nodes: {self.graph.number_of_nodes()}, Edges: {self.graph.number_of_edges()}")
            return True
        except Exception as e:
            print(f"⚠️ Error loading graph: {e}")
            return False
    
    def visualize_3d(self, output_path: Optional[str] = None, max_nodes: int = 500) -> bool:
        """
        Create an interactive 3D visualization of the graph using Plotly.
        
        Args:
            output_path: Path to save HTML file (optional, if None, opens in browser)
            max_nodes: Maximum number of nodes to visualize (for performance)
        
        Returns:
            bool: True if visualization was created successfully
        """
        if not self.graph:
            print("⚠️ No graph available for visualization")
            return False
        
        try:
            import plotly.graph_objects as go
            import plotly.express as px
            PLOTLY_AVAILABLE = True
        except ImportError:
            print("⚠️ Plotly not available. Install: pip install plotly")
            print("   Or use: python visualize_graph_3d.py --graph-file <graph.pkl>")
            return False
        
        # Limit nodes for performance
        nodes = list(self.graph.nodes(data=True))
        original_node_count = len(nodes)
        
        if len(nodes) > max_nodes:
            print(f"⚠️ Graph has {len(nodes)} nodes, limiting to {max_nodes} for visualization")
            # Use nodes with highest degree (most connected)
            degrees = dict(self.graph.degree())
            top_nodes = sorted(degrees.items(), key=lambda x: x[1], reverse=True)[:max_nodes]
            node_set = set([n[0] for n in top_nodes])
            nodes = [(n, d) for n, d in nodes if n in node_set]
            # Filter edges to only include selected nodes
            edges = [(u, v) for u, v in self.graph.edges() if u in node_set and v in node_set]
            print(f"   Selected {len(nodes)} nodes with highest connectivity")
        else:
            edges = list(self.graph.edges())
        
        # Calculate 3D layout using spring layout
        print("📐 Calculating 3D layout...")
        pos_2d = nx.spring_layout(self.graph, k=1, iterations=50, seed=42)
        
        # Convert 2D to 3D by adding a Z coordinate based on node type or degree
        pos_3d = {}
        entity_type_map = {}
        
        for node, data in nodes:
            x, y = pos_2d[node]
            
            # Z coordinate based on entity type (if rich schema) or degree
            if self.use_rich_graph and 'entity_type' in data:
                entity_type = data.get('entity_type', 'CodeChunk')
                entity_type_map[node] = entity_type
                
                # Map entity types to Z coordinates (hierarchical)
                z_map = {
                    'Application': 5.0,
                    'Service': 4.0,
                    'DeploymentUnit': 3.5,
                    'File': 3.0,
                    'JavaClass': 2.0,
                    'Method': 1.0,
                    'ConfigArtifact': 2.5,
                    'ConfigKey': 1.5,
                    'Environment': 1.8,
                    'ExternalResource': 2.2,
                    'CodeChunk': 1.5
                }
                z = z_map.get(entity_type, 1.0)
            else:
                # Use degree for Z coordinate (normalized)
                degree = self.graph.degree(node)
                z = min(degree * 0.1, 3.0)  # Cap at 3.0
                entity_type_map[node] = 'CodeChunk'
            
            pos_3d[node] = (x, y, z)
        
        # Prepare edge traces
        print("🔗 Preparing edge traces...")
        edge_x = []
        edge_y = []
        edge_z = []
        
        for u, v in edges:
            if u in pos_3d and v in pos_3d:
                x0, y0, z0 = pos_3d[u]
                x1, y1, z1 = pos_3d[v]
                edge_x.extend([x0, x1, None])
                edge_y.extend([y0, y1, None])
                edge_z.extend([z0, z1, None])
        
        edge_trace = go.Scatter3d(
            x=edge_x, y=edge_y, z=edge_z,
            line=dict(width=1, color='#888'),
            hoverinfo='none',
            mode='lines',
            name='Edges',
            showlegend=False
        )
        
        # Prepare node traces (grouped by entity type for rich schema)
        print("📊 Preparing node traces...")
        node_traces = []
        
        # Group nodes by entity type
        entity_types = {}
        for node, data in nodes:
            entity_type = entity_type_map.get(node, 'CodeChunk')
            if entity_type not in entity_types:
                entity_types[entity_type] = []
            entity_types[entity_type].append((node, data))
        
        # Color palette for different entity types
        colors = px.colors.qualitative.Set3 + px.colors.qualitative.Pastel
        
        for i, (entity_type, type_nodes) in enumerate(entity_types.items()):
            node_x = [pos_3d[n][0] for n, _ in type_nodes]
            node_y = [pos_3d[n][1] for n, _ in type_nodes]
            node_z = [pos_3d[n][2] for n, _ in type_nodes]
            
            node_text = []
            node_info = []
            node_sizes = []
            
            for node, data in type_nodes:
                # Get display name
                name = data.get('name', data.get('fqn', str(node)))
                node_text.append(name[:40])  # Truncate for display
                
                # Build hover info
                info = f"<b>{entity_type}</b><br>"
                info += f"Name: {name}<br>"
                if 'fqn' in data and data['fqn']:
                    info += f"FQN: {data['fqn']}<br>"
                if 'file_path' in data and data['file_path']:
                    info += f"File: {data['file_path']}<br>"
                if 'type' in data:
                    info += f"Type: {data['type']}<br>"
                info += f"Connections: {self.graph.degree(node)}"
                node_info.append(info)
                
                # Size based on degree
                degree = self.graph.degree(node)
                node_sizes.append(max(5, min(degree * 2, 20)))
            
            node_traces.append(go.Scatter3d(
                x=node_x, y=node_y, z=node_z,
                mode='markers',
                name=f"{entity_type} ({len(type_nodes)})",
                marker=dict(
                    size=node_sizes,
                    color=colors[i % len(colors)],
                    line=dict(width=0.5, color='white'),
                    opacity=0.8
                ),
                text=node_text,
                hovertemplate='%{customdata}<extra></extra>',
                customdata=node_info
            ))
        
        # Create figure
        print("🎨 Creating 3D visualization...")
        fig = go.Figure(data=[edge_trace] + node_traces)
        
        # Determine if rich schema
        is_rich_schema = len(entity_types) > 1
        
        fig.update_layout(
            title=dict(
                text=f'3D Knowledge Graph Visualization<br><sub>{original_node_count} nodes, {self.graph.number_of_edges()} edges</sub>',
                x=0.5,
                xanchor='center'
            ),
            scene=dict(
                xaxis=dict(title='X', backgroundcolor='rgb(240, 240, 240)'),
                yaxis=dict(title='Y', backgroundcolor='rgb(240, 240, 240)'),
                zaxis=dict(
                    title='Z (Entity Type Hierarchy)' if is_rich_schema else 'Z (Node Degree)',
                    backgroundcolor='rgb(240, 240, 240)'
                ),
                bgcolor='rgb(250, 250, 250)',
                camera=dict(
                    eye=dict(x=1.5, y=1.5, z=1.5)
                )
            ),
            width=1400,
            height=900,
            showlegend=True,
            hovermode='closest',
            margin=dict(b=20, l=5, r=5, t=60),
            legend=dict(
                x=1.02,
                y=1,
                bgcolor='rgba(255, 255, 255, 0.8)',
                bordercolor='rgba(0, 0, 0, 0.2)',
                borderwidth=1
            )
        )
        
        # Save or show
        if output_path:
            output_file = Path(output_path)
            output_file.parent.mkdir(parents=True, exist_ok=True)
            fig.write_html(str(output_file))
            print(f"✅ 3D graph visualization saved to {output_file}")
            print(f"   Open {output_file} in a web browser to view the interactive 3D graph")
        else:
            fig.show()
            print("✅ 3D graph visualization opened in browser")
        
        return True


class TigerGraphPort:
    """Port NetworkX graph to TigerDB."""
    
    def __init__(
        self,
        host: str,
        graphname: str,
        username: str = "tigergraph",
        password: Optional[str] = None,
        secret: Optional[str] = None,
        use_ssl: bool = True
    ):
        """
        Initialize TigerGraph connection.
        
        Args:
            host: TigerGraph host (e.g., "https://your-instance.i.tgcloud.io")
            graphname: Graph name in TigerDB
            username: TigerGraph username
            password: TigerGraph password
            secret: TigerGraph secret (for cloud instances)
            use_ssl: Use SSL for connection
        """
        self.host = host
        self.graphname = graphname
        self.username = username
        self.password = password
        self.secret = secret
        self.use_ssl = use_ssl
        self.conn = None
        
        if TIGERGRAPH_AVAILABLE:
            try:
                self.conn = TigerGraphConnection(
                    host=host,
                    graphname=graphname,
                    username=username,
                    password=password,
                    secret=secret,
                    useSSL=use_ssl
                )
                print(f"✅ Connected to TigerGraph: {host}/{graphname}")
            except Exception as e:
                print(f"⚠️ Failed to connect to TigerGraph: {e}")
        else:
            print("⚠️ TigerGraph not available. Install: pip install pyTigerGraph")
    
    def ensure_schema(self, use_rich_schema: bool = True):
        """Ensure TigerGraph schema exists (create if not)."""
        if not self.conn:
            return False
        
        try:
            # Check if graph exists
            graphs = self.conn.getGraphs()
            if self.graphname in graphs:
                print(f"✅ Graph '{self.graphname}' exists in TigerDB")
                return True
            
            # Create schema if it doesn't exist
            print(f"📝 Creating graph schema '{self.graphname}'...")
            
            if use_rich_schema:
                # Create rich schema with all entity types
                # Vertex types
                vertex_types = [
                    ("Application", "PRIMARY_ID app_id STRING, name STRING, display_name STRING, type STRING, build_system STRING"),
                    ("Service", "PRIMARY_ID service_id STRING, name STRING, path STRING, type STRING"),
                    ("File", "PRIMARY_ID file_id STRING, file_path STRING, name STRING"),
                    ("JavaClass", "PRIMARY_ID class_id STRING, name STRING, fqn STRING, file_path STRING, start_line INT, end_line INT, language STRING"),
                    ("Method", "PRIMARY_ID method_id STRING, name STRING, fqn STRING, class_name STRING, file_path STRING, start_line INT, end_line INT, language STRING"),
                    ("ConfigArtifact", "PRIMARY_ID artifact_id STRING, name STRING, path STRING, type STRING, environment STRING"),
                    ("ConfigKey", "PRIMARY_ID key_id STRING, key STRING, value STRING, artifact STRING, environment STRING"),
                    ("Environment", "PRIMARY_ID env_id STRING, name STRING"),
                    ("ExternalResource", "PRIMARY_ID resource_id STRING, name STRING, type STRING, source STRING"),
                    ("DeploymentUnit", "PRIMARY_ID du_id STRING, name STRING, type STRING, service STRING")
                ]
                
                for vertex_name, vertex_def in vertex_types:
                    try:
                        self.conn.gsql(f"CREATE VERTEX {vertex_name} ({vertex_def})")
                    except Exception as e:
                        print(f"⚠️ Error creating vertex {vertex_name}: {e}")
                
                # Edge types
                edge_types = [
                    ("DEPLOYED_AS", "Application", "DeploymentUnit", "relationship STRING"),
                    ("OWNS", "Application", "Service", "relationship STRING"),
                    ("CONTAINS", "Service", "File", "relationship STRING"),
                    ("DECLARES", "File", "JavaClass", "relationship STRING"),
                    ("EXTENDS", "JavaClass", "JavaClass", "relationship STRING"),
                    ("IMPLEMENTS", "JavaClass", "JavaClass", "relationship STRING"),
                    ("REFERENCES", "JavaClass", "JavaClass", "relationship STRING"),
                    ("DECLARES_METHOD", "JavaClass", "Method", "relationship STRING"),
                    ("CALLS", "Method", "Method", "relationship STRING"),
                    ("USES_CONFIG", "JavaClass", "ConfigArtifact", "relationship STRING"),
                    ("USES_CONFIG_METHOD", "Method", "ConfigArtifact", "relationship STRING"),
                    ("REFERENCES_KEY", "Method", "ConfigKey", "relationship STRING"),
                    ("DEFINES_KEY", "ConfigArtifact", "ConfigKey", "relationship STRING"),
                    ("OVERRIDES_IN_ENV", "ConfigKey", "Environment", "relationship STRING"),
                    ("CONFIGURED_BY", "DeploymentUnit", "ConfigArtifact", "relationship STRING"),
                    ("USES_RESOURCE", "Method", "ExternalResource", "relationship STRING")
                ]
                
                for edge_name, from_vertex, to_vertex, attrs in edge_types:
                    try:
                        self.conn.gsql(f"""
                            CREATE DIRECTED EDGE {edge_name} (
                                FROM {from_vertex},
                                TO {to_vertex},
                                {attrs}
                            )
                        """)
                    except Exception as e:
                        print(f"⚠️ Error creating edge {edge_name}: {e}")
                
                # Create graph with all vertices and edges
                all_vertices = ", ".join([v[0] for v in vertex_types])
                all_edges = ", ".join([e[0] for e in edge_types])
                
                self.conn.gsql(f"""
                    CREATE GRAPH {self.graphname} (
                        {all_vertices},
                        {all_edges}
                    )
                """)
            else:
                # Simple schema (backward compatibility)
                self.conn.gsql(f"""
                    CREATE VERTEX CodeChunk (
                        PRIMARY_ID chunk_id STRING,
                        fqn STRING,
                        type STRING,
                        file_path STRING,
                        start_line INT,
                        end_line INT,
                        code TEXT,
                        summary STRING,
                        language STRING
                    )
                """)
                
                self.conn.gsql(f"""
                    CREATE DIRECTED EDGE IN_FILE (
                        FROM CodeChunk,
                        TO CodeChunk,
                        relationship STRING
                    )
                """)
                
                self.conn.gsql(f"""
                    CREATE GRAPH {self.graphname} (
                        CodeChunk,
                        IN_FILE
                    )
                """)
            
            print(f"✅ Created graph schema '{self.graphname}'")
            return True
        except Exception as e:
            print(f"⚠️ Error ensuring schema: {e}")
            import traceback
            print(traceback.format_exc())
            return False
    
    def port_from_networkx(self, nx_graph, chunks: Optional[List[Dict[str, Any]]] = None, use_rich_schema: bool = True):
        """
        Port NetworkX graph to TigerDB.
        
        Args:
            nx_graph: NetworkX graph object
            chunks: Optional list of chunks for additional metadata
            use_rich_schema: Whether to use rich schema (default: True)
        """
        if not self.conn:
            print("⚠️ TigerGraph connection not available")
            return False
        
        if not self.ensure_schema(use_rich_schema=use_rich_schema):
            return False
        
        try:
            if use_rich_schema:
                # Port rich schema graph
                return self._port_rich_schema(nx_graph, chunks)
            else:
                # Port simple schema graph (backward compatibility)
                return self._port_simple_schema(nx_graph, chunks)
        except Exception as e:
            print(f"⚠️ Error porting graph to TigerDB: {e}")
            import traceback
            print(traceback.format_exc())
            return False
    
    def _port_rich_schema(self, nx_graph, chunks: Optional[List[Dict[str, Any]]]):
        """Port rich schema graph to TigerDB."""
        # Group vertices by entity type
        vertices_by_type = {}
        for node_id, node_data in nx_graph.nodes(data=True):
            entity_type = node_data.get('entity_type', 'CodeChunk')
            if entity_type not in vertices_by_type:
                vertices_by_type[entity_type] = []
            
            # Prepare vertex based on entity type
            vertex = {"id": node_id}
            
            if entity_type == 'Application':
                vertex.update({
                    "app_id": node_id,
                    "name": node_data.get('name', ''),
                    "display_name": node_data.get('display_name', ''),
                    "type": node_data.get('type', ''),
                    "build_system": node_data.get('build_system', '')
                })
            elif entity_type == 'Service':
                vertex.update({
                    "service_id": node_id,
                    "name": node_data.get('name', ''),
                    "path": node_data.get('path', ''),
                    "type": node_data.get('type', '')
                })
            elif entity_type == 'File':
                vertex.update({
                    "file_id": node_id,
                    "file_path": node_data.get('file_path', ''),
                    "name": node_data.get('name', '')
                })
            elif entity_type == 'JavaClass':
                vertex.update({
                    "class_id": node_id,
                    "name": node_data.get('name', ''),
                    "fqn": node_data.get('fqn', ''),
                    "file_path": node_data.get('file_path', ''),
                    "start_line": node_data.get('start_line', 1),
                    "end_line": node_data.get('end_line', 1),
                    "language": node_data.get('language', 'unknown')
                })
            elif entity_type == 'Method':
                vertex.update({
                    "method_id": node_id,
                    "name": node_data.get('name', ''),
                    "fqn": node_data.get('fqn', ''),
                    "class_name": node_data.get('class_name', ''),
                    "file_path": node_data.get('file_path', ''),
                    "start_line": node_data.get('start_line', 1),
                    "end_line": node_data.get('end_line', 1),
                    "language": node_data.get('language', 'unknown')
                })
            elif entity_type == 'ConfigArtifact':
                vertex.update({
                    "artifact_id": node_id,
                    "name": node_data.get('name', ''),
                    "path": node_data.get('path', ''),
                    "type": node_data.get('type', ''),
                    "environment": node_data.get('environment', 'default')
                })
            elif entity_type == 'ConfigKey':
                vertex.update({
                    "key_id": node_id,
                    "key": node_data.get('key', ''),
                    "value": node_data.get('value', ''),
                    "artifact": node_data.get('artifact', ''),
                    "environment": node_data.get('environment', 'default')
                })
            elif entity_type == 'Environment':
                vertex.update({
                    "env_id": node_id,
                    "name": node_data.get('name', 'default')
                })
            elif entity_type == 'ExternalResource':
                vertex.update({
                    "resource_id": node_id,
                    "name": node_data.get('name', ''),
                    "type": node_data.get('type', ''),
                    "source": node_data.get('source', '')
                })
            elif entity_type == 'DeploymentUnit':
                vertex.update({
                    "du_id": node_id,
                    "name": node_data.get('name', ''),
                    "type": node_data.get('type', ''),
                    "service": node_data.get('service', '')
                })
            
            vertices_by_type[entity_type].append(vertex)
        
        # Upload vertices by type
        total_vertices = 0
        for entity_type, vertices in vertices_by_type.items():
            if vertices:
                print(f"📤 Uploading {len(vertices)} {entity_type} vertices...")
                try:
                    self.conn.upsertVertex(entity_type, vertices)
                    total_vertices += len(vertices)
                    print(f"✅ Uploaded {len(vertices)} {entity_type} vertices")
                except Exception as e:
                    print(f"⚠️ Error uploading {entity_type} vertices: {e}")
        
        # Upload edges
        edges_by_type = {}
        for source, target, edge_data in nx_graph.edges(data=True):
            relationship = edge_data.get('relationship', 'UNKNOWN')
            source_type = nx_graph.nodes[source].get('entity_type', 'CodeChunk')
            target_type = nx_graph.nodes[target].get('entity_type', 'CodeChunk')
            
            edge_key = f"{relationship}_{source_type}_{target_type}"
            if edge_key not in edges_by_type:
                edges_by_type[edge_key] = []
            
            edges_by_type[edge_key].append({
                "source": source,
                "target": target,
                "relationship": relationship,
                "source_type": source_type,
                "target_type": target_type
            })
        
        total_edges = 0
        for edge_key, edges in edges_by_type.items():
            if edges:
                relationship = edges[0]['relationship']
                source_type = edges[0]['source_type']
                target_type = edges[0]['target_type']
                
                print(f"📤 Uploading {len(edges)} {relationship} edges...")
                try:
                    for edge in edges:
                        self.conn.upsertEdge(
                            source_type, edge['source'], relationship,
                            target_type, edge['target'],
                            {"relationship": relationship}
                        )
                    total_edges += len(edges)
                    print(f"✅ Uploaded {len(edges)} {relationship} edges")
                except Exception as e:
                    print(f"⚠️ Error uploading {relationship} edges: {e}")
        
        print(f"✅ Successfully ported rich graph to TigerDB: {total_vertices} nodes, {total_edges} edges")
        return True
    
    def _port_simple_schema(self, nx_graph, chunks: Optional[List[Dict[str, Any]]]):
        """Port simple schema graph to TigerDB (backward compatibility)."""
        # Prepare vertices (nodes)
        vertices = []
        for node_id, node_data in nx_graph.nodes(data=True):
            vertex = {
                "chunk_id": node_id,
                "fqn": node_data.get('fqn', ''),
                "type": node_data.get('type', ''),
                "file_path": node_data.get('file_path', ''),
                "start_line": node_data.get('start_line', 1),
                "end_line": node_data.get('end_line', 1),
                "code": "",
                "summary": "",
                "language": node_data.get('language', 'unknown')
            }
            
            if chunks:
                for chunk in chunks:
                    if chunk.get('chunk_id') == node_id:
                        vertex['summary'] = chunk.get('summary', '')
                        break
            
            vertices.append(vertex)
        
        # Upload vertices
        print(f"📤 Uploading {len(vertices)} vertices to TigerDB...")
        self.conn.upsertVertex("CodeChunk", vertices)
        print(f"✅ Uploaded {len(vertices)} vertices")
        
        # Upload edges
        edges = []
        for source, target, edge_data in nx_graph.edges(data=True):
            edges.append({
                "source": source,
                "target": target,
                "relationship": edge_data.get('relationship', 'IN_FILE')
            })
        
        print(f"📤 Uploading {len(edges)} edges to TigerDB...")
        for edge in edges:
            self.conn.upsertEdge(
                "CodeChunk", edge['source'], "IN_FILE",
                "CodeChunk", edge['target'],
                {"relationship": edge['relationship']}
            )
        print(f"✅ Uploaded {len(edges)} edges")
        
        print(f"✅ Successfully ported simple graph to TigerDB: {len(vertices)} nodes, {len(edges)} edges")
        return True
    
    def port_from_file(self, graph_file: str, chunks_file: Optional[str] = None):
        """
        Load NetworkX graph from file and port to TigerDB.
        
        Args:
            graph_file: Path to NetworkX pickle file
            chunks_file: Optional path to chunks JSON file for metadata
        """
        if not NETWORKX_AVAILABLE:
            print("⚠️ NetworkX not available")
            return False
        
        # Load graph
        try:
            with open(graph_file, 'rb') as f:
                nx_graph = pickle.load(f)
            print(f"✅ Loaded graph from {graph_file}")
        except Exception as e:
            print(f"⚠️ Error loading graph file: {e}")
            return False
        
        # Load chunks if provided
        chunks = None
        if chunks_file and Path(chunks_file).exists():
            try:
                with open(chunks_file, 'r') as f:
                    chunks = json.load(f)
                print(f"✅ Loaded chunks from {chunks_file}")
            except Exception as e:
                print(f"⚠️ Error loading chunks file: {e}")
        
        # Port to TigerDB (use rich schema by default)
        return self.port_from_networkx(nx_graph, chunks, use_rich_schema=True)


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
    parser.add_argument("--opensearch-host", help="OpenSearch host/endpoint (e.g., localhost:9200 or search-domain.us-east-1.es.amazonaws.com)")
    parser.add_argument("--opensearch-index", default="code_chunks", help="OpenSearch index name")
    parser.add_argument("--opensearch-config", help="Path to config.ini file for OpenSearch configuration")
    parser.add_argument("--opensearch-use-aws-auth", action="store_true", default=True, help="Use AWS authentication for OpenSearch (default: True)")
    parser.add_argument("--opensearch-no-aws-auth", action="store_false", dest="opensearch_use_aws_auth", help="Disable AWS authentication (use basic auth)")
    parser.add_argument("--opensearch-region", default="us-east-1", help="AWS region for OpenSearch (default: us-east-1)")
    parser.add_argument("--opensearch-use-ssl", action="store_true", default=True, help="Use SSL for OpenSearch connection (default: True)")
    parser.add_argument("--opensearch-verify-certs", action="store_true", default=True, help="Verify SSL certificates (default: True)")
    parser.add_argument("--opensearch-batch-size", type=int, default=100, help="Number of chunks per bulk index batch (default: 100)")
    parser.add_argument("--opensearch-max-workers", type=int, default=4, help="Maximum number of parallel workers for batch indexing (default: 4)")
    parser.add_argument("--application-name", help="Application name (if not provided, will be extracted from pom.xml)")
    parser.add_argument("--seal-id", help="Seal ID (if not provided, will be extracted from pom.xml properties)")
    parser.add_argument("--openai-api-key", help="OpenAI API key for embeddings")
    parser.add_argument("--embedding-model", default="text-embedding-3-small", help="Embedding model")
    parser.add_argument("--use-azure-embeddings", action="store_true", help="Use Azure OpenAI Embeddings service (requires config.ini)")
    parser.add_argument("--user-sid", default="default_user", help="User session ID for Azure embeddings (default: default_user)")
    parser.add_argument("--azure-cert-path", help="Path to Azure certificate file (.pem)")
    parser.add_argument("--azure-config-path", help="Path to config.ini file (default: script directory)")
    
    # TigerGraph/TigerDB arguments
    parser.add_argument("--tigergraph-host", help="TigerGraph host (e.g., https://your-instance.i.tgcloud.io)")
    parser.add_argument("--tigergraph-graphname", default="code_knowledge_graph", help="TigerGraph graph name (default: code_knowledge_graph)")
    parser.add_argument("--tigergraph-username", default="tigergraph", help="TigerGraph username (default: tigergraph)")
    parser.add_argument("--tigergraph-password", help="TigerGraph password")
    parser.add_argument("--tigergraph-secret", help="TigerGraph secret (for cloud instances)")
    parser.add_argument("--port-to-tigergraph", action="store_true", help="Port NetworkX graph to TigerDB after building")
    parser.add_argument("--port-graph-file", help="Port existing NetworkX graph file to TigerDB (requires --tigergraph-host)")
    parser.add_argument("--use-rich-graph", action="store_true", default=True, help="Use rich graph schema with Application, Service, Config, etc. (default: True)")
    parser.add_argument("--use-simple-graph", action="store_false", dest="use_rich_graph", help="Use simple graph schema (backward compatibility)")
    
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
    parser.add_argument("--visualize-3d", action="store_true", help="Generate 3D graph visualization (requires plotly)")
    parser.add_argument("--max-nodes-3d", type=int, default=500, help="Maximum nodes for 3D visualization (default: 500)")
    
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
    
    # Port graph file mode (standalone operation)
    if args.port_graph_file:
        if not args.tigergraph_host:
            raise SystemExit("❌ --tigergraph-host is required when using --port-graph-file")
        
        tigergraph = TigerGraphPort(
            host=args.tigergraph_host,
            graphname=args.tigergraph_graphname,
            username=args.tigergraph_username,
            password=args.tigergraph_password,
            secret=args.tigergraph_secret,
            use_ssl=True
        )
        
        # Find chunks file in same directory as graph file
        graph_path = Path(args.port_graph_file)
        chunks_file = graph_path.parent / "chunks.json"
        chunks_file = str(chunks_file) if chunks_file.exists() else None
        
        success = tigergraph.port_from_file(str(args.port_graph_file), chunks_file)
        if success:
            print("✅ Graph successfully ported to TigerDB")
        else:
            raise SystemExit("❌ Failed to port graph to TigerDB")
        return
    
    # Full repository mode
    if not args.repo_path:
        raise SystemExit("❌ Either --file (single file mode), --repo-path (full repository mode), or --port-graph-file (port mode) is required.")
    
    # Check OpenSearch connectivity at the start (if configured)
    opensearch = None
    if args.opensearch_host or args.opensearch_config:
        print("\n🔍 Initializing OpenSearch connection...")
        # Extract application_name and sealId early for OpenSearch initialization
        application_name = args.application_name
        seal_id = args.seal_id
        
        # If not provided, try to extract from pom.xml
        if not application_name or not seal_id:
            try:
                app_extractor = ApplicationServiceExtractor(args.repo_path)
                app_data = app_extractor.extract()
                if not application_name:
                    application_name = app_data.get('application', {}).get('name', '')
                if not seal_id:
                    seal_id = app_data.get('application', {}).get('seal_id', '')
            except Exception as e:
                print(f"⚠️ Could not extract application info from pom.xml: {e}")
        
        opensearch = StandaloneOpenSearch(
            host=args.opensearch_host,
            index=args.opensearch_index,
            config_path=args.opensearch_config,
            use_aws_auth=args.opensearch_use_aws_auth,
            region=args.opensearch_region,
            use_ssl=args.opensearch_use_ssl,
            verify_certs=args.opensearch_verify_certs,
            application_name=application_name,
            seal_id=seal_id
        )
        
        # Check connectivity and list indexes before proceeding
        connectivity_ok = await opensearch.check_connectivity_and_list_indexes()
        if not connectivity_ok:
            print("❌ OpenSearch connectivity check failed. Exiting.")
            raise SystemExit("Failed to connect to OpenSearch. Please check your configuration.")
        
        print()  # Empty line for readability
    
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
        checkpoint_file=checkpoint_file,
        use_azure_embeddings=args.use_azure_embeddings,
        user_sid=args.user_sid,
        azure_cert_path=args.azure_cert_path,
        azure_config_path=args.azure_config_path
    )
    
    # Process repository
    chunks = await indexer.process_repository(args.repo_path)
    
    # Extract application_name and sealId (if not already extracted during OpenSearch init)
    if not opensearch:
        application_name = args.application_name
        seal_id = args.seal_id
        
        # If not provided, extract from pom.xml
        if not application_name or not seal_id:
            app_extractor = ApplicationServiceExtractor(args.repo_path)
            app_data = app_extractor.extract()
            if not application_name:
                application_name = app_data.get('application', {}).get('name', '')
            if not seal_id:
                seal_id = app_data.get('application', {}).get('seal_id', '')
    
    # Save chunks to JSON
    chunks_file = output_dir / "chunks.json"
    with open(chunks_file, 'w') as f:
        json.dump(chunks, f, indent=2)
    print(f"✅ Saved chunks to {chunks_file}")
    
    # Index to OpenSearch if configured (opensearch instance already created and checked)
    if opensearch:
        print("\n🔍 Initializing OpenSearch connection...")
        opensearch = StandaloneOpenSearch(
            host=args.opensearch_host,
            index=args.opensearch_index,
            config_path=args.opensearch_config,
            use_aws_auth=args.opensearch_use_aws_auth,
            region=args.opensearch_region,
            use_ssl=args.opensearch_use_ssl,
            verify_certs=args.opensearch_verify_certs,
            application_name=application_name,
            seal_id=seal_id
        )
        
        # Check connectivity and list indexes before proceeding
        connectivity_ok = await opensearch.check_connectivity_and_list_indexes()
        if not connectivity_ok:
            print("❌ OpenSearch connectivity check failed. Exiting.")
            raise SystemExit("Failed to connect to OpenSearch. Please check your configuration.")
        
        print()  # Empty line for readability
        
        # Now proceed with indexing using bulk API with parallel processing
        await opensearch.index_chunks(
            chunks,
            batch_size=args.opensearch_batch_size,
            max_workers=args.opensearch_max_workers
        )
    
    # Extract additional data for rich graph
    application_data = None
    config_data = None
    external_resources = []
    parsed_files = []
    
    use_rich_graph = getattr(args, 'use_rich_graph', True)
    
    if use_rich_graph:
        print("\n📊 Extracting application and service information...")
        app_extractor = ApplicationServiceExtractor(args.repo_path)
        application_data = app_extractor.extract()
        
        print("📊 Extracting configuration data...")
        config_parser = ConfigFileParser(args.repo_path)
        config_data = config_parser.extract()
        
        print("📊 Collecting parsed file data...")
        # Re-parse files to get relationship data
        parser = StandaloneParser()
        code_files = indexer.find_code_files(args.repo_path)
        for file_path in code_files[:1000]:  # Limit to avoid memory issues
            parsed = parser.parse_file(file_path)
            if parsed:
                parsed_files.append(parsed)
        
        # External resource extraction removed - schema supports it but extraction is disabled for now
        # external_resources = []
    
    # Build graph (rich graph if enabled, otherwise simple)
    graph_builder = StandaloneGraphBuilder(use_rich_graph=use_rich_graph)
    graph_builder.build_graph(
        chunks=chunks,
        application_data=application_data,
        config_data=config_data,
        external_resources=external_resources,
        parsed_files=parsed_files
    )
    
    # Save graph
    graph_file = output_dir / "graph.pkl"
    graph_builder.save_graph(str(graph_file))
    
    stats = graph_builder.get_stats()
    print(f"\n✅ Graph built and saved: {stats}")
    
    # Generate 3D visualization if requested
    if args.visualize_3d:
        graph_3d_file = output_dir / "graph_3d.html"
        print(f"\n🎨 Generating 3D visualization...")
        graph_builder.visualize_3d(str(graph_3d_file), max_nodes=args.max_nodes_3d)
    
    # Port to TigerDB if configured or if Azure embeddings are enabled
    should_port_to_tiger = (args.port_to_tigergraph and args.tigergraph_host) or (args.use_azure_embeddings and args.tigergraph_host)
    if should_port_to_tiger:
        print(f"\n🐅 Porting graph to TigerDB...")
        tigergraph = TigerGraphPort(
            host=args.tigergraph_host,
            graphname=args.tigergraph_graphname,
            username=args.tigergraph_username,
            password=args.tigergraph_password,
            secret=args.tigergraph_secret,
            use_ssl=True
        )
        tigergraph.port_from_networkx(graph_builder.graph, chunks, use_rich_schema=use_rich_graph)
    
    print(f"\n✅ Complete! Stats: {stats}")


if __name__ == "__main__":
    asyncio.run(main())

