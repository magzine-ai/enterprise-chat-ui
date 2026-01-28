"""
Standalone Java repository indexer for OpenSearch.

Features:
- Parse a Java repo from a filesystem path
- Show directory / file statistics
- Chunk code into:
  - method chunks (type="method")
  - class chunks (type="class")
- Enrich each chunk with:
  - lookup_hash = sha256(project:seal_id:signature:fqn)  (methods)
  - lookup_hash = sha256(project:seal_id:class_decl:fqn) (classes)
  - simple summary string
- Push chunks to OpenSearch
- Parallel file processing with progress via tqdm

Usage example:

  python standalone_java_repo_indexer.py \\
    --repo-path /path/to/java/repo \\
    --config-path ./config.ini \\
    --max-workers 8

config.ini example (similar to standalone_build_repo_independent.py):

  [aws_info]
  opensearch_endpoint = localhost:9200
  index_name = java_code_chunks

  [application]
  application_name = my-app
  seal_id = 12345

  [azure_openai]
  azure_tenant_id = YOUR_TENANT_ID
  azure_client_id = YOUR_CLIENT_ID
  azure_endpoint = https://llm-multitenancy-exp.jpmchase.net/ver2/
  openai_api_key = YOUR_API_KEY
  openai_api_version = 2024-10-21
  deployment_name = gpt-4
"""

import argparse
import configparser
import hashlib
import json
import os
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import javalang  # type: ignore
from opensearchpy import OpenSearch  # type: ignore
from tqdm import tqdm  # type: ignore

try:
    from azure.identity import CertificateCredential  # type: ignore
    from langchain_openai import AzureChatOpenAI, AzureOpenAIEmbeddings  # type: ignore

    AZURE_LLM_AVAILABLE = True
except ImportError:
    AZURE_LLM_AVAILABLE = False


# ------------------------- Models & helpers ------------------------- #


@dataclass
class JavaMethodChunk:
    type: str
    fqn: str
    file_path: str
    start_line: int
    end_line: int
    chunk_length: int
    code: str
    summary: str
    lookup_hash: str


@dataclass
class JavaClassChunk:
    type: str
    fqn: str
    file_path: str
    start_line: int
    end_line: int
    chunk_length: int
    code: str
    summary: str
    lookup_hash: str


def sha256_hex(s: str) -> str:
    return hashlib.sha256(s.encode("utf-8", errors="ignore")).hexdigest()


def build_method_signature(method: javalang.tree.MethodDeclaration) -> str:
    """Return a compact Java method signature string."""
    mods = " ".join(sorted(method.modifiers)) if getattr(method, "modifiers", None) else ""
    ret_type = str(method.return_type) if getattr(method, "return_type", None) else "void"
    params: List[str] = []
    for p in getattr(method, "parameters", []) or []:
        p_type = str(getattr(p, "type", "") or "")
        p_name = getattr(p, "name", "") or ""
        params.append(f"{p_type} {p_name}".strip())
    params_str = ", ".join(params)
    parts = [mods.strip(), ret_type, method.name]
    parts = [p for p in parts if p]
    return " ".join(parts) + f"({params_str})"


def build_class_declaration(cls: javalang.tree.ClassDeclaration) -> str:
    """Return a compact Java class declaration: modifiers + class + name + extends/implements."""
    mods = " ".join(sorted(cls.modifiers)) if getattr(cls, "modifiers", None) else ""
    name = cls.name
    extends = ""
    if getattr(cls, "extends", None):
        extends = f" extends {cls.extends.name}"
    implements = ""
    if getattr(cls, "implements", None):
        impl_names = [str(i.name) for i in cls.implements]
        if impl_names:
            implements = " implements " + ", ".join(impl_names)
    parts = [mods.strip(), "class", name]
    decl = " ".join([p for p in parts if p])
    return f"{decl}{extends}{implements}".strip()


def hash_for_method(project_id: str, signature: str, fqn: str) -> str:
    key = f"{project_id}:{signature}:{fqn}"
    return sha256_hex(key)


def hash_for_class(project_id: str, class_decl: str, fqn: str) -> str:
    key = f"{project_id}:{class_decl}:{fqn}"
    return sha256_hex(key)


# ------------------------- Java parsing & chunking ------------------------- #


def find_java_files(repo_path: str) -> List[Path]:
    root = Path(repo_path)
    exclude = {".git", "target", "build", "out", ".idea", ".vscode"}
    files: List[Path] = []
    for path in root.rglob("*.java"):
        if any(part in exclude for part in path.parts):
            continue
        files.append(path)
    return files


def _get_package(tree: javalang.tree.CompilationUnit) -> str:
    pkg = getattr(tree, "package", None)
    return pkg.name if pkg and getattr(pkg, "name", None) else ""


def _extract_code_span(content: str, start_line: int, end_line: int) -> str:
    lines = content.splitlines()
    start = max(1, start_line)
    end = min(len(lines), end_line)
    return "\n".join(lines[start - 1 : end])


def _find_method_body_end_line(content: str, start_line: int) -> int:
    """Find the 1-based line number of the closing brace of the method body starting at start_line.
    Uses brace matching so multiline methods are handled correctly. Falls back to last line if not found.
    """
    lines = content.splitlines()
    if start_line < 1 or start_line > len(lines):
        return len(lines)
    # Character offset of the start of line start_line (1-based)
    pos = 0
    for _ in range(start_line - 1):
        pos = content.find("\n", pos)
        if pos == -1:
            break
        pos += 1
    start_offset = pos
    rest = content[start_offset:]
    brace_open = rest.find("{")
    if brace_open == -1:
        return len(lines)
    # Brace matching from the opening {
    depth = 0
    in_string = None
    escape = False
    i = 0
    while i < len(rest):
        c = rest[i]
        if escape:
            escape = False
            i += 1
            continue
        if c == "\\" and in_string:
            escape = True
            i += 1
            continue
        if in_string:
            if c == in_string:
                in_string = None
            i += 1
            continue
        if c in ('"', "'"):
            in_string = c
            i += 1
            continue
        if c == "{":
            depth += 1
            i += 1
            continue
        if c == "}":
            depth -= 1
            if depth == 0:
                end_char = start_offset + i
                return content[: end_char + 1].count("\n") + 1
            i += 1
            continue
        i += 1
    return len(lines)


def _enrich_class_with_llm(
    llm_client: Any,
    class_code: str,
    fqn_class: str,
    methods: List[javalang.tree.MethodDeclaration],
) -> Tuple[Optional[str], Optional[str], Dict[str, Dict[str, str]]]:
    """Call LLM once per class to get class declaration/summary and per-method signatures/summaries.

    Returns:
        (class_decl, class_summary, method_meta_by_name)
        where method_meta_by_name[name] = {"signature": str, "summary": str}
    """
    if not AZURE_LLM_AVAILABLE or llm_client is None:
        return None, None, {}

    method_names = [m.name for m in methods or []]
    prompt = f"""
You are a Java code analysis assistant.

Given the full source of a single Java class, extract:
1. \"class_declaration\": the full Java class declaration line, including modifiers, \"class\" keyword, name, and any extends/implements clauses.
2. \"class_summary\": one concise sentence (max 40 words) summarizing the purpose of this class.
3. \"methods\": an array where each item has:
   - \"name\": method name
   - \"signature\": full Java method signature including modifiers, return type, name and parameter types/names
   - \"summary\": one concise sentence (max 30 words) describing what the method does.

Only include methods whose names are in this list: {method_names}.

Return ONLY a single valid JSON object with keys: \"class_declaration\", \"class_summary\", \"methods\".
Do NOT include any markdown, backticks, comments, or extra text.

Java class FQN: {fqn_class}

Java class source:
{class_code}
"""
    try:
        response = llm_client.invoke(prompt)
        # AzureChatOpenAI returns an AIMessage; content may be str or list
        content = getattr(response, "content", response)
        if isinstance(content, list):
            # Newer langchain messages can be list[ContentChunk]; join text parts
            text_parts = [getattr(c, "text", "") or getattr(c, "content", "") for c in content]
            content_str = "".join(text_parts)
        else:
            content_str = str(content)

        data = json.loads(content_str)
        class_decl = data.get("class_declaration")
        class_summary = data.get("class_summary")
        method_meta: Dict[str, Dict[str, str]] = {}
        for m in data.get("methods", []) or []:
            name = m.get("name")
            if not name:
                continue
            method_meta[name] = {
                "signature": m.get("signature", ""),
                "summary": m.get("summary", ""),
            }
        return class_decl, class_summary, method_meta
    except Exception as e:
        print(f"⚠️ LLM enrichment failed for class {fqn_class}: {e}")
        return None, None, {}


def parse_java_file(
    file_path: Path,
    project_id: str,
    llm_client: Optional[Any] = None,
) -> Tuple[List[JavaMethodChunk], List[JavaClassChunk]]:
    text = file_path.read_text(encoding="utf-8", errors="ignore")
    try:
        tree = javalang.parse.parse(text)
    except Exception:
        return [], []

    pkg = _get_package(tree)
    methods: List[JavaMethodChunk] = []
    classes: List[JavaClassChunk] = []

    for type_decl in tree.types or []:
        if not isinstance(type_decl, javalang.tree.ClassDeclaration):
            continue

        class_decl_ast = build_class_declaration(type_decl)
        class_name = type_decl.name
        fqn_class = f"{pkg}.{class_name}".strip(".")

        # Approximate class span: from class keyword to closing brace
        # If javalang position unavailable, use whole file.
        class_start_line = 1
        if getattr(type_decl, "position", None) and type_decl.position.line:
            class_start_line = type_decl.position.line
        class_end_line = len(text.splitlines())

        class_code = _extract_code_span(text, class_start_line, class_end_line)

        # Optional LLM enrichment (one call per class)
        llm_class_decl: Optional[str] = None
        llm_class_summary: Optional[str] = None
        llm_methods_meta: Dict[str, Dict[str, str]] = {}
        if llm_client is not None and AZURE_LLM_AVAILABLE:
            llm_class_decl, llm_class_summary, llm_methods_meta = _enrich_class_with_llm(
                llm_client=llm_client,
                class_code=class_code,
                fqn_class=fqn_class,
                methods=type_decl.methods or [],
            )

        final_class_decl = llm_class_decl or class_decl_ast
        class_summary = llm_class_summary or f"Class {fqn_class}"

        class_lookup = hash_for_class(project_id, final_class_decl, fqn_class)
        classes.append(
            JavaClassChunk(
                type="class",
                fqn=fqn_class,
                file_path=str(file_path),
                start_line=class_start_line,
                end_line=class_end_line,
                chunk_length=max(0, class_end_line - class_start_line + 1),
                code=class_code,
                summary=class_summary,
                lookup_hash=class_lookup,
            )
        )

        # Methods for this class
        for method in type_decl.methods or []:
            sig_ast = build_method_signature(method)
            fqn_method = f"{fqn_class}.{method.name}"

            m_start = getattr(method, "position", None).line if getattr(method, "position", None) else 1
            # Use brace matching so multiline method bodies get correct end_line (not "to end of file").
            m_end = _find_method_body_end_line(text, m_start)
            method_code = _extract_code_span(text, m_start, m_end)
            # Prefer LLM-derived signature/summary if available
            llm_meta = llm_methods_meta.get(method.name, {}) if llm_methods_meta else {}
            sig_final = llm_meta.get("signature") or sig_ast
            method_summary = llm_meta.get("summary") or f"Method {fqn_method}"
            m_lookup = hash_for_method(project_id, sig_final, fqn_method)

            methods.append(
                JavaMethodChunk(
                    type="method",
                    fqn=fqn_method,
                    file_path=str(file_path),
                    start_line=m_start,
                    end_line=m_end,
                    chunk_length=max(0, m_end - m_start + 1),
                    code=method_code,
                    summary=method_summary,
                    lookup_hash=m_lookup,
                )
            )

    return methods, classes


def process_file_worker(args: Tuple[Path, str, Optional[Any]]) -> List[Dict[str, Any]]:
    file_path, project_id, llm_client = args
    method_chunks, class_chunks = parse_java_file(file_path, project_id, llm_client=llm_client)
    result: List[Dict[str, Any]] = []
    for ch in method_chunks:
        result.append(
            {
                "type": ch.type,
                "fqn": ch.fqn,
                "file_path": ch.file_path,
                "start_line": ch.start_line,
                "end_line": ch.end_line,
                "chunk_length": ch.chunk_length,
                "code": ch.code,
                "summary": ch.summary,
                "lookup_hash": ch.lookup_hash,
            }
        )
    for ch in class_chunks:
        result.append(
            {
                "type": ch.type,
                "fqn": ch.fqn,
                "file_path": ch.file_path,
                "start_line": ch.start_line,
                "end_line": ch.end_line,
                "chunk_length": ch.chunk_length,
                "code": ch.code,
                "summary": ch.summary,
                "lookup_hash": ch.lookup_hash,
            }
        )
    return result


# ------------------------- OpenSearch client ------------------------- #


class OSClient:
    def __init__(self, host: str, index: str):
        host_name, port = (host.split(":") + ["9200"])[:2]
        self.index = index
        self.client = OpenSearch(
            hosts=[{"host": host_name, "port": int(port)}],
            use_ssl=False,
            verify_certs=False,
        )

    def ensure_index(self, embedding_dim: Optional[int] = None) -> None:
        if self.client.indices.exists(index=self.index):
            return
        mapping = {
            "mappings": {
                "properties": {
                    "chunk_id": {"type": "keyword"},
                    "type": {"type": "keyword"},
                    "fqn": {"type": "text", "fields": {"keyword": {"type": "keyword", "ignore_above": 256}}},
                    "file_path": {"type": "keyword"},
                    "start_line": {"type": "integer"},
                    "end_line": {"type": "integer"},
                    "chunk_length": {"type": "integer"},
                    "code": {"type": "text"},
                    "summary": {"type": "text"},
                    "lookup_hash": {"type": "keyword"},
                }
            }
        }
        # Add vector field if we know the embedding dimension
        if embedding_dim:
            mapping["mappings"]["properties"]["embedding"] = {
                "type": "dense_vector",
                "dims": embedding_dim,
                "index": True,
                "similarity": "cosine",
            }
        self.client.indices.create(index=self.index, body=mapping)

    def bulk_index(self, chunks: List[Dict[str, Any]]) -> None:
        if not chunks:
            return
        # Infer embedding dimension from first chunk that has an embedding
        embedding_dim: Optional[int] = None
        for ch in chunks:
            emb = ch.get("embedding")
            if isinstance(emb, list) and emb:
                embedding_dim = len(emb)
                break

        self.ensure_index(embedding_dim=embedding_dim)
        body: List[Dict[str, Any]] = []
        for i, ch in enumerate(chunks):
            chunk_id = f"chunk_{i}"
            action = {"index": {"_index": self.index, "_id": chunk_id}}
            doc = {
                "chunk_id": chunk_id,
                **ch,
            }
            body.extend([action, doc])
        self.client.bulk(body=body)


# ------------------------- Main pipeline ------------------------- #


def run(
    repo_path: str,
    application_name: str,
    seal_id: str,
    opensearch_host: str,
    opensearch_index: str,
    max_workers: int,
) -> None:
    repo = Path(repo_path)
    if not repo.is_dir():
        raise SystemExit(f"❌ Repo path not found or not a directory: {repo_path}")

    project_id = f"{application_name}:{seal_id}"
    java_files = find_java_files(repo_path)

    if not java_files:
        print("⚠️ No Java files found.")
        return

    print(f"📁 Repository: {repo_path}")
    print(f"   Java files: {len(java_files)}")
    print(f"   Application: {application_name}")
    print(f"   Seal ID: {seal_id}")

    all_chunks: List[Dict[str, Any]] = []

    # Initialize LLM and embedding clients (optional). If Azure deps/config aren't
    # available, these remain None and the pipeline still runs (no LLM, no embeddings).
    llm_client: Optional[Any] = None
    embeddings_client: Optional[AzureOpenAIEmbeddings] = None
    if AZURE_LLM_AVAILABLE:
        try:
            # Reuse azure_openai section from config.ini if present
            config_path = os.path.join(os.path.dirname(__file__), "config.ini")
            if os.path.exists(config_path):
                cfg = configparser.ConfigParser()
                cfg.read(config_path)
                if "azure_openai" in cfg:
                    azure_cfg = cfg["azure_openai"]
                    tenant_id = azure_cfg.get("azure_tenant_id")
                    client_id = azure_cfg.get("azure_client_id")
                    azure_endpoint = azure_cfg.get(
                        "azure_endpoint", "https://llm-multitenancy-exp.jpmchase.net/ver2/"
                    )
                    openai_api_key = azure_cfg.get("openai_api_key", "")
                    api_version = azure_cfg.get("openai_api_version", "2024-10-21")
                    deployment_name = azure_cfg.get("deployment_name", "gpt-4")
                    if tenant_id and client_id:
                        current_dir = os.path.dirname(__file__)
                        cert_path = os.path.join(
                            current_dir, "..", "..", "discoveryeng.dev.azure.jpmchase.net.pem"
                        )
                        if not os.path.exists(cert_path):
                            alt_paths = [
                                os.path.join(current_dir, "discoveryeng.dev.azure.jpmchase.net.pem"),
                                os.path.join(os.path.dirname(current_dir), "discoveryeng.dev.azure.jpmchase.net.pem"),
                            ]
                            for alt in alt_paths:
                                if os.path.exists(alt):
                                    cert_path = alt
                                    break
                        credential = CertificateCredential(
                            tenant_id=tenant_id,
                            client_id=client_id,
                            certificate_path=cert_path,
                        )
                        access_token = credential.get_token(
                            "https://cognitiveservices.azure.com/.default"
                        ).token

                        # Chat client for class/method enrichment
                        llm_client = AzureChatOpenAI(
                            azure_endpoint=azure_endpoint,
                            openai_api_version=api_version,
                            deployment_name=deployment_name,
                            openai_api_key=openai_api_key,
                            openai_api_type="azure",
                            max_tokens=int(azure_cfg.get("max_tokens", "1024")),
                            temperature=float(azure_cfg.get("temperature", "0.2")),
                            default_headers={
                                "Authorization": f"Bearer {access_token}",
                                "user_sid": "standalone_java_repo_indexer",
                            },
                        )
                        print("✅ LLM client initialized for class/method enrichment")

                        # Embeddings client for chunk vectors
                        embeddings_client = AzureOpenAIEmbeddings(
                            azure_endpoint=azure_endpoint,
                            openai_api_version=api_version,
                            openai_api_key=openai_api_key,
                            openai_api_type="azure",
                            default_headers={
                                "Authorization": f"Bearer {access_token}",
                                "user_sid": "standalone_java_repo_indexer",
                            },
                        )
                        print("✅ Embeddings client initialized for chunk embeddings")
        except Exception as e:
            print(f"⚠️ Failed to initialize Azure LLM/embeddings, continuing without them: {e}")

    with ThreadPoolExecutor(max_workers=max_workers) as executor:
        futures = {
            executor.submit(process_file_worker, (path, project_id, llm_client)): path
            for path in java_files
        }
        for fut in tqdm(as_completed(futures), total=len(futures), desc="Chunking files"):
            chunks = fut.result()
            all_chunks.extend(chunks)

    print(f"✅ Total chunks generated: {len(all_chunks)}")
    by_type: Dict[str, int] = {}
    for ch in all_chunks:
        by_type[ch["type"]] = by_type.get(ch["type"], 0) + 1
    print(f"   Chunks by type: {by_type}")

    # Generate embeddings (if embeddings_client available)
    if embeddings_client and all_chunks:
        print(f"📊 Generating embeddings for {len(all_chunks)} chunks...")
        for ch in tqdm(all_chunks, desc="Embedding chunks"):
            try:
                text = ch.get("code") or ch.get("summary", "")
                if not text:
                    continue
                ch["embedding"] = embeddings_client.embed_query(text)
            except Exception as e:
                print(f"⚠️ Failed to embed chunk {ch.get('fqn', 'unknown')}: {e}")

    # Index to OpenSearch
    os_client = OSClient(opensearch_host, opensearch_index)
    print(f"📤 Indexing chunks to OpenSearch index '{opensearch_index}'...")
    os_client.bulk_index(all_chunks)
    print("✅ Indexing complete.")


def main() -> None:
    parser = argparse.ArgumentParser(description="Standalone Java repo indexer for OpenSearch.")
    parser.add_argument("--repo-path", required=True, help="Path to Java repository")
    parser.add_argument("--application-name", help="Application name (for lookup_hash; can come from config.ini)")
    parser.add_argument("--seal-id", help="Seal ID (for lookup_hash; can come from config.ini)")
    parser.add_argument("--opensearch-host", help="OpenSearch host, e.g. localhost:9200 (can come from config.ini)")
    parser.add_argument("--opensearch-index", help="OpenSearch index name (can come from config.ini)")
    parser.add_argument(
        "--config-path",
        help="Path to config.ini (default: config.ini next to this script, using [aws_info] and [application] sections)",
    )
    parser.add_argument("--max-workers", type=int, default=os.cpu_count() or 4, help="Number of parallel workers")

    args = parser.parse_args()

    # Load configuration from config.ini (if present) to fill in missing values,
    # similar to standalone_build_repo_independent.py.
    config_path = args.config_path or os.path.join(os.path.dirname(__file__), "config.ini")
    if os.path.exists(config_path):
        cfg = configparser.ConfigParser()
        cfg.read(config_path)
        # OpenSearch settings from [aws_info]
        if "aws_info" in cfg:
            aws_info = cfg["aws_info"]
            if not args.opensearch_host:
                args.opensearch_host = aws_info.get("opensearch_endpoint", args.opensearch_host)
            if not args.opensearch_index:
                args.opensearch_index = aws_info.get("index_name", args.opensearch_index)
        # Application settings from [application]
        if "application" in cfg:
            app_cfg = cfg["application"]
            if not args.application_name:
                args.application_name = app_cfg.get("application_name", args.application_name)
            if not args.seal_id:
                args.seal_id = app_cfg.get("seal_id", args.seal_id)

    # Final validation
    missing: List[str] = []
    if not args.application_name:
        missing.append("application-name")
    if not args.seal_id:
        missing.append("seal-id")
    if not args.opensearch_host:
        missing.append("opensearch-host")
    if not args.opensearch_index:
        missing.append("opensearch-index")
    if missing:
        raise SystemExit(
            f"❌ Missing required settings: {', '.join(missing)}. "
            f"Provide them via CLI flags or config.ini ([application] and [aws_info] sections)."
        )

    run(
        repo_path=args.repo_path,
        application_name=args.application_name,
        seal_id=args.seal_id,
        opensearch_host=args.opensearch_host,
        opensearch_index=args.opensearch_index,
        max_workers=args.max_workers,
    )


if __name__ == "__main__":
    main()

