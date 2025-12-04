/**
 * Java Repositories Page
 * 
 * A dedicated page for managing Java repositories with improved UI:
 * - Search and filter functionality
 * - Status filtering
 * - Better navigation
 * - Enhanced repository cards
 */
import React, { useState } from 'react';
import JavaRepositoryList from '../components/JavaRepositoryList';
import './JavaRepositoriesPage.css';

const JavaRepositoriesPage: React.FC = () => {
  const [searchQuery, setSearchQuery] = useState('');
  const [statusFilter, setStatusFilter] = useState<string>('all');

  const handleBackToMarketplace = () => {
    window.location.href = '/marketplace.html';
  };

  return (
    <div className="java-repositories-page">
      {/* Header with Navigation */}
      <div className="page-header">
        <div className="header-content">
          <button className="back-button" onClick={handleBackToMarketplace}>
            <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
              <path d="M19 12H5M12 19l-7-7 7-7" />
            </svg>
            Back to Marketplace
          </button>
          <div className="header-title-section">
            <div className="title-icon">☕</div>
            <div>
              <h1>Java Repositories</h1>
              <p className="page-subtitle">Manage and monitor your indexed Java codebases</p>
            </div>
          </div>
        </div>
      </div>

      {/* Main Content */}
      <div className="page-content">
        <JavaRepositoryList 
          searchQuery={searchQuery}
          statusFilter={statusFilter}
          onSearchChange={setSearchQuery}
          onStatusFilterChange={setStatusFilter}
        />
      </div>
    </div>
  );
};

export default JavaRepositoriesPage;

