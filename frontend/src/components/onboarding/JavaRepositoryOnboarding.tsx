/**
 * Java Repository Onboarding Component
 * 
 * Multi-step onboarding process for Java repository indexing.
 * Guides users through:
 * - Repository path selection
 * - Repository registration
 * - Indexing configuration
 * - Indexing progress
 * - Completion and review
 */
import React, { useState, useEffect } from 'react';
import { apiService } from '@/services/api';
import '../Marketplace.css';
import './JavaRepositoryOnboarding.css';

interface JavaRepository {
  id: number;
  name: string;
  local_path: string;
  description?: string;
  status: 'pending' | 'indexing' | 'completed' | 'failed';
  last_indexed_at?: string;
  created_at: string;
  updated_at: string;
}

interface IndexingStats {
  total_files: number;
  indexed_files: number;
  total_chunks: number;
  indexed_chunks: number;
  errors: number;
}

interface JavaRepositoryOnboardingProps {
  onBack: () => void;
  onRepositoryIndexed?: (repo: JavaRepository) => void;
}

const JavaRepositoryOnboarding: React.FC<JavaRepositoryOnboardingProps> = ({ onBack, onRepositoryIndexed }) => {
  const [currentStep, setCurrentStep] = useState(0);
  const [repositoryName, setRepositoryName] = useState('');
  const [repositoryPath, setRepositoryPath] = useState('');
  const [description, setDescription] = useState('');
  const [incremental, setIncremental] = useState(true);
  const [isRegistering, setIsRegistering] = useState(false);
  const [isIndexing, setIsIndexing] = useState(false);
  const [indexingProgress, setIndexingProgress] = useState(0);
  const [indexingStats, setIndexingStats] = useState<IndexingStats | null>(null);
  const [registeredRepository, setRegisteredRepository] = useState<JavaRepository | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [statusCheckInterval, setStatusCheckInterval] = useState<NodeJS.Timeout | null>(null);

  const steps = [
    { label: 'Repository Info', key: 'info' },
    { label: 'Register', key: 'register' },
    { label: 'Indexing', key: 'indexing' },
    { label: 'Review', key: 'review' },
  ];

  useEffect(() => {
    return () => {
      if (statusCheckInterval) {
        clearInterval(statusCheckInterval);
      }
    };
  }, [statusCheckInterval]);

  const handleRegister = async () => {
    if (!repositoryName.trim() || !repositoryPath.trim()) {
      setError('Repository name and path are required');
      return;
    }

    setIsRegistering(true);
    setError(null);

    try {
      console.log('📞 Calling registerJavaRepository API', {
        name: repositoryName.trim(),
        local_path: repositoryPath.trim(),
        description: description.trim() || undefined
      });
      
      const repo = await apiService.registerJavaRepository(
        repositoryName.trim(),
        repositoryPath.trim(),
        description.trim() || undefined
      );
      
      console.log('✅ Repository registered successfully', repo);
      
      if (!repo || !repo.id) {
        console.error('❌ Repository response missing id', repo);
        setError('Repository registration succeeded but ID is missing. Please try again.');
        return;
      }
      
      setRegisteredRepository(repo);
      setCurrentStep(1);
    } catch (err: any) {
      console.error('❌ Error registering repository:', err);
      setError(err.message || 'Failed to register repository');
    } finally {
      setIsRegistering(false);
    }
  };

  const handleStartIndexing = async () => {
    console.log('🔍 handleStartIndexing called', { registeredRepository, incremental });
    
    if (!registeredRepository) {
      console.error('❌ registeredRepository is null/undefined');
      setError('Repository not found. Please register the repository first.');
      return;
    }

    if (!registeredRepository.id) {
      console.error('❌ registeredRepository.id is missing', registeredRepository);
      setError('Repository ID is missing. Please try registering again.');
      return;
    }

    setIsIndexing(true);
    setError(null);
    setIndexingProgress(0);

    try {
      console.log('📞 Calling triggerJavaIndexing API', {
        repositoryId: registeredRepository.id,
        incremental
      });
      
      // Trigger indexing
      const result = await apiService.triggerJavaIndexing(registeredRepository.id, incremental);
      
      console.log('✅ Indexing triggered successfully', result);

      // Start polling for status
      const interval = setInterval(async () => {
        try {
          const status = await apiService.getJavaIndexingStatus(registeredRepository.id);
          console.log('📊 Status check:', status);
          
          if (status.status === 'completed') {
            clearInterval(interval);
            setIsIndexing(false);
            setIndexingProgress(100);
            setCurrentStep(3); // Go directly to review step
            // Fetch final stats if available
            setIndexingStats({
              total_files: status.chunk_count || 0,
              indexed_files: status.chunk_count || 0,
              total_chunks: status.chunk_count || 0,
              indexed_chunks: status.chunk_count || 0,
              errors: 0,
            });
            // Update registered repository with latest status
            const updatedRepo = {
              ...registeredRepository!,
              status: 'completed' as const,
              last_indexed_at: status.last_indexed_at || undefined
            };
            setRegisteredRepository(updatedRepo);
            // Notify parent component
            if (onRepositoryIndexed) {
              onRepositoryIndexed(updatedRepo);
            }
          } else if (status.status === 'failed') {
            clearInterval(interval);
            setIsIndexing(false);
            setError('Indexing failed. Please check the repository path and try again.');
          } else if (status.status === 'indexing') {
            // Update repository status for indexing state
            setRegisteredRepository(prev => prev ? { 
              ...prev, 
              status: 'indexing' as const,
              last_indexed_at: status.last_indexed_at || undefined 
            } : null);
            // Update progress (simplified - in production, get actual progress from backend)
            setIndexingProgress(prev => Math.min(prev + 10, 90));
          } else {
            // Update repository status for other states (pending, etc.)
            setRegisteredRepository(prev => prev ? { 
              ...prev, 
              status: status.status as 'pending' | 'indexing' | 'completed' | 'failed',
              last_indexed_at: status.last_indexed_at || undefined 
            } : null);
          }
        } catch (err) {
          console.error('Error checking indexing status:', err);
        }
      }, 2000);

      setStatusCheckInterval(interval);
    } catch (err: any) {
      console.error('❌ Error triggering indexing:', err);
      setIsIndexing(false);
      setError(err.message || 'Failed to start indexing. Please check the backend logs.');
    }
  };

  const renderStepContent = () => {
    switch (currentStep) {
      case 0: // Repository Info
        return (
          <div className="onboarding-step-content">
            <h2>Repository Information</h2>
            <p className="step-description">
              Provide information about your Java repository to begin indexing.
            </p>

            <div className="form-group">
              <label htmlFor="repo-name">Repository Name *</label>
              <input
                id="repo-name"
                type="text"
                value={repositoryName}
                onChange={(e) => setRepositoryName(e.target.value)}
                placeholder="e.g., My Java Project"
                className="form-input"
              />
            </div>

            <div className="form-group">
              <label htmlFor="repo-path">Local Repository Path *</label>
              <input
                id="repo-path"
                type="text"
                value={repositoryPath}
                onChange={(e) => setRepositoryPath(e.target.value)}
                placeholder="/path/to/java/repository"
                className="form-input"
              />
              <small className="form-hint">
                Enter the absolute path to your Java repository on the server
              </small>
            </div>

            <div className="form-group">
              <label htmlFor="repo-description">Description (Optional)</label>
              <textarea
                id="repo-description"
                value={description}
                onChange={(e) => setDescription(e.target.value)}
                placeholder="Brief description of the repository..."
                className="form-textarea"
                rows={3}
              />
            </div>

            {error && (
              <div className="error-message">{error}</div>
            )}

            <div className="step-actions">
              <button className="btn-secondary" onClick={onBack}>
                Cancel
              </button>
              <button
                className="btn-primary"
                onClick={handleRegister}
                disabled={isRegistering || !repositoryName.trim() || !repositoryPath.trim()}
              >
                {isRegistering ? 'Registering...' : 'Register Repository'}
              </button>
            </div>
          </div>
        );

      case 1: // Register & Configure
        return (
          <div className="onboarding-step-content">
            <h2>Indexing Configuration</h2>
            <p className="step-description">
              Configure indexing options for {registeredRepository?.name}
            </p>

            <div className="success-message">
              <svg width="20" height="20" viewBox="0 0 20 20" fill="none" xmlns="http://www.w3.org/2000/svg">
                <path d="M10 18C14.4183 18 18 14.4183 18 10C18 5.58172 14.4183 2 10 2C5.58172 2 2 5.58172 2 10C2 14.4183 5.58172 18 10 18Z" stroke="currentColor" strokeWidth="2" fill="none"/>
                <path d="M7 10L9 12L13 8" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"/>
              </svg>
              Repository registered successfully!
            </div>

            <div className="repo-info-card">
              <div className="info-row">
                <span className="info-label">Name:</span>
                <span className="info-value">{registeredRepository?.name}</span>
              </div>
              <div className="info-row">
                <span className="info-label">Path:</span>
                <span className="info-value">{registeredRepository?.local_path}</span>
              </div>
              {registeredRepository?.description && (
                <div className="info-row">
                  <span className="info-label">Description:</span>
                  <span className="info-value">{registeredRepository.description}</span>
                </div>
              )}
            </div>

            <div className="form-group">
              <label className="checkbox-label">
                <input
                  type="checkbox"
                  checked={incremental}
                  onChange={(e) => setIncremental(e.target.checked)}
                />
                <span>Incremental Indexing</span>
              </label>
              <small className="form-hint">
                Only index files that have changed since last indexing (recommended)
              </small>
            </div>

            {error && (
              <div className="error-message">{error}</div>
            )}

            <div className="step-actions">
              <button className="btn-secondary" onClick={() => setCurrentStep(0)}>
                Back
              </button>
              <button
                className="btn-primary"
                onClick={handleStartIndexing}
                disabled={isIndexing}
              >
                Start Indexing
              </button>
            </div>
          </div>
        );

      case 2: // Indexing Progress
        return (
          <div className="onboarding-step-content">
            <h2>Indexing in Progress</h2>
            <p className="step-description">
              Your repository is being indexed. This may take a few minutes...
            </p>

            <div className="progress-container">
              <div className="progress-bar">
                <div
                  className="progress-fill"
                  style={{ width: `${indexingProgress}%` }}
                />
              </div>
              <div className="progress-text">{indexingProgress}%</div>
            </div>

            {indexingStats && (
              <div className="stats-grid">
                <div className="stat-card">
                  <div className="stat-value">{indexingStats.total_files}</div>
                  <div className="stat-label">Total Files</div>
                </div>
                <div className="stat-card">
                  <div className="stat-value">{indexingStats.indexed_files}</div>
                  <div className="stat-label">Indexed Files</div>
                </div>
                <div className="stat-card">
                  <div className="stat-value">{indexingStats.total_chunks}</div>
                  <div className="stat-label">Code Chunks</div>
                </div>
                {indexingStats.errors > 0 && (
                  <div className="stat-card error">
                    <div className="stat-value">{indexingStats.errors}</div>
                    <div className="stat-label">Errors</div>
                  </div>
                )}
              </div>
            )}

            {error && (
              <div className="error-message">{error}</div>
            )}

            {indexingProgress === 100 && (
              <div className="step-actions">
                <button
                  className="btn-primary"
                  onClick={() => setCurrentStep(3)}
                >
                  View Results
                </button>
              </div>
            )}
          </div>
        );

      case 3: // Review
        return (
          <div className="onboarding-step-content">
            <h2>Indexing Complete!</h2>
            <p className="step-description">
              Your Java repository has been successfully indexed and is ready for code intelligence.
            </p>

            <div className="success-card">
              <svg width="48" height="48" viewBox="0 0 48 48" fill="none" xmlns="http://www.w3.org/2000/svg">
                <circle cx="24" cy="24" r="24" fill="#10B981" opacity="0.1"/>
                <path d="M24 44C35.0457 44 44 35.0457 44 24C44 12.9543 35.0457 4 24 4C12.9543 4 4 12.9543 4 24C4 35.0457 12.9543 44 24 44Z" stroke="#10B981" strokeWidth="2" fill="none"/>
                <path d="M16 24L21 29L32 18" stroke="#10B981" strokeWidth="3" strokeLinecap="round" strokeLinejoin="round"/>
              </svg>
              <h3>Repository Ready</h3>
              <p>You can now ask questions about your code in the chat interface!</p>
            </div>

            {indexingStats && (
              <div className="stats-grid">
                <div className="stat-card">
                  <div className="stat-value">{indexingStats.total_files}</div>
                  <div className="stat-label">Files Indexed</div>
                </div>
                <div className="stat-card">
                  <div className="stat-value">{indexingStats.total_chunks}</div>
                  <div className="stat-label">Code Chunks</div>
                </div>
              </div>
            )}

            <div className="step-actions">
              <button className="btn-secondary" onClick={onBack}>
                Back to Marketplace
              </button>
              <button
                className="btn-primary"
                onClick={() => {
                  // Notify parent that repository is indexed - this will navigate to repository list
                  if (registeredRepository && onRepositoryIndexed) {
                    onRepositoryIndexed(registeredRepository);
                  } else {
                    // Fallback to marketplace if callback not provided
                    onBack();
                  }
                }}
              >
                View Repositories
              </button>
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
        <div className="onboarding-title">Java Repository Onboarding</div>
      </div>

      <div className="onboarding-layout">
        {/* Sidebar with Steps */}
        <div className="onboarding-sidebar">
          <div className="sidebar-steps">
            {steps.map((step, index) => (
              <div
                key={step.key}
                className={`sidebar-step ${index === currentStep ? 'active' : ''} ${index < currentStep ? 'completed' : ''}`}
              >
                <div className="step-number">
                  {index < currentStep ? (
                    <svg width="16" height="16" viewBox="0 0 16 16" fill="none">
                      <path d="M13.3333 4L6 11.3333L2.66667 8" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"/>
                    </svg>
                  ) : (
                    index + 1
                  )}
                </div>
                <div className="step-label">{step.label}</div>
              </div>
            ))}
          </div>
        </div>

        {/* Main Content */}
        <div className="onboarding-main">
          {renderStepContent()}
        </div>
      </div>
    </div>
  );
};

export default JavaRepositoryOnboarding;

