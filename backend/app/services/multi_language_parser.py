"""
Multi-Language Code Parser Service using TreeSitter.

This service provides code parsing capabilities for multiple programming languages
using TreeSitter parsers. Supports Python, JavaScript/TypeScript, Java, Go, and Rust.
"""

from typing import List, Dict, Any, Optional
import logging

logger = logging.getLogger(__name__)

# Try to import TreeSitter and language modules
try:
    from tree_sitter import Language, Parser
    TREE_SITTER_AVAILABLE = True
except ImportError:
    TREE_SITTER_AVAILABLE = False
    logger.warning("tree-sitter not installed. Install with: pip install tree-sitter")

# Language module imports with fallback
LANGUAGE_MODULES = {}
SUPPORTED_LANGUAGES = []

if TREE_SITTER_AVAILABLE:
    try:
        import tree_sitter_python as tspython
        LANGUAGE_MODULES["python"] = tspython
        SUPPORTED_LANGUAGES.append("python")
    except ImportError:
        logger.warning("tree-sitter-python not installed")

    try:
        import tree_sitter_javascript as tsjavascript
        LANGUAGE_MODULES["javascript"] = tsjavascript
        LANGUAGE_MODULES["typescript"] = tsjavascript  # TypeScript uses JavaScript parser
        SUPPORTED_LANGUAGES.extend(["javascript", "typescript"])
    except ImportError:
        logger.warning("tree-sitter-javascript not installed")

    try:
        import tree_sitter_java as tsjava
        LANGUAGE_MODULES["java"] = tsjava
        SUPPORTED_LANGUAGES.append("java")
    except ImportError:
        logger.warning("tree-sitter-java not installed")

    try:
        import tree_sitter_go as tsgo
        LANGUAGE_MODULES["go"] = tsgo
        SUPPORTED_LANGUAGES.append("go")
    except ImportError:
        logger.warning("tree-sitter-go not installed")

    try:
        import tree_sitter_rust as tsrust
        LANGUAGE_MODULES["rust"] = tsrust
        SUPPORTED_LANGUAGES.append("rust")
    except ImportError:
        logger.warning("tree-sitter-rust not installed")


class MultiLanguageParser:
    """
    Multi-language code parser using TreeSitter.
    
    Provides AST parsing, function/class extraction, and import analysis
    for multiple programming languages.
    """
    
    def __init__(self):
        """Initialize parser with language support."""
        self.parsers = {}
        if TREE_SITTER_AVAILABLE:
            self._init_parsers()
        else:
            logger.warning("TreeSitter not available. Multi-language parsing disabled.")
    
    def _init_parsers(self):
        """Initialize parsers for all supported languages."""
        for lang, module in LANGUAGE_MODULES.items():
            try:
                language = Language(module.language())
                parser = Parser()
                parser.set_language(language)
                self.parsers[lang] = parser
                logger.info(f"✅ Initialized TreeSitter parser for {lang}")
            except Exception as e:
                logger.warning(f"⚠️ Failed to initialize parser for {lang}: {e}")
    
    def is_language_supported(self, language: str) -> bool:
        """
        Check if a language is supported.
        
        Args:
            language: Programming language name
            
        Returns:
            True if language is supported, False otherwise
        """
        return language.lower() in self.parsers
    
    def get_supported_languages(self) -> List[str]:
        """
        Get list of supported languages.
        
        Returns:
            List of supported language names
        """
        return list(self.parsers.keys())
    
    def parse(
        self, 
        code: str, 
        language: str,
        file_path: Optional[str] = None
    ) -> Optional[Dict[str, Any]]:
        """
        Parse code and extract structure.
        
        Args:
            code: Source code to parse
            language: Programming language (python, javascript, typescript, java, go, rust)
            file_path: Optional file path for context
            
        Returns:
            Dictionary with parsed structure or None if parsing fails
        """
        language = language.lower()
        
        if language not in self.parsers:
            logger.warning(f"Unsupported language: {language}. Supported: {list(self.parsers.keys())}")
            return None
        
        parser = self.parsers[language]
        
        try:
            tree = parser.parse(bytes(code, "utf8"))
            root_node = tree.root_node
            
            return {
                "ast": self._extract_structure(root_node, code),
                "functions": self._extract_functions(root_node, code, language),
                "classes": self._extract_classes(root_node, code, language),
                "imports": self._extract_imports(root_node, code, language),
                "language": language,
                "file_path": file_path,
            }
        except Exception as e:
            logger.error(f"Failed to parse code ({language}): {e}")
            return None
    
    def _extract_structure(self, node, code: str) -> Dict[str, Any]:
        """Extract basic AST structure."""
        return {
            "type": node.type,
            "start_byte": node.start_byte,
            "end_byte": node.end_byte,
            "start_point": node.start_point,
            "end_point": node.end_point,
            "children": [self._extract_structure(child, code) for child in node.children],
        }
    
    def _extract_functions(self, node, code: str, language: str) -> List[Dict[str, Any]]:
        """Extract function definitions."""
        functions = []
        
        # Language-specific function node types
        function_types = {
            "python": ["function_definition"],
            "javascript": ["function_declaration", "function_expression", "arrow_function"],
            "typescript": ["function_declaration", "function_expression", "arrow_function"],
            "java": ["method_declaration"],
            "go": ["function_declaration", "method_declaration"],
            "rust": ["function_item"],
        }
        
        node_types = function_types.get(language, ["function_definition"])
        
        def traverse(n):
            if n.type in node_types:
                func_name = self._get_function_name(n, code, language)
                func_code = code[n.start_byte:n.end_byte]
                functions.append({
                    "name": func_name,
                    "start_line": n.start_point[0] + 1,
                    "end_line": n.end_point[0] + 1,
                    "code": func_code,
                    "signature": self._extract_signature(n, code, language),
                    "docstring": self._extract_docstring(n, code, language),
                })
            
            for child in n.children:
                traverse(child)
        
        traverse(node)
        return functions
    
    def _extract_classes(self, node, code: str, language: str) -> List[Dict[str, Any]]:
        """Extract class definitions."""
        classes = []
        
        # Language-specific class node types
        class_types = {
            "python": ["class_definition"],
            "javascript": ["class_declaration"],
            "typescript": ["class_declaration"],
            "java": ["class_declaration"],
            "go": ["type_declaration"],  # Go uses type declarations
            "rust": ["struct_item", "impl_item"],
        }
        
        node_types = class_types.get(language, ["class_definition"])
        
        def traverse(n):
            if n.type in node_types:
                class_name = self._get_class_name(n, code, language)
                class_code = code[n.start_byte:n.end_byte]
                classes.append({
                    "name": class_name,
                    "start_line": n.start_point[0] + 1,
                    "end_line": n.end_point[0] + 1,
                    "code": class_code,
                    "docstring": self._extract_docstring(n, code, language),
                })
            
            for child in n.children:
                traverse(child)
        
        traverse(node)
        return classes
    
    def _extract_imports(self, node, code: str, language: str) -> List[Dict[str, Any]]:
        """Extract import statements."""
        imports = []
        
        # Language-specific import node types
        import_types = {
            "python": ["import_statement", "import_from_statement"],
            "javascript": ["import_statement"],
            "typescript": ["import_statement"],
            "java": ["import_declaration"],
            "go": ["import_declaration"],
            "rust": ["use_declaration"],
        }
        
        node_types = import_types.get(language, ["import_statement"])
        
        def traverse(n):
            if n.type in node_types:
                import_text = code[n.start_byte:n.end_byte]
                module_name = self._extract_module_name(n, code, language)
                imports.append({
                    "text": import_text,
                    "line": n.start_point[0] + 1,
                    "module": module_name,
                })
            
            for child in n.children:
                traverse(child)
        
        traverse(node)
        return imports
    
    def _get_function_name(self, node, code: str, language: str) -> str:
        """Extract function name from node."""
        # Common patterns for function names
        for child in node.children:
            if child.type in ["identifier", "property_identifier"]:
                return code[child.start_byte:child.end_byte]
            elif child.type == "function":
                return self._get_function_name(child, code, language)
        return "anonymous"
    
    def _get_class_name(self, node, code: str, language: str) -> str:
        """Extract class name from node."""
        for child in node.children:
            if child.type in ["identifier", "type_identifier"]:
                return code[child.start_byte:child.end_byte]
        return "Unknown"
    
    def _extract_signature(self, node, code: str, language: str) -> str:
        """Extract function signature."""
        # Try to find parameter list
        for child in node.children:
            if child.type in ["parameters", "formal_parameters"]:
                func_name = self._get_function_name(node, code, language)
                params = code[child.start_byte:child.end_byte]
                return f"{func_name}({params})"
        return ""
    
    def _extract_docstring(self, node, code: str, language: str) -> str:
        """Extract docstring/comment."""
        # Look for docstring nodes (language-specific)
        docstring_types = {
            "python": ["expression_statement"],
            "javascript": ["comment"],
            "typescript": ["comment"],
            "java": ["block_comment", "line_comment"],
            "go": ["comment"],
            "rust": ["line_comment", "block_comment"],
        }
        
        # For Python, look for string literals at the start
        if language == "python":
            for child in node.children:
                if child.type == "expression_statement":
                    expr = child.children[0] if child.children else None
                    if expr and expr.type == "string":
                        return code[expr.start_byte:expr.end_byte].strip('"\'')
        
        return ""
    
    def _extract_module_name(self, node, code: str, language: str) -> str:
        """Extract module name from import."""
        # Simplified extraction
        import_text = code[node.start_byte:node.end_byte]
        # Remove import keywords and extract module name
        for keyword in ["import", "from", "use", "package"]:
            import_text = import_text.replace(keyword, "").strip()
        return import_text.split()[0] if import_text.split() else ""


# Global parser instance
_parser: Optional[MultiLanguageParser] = None


def get_multi_language_parser() -> MultiLanguageParser:
    """
    Get or create multi-language parser instance.
    
    Returns:
        MultiLanguageParser instance
    """
    global _parser
    if _parser is None:
        _parser = MultiLanguageParser()
    return _parser

