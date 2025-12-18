"""
Standalone helper to:
1) Register or reuse a repository (local path or GitHub URL).
2) Index files into DB and OpenSearch (chunks with embeddings).
3) Build and persist the NetworkX knowledge graph.
4) Generate chunks as JSON for a specific file (without indexing).

Usage (Full Repository Indexing):
  PYTHONPATH=. python scripts/standalone_build_repo.py \
    --name hystrix \
    --path /absolute/path/to/hystrix \
    --rebuild-graph

Usage (Generate Chunks for Single File):
  PYTHONPATH=. python scripts/standalone_build_repo.py \
    --file /absolute/path/to/file.java \
    --output chunks.json \
    --chunking-strategy class_metadata

Options:
  --name            Repository name (required for full indexing)
  --path            Local repository path (required unless --github-url is set)
  --github-url      GitHub URL (optional alternative to --path)
  --github-branch   Branch to clone (default: main)
  --full            Do full reindex (non-incremental). Default incremental.
  --rebuild-graph   Clear existing graph for this repo before rebuild.
  
  --file            Path to a specific file to generate chunks for (single file mode)
  --output          Output JSON file path (default: chunks.json)
  --chunking-strategy  Chunking strategy: method_only, class_metadata, recursive, sliding_window, hybrid (default: class_metadata)
  --max-chunk-size  Maximum chunk size in characters (default: 1000)
  --enforce-size    Enforce chunk size limits (default: True)

Notes:
  - Respects settings in app.core.config (OpenSearch, data dirs, etc.).
  - Writes saved graph pickle to data/graphs/graph_repo_<id>.pkl.
  - Requires OpenSearch running if java_opensearch_enabled = True.
  - Single file mode (--file) does not require database or OpenSearch.
"""

import argparse
import asyncio
import json
from pathlib import Path
from sqlmodel import Session

from app.core.config import settings
from app.core.database import engine
from app.services.repository_manager import repository_manager
from app.services.graph_service import graph_service
from app.services.java_indexer_service import java_indexer_service


async def generate_chunks_for_file(
    file_path: str,
    output_path: str,
    chunking_strategy: str = "class_metadata",
    max_chunk_size: int = 1000,
    enforce_size: bool = True
):
    """
    Generate chunks for a single file and save to JSON.
    
    Args:
        file_path: Path to the file to process
        output_path: Output JSON file path
        chunking_strategy: Chunking strategy to use
        max_chunk_size: Maximum chunk size in characters
        enforce_size: Whether to enforce chunk size limits
    """
    file_path_obj = Path(file_path)
    if not file_path_obj.exists():
        raise SystemExit(f"❌ File not found: {file_path}")
    
    print(f"📄 Processing file: {file_path}")
    print(f"   Strategy: {chunking_strategy}")
    print(f"   Max chunk size: {max_chunk_size}")
    print(f"   Enforce size: {enforce_size}")
    
    # Update config for chunking strategy
    original_strategy = settings.java_chunking_strategy
    original_max_size = settings.java_max_chunk_size
    original_enforce = settings.java_enforce_chunk_size
    
    settings.java_chunking_strategy = chunking_strategy
    settings.java_max_chunk_size = max_chunk_size
    settings.java_enforce_chunk_size = enforce_size
    
    try:
        # Detect language
        language = java_indexer_service.detect_language(str(file_path))
        print(f"   Detected language: {language}")
        
        # Parse file
        parsed_data = java_indexer_service.parse_file(str(file_path), language)
        if not parsed_data:
            raise SystemExit(f"❌ Failed to parse file: {file_path}")
        
        # Read file content
        with open(file_path, 'r', encoding='utf-8', errors='ignore') as f:
            file_content = f.read()
        
        print(f"   File size: {len(file_content)} characters")
        print(f"   Classes found: {len(parsed_data.get('classes', []))}")
        print(f"   Methods found: {len(parsed_data.get('methods', []))}")
        
        # Generate chunks (using repository_id=0 for standalone mode)
        chunks = java_indexer_service.generate_chunks(
            parsed_data,
            file_content,
            repository_id=0,  # Not used in standalone mode
            language=language
        )
        
        print(f"✅ Generated {len(chunks)} chunks")
        
        # Prepare output data
        output_data = {
            "file_path": str(file_path),
            "language": language,
            "chunking_strategy": chunking_strategy,
            "max_chunk_size": max_chunk_size,
            "enforce_size": enforce_size,
            "total_chunks": len(chunks),
            "chunks": []
        }
        
        # Convert chunks to JSON-serializable format
        for chunk in chunks:
            # Handle chunk type (could be ChunkType enum or string)
            chunk_type = chunk.get('type', 'unknown')
            if hasattr(chunk_type, 'value'):
                chunk_type_str = chunk_type.value
            else:
                chunk_type_str = str(chunk_type)
            
            chunk_data = {
                "type": chunk_type_str,
                "fqn": chunk.get('fqn', ''),
                "file_path": chunk.get('file_path', str(file_path)),
                "start_line": chunk.get('start_line', 1),
                "end_line": chunk.get('end_line', 1),
                "code": chunk.get('code', ''),
                "summary": chunk.get('summary', ''),
                "code_size": len(chunk.get('code', '')),
                "imports": chunk.get('imports', []),
                "annotations": chunk.get('annotations', []),
            }
            
            # Add type-specific fields
            chunk_type_lower = chunk_type_str.lower()
            if chunk_type_lower == 'class':
                chunk_data["extended_class"] = chunk.get('extended_class')
                chunk_data["implemented_interfaces"] = chunk.get('implemented_interfaces', [])
                chunk_data["method_count"] = chunk.get('method_count', 0)
                chunk_data["method_fqns"] = chunk.get('method_fqns', [])
            elif chunk_type_lower == 'method':
                chunk_data["callers"] = chunk.get('callers', [])
                chunk_data["callees"] = chunk.get('callees', [])
            
            output_data["chunks"].append(chunk_data)
        
        # Save to JSON file
        output_path_obj = Path(output_path)
        output_path_obj.parent.mkdir(parents=True, exist_ok=True)
        
        with open(output_path_obj, 'w', encoding='utf-8') as f:
            json.dump(output_data, f, indent=2, ensure_ascii=False)
        
        print(f"✅ Chunks saved to: {output_path}")
        print(f"   Total chunks: {len(chunks)}")
        print(f"   Chunk types: {dict((c.get('type'), sum(1 for ch in chunks if ch.get('type') == c.get('type'))) for c in chunks)}")
        
        # Print chunk statistics
        if chunks:
            chunk_sizes = [len(c.get('code', '')) for c in chunks]
            avg_size = sum(chunk_sizes) / len(chunk_sizes)
            max_size = max(chunk_sizes)
            min_size = min(chunk_sizes)
            print(f"   Chunk sizes: min={min_size}, avg={avg_size:.0f}, max={max_size}")
        
    finally:
        # Restore original config
        settings.java_chunking_strategy = original_strategy
        settings.java_max_chunk_size = original_max_size
        settings.java_enforce_chunk_size = original_enforce


async def main():
    parser = argparse.ArgumentParser(description="Standalone repository index + graph build or single file chunk generation")
    
    # Single file mode arguments
    parser.add_argument("--file", help="Path to a specific file to generate chunks for (single file mode)")
    parser.add_argument("--output", default="chunks.json", help="Output JSON file path (default: chunks.json)")
    parser.add_argument(
        "--chunking-strategy",
        default="class_metadata",
        choices=["method_only", "class_metadata", "recursive", "sliding_window", "hybrid"],
        help="Chunking strategy (default: class_metadata)"
    )
    parser.add_argument("--max-chunk-size", type=int, default=1000, help="Maximum chunk size in characters (default: 1000)")
    parser.add_argument("--enforce-size", action="store_true", default=True, help="Enforce chunk size limits (default: True)")
    
    # Full repository indexing arguments
    parser.add_argument("--name", help="Repository name (required for full indexing)")
    parser.add_argument("--path", help="Local repo path")
    parser.add_argument("--github-url", help="GitHub repository URL (optional)")
    parser.add_argument("--github-branch", default="main", help="GitHub branch (default: main)")
    parser.add_argument("--full", action="store_true", help="Do full reindex (non-incremental)")
    parser.add_argument("--rebuild-graph", action="store_true", help="Clear existing graph for this repo")
    
    args = parser.parse_args()

    # Single file mode
    if args.file:
        await generate_chunks_for_file(
            file_path=args.file,
            output_path=args.output,
            chunking_strategy=args.chunking_strategy,
            max_chunk_size=args.max_chunk_size,
            enforce_size=args.enforce_size
        )
        return

    # Full repository indexing mode
    if not args.name:
        raise SystemExit("❌ Either --file (single file mode) or --name (full indexing mode) is required.")
    
    if not args.path and not args.github_url:
        raise SystemExit("Either --path or --github-url is required.")
    if args.path and args.github_url:
        raise SystemExit("Use only one of --path or --github-url.")

    with Session(engine) as session:
        # Register or reuse repository
        repo = repository_manager.register_repository(
            session=session,
            name=args.name,
            local_path=args.path,
            github_url=args.github_url,
            github_branch=args.github_branch,
            description=f"Standalone import: {args.name}",
        )
        print(f"📁 Repository id={repo.id}, path={repo.local_path}")

        # Index repository (chunks + embeddings + OpenSearch docs)
        print("🔎 Indexing repository...")
        stats = await repository_manager.index_repository(
            session=session,
            repository=repo,
            incremental=not args.full,
        )
        print(f"✅ Indexing done: {stats}")

        # Build knowledge graph
        print("🧠 Building graph...")
        success = graph_service.build_graph_from_chunks(
            session=session,
            repository_id=repo.id,
            rebuild=args.rebuild_graph,
        )
        if not success:
            raise SystemExit("Graph build failed.")

        # Persist graph
        saved = graph_service.save_graph(repo.id)
        stats = graph_service.get_graph_stats(repository_id=repo.id)
        print(f"✅ Graph saved={saved}, stats={stats}")


if __name__ == "__main__":
    asyncio.run(main())

