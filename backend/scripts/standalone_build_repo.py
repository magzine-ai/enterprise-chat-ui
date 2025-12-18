"""
Standalone helper to:
1) Register or reuse a repository (local path or GitHub URL).
2) Index files into DB and OpenSearch (chunks with embeddings).
3) Build and persist the NetworkX knowledge graph.

Usage:
  PYTHONPATH=. python scripts/standalone_build_repo.py \
    --name hystrix \
    --path /absolute/path/to/hystrix \
    --rebuild-graph

Options:
  --name            Repository name (required)
  --path            Local repository path (required unless --github-url is set)
  --github-url      GitHub URL (optional alternative to --path)
  --github-branch   Branch to clone (default: main)
  --full            Do full reindex (non-incremental). Default incremental.
  --rebuild-graph   Clear existing graph for this repo before rebuild.

Notes:
  - Respects settings in app.core.config (OpenSearch, data dirs, etc.).
  - Writes saved graph pickle to data/graphs/graph_repo_<id>.pkl.
  - Requires OpenSearch running if java_opensearch_enabled = True.
"""

import argparse
import asyncio
from sqlmodel import Session

from app.core.config import settings
from app.core.database import engine
from app.services.repository_manager import repository_manager
from app.services.graph_service import graph_service


async def main():
    parser = argparse.ArgumentParser(description="Standalone repository index + graph build")
    parser.add_argument("--name", required=True, help="Repository name")
    parser.add_argument("--path", help="Local repo path")
    parser.add_argument("--github-url", help="GitHub repository URL (optional)")
    parser.add_argument("--github-branch", default="main", help="GitHub branch (default: main)")
    parser.add_argument("--full", action="store_true", help="Do full reindex (non-incremental)")
    parser.add_argument("--rebuild-graph", action="store_true", help="Clear existing graph for this repo")
    args = parser.parse_args()

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

