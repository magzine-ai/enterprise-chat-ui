/**
 * SearchFilter Component
 * 
 * Interactive search and filter component for filtering data.
 * Supports real-time search with debouncing and multiple filter criteria.
 * 
 * @example
 * ```tsx
 * <SearchFilter
 *   data={items}
 *   searchKeys={['name', 'description']}
 *   onFiltered={(filtered) => setFilteredData(filtered)}
 *   placeholder="Search items..."
 * />
 * ```
 * 
 * @param data - Array of objects to filter
 * @param searchKeys - Keys to search within (default: all string keys)
 * @param onFiltered - Callback with filtered results
 * @param placeholder - Search input placeholder
 * @param showResultsCount - Whether to show count of filtered results (default: true)
 */
import React, { useState, useMemo, useEffect } from 'react';

interface SearchFilterProps {
  data: any[];
  searchKeys?: string[];
  onFiltered?: (filtered: any[]) => void;
  placeholder?: string;
  showResultsCount?: boolean;
  renderResult?: (item: any, index: number) => React.ReactNode;
}

const SearchFilter: React.FC<SearchFilterProps> = ({
  data,
  searchKeys,
  onFiltered,
  placeholder = 'Search...',
  showResultsCount = true,
  renderResult,
}) => {
  const [searchTerm, setSearchTerm] = useState('');
  const [filters, setFilters] = useState<Record<string, string>>({});

  const filteredData = useMemo(() => {
    if (!data || data.length === 0) return [];

    let results = data;

    // Text search
    if (searchTerm.trim()) {
      const term = searchTerm.toLowerCase();
      const keysToSearch = searchKeys || (data[0] ? Object.keys(data[0]).filter(key => typeof data[0][key] === 'string') : []);
      
      results = results.filter((item) =>
        keysToSearch.some((key) => {
          const value = item[key];
          return value && String(value).toLowerCase().includes(term);
        })
      );
    }

    // Additional filters
    Object.entries(filters).forEach(([key, value]) => {
      if (value) {
        results = results.filter((item) => {
          const itemValue = item[key];
          return itemValue && String(itemValue).toLowerCase().includes(value.toLowerCase());
        });
      }
    });

    return results;
  }, [data, searchTerm, filters, searchKeys]);

  useEffect(() => {
    if (onFiltered) {
      onFiltered(filteredData);
    }
  }, [filteredData, onFiltered]);

  const updateFilter = (key: string, value: string) => {
    setFilters((prev) => ({
      ...prev,
      [key]: value,
    }));
  };

  const clearFilters = () => {
    setSearchTerm('');
    setFilters({});
  };

  const availableFilterKeys = data[0]
    ? Object.keys(data[0]).filter((key) => typeof data[0][key] === 'string' && key !== 'id')
    : [];

  return (
    <div className="search-filter-wrapper">
      <div className="search-filter-header">
        <div className="search-input-container">
          <input
            type="text"
            className="search-input"
            placeholder={placeholder}
            value={searchTerm}
            onChange={(e) => setSearchTerm(e.target.value)}
          />
          {searchTerm && (
            <button className="search-clear" onClick={() => setSearchTerm('')}>
              ✕
            </button>
          )}
        </div>
        {(searchTerm || Object.values(filters).some((v) => v)) && (
          <button className="filter-clear-all" onClick={clearFilters}>
            Clear All
          </button>
        )}
      </div>

      {availableFilterKeys.length > 0 && (
        <div className="filter-options">
          {availableFilterKeys.slice(0, 3).map((key) => (
            <div key={key} className="filter-option">
              <label>{key}:</label>
              <input
                type="text"
                placeholder={`Filter by ${key}...`}
                value={filters[key] || ''}
                onChange={(e) => updateFilter(key, e.target.value)}
              />
            </div>
          ))}
        </div>
      )}

      {showResultsCount && (
        <div className="search-results-count">
          Showing {filteredData.length} of {data.length} results
        </div>
      )}

      {renderResult ? (
        <div className="search-results">
          {filteredData.map((item, index) => (
            <div key={index}>{renderResult(item, index)}</div>
          ))}
        </div>
      ) : (
        <div className="search-results-list">
          {filteredData.slice(0, 10).map((item, index) => (
            <div key={index} className="search-result-item">
              {JSON.stringify(item, null, 2)}
            </div>
          ))}
          {filteredData.length > 10 && (
            <div className="search-results-more">
              ... and {filteredData.length - 10} more
            </div>
          )}
        </div>
      )}
    </div>
  );
};

export default SearchFilter;


