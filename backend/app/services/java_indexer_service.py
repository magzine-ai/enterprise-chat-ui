"""
Multi-Language Code Indexer Service for AST extraction, chunk generation, and embedding.

This service parses codebases in multiple languages (Java, Python, JavaScript/TypeScript, Go, Rust),
extracts AST information, generates chunks at multiple levels (method, class, file, module),
builds call graphs, and creates embeddings for semantic search.

For Java, it uses javalang for optimal parsing. For other languages, it uses TreeSitter.
"""

from typing import List, Dict, Any, Optional, Set, Tuple
from pathlib import Path
import os
import re
from datetime import datetime
from sqlmodel import Session, select
from app.core.config import settings
from app.models.java_repository import JavaRepository, RepositoryIndexStatus
from app.models.java_chunk import JavaChunk, ChunkType
from openai import AsyncOpenAI
import asyncio
from app.services.multi_language_parser import get_multi_language_parser

# Try to import javalang for AST parsing
try:
    import javalang
    JAVALANG_AVAILABLE = True
except ImportError:
    JAVALANG_AVAILABLE = False
    javalang = None
    print("⚠️ javalang not installed. Install with: pip install javalang")

# Try to import networkx for call graphs
try:
    import networkx as nx
    NETWORKX_AVAILABLE = True
except ImportError:
    NETWORKX_AVAILABLE = False
    print("⚠️ networkx not installed. Install with: pip install networkx")


class JavaIndexerService:
    """
    Service for indexing Java codebases.
    
    Handles AST extraction, chunk generation, call graph building,
    and embedding generation for Java code.
    """
    
    def __init__(self):
        """Initialize the multi-language indexer service."""
        self.embedding_client = None
        if settings.openai_api_key:
            self.embedding_client = AsyncOpenAI(api_key=settings.openai_api_key)
        self.call_graph = {}  # Dict[str, Set[str]]: method FQN -> set of callee FQNs
        self.type_hierarchy = {}  # Dict[str, str]: class FQN -> parent class FQN
        self.multi_lang_parser = None
        try:
            self.multi_lang_parser = get_multi_language_parser()
        except Exception as e:
            print(f"⚠️ Multi-language parser not available: {e}")
    
    def detect_language(self, file_path: str) -> str:
        """
        Detect programming language from file extension.
        
        Args:
            file_path: Path to the file
            
        Returns:
            Language name (java, python, javascript, typescript, go, rust)
        """
        ext_map = {
            '.java': 'java',
            '.py': 'python',
            '.js': 'javascript',
            '.jsx': 'javascript',
            '.ts': 'typescript',
            '.tsx': 'typescript',
            '.go': 'go',
            '.rs': 'rust',
        }
        
        ext = Path(file_path).suffix.lower()
        return ext_map.get(ext, 'java')  # Default to Java for backward compatibility
    
    def find_code_files(self, repo_path: str, language: Optional[str] = None) -> List[str]:
        """
        Find all code files in a repository, optionally filtered by language.
        
        Args:
            repo_path: Path to the repository root
            language: Optional language filter (java, python, javascript, etc.)
            
        Returns:
            List[str]: List of code file paths
        """
        code_files = []
        repo = Path(repo_path)
        
        if not repo.exists():
            return code_files
        
        # Exclude common directories
        exclude_dirs = {'.git', '.idea', 'node_modules', 'target', 'build', '.gradle', '.mvn', 
                       '__pycache__', '.venv', 'venv', 'dist', '.pytest_cache'}
        
        # Language-specific extensions
        extensions = {
            'java': ['*.java'],
            'python': ['*.py'],
            'javascript': ['*.js', '*.jsx'],
            'typescript': ['*.ts', '*.tsx'],
            'go': ['*.go'],
            'rust': ['*.rs'],
        }
        
        if language:
            patterns = extensions.get(language.lower(), [])
        else:
            # All languages
            patterns = []
            for ext_list in extensions.values():
                patterns.extend(ext_list)
        
        for pattern in patterns:
            for code_file in repo.rglob(pattern):
                # Skip if in excluded directory
                if any(excluded in code_file.parts for excluded in exclude_dirs):
                    continue
                code_files.append(str(code_file))
        
        return code_files
    
    def find_java_files(self, repo_path: str) -> List[str]:
        """
        Find all Java files in a repository.
        
        Args:
            repo_path: Path to the repository root
        
        Returns:
            List[str]: List of Java file paths
        """
        java_files = []
        repo = Path(repo_path)
        
        if not repo.exists():
            return java_files
        
        # Exclude common directories
        exclude_dirs = {'.git', '.idea', 'node_modules', 'target', 'build', '.gradle', '.mvn'}
        
        for java_file in repo.rglob('*.java'):
            # Skip if in excluded directory
            if any(excluded in java_file.parts for excluded in exclude_dirs):
                continue
            java_files.append(str(java_file))
        
        return java_files
    
    def parse_file(self, file_path: str, language: Optional[str] = None) -> Optional[Dict[str, Any]]:
        """
        Parse a code file and extract AST information.
        Supports multiple languages with Java-optimized parsing.
        
        Args:
            file_path: Path to the code file
            language: Optional language hint (auto-detected if not provided)
        
        Returns:
            Dict with parsed information: classes, methods, imports, etc.
        """
        if language is None:
            language = self.detect_language(file_path)
        
        # Use Java-specific parser for Java files (optimized)
        if language == 'java':
            return self.parse_java_file(file_path)
        
        # Use TreeSitter for other languages
        if self.multi_lang_parser and self.multi_lang_parser.is_language_supported(language):
            return self._parse_with_treesitter(file_path, language)
        
        # Fallback: try basic parsing
        print(f"⚠️ Language {language} not supported, attempting basic parsing")
        return self._parse_file_basic(file_path, language)
    
    def parse_java_file(self, file_path: str) -> Optional[Dict[str, Any]]:
        """
        Parse a Java file using javalang (optimized for Java).
        
        Args:
            file_path: Path to the Java file
        
        Returns:
            Dict with parsed information: classes, methods, imports, etc.
        """
        if not JAVALANG_AVAILABLE:
            print("⚠️ javalang not available, trying TreeSitter or basic parsing")
            if self.multi_lang_parser and self.multi_lang_parser.is_language_supported('java'):
                return self._parse_with_treesitter(file_path, 'java')
            return self._parse_java_file_basic(file_path)
        
        try:
            with open(file_path, 'r', encoding='utf-8', errors='ignore') as f:
                content = f.read()
            
            tree = javalang.parse.parse(content)
            
            package_name = tree.package.name if tree.package else ""
            imports = [imp.path for imp in tree.imports] if tree.imports else []
            
            classes = []
            methods = []
            
            for path, node in tree:
                if isinstance(node, javalang.tree.ClassDeclaration):
                    class_info = self._extract_class_info(node, package_name, file_path)
                    classes.append(class_info)
                    
                    # Extract methods from class
                    for method in node.methods:
                        method_info = self._extract_method_info(
                            method, class_info['fqn'], file_path
                        )
                        methods.append(method_info)
            
            return {
                'package': package_name,
                'imports': imports,
                'classes': classes,
                'methods': methods,
                'file_path': file_path,
                'language': 'java'
            }
        except Exception as e:
            print(f"⚠️ Error parsing Java file {file_path}: {e}")
            # Fallback to TreeSitter or basic parsing
            if self.multi_lang_parser and self.multi_lang_parser.is_language_supported('java'):
                return self._parse_with_treesitter(file_path, 'java')
            return self._parse_java_file_basic(file_path)
    
    def _parse_with_treesitter(self, file_path: str, language: str) -> Optional[Dict[str, Any]]:
        """
        Parse a file using TreeSitter parser.
        
        Args:
            file_path: Path to the file
            language: Programming language
            
        Returns:
            Dict with parsed information
        """
        if not self.multi_lang_parser:
            return None
        
        try:
            with open(file_path, 'r', encoding='utf-8', errors='ignore') as f:
                content = f.read()
            
            parsed = self.multi_lang_parser.parse(content, language, file_path)
            if not parsed:
                return None
            
            # Convert TreeSitter format to our internal format
            return self._convert_treesitter_to_internal(parsed, language)
        except Exception as e:
            print(f"⚠️ Error parsing {file_path} with TreeSitter: {e}")
            return None
    
    def _convert_treesitter_to_internal(
        self, 
        parsed: Dict[str, Any], 
        language: str
    ) -> Dict[str, Any]:
        """
        Convert TreeSitter parsed output to internal format.
        
        Args:
            parsed: TreeSitter parsed output
            language: Programming language
            
        Returns:
            Dict in internal format
        """
        # Extract package/module name (language-specific)
        package = ""
        if language == 'python':
            # Python uses module name from file path
            file_path = parsed.get('file_path', '')
            if file_path:
                package = Path(file_path).stem
        
        # Convert functions to methods format
        methods = []
        for func in parsed.get('functions', []):
            # Build FQN based on language
            func_name = func.get('name', '')
            if language == 'python':
                fqn = f"{package}.{func_name}" if package else func_name
            else:
                fqn = func_name
            
            methods.append({
                'name': func_name,
                'fqn': fqn,
                'return_type': 'unknown',  # TreeSitter doesn't always extract this
                'parameters': self._extract_parameters_from_signature(func.get('signature', '')),
                'annotations': [],
                'class_fqn': '',  # Will be set if inside a class
                'file_path': parsed.get('file_path', ''),
                'start_line': func.get('start_line', 1)
            })
        
        # Convert classes
        classes = []
        for cls in parsed.get('classes', []):
            class_name = cls.get('name', '')
            if language == 'python':
                fqn = f"{package}.{class_name}" if package else class_name
            else:
                fqn = class_name
            
            classes.append({
                'name': class_name,
                'fqn': fqn,
                'annotations': [],
                'extended_class': None,
                'implemented_interfaces': [],
                'file_path': parsed.get('file_path', ''),
                'start_line': cls.get('start_line', 1)
            })
        
        # Convert imports
        imports = []
        for imp in parsed.get('imports', []):
            module = imp.get('module', '')
            if module:
                imports.append(module)
        
        return {
            'package': package,
            'imports': imports,
            'classes': classes,
            'methods': methods,
            'file_path': parsed.get('file_path', ''),
            'language': language
        }
    
    def _extract_parameters_from_signature(self, signature: str) -> List[str]:
        """Extract parameter list from function signature."""
        if not signature:
            return []
        
        # Try to extract parameters from signature like "func(param1, param2)"
        match = re.search(r'\(([^)]*)\)', signature)
        if match:
            params_str = match.group(1)
            if params_str.strip():
                return [p.strip() for p in params_str.split(',')]
        return []
    
    def _parse_file_basic(self, file_path: str, language: str) -> Dict[str, Any]:
        """
        Basic file parsing using regex (fallback).
        
        Args:
            file_path: Path to the file
            language: Programming language
            
        Returns:
            Dict with basic parsed information
        """
        if language == 'java':
            return self._parse_java_file_basic(file_path)
        
        # Basic parsing for other languages
        try:
            with open(file_path, 'r', encoding='utf-8', errors='ignore') as f:
                content = f.read()
                lines = content.split('\n')
            
            # Extract imports (language-specific patterns)
            imports = []
            if language == 'python':
                imports = re.findall(r'^(?:import|from)\s+([\w.]+)', content, re.MULTILINE)
            elif language in ['javascript', 'typescript']:
                imports = re.findall(r'import\s+(?:.*?\s+from\s+)?["\']([^"\']+)["\']', content)
            elif language == 'go':
                imports = re.findall(r'import\s+["\']([^"\']+)["\']', content)
            elif language == 'rust':
                imports = re.findall(r'use\s+([\w:]+)', content)
            
            # Extract functions (basic)
            functions = []
            if language == 'python':
                func_pattern = r'def\s+(\w+)\s*\('
            elif language in ['javascript', 'typescript']:
                func_pattern = r'(?:function|const|let|var)\s+(\w+)\s*=?\s*\([^)]*\)'
            elif language == 'go':
                func_pattern = r'func\s+(\w+)\s*\('
            elif language == 'rust':
                func_pattern = r'fn\s+(\w+)\s*\('
            else:
                func_pattern = r'(\w+)\s*\('
            
            for match in re.finditer(func_pattern, content):
                func_name = match.group(1)
                start_line = content[:match.start()].count('\n') + 1
                functions.append({
                    'name': func_name,
                    'fqn': func_name,
                    'start_line': start_line
                })
            
            # Extract classes (basic)
            classes = []
            if language == 'python':
                class_pattern = r'class\s+(\w+)'
            elif language in ['javascript', 'typescript']:
                class_pattern = r'class\s+(\w+)'
            elif language == 'go':
                class_pattern = r'type\s+(\w+)\s+struct'
            elif language == 'rust':
                class_pattern = r'struct\s+(\w+)'
            else:
                class_pattern = r'class\s+(\w+)'
            
            for match in re.finditer(class_pattern, content):
                class_name = match.group(1)
                start_line = content[:match.start()].count('\n') + 1
                classes.append({
                    'name': class_name,
                    'fqn': class_name,
                    'start_line': start_line
                })
            
            return {
                'package': '',
                'imports': imports,
                'classes': classes,
                'methods': functions,
                'file_path': file_path,
                'language': language
            }
        except Exception as e:
            print(f"⚠️ Error in basic parsing {file_path}: {e}")
            return {
                'package': '',
                'imports': [],
                'classes': [],
                'methods': [],
                'file_path': file_path,
                'language': language
            }
    
    def _parse_java_file_basic(self, file_path: str) -> Dict[str, Any]:
        """
        Basic Java file parsing using regex (fallback when javalang unavailable).
        
        Args:
            file_path: Path to the Java file
        
        Returns:
            Dict with basic parsed information
        """
        try:
            with open(file_path, 'r', encoding='utf-8', errors='ignore') as f:
                content = f.read()
                lines = content.split('\n')
            
            # Extract package
            package_match = re.search(r'package\s+([\w.]+);', content)
            package = package_match.group(1) if package_match else ""
            
            # Extract imports
            imports = re.findall(r'import\s+([\w.*]+);', content)
            
            # Extract class declarations
            classes = []
            class_pattern = r'(?:public\s+)?(?:abstract\s+)?(?:final\s+)?class\s+(\w+)'
            for match in re.finditer(class_pattern, content):
                class_name = match.group(1)
                classes.append({
                    'name': class_name,
                    'fqn': f"{package}.{class_name}" if package else class_name,
                    'start_line': content[:match.start()].count('\n') + 1
                })
            
            # Extract method declarations (basic)
            methods = []
            method_pattern = r'(?:public|private|protected)?\s*(?:static)?\s*(?:[\w<>,\s]+)?\s+(\w+)\s*\([^)]*\)\s*\{'
            for match in re.finditer(method_pattern, content):
                method_name = match.group(1)
                if method_name not in ['if', 'for', 'while', 'switch', 'catch']:
                    methods.append({
                        'name': method_name,
                        'fqn': f"{package}.{method_name}" if package else method_name,
                        'start_line': content[:match.start()].count('\n') + 1
                    })
            
            return {
                'package': package,
                'imports': imports,
                'classes': classes,
                'methods': methods,
                'file_path': file_path
            }
        except Exception as e:
            print(f"⚠️ Error in basic parsing {file_path}: {e}")
            return {
                'package': '',
                'imports': [],
                'classes': [],
                'methods': [],
                'file_path': file_path
            }
    
    def _extract_class_info(
        self, 
        node, 
        package: str, 
        file_path: str
    ) -> Dict[str, Any]:
        """Extract class information from AST node."""
        class_name = node.name
        fqn = f"{package}.{class_name}" if package else class_name
        
        # Get annotations
        annotations = [ann.name for ann in node.annotations] if node.annotations else []
        
        # Get extended class
        extended = node.extends.name if node.extends else None
        
        # Get implemented interfaces
        interfaces = []
        if node.implements:
            interfaces = [impl.name for impl in node.implements]
        
        return {
            'name': class_name,
            'fqn': fqn,
            'annotations': annotations,
            'extended_class': extended,
            'implemented_interfaces': interfaces,
            'file_path': file_path
        }
    
    def _extract_method_info(
        self,
        node,
        class_fqn: str,
        file_path: str
    ) -> Dict[str, Any]:
        """Extract method information from AST node."""
        method_name = node.name
        fqn = f"{class_fqn}.{method_name}"
        
        # Get annotations
        annotations = [ann.name for ann in node.annotations] if node.annotations else []
        
        # Get return type
        return_type = str(node.return_type.name) if node.return_type else "void"
        
        # Get parameters
        parameters = []
        if node.parameters:
            for param in node.parameters:
                param_type = str(param.type.name) if param.type else "Object"
                parameters.append(f"{param_type} {param.name}")
        
        return {
            'name': method_name,
            'fqn': fqn,
            'return_type': return_type,
            'parameters': parameters,
            'annotations': annotations,
            'class_fqn': class_fqn,
            'file_path': file_path
        }
    
    def generate_chunks(
        self,
        parsed_data: Dict[str, Any],
        file_content: str,
        repository_id: int,
        language: Optional[str] = None
    ) -> List[Dict[str, Any]]:
        """
        Generate chunks at multiple levels from parsed code file.
        Supports multiple languages and configurable chunking strategies.
        
        Strategies:
        - method_only: Only method-level chunks (smallest, best for search)
        - class_metadata: Method chunks + class metadata (no full class body)
        - recursive: Method chunks + recursively split large classes/methods
        - sliding_window: Method chunks + overlapping windows for large classes
        - hybrid: Method chunks + class metadata + file chunks (small files only)
        
        Args:
            parsed_data: Parsed AST information
            file_content: Full file content
            repository_id: Repository ID
            language: Optional language hint
        
        Returns:
            List of chunk dictionaries ready for database storage
        """
        strategy = settings.java_chunking_strategy
        max_size = settings.java_max_chunk_size
        enforce_size = settings.java_enforce_chunk_size
        
        # Route to appropriate strategy
        if strategy == "method_only":
            return self._generate_chunks_method_only(parsed_data, file_content, repository_id, language, max_size, enforce_size)
        elif strategy == "class_metadata":
            return self._generate_chunks_class_metadata(parsed_data, file_content, repository_id, language, max_size, enforce_size)
        elif strategy == "recursive":
            return self._generate_chunks_recursive(parsed_data, file_content, repository_id, language, max_size, enforce_size)
        elif strategy == "sliding_window":
            return self._generate_chunks_sliding_window(parsed_data, file_content, repository_id, language, max_size, enforce_size)
        elif strategy == "hybrid":
            return self._generate_chunks_hybrid(parsed_data, file_content, repository_id, language, max_size, enforce_size)
        else:
            # Default to class_metadata if unknown strategy
            print(f"⚠️ Unknown chunking strategy '{strategy}', using 'class_metadata'")
            return self._generate_chunks_class_metadata(parsed_data, file_content, repository_id, language, max_size, enforce_size)
    
    def _find_method_end(self, lines: List[str], start_idx: int) -> int:
        """Find the end line of a method by matching braces."""
        brace_count = 0
        found_start = False
        
        for i in range(start_idx, len(lines)):
            line = lines[i]
            for char in line:
                if char == '{':
                    brace_count += 1
                    found_start = True
                elif char == '}':
                    brace_count -= 1
                    if found_start and brace_count == 0:
                        return i + 1
        
        return len(lines)
    
    def _find_class_end(self, lines: List[str], start_idx: int) -> int:
        """Find the end line of a class by matching braces."""
        return self._find_method_end(lines, start_idx)
    
    def _generate_method_summary(self, method_info: Dict[str, Any], code: str) -> str:
        """Generate a brief summary for a method."""
        name = method_info.get('name', 'method')
        return_type = method_info.get('return_type', 'void')
        params = method_info.get('parameters', [])
        
        summary = f"Method {name}("
        if params:
            summary += ", ".join(params[:3])  # Limit parameter display
            if len(params) > 3:
                summary += "..."
        summary += f") returns {return_type}"
        
        return summary
    
    def _generate_class_summary(self, class_info: Dict[str, Any], code: str) -> str:
        """Generate a brief summary for a class."""
        name = class_info.get('name', 'class')
        extended = class_info.get('extended_class')
        interfaces = class_info.get('implemented_interfaces', [])
        
        summary = f"Class {name}"
        if extended:
            summary += f" extends {extended}"
        if interfaces:
            summary += f" implements {', '.join(interfaces[:2])}"
        
        return summary
    
    def _generate_file_summary(self, parsed_data: Dict[str, Any], content: str) -> str:
        """Generate a brief summary for a file."""
        package = parsed_data.get('package', '')
        classes = parsed_data.get('classes', [])
        methods = parsed_data.get('methods', [])
        
        summary = f"Java file"
        if package:
            summary += f" in package {package}"
        if classes:
            summary += f" with {len(classes)} class(es)"
        if methods:
            summary += f" and {len(methods)} method(s)"
        
        return summary
    
    # ============================================================================
    # CHUNKING STRATEGY IMPLEMENTATIONS
    # ============================================================================
    
    def _generate_chunks_method_only(
        self,
        parsed_data: Dict[str, Any],
        file_content: str,
        repository_id: int,
        language: Optional[str],
        max_size: int,
        enforce_size: bool
    ) -> List[Dict[str, Any]]:
        """
        Strategy 1: Method-Only Chunking
        
        Only creates method-level chunks. Best for:
        - Precise search (smallest chunks)
        - Fast retrieval
        - Minimal storage
        
        Trade-off: No class-level context
        """
        chunks = []
        file_path = parsed_data['file_path']
        lines = file_content.split('\n')
        
        for method_info in parsed_data.get('methods', []):
            method_fqn = method_info.get('fqn', '')
            start_line = method_info.get('start_line', 1)
            end_line = self._find_method_end(lines, start_line - 1)
            method_code = '\n'.join(lines[start_line - 1:end_line])
            
            # Enforce size limit if enabled
            if enforce_size and len(method_code) > max_size:
                # Split large methods by logical blocks
                method_chunks = self._split_large_method(method_code, max_size, method_info, file_path, start_line)
                chunks.extend(method_chunks)
            else:
                chunk = self._create_method_chunk(method_info, method_code, file_path, start_line, end_line, parsed_data, repository_id)
                chunks.append(chunk)
        
        return chunks
    
    def _generate_chunks_class_metadata(
        self,
        parsed_data: Dict[str, Any],
        file_content: str,
        repository_id: int,
        language: Optional[str],
        max_size: int,
        enforce_size: bool
    ) -> List[Dict[str, Any]]:
        """
        Strategy 2: Class Metadata Chunking (RECOMMENDED)
        
        Creates method chunks + class metadata chunks (no full class body).
        Industry best practice used by GitHub Copilot, Sourcegraph.
        
        Benefits:
        - Method-level precision
        - Class-level context without huge chunks
        - Optimal balance of size and context
        """
        chunks = []
        file_path = parsed_data['file_path']
        lines = file_content.split('\n')
        
        # Generate method chunks (with size enforcement)
        for method_info in parsed_data.get('methods', []):
            method_fqn = method_info.get('fqn', '')
            start_line = method_info.get('start_line', 1)
            end_line = self._find_method_end(lines, start_line - 1)
            method_code = '\n'.join(lines[start_line - 1:end_line])
            
            if enforce_size and len(method_code) > max_size:
                method_chunks = self._split_large_method(method_code, max_size, method_info, file_path, start_line)
                chunks.extend(method_chunks)
            else:
                chunk = self._create_method_chunk(method_info, method_code, file_path, start_line, end_line, parsed_data, repository_id)
                chunks.append(chunk)
        
        # Generate class metadata chunks (NO full class body)
        for class_info in parsed_data.get('classes', []):
            class_fqn = class_info.get('fqn', '')
            start_line = class_info.get('start_line', 1)
            
            # Get all methods in this class
            class_methods = [
                m for m in parsed_data.get('methods', [])
                if m.get('class_fqn') == class_fqn
            ]
            
            # Create metadata-only chunk (no code body)
            class_metadata_code = self._generate_class_signature(class_info, lines, start_line)
            summary = self._generate_class_summary(class_info, "")
            
            chunk = {
                'type': ChunkType.CLASS,
                'fqn': class_fqn,
                'file_path': file_path,
                'start_line': start_line,
                'end_line': start_line,  # Just the signature line
                'code': class_metadata_code,  # Only signature, not full body
                'summary': summary,
                'imports': parsed_data.get('imports', []),
                'annotations': class_info.get('annotations', []),
                'implemented_interfaces': class_info.get('implemented_interfaces', []),
                'extended_class': class_info.get('extended_class'),
                'method_count': len(class_methods),
                'method_fqns': [m.get('fqn', '') for m in class_methods],  # References only
                'repository_id': repository_id,
                'last_modified': datetime.utcnow()
            }
            chunks.append(chunk)
        
        return chunks
    
    def _generate_chunks_recursive(
        self,
        parsed_data: Dict[str, Any],
        file_content: str,
        repository_id: int,
        language: Optional[str],
        max_size: int,
        enforce_size: bool
    ) -> List[Dict[str, Any]]:
        """
        Strategy 3: Recursive Chunking
        
        Recursively splits large classes/methods by logical blocks (if/else, try/catch, loops).
        Best for very large codebases where methods/classes exceed size limits.
        """
        chunks = []
        file_path = parsed_data['file_path']
        lines = file_content.split('\n')
        
        # Method chunks with recursive splitting
        for method_info in parsed_data.get('methods', []):
            method_fqn = method_info.get('fqn', '')
            start_line = method_info.get('start_line', 1)
            end_line = self._find_method_end(lines, start_line - 1)
            method_code = '\n'.join(lines[start_line - 1:end_line])
            
            if enforce_size and len(method_code) > max_size:
                # Recursively split by logical blocks
                method_chunks = self._recursive_split_code(
                    method_code, max_size, method_info, file_path, start_line, "method"
                )
                chunks.extend(method_chunks)
            else:
                chunk = self._create_method_chunk(method_info, method_code, file_path, start_line, end_line, parsed_data, repository_id)
                chunks.append(chunk)
        
        # Class chunks with recursive splitting
        for class_info in parsed_data.get('classes', []):
            class_fqn = class_info.get('fqn', '')
            start_line = class_info.get('start_line', 1)
            end_line = self._find_class_end(lines, start_line - 1)
            class_code = '\n'.join(lines[start_line - 1:end_line])
            
            if enforce_size and len(class_code) > max_size:
                # Recursively split class by methods/logical blocks
                class_chunks = self._recursive_split_code(
                    class_code, max_size, class_info, file_path, start_line, "class"
                )
                chunks.extend(class_chunks)
            else:
                # Small class - create metadata chunk
                class_methods = [
                    m for m in parsed_data.get('methods', [])
                    if m.get('class_fqn') == class_fqn
                ]
                summary = self._generate_class_summary(class_info, class_code)
                
                chunk = {
                    'type': ChunkType.CLASS,
                    'fqn': class_fqn,
                    'file_path': file_path,
                    'start_line': start_line,
                    'end_line': end_line,
                    'code': class_code,
                    'summary': summary,
                    'imports': parsed_data.get('imports', []),
                    'annotations': class_info.get('annotations', []),
                    'implemented_interfaces': class_info.get('implemented_interfaces', []),
                    'extended_class': class_info.get('extended_class'),
                    'repository_id': repository_id,
                    'last_modified': datetime.utcnow()
                }
                chunks.append(chunk)
        
        return chunks
    
    def _generate_chunks_sliding_window(
        self,
        parsed_data: Dict[str, Any],
        file_content: str,
        repository_id: int,
        language: Optional[str],
        max_size: int,
        enforce_size: bool
    ) -> List[Dict[str, Any]]:
        """
        Strategy 4: Sliding Window Chunking
        
        Creates overlapping windows for large classes to preserve context.
        Best for maintaining semantic coherence across boundaries.
        """
        chunks = []
        file_path = parsed_data['file_path']
        lines = file_content.split('\n')
        overlap_size = settings.java_chunk_overlap_size
        
        # Method chunks (standard)
        for method_info in parsed_data.get('methods', []):
            method_fqn = method_info.get('fqn', '')
            start_line = method_info.get('start_line', 1)
            end_line = self._find_method_end(lines, start_line - 1)
            method_code = '\n'.join(lines[start_line - 1:end_line])
            
            if enforce_size and len(method_code) > max_size:
                method_chunks = self._split_large_method(method_code, max_size, method_info, file_path, start_line)
                chunks.extend(method_chunks)
            else:
                chunk = self._create_method_chunk(method_info, method_code, file_path, start_line, end_line, parsed_data, repository_id)
                chunks.append(chunk)
        
        # Class chunks with sliding window
        for class_info in parsed_data.get('classes', []):
            class_fqn = class_info.get('fqn', '')
            start_line = class_info.get('start_line', 1)
            end_line = self._find_class_end(lines, start_line - 1)
            class_code = '\n'.join(lines[start_line - 1:end_line])
            
            if enforce_size and len(class_code) > max_size:
                # Create overlapping windows
                window_chunks = self._create_sliding_windows(
                    class_code, max_size, overlap_size, class_info, file_path, start_line
                )
                chunks.extend(window_chunks)
            else:
                # Small class - create metadata chunk
                class_methods = [
                    m for m in parsed_data.get('methods', [])
                    if m.get('class_fqn') == class_fqn
                ]
                summary = self._generate_class_summary(class_info, class_code)
                
                chunk = {
                    'type': ChunkType.CLASS,
                    'fqn': class_fqn,
                    'file_path': file_path,
                    'start_line': start_line,
                    'end_line': end_line,
                    'code': class_code,
                    'summary': summary,
                    'imports': parsed_data.get('imports', []),
                    'annotations': class_info.get('annotations', []),
                    'implemented_interfaces': class_info.get('implemented_interfaces', []),
                    'extended_class': class_info.get('extended_class'),
                    'repository_id': repository_id,
                    'last_modified': datetime.utcnow()
                }
                chunks.append(chunk)
        
        return chunks
    
    def _generate_chunks_hybrid(
        self,
        parsed_data: Dict[str, Any],
        file_content: str,
        repository_id: int,
        language: Optional[str],
        max_size: int,
        enforce_size: bool
    ) -> List[Dict[str, Any]]:
        """
        Strategy 5: Hybrid Chunking
        
        Combines method chunks + class metadata + file chunks (only for small files).
        Most comprehensive but uses more storage.
        """
        chunks = []
        file_path = parsed_data['file_path']
        lines = file_content.split('\n')
        
        # Method chunks
        for method_info in parsed_data.get('methods', []):
            method_fqn = method_info.get('fqn', '')
            start_line = method_info.get('start_line', 1)
            end_line = self._find_method_end(lines, start_line - 1)
            method_code = '\n'.join(lines[start_line - 1:end_line])
            
            if enforce_size and len(method_code) > max_size:
                method_chunks = self._split_large_method(method_code, max_size, method_info, file_path, start_line)
                chunks.extend(method_chunks)
            else:
                chunk = self._create_method_chunk(method_info, method_code, file_path, start_line, end_line, parsed_data, repository_id)
                chunks.append(chunk)
        
        # Class metadata chunks (no full body)
        for class_info in parsed_data.get('classes', []):
            class_fqn = class_info.get('fqn', '')
            start_line = class_info.get('start_line', 1)
            
            class_methods = [
                m for m in parsed_data.get('methods', [])
                if m.get('class_fqn') == class_fqn
            ]
            
            class_metadata_code = self._generate_class_signature(class_info, lines, start_line)
            summary = self._generate_class_summary(class_info, "")
            
            chunk = {
                'type': ChunkType.CLASS,
                'fqn': class_fqn,
                'file_path': file_path,
                'start_line': start_line,
                'end_line': start_line,
                'code': class_metadata_code,
                'summary': summary,
                'imports': parsed_data.get('imports', []),
                'annotations': class_info.get('annotations', []),
                'implemented_interfaces': class_info.get('implemented_interfaces', []),
                'extended_class': class_info.get('extended_class'),
                'method_count': len(class_methods),
                'method_fqns': [m.get('fqn', '') for m in class_methods],
                'repository_id': repository_id,
                'last_modified': datetime.utcnow()
            }
            chunks.append(chunk)
        
        # File chunk - only for small files
        if len(file_content) <= max_size:
            file_summary = self._generate_file_summary(parsed_data, file_content)
            chunk = {
                'type': ChunkType.FILE,
                'fqn': file_path,
                'file_path': file_path,
                'start_line': 1,
                'end_line': len(lines),
                'code': file_content,
                'summary': file_summary,
                'imports': parsed_data.get('imports', []),
                'repository_id': repository_id,
                'last_modified': datetime.utcnow()
            }
            chunks.append(chunk)
        
        return chunks
    
    # ============================================================================
    # HELPER METHODS FOR CHUNKING STRATEGIES
    # ============================================================================
    
    def _create_method_chunk(
        self,
        method_info: Dict[str, Any],
        method_code: str,
        file_path: str,
        start_line: int,
        end_line: int,
        parsed_data: Dict[str, Any],
        repository_id: int
    ) -> Dict[str, Any]:
        """Create a method chunk with standard fields."""
        method_fqn = method_info.get('fqn', '')
        summary = self._generate_method_summary(method_info, method_code)
        
        return {
            'type': ChunkType.METHOD,
            'fqn': method_fqn,
            'file_path': file_path,
            'start_line': start_line,
            'end_line': end_line,
            'code': method_code,
            'summary': summary,
            'imports': parsed_data.get('imports', []),
            'annotations': method_info.get('annotations', []),
            'callers': [],
            'callees': [],
            'repository_id': repository_id,
            'last_modified': datetime.utcnow()
        }
    
    def _generate_class_signature(self, class_info: Dict[str, Any], lines: List[str], start_line: int) -> str:
        """Extract only the class signature line (declaration), not the full body."""
        if start_line <= len(lines):
            # Get the class declaration line (usually first line of class)
            signature_line = lines[start_line - 1]
            # Try to get a few more lines if it's a multi-line declaration
            if '{' not in signature_line and start_line < len(lines):
                # Multi-line declaration, get up to opening brace
                sig_lines = [signature_line]
                for i in range(start_line, min(start_line + 5, len(lines))):
                    sig_lines.append(lines[i])
                    if '{' in lines[i]:
                        break
                return '\n'.join(sig_lines)
            return signature_line
        return ""
    
    def _split_large_method(
        self,
        method_code: str,
        max_size: int,
        method_info: Dict[str, Any],
        file_path: str,
        start_line: int
    ) -> List[Dict[str, Any]]:
        """Split a large method into smaller chunks by logical blocks."""
        chunks = []
        lines = method_code.split('\n')
        
        # Try to split by logical blocks (if/else, try/catch, loops)
        blocks = self._extract_logical_blocks(method_code)
        
        if len(blocks) > 1:
            # Split by blocks
            current_chunk_lines = []
            current_start = start_line
            chunk_idx = 0
            
            for block_lines in blocks:
                block_code = '\n'.join(block_lines)
                
                if len('\n'.join(current_chunk_lines + block_lines)) > max_size and current_chunk_lines:
                    # Current chunk is full, save it
                    chunk_code = '\n'.join(current_chunk_lines)
                    chunk_end = current_start + len(current_chunk_lines) - 1
                    
                    chunk = {
                        'type': ChunkType.METHOD,
                        'fqn': f"{method_info.get('fqn', '')}_part{chunk_idx}",
                        'file_path': file_path,
                        'start_line': current_start,
                        'end_line': chunk_end,
                        'code': chunk_code,
                        'summary': f"{self._generate_method_summary(method_info, chunk_code)} (part {chunk_idx + 1})",
                        'imports': [],
                        'annotations': method_info.get('annotations', []),
                        'callers': [],
                        'callees': [],
                        'repository_id': method_info.get('repository_id', 0),
                        'last_modified': datetime.utcnow()
                    }
                    chunks.append(chunk)
                    
                    current_chunk_lines = block_lines
                    current_start = chunk_end + 1
                    chunk_idx += 1
                else:
                    current_chunk_lines.extend(block_lines)
            
            # Add remaining chunk
            if current_chunk_lines:
                chunk_code = '\n'.join(current_chunk_lines)
                chunk_end = current_start + len(current_chunk_lines) - 1
                chunk = {
                    'type': ChunkType.METHOD,
                    'fqn': f"{method_info.get('fqn', '')}_part{chunk_idx}",
                    'file_path': file_path,
                    'start_line': current_start,
                    'end_line': chunk_end,
                    'code': chunk_code,
                    'summary': f"{self._generate_method_summary(method_info, chunk_code)} (part {chunk_idx + 1})",
                    'imports': [],
                    'annotations': method_info.get('annotations', []),
                    'callers': [],
                    'callees': [],
                    'repository_id': method_info.get('repository_id', 0),
                    'last_modified': datetime.utcnow()
                }
                chunks.append(chunk)
        else:
            # Can't split by blocks, split by line count
            lines_per_chunk = max_size // 50  # Rough estimate: ~50 chars per line
            for i in range(0, len(lines), lines_per_chunk):
                chunk_lines = lines[i:i + lines_per_chunk]
                chunk_code = '\n'.join(chunk_lines)
                chunk_start = start_line + i
                chunk_end = start_line + i + len(chunk_lines) - 1
                
                chunk = {
                    'type': ChunkType.METHOD,
                    'fqn': f"{method_info.get('fqn', '')}_part{i // lines_per_chunk}",
                    'file_path': file_path,
                    'start_line': chunk_start,
                    'end_line': chunk_end,
                    'code': chunk_code,
                    'summary': f"{self._generate_method_summary(method_info, chunk_code)} (part {i // lines_per_chunk + 1})",
                    'imports': [],
                    'annotations': method_info.get('annotations', []),
                    'callers': [],
                    'callees': [],
                    'repository_id': method_info.get('repository_id', 0),
                    'last_modified': datetime.utcnow()
                }
                chunks.append(chunk)
        
        return chunks
    
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
            
            # Detect block boundaries
            if any(keyword in stripped for keyword in ['if (', 'else', 'try {', 'catch', 'for (', 'while (', 'switch']):
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
    
    def _recursive_split_code(
        self,
        code: str,
        max_size: int,
        entity_info: Dict[str, Any],
        file_path: str,
        start_line: int,
        entity_type: str
    ) -> List[Dict[str, Any]]:
        """Recursively split code by trying different strategies."""
        if len(code) <= max_size:
            # Base case: code fits
            return [{
                'type': ChunkType.METHOD if entity_type == "method" else ChunkType.CLASS,
                'fqn': entity_info.get('fqn', ''),
                'file_path': file_path,
                'start_line': start_line,
                'end_line': start_line + code.count('\n'),
                'code': code,
                'summary': entity_info.get('summary', ''),
                'repository_id': entity_info.get('repository_id', 0),
                'last_modified': datetime.utcnow()
            }]
        
        # Try splitting by logical blocks first
        blocks = self._extract_logical_blocks(code)
        if len(blocks) > 1:
            chunks = []
            current_start = start_line
            for block in blocks:
                block_code = '\n'.join(block)
                sub_chunks = self._recursive_split_code(
                    block_code, max_size, entity_info, file_path, current_start, entity_type
                )
                chunks.extend(sub_chunks)
                current_start += len(block)
            return chunks
        
        # Fallback: split by lines
        lines = code.split('\n')
        lines_per_chunk = max_size // 50
        chunks = []
        for i in range(0, len(lines), lines_per_chunk):
            chunk_lines = lines[i:i + lines_per_chunk]
            chunk_code = '\n'.join(chunk_lines)
            chunk_start = start_line + i
            chunk_end = start_line + i + len(chunk_lines) - 1
            
            chunks.append({
                'type': ChunkType.METHOD if entity_type == "method" else ChunkType.CLASS,
                'fqn': f"{entity_info.get('fqn', '')}_part{i // lines_per_chunk}",
                'file_path': file_path,
                'start_line': chunk_start,
                'end_line': chunk_end,
                'code': chunk_code,
                'summary': f"{entity_info.get('summary', '')} (part {i // lines_per_chunk + 1})",
                'repository_id': entity_info.get('repository_id', 0),
                'last_modified': datetime.utcnow()
            })
        
        return chunks
    
    def _create_sliding_windows(
        self,
        code: str,
        max_size: int,
        overlap_size: int,
        entity_info: Dict[str, Any],
        file_path: str,
        start_line: int
    ) -> List[Dict[str, Any]]:
        """Create overlapping windows for large code blocks."""
        chunks = []
        lines = code.split('\n')
        window_size = max_size // 50  # Approximate lines per window
        overlap_lines = overlap_size // 50
        
        for i in range(0, len(lines), window_size - overlap_lines):
            window_lines = lines[i:min(i + window_size, len(lines))]
            window_code = '\n'.join(window_lines)
            window_start = start_line + i
            window_end = start_line + i + len(window_lines) - 1
            
            chunks.append({
                'type': ChunkType.CLASS,
                'fqn': f"{entity_info.get('fqn', '')}_window{i // (window_size - overlap_lines)}",
                'file_path': file_path,
                'start_line': window_start,
                'end_line': window_end,
                'code': window_code,
                'summary': f"{entity_info.get('summary', '')} (window {i // (window_size - overlap_lines) + 1})",
                'repository_id': entity_info.get('repository_id', 0),
                'last_modified': datetime.utcnow()
            })
        
        return chunks
    
    async def generate_embeddings(self, texts: List[str]) -> List[List[float]]:
        """
        Generate embeddings for a list of texts using OpenAI API.
        
        Args:
            texts: List of text strings to embed
        
        Returns:
            List of embedding vectors
        """
        if not self.embedding_client:
            print("⚠️ OpenAI client not available for embeddings")
            return []
        
        try:
            # Batch embeddings
            batch_size = 100
            all_embeddings = []
            
            for i in range(0, len(texts), batch_size):
                batch = texts[i:i + batch_size]
                response = await self.embedding_client.embeddings.create(
                    model=settings.java_embedding_model,
                    input=batch
                )
                batch_embeddings = [item.embedding for item in response.data]
                all_embeddings.extend(batch_embeddings)
            
            return all_embeddings
        except Exception as e:
            print(f"❌ Error generating embeddings: {e}")
            return []
    
    def build_call_graph(self, chunks: List[Dict[str, Any]]) -> Dict[str, Set[str]]:
        """
        Build call graph from chunks.
        
        Args:
            chunks: List of chunk dictionaries
        
        Returns:
            Dict mapping method FQN to set of callee FQNs
        """
        call_graph = {}
        
        for chunk in chunks:
            if chunk['type'] != ChunkType.METHOD:
                continue
            
            method_fqn = chunk['fqn']
            code = chunk['code']
            
            # Find method calls in code (basic pattern matching)
            # Look for patterns like: methodName( or object.methodName(
            callees = set()
            
            # Simple regex to find method calls
            method_call_pattern = r'(\w+)\s*\('
            matches = re.finditer(method_call_pattern, code)
            
            for match in matches:
                method_name = match.group(1)
                # Try to find this method in other chunks
                for other_chunk in chunks:
                    if (other_chunk['type'] == ChunkType.METHOD and
                        other_chunk['fqn'].endswith(f".{method_name}")):
                        callees.add(other_chunk['fqn'])
            
            call_graph[method_fqn] = callees
        
        self.call_graph = call_graph
        return call_graph
    
    def update_chunk_callers_callees(self, chunks: List[Dict[str, Any]]):
        """Update callers and callees in chunks based on call graph."""
        # Build reverse call graph (callers)
        callers_map = {}
        for caller, callees in self.call_graph.items():
            for callee in callees:
                if callee not in callers_map:
                    callers_map[callee] = set()
                callers_map[callee].add(caller)
        
        # Update chunks
        for chunk in chunks:
            if chunk['type'] == ChunkType.METHOD:
                method_fqn = chunk['fqn']
                chunk['callees'] = list(self.call_graph.get(method_fqn, set()))
                chunk['callers'] = list(callers_map.get(method_fqn, set()))


# Global instance
java_indexer_service = JavaIndexerService()

