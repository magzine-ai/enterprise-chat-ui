"""
Generate a visually appealing architecture diagram as an image.

This script creates a high-quality visual representation of the system architecture
using matplotlib and networkx for better UX and visual appeal.

Usage:
    python generate_architecture_diagram.py --output architecture.png
    python generate_architecture_diagram.py --output architecture.svg --format svg
"""

import argparse
import matplotlib.pyplot as plt
import matplotlib.patches as mpatches
from matplotlib.patches import FancyBboxPatch, FancyArrowPatch, Circle, Rectangle
import matplotlib.patheffects as path_effects
from matplotlib import font_manager
import numpy as np

# Try to import networkx for graph layout
try:
    import networkx as nx
    NETWORKX_AVAILABLE = True
except ImportError:
    NETWORKX_AVAILABLE = False
    print("⚠️ NetworkX not available. Install: pip install networkx (for better layout)")

def create_architecture_diagram(output_path: str = "architecture.png", format: str = "png", dpi: int = 300):
    """
    Create a visually appealing architecture diagram.
    
    Args:
        output_path: Path to save the image
        format: Image format (png, svg, pdf)
        dpi: Resolution for raster formats
    """
    # Create figure with high DPI for quality
    fig, ax = plt.subplots(1, 1, figsize=(20, 14), facecolor='#FAFAFA')
    ax.set_xlim(0, 100)
    ax.set_ylim(0, 100)
    ax.axis('off')
    
    # Color palette - modern, accessible colors
    colors = {
        'user': '#1976D2',
        'orchestrator': '#388E3C',
        'primary_agent': '#1976D2',
        'secondary_agent': '#F57C00',
        'search': '#7B1FA2',
        'data_store': '#0277BD',
        'data_layer': '#C2185B',
        'etl': '#00695C',
        'llm': '#C62828',
        'response': '#E65100',
        'feature': '#2E7D32',
        'background': '#FAFAFA',
        'grid': '#E0E0E0'
    }
    
    # Helper function to create rounded rectangle boxes
    def create_box(x, y, width, height, label, color, icon='', subtext=''):
        """Create a styled box with icon and text."""
        # Main box
        box = FancyBboxPatch(
            (x - width/2, y - height/2), width, height,
            boxstyle="round,pad=0.5", 
            facecolor=color,
            edgecolor='white',
            linewidth=2.5,
            zorder=2
        )
        ax.add_patch(box)
        
        # Add shadow effect
        shadow = FancyBboxPatch(
            (x - width/2 + 0.3, y - height/2 - 0.3), width, height,
            boxstyle="round,pad=0.5",
            facecolor='black',
            alpha=0.1,
            zorder=1
        )
        ax.add_patch(shadow)
        
        # Add icon (with fallback for unsupported emojis)
        if icon:
            try:
                ax.text(x, y + height/4, icon, fontsize=24, ha='center', va='center', zorder=3)
            except Exception:
                # Fallback: use first character or symbol
                icon_fallback = icon[0] if icon else ''
                ax.text(x, y + height/4, icon_fallback, fontsize=20, ha='center', va='center', zorder=3, weight='bold')
        
        # Add main label
        text = ax.text(x, y, label, fontsize=11, ha='center', va='center', 
                      weight='bold', zorder=3, color='white')
        text.set_path_effects([path_effects.withStroke(linewidth=3, foreground='black', alpha=0.3)])
        
        # Add subtext
        if subtext:
            ax.text(x, y - height/4, subtext, fontsize=8, ha='center', va='center',
                   zorder=3, color='white', alpha=0.9)
        
        return box
    
    # Helper function to create arrows
    def create_arrow(x1, y1, x2, y2, style='solid', color='#666', width=1.5, alpha=0.7):
        """Create a styled arrow."""
        if style == 'solid':
            arrow = FancyArrowPatch(
                (x1, y1), (x2, y2),
                arrowstyle='->', mutation_scale=20,
                color=color, linewidth=width, alpha=alpha, zorder=1
            )
        else:  # dashed
            arrow = FancyArrowPatch(
                (x1, y1), (x2, y2),
                arrowstyle='->', mutation_scale=20,
                color=color, linewidth=width, alpha=alpha, 
                linestyle='--', zorder=1
            )
        ax.add_patch(arrow)
        return arrow
    
    # Layer 1: User Input (Top Center)
    create_box(50, 95, 12, 4, 'User Input', colors['user'], '👤', 'Query & Context')
    
    # Layer 2: Orchestrator (Below User)
    create_box(50, 85, 14, 4, 'Orchestrator Agent', colors['orchestrator'], '🎯', 'Intelligent Routing')
    
    # Layer 3: Primary Agents (Left)
    create_box(20, 70, 10, 3.5, 'API Discovery', colors['primary_agent'], '🔍', 'RAG Search')
    create_box(20, 65, 10, 3.5, 'Splunk Agent', colors['primary_agent'], 'SPL', 'Log Analysis')
    
    # Layer 3: Secondary Agents (Right)
    create_box(80, 72, 10, 3.5, 'Code Analyzer', colors['secondary_agent'], '💻', 'Code Intelligence')
    create_box(80, 67, 10, 3.5, 'JIRA Agent', colors['secondary_agent'], 'JIRA', 'Issue Tracking')
    create_box(80, 62, 10, 3.5, 'SNOW Agent', colors['secondary_agent'], 'SNOW', 'ITSM')
    
    # Layer 4: Search Mechanisms (Middle)
    create_box(15, 50, 8, 3, 'RAG Search', colors['search'], '🔎', 'Semantic')
    create_box(25, 50, 8, 3, 'RAG Search', colors['search'], '🔎', 'Code Context')
    create_box(35, 50, 8, 3, 'Graph Search', colors['search'], '🕸️', 'Relationships')
    create_box(45, 50, 8, 3, 'Splunk Query', colors['search'], 'SPL', 'Log Retrieval')
    create_box(65, 50, 8, 3, 'JIRA Metrics', colors['search'], 'JIRA', 'Issue Data')
    create_box(75, 50, 8, 3, 'SNOW Metrics', colors['search'], 'SNOW', 'Ticket Data')
    
    # Layer 5: Data Stores (Bottom)
    create_box(10, 30, 9, 3.5, 'OpenSearch', colors['data_store'], 'OS', 'Vector + Metadata')
    create_box(22, 30, 9, 3.5, 'TigerDB', colors['data_store'], 'TDB', 'Graph Database')
    create_box(34, 30, 9, 3.5, 'Splunk', colors['data_store'], 'SPL', 'Logs & Metrics')
    create_box(66, 30, 9, 3.5, 'JIRA', colors['data_store'], 'JIRA', 'Issues & Metrics')
    create_box(78, 30, 9, 3.5, 'ServiceNow', colors['data_store'], 'SNOW', 'Tickets & Metrics')
    
    # Data Layer (Left Side)
    create_box(10, 10, 9, 3, 'Embeddings', colors['data_layer'], '📊', 'Vectors')
    create_box(22, 10, 9, 3, 'Code Chunks', colors['data_layer'], '📄', 'Methods, Classes')
    create_box(34, 10, 9, 3, 'Graph Data', colors['data_layer'], '🕸️', 'Relationships')
    
    # ETL Pipeline (Left Side, Middle)
    create_box(10, 18, 9, 3, 'Code Parser', colors['etl'], '📝', 'AST Extraction')
    create_box(22, 18, 9, 3, 'Chunking', colors['etl'], '✂️', 'Strategy-based')
    create_box(34, 18, 9, 3, 'Embedding Gen', colors['etl'], '🧮', 'Azure/OpenAI')
    create_box(46, 18, 9, 3, 'Graph Builder', colors['etl'], 'TDB', 'NetworkX/TigerDB')
    
    # LLM Reasoning (Center)
    create_box(50, 40, 14, 4, 'LLM Overall Reasoning', colors['llm'], '🤖', 'Synthesis & Analysis')
    
    # Response (Right of LLM)
    create_box(70, 40, 12, 4, 'Response to User', colors['response'], '💬', 'Formatted Output')
    
    # Agent Features (Top Right)
    create_box(85, 90, 10, 3, 'Resiliency', colors['feature'], '🔄', 'Retry & Circuit Breaker')
    create_box(85, 85, 10, 3, 'Memory Persistence', colors['feature'], '💾', 'Context & History')
    
    # Arrows - User to Orchestrator
    create_arrow(50, 93, 50, 87, 'solid', colors['user'], 2.5)
    
    # Orchestrator to Agents (single layer, no path distinction)
    create_arrow(45, 85, 25, 73.5, 'solid', colors['orchestrator'], 2)
    create_arrow(45, 85, 25, 68.5, 'solid', colors['orchestrator'], 2)
    create_arrow(50, 85, 55, 73.5, 'solid', colors['orchestrator'], 2)
    create_arrow(50, 85, 55, 68.5, 'solid', colors['orchestrator'], 2)
    create_arrow(50, 85, 55, 63.5, 'solid', colors['orchestrator'], 2)
    
    # Agents to Search
    create_arrow(25, 70.25, 19, 51.5, 'solid', colors['primary_agent'], 2)  # API -> RAG1
    create_arrow(25, 65.25, 49, 51.5, 'solid', colors['primary_agent'], 2)  # Splunk -> SplunkQuery
    create_arrow(55, 70.25, 29, 51.5, 'solid', colors['primary_agent'], 2)  # CodeAnalyzer -> RAG2
    create_arrow(55, 70.25, 39, 51.5, 'solid', colors['primary_agent'], 2)  # CodeAnalyzer -> GraphSearch
    create_arrow(55, 65.25, 69, 51.5, 'solid', colors['primary_agent'], 2)  # JIRA -> JIRAMetrics
    create_arrow(55, 60.25, 79, 51.5, 'solid', colors['primary_agent'], 2)  # SNOW -> SNOWMetrics
    
    # Search to Data Stores
    create_arrow(19, 48.5, 14.5, 31.75, 'solid', colors['search'], 2)
    create_arrow(29, 48.5, 14.5, 31.75, 'solid', colors['search'], 2)
    create_arrow(39, 48.5, 26.5, 31.75, 'solid', colors['search'], 2)
    create_arrow(49, 48.5, 38.5, 31.75, 'solid', colors['search'], 2)
    create_arrow(69, 48.5, 70.5, 31.75, 'solid', colors['search'], 2, 0.6)
    create_arrow(79, 48.5, 82.5, 31.75, 'solid', colors['search'], 2, 0.6)
    
    # Search to LLM (dashed)
    create_arrow(19, 50, 43, 42, 'dashed', colors['search'], 1.5, 0.5)
    create_arrow(29, 50, 43, 42, 'dashed', colors['search'], 1.5, 0.5)
    create_arrow(39, 50, 43, 42, 'dashed', colors['search'], 1.5, 0.5)
    create_arrow(49, 50, 43, 42, 'dashed', colors['search'], 1.5, 0.5)
    create_arrow(69, 50, 57, 42, 'dashed', colors['search'], 1.5, 0.4)
    create_arrow(79, 50, 57, 42, 'dashed', colors['search'], 1.5, 0.4)
    
    # LLM to Response
    create_arrow(64, 40, 64, 40, 'solid', colors['llm'], 3)
    
    # Response feedback loop (dashed)
    create_arrow(70, 38, 55, 85, 'dashed', colors['response'], 2, 0.4)
    create_arrow(70, 40, 57, 42, 'dashed', colors['response'], 2, 0.4)
    
    # ETL to Data Layer
    create_arrow(14.5, 16.5, 14.5, 11.5, 'solid', colors['etl'], 2)
    create_arrow(26.5, 16.5, 26.5, 11.5, 'solid', colors['etl'], 2)
    create_arrow(38.5, 16.5, 38.5, 11.5, 'solid', colors['etl'], 2)
    
    # Data Layer to Data Stores
    create_arrow(14.5, 11.5, 14.5, 31.75, 'solid', colors['data_layer'], 2)  # Embeddings -> OpenSearch
    create_arrow(26.5, 11.5, 26.5, 31.75, 'solid', colors['data_layer'], 2)  # Chunks -> OpenSearch
    create_arrow(38.5, 11.5, 26.5, 31.75, 'solid', colors['data_layer'], 2)  # GraphData -> TigerDB
    
    # ETL internal flow
    create_arrow(19.5, 19.5, 22.5, 19.5, 'solid', colors['etl'], 1.5)
    create_arrow(31.5, 19.5, 34.5, 19.5, 'solid', colors['etl'], 1.5)
    create_arrow(43.5, 19.5, 46.5, 19.5, 'solid', colors['etl'], 1.5)
    
    # Agent Features connections (dashed, subtle)
    create_arrow(85, 88.5, 25, 73.5, 'dashed', colors['feature'], 1.5, 0.4)  # Resiliency -> Agents
    create_arrow(85, 88.5, 25, 68.5, 'dashed', colors['feature'], 1.5, 0.4)
    create_arrow(85, 88.5, 55, 73.5, 'dashed', colors['feature'], 1.5, 0.4)
    create_arrow(85, 88.5, 55, 68.5, 'dashed', colors['feature'], 1.5, 0.4)
    create_arrow(85, 88.5, 55, 63.5, 'dashed', colors['feature'], 1.5, 0.4)
    create_arrow(85, 86.5, 25, 73.5, 'dashed', colors['feature'], 1.5, 0.4)  # Memory -> Agents
    create_arrow(85, 86.5, 25, 68.5, 'dashed', colors['feature'], 1.5, 0.4)
    create_arrow(85, 86.5, 55, 73.5, 'dashed', colors['feature'], 1.5, 0.4)
    create_arrow(85, 86.5, 55, 68.5, 'dashed', colors['feature'], 1.5, 0.4)
    create_arrow(85, 86.5, 55, 63.5, 'dashed', colors['feature'], 1.5, 0.4)
    create_arrow(85, 86.5, 57, 42, 'dashed', colors['feature'], 1.5, 0.4)  # Memory -> LLM
    
    # Add title
    title = ax.text(50, 98, 'System Architecture - ETL Pipeline & Agent Orchestration', 
                   fontsize=20, ha='center', va='top', weight='bold', 
                   color='#212121', zorder=10)
    title.set_path_effects([path_effects.withStroke(linewidth=4, foreground='white', alpha=0.8)])
    
    # Add legend
    legend_elements = [
        mpatches.Patch(facecolor=colors['primary_agent'], label='Primary Agents', edgecolor='white', linewidth=2),
        mpatches.Patch(facecolor=colors['secondary_agent'], label='Secondary Agents', edgecolor='white', linewidth=2),
        mpatches.Patch(facecolor=colors['data_store'], label='Data Stores', edgecolor='white', linewidth=2),
        mpatches.Patch(facecolor=colors['etl'], label='ETL Pipeline', edgecolor='white', linewidth=2),
        mpatches.Patch(facecolor=colors['llm'], label='LLM Reasoning', edgecolor='white', linewidth=2),
    ]
    ax.legend(handles=legend_elements, loc='upper left', fontsize=10, 
             framealpha=0.95, edgecolor='#666', fancybox=True, shadow=True)
    
    # Save figure
    plt.tight_layout()
    plt.savefig(output_path, format=format, dpi=dpi, bbox_inches='tight', 
                facecolor=colors['background'], edgecolor='none')
    print(f"✅ Architecture diagram saved to {output_path}")
    print(f"   Format: {format}, DPI: {dpi}")
    
    # Optionally show
    # plt.show()

def main():
    parser = argparse.ArgumentParser(description="Generate architecture diagram as image")
    parser.add_argument("--output", default="architecture.png", help="Output file path")
    parser.add_argument("--format", default="png", choices=["png", "svg", "pdf"], 
                       help="Output format (default: png)")
    parser.add_argument("--dpi", type=int, default=300, help="DPI for raster formats (default: 300)")
    parser.add_argument("--show", action="store_true", help="Display the diagram")
    
    args = parser.parse_args()
    
    create_architecture_diagram(args.output, args.format, args.dpi)
    
    if args.show:
        import matplotlib.pyplot as plt
        plt.show()

if __name__ == "__main__":
    main()

