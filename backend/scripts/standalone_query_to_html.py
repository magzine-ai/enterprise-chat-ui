"""
Standalone helper to run a static query against existing chunks/graph and emit an HTML report
with metadata and a Mermaid graph snippet.

Prerequisites:
  - Repository already indexed and graphed (see standalone_build_repo.py).
  - OpenSearch reachable if java_opensearch_enabled = True.

Usage:
  PYTHONPATH=. python scripts/standalone_query_to_html.py \
    --query "who calls HystrixCommandDemo.startDemo" \
    --repo-id 2 \
    --output /tmp/hystrix_report.html \
    --max-results 8 \
    --graph-depth 2
"""

import argparse
import asyncio
import html
from typing import List, Dict, Any
from sqlmodel import Session

from app.core.database import engine
from app.services.java_search_service import java_search_service
from app.services.graph_service import graph_service


def mermaid_from_edges(nodes: List[Dict[str, Any]], edges: List[Dict[str, Any]]) -> str:
    """Generate a Mermaid flowchart snippet from nodes/edges."""
    node_lines = []
    for n in nodes:
        label = n.get("label") or n.get("fqn") or n.get("file_path") or n.get("id")
        short = html.escape(label.split(".")[-1][:40])
        node_lines.append(f'    {n["id"]}[{short}]')

    edge_lines = []
    for e in edges:
        rel = e.get("relationship", "rel")
        edge_lines.append(f'    {e["from"]} -->|{rel}| {e["to"]}')

    body = "\n".join(node_lines + edge_lines)
    return f"flowchart LR\n{body}"


def build_html(query: str, results: List[Dict[str, Any]], mermaid_snippet: str) -> str:
    rows = []
    for r in results:
        rows.append(f"""
        <tr>
          <td>{html.escape(str(r.get("score", "")))}</td>
          <td>{html.escape(r.get("fqn", '') or r.get("file_path", ''))}</td>
          <td>{html.escape(r.get("type", ''))}</td>
          <td>{html.escape(r.get("file_path", ''))}</td>
        </tr>
        """)

    return f"""
<!doctype html>
<html>
<head>
  <meta charset="utf-8"/>
  <title>Query Report</title>
  <script type="module">
    import mermaid from 'https://cdn.jsdelivr.net/npm/mermaid@10/dist/mermaid.esm.min.mjs';
    mermaid.initialize({{ startOnLoad: true }});
  </script>
  <style>
    body {{ font-family: Arial, sans-serif; margin: 24px; }}
    table {{ border-collapse: collapse; width: 100%; margin-top: 16px; }}
    th, td {{ border: 1px solid #ddd; padding: 8px; font-size: 13px; }}
    th {{ background: #f4f4f4; text-align: left; }}
    .mermaid {{ border: 1px solid #ddd; padding: 12px; border-radius: 6px; }}
  </style>
</head>
<body>
  <h2>Query</h2>
  <pre>{html.escape(query)}</pre>

  <h2>Top Results</h2>
  <table>
    <thead><tr><th>Score</th><th>FQN/Path</th><th>Type</th><th>File Path</th></tr></thead>
    <tbody>
      {''.join(rows)}
    </tbody>
  </table>

  <h2>Graph (Mermaid)</h2>
  <div class="mermaid">
{mermaid_snippet}
  </div>
</body>
</html>
"""


async def main():
    parser = argparse.ArgumentParser(description="Run static query and emit HTML with mermaid")
    parser.add_argument("--query", required=True, help="User query")
    parser.add_argument("--repo-id", type=int, required=True, help="Repository ID to scope search")
    parser.add_argument("--output", required=True, help="Output HTML path")
    parser.add_argument("--max-results", type=int, default=8, help="Max search results")
    parser.add_argument("--graph-depth", type=int, default=2, help="Graph traversal depth for neighbors")
    args = parser.parse_args()

    # Run search
    with Session(engine) as session:
        search_results = await java_search_service.search_code(
            session=session,
            query=args.query,
            repository_id=args.repo_id,
            top_k=args.max_results,
        )

        # Build a small local subgraph around top results
        nodes = []
        edges = []
        seen = set()
        for res in search_results:
            chunk_id = res.get("id") or res.get("chunk_id") or res.get("chunkId")
            if not chunk_id:
                continue
            node_id = f"chunk_{chunk_id}"
            nodes.append({"id": node_id, "label": res.get("fqn") or res.get("file_path"), "type": res.get("type")})
            seen.add(node_id)

            neighbors = await graph_service.find_related_code(
                session=session,
                chunk_id=chunk_id,
                max_depth=args.graph_depth,
                include_cross_repo=False,
            )
            for n in neighbors:
                nid = f"chunk_{n['chunk_id']}"
                if nid not in seen:
                    nodes.append({"id": nid, "label": n.get("fqn") or n.get("file_path"), "type": "related"})
                    seen.add(nid)
                edges.append({"from": node_id, "to": nid, "relationship": n.get("relationship", "rel")})

        mermaid_snippet = mermaid_from_edges(nodes, edges)
        html_out = build_html(args.query, search_results, mermaid_snippet)

        with open(args.output, "w", encoding="utf-8") as f:
            f.write(html_out)
        print(f"✅ Wrote report to {args.output}")


if __name__ == "__main__":
    asyncio.run(main())

