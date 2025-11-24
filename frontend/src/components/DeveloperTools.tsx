/**
 * DeveloperTools Component
 * 
 * A comprehensive developer/admin tools page for managing chat components,
 * styles, configurations, and viewing component documentation.
 */
import React, { useState, useMemo } from 'react';
import BlockRenderer from './BlockRenderer';
import type { Block } from '@/types';
import './DeveloperTools.css';

interface ComponentInfo {
  type: string;
  name: string;
  description: string;
  category: string;
  example: any;
  props?: Record<string, any>;
  usage: string;
}

const COMPONENT_DOCS: ComponentInfo[] = [
  {
    type: 'markdown',
    name: 'Markdown',
    description: 'Renders markdown content with formatting',
    category: 'Text',
    example: {
      type: 'markdown',
      data: { content: '# Hello World\n\nThis is **bold** and this is *italic*.' }
    },
    usage: 'Use for formatted text content'
  },
  {
    type: 'code',
    name: 'Code Block',
    description: 'Syntax-highlighted code snippets with copy functionality',
    category: 'Code',
    example: {
      type: 'code',
      data: {
        code: 'const greeting = "Hello, World!";\nconsole.log(greeting);',
        language: 'javascript',
        title: 'Example Code'
      }
    },
    usage: 'Display code snippets with syntax highlighting'
  },
  {
    type: 'query',
    name: 'Query Block',
    description: 'Executable SQL/Splunk queries with results',
    category: 'Data',
    example: {
      type: 'query',
      data: {
        query: 'SELECT * FROM users LIMIT 10',
        language: 'sql',
        autoExecute: true
      }
    },
    usage: 'Execute and display query results'
  },
  {
    type: 'splunk-chart',
    name: 'Splunk Chart',
    description: 'Interactive charts (line, bar, area, pie, timechart)',
    category: 'Visualization',
    example: {
      type: 'splunk-chart',
      data: {
        type: 'line',
        data: [
          { name: 'Mon', value: 1200 },
          { name: 'Tue', value: 1350 },
          { name: 'Wed', value: 1100 }
        ],
        title: 'Sample Chart'
      }
    },
    usage: 'Visualize data with various chart types'
  },
  {
    type: 'table',
    name: 'Data Table',
    description: 'Sortable and paginated data tables',
    category: 'Data',
    example: {
      type: 'table',
      data: {
        columns: ['Name', 'Age', 'City'],
        rows: [
          ['John', '30', 'New York'],
          ['Jane', '25', 'London']
        ]
      }
    },
    usage: 'Display tabular data with sorting'
  },
  {
    type: 'json-explorer',
    name: 'JSON Explorer',
    description: 'Interactive JSON viewer with expand/collapse',
    category: 'Data',
    example: {
      type: 'json-explorer',
      data: {
        data: { name: 'John', age: 30, city: 'New York' },
        title: 'User Data'
      }
    },
    usage: 'Explore JSON data interactively'
  },
  {
    type: 'timeline',
    name: 'Timeline Viewer',
    description: 'Event timeline visualization',
    category: 'Visualization',
    example: {
      type: 'timeline',
      data: {
        events: [
          { id: '1', title: 'Event 1', time: '10:00 AM', type: 'info' },
          { id: '2', title: 'Event 2', time: '11:00 AM', type: 'success' }
        ]
      }
    },
    usage: 'Display events on a timeline'
  },
  {
    type: 'form-viewer',
    name: 'Form Viewer',
    description: 'Structured form data display (ServiceNow, tickets)',
    category: 'Forms',
    example: {
      type: 'form-viewer',
      data: {
        title: 'Change Request CR12345',
        fields: [
          { name: 'number', label: 'Number', value: 'CR12345', type: 'text' },
          { name: 'status', label: 'Status', value: 'In Progress', type: 'badge', badgeType: 'info' }
        ]
      }
    },
    usage: 'Display structured form data'
  },
  {
    type: 'file-upload-download',
    name: 'File Upload/Download',
    description: 'File upload with drag-drop and download',
    category: 'Files',
    example: {
      type: 'file-upload-download',
      data: {
        mode: 'both',
        files: [
          { name: 'example.log', size: 1024, url: '/files/example.log' }
        ]
      }
    },
    usage: 'Upload and download files'
  },
  {
    type: 'checklist',
    name: 'Checklist',
    description: 'Interactive checklist with completion tracking',
    category: 'Forms',
    example: {
      type: 'checklist',
      data: {
        title: 'Task List',
        items: [
          { id: '1', text: 'Task 1', checked: false },
          { id: '2', text: 'Task 2', checked: true }
        ]
      }
    },
    usage: 'Manage task checklists'
  },
  {
    type: 'diagram',
    name: 'Diagram Viewer',
    description: 'Workflow, architecture, and AWS diagrams',
    category: 'Visualization',
    example: {
      type: 'diagram',
      data: {
        type: 'mermaid',
        diagram: 'graph TD\n    A[Start] --> B[Process]\n    B --> C[End]',
        title: 'Sample Workflow'
      }
    },
    usage: 'Render various diagram types'
  },
  {
    type: 'alert',
    name: 'Alert Block',
    description: 'Alert/notification messages',
    category: 'UI',
    example: {
      type: 'alert',
      data: {
        type: 'info',
        title: 'Information',
        message: 'This is an alert message'
      }
    },
    usage: 'Display alerts and notifications'
  },
  {
    type: 'collapsible',
    name: 'Collapsible Section',
    description: 'Expandable/collapsible content',
    category: 'UI',
    example: {
      type: 'collapsible',
      data: {
        title: 'Click to expand',
        content: 'This is collapsible content'
      }
    },
    usage: 'Create expandable sections'
  }
];

interface CSSVariable {
  name: string;
  value: string;
  type: 'color' | 'shadow' | 'text';
  description: string;
}

const DEFAULT_CSS_VARIABLES: CSSVariable[] = [
  { name: '--bg-primary', value: '#ffffff', type: 'color', description: 'Primary background color' },
  { name: '--bg-secondary', value: '#f7f7f8', type: 'color', description: 'Secondary background color' },
  { name: '--bg-tertiary', value: '#f0f0f0', type: 'color', description: 'Tertiary background color' },
  { name: '--text-primary', value: '#353740', type: 'color', description: 'Primary text color' },
  { name: '--text-secondary', value: '#6e6e80', type: 'color', description: 'Secondary text color' },
  { name: '--border-color', value: '#e5e5e6', type: 'color', description: 'Border color' },
  { name: '--user-bubble', value: '#19c37d', type: 'color', description: 'User message bubble color' },
  { name: '--assistant-bubble', value: '#f7f7f8', type: 'color', description: 'Assistant message bubble color' },
  { name: '--input-bg', value: '#ffffff', type: 'color', description: 'Input background color' },
  { name: '--input-border', value: '#d1d5db', type: 'color', description: 'Input border color' },
  { name: '--input-focus', value: '#10a37f', type: 'color', description: 'Input focus color' },
  { name: '--shadow-sm', value: '0 1px 2px 0 rgba(0, 0, 0, 0.05)', type: 'shadow', description: 'Small shadow' },
  { name: '--shadow-md', value: '0 4px 6px -1px rgba(0, 0, 0, 0.1)', type: 'shadow', description: 'Medium shadow' },
];

const DeveloperTools: React.FC = () => {
  const [selectedComponent, setSelectedComponent] = useState<ComponentInfo | null>(null);
  const [activeTab, setActiveTab] = useState<'components' | 'styles' | 'config' | 'preview'>('components');
  const [customStyles, setCustomStyles] = useState<string>('');
  const [cssVariables, setCssVariables] = useState<CSSVariable[]>(DEFAULT_CSS_VARIABLES);
  const [previewBlock, setPreviewBlock] = useState<Block | null>(null);
  const [searchQuery, setSearchQuery] = useState('');
  const [selectedCategory, setSelectedCategory] = useState<string>('all');
  const [styleViewMode, setStyleViewMode] = useState<'ui' | 'code'>('ui');
  const [previewMode, setPreviewMode] = useState(false);

  const categories = useMemo(() => {
    const cats = new Set(COMPONENT_DOCS.map(c => c.category));
    return ['all', ...Array.from(cats)];
  }, []);

  const filteredComponents = useMemo(() => {
    let filtered = COMPONENT_DOCS;
    
    if (selectedCategory !== 'all') {
      filtered = filtered.filter(c => c.category === selectedCategory);
    }
    
    if (searchQuery) {
      const query = searchQuery.toLowerCase();
      filtered = filtered.filter(c => 
        c.name.toLowerCase().includes(query) ||
        c.description.toLowerCase().includes(query) ||
        c.type.toLowerCase().includes(query)
      );
    }
    
    return filtered;
  }, [searchQuery, selectedCategory]);

  const handlePreview = (component: ComponentInfo) => {
    setPreviewBlock(component.example);
    setActiveTab('preview');
  };

  // Load current CSS variables from document
  React.useEffect(() => {
    if (activeTab === 'styles') {
      const root = document.documentElement;
      const computed = getComputedStyle(root);
      setCssVariables(prev => prev.map(variable => {
        const value = computed.getPropertyValue(variable.name).trim();
        return { ...variable, value: value || variable.value };
      }));
    }
  }, [activeTab]);

  const handleVariableChange = (name: string, value: string) => {
    setCssVariables(prev => prev.map(v => v.name === name ? { ...v, value } : v));
    
    // Apply preview immediately if preview mode is on
    if (previewMode) {
      const root = document.documentElement;
      root.style.setProperty(name, value);
    }
  };

  const handleApplyVariables = () => {
    const root = document.documentElement;
    cssVariables.forEach(variable => {
      root.style.setProperty(variable.name, variable.value);
    });
    setPreviewMode(false);
    alert('CSS variables applied successfully!');
  };

  const handleResetVariables = () => {
    setCssVariables(DEFAULT_CSS_VARIABLES);
    const root = document.documentElement;
    DEFAULT_CSS_VARIABLES.forEach(variable => {
      root.style.setProperty(variable.name, variable.value);
    });
    setPreviewMode(false);
    alert('CSS variables reset to defaults!');
  };

  const handleStyleApply = () => {
    if (customStyles.trim()) {
      const styleElement = document.getElementById('custom-styles') || document.createElement('style');
      styleElement.id = 'custom-styles';
      styleElement.textContent = customStyles;
      if (!document.getElementById('custom-styles')) {
        document.head.appendChild(styleElement);
      }
      alert('Custom styles applied!');
    }
  };

  const generateCSSFromVariables = () => {
    return `:root {\n${cssVariables.map(v => `  ${v.name}: ${v.value};`).join('\n')}\n}`;
  };

  const handleCodeUpdate = (code: string) => {
    // Parse CSS code and update variables
    const lines = code.split('\n');
    const updated = [...cssVariables];
    
    lines.forEach(line => {
      const match = line.match(/--([a-z-]+):\s*(.+?);/);
      if (match) {
        const varName = `--${match[1]}`;
        const value = match[2].trim();
        const index = updated.findIndex(v => v.name === varName);
        if (index !== -1) {
          updated[index] = { ...updated[index], value };
        }
      }
    });
    
    setCssVariables(updated);
    
    if (previewMode) {
      updated.forEach(variable => {
        document.documentElement.style.setProperty(variable.name, variable.value);
      });
    }
  };

  return (
    <div className="developer-tools">
      <div className="dev-tools-header">
        <h1>Developer Tools</h1>
        <div className="dev-tools-nav">
          <button
            className={`nav-tab ${activeTab === 'components' ? 'active' : ''}`}
            onClick={() => setActiveTab('components')}
          >
            Components
          </button>
          <button
            className={`nav-tab ${activeTab === 'styles' ? 'active' : ''}`}
            onClick={() => setActiveTab('styles')}
          >
            Styles
          </button>
          <button
            className={`nav-tab ${activeTab === 'config' ? 'active' : ''}`}
            onClick={() => setActiveTab('config')}
          >
            Configuration
          </button>
          <button
            className={`nav-tab ${activeTab === 'preview' ? 'active' : ''}`}
            onClick={() => setActiveTab('preview')}
          >
            Preview
          </button>
          <a href="/" className="back-to-chat-button">
            ← Back to Chat
          </a>
        </div>
      </div>

      <div className="dev-tools-content">
        {activeTab === 'components' && (
          <div className="components-tab">
            <div className="components-filters">
              <input
                type="text"
                placeholder="Search components..."
                className="search-input"
                value={searchQuery}
                onChange={(e) => setSearchQuery(e.target.value)}
              />
              <select
                className="category-select"
                value={selectedCategory}
                onChange={(e) => setSelectedCategory(e.target.value)}
              >
                {categories.map(cat => (
                  <option key={cat} value={cat}>
                    {cat === 'all' ? 'All Categories' : cat}
                  </option>
                ))}
              </select>
            </div>

            <div className="components-grid">
              {filteredComponents.map((component) => (
                <div
                  key={component.type}
                  className="component-card"
                  onClick={() => setSelectedComponent(component)}
                >
                  <div className="component-card-header">
                    <h3>{component.name}</h3>
                    <span className="component-type">{component.type}</span>
                  </div>
                  <p className="component-description">{component.description}</p>
                  <div className="component-meta">
                    <span className="component-category">{component.category}</span>
                    <button
                      className="preview-button"
                      onClick={(e) => {
                        e.stopPropagation();
                        handlePreview(component);
                      }}
                    >
                      Preview
                    </button>
                  </div>
                </div>
              ))}
            </div>

            {selectedComponent && (
              <div className="component-detail-modal" onClick={() => setSelectedComponent(null)}>
                <div className="component-detail-content" onClick={(e) => e.stopPropagation()}>
                  <div className="component-detail-header">
                    <h2>{selectedComponent.name}</h2>
                    <button className="close-button" onClick={() => setSelectedComponent(null)}>×</button>
                  </div>
                  <div className="component-detail-body">
                    <div className="detail-section">
                      <h3>Description</h3>
                      <p>{selectedComponent.description}</p>
                    </div>
                    <div className="detail-section">
                      <h3>Usage</h3>
                      <p>{selectedComponent.usage}</p>
                    </div>
                    <div className="detail-section">
                      <h3>Example Code</h3>
                      <pre className="code-example">
                        {JSON.stringify(selectedComponent.example, null, 2)}
                      </pre>
                    </div>
                    <div className="detail-section">
                      <h3>Live Preview</h3>
                      <div className="preview-container">
                        <BlockRenderer block={selectedComponent.example} />
                      </div>
                    </div>
                  </div>
                </div>
              </div>
            )}
          </div>
        )}

        {activeTab === 'styles' && (
          <div className="styles-tab">
            <div className="styles-header">
              <h2>Global CSS Styles</h2>
              <div className="styles-controls">
                <div className="view-mode-toggle">
                  <button
                    className={`mode-button ${styleViewMode === 'ui' ? 'active' : ''}`}
                    onClick={() => setStyleViewMode('ui')}
                  >
                    UI Editor
                  </button>
                  <button
                    className={`mode-button ${styleViewMode === 'code' ? 'active' : ''}`}
                    onClick={() => setStyleViewMode('code')}
                  >
                    Code Editor
                  </button>
                </div>
                <label className="preview-toggle">
                  <input
                    type="checkbox"
                    checked={previewMode}
                    onChange={(e) => {
                      setPreviewMode(e.target.checked);
                      if (!e.target.checked) {
                        // Reset to original values when preview is off
                        const root = document.documentElement;
                        const computed = getComputedStyle(root);
                        cssVariables.forEach(variable => {
                          const original = computed.getPropertyValue(variable.name).trim();
                          root.style.setProperty(variable.name, original || variable.value);
                        });
                      }
                    }}
                  />
                  Live Preview
                </label>
                <button className="apply-button" onClick={handleApplyVariables}>
                  Apply Changes
                </button>
                <button className="reset-button" onClick={handleResetVariables}>
                  Reset
                </button>
              </div>
            </div>

            {styleViewMode === 'ui' ? (
              <div className="css-variables-editor">
                <div className="variables-grid">
                  {cssVariables.map((variable) => (
                    <div key={variable.name} className="variable-item">
                      <div className="variable-header">
                        <label className="variable-name">{variable.name}</label>
                        <span className="variable-type">{variable.type}</span>
                      </div>
                      <p className="variable-description">{variable.description}</p>
                      {variable.type === 'color' ? (
                        <div className="color-input-group">
                          <input
                            type="color"
                            value={variable.value}
                            onChange={(e) => handleVariableChange(variable.name, e.target.value)}
                            className="color-picker"
                          />
                          <input
                            type="text"
                            value={variable.value}
                            onChange={(e) => handleVariableChange(variable.name, e.target.value)}
                            className="color-text-input"
                            placeholder="#ffffff"
                          />
                        </div>
                      ) : (
                        <input
                          type="text"
                          value={variable.value}
                          onChange={(e) => handleVariableChange(variable.name, e.target.value)}
                          className="variable-input"
                          placeholder={variable.value}
                        />
                      )}
                      {previewMode && variable.type === 'color' && (
                        <div 
                          className="variable-preview" 
                          style={{ backgroundColor: variable.value }}
                        >
                          <span style={{ 
                            color: variable.value === '#ffffff' || variable.value === '#f7f7f8' || variable.value === '#f0f0f0' 
                              ? '#000' 
                              : '#fff' 
                          }}>
                            Preview
                          </span>
                        </div>
                      )}
                    </div>
                  ))}
                </div>
                <div className="variables-code-preview">
                  <h3>Generated CSS Code</h3>
                  <pre className="code-preview">{generateCSSFromVariables()}</pre>
                </div>
              </div>
            ) : (
              <div className="styles-editor">
                <div className="editor-header">
                  <h3>CSS Variables Code Editor</h3>
                </div>
                <textarea
                  className="styles-textarea"
                  value={generateCSSFromVariables()}
                  onChange={(e) => handleCodeUpdate(e.target.value)}
                  spellCheck={false}
                />
                <div className="editor-footer">
                  <p>💡 Edit the CSS variables code above. Changes will be reflected in the UI editor when you switch back.</p>
                </div>
              </div>
            )}

            <div className="custom-css-section">
              <h3>Additional Custom CSS</h3>
              <div className="styles-editor">
                <div className="editor-header">
                  <h4>Custom CSS Editor</h4>
                  <button className="apply-button" onClick={handleStyleApply}>
                    Apply Custom Styles
                  </button>
                </div>
                <textarea
                  className="styles-textarea"
                  value={customStyles}
                  onChange={(e) => setCustomStyles(e.target.value)}
                  placeholder="/* Add your custom CSS here */&#10;&#10;.custom-class {&#10;  color: #333;&#10;  padding: 1rem;&#10;}"
                  spellCheck={false}
                />
                <div className="editor-footer">
                  <p>💡 Tip: Your custom styles will be applied globally. Use specific selectors to avoid conflicts.</p>
                </div>
              </div>
            </div>
          </div>
        )}

        {activeTab === 'config' && (
          <div className="config-tab">
            <h2>Application Configuration</h2>
            <div className="config-sections">
              <div className="config-section">
                <h3>API Configuration</h3>
                <div className="config-item">
                  <label>API URL</label>
                  <input type="text" defaultValue={import.meta.env.VITE_API_URL || 'http://localhost:8000'} />
                </div>
                <div className="config-item">
                  <label>WebSocket URL</label>
                  <input type="text" defaultValue={import.meta.env.VITE_WS_URL || 'ws://localhost:8000/ws'} />
                </div>
                <div className="config-item">
                  <label>Mock Services</label>
                  <select defaultValue={import.meta.env.VITE_MOCK_SERVICES || 'true'}>
                    <option value="true">Enabled</option>
                    <option value="false">Disabled</option>
                  </select>
                </div>
              </div>

              <div className="config-section">
                <h3>UI Configuration</h3>
                <div className="config-item">
                  <label>Theme</label>
                  <select defaultValue="light">
                    <option value="light">Light</option>
                    <option value="dark">Dark</option>
                  </select>
                </div>
                <div className="config-item">
                  <label>Max Message Width</label>
                  <input type="number" defaultValue={1200} />
                </div>
                <div className="config-item">
                  <label>Auto-scroll Messages</label>
                  <input type="checkbox" defaultChecked />
                </div>
              </div>

              <div className="config-section">
                <h3>Feature Flags</h3>
                <div className="config-item">
                  <label>Enable File Upload</label>
                  <input type="checkbox" defaultChecked />
                </div>
                <div className="config-item">
                  <label>Enable Diagram Viewer</label>
                  <input type="checkbox" defaultChecked />
                </div>
                <div className="config-item">
                  <label>Enable Marketplace</label>
                  <input type="checkbox" defaultChecked />
                </div>
              </div>
            </div>
            <div className="config-actions">
              <button className="save-button">Save Configuration</button>
              <button className="reset-button">Reset to Defaults</button>
            </div>
          </div>
        )}

        {activeTab === 'preview' && (
          <div className="preview-tab">
            <div className="preview-header">
              <h2>Component Preview</h2>
              {previewBlock && (
                <button className="clear-preview-button" onClick={() => setPreviewBlock(null)}>
                  Clear Preview
                </button>
              )}
            </div>
            {previewBlock ? (
              <div className="preview-content">
                <div className="preview-block">
                  <BlockRenderer block={previewBlock} />
                </div>
                <div className="preview-code">
                  <h3>Block JSON</h3>
                  <pre>{JSON.stringify(previewBlock, null, 2)}</pre>
                </div>
              </div>
            ) : (
              <div className="preview-empty">
                <p>No component selected for preview.</p>
                <p>Go to the Components tab and click "Preview" on any component.</p>
              </div>
            )}
          </div>
        )}
      </div>
    </div>
  );
};

export default DeveloperTools;

