#!/usr/bin/env python3
"""
Inspect a graph.pkl and print nodes/edges for a given file_path or class name.

Usage:
  # Query by file path
  python graph_inspect.py --graph-file ./output/graph.pkl --file-path src/MyClass.java
  python graph_inspect.py --graph-file ./output/graph.pkl --file-path services/user/UserService.java --max-neighbors 5
  
  # Query by class name (shows all relationships)
  python graph_inspect.py --graph-file ./output/graph.pkl --class-name UserService
  python graph_inspect.py --graph-file ./output/graph.pkl --fqn com.example.UserService
  
  # Query by class name with all relationships (no limit)
  python graph_inspect.py --graph-file ./output/graph.pkl --class-name UserService --show-all-relations

Requirements:
  pip install networkx
"""

import argparse
import pickle
from pathlib import Path
from collections import defaultdict

try:
    import networkx as nx  # noqa: F401
except ImportError:
    raise SystemExit("Please install networkx: pip install networkx")


def find_class_nodes(G, class_name=None, fqn=None):
    """Find class nodes by name or FQN."""
    matching_nodes = []
    
    for n, d in G.nodes(data=True):
        entity_type = d.get('entity_type') or d.get('type', '')
        
        # Check if it's a class node (JavaClass or type='class')
        is_class = (entity_type == 'JavaClass' or 
                   entity_type == 'Class' or 
                   d.get('type') == 'class')
        
        if not is_class:
            continue
        
        # Match by FQN (exact or contains)
        if fqn:
            node_fqn = d.get('fqn', '')
            if fqn == node_fqn or node_fqn.endswith(f'.{fqn}') or fqn in node_fqn:
                matching_nodes.append((n, d))
        
        # Match by class name
        elif class_name:
            node_name = d.get('name', '')
            node_fqn = d.get('fqn', '')
            # Check if name matches or if FQN ends with the class name
            if (class_name == node_name or 
                node_fqn.endswith(f'.{class_name}') or
                class_name in node_fqn):
                matching_nodes.append((n, d))
    
    return matching_nodes


def get_all_relationships(G, node):
    """Get all relationships for a node, grouped by relationship type."""
    relationships = defaultdict(list)
    
    # Outgoing edges (from this node)
    for target in G.successors(node):
        edges = G.get_edge_data(node, target)
        if edges:
            # Handle MultiDiGraph edge dict
            for edge_key, edge_data in edges.items():
                rel_type = edge_data.get("relationship") or edge_data.get("type") or "related"
                target_data = G.nodes[target]
                relationships[rel_type].append({
                    'direction': 'outgoing',
                    'target': target,
                    'target_data': target_data,
                    'edge_data': edge_data
                })
    
    # Incoming edges (to this node)
    for source in G.predecessors(node):
        edges = G.get_edge_data(source, node)
        if edges:
            # Handle MultiDiGraph edge dict
            for edge_key, edge_data in edges.items():
                rel_type = edge_data.get("relationship") or edge_data.get("type") or "related"
                source_data = G.nodes[source]
                relationships[rel_type].append({
                    'direction': 'incoming',
                    'source': source,
                    'source_data': source_data,
                    'edge_data': edge_data
                })
    
    return relationships


def print_class_relationships(G, node, data, show_all=False, max_per_type=20):
    """Print all relationships for a class node."""
    print(f"\n{'='*80}")
    print(f"Class: {data.get('name', 'Unknown')}")
    print(f"FQN: {data.get('fqn', 'N/A')}")
    print(f"File: {data.get('file_path', 'N/A')}")
    print(f"Lines: {data.get('start_line', 'N/A')}-{data.get('end_line', 'N/A')}")
    print(f"Entity Type: {data.get('entity_type') or data.get('type', 'N/A')}")
    print(f"Node ID: {node}")
    print(f"{'='*80}")
    
    relationships = get_all_relationships(G, node)
    
    if not relationships:
        print("\n⚠️  No relationships found for this class.")
        return
    
    # Sort relationship types for consistent output
    sorted_rel_types = sorted(relationships.keys())
    
    print(f"\n📊 Found {len(sorted_rel_types)} relationship types:")
    for rel_type in sorted_rel_types:
        print(f"   - {rel_type}: {len(relationships[rel_type])} edges")
    
    print(f"\n{'='*80}\n")
    
    # Print relationships grouped by type
    for rel_type in sorted_rel_types:
        rels = relationships[rel_type]
        limit = len(rels) if show_all else min(max_per_type, len(rels))
        
        print(f"\n🔗 {rel_type.upper()} ({len(rels)} total, showing {limit}):")
        print("-" * 80)
        
        for i, rel in enumerate(rels[:limit]):
            if rel['direction'] == 'outgoing':
                target = rel['target']
                target_data = rel['target_data']
                target_type = target_data.get('entity_type') or target_data.get('type', 'Unknown')
                target_name = target_data.get('name') or target_data.get('fqn') or str(target)
                print(f"  [{i+1}] → {target_name} ({target_type})")
                if target_data.get('file_path'):
                    print(f"      File: {target_data.get('file_path')}")
                if target_data.get('fqn'):
                    print(f"      FQN: {target_data.get('fqn')}")
            else:  # incoming
                source = rel['source']
                source_data = rel['source_data']
                source_type = source_data.get('entity_type') or source_data.get('type', 'Unknown')
                source_name = source_data.get('name') or source_data.get('fqn') or str(source)
                print(f"  [{i+1}] ← {source_name} ({source_type})")
                if source_data.get('file_path'):
                    print(f"      File: {source_data.get('file_path')}")
                if source_data.get('fqn'):
                    print(f"      FQN: {source_data.get('fqn')}")
        
        if len(rels) > limit and not show_all:
            print(f"  ... and {len(rels) - limit} more (use --show-all-relations to see all)")


def main():
    parser = argparse.ArgumentParser(
        description="Inspect graph nodes/edges for a specific file or class",
        formatter_class=argparse.RawDescriptionHelpFormatter
    )
    parser.add_argument("--graph-file", required=True, help="Path to graph.pkl")
    
    # Query options (mutually exclusive)
    query_group = parser.add_mutually_exclusive_group(required=True)
    query_group.add_argument("--file-path", help="Relative file path to search for")
    query_group.add_argument("--class-name", help="Class name to search for (e.g., 'UserService')")
    query_group.add_argument("--fqn", help="Fully qualified name to search for (e.g., 'com.example.UserService')")
    
    parser.add_argument("--max-neighbors", type=int, default=20, 
                       help="Max neighbors to show when querying by file-path (default: 20)")
    parser.add_argument("--show-all-relations", action="store_true",
                       help="Show all relationships when querying by class (default: limit to 20 per type)")
    args = parser.parse_args()

    if not Path(args.graph_file).exists():
        raise SystemExit(f"Graph file not found: {args.graph_file}")

    with open(args.graph_file, "rb") as f:
        G = pickle.load(f)

    matching_nodes = []
    
    # Query by file path
    if args.file_path:
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
    
    # Query by class name or FQN
    elif args.class_name or args.fqn:
        matching_nodes = find_class_nodes(G, class_name=args.class_name, fqn=args.fqn)
        
        if not matching_nodes:
            query = args.class_name or args.fqn
            print(f"No class nodes found matching: {query}")
            print("\n💡 Tip: Try searching with a partial class name or check the FQN format.")
            return
        
        print(f"Found {len(matching_nodes)} class node(s) matching: {args.class_name or args.fqn}")
        
        # Show relationships for each matching class
        for idx, (node, data) in enumerate(matching_nodes, 1):
            if len(matching_nodes) > 1:
                print(f"\n{'#'*80}")
                print(f"# Class {idx} of {len(matching_nodes)}")
                print(f"{'#'*80}")
            
            print_class_relationships(G, node, data, 
                                     show_all=args.show_all_relations,
                                     max_per_type=20)


if __name__ == "__main__":
    main()

