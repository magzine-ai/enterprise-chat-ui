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
        Supports multiple languages with unified chunking strategy.
        
        Args:
            parsed_data: Parsed AST information
            file_content: Full file content
            repository_id: Repository ID
            language: Optional language hint
        
        Returns:
            List of chunk dictionaries ready for database storage
        """
        chunks = []
        file_path = parsed_data['file_path']
        language = language or parsed_data.get('language', 'java')
        lines = file_content.split('\n')
        
        # Generate method-level chunks
        for method_info in parsed_data.get('methods', []):
            method_fqn = method_info.get('fqn', '')
            start_line = method_info.get('start_line', 1)
            
            # Find method end (basic - look for matching braces)
            end_line = self._find_method_end(lines, start_line - 1)
            
            method_code = '\n'.join(lines[start_line - 1:end_line])
            
            # Generate summary
            summary = self._generate_method_summary(method_info, method_code)
            
            chunk = {
                'type': ChunkType.METHOD,
                'fqn': method_fqn,
                'file_path': file_path,
                'start_line': start_line,
                'end_line': end_line,
                'code': method_code,
                'summary': summary,
                'imports': parsed_data.get('imports', []),
                'annotations': method_info.get('annotations', []),
                'callers': [],  # Will be populated during call graph building
                'callees': [],  # Will be populated during call graph building
                'repository_id': repository_id,
                'last_modified': datetime.utcnow()
            }
            chunks.append(chunk)
        
        # Generate class-level chunks
        for class_info in parsed_data.get('classes', []):
            class_fqn = class_info.get('fqn', '')
            start_line = class_info.get('start_line', 1)
            
            # Find class end
            end_line = self._find_class_end(lines, start_line - 1)
            
            class_code = '\n'.join(lines[start_line - 1:end_line])
            summary = self._generate_class_summary(class_info, class_code)
            
            # Get all methods in this class
            class_methods = [
                m for m in parsed_data.get('methods', [])
                if m.get('class_fqn') == class_fqn
            ]
            
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
        
        # Generate file-level chunk
        if chunks:
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

