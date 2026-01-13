"""
Generate a visually appealing architecture diagram as an image.

This script creates a high-quality visual representation of the system architecture
using matplotlib for better UX and visual appeal with neatly organized arrows.

Usage:
    python generate_architecture_diagram.py --output architecture.png
    python generate_architecture_diagram.py --output architecture.svg --format svg
"""

import argparse
import matplotlib.pyplot as plt
import matplotlib.patches as mpatches
from matplotlib.patches import FancyBboxPatch, FancyArrowPatch, Circle, Rectangle, Ellipse
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
    fig, ax = plt.subplots(1, 1, figsize=(24, 16), facecolor='#FAFAFA')
    ax.set_xlim(0, 100)
    ax.set_ylim(0, 100)
    ax.axis('off')
    
    # Color palette - modern, accessible colors
    colors = {
        'ui': '#1976D2',
        'backend': '#7B1FA2',
        'orchestrator': '#388E3C',
        'agent': '#1976D2',
        'rag': '#7B1FA2',
        'llm': '#C62828',
        'data_store': '#0277BD',
        'external_data': '#F57C00',
        'tool': '#E65100',
        'etl': '#00695C',
        'background': '#FAFAFA',
        'arrow': '#424242',
        'arrow_highlight': '#1976D2'
    }
    
    # Helper function to create rounded rectangle boxes with icons
    def create_box(x, y, width, height, label, color, icon='', subtext='', icon_size=16):
        """Create a styled box with icon and text."""
        # Main box with rounded corners
        box = FancyBboxPatch(
            (x - width/2, y - height/2), width, height,
            boxstyle="round,pad=0.6", 
            facecolor=color,
            edgecolor='white',
            linewidth=2.5,
            zorder=2,
            alpha=0.95
        )
        ax.add_patch(box)
        
        # Add shadow effect
        shadow = FancyBboxPatch(
            (x - width/2 + 0.4, y - height/2 - 0.4), width, height,
            boxstyle="round,pad=0.6",
            facecolor='black',
            alpha=0.15,
            zorder=1
        )
        ax.add_patch(shadow)
        
        # Add icon (text-based for tools)
        if icon:
            ax.text(x, y + height/3.5, icon, fontsize=icon_size, ha='center', va='center', 
                   zorder=3, weight='bold', color='white')
        
        # Add main label
        text = ax.text(x, y, label, fontsize=10, ha='center', va='center', 
                      weight='bold', zorder=3, color='white')
        text.set_path_effects([path_effects.withStroke(linewidth=4, foreground='black', alpha=0.4)])
        
        # Add subtext
        if subtext:
            ax.text(x, y - height/3.5, subtext, fontsize=7, ha='center', va='center',
                   zorder=3, color='white', alpha=0.95, wrap=True)
        
        return box
    
    # Helper function to create arrows with better styling
    def create_arrow(x1, y1, x2, y2, style='solid', color='#666', width=2, alpha=0.8, label='', label_offset=0):
        """Create a styled arrow with optional label."""
        # Calculate arrow path with slight curve for better visual appeal
        mid_x = (x1 + x2) / 2
        mid_y = (y1 + y2) / 2
        
        # Add slight curve for longer arrows
        if abs(x2 - x1) > 10 or abs(y2 - y1) > 10:
            # Bezier-like curve
            control_x = mid_x + (y2 - y1) * 0.1
            control_y = mid_y - (x2 - x1) * 0.1
            path = [(x1, y1), (control_x, control_y), (x2, y2)]
        else:
            path = [(x1, y1), (x2, y2)]
        
        if style == 'solid':
            arrow = FancyArrowPatch(
                (x1, y1), (x2, y2),
                arrowstyle='->', mutation_scale=25,
                color=color, linewidth=width, alpha=alpha, zorder=1,
                connectionstyle='arc3,rad=0.1' if abs(x2 - x1) > 10 else 'arc3,rad=0'
            )
        else:  # dashed
            arrow = FancyArrowPatch(
                (x1, y1), (x2, y2),
                arrowstyle='->', mutation_scale=25,
                color=color, linewidth=width, alpha=alpha, 
                linestyle='--', zorder=1,
                connectionstyle='arc3,rad=0.1' if abs(x2 - x1) > 10 else 'arc3,rad=0'
            )
        ax.add_patch(arrow)
        
        # Add label if provided
        if label:
            label_x = mid_x + label_offset
            label_y = mid_y + label_offset
            ax.text(label_x, label_y, label, fontsize=7, ha='center', va='center',
                   bbox=dict(boxstyle='round,pad=0.3', facecolor='white', alpha=0.8, edgecolor=color),
                   zorder=4, color=color, weight='bold')
        
        return arrow
    
    # ========== LAYER 1: UI LAYER (Top) ==========
    create_box(50, 95, 14, 3.5, 'React UI', colors['ui'], '⚛️', 'Chat Interface • WebSocket • Activity Indicators', 18)
    
    # ========== LAYER 2: BACKEND LAYER ==========
    create_box(30, 85, 12, 3.5, 'FastAPI', colors['backend'], '🚀', 'REST API • WebSocket • Jobs', 16)
    create_box(70, 85, 12, 3.5, 'Orchestrator', colors['orchestrator'], '🎯', 'Agent Routing • Workflow', 16)
    
    # ========== LAYER 3: AGENTS ==========
    create_box(15, 72, 10, 3, 'API Discovery', colors['agent'], '🔍', 'RAG Search')
    create_box(15, 67, 10, 3, 'Splunk Agent', colors['agent'], 'SPL', 'Log Analysis')
    create_box(50, 72, 10, 3, 'Code Analyzer', colors['agent'], '💻', 'Code Intelligence')
    create_box(50, 67, 10, 3, 'JIRA Agent', colors['agent'], 'JIRA', 'Issue Tracking')
    create_box(50, 62, 10, 3, 'SNOW Agent', colors['agent'], 'SNOW', 'ITSM')
    
    # ========== LAYER 4: RAG & LLM ==========
    create_box(35, 50, 12, 4, 'RAG', colors['rag'], '🔎', 'Retrieval Augmented\nGeneration', 18)
    create_box(70, 50, 12, 4, 'LLM', colors['llm'], '🧠', 'OpenAI/Claude\nSynthesis & Analysis', 18)
    
    # ========== LAYER 5: DATA STORES ==========
    create_box(10, 30, 10, 3.5, 'VectorDB', colors['data_store'], '🔍', 'OpenSearch\nVector + Metadata')
    create_box(25, 30, 10, 3.5, 'TigerDB', colors['data_store'], 'TDB', 'Graph Database\nNetworkX')
    create_box(40, 30, 10, 3.5, 'Aurora', colors['data_store'], 'AURORA', 'AWS Aurora\nPostgreSQL')
    
    # ========== LAYER 6: EXTERNAL DATA SOURCES ==========
    create_box(60, 30, 10, 3.5, 'Splunk', colors['external_data'], 'SPL', 'Logs & Metrics')
    create_box(75, 30, 10, 3.5, 'JIRA', colors['external_data'], 'JIRA', 'Issues & Metrics')
    create_box(90, 30, 10, 3.5, 'ServiceNow', colors['external_data'], 'SNOW', 'Tickets & Metrics')
    
    # ========== LAYER 7: TOOLS ==========
    create_box(60, 15, 10, 3, 'Splunk API', colors['tool'], 'SPL', 'External API')
    create_box(75, 15, 10, 3, 'JIRA API', colors['tool'], 'JIRA', 'External API')
    create_box(90, 15, 10, 3, 'SNOW API', colors['tool'], 'SNOW', 'External API')
    
    # ========== LAYER 8: ETL PIPELINE (Left Side) ==========
    create_box(10, 15, 9, 3, 'Code Parser', colors['etl'], '📝', 'AST Extraction')
    create_box(22, 15, 9, 3, 'Chunking', colors['etl'], '✂️', 'Strategy-based')
    create_box(34, 15, 9, 3, 'Embedding', colors['etl'], '🧮', 'Azure/OpenAI')
    create_box(46, 15, 9, 3, 'Graph Builder', colors['etl'], 'TDB', 'NetworkX/TigerDB')
    
    # ========== ARROWS - UI to Backend ==========
    create_arrow(50, 93.25, 36, 86.75, 'solid', colors['arrow_highlight'], 3, 0.9, 'HTTP/WS')
    create_arrow(36, 85.25, 50, 93.25, 'solid', colors['arrow_highlight'], 3, 0.9, 'WebSocket')
    
    # ========== ARROWS - Backend to Orchestrator ==========
    create_arrow(36, 85.25, 64, 86.75, 'solid', colors['backend'], 2.5, 0.8)
    
    # ========== ARROWS - Orchestrator to Agents ==========
    create_arrow(64, 85.25, 20, 73.5, 'solid', colors['orchestrator'], 2.5, 0.8)
    create_arrow(64, 85.25, 20, 68.5, 'solid', colors['orchestrator'], 2.5, 0.8)
    create_arrow(64, 85.25, 55, 73.5, 'solid', colors['orchestrator'], 2.5, 0.8)
    create_arrow(64, 85.25, 55, 68.5, 'solid', colors['orchestrator'], 2.5, 0.8)
    create_arrow(64, 85.25, 55, 63.5, 'solid', colors['orchestrator'], 2.5, 0.8)
    
    # ========== ARROWS - Agents to RAG ==========
    create_arrow(20, 70.5, 29, 52, 'solid', colors['agent'], 2, 0.7, 'Query')
    create_arrow(55, 70.5, 29, 52, 'solid', colors['agent'], 2, 0.7, 'Query')
    
    # ========== ARROWS - Data Stores to RAG ==========
    create_arrow(15, 31.75, 29, 48, 'solid', colors['data_store'], 2.5, 0.8, 'Vector Search')
    create_arrow(30, 31.75, 29, 48, 'solid', colors['data_store'], 2, 0.7, 'Graph Query')
    
    # ========== ARROWS - RAG to LLM ==========
    create_arrow(41, 50, 64, 52, 'solid', colors['rag'], 3, 0.9, 'Context')
    
    # ========== ARROWS - LLM to Agents ==========
    create_arrow(76, 50, 20, 68.5, 'solid', colors['llm'], 2.5, 0.8, 'Response')
    
    # ========== ARROWS - Agents to External Tools ==========
    create_arrow(20, 65.5, 65, 31.75, 'solid', colors['tool'], 2, 0.7, 'Query')
    create_arrow(55, 65.5, 80, 31.75, 'solid', colors['tool'], 2, 0.7, 'Query')
    create_arrow(55, 60.5, 95, 31.75, 'solid', colors['tool'], 2, 0.7, 'Query')
    
    # ========== ARROWS - Agents to Tool APIs ==========
    create_arrow(20, 65.5, 65, 16.5, 'solid', colors['tool'], 2, 0.7)
    create_arrow(55, 65.5, 80, 16.5, 'solid', colors['tool'], 2, 0.7)
    create_arrow(55, 60.5, 95, 16.5, 'solid', colors['tool'], 2, 0.7)
    
    # ========== ARROWS - Tool APIs to External Data ==========
    create_arrow(65, 13.5, 65, 28.25, 'solid', colors['tool'], 2, 0.6)
    create_arrow(80, 13.5, 80, 28.25, 'solid', colors['tool'], 2, 0.6)
    create_arrow(95, 13.5, 95, 28.25, 'solid', colors['tool'], 2, 0.6)
    
    # ========== ARROWS - Tool Results to Code Analyzer ==========
    create_arrow(65, 16.5, 50, 70.5, 'solid', colors['tool'], 2, 0.7, 'Results')
    
    # ========== ARROWS - Backend to Data Stores ==========
    create_arrow(36, 83.25, 15, 31.75, 'dashed', colors['data_store'], 2, 0.6, 'Query')
    create_arrow(36, 83.25, 30, 31.75, 'dashed', colors['data_store'], 2, 0.6, 'Query')
    create_arrow(36, 83.25, 45, 31.75, 'solid', colors['data_store'], 2.5, 0.8, 'Read/Write')
    
    # ========== ARROWS - LLM Response to Backend ==========
    create_arrow(76, 48, 36, 86.75, 'solid', colors['llm'], 2.5, 0.8, 'Response')
    
    # ========== ARROWS - Backend to UI ==========
    create_arrow(36, 86.75, 50, 93.25, 'solid', colors['ui'], 3, 0.9, 'Display')
    
    # ========== ARROWS - ETL Pipeline Flow ==========
    create_arrow(14.5, 16.5, 22.5, 16.5, 'solid', colors['etl'], 2, 0.7)
    create_arrow(26.5, 16.5, 34.5, 16.5, 'solid', colors['etl'], 2, 0.7)
    create_arrow(38.5, 16.5, 46.5, 16.5, 'solid', colors['etl'], 2, 0.7)
    
    # ========== ARROWS - ETL to Data Stores ==========
    create_arrow(14.5, 16.5, 15, 31.75, 'solid', colors['etl'], 2, 0.7, 'Chunks')
    create_arrow(26.5, 16.5, 15, 31.75, 'solid', colors['etl'], 2, 0.7, 'Embeddings')
    create_arrow(38.5, 16.5, 30, 31.75, 'solid', colors['etl'], 2, 0.7, 'Graph Data')
    
    # ========== Add title ==========
    title = ax.text(50, 98.5, 'Enterprise Chat System Architecture', 
                   fontsize=24, ha='center', va='top', weight='bold', 
                   color='#212121', zorder=10)
    title.set_path_effects([path_effects.withStroke(linewidth=5, foreground='white', alpha=0.9)])
    
    # ========== Add layer labels ==========
    layer_labels = [
        (5, 96.5, 'UI Layer', colors['ui']),
        (5, 86.5, 'Backend Layer', colors['backend']),
        (5, 73.5, 'Agents Layer', colors['agent']),
        (5, 52, 'Processing Layer', colors['rag']),
        (5, 32, 'Data Stores', colors['data_store']),
        (55, 32, 'External Data', colors['external_data']),
        (55, 16.5, 'Tools & ETL', colors['tool'])
    ]
    
    for x, y, label, color in layer_labels:
        ax.text(x, y, label, fontsize=11, ha='left', va='center', 
               weight='bold', color=color, zorder=10,
               bbox=dict(boxstyle='round,pad=0.5', facecolor='white', alpha=0.9, edgecolor=color, linewidth=2))
    
    # ========== Add legend ==========
    legend_elements = [
        mpatches.Patch(facecolor=colors['ui'], label='Frontend Layer', edgecolor='white', linewidth=2),
        mpatches.Patch(facecolor=colors['backend'], label='Backend Layer', edgecolor='white', linewidth=2),
        mpatches.Patch(facecolor=colors['agent'], label='Agents', edgecolor='white', linewidth=2),
        mpatches.Patch(facecolor=colors['data_store'], label='Data Stores', edgecolor='white', linewidth=2),
        mpatches.Patch(facecolor=colors['external_data'], label='External Data', edgecolor='white', linewidth=2),
        mpatches.Patch(facecolor=colors['tool'], label='Tools & APIs', edgecolor='white', linewidth=2),
        mpatches.Patch(facecolor=colors['rag'], label='RAG/LLM', edgecolor='white', linewidth=2),
    ]
    ax.legend(handles=legend_elements, loc='upper right', fontsize=9, 
             framealpha=0.95, edgecolor='#666', fancybox=True, shadow=True, ncol=2)
    
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
