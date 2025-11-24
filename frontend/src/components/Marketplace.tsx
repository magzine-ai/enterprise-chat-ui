/**
 * Marketplace Component
 * 
 * A modern marketplace-style interface showing available onboarding components.
 * Features:
 * - Hero section with search
 * - Category filtering
 * - Beautiful component cards with hover effects
 * - Featured components section
 * - Recent activity
 */
import React, { useState, useMemo } from 'react';
import SplunkOnboarding from './onboarding/SplunkOnboarding';
import GrafanaOnboarding from './onboarding/GrafanaOnboarding';
import './Marketplace.css';

interface OnboardingComponent {
  id: string;
  name: string;
  description: string;
  longDescription?: string;
  icon: string;
  category: string;
  color: string;
  gradient: string;
  featured?: boolean;
  tags: string[];
  estimatedTime?: string;
  difficulty?: 'Beginner' | 'Intermediate' | 'Advanced';
}

const ONBOARDING_COMPONENTS: OnboardingComponent[] = [
  {
    id: 'splunk',
    name: 'Splunk Onboarding',
    description: 'Configure and set up Splunk integration with step-by-step guidance',
    longDescription: 'Complete index profiling, field discovery, relationship mapping, and metadata configuration for your Splunk instance.',
    icon: '📊',
    category: 'Monitoring',
    color: '#65A637',
    gradient: 'linear-gradient(135deg, #65A637 0%, #4A7C2A 100%)',
    featured: true,
    tags: ['Splunk', 'Logging', 'Analytics', 'Indexing'],
    estimatedTime: '15-20 min',
    difficulty: 'Intermediate',
  },
  {
    id: 'grafana',
    name: 'Grafana Onboarding',
    description: 'Get started with Grafana dashboards and data sources',
    longDescription: 'Connect your Grafana instance, configure data sources, and set up beautiful dashboards for visualization.',
    icon: '📈',
    category: 'Visualization',
    color: '#F46800',
    gradient: 'linear-gradient(135deg, #F46800 0%, #D85A00 100%)',
    featured: true,
    tags: ['Grafana', 'Dashboards', 'Metrics', 'Visualization'],
    estimatedTime: '10-15 min',
    difficulty: 'Beginner',
  },
  {
    id: 'elasticsearch',
    name: 'Elasticsearch Onboarding',
    description: 'Set up Elasticsearch clusters and configure indices',
    icon: '🔍',
    category: 'Search',
    color: '#005571',
    gradient: 'linear-gradient(135deg, #005571 0%, #003D4F 100%)',
    tags: ['Elasticsearch', 'Search', 'Analytics'],
    estimatedTime: '20-25 min',
    difficulty: 'Advanced',
  },
  {
    id: 'prometheus',
    name: 'Prometheus Onboarding',
    description: 'Configure Prometheus monitoring and alerting',
    icon: '⚡',
    category: 'Monitoring',
    color: '#E6522C',
    gradient: 'linear-gradient(135deg, #E6522C 0%, #C43E1F 100%)',
    tags: ['Prometheus', 'Metrics', 'Alerting'],
    estimatedTime: '15-20 min',
    difficulty: 'Intermediate',
  },
  {
    id: 'datadog',
    name: 'Datadog Onboarding',
    description: 'Integrate Datadog for comprehensive monitoring',
    icon: '🐕',
    category: 'Monitoring',
    color: '#632CA6',
    gradient: 'linear-gradient(135deg, #632CA6 0%, #4A1F7A 100%)',
    tags: ['Datadog', 'APM', 'Monitoring'],
    estimatedTime: '10-15 min',
    difficulty: 'Beginner',
  },
  {
    id: 'newrelic',
    name: 'New Relic Onboarding',
    description: 'Set up New Relic for application performance monitoring',
    icon: '🔮',
    category: 'Monitoring',
    color: '#00AC69',
    gradient: 'linear-gradient(135deg, #00AC69 0%, #008A54 100%)',
    tags: ['New Relic', 'APM', 'Performance'],
    estimatedTime: '12-18 min',
    difficulty: 'Intermediate',
  },
];

type ViewMode = 'marketplace' | 'onboarding';

const Marketplace: React.FC = () => {
  const [selectedComponent, setSelectedComponent] = useState<string | null>(null);
  const [viewMode, setViewMode] = useState<ViewMode>('marketplace');
  const [searchQuery, setSearchQuery] = useState('');
  const [selectedCategory, setSelectedCategory] = useState<string>('All');
  const [hoveredCard, setHoveredCard] = useState<string | null>(null);

  const categories = ['All', ...Array.from(new Set(ONBOARDING_COMPONENTS.map(c => c.category)))];

  const filteredComponents = useMemo(() => {
    return ONBOARDING_COMPONENTS.filter(component => {
      const matchesSearch = 
        component.name.toLowerCase().includes(searchQuery.toLowerCase()) ||
        component.description.toLowerCase().includes(searchQuery.toLowerCase()) ||
        component.tags.some(tag => tag.toLowerCase().includes(searchQuery.toLowerCase()));
      
      const matchesCategory = selectedCategory === 'All' || component.category === selectedCategory;
      
      return matchesSearch && matchesCategory;
    });
  }, [searchQuery, selectedCategory]);

  const featuredComponents = ONBOARDING_COMPONENTS.filter(c => c.featured);
  const otherComponents = filteredComponents.filter(c => !c.featured);

  const handleComponentClick = (componentId: string) => {
    setSelectedComponent(componentId);
    setViewMode('onboarding');
  };

  const handleBackToMarketplace = () => {
    setSelectedComponent(null);
    setViewMode('marketplace');
  };

  if (viewMode === 'onboarding' && selectedComponent) {
    if (selectedComponent === 'splunk') {
      return <SplunkOnboarding onBack={handleBackToMarketplace} />;
    }
    if (selectedComponent === 'grafana') {
      return <GrafanaOnboarding onBack={handleBackToMarketplace} />;
    }
  }

  return (
    <div className="marketplace-container">
      {/* Navigation Header */}
      <div className="marketplace-nav-header">
        <button
          className="marketplace-nav-button"
          onClick={() => {
            window.location.href = '/';
          }}
          title="Back to Chat UI"
        >
          <svg
            xmlns="http://www.w3.org/2000/svg"
            width="18"
            height="18"
            viewBox="0 0 24 24"
            fill="none"
            stroke="currentColor"
            strokeWidth="2"
            strokeLinecap="round"
            strokeLinejoin="round"
          >
            <path d="M19 12H5M12 19l-7-7 7-7" />
          </svg>
          <span>Back to Chat</span>
        </button>
      </div>

      {/* Hero Section */}
      <div className="marketplace-hero">
        <div className="marketplace-hero-content">
          <h1 className="marketplace-hero-title">
            Administration Marketplace
          </h1>
          <p className="marketplace-hero-subtitle">
            Discover and configure integration components to enhance your infrastructure
          </p>
          
          {/* Search Bar */}
          <div className="marketplace-search-container">
            <div className="marketplace-search-wrapper">
              <svg
                className="search-icon"
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
                <circle cx="11" cy="11" r="8" />
                <path d="m21 21-4.35-4.35" />
              </svg>
              <input
                type="text"
                className="marketplace-search-input"
                placeholder="Search components, tags, or categories..."
                value={searchQuery}
                onChange={(e) => setSearchQuery(e.target.value)}
              />
              {searchQuery && (
                <button
                  className="search-clear-btn"
                  onClick={() => setSearchQuery('')}
                >
                  ✕
                </button>
              )}
            </div>
          </div>

          {/* Category Filter */}
          <div className="marketplace-categories">
            {categories.map((category) => (
              <button
                key={category}
                className={`category-chip ${selectedCategory === category ? 'active' : ''}`}
                onClick={() => setSelectedCategory(category)}
              >
                {category}
              </button>
            ))}
          </div>
        </div>
      </div>

      {/* Main Content */}
      <div className="marketplace-content-wrapper">
        {/* Featured Section */}
        {featuredComponents.length > 0 && searchQuery === '' && selectedCategory === 'All' && (
          <section className="marketplace-section">
            <div className="section-header">
              <div className="section-title-group">
                <h2 className="section-title">Featured Components</h2>
                <span className="section-badge">Popular</span>
              </div>
              <p className="section-description">
                Most commonly used integrations to get you started
              </p>
            </div>
            <div className="marketplace-grid featured-grid">
              {featuredComponents.map((component) => (
                <div
                  key={component.id}
                  className={`marketplace-card featured-card`}
                  onClick={() => handleComponentClick(component.id)}
                  onMouseEnter={() => setHoveredCard(component.id)}
                  onMouseLeave={() => setHoveredCard(null)}
                  style={{
                    '--card-color': component.color,
                    '--card-gradient': component.gradient,
                  } as React.CSSProperties}
                >
                  <div className="card-featured-badge">⭐ Featured</div>
                  <div className="card-icon-wrapper" style={{ background: component.gradient }}>
                    <span className="card-icon">{component.icon}</span>
                  </div>
                  <div className="card-content">
                    <h3 className="card-title">{component.name}</h3>
                    <p className="card-description">{component.description}</p>
                    <div className="card-tags">
                      {component.tags.slice(0, 3).map((tag) => (
                        <span key={tag} className="card-tag">{tag}</span>
                      ))}
                    </div>
                    <div className="card-footer">
                      <div className="card-meta">
                        {component.estimatedTime && (
                          <span className="card-meta-item">
                            <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                              <circle cx="12" cy="12" r="10" />
                              <polyline points="12 6 12 12 16 14" />
                            </svg>
                            {component.estimatedTime}
                          </span>
                        )}
                        {component.difficulty && (
                          <span className="card-meta-item">
                            <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                              <path d="M12 2L2 7l10 5 10-5-10-5z" />
                              <path d="M2 17l10 5 10-5M2 12l10 5 10-5" />
                            </svg>
                            {component.difficulty}
                          </span>
                        )}
                      </div>
                      <div className="card-arrow">
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
                          <path d="M5 12h14M12 5l7 7-7 7" />
                        </svg>
                      </div>
                    </div>
                  </div>
                </div>
              ))}
            </div>
          </section>
        )}

        {/* All Components Section */}
        <section className="marketplace-section">
          <div className="section-header">
            <h2 className="section-title">
              {searchQuery || selectedCategory !== 'All' 
                ? `Search Results (${otherComponents.length})` 
                : 'All Components'}
            </h2>
            {!searchQuery && selectedCategory === 'All' && (
              <p className="section-description">
                Browse all available integration components
              </p>
            )}
          </div>
          
          {otherComponents.length > 0 ? (
            <div className="marketplace-grid">
              {otherComponents.map((component) => (
                <div
                  key={component.id}
                  className="marketplace-card"
                  onClick={() => handleComponentClick(component.id)}
                  onMouseEnter={() => setHoveredCard(component.id)}
                  onMouseLeave={() => setHoveredCard(null)}
                  style={{
                    '--card-color': component.color,
                    '--card-gradient': component.gradient,
                  } as React.CSSProperties}
                >
                  <div className="card-icon-wrapper" style={{ background: component.gradient }}>
                    <span className="card-icon">{component.icon}</span>
                  </div>
                  <div className="card-content">
                    <h3 className="card-title">{component.name}</h3>
                    <p className="card-description">{component.description}</p>
                    <div className="card-tags">
                      {component.tags.slice(0, 2).map((tag) => (
                        <span key={tag} className="card-tag">{tag}</span>
                      ))}
                      {component.tags.length > 2 && (
                        <span className="card-tag">+{component.tags.length - 2}</span>
                      )}
                    </div>
                    <div className="card-footer">
                      <div className="card-meta">
                        {component.estimatedTime && (
                          <span className="card-meta-item">
                            <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                              <circle cx="12" cy="12" r="10" />
                              <polyline points="12 6 12 12 16 14" />
                            </svg>
                            {component.estimatedTime}
                          </span>
                        )}
                      </div>
                      <div className="card-arrow">
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
                          <path d="M5 12h14M12 5l7 7-7 7" />
                        </svg>
                      </div>
                    </div>
                  </div>
                </div>
              ))}
            </div>
          ) : (
            <div className="marketplace-empty-state">
              <div className="empty-state-icon">🔍</div>
              <h3 className="empty-state-title">No components found</h3>
              <p className="empty-state-description">
                Try adjusting your search or filter criteria
              </p>
              <button
                className="empty-state-button"
                onClick={() => {
                  setSearchQuery('');
                  setSelectedCategory('All');
                }}
              >
                Clear Filters
              </button>
            </div>
          )}
        </section>
      </div>
    </div>
  );
};

export default Marketplace;
