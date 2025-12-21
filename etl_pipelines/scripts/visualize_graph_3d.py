"""
Standalone script to visualize NetworkX graph in 3D using Plotly.

Usage:
  python visualize_graph_3d.py \
    --graph-file ./output/graph.pkl \
    --output graph_3d.html \
    --max-nodes 500

Requirements:
  pip install plotly networkx
"""

import argparse
import pickle
from pathlib import Path
from typing import Dict, Any, Optional

# NetworkX for graph
try:
    import networkx as nx
    NETWORKX_AVAILABLE = True
except ImportError:
    NETWORKX_AVAILABLE = False
    print("⚠️ NetworkX not available. Install: pip install networkx")

# Plotly for 3D visualization
try:
    import plotly.graph_objects as go
    import plotly.express as px
    PLOTLY_AVAILABLE = True
except ImportError:
    PLOTLY_AVAILABLE = False
    print("⚠️ Plotly not available. Install: pip install plotly")


def visualize_graph_3d(
    graph_file: str,
    output_file: str,
    max_nodes: int = 500,
    layout_iterations: int = 50
):
    """
    Load and visualize NetworkX graph in 3D.
    
    Args:
        graph_file: Path to graph pickle file
        output_file: Output HTML file path
        max_nodes: Maximum number of nodes to visualize (for performance)
        layout_iterations: Number of iterations for spring layout calculation
    """
    if not PLOTLY_AVAILABLE:
        print("❌ Plotly is required for 3D visualization")
        return False
    
    if not NETWORKX_AVAILABLE:
        print("❌ NetworkX is required")
        return False
    
    # Load graph
    try:
        with open(graph_file, 'rb') as f:
            graph = pickle.load(f)
        print(f"✅ Graph loaded: {graph.number_of_nodes()} nodes, {graph.number_of_edges()} edges")
    except Exception as e:
        print(f"❌ Error loading graph: {e}")
        return False
    
    # Limit nodes for performance
    nodes = list(graph.nodes(data=True))
    original_node_count = len(nodes)
    
    if len(nodes) > max_nodes:
        print(f"⚠️ Graph has {len(nodes)} nodes, limiting to {max_nodes} for visualization")
        # Use nodes with highest degree (most connected)
        degrees = dict(graph.degree())
        top_nodes = sorted(degrees.items(), key=lambda x: x[1], reverse=True)[:max_nodes]
        node_set = set([n[0] for n in top_nodes])
        nodes = [(n, d) for n, d in nodes if n in node_set]
        # Filter edges to only include selected nodes
        edges = [(u, v) for u, v in graph.edges() if u in node_set and v in node_set]
        print(f"   Selected {len(nodes)} nodes with highest connectivity")
    else:
        edges = list(graph.edges())
    
    # Calculate 3D layout using spring layout
    print("📐 Calculating 3D layout...")
    pos_2d = nx.spring_layout(graph, k=1, iterations=layout_iterations, seed=42)
    
    # Convert 2D to 3D by adding a Z coordinate based on node type or degree
    pos_3d = {}
    entity_type_map = {}
    
    for node, data in nodes:
        x, y = pos_2d[node]
        
        # Z coordinate based on entity type (if rich schema) or degree
        if 'entity_type' in data:
            entity_type = data.get('entity_type', 'CodeChunk')
            entity_type_map[node] = entity_type
            
            # Map entity types to Z coordinates (hierarchical)
            z_map = {
                'Application': 5.0,
                'Service': 4.0,
                'DeploymentUnit': 3.5,
                'File': 3.0,
                'JavaClass': 2.0,
                'Method': 1.0,
                'ConfigArtifact': 2.5,
                'ConfigKey': 1.5,
                'Environment': 1.8,
                'ExternalResource': 2.2,
                'CodeChunk': 1.5
            }
            z = z_map.get(entity_type, 1.0)
        else:
            # Use degree for Z coordinate (normalized)
            degree = graph.degree(node)
            z = min(degree * 0.1, 3.0)  # Cap at 3.0
            entity_type_map[node] = 'CodeChunk'
        
        pos_3d[node] = (x, y, z)
    
    # Prepare edge traces
    print("🔗 Preparing edge traces...")
    edge_x = []
    edge_y = []
    edge_z = []
    
    for u, v in edges:
        if u in pos_3d and v in pos_3d:
            x0, y0, z0 = pos_3d[u]
            x1, y1, z1 = pos_3d[v]
            edge_x.extend([x0, x1, None])
            edge_y.extend([y0, y1, None])
            edge_z.extend([z0, z1, None])
    
    edge_trace = go.Scatter3d(
        x=edge_x, y=edge_y, z=edge_z,
        line=dict(width=1, color='#888'),
        hoverinfo='none',
        mode='lines',
        name='Edges',
        showlegend=False
    )
    
    # Prepare node traces (grouped by entity type for rich schema)
    print("📊 Preparing node traces...")
    node_traces = []
    
    # Group nodes by entity type
    entity_types = {}
    for node, data in nodes:
        entity_type = entity_type_map.get(node, 'CodeChunk')
        if entity_type not in entity_types:
            entity_types[entity_type] = []
        entity_types[entity_type].append((node, data))
    
    # Color palette for different entity types
    colors = px.colors.qualitative.Set3 + px.colors.qualitative.Pastel
    
    for i, (entity_type, type_nodes) in enumerate(entity_types.items()):
        node_x = [pos_3d[n][0] for n, _ in type_nodes]
        node_y = [pos_3d[n][1] for n, _ in type_nodes]
        node_z = [pos_3d[n][2] for n, _ in type_nodes]
        
        node_text = []
        node_info = []
        node_sizes = []
        
        for node, data in type_nodes:
            # Get display name
            name = data.get('name', data.get('fqn', str(node)))
            node_text.append(name[:40])  # Truncate for display
            
            # Build hover info
            info = f"<b>{entity_type}</b><br>"
            info += f"Name: {name}<br>"
            if 'fqn' in data and data['fqn']:
                info += f"FQN: {data['fqn']}<br>"
            if 'file_path' in data and data['file_path']:
                info += f"File: {data['file_path']}<br>"
            if 'type' in data:
                info += f"Type: {data['type']}<br>"
            info += f"Connections: {graph.degree(node)}"
            node_info.append(info)
            
            # Size based on degree
            degree = graph.degree(node)
            node_sizes.append(max(5, min(degree * 2, 20)))
        
        node_traces.append(go.Scatter3d(
            x=node_x, y=node_y, z=node_z,
            mode='markers',
            name=f"{entity_type} ({len(type_nodes)})",
            marker=dict(
                size=node_sizes,
                color=colors[i % len(colors)],
                line=dict(width=0.5, color='white'),
                opacity=0.8
            ),
            text=node_text,
            hovertemplate='%{customdata}<extra></extra>',
            customdata=node_info
        ))
    
    # Create figure
    print("🎨 Creating 3D visualization...")
    fig = go.Figure(data=[edge_trace] + node_traces)
    
    # Determine if rich schema
    is_rich_schema = len(entity_types) > 1
    
    fig.update_layout(
        title=dict(
            text=f'3D Knowledge Graph Visualization<br><sub>{original_node_count} nodes, {graph.number_of_edges()} edges</sub>',
            x=0.5,
            xanchor='center'
        ),
        scene=dict(
            xaxis=dict(title='X', backgroundcolor='rgb(240, 240, 240)'),
            yaxis=dict(title='Y', backgroundcolor='rgb(240, 240, 240)'),
            zaxis=dict(
                title='Z (Entity Type Hierarchy)' if is_rich_schema else 'Z (Node Degree)',
                backgroundcolor='rgb(240, 240, 240)'
            ),
            bgcolor='rgb(250, 250, 250)',
            camera=dict(
                eye=dict(x=1.5, y=1.5, z=1.5)
            )
        ),
        width=1400,
        height=900,
        showlegend=True,
        hovermode='closest',
        margin=dict(b=20, l=5, r=5, t=60),
        legend=dict(
            x=1.02,
            y=1,
            bgcolor='rgba(255, 255, 255, 0.8)',
            bordercolor='rgba(0, 0, 0, 0.2)',
            borderwidth=1
        )
    )
    
    # Save HTML file
    output_path = Path(output_file)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    
    fig.write_html(str(output_path))
    print(f"✅ 3D graph visualization saved to {output_path}")
    print(f"   Open {output_path} in a web browser to view the interactive 3D graph")
    
    return True


def create_sample_graph(output_file: str):
    """
    Create a sample graph for testing visualization.
    
    Args:
        output_file: Path to save sample graph pickle file
    """
    if not NETWORKX_AVAILABLE:
        print("❌ NetworkX not available")
        return False
    
    print("📊 Creating sample knowledge graph...")
    graph = nx.MultiDiGraph()
    
    # Add Application
    app_id = "app_sample_app"
    graph.add_node(app_id, entity_type='Application', name='SampleApp', display_name='Sample Application')
    
    # Add Services
    services = [
        ('service_user_service', 'UserService'),
        ('service_order_service', 'OrderService'),
        ('service_payment_service', 'PaymentService')
    ]
    for service_id, service_name in services:
        graph.add_node(service_id, entity_type='Service', name=service_name)
        graph.add_edge(app_id, service_id, relationship='OWNS')
    
    # Add Files
    files = [
        ('file_user_service_java', 'UserService.java', 'service_user_service'),
        ('file_user_repository_java', 'UserRepository.java', 'service_user_service'),
        ('file_order_service_java', 'OrderService.java', 'service_order_service'),
        ('file_payment_service_java', 'PaymentService.java', 'service_payment_service'),
    ]
    for file_id, file_name, service_id in files:
        graph.add_node(file_id, entity_type='File', name=file_name, file_path=f'src/main/java/{file_name}')
        graph.add_edge(service_id, file_id, relationship='CONTAINS')
    
    # Add Classes
    classes = [
        ('class_user_service', 'UserService', 'file_user_service_java'),
        ('class_user_repository', 'UserRepository', 'file_user_repository_java'),
        ('class_order_service', 'OrderService', 'file_order_service_java'),
        ('class_payment_service', 'PaymentService', 'file_payment_service_java'),
    ]
    for class_id, class_name, file_id in classes:
        graph.add_node(class_id, entity_type='JavaClass', name=class_name, fqn=f'com.example.{class_name}')
        graph.add_edge(file_id, class_id, relationship='DECLARES')
    
    # Add Methods
    methods = [
        ('method_get_user', 'getUser', 'class_user_service'),
        ('method_create_user', 'createUser', 'class_user_service'),
        ('method_find_by_id', 'findById', 'class_user_repository'),
        ('method_process_order', 'processOrder', 'class_order_service'),
        ('method_process_payment', 'processPayment', 'class_payment_service'),
    ]
    for method_id, method_name, class_id in methods:
        graph.add_node(method_id, entity_type='Method', name=method_name, fqn=f'{method_id}.{method_name}')
        graph.add_edge(class_id, method_id, relationship='DECLARES_METHOD')
    
    # Add relationships
    graph.add_edge('class_user_service', 'class_user_repository', relationship='REFERENCES')
    graph.add_edge('method_get_user', 'method_find_by_id', relationship='CALLS')
    graph.add_edge('method_process_order', 'method_process_payment', relationship='CALLS')
    graph.add_edge('class_order_service', 'class_payment_service', relationship='REFERENCES')
    
    # Add Config
    config_id = 'config_app_yml'
    graph.add_node(config_id, entity_type='ConfigArtifact', name='application.yml', path='src/main/resources/application.yml')
    graph.add_edge('class_user_service', config_id, relationship='USES_CONFIG')
    
    # Save graph
    output_path = Path(output_file)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    
    with open(output_path, 'wb') as f:
        pickle.dump(graph, f)
    
    print(f"✅ Sample graph created: {graph.number_of_nodes()} nodes, {graph.number_of_edges()} edges")
    print(f"   Saved to {output_path}")
    
    return True


def main():
    parser = argparse.ArgumentParser(description="Visualize NetworkX graph in 3D")
    parser.add_argument("--graph-file", help="Path to graph pickle file")
    parser.add_argument("--output", default="graph_3d.html", help="Output HTML file (default: graph_3d.html)")
    parser.add_argument("--max-nodes", type=int, default=500, help="Maximum nodes to visualize (default: 500)")
    parser.add_argument("--layout-iterations", type=int, default=50, help="Layout calculation iterations (default: 50)")
    parser.add_argument("--create-sample", action="store_true", help="Create a sample graph for testing")
    parser.add_argument("--sample-file", default="sample_graph.pkl", help="Sample graph file path (default: sample_graph.pkl)")
    
    args = parser.parse_args()
    
    # Create sample graph if requested
    if args.create_sample:
        success = create_sample_graph(args.sample_file)
        if success:
            print(f"\n💡 To visualize the sample graph, run:")
            print(f"   python visualize_graph_3d.py --graph-file {args.sample_file} --output sample_graph_3d.html")
        return
    
    # Visualize graph
    if not args.graph_file:
        parser.error("Either --graph-file or --create-sample is required")
    
    if not Path(args.graph_file).exists():
        print(f"❌ Graph file not found: {args.graph_file}")
        print(f"💡 Create a sample graph with: python visualize_graph_3d.py --create-sample")
        return
    
    visualize_graph_3d(
        graph_file=args.graph_file,
        output_file=args.output,
        max_nodes=args.max_nodes,
        layout_iterations=args.layout_iterations
    )


if __name__ == "__main__":
    main()

