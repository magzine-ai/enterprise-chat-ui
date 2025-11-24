/**
 * Splunk Index Onboarding Component
 * 
 * Multi-step onboarding process for Splunk index profiling and field discovery.
 * Guides users through:
 * - Index selection and profiling
 * - Field discovery with sample data
 * - Field description (manual or LLM-generated)
 * - Field relationships
 * - Parent-child value exploration
 * - Metadata configuration
 */
import React, { useState } from 'react';
import '../Marketplace.css';
import './SplunkOnboarding.css';

interface SplunkField {
  name: string;
  type: 'string' | 'number' | 'boolean' | 'timestamp' | 'ip' | 'url';
  description: string;
  sampleValues: string[];
  metadata: {
    required: boolean;
    indexed: boolean;
    searchable: boolean;
    category?: string;
    tags?: string[];
  };
}

interface FieldRelationship {
  parentField: string;
  childField: string;
  relationshipType: 'one-to-many' | 'many-to-one' | 'many-to-many';
  parentValues: Array<{
    value: string;
    childValues: string[];
  }>;
}

interface SplunkIndexConfig {
  indexName: string;
  connectionUrl: string;
  token: string;
  fields: SplunkField[];
  relationships: FieldRelationship[];
  dataLoadMode: 'full' | 'sample';
  sampleSize: number;
}

const SplunkOnboarding: React.FC<{ onBack: () => void }> = ({ onBack }) => {
  const [currentStep, setCurrentStep] = useState(0);
  const [config, setConfig] = useState<SplunkIndexConfig>({
    indexName: '',
    connectionUrl: '',
    token: '',
    fields: [],
    relationships: [],
    dataLoadMode: 'sample',
    sampleSize: 1000,
  });

  const [selectedIndex, setSelectedIndex] = useState<string>('');
  const [availableIndexes, setAvailableIndexes] = useState<string[]>([]);
  const [isProfiling, setIsProfiling] = useState(false);
  const [profilingProgress, setProfilingProgress] = useState(0);
  const [selectedField, setSelectedField] = useState<string | null>(null);
  const [isGeneratingDescription, setIsGeneratingDescription] = useState(false);
  const [relationshipParent, setRelationshipParent] = useState<string>('');
  const [relationshipChild, setRelationshipChild] = useState<string>('');

  const steps = [
    { label: 'Connection', key: 'connection' },
    { label: 'Index Selection', key: 'index' },
    { label: 'Profile & Discover', key: 'profile' },
    { label: 'Field Descriptions', key: 'descriptions' },
    { label: 'Relationships', key: 'relationships' },
    { label: 'Metadata', key: 'metadata' },
    { label: 'Review', key: 'review' },
  ];

  // Mock function to fetch indexes
  const fetchIndexes = async () => {
    // Simulate API call
    await new Promise((resolve) => setTimeout(resolve, 1000));
    return ['main', 'web_logs', 'api_logs', 'security', 'application'];
  };

  // Mock function to profile index
  const profileIndex = async (indexName: string) => {
    setIsProfiling(true);
    setProfilingProgress(0);

    // Simulate profiling progress
    for (let i = 0; i <= 100; i += 10) {
      await new Promise((resolve) => setTimeout(resolve, 200));
      setProfilingProgress(i);
    }

    // Mock discovered fields with sample data
    const mockFields: SplunkField[] = [
      {
        name: 'timestamp',
        type: 'timestamp',
        description: '',
        sampleValues: ['2024-01-15T10:30:00Z', '2024-01-15T10:31:00Z', '2024-01-15T10:32:00Z'],
        metadata: { required: true, indexed: true, searchable: true, category: 'Time' },
      },
      {
        name: 'status',
        type: 'number',
        description: '',
        sampleValues: ['200', '404', '500', '301', '302'],
        metadata: { required: false, indexed: true, searchable: true, category: 'HTTP' },
      },
      {
        name: 'method',
        type: 'string',
        description: '',
        sampleValues: ['GET', 'POST', 'PUT', 'DELETE', 'PATCH'],
        metadata: { required: false, indexed: true, searchable: true, category: 'HTTP' },
      },
      {
        name: 'path',
        type: 'string',
        description: '',
        sampleValues: ['/api/users', '/api/products', '/api/orders', '/api/auth/login'],
        metadata: { required: false, indexed: true, searchable: true, category: 'HTTP' },
      },
      {
        name: 'user_id',
        type: 'string',
        description: '',
        sampleValues: ['user_123', 'user_456', 'user_789', 'user_101'],
        metadata: { required: false, indexed: true, searchable: true, category: 'User' },
      },
      {
        name: 'ip_address',
        type: 'ip',
        description: '',
        sampleValues: ['192.168.1.1', '10.0.0.1', '172.16.0.1', '203.0.113.1'],
        metadata: { required: false, indexed: true, searchable: true, category: 'Network' },
      },
      {
        name: 'response_time',
        type: 'number',
        description: '',
        sampleValues: ['45', '120', '89', '234', '156'],
        metadata: { required: false, indexed: false, searchable: true, category: 'Performance' },
      },
    ];

    setConfig((prev) => ({ ...prev, fields: mockFields }));
    setIsProfiling(false);
    setProfilingProgress(0);
  };

  // Mock LLM description generation
  const generateFieldDescription = async (fieldName: string) => {
    setIsGeneratingDescription(true);
    await new Promise((resolve) => setTimeout(resolve, 1500));

    const descriptions: Record<string, string> = {
      timestamp: 'The timestamp when the event occurred, in ISO 8601 format',
      status: 'HTTP status code returned by the server (e.g., 200 for success, 404 for not found)',
      method: 'HTTP method used for the request (GET, POST, PUT, DELETE, etc.)',
      path: 'The URL path of the API endpoint that was accessed',
      user_id: 'Unique identifier for the user who made the request',
      ip_address: 'IP address of the client that made the request',
      response_time: 'Time taken to process the request in milliseconds',
    };

    const description = descriptions[fieldName] || `Field ${fieldName} contains data related to the event`;

    setConfig((prev) => ({
      ...prev,
      fields: prev.fields.map((f) =>
        f.name === fieldName ? { ...f, description } : f
      ),
    }));

    setIsGeneratingDescription(false);
  };

  // Load parent-child values
  const loadParentChildValues = async (parentField: string, childField: string) => {
    // Mock data showing parent values and their child values
    const mockData = [
      { parent: 'GET', children: ['/api/users', '/api/products', '/api/orders'] },
      { parent: 'POST', children: ['/api/users', '/api/auth/login', '/api/orders'] },
      { parent: 'PUT', children: ['/api/users', '/api/products'] },
      { parent: 'DELETE', children: ['/api/users', '/api/products'] },
    ];

    const relationship: FieldRelationship = {
      parentField,
      childField,
      relationshipType: 'one-to-many',
      parentValues: mockData.map((d) => ({
        value: d.parent,
        childValues: d.children,
      })),
    };

    setConfig((prev) => ({
      ...prev,
      relationships: [...prev.relationships, relationship],
    }));

    setRelationshipParent('');
    setRelationshipChild('');
  };

  const handleNext = () => {
    if (currentStep < steps.length - 1) {
      setCurrentStep(currentStep + 1);
    }
  };

  const handlePrevious = () => {
    if (currentStep > 0) {
      setCurrentStep(currentStep - 1);
    }
  };

  const handleFinish = () => {
    alert('Splunk index onboarding completed successfully!');
    onBack();
  };

  const renderStepContent = () => {
    switch (currentStep) {
      case 0: // Connection
        return (
          <div className="onboarding-step-content">
            <h2 style={{ marginBottom: '1.5rem' }}>Splunk Connection</h2>
            <div className="onboarding-form-group">
              <label className="onboarding-form-label">
                Splunk Server URL <span style={{ color: 'red' }}>*</span>
              </label>
              <input
                type="text"
                className="onboarding-form-input"
                placeholder="https://splunk.example.com"
                value={config.connectionUrl}
                onChange={(e) => setConfig((prev) => ({ ...prev, connectionUrl: e.target.value }))}
              />
            </div>
            <div className="onboarding-form-group">
              <label className="onboarding-form-label">
                Authentication Token <span style={{ color: 'red' }}>*</span>
              </label>
              <input
                type="password"
                className="onboarding-form-input"
                placeholder="Enter your Splunk token"
                value={config.token}
                onChange={(e) => setConfig((prev) => ({ ...prev, token: e.target.value }))}
              />
            </div>
          </div>
        );

      case 1: // Index Selection
        return (
          <div className="onboarding-step-content">
            <h2 style={{ marginBottom: '1.5rem' }}>Select Index</h2>
            {availableIndexes.length === 0 ? (
              <div>
                <button
                  className="onboarding-button onboarding-button-primary"
                  onClick={async () => {
                    const indexes = await fetchIndexes();
                    setAvailableIndexes(indexes);
                  }}
                >
                  Load Available Indexes
                </button>
              </div>
            ) : (
              <div className="index-selection-grid">
                {availableIndexes.map((index) => (
                  <div
                    key={index}
                    className={`index-card ${selectedIndex === index ? 'selected' : ''}`}
                    onClick={() => {
                      setSelectedIndex(index);
                      setConfig((prev) => ({ ...prev, indexName: index }));
                    }}
                  >
                    <div className="index-card-icon">📊</div>
                    <div className="index-card-name">{index}</div>
                  </div>
                ))}
              </div>
            )}
          </div>
        );

      case 2: // Profile & Discover
        return (
          <div className="onboarding-step-content">
            <h2 style={{ marginBottom: '1.5rem' }}>Profile Index & Discover Fields</h2>
            {config.fields.length === 0 ? (
              <div>
                <div className="onboarding-info-box">
                  <div className="onboarding-info-box-title">Data Loading Options</div>
                  <div className="onboarding-form-group" style={{ marginTop: '1rem' }}>
                    <label className="onboarding-form-checkbox">
                      <input
                        type="radio"
                        name="dataLoadMode"
                        checked={config.dataLoadMode === 'full'}
                        onChange={() => setConfig((prev) => ({ ...prev, dataLoadMode: 'full' }))}
                      />
                      <span>Load Full Data</span>
                    </label>
                  </div>
                  <div className="onboarding-form-group">
                    <label className="onboarding-form-checkbox">
                      <input
                        type="radio"
                        name="dataLoadMode"
                        checked={config.dataLoadMode === 'sample'}
                        onChange={() => setConfig((prev) => ({ ...prev, dataLoadMode: 'sample' }))}
                      />
                      <span>Load Sample Data</span>
                    </label>
                  </div>
                  {config.dataLoadMode === 'sample' && (
                    <div className="onboarding-form-group">
                      <label className="onboarding-form-label">Sample Size</label>
                      <input
                        type="number"
                        className="onboarding-form-input"
                        value={config.sampleSize}
                        onChange={(e) =>
                          setConfig((prev) => ({ ...prev, sampleSize: parseInt(e.target.value) || 1000 }))
                        }
                      />
                    </div>
                  )}
                </div>
                <button
                  className="onboarding-button onboarding-button-primary"
                  onClick={() => profileIndex(config.indexName)}
                  disabled={!config.indexName || isProfiling}
                >
                  {isProfiling ? `Profiling... ${profilingProgress}%` : 'Start Profiling'}
                </button>
                {isProfiling && (
                  <div className="progress-bar">
                    <div
                      className="progress-bar-fill"
                      style={{ width: `${profilingProgress}%` }}
                    />
                  </div>
                )}
              </div>
            ) : (
              <div>
                <h3 style={{ marginBottom: '1rem' }}>
                  Discovered {config.fields.length} Fields
                </h3>
                <div className="fields-grid">
                  {config.fields.map((field) => (
                    <div key={field.name} className="field-card">
                      <div className="field-card-header">
                        <span className="field-name">{field.name}</span>
                        <span className="field-type">{field.type}</span>
                      </div>
                      <div className="field-samples">
                        <strong>Sample Values:</strong>
                        <div className="sample-values">
                          {field.sampleValues.slice(0, 3).map((val, idx) => (
                            <span key={idx} className="sample-value">{val}</span>
                          ))}
                          {field.sampleValues.length > 3 && (
                            <span className="sample-value">+{field.sampleValues.length - 3} more</span>
                          )}
                        </div>
                      </div>
                    </div>
                  ))}
                </div>
              </div>
            )}
          </div>
        );

      case 3: // Field Descriptions
        return (
          <div className="onboarding-step-content">
            <h2 style={{ marginBottom: '1.5rem' }}>Field Descriptions</h2>
            <p style={{ color: 'var(--text-secondary)', marginBottom: '1.5rem' }}>
              Add descriptions to fields manually or use AI to generate them automatically.
            </p>
            <div className="fields-list">
              {config.fields.map((field) => (
                <div key={field.name} className="field-description-item">
                  <div className="field-description-header">
                    <div>
                      <strong>{field.name}</strong>
                      <span className="field-type-badge">{field.type}</span>
                    </div>
                    <button
                      className="onboarding-button onboarding-button-secondary"
                      onClick={() => generateFieldDescription(field.name)}
                      disabled={isGeneratingDescription}
                      style={{ fontSize: '0.875rem', padding: '0.5rem 1rem' }}
                    >
                      {isGeneratingDescription && selectedField === field.name
                        ? 'Generating...'
                        : '🤖 Generate with AI'}
                    </button>
                  </div>
                  <textarea
                    className="onboarding-form-input onboarding-form-textarea"
                    placeholder="Enter field description..."
                    value={field.description}
                    onChange={(e) =>
                      setConfig((prev) => ({
                        ...prev,
                        fields: prev.fields.map((f) =>
                          f.name === field.name ? { ...f, description: e.target.value } : f
                        ),
                      }))
                    }
                    rows={2}
                  />
                </div>
              ))}
            </div>
          </div>
        );

      case 4: // Relationships
        return (
          <div className="onboarding-step-content">
            <h2 style={{ marginBottom: '1.5rem' }}>Field Relationships</h2>
            <p style={{ color: 'var(--text-secondary)', marginBottom: '1.5rem' }}>
              Define relationships between fields and explore parent-child value mappings.
            </p>

            <div className="relationship-builder">
              <div className="onboarding-form-group">
                <label className="onboarding-form-label">Parent Field</label>
                <select
                  className="onboarding-form-input"
                  value={relationshipParent}
                  onChange={(e) => setRelationshipParent(e.target.value)}
                >
                  <option value="">Select parent field</option>
                  {config.fields.map((field) => (
                    <option key={field.name} value={field.name}>
                      {field.name}
                    </option>
                  ))}
                </select>
              </div>

              <div className="onboarding-form-group">
                <label className="onboarding-form-label">Child Field</label>
                <select
                  className="onboarding-form-input"
                  value={relationshipChild}
                  onChange={(e) => setRelationshipChild(e.target.value)}
                >
                  <option value="">Select child field</option>
                  {config.fields
                    .filter((f) => f.name !== relationshipParent)
                    .map((field) => (
                      <option key={field.name} value={field.name}>
                        {field.name}
                      </option>
                    ))}
                </select>
              </div>

              <div className="onboarding-form-group">
                <label className="onboarding-form-label">Relationship Type</label>
                <select className="onboarding-form-input">
                  <option value="one-to-many">One-to-Many</option>
                  <option value="many-to-one">Many-to-One</option>
                  <option value="many-to-many">Many-to-Many</option>
                </select>
              </div>

              <button
                className="onboarding-button onboarding-button-primary"
                onClick={() => {
                  if (relationshipParent && relationshipChild) {
                    loadParentChildValues(relationshipParent, relationshipChild);
                  }
                }}
                disabled={!relationshipParent || !relationshipChild}
              >
                Load Parent-Child Values
              </button>
            </div>

            {config.relationships.length > 0 && (
              <div className="relationships-list" style={{ marginTop: '2rem' }}>
                <h3 style={{ marginBottom: '1rem' }}>Defined Relationships</h3>
                {config.relationships.map((rel, idx) => (
                  <div key={idx} className="relationship-card">
                    <div className="relationship-header">
                      <strong>{rel.parentField}</strong>
                      <span>→</span>
                      <strong>{rel.childField}</strong>
                      <span className="relationship-type">{rel.relationshipType}</span>
                    </div>
                    <div className="relationship-values">
                      {rel.parentValues.map((pv, pidx) => (
                        <div key={pidx} className="parent-child-group">
                          <div className="parent-value">
                            <strong>{pv.value}</strong>
                          </div>
                          <div className="child-values">
                            {pv.childValues.map((cv, cidx) => (
                              <span key={cidx} className="child-value">{cv}</span>
                            ))}
                          </div>
                        </div>
                      ))}
                    </div>
                  </div>
                ))}
              </div>
            )}
          </div>
        );

      case 5: // Metadata
        return (
          <div className="onboarding-step-content">
            <h2 style={{ marginBottom: '1.5rem' }}>Field Metadata</h2>
            <p style={{ color: 'var(--text-secondary)', marginBottom: '1.5rem' }}>
              Configure metadata for each field: indexing, searchability, categories, and tags.
            </p>
            <div className="fields-metadata-list">
              {config.fields.map((field) => (
                <div key={field.name} className="field-metadata-card">
                  <div className="field-metadata-header">
                    <strong>{field.name}</strong>
                    <span className="field-type-badge">{field.type}</span>
                  </div>
                  <div className="metadata-controls">
                    <label className="onboarding-form-checkbox">
                      <input
                        type="checkbox"
                        checked={field.metadata.required}
                        onChange={(e) =>
                          setConfig((prev) => ({
                            ...prev,
                            fields: prev.fields.map((f) =>
                              f.name === field.name
                                ? { ...f, metadata: { ...f.metadata, required: e.target.checked } }
                                : f
                            ),
                          }))
                        }
                      />
                      <span>Required</span>
                    </label>
                    <label className="onboarding-form-checkbox">
                      <input
                        type="checkbox"
                        checked={field.metadata.indexed}
                        onChange={(e) =>
                          setConfig((prev) => ({
                            ...prev,
                            fields: prev.fields.map((f) =>
                              f.name === field.name
                                ? { ...f, metadata: { ...f.metadata, indexed: e.target.checked } }
                                : f
                            ),
                          }))
                        }
                      />
                      <span>Indexed</span>
                    </label>
                    <label className="onboarding-form-checkbox">
                      <input
                        type="checkbox"
                        checked={field.metadata.searchable}
                        onChange={(e) =>
                          setConfig((prev) => ({
                            ...prev,
                            fields: prev.fields.map((f) =>
                              f.name === field.name
                                ? { ...f, metadata: { ...f.metadata, searchable: e.target.checked } }
                                : f
                            ),
                          }))
                        }
                      />
                      <span>Searchable</span>
                    </label>
                  </div>
                  <div className="onboarding-form-group" style={{ marginTop: '1rem' }}>
                    <label className="onboarding-form-label">Category</label>
                    <input
                      type="text"
                      className="onboarding-form-input"
                      value={field.metadata.category || ''}
                      onChange={(e) =>
                        setConfig((prev) => ({
                          ...prev,
                          fields: prev.fields.map((f) =>
                            f.name === field.name
                              ? { ...f, metadata: { ...f.metadata, category: e.target.value } }
                              : f
                          ),
                        }))
                      }
                      placeholder="e.g., HTTP, User, Network"
                    />
                  </div>
                  <div className="onboarding-form-group">
                    <label className="onboarding-form-label">Tags (comma-separated)</label>
                    <input
                      type="text"
                      className="onboarding-form-input"
                      value={field.metadata.tags?.join(', ') || ''}
                      onChange={(e) =>
                        setConfig((prev) => ({
                          ...prev,
                          fields: prev.fields.map((f) =>
                            f.name === field.name
                              ? {
                                  ...f,
                                  metadata: {
                                    ...f.metadata,
                                    tags: e.target.value.split(',').map((t) => t.trim()).filter(Boolean),
                                  },
                                }
                              : f
                          ),
                        }))
                      }
                      placeholder="e.g., security, performance, api"
                    />
                  </div>
                </div>
              ))}
            </div>
          </div>
        );

      case 6: // Review
        return (
          <div className="onboarding-step-content">
            <h2 style={{ marginBottom: '1.5rem' }}>Review Configuration</h2>
            <div className="review-summary">
              <div className="review-section">
                <h3>Index</h3>
                <p>{config.indexName}</p>
              </div>
              <div className="review-section">
                <h3>Fields ({config.fields.length})</h3>
                <div className="review-fields">
                  {config.fields.map((field) => (
                    <div key={field.name} className="review-field-item">
                      <strong>{field.name}</strong> ({field.type})
                      {field.description && <div className="review-field-desc">{field.description}</div>}
                    </div>
                  ))}
                </div>
              </div>
              {config.relationships.length > 0 && (
                <div className="review-section">
                  <h3>Relationships ({config.relationships.length})</h3>
                  {config.relationships.map((rel, idx) => (
                    <div key={idx} className="review-relationship">
                      {rel.parentField} → {rel.childField}
                    </div>
                  ))}
                </div>
              )}
              <div className="review-section">
                <h3>Data Loading</h3>
                <p>
                  Mode: {config.dataLoadMode === 'full' ? 'Full Data' : 'Sample Data'}
                  {config.dataLoadMode === 'sample' && ` (${config.sampleSize} records)`}
                </p>
              </div>
            </div>
          </div>
        );

      default:
        return null;
    }
  };

  return (
    <div className="onboarding-container">
      <div className="onboarding-header">
        <button className="onboarding-back-button" onClick={onBack}>
          <svg
            xmlns="http://www.w3.org/2000/svg"
            width="16"
            height="16"
            viewBox="0 0 24 24"
            fill="none"
            stroke="currentColor"
            strokeWidth="2"
            strokeLinecap="round"
            strokeLinejoin="round"
          >
            <path d="M19 12H5M12 19l-7-7 7-7" />
          </svg>
          Back to Marketplace
        </button>
        <div className="onboarding-title">Splunk Index Onboarding</div>
      </div>

      <div className="onboarding-layout">
        {/* Sidebar with Steps */}
        <div className="onboarding-sidebar">
          <div className="sidebar-steps">
            {steps.map((step, index) => (
              <div
                key={step.key}
                className={`sidebar-step ${index === currentStep ? 'active' : ''} ${index < currentStep ? 'completed' : ''}`}
                onClick={() => {
                  // Allow navigation to completed steps or current step
                  if (index <= currentStep || index < currentStep + 1) {
                    setCurrentStep(index);
                  }
                }}
              >
                <div className="sidebar-step-indicator">
                  <div className="sidebar-step-circle">
                    {index < currentStep ? (
                      <svg
                        xmlns="http://www.w3.org/2000/svg"
                        width="16"
                        height="16"
                        viewBox="0 0 24 24"
                        fill="none"
                        stroke="currentColor"
                        strokeWidth="2"
                        strokeLinecap="round"
                        strokeLinejoin="round"
                      >
                        <polyline points="20 6 9 17 4 12" />
                      </svg>
                    ) : (
                      index + 1
                    )}
                  </div>
                  {index < steps.length - 1 && <div className="sidebar-step-line" />}
                </div>
                <div className="sidebar-step-content">
                  <div className="sidebar-step-label">{step.label}</div>
                  {index === currentStep && (
                    <div className="sidebar-step-description">Current step</div>
                  )}
                </div>
              </div>
            ))}
          </div>
        </div>

        {/* Main Content Area */}
        <div className="onboarding-main-content">
          <div className="onboarding-step-progress">
            <span className="step-progress-text">
              Step {currentStep + 1} of {steps.length}
            </span>
            <div className="step-progress-bar">
              <div
                className="step-progress-fill"
                style={{ width: `${((currentStep + 1) / steps.length) * 100}%` }}
              />
            </div>
          </div>

          <div className="onboarding-step-wrapper">
            {renderStepContent()}
          </div>

          <div className="onboarding-step-actions">
            <button
              className="onboarding-button onboarding-button-secondary"
              onClick={handlePrevious}
              disabled={currentStep === 0}
            >
              <svg
                xmlns="http://www.w3.org/2000/svg"
                width="16"
                height="16"
                viewBox="0 0 24 24"
                fill="none"
                stroke="currentColor"
                strokeWidth="2"
                strokeLinecap="round"
                strokeLinejoin="round"
              >
                <path d="M19 12H5M12 19l-7-7 7-7" />
              </svg>
              Previous
            </button>
            {currentStep < steps.length - 1 ? (
              <button
                className="onboarding-button onboarding-button-primary"
                onClick={handleNext}
                disabled={
                  (currentStep === 0 && (!config.connectionUrl || !config.token)) ||
                  (currentStep === 1 && !config.indexName) ||
                  (currentStep === 2 && config.fields.length === 0)
                }
              >
                Next
                <svg
                  xmlns="http://www.w3.org/2000/svg"
                  width="16"
                  height="16"
                  viewBox="0 0 24 24"
                  fill="none"
                  stroke="currentColor"
                  strokeWidth="2"
                  strokeLinecap="round"
                  strokeLinejoin="round"
                >
                  <path d="M5 12h14M12 5l7 7-7 7" />
                </svg>
              </button>
            ) : (
              <button
                className="onboarding-button onboarding-button-primary"
                onClick={handleFinish}
              >
                <svg
                  xmlns="http://www.w3.org/2000/svg"
                  width="16"
                  height="16"
                  viewBox="0 0 24 24"
                  fill="none"
                  stroke="currentColor"
                  strokeWidth="2"
                  strokeLinecap="round"
                  strokeLinejoin="round"
                >
                  <polyline points="20 6 9 17 4 12" />
                </svg>
                Finish Setup
              </button>
            )}
          </div>
        </div>
      </div>
    </div>
  );
};

export default SplunkOnboarding;
