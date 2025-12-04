/**
 * Java Repository List Component
 * 
 * Displays a list of registered Java repositories in a marketplace-style UI.
 * Shows repository status, indexing progress, and allows management actions.
 */
import React, { useState, useEffect, useMemo } from 'react';
import { apiService } from '@/services/api';
import './JavaRepositoryList.css';

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

interface RepositoryStatus {
  repository_id: number;
  status: string;
  last_indexed_at?: string;
  chunk_count: number;
}

interface JavaRepositoryListProps {
  searchQuery?: string;
  statusFilter?: string;
  onSearchChange?: (query: string) => void;
  onStatusFilterChange?: (filter: string) => void;
}

const JavaRepositoryList: React.FC<JavaRepositoryListProps> = ({
  searchQuery: externalSearchQuery,
  statusFilter: externalStatusFilter,
  onSearchChange,
  onStatusFilterChange,
}) => {
  const [repositories, setRepositories] = useState<JavaRepository[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [statusMap, setStatusMap] = useState<Record<number, RepositoryStatus>>({});
  const [refreshing, setRefreshing] = useState<Record<number, boolean>>({});
  const [internalSearchQuery, setInternalSearchQuery] = useState('');
  const [internalStatusFilter, setInternalStatusFilter] = useState('all');

  // Use external props if provided, otherwise use internal state
  const searchQuery = externalSearchQuery !== undefined ? externalSearchQuery : internalSearchQuery;
  const statusFilter = externalStatusFilter !== undefined ? externalStatusFilter : internalStatusFilter;

  useEffect(() => {
    loadRepositories();
  }, []);

  const loadRepositories = async () => {
    try {
      setLoading(true);
      const repos = await apiService.listJavaRepositories();
      setRepositories(repos);

      // Load status for each repository
      const statusPromises = repos.map(async (repo: JavaRepository) => {
        try {
          const status = await apiService.getJavaIndexingStatus(repo.id);
          return { repoId: repo.id, status };
        } catch (err) {
          console.error(`Error loading status for repo ${repo.id}:`, err);
          return { repoId: repo.id, status: null };
        }
      });

      const statuses = await Promise.all(statusPromises);
      const statusMap: Record<number, RepositoryStatus> = {};
      statuses.forEach(({ repoId, status }) => {
        if (status) {
          statusMap[repoId] = status;
        }
      });
      setStatusMap(statusMap);
    } catch (err: any) {
      setError(err.message || 'Failed to load repositories');
    } finally {
      setLoading(false);
    }
  };

  const handleReindex = async (repositoryId: number) => {
    setRefreshing({ ...refreshing, [repositoryId]: true });
    try {
      await apiService.triggerJavaIndexing(repositoryId, false);
      // Refresh status after a delay
      setTimeout(() => {
        refreshStatus(repositoryId);
      }, 2000);
    } catch (err: any) {
      alert(err.message || 'Failed to start reindexing');
    } finally {
      setRefreshing({ ...refreshing, [repositoryId]: false });
    }
  };

  const handleDelete = async (repositoryId: number) => {
    if (!confirm('Are you sure you want to delete this repository? This will remove all indexed data.')) {
      return;
    }

    try {
      await apiService.deleteJavaRepository(repositoryId);
      setRepositories(repos => repos.filter(r => r.id !== repositoryId));
      const newStatusMap = { ...statusMap };
      delete newStatusMap[repositoryId];
      setStatusMap(newStatusMap);
    } catch (err: any) {
      alert(err.message || 'Failed to delete repository');
    }
  };

  const refreshStatus = async (repositoryId: number) => {
    try {
      const status = await apiService.getJavaIndexingStatus(repositoryId);
      setStatusMap(prev => ({ ...prev, [repositoryId]: status }));
    } catch (err) {
      console.error('Error refreshing status:', err);
    }
  };

  const getStatusBadge = (status: string) => {
    const statusConfig: Record<string, { label: string; className: string }> = {
      pending: { label: 'Pending', className: 'status-pending' },
      indexing: { label: 'Indexing', className: 'status-indexing' },
      completed: { label: 'Ready', className: 'status-completed' },
      failed: { label: 'Failed', className: 'status-failed' },
    };

    const config = statusConfig[status] || statusConfig.pending;
    return (
      <span className={`status-badge ${config.className}`}>
        {config.label}
      </span>
    );
  };

  const formatDate = (dateString?: string) => {
    if (!dateString) return 'Never';
    const date = new Date(dateString);
    return date.toLocaleDateString() + ' ' + date.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' });
  };

  // Filter repositories based on search and status
  const filteredRepositories = useMemo(() => {
    return repositories.filter(repo => {
      const status = statusMap[repo.id]?.status || repo.status;
      
      // Status filter
      if (statusFilter !== 'all' && status !== statusFilter) {
        return false;
      }
      
      // Search filter
      if (searchQuery) {
        const query = searchQuery.toLowerCase();
        const matchesName = repo.name.toLowerCase().includes(query);
        const matchesPath = repo.local_path.toLowerCase().includes(query);
        const matchesDescription = repo.description?.toLowerCase().includes(query) || false;
        
        if (!matchesName && !matchesPath && !matchesDescription) {
          return false;
        }
      }
      
      return true;
    });
  }, [repositories, statusMap, searchQuery, statusFilter]);

  const handleSearchChange = (value: string) => {
    if (onSearchChange) {
      onSearchChange(value);
    } else {
      setInternalSearchQuery(value);
    }
  };

  const handleStatusFilterChange = (value: string) => {
    if (onStatusFilterChange) {
      onStatusFilterChange(value);
    } else {
      setInternalStatusFilter(value);
    }
  };

  if (loading) {
    return (
      <div className="repository-list-container">
        <div className="loading-state">
          <div className="spinner"></div>
          <p>Loading repositories...</p>
        </div>
      </div>
    );
  }

  if (error) {
    return (
      <div className="repository-list-container">
        <div className="error-state">
          <p>Error: {error}</p>
          <button className="btn-primary" onClick={loadRepositories}>
            Retry
          </button>
        </div>
      </div>
    );
  }

  if (!loading && repositories.length === 0) {
    return (
      <div className="repository-list-container">
        <div className="empty-state">
          <div className="empty-icon">☕</div>
          <h3>No Java Repositories</h3>
          <p>Get started by onboarding your first Java repository</p>
          <button 
            className="btn-primary" 
            onClick={() => {
              window.location.href = '/marketplace.html';
            }}
            style={{ marginTop: '1rem' }}
          >
            Go to Marketplace
          </button>
        </div>
      </div>
    );
  }

  if (!loading && filteredRepositories.length === 0 && repositories.length > 0) {
    return (
      <div className="repository-list-container">
        <div className="repository-controls">
          <div className="search-container">
            <svg className="search-icon" width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
              <circle cx="11" cy="11" r="8"></circle>
              <path d="m21 21-4.35-4.35"></path>
            </svg>
            <input
              type="text"
              className="search-input"
              placeholder="Search repositories by name, path, or description..."
              value={searchQuery}
              onChange={(e) => handleSearchChange(e.target.value)}
            />
          </div>
          
          <div className="filter-container">
            <select
              className="status-filter"
              value={statusFilter}
              onChange={(e) => handleStatusFilterChange(e.target.value)}
            >
              <option value="all">All Status</option>
              <option value="completed">Ready</option>
              <option value="indexing">Indexing</option>
              <option value="pending">Pending</option>
              <option value="failed">Failed</option>
            </select>
          </div>

          <button className="btn-secondary btn-refresh" onClick={loadRepositories}>
            <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
              <path d="M3 12a9 9 0 0 1 9-9 9.75 9.75 0 0 1 6.74 2.74L21 8"></path>
              <path d="M21 3v5h-5"></path>
              <path d="M21 12a9 9 0 0 1-9 9 9.75 9.75 0 0 1-6.74-2.74L3 16"></path>
              <path d="M3 21v-5h5"></path>
            </svg>
            Refresh
          </button>
        </div>
        <div className="empty-state">
          <div className="empty-icon">🔍</div>
          <h3>No repositories found</h3>
          <p>Try adjusting your search or filter criteria</p>
        </div>
      </div>
    );
  }

  return (
    <div className="repository-list-container">
      {/* Search and Filter Bar */}
      <div className="repository-controls">
        <div className="search-container">
          <svg className="search-icon" width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
            <circle cx="11" cy="11" r="8"></circle>
            <path d="m21 21-4.35-4.35"></path>
          </svg>
          <input
            type="text"
            className="search-input"
            placeholder="Search repositories by name, path, or description..."
            value={searchQuery}
            onChange={(e) => handleSearchChange(e.target.value)}
          />
        </div>
        
        <div className="filter-container">
          <select
            className="status-filter"
            value={statusFilter}
            onChange={(e) => handleStatusFilterChange(e.target.value)}
          >
            <option value="all">All Status</option>
            <option value="completed">Ready</option>
            <option value="indexing">Indexing</option>
            <option value="pending">Pending</option>
            <option value="failed">Failed</option>
          </select>
        </div>

        <button className="btn-secondary btn-refresh" onClick={loadRepositories}>
          <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
            <path d="M3 12a9 9 0 0 1 9-9 9.75 9.75 0 0 1 6.74 2.74L21 8"></path>
            <path d="M21 3v5h-5"></path>
            <path d="M21 12a9 9 0 0 1-9 9 9.75 9.75 0 0 1-6.74-2.74L3 16"></path>
            <path d="M3 21v-5h5"></path>
          </svg>
          Refresh
        </button>
      </div>

      {/* Results Count */}
      {!loading && (
        <div className="results-count">
          Showing {filteredRepositories.length} of {repositories.length} repositories
        </div>
      )}

      <div className="repository-grid">
        {filteredRepositories.map((repo) => {
          const status = statusMap[repo.id];
          const isRefreshing = refreshing[repo.id];

          return (
            <div key={repo.id} className="repository-card">
              <div className="repository-card-header">
                <div className="repository-icon">☕</div>
                <div className="repository-title-section">
                  <h3>{repo.name}</h3>
                  {getStatusBadge(status?.status || repo.status)}
                </div>
              </div>

              <div className="repository-details">
                <div className="detail-row">
                  <span className="detail-label">Path:</span>
                  <span className="detail-value" title={repo.local_path}>
                    {repo.local_path.length > 50
                      ? repo.local_path.substring(0, 50) + '...'
                      : repo.local_path}
                  </span>
                </div>
                {repo.description && (
                  <div className="detail-row">
                    <span className="detail-label">Description:</span>
                    <span className="detail-value">{repo.description}</span>
                  </div>
                )}
                <div className="detail-row">
                  <span className="detail-label">Last Indexed:</span>
                  <span className="detail-value">{formatDate(status?.last_indexed_at || repo.last_indexed_at)}</span>
                </div>
                {status && (
                  <div className="detail-row">
                    <span className="detail-label">Code Chunks:</span>
                    <span className="detail-value">{status.chunk_count.toLocaleString()}</span>
                  </div>
                )}
              </div>

              <div className="repository-actions">
                <button
                  className="btn-secondary btn-sm"
                  onClick={() => handleReindex(repo.id)}
                  disabled={isRefreshing || status?.status === 'indexing'}
                >
                  {isRefreshing ? 'Starting...' : 'Reindex'}
                </button>
                <button
                  className="btn-danger btn-sm"
                  onClick={() => handleDelete(repo.id)}
                  disabled={isRefreshing}
                >
                  Delete
                </button>
              </div>
            </div>
          );
        })}
      </div>
    </div>
  );
};

export default JavaRepositoryList;

