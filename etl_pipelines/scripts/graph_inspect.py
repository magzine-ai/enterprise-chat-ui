#!/usr/bin/env python3
"""
Inspect a graph.pkl and print nodes/edges for a given file_path.

Usage:
  python graph_inspect.py --graph-file ./output/graph.pkl --file-path src/MyClass.java
  python graph_inspect.py --graph-file ./output/graph.pkl --file-path services/user/UserService.java --max-neighbors 5

Requirements:
  pip install networkx
"""

import argparse
import pickle
from pathlib import Path

try:
    import networkx as nx  # noqa: F401
except ImportError:
    raise SystemExit("Please install networkx: pip install networkx")


def main():
    parser = argparse.ArgumentParser(description="Inspect graph nodes/edges for a specific file")
    parser.add_argument("--graph-file", required=True, help="Path to graph.pkl")
    parser.add_argument("--file-path", required=True, help="Relative file path to search for")
    parser.add_argument("--max-neighbors", type=int, default=20, help="Max neighbors to show (default: 20)")
    args = parser.parse_args()

    if not Path(args.graph_file).exists():
        raise SystemExit(f"Graph file not found: {args.graph_file}")

    with open(args.graph_file, "rb") as f:
        G = pickle.load(f)

    # Find nodes whose file_path matches exactly
    matching_nodes = [
        (n, d) for n, d in G.nodes(data=True)
        if d.get("file_path") == args.file_path
    ]

    # If no direct match, try matching by filename suffix
    if not matching_nodes:
        target_name = Path(args.file_path).name
        matches_by_name = [
            (n, d) for n, d in G.nodes(data=True)
            if d.get("file_path", "").replace("\\", "/").endswith(f"/{target_name}")
               or Path(d.get("file_path", "")).name == target_name
        ]
        if matches_by_name:
            matching_nodes = [matches_by_name[0]]

    if not matching_nodes:
        print(f"No nodes found with file_path = {args.file_path}")
        return

    print(f"Found {len(matching_nodes)} nodes for file_path = {args.file_path}")
    for idx, (node, data) in enumerate(matching_nodes, 1):
        print(f"\n[{idx}] Node ID: {node}")
        print(f"    type: {data.get('type')}")
        print(f"    entity_type: {data.get('entity_type')}")
        print(f"    fqn: {data.get('fqn')}")
        print(f"    start_line: {data.get('start_line')}")
        print(f"    end_line: {data.get('end_line')}")

        # Neighbors (both directions)
        neighbors = list(G.neighbors(node)) + list(G.predecessors(node))
        neighbors = neighbors[:args.max_neighbors]
        print(f"    Neighbors (max {args.max_neighbors}): {len(neighbors)}")

        for nb in neighbors:
            edge_data = G.get_edge_data(node, nb) or G.get_edge_data(nb, node) or {}
            if edge_data and isinstance(edge_data, dict):
                # handle MultiDiGraph edge dict
                edge_info = list(edge_data.values())[0] if edge_data else {}
                rel = edge_info.get("relationship") or edge_info.get("type") or "related"
            else:
                rel = "related"
            nb_data = G.nodes[nb]
            print(f"      -> {nb} ({nb_data.get('entity_type') or nb_data.get('type')}) rel={rel}")


if __name__ == "__main__":
    main()

