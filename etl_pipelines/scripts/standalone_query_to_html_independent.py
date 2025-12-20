"""
Completely standalone script to query OpenSearch chunks and generate HTML report with Mermaid graph.
No dependencies on project structure.

Usage:
  python standalone_query_to_html_independent.py \
    --query "who calls startDemo" \
    --opensearch-host localhost:9200 \
    --opensearch-index code_chunks \
    --graph-file ./output/graph.pkl \
    --output report.html

Requirements:
  pip install opensearch-py networkx
"""

import argparse
import html
import pickle
from pathlib import Path
from typing import List, Dict, Any, Optional

# OpenSearch
try:
    from opensearchpy import OpenSearch
    OPENSEARCH_AVAILABLE = True
except ImportError:
    OPENSEARCH_AVAILABLE = False
    print("⚠️ OpenSearch not available. Install: pip install opensearch-py")

# NetworkX for graph
try:
    import networkx as nx
    NETWORKX_AVAILABLE = True
except ImportError:
    NETWORKX_AVAILABLE = False
    print("⚠️ NetworkX not available. Install: pip install networkx")


class StandaloneSearcher:
    """Self-contained OpenSearch searcher."""
    
    def __init__(self, host: str, index: str, use_ssl: bool = False):
        self.host = host
        self.index = index
        self.client = None
        
        if OPENSEARCH_AVAILABLE:
            try:
                host_parts = host.split(':')
                hostname = host_parts[0]
                port = int(host_parts[1]) if len(host_parts) > 1 else 9200
                
                self.client = OpenSearch(
                    hosts=[{'host': hostname, 'port': port}],
                    use_ssl=use_ssl,
                    verify_certs=False,
                )
            except Exception as e:
                print(f"⚠️ Failed to connect: {e}")
    
    def search(self, query: str, top_k: int = 10) -> List[Dict[str, Any]]:
        """Search OpenSearch index."""
        if not self.client:
            return []
        
        try:
            response = self.client.search(
                index=self.index,
                body={
                    "size": top_k,
                    "query": {
                        "multi_match": {
                            "query": query,
                            "fields": ["code", "summary", "fqn"]
                        }
                    }
                }
            )
            
            results = []
            for hit in response['hits']['hits']:
                source = hit['_source']
                results.append({
                    'id': hit['_id'],
                    'score': hit['_score'],
                    'fqn': source.get('fqn', ''),
                    'type': source.get('type', ''),
                    'file_path': source.get('file_path', ''),
                    'code': source.get('code', ''),
                    'summary': source.get('summary', ''),
                })
            
            return results
        except Exception as e:
            print(f"⚠️ Search error: {e}")
            return []


class StandaloneGraphLoader:
    """Self-contained graph loader."""
    
    def __init__(self, graph_file: str):
        self.graph = None
        if NETWORKX_AVAILABLE and Path(graph_file).exists():
            try:
                with open(graph_file, 'rb') as f:
                    self.graph = pickle.load(f)
                print(f"✅ Loaded graph: {self.graph.number_of_nodes()} nodes, {self.graph.number_of_edges()} edges")
            except Exception as e:
                print(f"⚠️ Failed to load graph: {e}")
    
    def find_related(self, chunk_id: str, max_depth: int = 2) -> List[Dict[str, Any]]:
        """Find related chunks in graph."""
        if not self.graph:
            return []
        
        node_id = f"chunk_{chunk_id}"
        if node_id not in self.graph:
            return []
        
        related = []
        visited = set()
        queue = [(node_id, 0)]
        
        while queue:
            current, depth = queue.pop(0)
            if depth > max_depth or current in visited:
                continue
            
            visited.add(current)
            
            # Get neighbors
            for neighbor in list(self.graph.successors(current)) + list(self.graph.predecessors(current)):
                if neighbor not in visited:
                    edge_data = self.graph.get_edge_data(current, neighbor)
                    if edge_data:
                        rel_type = list(edge_data.values())[0].get('relationship', 'related')
                        related.append({
                            'chunk_id': neighbor.replace('chunk_', ''),
                            'relationship': rel_type,
                            'fqn': self.graph.nodes[neighbor].get('fqn', ''),
                        })
                        queue.append((neighbor, depth + 1))
        
        return related


def mermaid_from_graph(nodes: List[Dict[str, Any]], edges: List[Dict[str, Any]]) -> str:
    """Generate Mermaid diagram from nodes and edges."""
    node_lines = []
    for n in nodes:
        label = n.get('label', n.get('fqn', n.get('id', '')))
        short = html.escape(label.split('.')[-1][:30])
        node_lines.append(f'    {n["id"]}["{short}"]')
    
    edge_lines = []
    for e in edges:
        rel = e.get('relationship', 'rel')
        edge_lines.append(f'    {e["from"]} -->|{rel}| {e["to"]}')
    
    body = "\n".join(node_lines + edge_lines)
    return f"flowchart LR\n{body}"


def build_html(query: str, results: List[Dict[str, Any]], mermaid_snippet: str) -> str:
    """Build HTML report."""
    rows = []
    for r in results:
        rows.append(f"""
        <tr>
          <td>{html.escape(str(r.get('score', '')))}</td>
          <td>{html.escape(r.get('fqn', ''))}</td>
          <td>{html.escape(r.get('type', ''))}</td>
          <td>{html.escape(r.get('file_path', ''))}</td>
        </tr>
        """)
    
    return f"""<!doctype html>
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
    .mermaid {{ border: 1px solid #ddd; padding: 12px; border-radius: 6px; margin-top: 16px; }}
  </style>
</head>
<body>
  <h2>Query</h2>
  <pre>{html.escape(query)}</pre>

  <h2>Top Results ({len(results)})</h2>
  <table>
    <thead><tr><th>Score</th><th>FQN</th><th>Type</th><th>File Path</th></tr></thead>
    <tbody>
      {''.join(rows)}
    </tbody>
  </table>

  <h2>Graph Visualization</h2>
  <div class="mermaid">
{mermaid_snippet}
  </div>
</body>
</html>"""


def main():
    parser = argparse.ArgumentParser(description="Query OpenSearch and generate HTML report")
    parser.add_argument("--query", required=True, help="Search query")
    parser.add_argument("--opensearch-host", required=True, help="OpenSearch host")
    parser.add_argument("--opensearch-index", required=True, help="OpenSearch index")
    parser.add_argument("--graph-file", help="Graph pickle file (optional)")
    parser.add_argument("--output", required=True, help="Output HTML file")
    parser.add_argument("--max-results", type=int, default=10, help="Max search results")
    parser.add_argument("--graph-depth", type=int, default=2, help="Graph traversal depth")
    args = parser.parse_args()
    
    # Search
    searcher = StandaloneSearcher(args.opensearch_host, args.opensearch_index)
    results = searcher.search(args.query, top_k=args.max_results)
    print(f"✅ Found {len(results)} results")
    
    # Build graph visualization
    nodes = []
    edges = []
    seen = set()
    
    # Add result nodes
    for res in results:
        chunk_id = res['id']
        node_id = f"chunk_{chunk_id}"
        nodes.append({
            'id': node_id,
            'label': res['fqn'],
            'fqn': res['fqn']
        })
        seen.add(node_id)
    
    # Load graph and find relationships
    if args.graph_file:
        graph_loader = StandaloneGraphLoader(args.graph_file)
        for res in results:
            chunk_id = res['id']
            related = graph_loader.find_related(chunk_id, max_depth=args.graph_depth)
            
            for rel in related:
                nid = f"chunk_{rel['chunk_id']}"
                if nid not in seen:
                    nodes.append({
                        'id': nid,
                        'label': rel.get('fqn', ''),
                        'fqn': rel.get('fqn', '')
                    })
                    seen.add(nid)
                
                edges.append({
                    'from': f"chunk_{chunk_id}",
                    'to': nid,
                    'relationship': rel['relationship']
                })
    
    # Generate HTML
    mermaid_snippet = mermaid_from_graph(nodes, edges)
    html_content = build_html(args.query, results, mermaid_snippet)
    
    with open(args.output, 'w', encoding='utf-8') as f:
        f.write(html_content)
    
    print(f"✅ Wrote report to {args.output}")


if __name__ == "__main__":
    main()


