"""
Repo Parser (Standalone, Repo-Independent)
=========================================
Creates OpenSearch-ready code chunks, embeddings, and a knowledge graph.

Key requirements implemented:
- Parse code using AST (TreeSitter / javalang via existing standalone parser)
- Generate chunks using AST chunking + LLM enrichment
- For each chunk, make an LLM call to:
  - Extract a canonical signature (method/class)
  - Generate a summary
- Generate lookup_hash using the LLM-extracted signature + FULL code (full SHA256 hex; NOT trimmed)
- Embed chunks in batches
- Publish chunks to OpenSearch using bulk indexing with parallel batch processing
- Generate a NetworkX graph pickle (.pkl)

Usage:
  python repo_parser.py \
    --repo-path /path/to/repo \
    --output-dir ./output \
    --opensearch-host localhost:9200 \
    --opensearch-index code_chunks \
    --llm-model gpt-4o-mini

Environment variables:
- OPENAI_API_KEY: used as default for LLM and embeddings if CLI key not provided
- OPENAI_MODEL: used as default for --llm-model if provided
"""

from __future__ import annotations

import argparse
import asyncio
import hashlib
import json
import os
import pickle
import re
import configparser
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple


# OpenAI (LLM + embeddings)
try:
    from openai import AsyncOpenAI  # type: ignore

    OPENAI_AVAILABLE = True
except Exception:
    OPENAI_AVAILABLE = False
    AsyncOpenAI = None  # type: ignore


# TreeSitter for parsing
try:
    from tree_sitter import Language, Parser  # type: ignore
    import tree_sitter_python as tspython  # type: ignore
    import tree_sitter_java as tsjava  # type: ignore
    import tree_sitter_javascript as tsjavascript  # type: ignore

    TREE_SITTER_AVAILABLE = True
except Exception:
    TREE_SITTER_AVAILABLE = False

# javalang for Java parsing
try:
    import javalang  # type: ignore

    JAVALANG_AVAILABLE = True
except Exception:
    JAVALANG_AVAILABLE = False

# Azure embeddings (optional)
try:
    from azure.identity import CertificateCredential  # type: ignore
    from azure.core.exceptions import ClientAuthenticationError  # type: ignore
    from langchain_openai import AzureOpenAIEmbeddings  # type: ignore
    import configparser

    AZURE_EMBEDDINGS_AVAILABLE = True
except Exception:
    AZURE_EMBEDDINGS_AVAILABLE = False

# OpenSearch (optional)
try:
    from opensearchpy import OpenSearch, RequestsHttpConnection  # type: ignore

    OPENSEARCH_AVAILABLE = True
except Exception:
    OPENSEARCH_AVAILABLE = False

# AWS Auth for OpenSearch (optional)
try:
    from aws_requests_auth.aws_auth import AWSRequestsAuth  # type: ignore
    from boto3 import session  # type: ignore

    AWS_AUTH_AVAILABLE = True
except Exception:
    AWS_AUTH_AVAILABLE = False

# Graph (optional)
try:
    import networkx as nx  # type: ignore

    NETWORKX_AVAILABLE = True
except Exception:
    NETWORKX_AVAILABLE = False

# Progress bar (optional)
try:
    from tqdm import tqdm  # type: ignore

    TQDM_AVAILABLE = True
except Exception:
    TQDM_AVAILABLE = False


def _safe_json_extract(text: str) -> Optional[Dict[str, Any]]:
    """Parse JSON from a model response, tolerating surrounding text."""
    text = (text or "").strip()
    if not text:
        return None
    try:
        return json.loads(text)
    except Exception:
        pass

    # Try to extract the first JSON object within the string
    start = text.find("{")
    end = text.rfind("}")
    if start == -1 or end == -1 or end <= start:
        return None
    candidate = text[start : end + 1]
    try:
        return json.loads(candidate)
    except Exception:
        return None


def _sha256_hex(s: str) -> str:
    return hashlib.sha256(s.encode("utf-8", errors="ignore")).hexdigest()


def _build_lookup_hash(project_id: str, signature: str, full_code: str) -> str:
    """
    Full-length lookup hash (NOT trimmed).
    Uses the LLM-extracted signature + full code as required.
    """
    payload = json.dumps(
        {"project_id": project_id, "signature": signature, "code": full_code},
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
    )
    return f"lookup_{_sha256_hex(payload)}"


def _infer_class_name_from_method_fqn(method_fqn: str) -> str:
    parts = method_fqn.split(".")
    if len(parts) >= 2:
        return parts[-2]
    return ""


def _infer_method_name_from_method_fqn(method_fqn: str) -> str:
    parts = method_fqn.split(".")
    return parts[-1] if parts else ""


def _base_method_name(method_name: str) -> str:
    # Handles the existing splitter naming: method_part0 / method_window0 etc.
    for marker in ("_part", "_window"):
        if marker in method_name:
            return method_name.split(marker)[0]
    return method_name


class AzureEmbeddingService:
    """Azure OpenAI embedding helper (certificate-based bearer token)."""

    def __init__(
        self,
        *,
        user_sid: str = "default_user",
        cert_path: Optional[str] = None,
        config_path: Optional[str] = None,
        azure_endpoint: Optional[str] = None,
        api_version: Optional[str] = None,
        deployment_name: Optional[str] = None,
    ):
        if not AZURE_EMBEDDINGS_AVAILABLE:
            raise RuntimeError("Azure embeddings not available. Install `azure-identity` and `langchain-openai`.")

        self.user_sid = user_sid
        self.config = self._load_config(config_path)
        self.access_token = self._get_access_token(cert_path)

        cfg = self.config["azure_openai"] if self.config and "azure_openai" in self.config else {}
        self.azure_endpoint = azure_endpoint or (cfg.get("azure_endpoint") if cfg else None) or os.getenv("AZURE_OPENAI_ENDPOINT")
        self.api_version = api_version or (cfg.get("azure_api_version") if cfg else None) or os.getenv("AZURE_OPENAI_API_VERSION") or "2024-10-21"
        # For LangChain AzureOpenAIEmbeddings this is typically the deployment name
        self.deployment_name = deployment_name or (cfg.get("deployment_name") if cfg else None) or os.getenv("AZURE_OPENAI_DEPLOYMENT_NAME")

        # Some clients require an api_key param even when using bearer token headers.
        # Never hardcode secrets; use config/env if present, else a dummy placeholder.
        api_key = (cfg.get("openai_api_key") if cfg else None) or os.getenv("AZURE_OPENAI_API_KEY") or "DUMMY"

        if not self.azure_endpoint:
            raise RuntimeError("Azure embeddings: missing azure_endpoint (set in config.ini [azure_openai] or AZURE_OPENAI_ENDPOINT)")
        if not self.deployment_name:
            raise RuntimeError("Azure embeddings: missing deployment_name (set in config.ini [azure_openai] or AZURE_OPENAI_DEPLOYMENT_NAME)")
        if not self.access_token:
            raise RuntimeError("Azure embeddings: failed to obtain bearer token via certificate credential")

        self.embeddings = AzureOpenAIEmbeddings(
            azure_endpoint=self.azure_endpoint,
            openai_api_version=self.api_version,
            azure_deployment=self.deployment_name,
            openai_api_key=api_key,
            openai_api_type="azure",
            default_headers={
                "Authorization": f"Bearer {self.access_token}",
                "user_sid": self.user_sid,
            },
        )

    @staticmethod
    def _load_config(config_path: Optional[str]) -> Optional["configparser.ConfigParser"]:
        if not config_path:
            return None
        if not os.path.exists(config_path):
            raise FileNotFoundError(f"Config file not found: {config_path}")
        cp = configparser.ConfigParser()
        cp.read(config_path)
        return cp

    def _get_access_token(self, cert_path: Optional[str]) -> Optional[str]:
        cfg = self.config["azure_openai"] if self.config and "azure_openai" in self.config else {}
        tenant_id = (cfg.get("azure_tenant_id") if cfg else None) or os.getenv("AZURE_TENANT_ID")
        client_id = (cfg.get("azure_client_id") if cfg else None) or os.getenv("AZURE_CLIENT_ID")
        if not tenant_id or not client_id:
            raise RuntimeError("Azure embeddings: missing azure_tenant_id / azure_client_id (config.ini [azure_openai])")

        if not cert_path:
            # If not provided, try a few likely relative locations
            candidates = [
                os.path.join(os.path.dirname(__file__), "discoveryeng.dev.azure.jpmchase.net.pem"),
                os.path.join(os.path.dirname(__file__), "..", "..", "discoveryeng.dev.azure.jpmchase.net.pem"),
            ]
            cert_path = next((p for p in candidates if os.path.exists(p)), None)
        if not cert_path or not os.path.exists(cert_path):
            raise FileNotFoundError(f"Azure certificate file not found: {cert_path}")

        try:
            credential = CertificateCredential(
                tenant_id=tenant_id,
                client_id=client_id,
                certificate_path=cert_path,
            )
            return credential.get_token("https://cognitiveservices.azure.com/.default").token
        except ClientAuthenticationError as e:
            raise RuntimeError(f"Azure certificate authentication failed: {e}") from e

    @staticmethod
    def chunk_list(data: List[str], chunk_size: int):
        for i in range(0, len(data), chunk_size):
            yield data[i : i + chunk_size]

    def embed_texts(self, texts: List[str]) -> List[List[float]]:
        return self.embeddings.embed_documents(texts)


class StandaloneParser:
    """Self-contained multi-language parser using TreeSitter (and javalang for Java)."""

    def __init__(self):
        self.parsers: Dict[str, Any] = {}
        if TREE_SITTER_AVAILABLE:
            self._init_parsers()

    def _init_parsers(self) -> None:
        def _mk_parser(lang_obj):
            try:
                return Parser(Language(lang_obj))
            except TypeError:
                p = Parser()
                p.set_language(Language(lang_obj))
                return p

        try:
            self.parsers["python"] = _mk_parser(tspython.language())
        except Exception:
            pass
        try:
            self.parsers["java"] = _mk_parser(tsjava.language())
        except Exception:
            pass
        try:
            js_parser = _mk_parser(tsjavascript.language())
            self.parsers["javascript"] = js_parser
            self.parsers["typescript"] = js_parser
        except Exception:
            pass

    def detect_language(self, file_path: str) -> str:
        ext = Path(file_path).suffix.lower()
        return {
            ".java": "java",
            ".py": "python",
            ".js": "javascript",
            ".jsx": "javascript",
            ".ts": "typescript",
            ".tsx": "typescript",
        }.get(ext, "unknown")

    def parse_file(self, file_path: str) -> Optional[Dict[str, Any]]:
        language = self.detect_language(file_path)
        try:
            content = Path(file_path).read_text(encoding="utf-8", errors="ignore")
        except Exception:
            return None

        if language == "java" and JAVALANG_AVAILABLE:
            try:
                return self._parse_java_with_javalang(file_path, content)
            except Exception:
                # fall back below
                pass

        if language not in self.parsers:
            return None

        try:
            parser = self.parsers[language]
            tree = parser.parse(bytes(content, "utf8"))
            root = tree.root_node
            return {
                "language": language,
                "file_path": file_path,
                "file_content": content,
                "functions": self._extract_functions(root, content, language),
                "classes": self._extract_classes(root, content, language),
                "imports": self._extract_imports(root, content, language),
            }
        except Exception:
            return None

    def _parse_java_with_javalang(self, file_path: str, content: str) -> Dict[str, Any]:
        tree = javalang.parse.parse(content)
        imports: List[str] = []
        if getattr(tree, "package", None) and getattr(tree.package, "name", None):
            imports.append(f"package {tree.package.name};")
        for imp in getattr(tree, "imports", []) or []:
            imports.append(f"import {imp.path};")

        classes: List[Dict[str, Any]] = []
        functions: List[Dict[str, Any]] = []

        for type_decl in getattr(tree, "types", []) or []:
            if isinstance(type_decl, javalang.tree.ClassDeclaration):
                class_info = self._extract_class_with_javalang(type_decl, content)
                if class_info:
                    classes.append(class_info)
                for method in getattr(type_decl, "methods", []) or []:
                    mi = self._extract_method_with_javalang(method, type_decl.name, content)
                    if mi:
                        functions.append(mi)

        return {
            "language": "java",
            "file_path": file_path,
            "file_content": content,
            "functions": functions,
            "classes": classes,
            "imports": imports,
            "javalang_tree": tree,
        }

    def _extract_functions(self, root, content: str, language: str) -> List[Dict[str, Any]]:
        functions: List[Dict[str, Any]] = []

        function_node_types = {
            "python": {"function_definition"},
            "java": {"method_declaration"},
            "javascript": {"function_declaration", "method_definition"},
            "typescript": {"function_declaration", "method_definition"},
        }.get(language, set())

        class_node_types = {"class_declaration", "class_definition"}

        def traverse(node, parent_class: Optional[str] = None):
            if node.type in class_node_types:
                name_node = node.child_by_field_name("name")
                current_class = content[name_node.start_byte : name_node.end_byte] if name_node else parent_class
                for child in node.children:
                    traverse(child, current_class)
                return

            if node.type in function_node_types:
                name_node = node.child_by_field_name("name")
                if name_node:
                    name = content[name_node.start_byte : name_node.end_byte]
                    code = content[node.start_byte : node.end_byte]
                    functions.append(
                        {
                            "name": name,
                            "class_name": parent_class,
                            "start_line": node.start_point[0] + 1,
                            "end_line": node.end_point[0] + 1,
                            "code": code,
                        }
                    )
            for child in node.children:
                traverse(child, parent_class)

        traverse(root)
        return functions

    def _extract_classes(self, root, content: str, language: str) -> List[Dict[str, Any]]:
        classes: List[Dict[str, Any]] = []
        class_node_types = {"class_declaration", "class_definition"}

        def traverse(node):
            if node.type in class_node_types:
                name_node = node.child_by_field_name("name")
                if name_node:
                    name = content[name_node.start_byte : name_node.end_byte]
                    code = content[node.start_byte : node.end_byte]
                    classes.append(
                        {
                            "name": name,
                            "start_line": node.start_point[0] + 1,
                            "end_line": node.end_point[0] + 1,
                            "code": code,
                        }
                    )
            for child in node.children:
                traverse(child)

        traverse(root)
        return classes

    def _extract_imports(self, root, content: str, language: str) -> List[str]:
        imports: List[str] = []
        import_node_types = {"import_declaration", "import_statement", "import_from_statement", "package_declaration"}

        def traverse(node):
            if node.type in import_node_types:
                imports.append(content[node.start_byte : node.end_byte].strip())
            for child in node.children:
                traverse(child)

        traverse(root)
        return imports

    def _get_class_code_from_content(self, class_name: str, content: str) -> str:
        patterns = [
            rf"\bclass\s+{re.escape(class_name)}\b",
            rf"\bpublic\s+class\s+{re.escape(class_name)}\b",
            rf"\bprivate\s+class\s+{re.escape(class_name)}\b",
            rf"\bprotected\s+class\s+{re.escape(class_name)}\b",
            rf"\bfinal\s+class\s+{re.escape(class_name)}\b",
        ]
        for pattern in patterns:
            match = re.search(pattern, content)
            if not match:
                continue
            class_start = match.start()
            brace_pos = content.find("{", class_start)
            if brace_pos == -1:
                continue
            brace_count = 0
            i = brace_pos
            in_string = False
            string_char = None
            while i < len(content):
                ch = content[i]
                if ch in ['"', "'"] and (i == 0 or content[i - 1] != "\\"):
                    if not in_string:
                        in_string = True
                        string_char = ch
                    elif ch == string_char:
                        in_string = False
                        string_char = None
                if not in_string:
                    if ch == "{":
                        brace_count += 1
                    elif ch == "}":
                        brace_count -= 1
                        if brace_count == 0:
                            return content[class_start : i + 1]
                i += 1
        return ""

    def _get_constructor_code_from_content(self, constructor, class_name: str, content: str) -> str:
        # Prefer position-based localized search
        try:
            pos = getattr(constructor, "position", None)
            line = getattr(pos, "line", None) if pos else None
            if line and isinstance(line, int) and line > 0:
                lines = content.splitlines(True)
                if line - 1 < len(lines):
                    start_idx = sum(len(l) for l in lines[: line - 1])
                    window = content[start_idx : min(len(content), start_idx + 8000)]
                    m = re.search(rf"\b{re.escape(class_name)}\s*\(", window)
                    if m:
                        match_start = start_idx + m.start()
                        before = content[max(0, match_start - 50) : match_start]
                        prev_word = re.findall(r"\b([A-Za-z_][A-Za-z0-9_]*)\b", before)
                        if prev_word and prev_word[-1] == "new":
                            return ""
                        line_start = content.rfind("\n", max(0, match_start - 200), match_start)
                        if line_start == -1:
                            line_start = max(0, match_start - 200)
                        brace_pos = content.find("{", start_idx + m.end())
                        if brace_pos != -1:
                            brace_count = 0
                            i = brace_pos
                            in_string = False
                            string_char = None
                            while i < len(content):
                                ch = content[i]
                                if ch in ['"', "'"] and (i == 0 or content[i - 1] != "\\"):
                                    if not in_string:
                                        in_string = True
                                        string_char = ch
                                    elif ch == string_char:
                                        in_string = False
                                        string_char = None
                                if not in_string:
                                    if ch == "{":
                                        brace_count += 1
                                    elif ch == "}":
                                        brace_count -= 1
                                        if brace_count == 0:
                                            return content[line_start : i + 1].strip()
                                i += 1
        except Exception:
            pass

        # Fallback full-scan (skip `new ClassName(`)
        for match in re.finditer(rf"\b{re.escape(class_name)}\s*\(", content):
            match_start = match.start()
            before = content[max(0, match_start - 50) : match_start]
            prev_word = re.findall(r"\b([A-Za-z_][A-Za-z0-9_]*)\b", before)
            if prev_word and prev_word[-1] == "new":
                continue
            line_start = content.rfind("\n", max(0, match_start - 200), match_start)
            if line_start == -1:
                line_start = max(0, match_start - 200)
            brace_pos = content.find("{", match.end())
            if brace_pos == -1:
                continue
            brace_count = 0
            i = brace_pos
            in_string = False
            string_char = None
            while i < len(content):
                ch = content[i]
                if ch in ['"', "'"] and (i == 0 or content[i - 1] != "\\"):
                    if not in_string:
                        in_string = True
                        string_char = ch
                    elif ch == string_char:
                        in_string = False
                        string_char = None
                if not in_string:
                    if ch == "{":
                        brace_count += 1
                    elif ch == "}":
                        brace_count -= 1
                        if brace_count == 0:
                            return content[line_start : i + 1].strip()
                i += 1
        return ""

    def _extract_brace_block(self, content: str, start_brace_pos: int) -> Tuple[str, int]:
        """Return (block_text, end_pos) for a {...} block starting at start_brace_pos."""
        if start_brace_pos < 0 or start_brace_pos >= len(content) or content[start_brace_pos] != "{":
            return "", -1
        brace_count = 0
        i = start_brace_pos
        in_string = False
        string_char = None
        while i < len(content):
            ch = content[i]
            if ch in ['"', "'"] and (i == 0 or content[i - 1] != "\\"):
                if not in_string:
                    in_string = True
                    string_char = ch
                elif ch == string_char:
                    in_string = False
                    string_char = None
            if not in_string:
                if ch == "{":
                    brace_count += 1
                elif ch == "}":
                    brace_count -= 1
                    if brace_count == 0:
                        return content[start_brace_pos : i + 1], i
            i += 1
        return "", -1

    def _slice_statement_until_semicolon(self, content: str, start_idx: int, max_chars: int = 8000) -> str:
        """
        Slice from start_idx until the first semicolon at nesting depth 0.
        Handles strings and (), [], {} nesting so we don't stop early.
        """
        if start_idx < 0 or start_idx >= len(content):
            return ""
        end_limit = min(len(content), start_idx + max_chars)
        i = start_idx
        in_string = False
        string_char = None
        paren = 0
        bracket = 0
        brace = 0
        while i < end_limit:
            ch = content[i]
            if ch in ['"', "'"] and (i == 0 or content[i - 1] != "\\"):
                if not in_string:
                    in_string = True
                    string_char = ch
                elif ch == string_char:
                    in_string = False
                    string_char = None
            if not in_string:
                if ch == "(":
                    paren += 1
                elif ch == ")":
                    paren = max(0, paren - 1)
                elif ch == "[":
                    bracket += 1
                elif ch == "]":
                    bracket = max(0, bracket - 1)
                elif ch == "{":
                    brace += 1
                elif ch == "}":
                    brace = max(0, brace - 1)
                elif ch == ";" and paren == 0 and bracket == 0 and brace == 0:
                    return content[start_idx : i + 1].strip()
            i += 1
        return content[start_idx:end_limit].strip()

    def _extract_class_level_blocks_and_fields(self, class_code: str, full_content: str, class_decl) -> Tuple[List[Dict[str, Any]], List[Dict[str, Any]], List[str], List[str]]:
        """
        Extract class-level fields + static/instance initializer blocks for Java classes.
        Returns: (static_fields, instance_fields, static_blocks, instance_blocks)
        """
        static_fields: List[Dict[str, Any]] = []
        instance_fields: List[Dict[str, Any]] = []

        # Fields from AST (more reliable than regex)
        try:
            for body_decl in getattr(class_decl, "body", []) or []:
                if isinstance(body_decl, javalang.tree.FieldDeclaration):
                    mods = list(getattr(body_decl, "modifiers", []) or [])
                    is_static = "static" in mods

                    pos = getattr(body_decl, "position", None)
                    line = getattr(pos, "line", None) if pos else None
                    start_idx = None
                    if line and isinstance(line, int) and line > 0:
                        lines = full_content.splitlines(True)
                        if line - 1 < len(lines):
                            # Use line start (not column) so we don't drop modifiers.
                            start_idx = sum(len(l) for l in lines[: line - 1])

                            # Extend upwards to capture contiguous annotations/comments directly above the field.
                            prev_line_idx = line - 2
                            while prev_line_idx >= 0:
                                prev_line = lines[prev_line_idx]
                                stripped = prev_line.strip()
                                if stripped == "":
                                    break
                                lstripped = prev_line.lstrip()
                                if lstripped.startswith("@") or lstripped.startswith("//") or lstripped.startswith("/*") or lstripped.startswith("*") or lstripped.startswith("*/"):
                                    start_idx -= len(prev_line)
                                    prev_line_idx -= 1
                                    continue
                                break

                    field_code = self._slice_statement_until_semicolon(full_content, start_idx) if start_idx is not None else ""
                    if field_code:
                        target = static_fields if is_static else instance_fields
                        target.append({"code": field_code, "modifiers": mods})
        except Exception:
            pass

        # Static + instance initializer blocks from source (AST doesn't reliably expose them)
        static_blocks: List[str] = []
        instance_blocks: List[str] = []

        # Scan inside class body at depth 1
        body_start = class_code.find("{")
        if body_start == -1:
            return static_fields, instance_fields, static_blocks, instance_blocks

        i = body_start + 1
        depth = 1
        in_string = False
        string_char = None

        def prev_non_ws(pos: int) -> str:
            j = pos - 1
            while j >= 0 and class_code[j].isspace():
                j -= 1
            return class_code[j] if j >= 0 else ""

        while i < len(class_code) - 1 and depth > 0:
            ch = class_code[i]
            if ch in ['"', "'"] and class_code[i - 1] != "\\":
                if not in_string:
                    in_string = True
                    string_char = ch
                elif ch == string_char:
                    in_string = False
                    string_char = None

            if not in_string:
                if ch == "{":
                    if depth == 1:
                        before = class_code[max(0, i - 80) : i]
                        prev = prev_non_ws(i)

                        # If this is a method/constructor/anonymous class body, skip it quickly.
                        if prev == ")":
                            block, end_pos = self._extract_brace_block(class_code, i)
                            if end_pos != -1:
                                i = end_pos + 1
                                continue

                        # Static initializer block: `static { ... }`
                        if re.search(r"\bstatic\s*$", before):
                            static_kw_pos = before.rfind("static")
                            start_pos = max(0, i - 80) + static_kw_pos if static_kw_pos != -1 else i
                            block, end_pos = self._extract_brace_block(class_code, i)
                            if end_pos != -1:
                                static_blocks.append(class_code[start_pos : end_pos + 1].strip())
                                i = end_pos + 1
                                continue

                        # Nested type declaration: skip (not an initializer block)
                        if re.search(r"\b(class|interface|enum|record)\b", before):
                            block, end_pos = self._extract_brace_block(class_code, i)
                            if end_pos != -1:
                                i = end_pos + 1
                                continue

                        # Instance initializer block: `{ ... }` at class level
                        block, end_pos = self._extract_brace_block(class_code, i)
                        if end_pos != -1 and len(block.strip()) > 2:
                            instance_blocks.append(block.strip())
                            i = end_pos + 1
                            continue

                    depth += 1
                elif ch == "}":
                    depth -= 1

            i += 1

        return static_fields, instance_fields, static_blocks, instance_blocks

    def _extract_method_with_javalang(self, method: "javalang.tree.MethodDeclaration", class_name: str, content: str) -> Dict[str, Any]:
        method_name = method.name
        method_code = self._get_method_code_from_content(method_name, content)
        start_line = 1
        end_line = len(content.splitlines())
        m = re.search(rf"\b{re.escape(method_name)}\s*\(", content)
        if m:
            start_line = content[: m.start()].count("\n") + 1

        params = []
        for p in getattr(method, "parameters", []) or []:
            p_type = getattr(p, "type", None)
            p_name = getattr(p, "name", None)
            params.append({"name": p_name or "", "type": str(p_type) if p_type is not None else "Object"})

        return {
            "name": method_name,
            "class_name": class_name,
            "start_line": start_line,
            "end_line": end_line,
            "code": method_code,
            "modifiers": list(getattr(method, "modifiers", []) or []),
            "return_type": getattr(method, "return_type", None),
            "throws": list(getattr(method, "throws", []) or []),
            "parameters": params,
        }

    def _get_method_code_from_content(self, method_name: str, content: str) -> str:
        patterns = [
            rf"\b{re.escape(method_name)}\s*\(",
            rf"\b\w+\s+{re.escape(method_name)}\s*\(",
        ]
        for pattern in patterns:
            for match in re.finditer(pattern, content):
                method_start = match.start()
                line_start = content.rfind("\n", max(0, method_start - 200), method_start)
                if line_start == -1:
                    line_start = max(0, method_start - 200)
                brace_pos = content.find("{", match.end())
                if brace_pos == -1:
                    continue
                brace_count = 0
                i = brace_pos
                in_string = False
                string_char = None
                while i < len(content):
                    ch = content[i]
                    if ch in ['"', "'"] and (i == 0 or content[i - 1] != "\\"):
                        if not in_string:
                            in_string = True
                            string_char = ch
                        elif ch == string_char:
                            in_string = False
                            string_char = None
                    if not in_string:
                        if ch == "{":
                            brace_count += 1
                        elif ch == "}":
                            brace_count -= 1
                            if brace_count == 0:
                                return content[line_start : i + 1].strip()
                    i += 1
        return ""

    def _extract_class_with_javalang(self, class_decl: "javalang.tree.ClassDeclaration", content: str) -> Dict[str, Any]:
        class_name = class_decl.name
        start_line = 1
        end_line = len(content.splitlines())
        m = re.search(rf"\bclass\s+{re.escape(class_name)}\b", content)
        if m:
            start_line = content[: m.start()].count("\n") + 1

        constructors = []
        for ctor in getattr(class_decl, "constructors", []) or []:
            ctor_code = self._get_constructor_code_from_content(ctor, class_name, content)
            if ctor_code:
                constructors.append({"name": class_name, "code": ctor_code, "modifiers": list(getattr(ctor, "modifiers", []) or [])})

        # Minimal class-level code to avoid method bodies, but keep constructors in metadata
        class_code = self._get_class_code_from_content(class_name, content)

        static_fields, instance_fields, static_blocks, instance_blocks = self._extract_class_level_blocks_and_fields(
            class_code=class_code,
            full_content=content,
            class_decl=class_decl,
        )

        return {
            "name": class_name,
            "start_line": start_line,
            "end_line": end_line,
            "code": class_code,
            "static_fields": static_fields,
            "instance_fields": instance_fields,
            "static_blocks": static_blocks,
            "instance_blocks": instance_blocks,
            "constructors": constructors,
            "javalang_data": True,
        }


class StandaloneIndexer:
    """Chunk generator + embedding generator."""

    def __init__(
        self,
        openai_api_key: Optional[str] = None,
        embedding_model: str = "text-embedding-3-small",
        chunking_strategy: str = "class_metadata",
        max_chunk_size: int = 1000,
        enforce_chunk_size: bool = True,
        chunk_overlap_size: int = 50,
        batch_size: int = 100,
        use_azure_embeddings: bool = False,
        user_sid: str = "default_user",
        azure_cert_path: Optional[str] = None,
        azure_config_path: Optional[str] = None,
        application_name: Optional[str] = None,
        seal_id: Optional[str] = None,
    ):
        self.parser = StandaloneParser()
        self.embedding_model = embedding_model
        self.chunking_strategy = chunking_strategy
        self.max_chunk_size = max_chunk_size
        self.enforce_chunk_size = enforce_chunk_size
        self.chunk_overlap_size = chunk_overlap_size
        self.batch_size = batch_size

        self.repo_path: Optional[str] = None
        self.module_map: Dict[str, Optional[str]] = {}

        self.application_name = application_name or ""
        self.seal_id = seal_id or ""
        self.project_id = f"{self.application_name}:{self.seal_id}" if (self.application_name and self.seal_id) else ""

        self.embedding_client = None
        self.azure_embedding_service: Optional[AzureEmbeddingService] = None

        if use_azure_embeddings:
            self.azure_embedding_service = AzureEmbeddingService(
                user_sid=user_sid,
                cert_path=azure_cert_path,
                config_path=azure_config_path,
            )
        elif OPENAI_AVAILABLE and openai_api_key:
            self.embedding_client = AsyncOpenAI(api_key=openai_api_key)

    def find_code_files(self, repo_path: str) -> List[str]:
        repo = Path(repo_path)
        exclude_dirs = {".git", "node_modules", "target", "build", "__pycache__", ".venv"}
        code_files: List[str] = []
        for ext in ["*.java", "*.py", "*.js", "*.jsx", "*.ts", "*.tsx"]:
            for f in repo.rglob(ext):
                if any(ex in f.parts for ex in exclude_dirs):
                    continue
                code_files.append(str(f))
        return code_files

    async def generate_embeddings_batch(self, texts: List[str]) -> List[Optional[List[float]]]:
        if not texts:
            return []

        # Azure embeddings (sync) -> executor
        if self.azure_embedding_service:
            loop = asyncio.get_event_loop()
            all_embeddings: List[Optional[List[float]]] = []
            for batch in AzureEmbeddingService.chunk_list(texts, self.batch_size):
                try:
                    batch_embeddings = await loop.run_in_executor(None, self.azure_embedding_service.embed_texts, batch)
                    all_embeddings.extend(batch_embeddings)
                except Exception:
                    all_embeddings.extend([None] * len(batch))
            return all_embeddings

        if not self.embedding_client:
            return [None] * len(texts)

        all_embeddings: List[Optional[List[float]]] = []
        for i in range(0, len(texts), self.batch_size):
            batch = texts[i : i + self.batch_size]
            try:
                resp = await self.embedding_client.embeddings.create(model=self.embedding_model, input=batch)
                all_embeddings.extend([item.embedding for item in resp.data])
            except Exception:
                all_embeddings.extend([None] * len(batch))
        return all_embeddings

    def _get_relative_path(self, file_path: str) -> str:
        if not self.repo_path:
            return file_path
        try:
            return str(Path(file_path).resolve().relative_to(Path(self.repo_path).resolve()))
        except Exception:
            return file_path

    def _get_filetype(self, file_path: str) -> str:
        return Path(file_path).suffix.lower() or "unknown"

    def _extract_package_name(self, parsed: Dict[str, Any], file_path: str) -> str:
        for imp in parsed.get("imports", []) or []:
            if "package" in imp.lower():
                m = re.search(r"package\s+([\w.]+)", imp)
                if m:
                    return m.group(1)
        if file_path.endswith(".java"):
            for pattern in [
                r"src/main/java/(.+?)/[^/]+\.java$",
                r"src/(.+?)/[^/]+\.java$",
                r"java/(.+?)/[^/]+\.java$",
            ]:
                m = re.search(pattern, file_path.replace("\\", "/"))
                if m:
                    return m.group(1).replace("/", ".")
        return ""

    def _extract_method_signature(self, func: Dict[str, Any], parsed: Dict[str, Any], file_path: str) -> str:
        if parsed.get("language") != "java":
            return func.get("name", "")
        name = func.get("name", "")
        modifiers = func.get("modifiers", []) or []
        return_type = func.get("return_type", None)
        throws = func.get("throws", []) or []
        params = func.get("parameters", []) or []

        def fmt_type(t) -> str:
            if t is None:
                return "void"
            return str(t)

        mods = " ".join(modifiers).strip()
        ret = fmt_type(return_type)
        params_str = ", ".join([f"{p.get('type','Object')} {p.get('name','')}".strip() for p in params]).strip()
        throws_str = ""
        if throws:
            throws_str = " throws " + ", ".join([str(x) for x in throws])
        sig = f"{mods} {ret} {name}({params_str}){throws_str}".strip()
        return re.sub(r"\s+", " ", sig).strip()

    def _generate_chunk_id(self, chunk: Dict[str, Any]) -> str:
        unique_string = (
            f"{chunk.get('file_path', '')}:"
            f"{chunk.get('start_line', -1)}:"
            f"{chunk.get('end_line', -1)}:"
            f"{chunk.get('chunk_order', 0)}:"
            f"{chunk.get('type', '')}:"
            f"{chunk.get('fqn', '')}"
        )
        return f"chunk_{hashlib.sha256(unique_string.encode()).hexdigest()[:16]}"

    def _generate_chunk_content_id(self, chunk: Dict[str, Any]) -> str:
        content_string = f"{chunk.get('code', '')}{chunk.get('summary', '')}{chunk.get('fqn', '')}{chunk.get('type', '')}"
        return f"content_{hashlib.sha256(content_string.encode()).hexdigest()}"

    def _generate_chunks_for_file(self, parsed: Dict[str, Any], file_path: str) -> List[Dict[str, Any]]:
        if self.chunking_strategy in {"method_only", "class_metadata", "hybrid", "recursive", "sliding_window"}:
            # For now, keep behavior close to "class_metadata"
            return self._generate_chunks_class_metadata(parsed, file_path)
        return self._generate_chunks_class_metadata(parsed, file_path)

    def _generate_chunks_class_metadata(self, parsed: Dict[str, Any], file_path: str) -> List[Dict[str, Any]]:
        chunks: List[Dict[str, Any]] = []
        for func in parsed.get("functions", []) or []:
            chunk = self._create_method_chunk(func, parsed, file_path)
            chunks.append(chunk)
        for cls in parsed.get("classes", []) or []:
            chunk = self._create_class_metadata_chunk(cls, parsed, file_path)
            chunks.append(chunk)
        return chunks

    def _create_method_chunk(self, func: Dict[str, Any], parsed: Dict[str, Any], file_path: str) -> Dict[str, Any]:
        rel_path = self._get_relative_path(file_path)
        package = self._extract_package_name(parsed, rel_path)
        class_name = func.get("class_name") or Path(file_path).stem
        method_name = func.get("name", "")
        fqn = f"{package}.{class_name}.{method_name}".strip(".") if package else f"{class_name}.{method_name}"

        chunk = {
            "type": "method",
            "fqn": fqn,
            "file_path": rel_path,
            "start_line": func.get("start_line", 1),
            "end_line": func.get("end_line", 1),
            "code": func.get("code", ""),
            "summary": f"Method {method_name}",
            "language": parsed.get("language", "unknown"),
            "filetype": self._get_filetype(file_path),
            "lookup_hash": "",
        }
        chunk["chunk_id"] = self._generate_chunk_id(chunk)
        chunk["_id"] = self._generate_chunk_content_id(chunk)
        return chunk

    def _create_class_metadata_chunk(self, cls: Dict[str, Any], parsed: Dict[str, Any], file_path: str) -> Dict[str, Any]:
        rel_path = self._get_relative_path(file_path)
        class_name = cls.get("name", "")
        class_code = cls.get("code", "") or ""

        signature = ""
        if "{" in class_code:
            signature = class_code.split("{")[0].strip() + " {"
        if not signature:
            signature = f"class {class_name} {{"

        class_parts = [signature]

        # Include class variables (fields)
        for field in cls.get("static_fields", []) or []:
            field_code = field.get("code", "") if isinstance(field, dict) else str(field)
            if field_code:
                class_parts.append(field_code)

        for field in cls.get("instance_fields", []) or []:
            field_code = field.get("code", "") if isinstance(field, dict) else str(field)
            if field_code:
                class_parts.append(field_code)

        # Include static blocks / instance initializer blocks
        for block in cls.get("static_blocks", []) or []:
            if block:
                class_parts.append(block)

        for block in cls.get("instance_blocks", []) or []:
            if block:
                class_parts.append(block)

        # Include constructors if present (Java javalang path)
        for ctor in cls.get("constructors", []) or []:
            ctor_code = ctor.get("code", "")
            if ctor_code:
                class_parts.append(ctor_code)

        class_metadata_code = "\n".join([p for p in class_parts if p])
        end_line = cls.get("end_line", cls.get("start_line", 1))

        chunk = {
            "type": "class",
            "fqn": f"{Path(file_path).stem}.{class_name}",
            "file_path": rel_path,
            "start_line": cls.get("start_line", 1),
            "end_line": end_line,
            "code": class_metadata_code,
            "summary": f"Class {class_name}",
            "language": parsed.get("language", "unknown"),
            "filetype": self._get_filetype(file_path),
            "lookup_hash": "",
        }
        chunk["chunk_id"] = self._generate_chunk_id(chunk)
        chunk["_id"] = self._generate_chunk_content_id(chunk)
        return chunk


class StandaloneOpenSearch:
    """Standalone OpenSearch client (optional AWS auth + bulk indexing)."""

    def __init__(
        self,
        host: Optional[str] = None,
        index: Optional[str] = None,
        config_path: Optional[str] = None,
        use_aws_auth: bool = False,
        region: Optional[str] = None,
        use_ssl: bool = False,
        verify_certs: bool = False,
        application_name: Optional[str] = None,
        seal_id: Optional[str] = None,
    ):
        self.client = None
        self.application_name = application_name or ""
        self.seal_id = seal_id or ""

        self.use_aws_auth = use_aws_auth
        self.use_ssl = use_ssl
        self.verify_certs = verify_certs
        self.aws_session = None
        self.aws_host = None
        self.hostname = None
        self.port = None
        self.region = region or "us-east-1"

        self.config = None
        self.opensearch_endpoint = host or ""
        self.index_name = index or "code_chunks"

        if config_path and os.path.exists(config_path):
            self.config = configparser.ConfigParser()
            self.config.read(config_path)
            if "aws_info" in self.config:
                aws_info = self.config["aws_info"]
                self.opensearch_endpoint = aws_info.get("opensearch_endpoint", self.opensearch_endpoint)
                self.index_name = aws_info.get("index_name", self.index_name)
                self.region = aws_info.get("region", self.region)

        if not self.opensearch_endpoint or not OPENSEARCH_AVAILABLE:
            return

        if self.use_aws_auth and AWS_AUTH_AVAILABLE:
            self.aws_session = session.Session()
            self._refresh_aws_auth()
        else:
            host_parts = self.opensearch_endpoint.replace("https://", "").replace("http://", "").split(":")
            self.hostname = host_parts[0]
            self.port = int(host_parts[1]) if len(host_parts) > 1 else 9200
            self.client = OpenSearch(
                hosts=[{"host": self.hostname, "port": self.port}],
                use_ssl=use_ssl,
                verify_certs=verify_certs,
                connection_class=RequestsHttpConnection,
            )

    def _refresh_aws_auth(self) -> bool:
        if not (self.use_aws_auth and AWS_AUTH_AVAILABLE and self.aws_session):
            return False
        try:
            credentials = self.aws_session.get_credentials()
            if not credentials:
                return False
            self.aws_host = self.opensearch_endpoint.replace("https://", "").replace("http://", "").split(":")[0]
            self.hostname = self.aws_host
            self.port = 443
            if ":" in self.opensearch_endpoint:
                port_part = self.opensearch_endpoint.split(":")[-1].split("/")[0]
                try:
                    self.port = int(port_part)
                except Exception:
                    self.port = 443
            awsauth = AWSRequestsAuth(
                aws_access_key=credentials.access_key,
                aws_secret_access_key=credentials.secret_key,
                aws_token=credentials.token,
                aws_host=self.aws_host,
                aws_region=self.region,
                aws_service="es",
            )
            self.client = OpenSearch(
                hosts=[{"host": self.hostname, "port": self.port}],
                http_auth=awsauth,
                use_ssl=True,
                verify_certs=self.verify_certs,
                connection_class=RequestsHttpConnection,
            )
            return True
        except Exception:
            return False

    async def ensure_index(self, embedding_dim: int = 1536) -> bool:
        if not self.client:
            return False
        try:
            if self.client.indices.exists(index=self.index_name):
                return True
            index_body = {
                "settings": {"index": {"knn": True, "number_of_shards": 5, "number_of_replicas": 1}},
                "mappings": {
                    "properties": {
                        "chunk_id": {"type": "keyword"},
                        "type": {"type": "keyword"},
                        # fqn as text + exact-match subfield
                        "fqn": {"type": "text", "fields": {"keyword": {"type": "keyword", "ignore_above": 256}}},
                        "file_path": {"type": "keyword"},
                        "filetype": {"type": "keyword"},
                        "module": {"type": "keyword"},
                        "start_line": {"type": "integer"},
                        "end_line": {"type": "integer"},
                        "code": {"type": "text"},
                        "summary": {"type": "text"},
                        "application_name": {"type": "keyword"},
                        "seal_id": {"type": "keyword"},
                        "lookup_hash": {"type": "keyword"},
                        "embedding": {"type": "knn_vector", "dimension": embedding_dim},
                    }
                },
            }
            self.client.indices.create(index=self.index_name, body=index_body)
            return True
        except Exception:
            return False

    def _prepare_bulk_body(self, batch_chunks: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        bulk_body: List[Dict[str, Any]] = []
        for chunk in batch_chunks:
            doc_id = chunk.get("_id", chunk.get("chunk_id"))
            bulk_body.append({"index": {"_index": self.index_name, "_id": doc_id}})
            doc = {
                "chunk_id": chunk.get("chunk_id", ""),
                "type": chunk.get("type", ""),
                "fqn": chunk.get("fqn", ""),
                "file_path": chunk.get("file_path", ""),
                "filetype": chunk.get("filetype", ""),
                "start_line": chunk.get("start_line", -1),
                "end_line": chunk.get("end_line", -1),
                "code": chunk.get("code", ""),
                "summary": chunk.get("summary", ""),
                "application_name": self.application_name,
                "seal_id": self.seal_id,
                "lookup_hash": chunk.get("lookup_hash", ""),
                "embedding": chunk.get("embedding"),
            }
            if chunk.get("module"):
                doc["module"] = chunk["module"]
            bulk_body.append(doc)
        return bulk_body

    def _index_batch(self, batch_chunks: List[Dict[str, Any]], batch_num: int) -> Tuple[int, int, Optional[str]]:
        if not self.client:
            return 0, len(batch_chunks), f"Batch {batch_num}: OpenSearch client not initialized"
        bulk_body = self._prepare_bulk_body(batch_chunks)
        try:
            resp = self.client.bulk(body=bulk_body)
            if resp.get("errors"):
                errors = [it for it in resp.get("items", []) if "error" in it.get("index", {})]
                err_count = len(errors)
                ok = len(batch_chunks) - err_count
                msg = None
                if errors:
                    msg = f"Batch {batch_num}: {errors[0]['index']['error'].get('reason', 'Unknown error')}"
                return ok, err_count, msg
            return len(batch_chunks), 0, None
        except Exception as e:
            return 0, len(batch_chunks), f"Batch {batch_num}: {e}"

    async def index_chunks(self, chunks: List[Dict[str, Any]], batch_size: int = 100, max_workers: int = 4) -> None:
        if not self.client:
            return
        # Determine embedding dim from first embedding
        dim = None
        for c in chunks:
            emb = c.get("embedding")
            if isinstance(emb, list) and emb:
                dim = len(emb)
                break
        await self.ensure_index(embedding_dim=dim or 1536)

        valid = [c for c in chunks if c.get("embedding") is not None]
        if not valid:
            return

        batches = [valid[i : i + batch_size] for i in range(0, len(valid), batch_size)]
        if max_workers > 1 and len(batches) > 1:
            with ThreadPoolExecutor(max_workers=max_workers) as ex:
                future_to_idx = {ex.submit(self._index_batch, b, i + 1): i for i, b in enumerate(batches)}
                for fut in as_completed(future_to_idx):
                    _ = fut.result()
        else:
            for i, b in enumerate(batches, 1):
                self._index_batch(b, i)


class StandaloneGraphBuilder:
    """NetworkX graph builder + pickle writer."""

    def __init__(self):
        self.graph = nx.MultiDiGraph() if NETWORKX_AVAILABLE else None

    def build_graph(self, chunks: List[Dict[str, Any]]) -> None:
        if not self.graph:
            return
        # Nodes: chunk_id
        for c in chunks:
            cid = c.get("chunk_id")
            if not cid:
                continue
            self.graph.add_node(
                cid,
                type=c.get("type"),
                fqn=c.get("fqn"),
                file_path=c.get("file_path"),
            )
        # Edges: in same file
        by_file: Dict[str, List[str]] = {}
        for c in chunks:
            cid = c.get("chunk_id")
            fp = c.get("file_path")
            if cid and fp:
                by_file.setdefault(fp, []).append(cid)
        for fp, ids in by_file.items():
            for a in ids:
                for b in ids:
                    if a != b:
                        self.graph.add_edge(a, b, relationship="IN_FILE", file_path=fp)

    def save_graph(self, output_path: str) -> None:
        if not self.graph:
            return
        with open(output_path, "wb") as f:
            pickle.dump(self.graph, f)

    def get_stats(self) -> Dict[str, int]:
        if not self.graph:
            return {"nodes": 0, "edges": 0}
        return {"nodes": self.graph.number_of_nodes(), "edges": self.graph.number_of_edges()}


@dataclass(frozen=True)
class LLMChunkResult:
    signature: str
    summary: str


class LLMChunkAnnotator:
    """
    Uses an LLM call to:
    - Extract canonical method/class signature
    - Generate a chunk summary
    Then the caller generates lookup_hash using signature + full code.
    """

    def __init__(
        self,
        api_key: str,
        model: str,
        max_concurrency: int = 16,
        timeout_s: int = 60,
    ):
        if not OPENAI_AVAILABLE:
            raise RuntimeError("OpenAI client not available. Install `openai` and retry.")
        self.client = AsyncOpenAI(api_key=api_key)
        self.model = model
        self.timeout_s = timeout_s
        self._sem = asyncio.Semaphore(max_concurrency)
        self._cache: Dict[str, LLMChunkResult] = {}

    async def _call(self, *, cache_key: str, messages: List[Dict[str, str]]) -> LLMChunkResult:
        if cache_key in self._cache:
            return self._cache[cache_key]

        async with self._sem:
            resp = await self.client.chat.completions.create(
                model=self.model,
                messages=messages,
                temperature=0,
                timeout=self.timeout_s,
            )

        content = (resp.choices[0].message.content or "").strip()
        data = _safe_json_extract(content) or {}
        signature = (data.get("signature") or "").strip()
        summary = (data.get("summary") or "").strip()

        if not signature:
            signature = (data.get("method_signature") or data.get("class_signature") or "").strip()
        if not summary:
            summary = (data.get("chunk_summary") or "").strip()

        result = LLMChunkResult(signature=signature, summary=summary)
        self._cache[cache_key] = result
        return result

    async def annotate_method(
        self,
        *,
        language: str,
        fqn: str,
        ast_signature_guess: str,
        full_method_code: str,
    ) -> LLMChunkResult:
        cache_key = f"method::{language}::{fqn}::{_sha256_hex(full_method_code)}"
        messages = [
            {
                "role": "system",
                "content": (
                    "You extract code signatures and write concise summaries. "
                    "Return STRICT JSON only, with keys: signature, summary."
                ),
            },
            {
                "role": "user",
                "content": (
                    f"Language: {language}\n"
                    f"FQN: {fqn}\n"
                    f"AST signature guess: {ast_signature_guess}\n\n"
                    "Task:\n"
                    "- Extract the canonical method/function signature (include modifiers/return type/params/throws when relevant).\n"
                    "- Write a concise summary of JUST this method/function (1-4 sentences).\n\n"
                    "Method code:\n"
                    "``` \n"
                    f"{full_method_code}\n"
                    "```\n\n"
                    "Return JSON like:\n"
                    '{"signature":"...","summary":"..."}'
                ),
            },
        ]
        return await self._call(cache_key=cache_key, messages=messages)

    async def annotate_class(
        self,
        *,
        language: str,
        fqn: str,
        class_code: str,
        method_summaries: List[Tuple[str, str]],
    ) -> LLMChunkResult:
        method_lines = "\n".join([f"- {sig}: {summ}" for sig, summ in method_summaries][:200])
        cache_key = f"class::{language}::{fqn}::{_sha256_hex(class_code)}::{_sha256_hex(method_lines)}"
        messages = [
            {
                "role": "system",
                "content": (
                    "You extract code signatures and write concise summaries. "
                    "Return STRICT JSON only, with keys: signature, summary."
                ),
            },
            {
                "role": "user",
                "content": (
                    f"Language: {language}\n"
                    f"FQN: {fqn}\n\n"
                    "Task:\n"
                    "- Extract the canonical class signature (include modifiers/extends/implements when relevant).\n"
                    "- Write a summary of the ENTIRE class for similarity search (2-6 sentences).\n\n"
                    "Class code:\n"
                    "``` \n"
                    f"{class_code}\n"
                    "```\n\n"
                    "Methods in this class (signature: summary):\n"
                    f"{method_lines}\n\n"
                    "Return JSON like:\n"
                    '{"signature":"...","summary":"..."}'
                ),
            },
        ]
        return await self._call(cache_key=cache_key, messages=messages)


async def _ensure_summary_mapping(opensearch: StandaloneOpenSearch) -> None:
    """
    Ensure `summary` exists in the OpenSearch mapping, even if the index pre-exists.
    """
    if not getattr(opensearch, "client", None):
        return
    index_name = getattr(opensearch, "index_name", None)
    if not index_name:
        return

    try:
        if not opensearch.client.indices.exists(index=index_name):
            return  # will be created by ensure_index
        mapping = opensearch.client.indices.get_mapping(index=index_name)
        props = (
            mapping.get(index_name, {})
            .get("mappings", {})
            .get("properties", {})
        )
        if "summary" in props:
            return
        opensearch.client.indices.put_mapping(
            index=index_name,
            body={"properties": {"summary": {"type": "text"}}},
        )
    except Exception:
        # Non-fatal; indexing can still proceed if summary already exists or mapping update is blocked.
        return


def _embedding_text_for_chunk(chunk: Dict[str, Any], max_chars: int = 12000) -> str:
    """
    Create the text that will be embedded.
    Prefer summaries (more semantic), but keep some code context.
    """
    summary = (chunk.get("summary") or "").strip()
    code = (chunk.get("code") or "").strip()
    if chunk.get("type") == "class":
        text = summary or code
    else:
        text = f"{summary}\n\n{code}".strip() if summary else code
    return text[:max_chars]


async def run_pipeline(
    *,
    repo_path: str,
    output_dir: str,
    opensearch_host: Optional[str],
    opensearch_index: str,
    opensearch_config_path: Optional[str],
    llm_api_key: str,
    embedding_openai_api_key: Optional[str],
    llm_model: str,
    embedding_model: str,
    chunking_strategy: str,
    max_chunk_size: int,
    enforce_chunk_size: bool,
    chunk_overlap_size: int,
    embedding_batch_size: int,
    llm_concurrency: int,
    opensearch_batch_size: int,
    opensearch_workers: int,
    use_aws_auth: bool,
    region: Optional[str],
    use_ssl: bool,
    verify_certs: bool,
    application_name: Optional[str],
    seal_id: Optional[str],
    use_azure_embeddings: bool,
    azure_cert_path: Optional[str],
    azure_config_path: Optional[str],
) -> Dict[str, Any]:
    output_path = Path(output_dir)
    output_path.mkdir(parents=True, exist_ok=True)

    indexer = StandaloneIndexer(
        openai_api_key=embedding_openai_api_key,
        embedding_model=embedding_model,
        chunking_strategy=chunking_strategy,
        max_chunk_size=max_chunk_size,
        enforce_chunk_size=enforce_chunk_size,
        chunk_overlap_size=chunk_overlap_size,
        batch_size=embedding_batch_size,
        application_name=application_name,
        seal_id=seal_id,
        use_azure_embeddings=use_azure_embeddings,
        azure_cert_path=azure_cert_path,
        azure_config_path=azure_config_path,
    )
    # Ensure relative paths and module detection work
    indexer.repo_path = repo_path
    indexer.module_map = {}

    project_id = getattr(indexer, "project_id", "") or ""
    if not project_id:
        # Keep behavior consistent with the existing pipeline: lookup hashes are meaningful with app+seal.
        project_id = f"{application_name or ''}:{seal_id or ''}".strip(":")

    print(f"📁 Scanning repository: {repo_path}")
    code_files = indexer.find_code_files(repo_path)
    print(f"   Found {len(code_files)} code files")

    all_chunks: List[Dict[str, Any]] = []
    parsed_files: List[Dict[str, Any]] = []

    file_iter = tqdm(code_files, desc="Parsing & chunking") if TQDM_AVAILABLE else code_files
    for file_path in file_iter:
        parsed = indexer.parser.parse_file(file_path)
        if not parsed:
            continue

        # Normalize file_path to relative path (matches chunks & graph builder expectations)
        rel_path = indexer._get_relative_path(file_path)
        parsed["file_path"] = rel_path

        # Build maps for "full code" lookup for LLM calls
        class_code_by_name: Dict[str, str] = {}
        for cls in parsed.get("classes", []):
            name = cls.get("name", "")
            code = cls.get("code", "") or ""
            if name and code:
                class_code_by_name[name] = code

        method_full_by_name: Dict[str, Tuple[str, str]] = {}
        for fn in parsed.get("functions", []):
            name = fn.get("name", "")
            full_code = fn.get("code", "") or ""
            if not name or not full_code:
                continue
            ast_sig = indexer._extract_method_signature(fn, parsed, file_path)
            method_full_by_name[name] = (full_code, ast_sig)

        file_chunks = indexer._generate_chunks_for_file(parsed, file_path)
        if not file_chunks:
            continue

        # Enrich chunks with helper fields for later LLM calls (not indexed)
        for ch in file_chunks:
            if ch.get("type") == "method":
                method_name = _base_method_name(_infer_method_name_from_method_fqn(ch.get("fqn", "")))
                full_code, ast_sig = method_full_by_name.get(method_name, (ch.get("code", "") or "", ""))
                ch["_llm_full_code"] = full_code
                ch["_llm_ast_signature_guess"] = ast_sig
            elif ch.get("type") == "class":
                class_name = (ch.get("fqn", "").split(".")[-1] if ch.get("fqn") else "")
                ch["_llm_full_code"] = class_code_by_name.get(class_name, ch.get("code", "") or "")

        all_chunks.extend(file_chunks)
        parsed_files.append(parsed)

    print(f"✅ Generated {len(all_chunks)} chunks (pre-LLM)")

    # LLM enrichment: signatures + summaries, then lookup_hash from signature + full code
    annotator = LLMChunkAnnotator(
        api_key=llm_api_key,
        model=llm_model,
        max_concurrency=llm_concurrency,
    )

    # 1) Methods first (so class summaries can incorporate method summaries)
    method_chunks = [c for c in all_chunks if c.get("type") == "method"]

    async def _annotate_one_method(c: Dict[str, Any]) -> None:
        full_code = c.get("_llm_full_code") or c.get("code") or ""
        ast_sig = c.get("_llm_ast_signature_guess") or ""
        res = await annotator.annotate_method(
            language=c.get("language", "unknown"),
            fqn=c.get("fqn", ""),
            ast_signature_guess=ast_sig,
            full_method_code=full_code,
        )
        signature = res.signature or ast_sig or c.get("fqn", "")
        summary = res.summary or c.get("summary", "") or f"Method {c.get('fqn', '')}"
        c["summary"] = summary
        if project_id:
            c["lookup_hash"] = _build_lookup_hash(project_id, signature, full_code)
        c["_llm_signature"] = signature

    if method_chunks:
        method_iter = tqdm(method_chunks, desc="LLM methods") if TQDM_AVAILABLE else method_chunks
        # Use bounded concurrency via the annotator's semaphore
        await asyncio.gather(*[_annotate_one_method(c) for c in method_iter])

    # 2) Classes next
    # Build mapping: (file_path, class_name) -> [(method_signature, method_summary), ...]
    methods_by_class: Dict[Tuple[str, str], List[Tuple[str, str]]] = {}
    for c in method_chunks:
        file_path = c.get("file_path", "")
        class_name = _infer_class_name_from_method_fqn(c.get("fqn", ""))
        if not file_path or not class_name:
            continue
        sig = (c.get("_llm_signature") or c.get("fqn") or "").strip()
        summ = (c.get("summary") or "").strip()
        methods_by_class.setdefault((file_path, class_name), []).append((sig, summ))

    class_chunks = [c for c in all_chunks if c.get("type") == "class"]

    async def _annotate_one_class(c: Dict[str, Any]) -> None:
        file_path = c.get("file_path", "")
        class_name = (c.get("fqn", "").split(".")[-1] if c.get("fqn") else "")
        full_code = c.get("_llm_full_code") or c.get("code") or ""
        method_summaries = methods_by_class.get((file_path, class_name), [])
        res = await annotator.annotate_class(
            language=c.get("language", "unknown"),
            fqn=c.get("fqn", ""),
            class_code=full_code,
            method_summaries=method_summaries,
        )
        signature = res.signature or c.get("fqn", "") or f"class {class_name}"
        summary = res.summary or c.get("summary", "") or f"Class {class_name}"
        c["summary"] = summary
        if project_id:
            c["lookup_hash"] = _build_lookup_hash(project_id, signature, full_code)
        c["_llm_signature"] = signature

    if class_chunks:
        class_iter = tqdm(class_chunks, desc="LLM classes") if TQDM_AVAILABLE else class_chunks
        await asyncio.gather(*[_annotate_one_class(c) for c in class_iter])

    # Cleanup helper fields (avoid writing them out)
    for c in all_chunks:
        c.pop("_llm_full_code", None)
        c.pop("_llm_ast_signature_guess", None)
        c.pop("_llm_signature", None)

    # Embeddings (batched)
    print(f"📊 Generating embeddings for {len(all_chunks)} chunks...")
    texts = [_embedding_text_for_chunk(c) for c in all_chunks]
    embeddings = await indexer.generate_embeddings_batch(texts)
    for c, emb in zip(all_chunks, embeddings):
        if emb:
            c["embedding"] = emb

    # Save chunks to JSON (for debugging / inspection)
    chunks_file = output_path / "chunks.json"
    with open(chunks_file, "w", encoding="utf-8") as f:
        json.dump(all_chunks, f, indent=2, ensure_ascii=False)
    print(f"✅ Saved chunks to {chunks_file}")

    # Publish to OpenSearch
    if opensearch_host or opensearch_config_path:
        opensearch = StandaloneOpenSearch(
            host=opensearch_host,
            index=opensearch_index,
            config_path=opensearch_config_path,
            use_aws_auth=use_aws_auth,
            region=region,
            use_ssl=use_ssl,
            verify_certs=verify_certs,
            application_name=application_name,
            seal_id=seal_id,
        )
        await _ensure_summary_mapping(opensearch)
        await opensearch.index_chunks(
            all_chunks,
            batch_size=opensearch_batch_size,
            max_workers=opensearch_workers,
        )

    # Graph
    graph_builder = StandaloneGraphBuilder()
    graph_builder.build_graph(all_chunks)
    graph_file = output_path / "graph.pkl"
    graph_builder.save_graph(str(graph_file))

    stats = graph_builder.get_stats()
    return {
        "chunks": len(all_chunks),
        "files": len(parsed_files),
        "graph_nodes": stats.get("nodes", 0),
        "graph_edges": stats.get("edges", 0),
        "chunks_file": str(chunks_file),
        "graph_file": str(graph_file),
    }


async def main() -> None:
    p = argparse.ArgumentParser(description="Repo parser: chunks + LLM hash/summary + embeddings + OpenSearch + graph")
    mode = p.add_mutually_exclusive_group(required=True)
    mode.add_argument("--repo-path", help="Repository path (full repo mode)")
    mode.add_argument("--file", help="Path to a single file to generate chunks for (single file mode)")
    p.add_argument("--output-dir", default="./output", help="Output directory (repo mode)")
    p.add_argument("--output", default="chunks.json", help="Output JSON path (single file mode)")

    p.add_argument("--opensearch-host", help="OpenSearch endpoint (e.g., localhost:9200)")
    p.add_argument("--opensearch-index", default="code_chunks", help="OpenSearch index name")
    p.add_argument("--opensearch-config", help="Path to OpenSearch config.ini (same format as standalone_build_repo_independent.py)")
    p.add_argument("--opensearch-batch-size", type=int, default=100, help="Chunks per bulk batch (default: 100)")
    p.add_argument(
        "--opensearch-workers",
        "--opensearch-max-workers",
        dest="opensearch_workers",
        type=int,
        default=4,
        help="Parallel bulk workers (default: 4)",
    )
    p.add_argument("--use-aws-auth", action="store_true", default=False, help="Use AWS auth for OpenSearch (default: False)")
    p.add_argument("--region", help="AWS region (optional)")
    p.add_argument("--use-ssl", action="store_true", default=False, help="Use SSL for OpenSearch (default: False)")
    p.add_argument("--verify-certs", action="store_true", default=False, help="Verify SSL certs (default: False)")

    p.add_argument(
        "--openai-api-key",
        help="OpenAI API key for embeddings (defaults to env OPENAI_API_KEY)",
    )
    p.add_argument(
        "--llm-api-key",
        help="OpenAI API key for LLM signature+summary (defaults to --openai-api-key, then env OPENAI_API_KEY)",
    )
    p.add_argument(
        "--llm-model",
        "--openai-model",
        dest="llm_model",
        default=os.getenv("OPENAI_MODEL") or "gpt-4o-mini",
        help="LLM model for signature+summary (default: env OPENAI_MODEL or gpt-4o-mini)",
    )
    p.add_argument("--llm-concurrency", type=int, default=16, help="Max parallel LLM calls (default: 16)")

    p.add_argument("--embedding-model", default="text-embedding-3-small", help="Embedding model")
    p.add_argument("--embedding-batch-size", type=int, default=100, help="Embedding batch size (default: 100)")
    p.add_argument("--use-azure-embeddings", action="store_true", help="Use Azure OpenAI Embeddings service (requires config.ini)")
    p.add_argument("--azure-cert-path", help="Path to Azure certificate file (.pem)")
    p.add_argument("--azure-config-path", help="Path to config.ini file for Azure embeddings (default: script directory)")

    p.add_argument(
        "--chunking-strategy",
        default="class_metadata",
        choices=["method_only", "class_metadata", "recursive", "sliding_window", "hybrid"],
        help="Chunking strategy (default: class_metadata)",
    )
    p.add_argument("--max-chunk-size", type=int, default=1000, help="Max chunk size in characters (default: 1000)")
    p.add_argument("--enforce-chunk-size", action="store_true", default=True, help="Enforce chunk size (default: True)")
    p.add_argument("--chunk-overlap-size", type=int, default=50, help="Overlap size for sliding_window strategy")

    # Used to create project_id (and included in lookup_hash payload)
    p.add_argument("--application-name", help="Application name (optional; used in lookup_hash project_id)")
    p.add_argument("--seal-id", help="Seal ID (optional; used in lookup_hash project_id)")
    p.add_argument("--skip-llm", action="store_true", help="Skip LLM signature+summary+lookup_hash generation")
    p.add_argument("--skip-embeddings", action="store_true", help="Skip embeddings generation")

    args = p.parse_args()

    # Resolve keys:
    embedding_openai_api_key = None if args.skip_embeddings else (args.openai_api_key or os.getenv("OPENAI_API_KEY"))
    llm_api_key = None if args.skip_llm else (args.llm_api_key or args.openai_api_key or os.getenv("OPENAI_API_KEY"))
    if args.file and not llm_api_key:
        # Single-file convenience: allow chunk JSON generation without LLM
        args.skip_llm = True
    if args.repo_path and not llm_api_key and not args.skip_llm:
        raise SystemExit(
            "❌ Missing OpenAI API key for LLM calls. Provide --llm-api-key (or --openai-api-key) "
            "or set OPENAI_API_KEY in the environment, or pass --skip-llm."
        )

    if args.file:
        # Single file mode: parse + chunk + write JSON
        indexer = StandaloneIndexer(
            openai_api_key=embedding_openai_api_key,
            embedding_model=args.embedding_model,
            chunking_strategy=args.chunking_strategy,
            max_chunk_size=args.max_chunk_size,
            enforce_chunk_size=args.enforce_chunk_size,
            chunk_overlap_size=args.chunk_overlap_size,
            batch_size=args.embedding_batch_size,
            application_name=args.application_name,
            seal_id=args.seal_id,
            use_azure_embeddings=args.use_azure_embeddings,
            azure_cert_path=args.azure_cert_path,
            azure_config_path=args.azure_config_path,
        )
        parsed = indexer.parser.parse_file(args.file)
        if not parsed:
            raise SystemExit(f"❌ Failed to parse file: {args.file}")
        chunks = indexer._generate_chunks_for_file(parsed, args.file)

        # Optionally run LLM + embeddings (same as repo mode, but on one file)
        if not args.skip_llm and llm_api_key:
            # Reuse the existing LLM enrichment by running a minimal pipeline in-memory
            # (We keep it simple: annotate all method/class chunks)
            project_id = indexer.project_id or f"{args.application_name or ''}:{args.seal_id or ''}".strip(":")
            annotator = LLMChunkAnnotator(api_key=llm_api_key, model=args.llm_model, max_concurrency=args.llm_concurrency)

            async def _annotate_chunk(c: Dict[str, Any]) -> None:
                full_code = c.get("code", "") or ""
                if c.get("type") == "method":
                    res = await annotator.annotate_method(
                        language=c.get("language", "unknown"),
                        fqn=c.get("fqn", ""),
                        ast_signature_guess="",
                        full_method_code=full_code,
                    )
                    sig = res.signature or c.get("fqn", "")
                    c["summary"] = res.summary or c.get("summary", "")
                    if project_id:
                        c["lookup_hash"] = _build_lookup_hash(project_id, sig, full_code)
                elif c.get("type") == "class":
                    res = await annotator.annotate_class(
                        language=c.get("language", "unknown"),
                        fqn=c.get("fqn", ""),
                        class_code=full_code,
                        method_summaries=[],
                    )
                    sig = res.signature or c.get("fqn", "")
                    c["summary"] = res.summary or c.get("summary", "")
                    if project_id:
                        c["lookup_hash"] = _build_lookup_hash(project_id, sig, full_code)

            await asyncio.gather(*[_annotate_chunk(c) for c in chunks])

        if not args.skip_embeddings:
            texts = [_embedding_text_for_chunk(c) for c in chunks]
            embeddings = await indexer.generate_embeddings_batch(texts)
            for c, emb in zip(chunks, embeddings):
                if emb:
                    c["embedding"] = emb

        out = Path(args.output)
        out.parent.mkdir(parents=True, exist_ok=True)
        with open(out, "w", encoding="utf-8") as f:
            json.dump(
                {
                    "file_path": args.file,
                    "language": parsed.get("language", "unknown"),
                    "chunking_strategy": args.chunking_strategy,
                    "total_chunks": len(chunks),
                    "chunks": chunks,
                },
                f,
                indent=2,
                ensure_ascii=False,
            )
        print(f"✅ Wrote {len(chunks)} chunks to {out}")
        return

    stats = await run_pipeline(
        repo_path=args.repo_path,
        output_dir=args.output_dir,
        opensearch_host=args.opensearch_host,
        opensearch_index=args.opensearch_index,
        opensearch_config_path=args.opensearch_config,
        llm_api_key=llm_api_key or "",
        embedding_openai_api_key=embedding_openai_api_key,
        llm_model=args.llm_model,
        embedding_model=args.embedding_model,
        chunking_strategy=args.chunking_strategy,
        max_chunk_size=args.max_chunk_size,
        enforce_chunk_size=args.enforce_chunk_size,
        chunk_overlap_size=args.chunk_overlap_size,
        embedding_batch_size=args.embedding_batch_size,
        llm_concurrency=args.llm_concurrency,
        opensearch_batch_size=args.opensearch_batch_size,
        opensearch_workers=args.opensearch_workers,
        use_aws_auth=args.use_aws_auth,
        region=args.region,
        use_ssl=args.use_ssl,
        verify_certs=args.verify_certs,
        application_name=args.application_name,
        seal_id=args.seal_id,
        use_azure_embeddings=args.use_azure_embeddings,
        azure_cert_path=args.azure_cert_path,
        azure_config_path=args.azure_config_path,
    )

    print("\n✅ Done")
    print(json.dumps(stats, indent=2))


if __name__ == "__main__":
    asyncio.run(main())

