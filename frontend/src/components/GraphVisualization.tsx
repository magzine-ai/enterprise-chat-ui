/**
 * Graph Visualization Component
 * 
 * Interactive graph visualization with zoom, pan, and node dragging
 * using react-force-graph-2d for better UX.
 */
import React, { useMemo, useCallback, useState } from 'react';
// @ts-ignore - react-force-graph-2d doesn't have types
import ForceGraph2D from 'react-force-graph-2d';
import './GraphVisualization.css';

interface Node {
  id: number;
  label: string;
  type: string;
  file_path?: string;
  repository_id?: number;
}

interface Edge {
  source: number;
  target: number;
  type?: string;
}

interface GraphVisualizationProps {
  nodes: Node[];
  edges: Edge[];
}

const GraphVisualization: React.FC<GraphVisualizationProps> = ({ nodes, edges }) => {
  const [hoveredNode, setHoveredNode] = useState<Node | null>(null);
  const [selectedNode, setSelectedNode] = useState<Node | null>(null);
  const [layoutMode, setLayoutMode] = useState<'force' | 'radial' | 'hierarchical'>('force');
  const [showLabels, setShowLabels] = useState<boolean>(false);
  const [spacing, setSpacing] = useState<number>(3); // Multiplier for edge distances
  const [filteredTypes, setFilteredTypes] = useState<Set<string>>(new Set(['method', 'class', 'file', 'module']));

  // Helper function to extract short name from FQN or path
  const getShortName = (label: string, type: string): string => {
    if (!label) return '';
    
    // For file paths, extract just the filename
    if (type === 'file' && label.includes('/')) {
      const parts = label.split('/');
      return parts[parts.length - 1] || label;
    }
    
    // For FQN (fully qualified names), extract just the class/method name
    if (label.includes('.')) {
      const parts = label.split('.');
      // Get the last part (method/class name)
      const shortName = parts[parts.length - 1];
      // If it's a method, it might have parameters - show just the name part
      if (shortName.includes('(')) {
        return shortName.split('(')[0];
      }
      return shortName;
    }
    
    // For simple names, return as is
    return label;
  };

  // Transform nodes and edges for react-force-graph
  const graphData = useMemo(() => {
    console.log('GraphVisualization render:', { 
      nodeCount: nodes.length, 
      edgeCount: edges.length
    });

    const getNodeColor = (type: string): string => {
      const colors: Record<string, string> = {
        method: '#4CAF50',
        class: '#2196F3',
        file: '#FF9800',
        module: '#9C27B0',
        unknown: '#757575',
      };
      return colors[type] || colors.unknown;
    };

    const getNodeSize = (type: string): number => {
      const sizes: Record<string, number> = {
        method: 3,
        class: 5,
        file: 4,
        module: 6,
        unknown: 3,
      };
      return sizes[type] || 3;
    };

    // Transform nodes - filter by type if needed
    const graphNodes = nodes
      .filter(node => filteredTypes.has(node.type))
      .map((node, index) => ({
        id: String(node.id),
        label: node.label, // Keep full label for tooltips and metadata
        shortLabel: getShortName(node.label, node.type), // Short name for display
        type: node.type,
        file_path: node.file_path,
        repository_id: node.repository_id,
        // Add visual properties
        color: getNodeColor(node.type),
        size: getNodeSize(node.type),
      }));

    const getEdgeColor = (type?: string): string => {
      const colors: Record<string, string> = {
        calls: '#666',
        imports: '#999',
        extends: '#2196F3',
        implements: '#9C27B0',
        belongs_to: '#4CAF50',
        in_file: '#FF9800',
        same_file: '#FF9800',
        related: '#ccc',
      };
      return colors[type || 'related'] || '#ccc';
    };

    // Transform edges - ensure source and target are strings and filtered
    const graphEdges = edges
      .filter(edge => {
        // Only include edges where both nodes exist and are in filtered set
        const sourceNode = nodes.find(n => n.id === edge.source);
        const targetNode = nodes.find(n => n.id === edge.target);
        return sourceNode && targetNode && 
               filteredTypes.has(sourceNode.type) && 
               filteredTypes.has(targetNode.type);
      })
      .map(edge => ({
        source: String(edge.source),
        target: String(edge.target),
        type: edge.type || 'related',
        color: getEdgeColor(edge.type),
      }));

    console.log('Graph data prepared:', {
      nodes: graphNodes.length,
      edges: graphEdges.length,
      sampleNodes: graphNodes.slice(0, 3),
      sampleEdges: graphEdges.slice(0, 3)
    });

    return {
      nodes: graphNodes,
      links: graphEdges,
    };
  }, [nodes, edges, filteredTypes, layoutMode]);

  const handleNodeHover = useCallback((node: any) => {
    setHoveredNode(node ? {
      id: parseInt(node.id),
      label: node.label,
      type: node.type,
      file_path: node.file_path,
      repository_id: node.repository_id,
    } : null);
  }, []);

  const handleNodeClick = useCallback((node: any) => {
    setSelectedNode(node ? {
      id: parseInt(node.id),
      label: node.label,
      type: node.type,
      file_path: node.file_path,
      repository_id: node.repository_id,
    } : null);
  }, []);

  if (nodes.length === 0) {
    return (
      <div className="graph-visualization-empty">
        No graph data to display. Enter a search query to visualize relationships.
      </div>
    );
  }

  return (
    <div className="graph-visualization-container">
      <div className="graph-visualization-wrapper">
        <ForceGraph2D
          graphData={graphData}
          nodeLabel={(node: any) => {
            // Show full details in tooltip (hover)
            const escapedLabel = node.label.replace(/</g, '&lt;').replace(/>/g, '&gt;');
            const escapedPath = node.file_path ? node.file_path.replace(/</g, '&lt;').replace(/>/g, '&gt;') : '';
            return `
            <div style="
              background: white;
              padding: 12px;
              border-radius: 6px;
              box-shadow: 0 4px 12px rgba(0,0,0,0.25);
              max-width: 400px;
              border: 2px solid ${node.color};
            ">
              <div style="font-weight: bold; font-size: 1.1em; margin-bottom: 6px; color: #333; word-break: break-word;">${escapedLabel}</div>
              <div style="font-size: 0.9em; color: #666; margin-bottom: 4px;">
                <span style="font-weight: 600;">Type:</span> <span style="text-transform: capitalize;">${node.type}</span>
              </div>
              ${escapedPath ? `<div style="font-size: 0.8em; color: #999; margin-top: 6px; padding-top: 6px; border-top: 1px solid #eee; word-break: break-all;">${escapedPath}</div>` : ''}
            </div>
          `;
          }}
          nodeColor={(node: any) => node.color}
          nodeVal={(node: any) => node.size}
          linkLabel={(link: any) => {
            const type = link.type || 'related';
            return `
            <div style="
              background: rgba(255, 255, 255, 0.95);
              padding: 4px 8px;
              border-radius: 4px;
              box-shadow: 0 2px 4px rgba(0,0,0,0.2);
              font-size: 0.75em;
              border: 1px solid ${link.color || '#ccc'};
            ">
              ${type}
            </div>
          `;
          }}
          linkColor={(link: any) => link.color}
          linkWidth={(link: any) => {
            // Thicker lines for important relationships
            const widths: Record<string, number> = {
              belongs_to: 4,
              in_file: 3.5,
              calls: 3.5,
              extends: 4,
              implements: 4,
            };
            return widths[link.type] || 3;
          }}
          linkDirectionalArrowLength={8}
          linkDirectionalArrowRelPos={0.88}
          linkDirectionalArrowColor={(link: any) => link.color}
          linkDirectionalArrowWidth={3}
          linkCurvature={0.3}
          linkOpacity={0.7}
          linkDirectionalParticles={2}
          linkDirectionalParticleWidth={3}
          linkDirectionalParticleSpeed={0.01}
          linkCanvasObjectMode={() => 'after'}
          linkCanvasObject={(link: any, ctx: CanvasRenderingContext2D, globalScale: number) => {
            // Draw edge type as simple small text (no box, no padding) - half size
            const type = link.type || 'related';
            const fontSize = Math.max(3.5, Math.min(4.5, 4 / Math.sqrt(globalScale)));
            ctx.font = `${fontSize}px -apple-system, BlinkMacSystemFont, 'Segoe UI', 'Roboto', 'Oxygen', 'Ubuntu', 'Cantarell', sans-serif`;
            ctx.textAlign = 'center';
            ctx.textBaseline = 'middle';
            
            // Get source and target node positions
            const source = link.source;
            const target = link.target;
            
            // Calculate midpoint of the edge
            const midX = (source.x + target.x) / 2;
            const midY = (source.y + target.y) / 2;
            
            // Draw text only - no background, no border
            ctx.fillStyle = link.color || '#666';
            ctx.fillText(type, midX, midY);
          }}
          onNodeHover={handleNodeHover}
          onNodeClick={handleNodeClick}
          nodeCanvasObjectMode={() => showLabels ? 'after' : 'replace'}
          nodeCanvasObject={(node: any, ctx: CanvasRenderingContext2D, globalScale: number) => {
            // Draw the node circle with proper fill and border
            const nodeSize = node.size || 3;
            const borderWidth = 1;
            
            // Draw filled circle with border in one go
            ctx.beginPath();
            ctx.arc(node.x, node.y, nodeSize, 0, 2 * Math.PI);
            ctx.fillStyle = node.color || '#999';
            ctx.fill();
            ctx.strokeStyle = '#000';
            ctx.lineWidth = borderWidth;
            ctx.stroke();
            
            // Only draw label if showLabels is true or node is hovered/selected
            const shouldShowLabel = showLabels || 
                                   (hoveredNode && parseInt(hoveredNode.id.toString()) === parseInt(node.id)) ||
                                   (selectedNode && parseInt(selectedNode.id.toString()) === parseInt(node.id));
            
            if (shouldShowLabel) {
              // Use short label for display (just method/class name, not full path/FQN)
              const displayLabel = node.shortLabel || getShortName(node.label, node.type);
              // Small font size similar to edge type (no box, no padding)
              const fontSize = Math.max(4, Math.min(5, 4.5 / Math.sqrt(globalScale)));
              ctx.font = `${fontSize}px -apple-system, BlinkMacSystemFont, 'Segoe UI', 'Roboto', 'Oxygen', 'Ubuntu', 'Cantarell', sans-serif`;
              ctx.textAlign = 'center';
              ctx.textBaseline = 'middle';
              
              // Use short label
              const text = displayLabel;
              const nodeSize = node.size || 3;
              
              // Draw text only - no background, no border, no padding
              ctx.fillStyle = node.color || '#333';
              ctx.fillText(text, node.x, node.y + nodeSize + 5);
            }
          }}
          cooldownTicks={150}
          onEngineStop={() => console.log('Graph layout stabilized')}
          // Force simulation parameters for better layout
          d3Force={layoutMode === 'radial' ? {
            // Radial layout - arrange nodes in circles
            radial: {
              radius: (node: any) => {
                const typeOrder: Record<string, number> = {
                  class: 1,
                  file: 2,
                  method: 3,
                  module: 1.5,
                };
                return (typeOrder[node.type] || 2.5) * 100 * spacing;
              },
              strength: 0.8,
            },
            link: {
              distance: (link: any) => {
                const distances: Record<string, number> = {
                  belongs_to: 180,  // 60 * 3
                  in_file: 150,     // 50 * 3
                  same_file: 120,   // 40 * 3
                  calls: 300,       // 100 * 3
                  imports: 360,     // 120 * 3
                  extends: 450,     // 150 * 3
                  implements: 450,  // 150 * 3
                };
                return (distances[link.type] || 300) * spacing;  // 100 * 3
              },
              strength: 0.3,
            },
            charge: {
              strength: -800 * spacing,
            },
            center: {
              strength: 0.1,
            },
          } : layoutMode === 'hierarchical' ? {
            // Hierarchical layout - arrange by type
            link: {
              distance: (link: any) => {
                const distances: Record<string, number> = {
                  belongs_to: 240,  // 80 * 3
                  in_file: 210,     // 70 * 3
                  same_file: 180,   // 60 * 3
                  calls: 360,       // 120 * 3
                  imports: 450,     // 150 * 3
                  extends: 600,     // 200 * 3
                  implements: 600,  // 200 * 3
                };
                return (distances[link.type] || 360) * spacing;  // 120 * 3
              },
              strength: 0.8,
            },
            charge: {
              strength: (node: any) => {
                return -1200 * spacing;
              },
            },
            center: {
              strength: 0.05,
            },
            collision: {
              radius: (node: any) => {
                return ((node.size || 5) + 20) * spacing;
              },
              strength: 1.0,
            },
          } : {
            // Force-directed layout with much stronger repulsion
            link: {
              distance: (link: any) => {
                const distances: Record<string, number> = {
                  belongs_to: 300,   // 100 * 3
                  in_file: 270,      // 90 * 3
                  same_file: 210,    // 70 * 3
                  calls: 450,        // 150 * 3
                  imports: 540,      // 180 * 3
                  extends: 660,      // 220 * 3
                  implements: 660,   // 220 * 3
                };
                return (distances[link.type] || 450) * spacing;  // 150 * 3
              },
              strength: 0.6,
            },
            charge: {
              strength: (node: any) => {
                // Much stronger repulsion - scales with spacing
                const baseStrength = -2000;
                return baseStrength * spacing * (node.size ? (node.size / 5) : 1);
              },
            },
            center: {
              strength: 0.02,
            },
            collision: {
              radius: (node: any) => {
                // Larger collision radius to prevent overlap
                return ((node.size || 5) + 40) * spacing;
              },
              strength: 1.2,
            },
          }}
          // Enable zoom and pan
          minZoom={0.1}
          maxZoom={4}
          enableZoomInteraction={true}
          enablePanInteraction={true}
          enableNodeDrag={true}
          // Better layout stabilization
          warmupTicks={100}
          cooldownTicks={Infinity}
        />
      </div>
      
      {/* Legend */}
      <div className="graph-legend">
        <div className="legend-title">Node Types</div>
        <div className="legend-item">
          <span className="legend-color" style={{ background: '#4CAF50' }}></span>
          <span>Method</span>
        </div>
        <div className="legend-item">
          <span className="legend-color" style={{ background: '#2196F3' }}></span>
          <span>Class</span>
        </div>
        <div className="legend-item">
          <span className="legend-color" style={{ background: '#FF9800' }}></span>
          <span>File</span>
        </div>
        <div className="legend-item">
          <span className="legend-color" style={{ background: '#9C27B0' }}></span>
          <span>Module</span>
        </div>
        <div style={{ marginTop: '0.75rem', paddingTop: '0.75rem', borderTop: '1px solid #e0e0e0' }}>
          <div className="legend-title" style={{ fontSize: '0.7rem', marginBottom: '0.5rem' }}>Controls</div>
          <button
            className="layout-toggle-btn"
            onClick={() => setShowLabels(!showLabels)}
            title="Toggle node labels"
            style={{ marginBottom: '0.5rem' }}
          >
            {showLabels ? '👁️ Hide Labels' : '👁️ Show Labels'}
          </button>
          <button
            className="layout-toggle-btn"
            onClick={() => {
              const modes: Array<'force' | 'radial' | 'hierarchical'> = ['force', 'radial', 'hierarchical'];
              const currentIndex = modes.indexOf(layoutMode);
              setLayoutMode(modes[(currentIndex + 1) % modes.length]);
            }}
            title="Toggle layout mode"
            style={{ marginBottom: '0.5rem' }}
          >
            {layoutMode === 'force' ? '🔄 Radial' : layoutMode === 'radial' ? '🔄 Hierarchical' : '🔄 Force'}
          </button>
          <div style={{ marginTop: '0.5rem', marginBottom: '0.5rem' }}>
            <label style={{ fontSize: '0.7rem', display: 'block', marginBottom: '0.25rem' }}>Spacing: {spacing}x</label>
            <input
              type="range"
              min="1"
              max="8"
              step="0.5"
              value={spacing}
              onChange={(e) => setSpacing(parseFloat(e.target.value))}
              style={{ width: '100%' }}
            />
          </div>
          <div style={{ marginTop: '0.75rem', paddingTop: '0.75rem', borderTop: '1px solid #e0e0e0' }}>
            <div className="legend-title" style={{ fontSize: '0.7rem', marginBottom: '0.5rem' }}>Filter Nodes</div>
            {['method', 'class', 'file', 'module'].map(type => (
              <label key={type} style={{ display: 'flex', alignItems: 'center', gap: '0.5rem', fontSize: '0.7rem', marginBottom: '0.25rem', cursor: 'pointer' }}>
                <input
                  type="checkbox"
                  checked={filteredTypes.has(type)}
                  onChange={(e) => {
                    const newFiltered = new Set(filteredTypes);
                    if (e.target.checked) {
                      newFiltered.add(type);
                    } else {
                      newFiltered.delete(type);
                    }
                    setFilteredTypes(newFiltered);
                  }}
                />
                <span style={{ textTransform: 'capitalize' }}>{type}</span>
              </label>
            ))}
          </div>
        </div>
      </div>

      {/* Controls */}
      <div className="graph-controls">
        <div className="control-hint">
          <div>🖱️ Drag nodes to reposition</div>
          <div>🔍 Scroll to zoom</div>
          <div>👆 Click node for details</div>
        </div>
      </div>

      {/* Node Info Panel */}
      {(hoveredNode || selectedNode) && (
        <div className="graph-node-info">
          <div className="node-info-header">
            <strong>{(selectedNode || hoveredNode)?.label}</strong>
            {selectedNode && (
              <button 
                className="close-info-btn"
                onClick={() => setSelectedNode(null)}
              >
                ×
              </button>
            )}
          </div>
          <div className="node-info-details">
            <div><strong>Type:</strong> {(selectedNode || hoveredNode)?.type}</div>
            {(selectedNode || hoveredNode)?.file_path && (
              <div><strong>File:</strong> {(selectedNode || hoveredNode)?.file_path}</div>
            )}
          </div>
        </div>
      )}
    </div>
  );
};

export default GraphVisualization;
