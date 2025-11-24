/**
 * DiagramViewer Component
 * 
 * Renders workflow diagrams, architecture diagrams, and AWS architecture diagrams.
 * Supports Mermaid diagrams, SVG diagrams, and custom diagram types.
 * 
 * @example
 * ```tsx
 * <DiagramViewer
 *   type="mermaid"
 *   diagram={`
 *     graph TD
 *       A[Start] --> B[Process]
 *       B --> C[End]
 *   `}
 *   title="Workflow Diagram"
 * />
 * ```
 */
import React, { useState, useEffect, useRef } from 'react';
import mermaid from 'mermaid';

export type DiagramType = 'mermaid' | 'svg' | 'aws' | 'flowchart' | 'sequence' | 'architecture';

interface DiagramViewerProps {
  type: DiagramType;
  diagram: string; // Mermaid code, SVG markup, or diagram data
  title?: string;
  description?: string;
  width?: number | string;
  height?: number | string;
  interactive?: boolean;
  showControls?: boolean;
  theme?: 'light' | 'dark';
}

const DiagramViewer: React.FC<DiagramViewerProps> = ({
  type,
  diagram,
  title,
  description,
  width = '100%',
  height = 'auto',
  interactive = true,
  showControls = true,
  theme = 'light',
}) => {
  const [error, setError] = useState<string | null>(null);
  const [isLoading, setIsLoading] = useState(true);
  const diagramRef = useRef<HTMLDivElement>(null);
  const mermaidRef = useRef<HTMLDivElement>(null);
  const [zoom, setZoom] = useState(1);
  const [pan, setPan] = useState({ x: 0, y: 0 });
  const [isDragging, setIsDragging] = useState(false);
  const [dragStart, setDragStart] = useState({ x: 0, y: 0 });
  const [mermaidId] = useState(() => `mermaid-${Math.random().toString(36).substr(2, 9)}`);

  useEffect(() => {
    // Initialize Mermaid once
    mermaid.initialize({
      startOnLoad: false,
      theme: theme === 'dark' ? 'dark' : 'default',
      securityLevel: 'loose',
      flowchart: {
        useMaxWidth: true,
        htmlLabels: true,
        curve: 'basis',
      },
    });
  }, [theme]);

  useEffect(() => {
    if (type !== 'mermaid') {
      setIsLoading(false);
      return;
    }

    setIsLoading(true);
    setError(null);

    // Wait for ref to be available and DOM to be ready
    const renderDiagram = async () => {
      // Check if ref is available, if not wait a bit
      if (!mermaidRef.current) {
        setTimeout(renderDiagram, 100);
        return;
      }

      try {
        // Clear previous content
        mermaidRef.current.innerHTML = '';
        mermaidRef.current.removeAttribute('data-processed');
        
        // Create a unique ID for this diagram
        const diagramId = `mermaid-${mermaidId}-${Date.now()}`;
        
        console.log('Rendering Mermaid diagram with ID:', diagramId);
        console.log('Diagram code:', diagram);
        
        // Parse and render the diagram
        const result = await mermaid.render(diagramId, diagram);
        console.log('Mermaid render result:', result);
        
        if (mermaidRef.current && result.svg) {
          mermaidRef.current.innerHTML = result.svg;
          setIsLoading(false);
          setError(null);
        } else {
          throw new Error('Mermaid render returned no SVG');
        }
      } catch (err: any) {
        console.error('Mermaid rendering error:', err);
        console.error('Error details:', err);
        setError(err.message || 'Failed to render Mermaid diagram');
        setIsLoading(false);
        
        // Show the diagram code in case of error
        if (mermaidRef.current) {
          mermaidRef.current.innerHTML = `
            <div style="padding: 1rem; background: var(--bg-secondary); border-radius: 6px;">
              <p style="color: #dc2626; margin-bottom: 0.5rem;">Error: ${err.message || 'Failed to render'}</p>
              <details>
                <summary style="cursor: pointer; color: var(--text-primary);">Show diagram code</summary>
                <pre style="margin-top: 0.5rem; padding: 0.5rem; background: var(--bg-primary); border-radius: 4px; overflow: auto; font-size: 0.875rem;">${diagram}</pre>
              </details>
            </div>
          `;
        }
      }
    };

    // Use requestAnimationFrame to ensure DOM is ready
    requestAnimationFrame(() => {
      setTimeout(renderDiagram, 100);
    });
  }, [type, diagram, mermaidId, theme]);

  const handleZoomIn = () => {
    setZoom((prev) => Math.min(prev + 0.1, 2));
  };

  const handleZoomOut = () => {
    setZoom((prev) => Math.max(prev - 0.1, 0.5));
  };

  const handleReset = () => {
    setZoom(1);
    setPan({ x: 0, y: 0 });
  };

  const handleMouseDown = (e: React.MouseEvent) => {
    if (!interactive) return;
    setIsDragging(true);
    setDragStart({ x: e.clientX - pan.x, y: e.clientY - pan.y });
  };

  const handleMouseMove = (e: React.MouseEvent) => {
    if (!isDragging || !interactive) return;
    setPan({
      x: e.clientX - dragStart.x,
      y: e.clientY - dragStart.y,
    });
  };

  const handleMouseUp = () => {
    setIsDragging(false);
  };

  const renderMermaid = () => {
    return (
      <div className="diagram-mermaid">
        <div 
          ref={mermaidRef}
          className="diagram-mermaid-container"
          style={{ minHeight: '200px' }}
        />
        {error && (
          <div className="diagram-error">
            Error rendering diagram: {error}
            <details style={{ marginTop: '0.5rem', fontSize: '0.875rem' }}>
              <summary>Show diagram code</summary>
              <pre style={{ 
                marginTop: '0.5rem', 
                padding: '0.5rem', 
                background: 'var(--bg-secondary)', 
                borderRadius: '4px',
                overflow: 'auto'
              }}>
                {diagram}
              </pre>
            </details>
          </div>
        )}
      </div>
    );
  };

  const renderSVG = () => {
    try {
      return (
        <div
          className="diagram-svg"
          dangerouslySetInnerHTML={{ __html: diagram }}
        />
      );
    } catch (err) {
      setError('Invalid SVG markup');
      return null;
    }
  };

  const renderAWS = () => {
    // AWS Architecture Diagram
    // Parse diagram data and render AWS-style components
    const components = diagram.split('\n').filter((line) => line.trim());
    
    return (
      <div className="diagram-aws">
        <svg viewBox="0 0 800 600" className="diagram-aws-svg">
          <defs>
            <linearGradient id="aws-gradient" x1="0%" y1="0%" x2="100%" y2="100%">
              <stop offset="0%" stopColor="#FF9900" />
              <stop offset="100%" stopColor="#FF6600" />
            </linearGradient>
          </defs>
          
          {/* Sample AWS components */}
          {components.map((component, idx) => {
            const x = 100 + (idx % 3) * 200;
            const y = 100 + Math.floor(idx / 3) * 150;
            
            return (
              <g key={idx}>
                <rect
                  x={x}
                  y={y}
                  width="120"
                  height="80"
                  rx="4"
                  fill="url(#aws-gradient)"
                  stroke="#333"
                  strokeWidth="2"
                />
                <text
                  x={x + 60}
                  y={y + 45}
                  textAnchor="middle"
                  fill="white"
                  fontSize="12"
                  fontWeight="bold"
                >
                  {component.trim()}
                </text>
              </g>
            );
          })}
        </svg>
      </div>
    );
  };

  const renderFlowchart = () => {
    // Simple flowchart rendering
    const nodes = diagram.split('\n').filter((line) => line.trim());
    
    return (
      <div className="diagram-flowchart">
        {nodes.map((node, idx) => (
          <div key={idx} className="diagram-flowchart-node">
            <div className="diagram-flowchart-node-content">{node.trim()}</div>
            {idx < nodes.length - 1 && (
              <div className="diagram-flowchart-arrow">↓</div>
            )}
          </div>
        ))}
      </div>
    );
  };

  const renderSequence = () => {
    // Sequence diagram rendering
    const lines = diagram.split('\n').filter((line) => line.trim());
    
    return (
      <div className="diagram-sequence">
        {lines.map((line, idx) => (
          <div key={idx} className="diagram-sequence-line">
            <span className="diagram-sequence-actor">Actor</span>
            <span className="diagram-sequence-message">{line.trim()}</span>
            <span className="diagram-sequence-actor">System</span>
          </div>
        ))}
      </div>
    );
  };

  const renderArchitecture = () => {
    // Generic architecture diagram
    return (
      <div className="diagram-architecture">
        <div className="diagram-architecture-layers">
          {['Presentation', 'Application', 'Data'].map((layer, idx) => (
            <div key={idx} className="diagram-architecture-layer">
              <div className="diagram-architecture-layer-title">{layer}</div>
              <div className="diagram-architecture-components">
                {diagram.split('\n').filter((line) => line.trim()).slice(idx * 2, (idx + 1) * 2).map((comp, compIdx) => (
                  <div key={compIdx} className="diagram-architecture-component">
                    {comp.trim()}
                  </div>
                ))}
              </div>
            </div>
          ))}
        </div>
      </div>
    );
  };

  const renderDiagram = () => {
    switch (type) {
      case 'mermaid':
        return renderMermaid();
      case 'svg':
        return renderSVG();
      case 'aws':
        return renderAWS();
      case 'flowchart':
        return renderFlowchart();
      case 'sequence':
        return renderSequence();
      case 'architecture':
        return renderArchitecture();
      default:
        return <div className="diagram-unknown">Unknown diagram type: {type}</div>;
    }
  };

  return (
    <div className="diagram-viewer-wrapper">
      {title && <h3 className="diagram-title">{title}</h3>}
      {description && <p className="diagram-description">{description}</p>}

      {showControls && (
        <div className="diagram-controls">
          <button className="diagram-control-button" onClick={handleZoomIn} title="Zoom In">
            <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
              <circle cx="11" cy="11" r="8" />
              <line x1="21" y1="21" x2="16.65" y2="16.65" />
              <line x1="11" y1="8" x2="11" y2="14" />
              <line x1="8" y1="11" x2="14" y2="11" />
            </svg>
          </button>
          <button className="diagram-control-button" onClick={handleZoomOut} title="Zoom Out">
            <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
              <circle cx="11" cy="11" r="8" />
              <line x1="21" y1="21" x2="16.65" y2="16.65" />
              <line x1="8" y1="11" x2="14" y2="11" />
            </svg>
          </button>
          <button className="diagram-control-button" onClick={handleReset} title="Reset">
            <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
              <path d="M3 12a9 9 0 0 1 9-9 9.75 9.75 0 0 1 6.74 2.74L21 8" />
              <path d="M21 3v5h-5" />
              <path d="M21 12a9 9 0 0 1-9 9 9.75 9.75 0 0 1-6.74-2.74L3 16" />
              <path d="M3 21v-5h5" />
            </svg>
          </button>
          <span className="diagram-zoom-level">{Math.round(zoom * 100)}%</span>
        </div>
      )}

      <div
        className="diagram-container"
        ref={diagramRef}
        style={{
          width,
          height,
          transform: `scale(${zoom}) translate(${pan.x / zoom}px, ${pan.y / zoom}px)`,
          cursor: interactive ? (isDragging ? 'grabbing' : 'grab') : 'default',
        }}
        onMouseDown={handleMouseDown}
        onMouseMove={handleMouseMove}
        onMouseUp={handleMouseUp}
        onMouseLeave={handleMouseUp}
      >
        {isLoading ? (
          <div className="diagram-loading">Loading diagram...</div>
        ) : error ? (
          <div className="diagram-error">Error: {error}</div>
        ) : (
          renderDiagram()
        )}
      </div>
    </div>
  );
};

export default DiagramViewer;

