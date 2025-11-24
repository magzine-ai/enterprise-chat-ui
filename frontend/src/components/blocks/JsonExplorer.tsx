/**
 * JsonExplorer Component
 * 
 * Interactive JSON data explorer with expand/collapse functionality.
 * Useful for exploring API responses, configuration files, and nested data structures.
 * Supports opening in popup or new tab for better viewing.
 * 
 * @example
 * ```tsx
 * <JsonExplorer
 *   data={{ user: { name: "John", age: 30 } }}
 *   title="User Data"
 *   collapsed={false}
 * />
 * ```
 * 
 * @param data - JSON object or array to display
 * @param title - Optional title for the explorer
 * @param collapsed - Whether to start collapsed (default: false)
 * @param maxDepth - Maximum depth to expand by default (default: 3)
 */
import React, { useState, useRef } from 'react';

interface JsonExplorerProps {
  data: any;
  title?: string;
  collapsed?: boolean;
  maxDepth?: number;
}

interface JsonNodeProps {
  data: any;
  keyName?: string;
  depth: number;
  maxDepth: number;
}

const JsonNode: React.FC<JsonNodeProps> = ({ data, keyName, depth, maxDepth }) => {
  const [isExpanded, setIsExpanded] = useState(depth < maxDepth);
  const [isCopied, setIsCopied] = useState(false);

  const handleCopy = async (value: string) => {
    try {
      await navigator.clipboard.writeText(value);
      setIsCopied(true);
      setTimeout(() => setIsCopied(false), 2000);
    } catch (err) {
      console.error('Failed to copy:', err);
    }
  };

  if (data === null) {
    return <span className="json-null">null</span>;
  }

  if (data === undefined) {
    return <span className="json-undefined">undefined</span>;
  }

  const type = Array.isArray(data) ? 'array' : typeof data;

  if (type === 'string') {
    return (
      <span>
        <span className="json-key">{keyName ? `${keyName}: ` : ''}</span>
        <span className="json-string">"{data}"</span>
        <button
          className="json-copy-btn"
          onClick={() => handleCopy(data)}
          title="Copy value"
        >
          {isCopied ? '✓' : '📋'}
        </button>
      </span>
    );
  }

  if (type === 'number' || type === 'boolean') {
    return (
      <span>
        <span className="json-key">{keyName ? `${keyName}: ` : ''}</span>
        <span className={`json-${type}`}>{String(data)}</span>
      </span>
    );
  }

  if (type === 'array' || type === 'object') {
    const keys = Array.isArray(data) 
      ? data.map((_, i) => i)
      : Object.keys(data);
    const isEmpty = keys.length === 0;

    return (
      <div className="json-node">
        <div className="json-node-header">
          <button
            className="json-toggle"
            onClick={() => setIsExpanded(!isExpanded)}
            disabled={isEmpty}
          >
            {isEmpty ? '○' : isExpanded ? '▼' : '▶'}
          </button>
          <span className="json-key">
            {keyName && `${keyName}: `}
            <span className="json-bracket">
              {Array.isArray(data) ? '[' : '{'}
            </span>
            {isEmpty && (
              <span className="json-bracket">
                {Array.isArray(data) ? ']' : '}'}
              </span>
            )}
            {!isEmpty && <span className="json-count"> {keys.length} {Array.isArray(data) ? 'items' : 'keys'}</span>}
          </span>
          {!isEmpty && (
            <button
              className="json-copy-btn"
              onClick={() => handleCopy(JSON.stringify(data, null, 2))}
              title="Copy JSON"
            >
              {isCopied ? '✓' : '📋'}
            </button>
          )}
        </div>
        {isExpanded && !isEmpty && (
          <div className="json-node-children">
            {keys.map((key) => (
              <div key={String(key)} className="json-node-item">
                <JsonNode
                  data={data[key]}
                  keyName={Array.isArray(data) ? undefined : String(key)}
                  depth={depth + 1}
                  maxDepth={maxDepth}
                />
              </div>
            ))}
            <div className="json-bracket">
              {Array.isArray(data) ? ']' : '}'}
            </div>
          </div>
        )}
      </div>
    );
  }

  return <span>{String(data)}</span>;
};

const JsonExplorer: React.FC<JsonExplorerProps> = ({
  data,
  title,
  collapsed = false,
  maxDepth = 3,
}) => {
  const [isCollapsed, setIsCollapsed] = useState(collapsed);
  const jsonRef = useRef<HTMLDivElement>(null);

  const handleOpenPopup = () => {
    const left = Math.round((window.screen.width - 1200) / 2);
    const top = Math.round((window.screen.height - 800) / 2);
    const jsonHTML = jsonRef.current?.innerHTML || '';
    const htmlContent = `
      <!DOCTYPE html>
      <html>
        <head>
          <title>${title || 'JSON Explorer'}</title>
          <meta charset="utf-8">
          <style>
            * { margin: 0; padding: 0; box-sizing: border-box; }
            body { 
              margin: 0; 
              padding: 20px; 
              font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', 'Roboto', sans-serif; 
              background: #f5f5f5; 
            }
            .popup-json-container {
              background: white;
              padding: 20px;
              border-radius: 8px;
              box-shadow: 0 2px 8px rgba(0,0,0,0.1);
              height: calc(100vh - 80px);
              overflow: auto;
            }
            h2 { margin-bottom: 20px; color: #333; }
          </style>
        </head>
        <body>
          <div class="popup-json-container">
            <h2>${title || 'JSON Explorer'}</h2>
            ${jsonHTML}
          </div>
        </body>
      </html>
    `;
    
    const popup = window.open(
      '',
      'jsonPopup',
      `width=1200,height=800,left=${left},top=${top},resizable=yes,scrollbars=yes,toolbar=no,menubar=no,location=no,status=no`
    );
    
    if (popup) {
      popup.document.open();
      popup.document.write(htmlContent);
      popup.document.close();
      popup.focus();
    }
  };

  const handleOpenNewTab = () => {
    const jsonHTML = jsonRef.current?.innerHTML || '';
    const htmlContent = `
      <!DOCTYPE html>
      <html>
        <head>
          <title>${title || 'JSON Explorer'}</title>
          <meta charset="utf-8">
          <style>
            * { margin: 0; padding: 0; box-sizing: border-box; }
            body { 
              margin: 0; 
              padding: 20px; 
              font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', 'Roboto', sans-serif; 
              background: #f5f5f5; 
            }
            .tab-json-container {
              background: white;
              padding: 20px;
              border-radius: 8px;
              box-shadow: 0 2px 8px rgba(0,0,0,0.1);
              min-height: calc(100vh - 80px);
            }
            h2 { margin-bottom: 20px; color: #333; }
          </style>
        </head>
        <body>
          <div class="tab-json-container">
            <h2>${title || 'JSON Explorer'}</h2>
            ${jsonHTML}
          </div>
        </body>
      </html>
    `;
    
    const newTab = window.open('', '_blank');
    if (newTab) {
      newTab.document.open();
      newTab.document.write(htmlContent);
      newTab.document.close();
    }
  };

  return (
    <div ref={jsonRef} className="json-explorer-wrapper">
      <div className="json-explorer-header">
        {title && <div className="json-explorer-title">{title}</div>}
        <div className="json-explorer-actions">
          <button
            className="json-collapse-btn"
            onClick={() => setIsCollapsed(!isCollapsed)}
          >
            {isCollapsed ? '▼' : '▲'}
          </button>
          <button className="json-action-button" onClick={handleOpenPopup} title="Open in popup">
            🔲
          </button>
          <button className="json-action-button" onClick={handleOpenNewTab} title="Open in new tab">
            📑
          </button>
        </div>
      </div>
      {!isCollapsed && (
        <div className="json-explorer-content">
          <JsonNode data={data} depth={0} maxDepth={maxDepth} />
        </div>
      )}
    </div>
  );
};

export default JsonExplorer;

