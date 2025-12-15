/**
 * Repository Viewer Component
 * 
 * Displays repository metadata including file count, languages, last indexed time,
 * and provides graph visualization based on search queries.
 */
import React, { useState, useEffect } from 'react';
import { apiService } from '@/services/api';
import GraphVisualization from './GraphVisualization';
import './RepositoryViewer.css';

interface RepositoryMetadata {
  repository_id: number;
  name: string;
  description?: string;
  status: string;
  last_indexed_at?: string;
  created_at: string;
  updated_at: string;
  github_url?: string;
  local_path?: string;
  file_count?: number;
  chunk_count?: number;
  method_count?: number;
  class_count?: number;
  languages?: string[];
  graph_stats?: {
    nodes: number;
    edges: number;
  };
}

interface RepositoryViewerProps {
  repositoryId: number;
  onClose?: () => void;
}

const RepositoryViewer: React.FC<RepositoryViewerProps> = ({ repositoryId, onClose }) => {
  const [metadata, setMetadata] = useState<RepositoryMetadata | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [graphQuery, setGraphQuery] = useState('');
  const [showGraph, setShowGraph] = useState(false);
  const [graphData, setGraphData] = useState<{ nodes: any[]; edges: any[] } | null>(null);
  const [graphLoading, setGraphLoading] = useState(false);
  const [buildingGraph, setBuildingGraph] = useState(false);
  const [buildJobId, setBuildJobId] = useState<string | null>(null);
  const [buildProgress, setBuildProgress] = useState(0);
  const [buildStatus, setBuildStatus] = useState<string>('');
  const [buildMessage, setBuildMessage] = useState<string>('');
  const [realtimeGraphStats, setRealtimeGraphStats] = useState<{ nodes: number; edges: number } | null>(null);

  useEffect(() => {
    loadMetadata();
    
    // Request notification permission
    if ('Notification' in window && Notification.permission === 'default') {
      Notification.requestPermission();
    }
  }, [repositoryId]);

  const loadMetadata = async () => {
    try {
      setLoading(true);
      setError(null);
      const data = await apiService.getRepositoryMetadata(repositoryId);
      setMetadata(data);
    } catch (err: any) {
      setError(err.message || 'Failed to load repository metadata');
    } finally {
      setLoading(false);
    }
  };

  const handleBuildGraph = async (rebuild: boolean = false) => {
    setBuildingGraph(true);
    setError(null);
    setBuildProgress(0);
    setBuildStatus('');
    setBuildMessage(rebuild ? 'Rebuilding graph...' : 'Starting graph construction...');
    
    try {
      const result = await apiService.buildRepositoryGraph(repositoryId, rebuild);
      
      if (!result.success || !result.job_id) {
        setError(result.message || 'Failed to create graph building job.');
        setBuildingGraph(false);
        return;
      }
      
      // Start polling for job status
      setBuildJobId(result.job_id);
      pollJobStatus(result.job_id);
    } catch (err: any) {
      console.error('Error building graph:', err);
      setError(err.message || 'Failed to build graph');
      setBuildingGraph(false);
    }
  };

  const pollJobStatus = async (jobId: string) => {
    const pollInterval = 1000; // Poll every second
    const maxAttempts = 300; // Max 5 minutes
    let attempts = 0;
    
    const poll = async () => {
      try {
        const job = await apiService.getJob(jobId);
        
        setBuildProgress(job.progress || 0);
        setBuildStatus(job.status);
        
        // Extract node/edge counts from job params (progress_data) or result
        if (job.params?.progress_data) {
          // Real-time counts from progress updates stored in params
          const progressData = job.params.progress_data;
          setRealtimeGraphStats({
            nodes: progressData.nodes || 0,
            edges: progressData.edges || 0
          });
        } else {
          // Fallback: try to get from result
          const resultData = job.result || (job as any).data;
          if (resultData) {
            if (resultData.data) {
              setRealtimeGraphStats({
                nodes: resultData.data.nodes || 0,
                edges: resultData.data.edges || 0
              });
            } else if (resultData.graph_stats) {
              setRealtimeGraphStats({
                nodes: resultData.graph_stats.nodes || 0,
                edges: resultData.graph_stats.edges || 0
              });
            }
          }
        }
        
        if (job.status === 'completed') {
          const result = job.result;
          const finalNodes = result?.graph_stats?.nodes || realtimeGraphStats?.nodes || 0;
          const finalEdges = result?.graph_stats?.edges || realtimeGraphStats?.edges || 0;
          
          // Preserve final stats in realtimeGraphStats until metadata loads
          if (finalNodes > 0 || finalEdges > 0) {
            setRealtimeGraphStats({
              nodes: finalNodes,
              edges: finalEdges
            });
          }
          
          setBuildingGraph(false);
          setBuildJobId(null);
          
          // Reload metadata to get updated graph stats
          // Wait a bit for the graph to be fully committed
          await new Promise(resolve => setTimeout(resolve, 500));
          await loadMetadata();
          
          if (result?.graph_stats) {
            const nodes = result.graph_stats.nodes || 0;
            const edges = result.graph_stats.edges || 0;
            setBuildMessage(`Graph built successfully! ${nodes} nodes, ${edges} edges`);
            
            // Show success notification
            if (window.Notification && Notification.permission === 'granted') {
              new Notification('Graph Build Complete', {
                body: `Successfully built graph with ${nodes} nodes and ${edges} edges`,
                icon: '/favicon.ico'
              });
            } else {
              // Fallback: Show browser alert or custom notification
              alert(`✅ Graph built successfully!\n\n${nodes} nodes\n${edges} edges`);
            }
            
            // Keep realtimeGraphStats until metadata is confirmed loaded
            // Only clear after metadata has graph_stats to prevent showing 0
            setTimeout(() => {
              setBuildMessage('');
              // Reload metadata one more time to ensure it's updated
              loadMetadata().then(() => {
                // Only clear realtime stats if metadata now has graph_stats
                // Otherwise keep them to prevent showing 0
                setTimeout(() => {
                  if (metadata?.graph_stats && metadata.graph_stats.nodes > 0) {
                    setRealtimeGraphStats(null);
                  }
                }, 500);
              });
            }, 5000);
          } else {
            setBuildMessage('Graph built successfully!');
            setTimeout(() => {
              setBuildMessage('');
              loadMetadata().then(() => {
                setTimeout(() => {
                  if (metadata?.graph_stats && metadata.graph_stats.nodes > 0) {
                    setRealtimeGraphStats(null);
                  }
                }, 500);
              });
            }, 3000);
          }
          return;
        }
        
        if (job.status === 'failed') {
          setBuildingGraph(false);
          setBuildJobId(null);
          setRealtimeGraphStats(null);
          setError(job.error || 'Graph building failed');
          return;
        }
        
        // Update message if available (check both result and data fields)
        const messageData = job.result || (job as any).data?.result;
        if (messageData?.message) {
          setBuildMessage(messageData.message);
        }
        
        // Continue polling if job is still in progress
        if (attempts < maxAttempts && (job.status === 'queued' || job.status === 'started' || job.status === 'progress')) {
          attempts++;
          setTimeout(poll, pollInterval);
        } else if (attempts >= maxAttempts) {
          setBuildingGraph(false);
          setBuildJobId(null);
          setRealtimeGraphStats(null);
          setError('Graph building timed out. Please try again.');
        }
      } catch (err: any) {
        console.error('Error polling job status:', err);
        setBuildingGraph(false);
        setBuildJobId(null);
        setRealtimeGraphStats(null);
        setError('Failed to check job status');
      }
    };
    
    poll();
  };

  const handleVisualizeGraph = async () => {
    if (!graphQuery.trim()) {
      return;
    }

    // Check if graph is built (allow during building if nodes exist)
    const hasGraph = (metadata.graph_stats && metadata.graph_stats.nodes > 0) || 
                     (buildingGraph && realtimeGraphStats && realtimeGraphStats.nodes > 0);
    
    if (!hasGraph) {
      if (buildingGraph) {
        setError('Graph is still being built. Please wait for it to complete.');
      } else {
        setError('Graph not built yet. Please build the knowledge graph first.');
      }
      return;
    }
    
    // Warn if still building
    if (buildingGraph) {
      setError('Graph is still being built. Visualization may be incomplete.');
    }

    setGraphLoading(true);
    setError(null);
    try {
      const data = await apiService.visualizeGraph(graphQuery, repositoryId);
      
      // Debug logging
      console.log('Graph visualization response:', {
        nodeCount: data.nodes?.length || 0,
        edgeCount: data.edges?.length || 0,
        hasError: !!data.error,
        sampleNodes: data.nodes?.slice(0, 3),
        sampleEdges: data.edges?.slice(0, 3)
      });
      
      // Check for error in response
      if (data.error) {
        setError(data.error);
        setShowGraph(false);
        return;
      }
      
      if (!data.nodes || data.nodes.length === 0) {
        setError('No results found for this query. Try a different search term.');
        setShowGraph(false);
        return;
      }
      
      // Ensure edges array exists
      if (!data.edges) {
        console.warn('No edges in response, using empty array');
        data.edges = [];
      }
      
      setGraphData(data);
      setShowGraph(true);
    } catch (err: any) {
      setError(err.message || 'Failed to generate graph visualization');
      setShowGraph(false);
    } finally {
      setGraphLoading(false);
    }
  };

  if (loading) {
    return (
      <div className="repository-viewer">
        <div className="loading">Loading repository metadata...</div>
      </div>
    );
  }

  if (error && !metadata) {
    return (
      <div className="repository-viewer">
        <div className="error">Error: {error}</div>
      </div>
    );
  }

  if (!metadata) {
    return null;
  }

  const formatDate = (dateString?: string) => {
    if (!dateString) return 'Never';
    return new Date(dateString).toLocaleString();
  };

  return (
    <div className="repository-viewer">
      <div className="repository-viewer-header">
        <h2>{metadata.name}</h2>
        {onClose && (
          <button className="close-button" onClick={onClose}>
            ×
          </button>
        )}
      </div>

      {error && <div className="error-banner">{error}</div>}

      <div className="repository-metadata">
        <div className="metadata-section">
          <h3>Overview</h3>
          <div className="metadata-grid">
            <div className="metadata-item">
              <span className="metadata-label">Status</span>
              <span className={`metadata-value status-${metadata.status}`}>
                {metadata.status}
              </span>
            </div>
            <div className="metadata-item">
              <span className="metadata-label">Files</span>
              <span className="metadata-value">{metadata.file_count || 0}</span>
            </div>
            <div className="metadata-item">
              <span className="metadata-label">Chunks</span>
              <span className="metadata-value">{metadata.chunk_count || 0}</span>
            </div>
            <div className="metadata-item">
              <span className="metadata-label">Methods</span>
              <span className="metadata-value">{metadata.method_count || 0}</span>
            </div>
            <div className="metadata-item">
              <span className="metadata-label">Classes</span>
              <span className="metadata-value">{metadata.class_count || 0}</span>
            </div>
            <div className="metadata-item">
              <span className="metadata-label">Last Indexed</span>
              <span className="metadata-value">{formatDate(metadata.last_indexed_at)}</span>
            </div>
          </div>
        </div>

        {metadata.languages && metadata.languages.length > 0 && (
          <div className="metadata-section">
            <h3>Languages</h3>
            <div className="languages-list">
              {metadata.languages.map((lang, idx) => (
                <span key={idx} className="language-badge">
                  {lang}
                </span>
              ))}
            </div>
          </div>
        )}

        <div className="metadata-section">
          <h3>Repository Details</h3>
          <div className="metadata-details">
            {metadata.github_url && (
              <div className="detail-item">
                <span className="detail-label">GitHub URL</span>
                <a href={metadata.github_url} target="_blank" rel="noopener noreferrer">
                  {metadata.github_url}
                </a>
              </div>
            )}
            {metadata.local_path && (
              <div className="detail-item">
                <span className="detail-label">Local Path</span>
                <code>{metadata.local_path}</code>
              </div>
            )}
            {metadata.description && (
              <div className="detail-item">
                <span className="detail-label">Description</span>
                <span>{metadata.description}</span>
              </div>
            )}
          </div>
        </div>

        <div className="metadata-section">
          <h3>Graph Statistics</h3>
          <div className="graph-stats">
            <div className="stat-item">
              <span className="stat-label">Nodes</span>
              <span className="stat-value">
                {buildingGraph && realtimeGraphStats !== null
                  ? realtimeGraphStats.nodes 
                  : metadata.graph_stats?.nodes || 0}
              </span>
            </div>
            <div className="stat-item">
              <span className="stat-label">Edges</span>
              <span className="stat-value">
                {buildingGraph && realtimeGraphStats !== null
                  ? realtimeGraphStats.edges 
                  : metadata.graph_stats?.edges || 0}
              </span>
            </div>
          </div>
          
          {/* Build/Rebuild Graph Section */}
          <div style={{ marginTop: '1rem', padding: '1rem', background: '#f8f9fa', borderRadius: '8px' }}>
            {buildingGraph && (
              <div style={{ marginBottom: '1rem' }}>
                <div style={{ display: 'flex', justifyContent: 'space-between', marginBottom: '0.5rem' }}>
                  <span style={{ fontSize: '0.875rem', color: '#666' }}>
                    {buildMessage || 'Building graph...'}
                  </span>
                  <span style={{ fontSize: '0.875rem', color: '#666', fontWeight: 'bold' }}>
                    {buildProgress}%
                  </span>
                </div>
                <div style={{ 
                  width: '100%', 
                  height: '8px', 
                  background: '#e5e7eb', 
                  borderRadius: '4px',
                  overflow: 'hidden'
                }}>
                  <div style={{
                    width: `${buildProgress}%`,
                    height: '100%',
                    background: buildStatus === 'failed' ? '#ef4444' : '#F89820',
                    transition: 'width 0.3s ease',
                    borderRadius: '4px'
                  }} />
                </div>
                {buildStatus && (
                  <p style={{ fontSize: '0.75rem', color: '#666', marginTop: '0.5rem' }}>
                    Status: {buildStatus}
                  </p>
                )}
              </div>
            )}
            
            {(!metadata.graph_stats || metadata.graph_stats.nodes === 0) && !buildingGraph && (!realtimeGraphStats || realtimeGraphStats.nodes === 0) ? (
              <>
                <p style={{ fontSize: '0.875rem', color: '#666', marginBottom: '0.5rem' }}>
                  Graph not built yet. Build the knowledge graph to see relationships between code entities.
                </p>
                <button
                  onClick={() => handleBuildGraph(false)}
                  disabled={buildingGraph || metadata.chunk_count === 0}
                  className="visualize-button"
                  style={{ marginTop: '0.5rem' }}
                >
                  Build Knowledge Graph
                </button>
                {metadata.chunk_count === 0 && (
                  <p style={{ fontSize: '0.75rem', color: '#999', marginTop: '0.5rem', fontStyle: 'italic' }}>
                    Repository must be indexed first before building the graph.
                  </p>
                )}
              </>
            ) : (
              <>
                <div style={{ display: 'flex', gap: '0.5rem', alignItems: 'center' }}>
                  <button
                    onClick={() => handleBuildGraph(true)}
                    disabled={buildingGraph || metadata.chunk_count === 0}
                    className="visualize-button"
                    style={{ 
                      flex: 1,
                      background: buildingGraph ? '#9ca3af' : '#F89820'
                    }}
                  >
                    {buildingGraph ? 'Rebuilding Graph...' : 'Rebuild Graph'}
                  </button>
                </div>
                {buildMessage && !buildingGraph && buildStatus !== 'failed' && (
                  <p style={{ 
                    fontSize: '0.875rem', 
                    color: '#10b981',
                    marginTop: '0.5rem',
                    fontWeight: '500'
                  }}>
                    {buildMessage}
                  </p>
                )}
              </>
            )}
          </div>
        </div>

        <div className="metadata-section">
          <h3>Graph Visualization</h3>
          <div className="graph-search">
            <input
              type="text"
              value={graphQuery}
              onChange={(e) => setGraphQuery(e.target.value)}
              placeholder="Enter search query to visualize graph structure..."
              className="graph-search-input"
              onKeyPress={(e) => {
                if (e.key === 'Enter') {
                  handleVisualizeGraph();
                }
              }}
            />
            <button
              onClick={handleVisualizeGraph}
              disabled={!graphQuery.trim() || graphLoading}
              className="visualize-button"
            >
              {graphLoading ? 'Loading...' : 'Visualize Graph'}
            </button>
          </div>
          {error && (
            <div style={{ 
              marginTop: '1rem', 
              padding: '0.75rem', 
              background: '#fee2e2', 
              border: '1px solid #fecaca',
              borderRadius: '8px',
              color: '#991b1b'
            }}>
              {error}
            </div>
          )}
          {showGraph && graphData && graphData.nodes && graphData.nodes.length > 0 && (
            <div className="graph-container" style={{ marginTop: '1rem' }}>
              <GraphVisualization nodes={graphData.nodes} edges={graphData.edges || []} />
            </div>
          )}
        </div>
      </div>
    </div>
  );
};

export default RepositoryViewer;

