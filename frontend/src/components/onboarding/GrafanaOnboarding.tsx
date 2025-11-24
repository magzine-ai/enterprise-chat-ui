/**
 * Grafana Onboarding Component
 * 
 * Multi-step onboarding process for Grafana integration.
 * Guides users through configuration with multiple steps.
 */
import React, { useState } from 'react';
import '../Marketplace.css';

interface GrafanaOnboardingProps {
  onBack: () => void;
}

interface GrafanaConfig {
  grafanaUrl: string;
  apiKey: string;
  organization: string;
  defaultDashboard: string;
  dataSource: string;
}

const GrafanaOnboarding: React.FC<GrafanaOnboardingProps> = ({ onBack }) => {
  const [currentStep, setCurrentStep] = useState(0);
  const [config, setConfig] = useState<GrafanaConfig>({
    grafanaUrl: '',
    apiKey: '',
    organization: 'Main Org.',
    defaultDashboard: '',
    dataSource: 'Prometheus',
  });

  const steps = [
    { label: 'Welcome', key: 'welcome' },
    { label: 'Server', key: 'server' },
    { label: 'API Key', key: 'apiKey' },
    { label: 'Settings', key: 'settings' },
    { label: 'Complete', key: 'complete' },
  ];

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

  const handleInputChange = (field: keyof GrafanaConfig, value: string) => {
    setConfig((prev) => ({ ...prev, [field]: value }));
  };

  const handleFinish = () => {
    alert('Grafana onboarding completed successfully!');
    onBack();
  };

  const renderStepContent = () => {
    switch (currentStep) {
      case 0: // Welcome
        return (
          <div className="onboarding-step-content">
            <h2 style={{ marginBottom: '1rem' }}>Welcome to Grafana Onboarding</h2>
            <div className="onboarding-info-box">
              <div className="onboarding-info-box-title">What you'll configure:</div>
              <ul style={{ marginLeft: '1.5rem', marginTop: '0.5rem', lineHeight: '1.8' }}>
                <li>Grafana server connection</li>
                <li>API key for authentication</li>
                <li>Organization settings</li>
                <li>Default data source configuration</li>
              </ul>
            </div>
            <p style={{ color: 'var(--text-secondary)', lineHeight: '1.6' }}>
              This wizard will help you connect to your Grafana instance and configure
              dashboards and data sources for visualization.
            </p>
          </div>
        );

      case 1: // Server
        return (
          <div className="onboarding-step-content">
            <h2 style={{ marginBottom: '1.5rem' }}>Grafana Server Settings</h2>
            <div className="onboarding-form-group">
              <label className="onboarding-form-label">
                Grafana Server URL <span style={{ color: 'red' }}>*</span>
              </label>
              <input
                type="text"
                className="onboarding-form-input"
                placeholder="https://grafana.example.com"
                value={config.grafanaUrl}
                onChange={(e) => handleInputChange('grafanaUrl', e.target.value)}
              />
              <small style={{ color: 'var(--text-secondary)', display: 'block', marginTop: '0.25rem' }}>
                Enter the full URL of your Grafana instance (including protocol)
              </small>
            </div>
            <div className="onboarding-info-box">
              <div className="onboarding-info-box-title">💡 Information</div>
              <div className="onboarding-info-box-text">
                Make sure your Grafana instance is accessible and you have administrator
                privileges to create API keys.
              </div>
            </div>
          </div>
        );

      case 2: // API Key
        return (
          <div className="onboarding-step-content">
            <h2 style={{ marginBottom: '1.5rem' }}>API Key Authentication</h2>
            <div className="onboarding-info-box">
              <div className="onboarding-info-box-title">How to create an API Key:</div>
              <ol style={{ marginLeft: '1.5rem', marginTop: '0.5rem', lineHeight: '1.8' }}>
                <li>Log in to your Grafana instance</li>
                <li>Go to Configuration → API Keys</li>
                <li>Click "New API Key"</li>
                <li>Set Role to "Admin" and expiration as needed</li>
                <li>Copy the generated key</li>
              </ol>
            </div>
            <div className="onboarding-form-group">
              <label className="onboarding-form-label">
                API Key <span style={{ color: 'red' }}>*</span>
              </label>
              <input
                type="password"
                className="onboarding-form-input"
                placeholder="Enter your Grafana API key"
                value={config.apiKey}
                onChange={(e) => handleInputChange('apiKey', e.target.value)}
              />
              <small style={{ color: 'var(--text-secondary)', display: 'block', marginTop: '0.25rem' }}>
                The API key will be encrypted and stored securely.
              </small>
            </div>
          </div>
        );

      case 3: // Settings
        return (
          <div className="onboarding-step-content">
            <h2 style={{ marginBottom: '1.5rem' }}>Organization & Data Source Settings</h2>
            <div className="onboarding-form-group">
              <label className="onboarding-form-label">Organization</label>
              <input
                type="text"
                className="onboarding-form-input"
                placeholder="Main Org."
                value={config.organization}
                onChange={(e) => handleInputChange('organization', e.target.value)}
              />
              <small style={{ color: 'var(--text-secondary)', display: 'block', marginTop: '0.25rem' }}>
                The Grafana organization to use for dashboards
              </small>
            </div>
            <div className="onboarding-form-group">
              <label className="onboarding-form-label">Default Data Source</label>
              <select
                className="onboarding-form-input"
                value={config.dataSource}
                onChange={(e) => handleInputChange('dataSource', e.target.value)}
              >
                <option value="Prometheus">Prometheus</option>
                <option value="InfluxDB">InfluxDB</option>
                <option value="Elasticsearch">Elasticsearch</option>
                <option value="Loki">Loki</option>
                <option value="MySQL">MySQL</option>
                <option value="PostgreSQL">PostgreSQL</option>
              </select>
              <small style={{ color: 'var(--text-secondary)', display: 'block', marginTop: '0.25rem' }}>
                Select the default data source for your dashboards
              </small>
            </div>
            <div className="onboarding-form-group">
              <label className="onboarding-form-label">Default Dashboard (Optional)</label>
              <input
                type="text"
                className="onboarding-form-input"
                placeholder="Enter dashboard name or leave empty"
                value={config.defaultDashboard}
                onChange={(e) => handleInputChange('defaultDashboard', e.target.value)}
              />
              <small style={{ color: 'var(--text-secondary)', display: 'block', marginTop: '0.25rem' }}>
                Specify a default dashboard to use when creating new visualizations
              </small>
            </div>
          </div>
        );

      case 4: // Complete
        return (
          <div className="onboarding-step-content">
            <h2 style={{ marginBottom: '1.5rem' }}>Configuration Summary</h2>
            <div style={{ background: 'var(--bg-secondary)', padding: '1.5rem', borderRadius: '8px' }}>
              <h3 style={{ marginBottom: '1rem', fontSize: '1rem', fontWeight: 600 }}>Review Your Settings</h3>
              <div style={{ display: 'grid', gap: '0.75rem' }}>
                <div style={{ display: 'flex', justifyContent: 'space-between' }}>
                  <span style={{ color: 'var(--text-secondary)' }}>Grafana URL:</span>
                  <span style={{ fontWeight: 500 }}>{config.grafanaUrl || 'Not set'}</span>
                </div>
                <div style={{ display: 'flex', justifyContent: 'space-between' }}>
                  <span style={{ color: 'var(--text-secondary)' }}>API Key:</span>
                  <span style={{ fontWeight: 500 }}>{config.apiKey ? '••••••••' : 'Not set'}</span>
                </div>
                <div style={{ display: 'flex', justifyContent: 'space-between' }}>
                  <span style={{ color: 'var(--text-secondary)' }}>Organization:</span>
                  <span style={{ fontWeight: 500 }}>{config.organization}</span>
                </div>
                <div style={{ display: 'flex', justifyContent: 'space-between' }}>
                  <span style={{ color: 'var(--text-secondary)' }}>Data Source:</span>
                  <span style={{ fontWeight: 500 }}>{config.dataSource}</span>
                </div>
                {config.defaultDashboard && (
                  <div style={{ display: 'flex', justifyContent: 'space-between' }}>
                    <span style={{ color: 'var(--text-secondary)' }}>Default Dashboard:</span>
                    <span style={{ fontWeight: 500 }}>{config.defaultDashboard}</span>
                  </div>
                )}
              </div>
            </div>
            <div className="onboarding-info-box" style={{ marginTop: '1.5rem' }}>
              <div className="onboarding-info-box-title">✅ Ready to Complete</div>
              <div className="onboarding-info-box-text">
                Your Grafana integration is configured and ready to use. Click "Finish" to complete the setup.
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
        <div className="onboarding-title">Grafana Onboarding</div>
      </div>

      <div className="onboarding-content">
        <div className="onboarding-steps">
          {steps.map((step, index) => (
            <div
              key={step.key}
              className={`onboarding-step ${index === currentStep ? 'active' : ''} ${index < currentStep ? 'completed' : ''}`}
            >
              <div className="onboarding-step-circle">
                {index < currentStep ? (
                  <svg
                    xmlns="http://www.w3.org/2000/svg"
                    width="20"
                    height="20"
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
              <div className="onboarding-step-label">{step.label}</div>
            </div>
          ))}
        </div>

        {renderStepContent()}

        <div className="onboarding-step-actions">
          <button
            className="onboarding-button onboarding-button-secondary"
            onClick={handlePrevious}
            disabled={currentStep === 0}
          >
            Previous
          </button>
          {currentStep < steps.length - 1 ? (
            <button
              className="onboarding-button onboarding-button-primary"
              onClick={handleNext}
              disabled={
                (currentStep === 1 && !config.grafanaUrl) ||
                (currentStep === 2 && !config.apiKey)
              }
            >
              Next
            </button>
          ) : (
            <button
              className="onboarding-button onboarding-button-primary"
              onClick={handleFinish}
            >
              Finish
            </button>
          )}
        </div>
      </div>
    </div>
  );
};

export default GrafanaOnboarding;


