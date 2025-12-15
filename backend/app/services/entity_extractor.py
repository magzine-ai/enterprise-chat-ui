"""
Entity Extraction Service for extracting code entities across multiple languages.

Extracts functions, classes, REST endpoints, URLs, and other entities from code
for use in search, RAG, and graph building.
"""

from typing import List, Dict, Any, Optional, Set
import re
import logging

logger = logging.getLogger(__name__)


class EntityExtractor:
    """
    Service for extracting entities from code.
    
    Supports extraction of:
    - Functions/methods
    - Classes
    - REST endpoints
    - URLs
    - Imports/modules
    - API endpoints
    """
    
    def __init__(self):
        """Initialize entity extractor."""
        # REST endpoint patterns for different frameworks
        self.rest_patterns = [
            # FastAPI/Flask
            r'@router\.(get|post|put|delete|patch|head|options)\("([^"]+)"',
            r'@app\.(get|post|put|delete|patch|head|options)\("([^"]+)"',
            r'@route\("([^"]+)"',
            r'@.*\.route\("([^"]+)"',
            # Spring Boot (Java)
            r'@(?:GetMapping|PostMapping|PutMapping|DeleteMapping|PatchMapping|RequestMapping)\s*\([^)]*["\']([^"\']+)["\']',
            r'@RequestMapping\s*\([^)]*value\s*=\s*["\']([^"\']+)["\']',
            # Express.js (Node.js)
            r'\.(get|post|put|delete|patch)\s*\(["\']([^"\']+)["\']',
            r'app\.(get|post|put|delete|patch)\s*\(["\']([^"\']+)["\']',
            # Go (Gin, Echo, etc.)
            r'\.(GET|POST|PUT|DELETE|PATCH)\s*\(["\']([^"\']+)["\']',
            r'router\.(GET|POST|PUT|DELETE|PATCH)\s*\(["\']([^"\']+)["\']',
        ]
        
        # URL patterns
        self.url_patterns = [
            r'https?://[^\s"\'<>]+',
            r'["\']([^"\']*api[^"\']*\.com[^"\']*)["\']',
            r'base[_\s]*url["\']?\s*[:=]\s*["\']([^"\']+)["\']',
            r'endpoint["\']?\s*[:=]\s*["\']([^"\']+)["\']',
        ]
    
    def extract_entities(
        self,
        code: str,
        language: str,
        file_path: Optional[str] = None
    ) -> Dict[str, List[Any]]:
        """
        Extract all entities from code.
        
        Args:
            code: Source code
            language: Programming language
            file_path: Optional file path for context
        
        Returns:
            Dict with extracted entities
        """
        return {
            'functions': self.extract_functions(code, language),
            'classes': self.extract_classes(code, language),
            'rest_endpoints': self.extract_rest_endpoints(code, language),
            'urls': self.extract_urls(code),
            'imports': self.extract_imports(code, language),
        }
    
    def extract_functions(self, code: str, language: str) -> List[Dict[str, Any]]:
        """
        Extract function/method names from code.
        
        Args:
            code: Source code
            language: Programming language
        
        Returns:
            List of function dictionaries
        """
        functions = []
        
        # Language-specific function patterns
        patterns = {
            'python': [
                r'def\s+(\w+)\s*\(',
                r'async\s+def\s+(\w+)\s*\(',
            ],
            'javascript': [
                r'function\s+(\w+)\s*\(',
                r'const\s+(\w+)\s*=\s*\([^)]*\)\s*=>',
                r'(\w+)\s*:\s*function\s*\(',
                r'(\w+)\s*:\s*\([^)]*\)\s*=>',
            ],
            'typescript': [
                r'function\s+(\w+)\s*\(',
                r'const\s+(\w+)\s*[:=]\s*\([^)]*\)\s*[:=]',
                r'(\w+)\s*:\s*\([^)]*\)\s*[:=]',
                r'async\s+function\s+(\w+)\s*\(',
            ],
            'java': [
                r'(?:public|private|protected|static)\s+(?:[\w<>,\s]+)?\s+(\w+)\s*\([^)]*\)\s*\{',
                r'@\w+\s+(?:public|private|protected)?\s*(?:[\w<>,\s]+)?\s+(\w+)\s*\(',
            ],
            'go': [
                r'func\s+(?:\([^)]+\)\s+)?(\w+)\s*\(',
            ],
            'rust': [
                r'fn\s+(\w+)\s*\(',
            ],
        }
        
        func_patterns = patterns.get(language.lower(), [r'(\w+)\s*\('])
        
        for pattern in func_patterns:
            for match in re.finditer(pattern, code):
                func_name = match.group(1)
                # Filter out common keywords
                if func_name not in ['if', 'for', 'while', 'switch', 'catch', 'with', 'async']:
                    start_pos = match.start()
                    line_num = code[:start_pos].count('\n') + 1
                    functions.append({
                        'name': func_name,
                        'line': line_num,
                        'signature': self._extract_function_signature(code, match, language)
                    })
        
        # Deduplicate
        seen = set()
        unique_functions = []
        for func in functions:
            key = (func['name'], func['line'])
            if key not in seen:
                seen.add(key)
                unique_functions.append(func)
        
        return unique_functions
    
    def extract_classes(self, code: str, language: str) -> List[Dict[str, Any]]:
        """
        Extract class names from code.
        
        Args:
            code: Source code
            language: Programming language
        
        Returns:
            List of class dictionaries
        """
        classes = []
        
        # Language-specific class patterns
        patterns = {
            'python': [
                r'class\s+(\w+)(?:\s*\([^)]+\))?\s*:',
            ],
            'javascript': [
                r'class\s+(\w+)',
            ],
            'typescript': [
                r'class\s+(\w+)',
                r'interface\s+(\w+)',
            ],
            'java': [
                r'(?:public|private|protected|abstract|final)?\s*class\s+(\w+)',
                r'interface\s+(\w+)',
            ],
            'go': [
                r'type\s+(\w+)\s+struct',
                r'type\s+(\w+)\s+interface',
            ],
            'rust': [
                r'struct\s+(\w+)',
                r'impl\s+(\w+)',
                r'trait\s+(\w+)',
            ],
        }
        
        class_patterns = patterns.get(language.lower(), [r'class\s+(\w+)'])
        
        for pattern in class_patterns:
            for match in re.finditer(pattern, code):
                class_name = match.group(1)
                start_pos = match.start()
                line_num = code[:start_pos].count('\n') + 1
                classes.append({
                    'name': class_name,
                    'line': line_num,
                })
        
        # Deduplicate
        seen = set()
        unique_classes = []
        for cls in classes:
            key = (cls['name'], cls['line'])
            if key not in seen:
                seen.add(key)
                unique_classes.append(cls)
        
        return unique_classes
    
    def extract_rest_endpoints(self, code: str, language: str) -> List[Dict[str, Any]]:
        """
        Extract REST API endpoints from code.
        
        Args:
            code: Source code
            language: Programming language
        
        Returns:
            List of REST endpoint dictionaries
        """
        endpoints = []
        
        for pattern in self.rest_patterns:
            for match in re.finditer(pattern, code, re.IGNORECASE):
                if len(match.groups()) >= 2:
                    method = match.group(1).upper()
                    path = match.group(2)
                elif len(match.groups()) == 1:
                    method = "GET"  # Default
                    path = match.group(1)
                else:
                    continue
                
                start_pos = match.start()
                line_num = code[:start_pos].count('\n') + 1
                
                endpoints.append({
                    'method': method,
                    'path': path,
                    'endpoint': f"{method} {path}",
                    'line': line_num,
                })
        
        # Deduplicate
        seen = set()
        unique_endpoints = []
        for endpoint in endpoints:
            key = endpoint['endpoint']
            if key not in seen:
                seen.add(key)
                unique_endpoints.append(endpoint)
        
        return unique_endpoints
    
    def extract_urls(self, code: str) -> List[Dict[str, Any]]:
        """
        Extract URLs from code.
        
        Args:
            code: Source code
        
        Returns:
            List of URL dictionaries
        """
        urls = []
        
        for pattern in self.url_patterns:
            for match in re.finditer(pattern, code, re.IGNORECASE):
                if match.groups():
                    url = match.group(1) if match.group(1) else match.group(0)
                else:
                    url = match.group(0)
                
                start_pos = match.start()
                line_num = code[:start_pos].count('\n') + 1
                
                urls.append({
                    'url': url,
                    'line': line_num,
                })
        
        # Deduplicate
        seen = set()
        unique_urls = []
        for url_info in urls:
            if url_info['url'] not in seen:
                seen.add(url_info['url'])
                unique_urls.append(url_info)
        
        return unique_urls
    
    def extract_imports(self, code: str, language: str) -> List[Dict[str, Any]]:
        """
        Extract import/module statements from code.
        
        Args:
            code: Source code
            language: Programming language
        
        Returns:
            List of import dictionaries
        """
        imports = []
        
        # Language-specific import patterns
        patterns = {
            'python': [
                r'import\s+([\w.]+)',
                r'from\s+([\w.]+)\s+import',
            ],
            'javascript': [
                r'import\s+(?:.*?\s+from\s+)?["\']([^"\']+)["\']',
                r'require\s*\(["\']([^"\']+)["\']',
            ],
            'typescript': [
                r'import\s+(?:.*?\s+from\s+)?["\']([^"\']+)["\']',
            ],
            'java': [
                r'import\s+([\w.*]+);',
            ],
            'go': [
                r'import\s+["\']([^"\']+)["\']',
            ],
            'rust': [
                r'use\s+([\w:]+)',
            ],
        }
        
        import_patterns = patterns.get(language.lower(), [r'import\s+([\w.]+)'])
        
        for pattern in import_patterns:
            for match in re.finditer(pattern, code):
                module = match.group(1)
                start_pos = match.start()
                line_num = code[:start_pos].count('\n') + 1
                imports.append({
                    'module': module,
                    'line': line_num,
                })
        
        # Deduplicate
        seen = set()
        unique_imports = []
        for imp in imports:
            if imp['module'] not in seen:
                seen.add(imp['module'])
                unique_imports.append(imp)
        
        return unique_imports
    
    def _extract_function_signature(
        self,
        code: str,
        match: re.Match,
        language: str
    ) -> str:
        """Extract full function signature."""
        start_pos = match.start()
        end_pos = match.end()
        
        # Try to find the closing parenthesis
        paren_count = 0
        found_open = False
        sig_end = end_pos
        
        for i in range(start_pos, min(start_pos + 500, len(code))):  # Limit search
            char = code[i]
            if char == '(':
                paren_count += 1
                found_open = True
            elif char == ')':
                paren_count -= 1
                if found_open and paren_count == 0:
                    sig_end = i + 1
                    break
        
        return code[start_pos:sig_end]
    
    def extract_entities_from_parsed(
        self,
        parsed_data: Dict[str, Any],
        code: str,
        language: str
    ) -> Dict[str, List[Any]]:
        """
        Extract entities from parsed AST data.
        
        Args:
            parsed_data: Parsed AST data
            code: Source code
            language: Programming language
        
        Returns:
            Dict with extracted entities
        """
        entities = {
            'functions': [],
            'classes': [],
            'rest_endpoints': self.extract_rest_endpoints(code, language),
            'urls': self.extract_urls(code),
            'imports': [],
        }
        
        # Extract from parsed data
        for func in parsed_data.get('functions', []):
            entities['functions'].append({
                'name': func.get('name', ''),
                'line': func.get('start_line', 0),
                'signature': func.get('signature', ''),
            })
        
        for cls in parsed_data.get('classes', []):
            entities['classes'].append({
                'name': cls.get('name', ''),
                'line': cls.get('start_line', 0),
            })
        
        for imp in parsed_data.get('imports', []):
            module = imp.get('module', '') or imp.get('text', '')
            entities['imports'].append({
                'module': module,
                'line': imp.get('line', 0),
            })
        
        return entities


# Global instance
entity_extractor = EntityExtractor()

