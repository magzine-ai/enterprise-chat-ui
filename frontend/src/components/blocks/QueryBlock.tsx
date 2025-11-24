/**
 * QueryBlock Component
 * 
 * Displays executable SQL or Splunk queries with run functionality.
 * Executes queries and displays results in a table format.
 * Supports editing queries and regenerating results.
 * Supports opening in popup or new tab for better viewing.
 * 
 * Features:
 * - Edit query text inline
 * - Execute edited queries
 * - Save/Cancel edit mode
 * - Auto-generates different mock results based on query content
 * 
 * @example
 * ```tsx
 * <QueryBlock 
 *   query="index=web_logs | stats count by status"
 *   language="spl"
 *   onExecute={(query) => executeSplunkQuery(query)}
 * />
 * ```
 * 
 * @param query - The query string to display and execute
 * @param language - Query language type: 'sql' or 'spl' (Splunk)
 * @param onExecute - Callback function when query is executed. Receives query string and returns Promise<QueryResult>
 * @param title - Optional title for the query block
 * @param autoExecute - Whether to auto-execute on mount (default: false)
 */
import React, { useState, useEffect, useRef } from 'react';
import CodeBlock from './CodeBlock';
import DataTable from './DataTable';
import SplunkChart from './SplunkChart';

interface QueryResult {
  columns: string[];
  rows: any[][];
  rowCount: number;
  executionTime?: number;
  visualizationType?: 'table' | 'chart' | 'single-value' | 'gauge' | 'map' | 'heatmap' | 'scatter';
  visualizationConfig?: {
    chartType?: 'line' | 'bar' | 'area' | 'pie' | 'column';
    xAxis?: string;
    yAxis?: string;
    series?: string[];
    format?: string; // For single value: 'number', 'percent', 'currency', etc.
    valueField?: string;
    labelField?: string;
    unit?: string; // For single value: 'ms', 'GB', etc.
  };
  singleValue?: number;
  gaugeValue?: number;
  chartData?: any[];
  isTimeSeries?: boolean;
  allowChartTypeSwitch?: boolean;
}

interface QueryBlockProps {
  query: string;
  language: 'sql' | 'spl';
  onExecute?: (query: string) => Promise<QueryResult>;
  title?: string;
  autoExecute?: boolean;
}

const QueryBlock: React.FC<QueryBlockProps> = ({
  query,
  language,
  onExecute,
  title,
  autoExecute = false,
}) => {
  const [isExecuting, setIsExecuting] = useState(false);
  const [result, setResult] = useState<QueryResult | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [isEditing, setIsEditing] = useState(false);
  const [editedQuery, setEditedQuery] = useState(query);
  const [selectedChartType, setSelectedChartType] = useState<'line' | 'bar' | 'area' | 'column' | 'pie'>('line');

  useEffect(() => {
    if (autoExecute && onExecute) {
      handleExecute();
    }
  }, [autoExecute]);

  useEffect(() => {
    // Update edited query when prop changes
    setEditedQuery(query);
  }, [query]);

  useEffect(() => {
    // Reset chart type to line when new time series result is loaded
    if (result?.visualizationType === 'chart' && (result as any).isTimeSeries) {
      setSelectedChartType('line');
    }
  }, [result]);

  const handleExecute = async () => {
    const queryToExecute = isEditing ? editedQuery : query;
    
    if (!onExecute) {
      // Use mock execution if no handler provided
      executeMockQuery(queryToExecute);
      return;
    }

    setIsExecuting(true);
    setError(null);
    try {
      const queryResult = await onExecute(queryToExecute);
      setResult(queryResult);
      // Exit edit mode after successful execution
      setIsEditing(false);
    } catch (err: any) {
      setError(err.message || 'Failed to execute query');
    } finally {
      setIsExecuting(false);
    }
  };

  const handleEdit = () => {
    setIsEditing(true);
    setEditedQuery(query);
  };

  const handleCancelEdit = () => {
    setIsEditing(false);
    setEditedQuery(query);
    setError(null);
  };

  const handleSaveEdit = () => {
    setIsEditing(false);
    // Optionally execute the edited query automatically
    // handleExecute();
  };

  const executeMockQuery = (queryToExecute?: string) => {
    setIsExecuting(true);
    setError(null);
    
    // Simulate query execution
    setTimeout(() => {
      // Generate different results based on query content
      const queryText = (queryToExecute || query).toLowerCase();
      const isTimechart = queryText.includes('timechart');
      const isStats = queryText.includes('stats');
      const isSingleValue = queryText.includes('stats count') || queryText.includes('stats sum') || queryText.includes('stats avg');
      const isGauge = queryText.includes('gauge') || queryText.includes('percent');
      const isPie = queryText.includes('by') && (queryText.includes('pie') || queryText.match(/stats.*count.*by/));
      const isBar = queryText.includes('bar') || (queryText.includes('stats') && queryText.includes('by') && !isPie);
      
      let mockResult: QueryResult;
      
      if (isTimechart) {
        // Timechart - show as time series chart with multiple chart type options
        const chartData = Array.from({ length: 24 }, (_, i) => {
          const hour = String(i).padStart(2, '0') + ':00';
          return {
            time: hour,
            count: Math.floor(Math.random() * 1000) + 500,
            avg: Math.random() * 100 + 50,
          };
        });
        
        mockResult = {
          columns: ['_time', 'count', 'avg'],
          rows: chartData.map(d => [d.time, String(d.count), String(d.avg.toFixed(2))]),
          rowCount: 24,
          executionTime: Math.random() * 1000 + 200,
          visualizationType: 'chart',
          visualizationConfig: {
            chartType: 'line',
            xAxis: 'time',
            yAxis: 'count',
            series: ['count', 'avg'],
          },
          // Store chart data separately for rendering
          chartData: chartData,
          isTimeSeries: true, // Flag to enable chart type selector
        } as any;
      } else if (isSingleValue && !isGauge) {
        // Single value query (e.g., stats count)
        const value = Math.floor(Math.random() * 10000) + 1000;
        mockResult = {
          columns: ['count'],
          rows: [[String(value)]],
          rowCount: 1,
          executionTime: Math.random() * 500 + 100,
          visualizationType: 'single-value',
          visualizationConfig: {
            format: 'number',
            valueField: 'count',
          },
          singleValue: value,
        };
      } else if (isGauge) {
        // Gauge visualization
        const value = Math.floor(Math.random() * 100);
        mockResult = {
          columns: ['value', 'max'],
          rows: [[String(value), '100']],
          rowCount: 1,
          executionTime: Math.random() * 500 + 100,
          visualizationType: 'gauge',
          visualizationConfig: {
            format: 'percent',
            valueField: 'value',
          },
          gaugeValue: value,
        };
      } else if (isPie) {
        // Pie chart
        const pieData = [
          { name: 'Success', value: 1250 },
          { name: 'Warning', value: 150 },
          { name: 'Error', value: 75 },
          { name: 'Info', value: 200 },
        ];
        mockResult = {
          columns: ['status', 'count'],
          rows: pieData.map(d => [d.name, String(d.value)]),
          rowCount: 4,
          executionTime: Math.random() * 1000 + 200,
          visualizationType: 'chart',
          visualizationConfig: {
            chartType: 'pie',
            labelField: 'name',
            valueField: 'value',
          },
          chartData: pieData,
        };
      } else if (isBar || isStats) {
        // Bar chart for stats by field - also allow chart type switching
        const barData = language === 'spl'
          ? [
              { name: '200', value: 1250 },
              { name: '404', value: 150 },
              { name: '500', value: 75 },
            ]
          : [
              { name: 'Category A', value: 500 },
              { name: 'Category B', value: 300 },
              { name: 'Category C', value: 200 },
            ];
        mockResult = {
          columns: language === 'spl' 
            ? ['status', 'count']
            : ['category', 'count'],
          rows: barData.map(d => [d.name, String(d.value)]),
          rowCount: barData.length,
          executionTime: Math.random() * 1000 + 200,
          visualizationType: 'chart',
          visualizationConfig: {
            chartType: 'bar',
            xAxis: 'name',
            yAxis: 'value',
          },
          chartData: barData,
          isTimeSeries: false, // Not time series, but still allow chart type switching
          allowChartTypeSwitch: true, // Flag to enable chart type selector
        } as any;
      } else {
        // Default table view
        mockResult = {
          columns: ['id', 'name', 'value', 'timestamp'],
          rows: [
            ['1', 'User A', '100', '2024-01-15 10:30:00'],
            ['2', 'User B', '200', '2024-01-15 11:00:00'],
            ['3', 'User C', '150', '2024-01-15 11:30:00'],
          ],
          rowCount: 3,
          executionTime: Math.random() * 1000 + 200,
          visualizationType: 'table',
        };
      }
      
      setResult(mockResult as any);
      setIsExecuting(false);
      setIsEditing(false);
    }, 800);
  };

  const queryRef = React.useRef<HTMLDivElement>(null);

  const handleOpenPopup = () => {
    const left = Math.round((window.screen.width - 1200) / 2);
    const top = Math.round((window.screen.height - 800) / 2);
    const queryHTML = queryRef.current?.innerHTML || '';
    const htmlContent = `
      <!DOCTYPE html>
      <html>
        <head>
          <title>Query View</title>
          <meta charset="utf-8">
          <style>
            * { margin: 0; padding: 0; box-sizing: border-box; }
            body { 
              margin: 0; 
              padding: 20px; 
              font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', 'Roboto', sans-serif; 
              background: #f5f5f5; 
            }
            .popup-query-container {
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
          <div class="popup-query-container">
            <h2>${title || 'Query'}</h2>
            ${queryHTML}
          </div>
        </body>
      </html>
    `;
    
    // Open as popup window
    const popup = window.open(
      '',
      'queryPopup',
      `width=1200,height=800,left=${left},top=${top},resizable=yes,scrollbars=yes,toolbar=no,menubar=no,location=no,status=no`
    );
    
    if (popup) {
      popup.document.open();
      popup.document.write(htmlContent);
      popup.document.close();
      popup.focus();
    } else {
      alert('Popup blocked. Opening in new tab instead.');
      handleOpenNewTab();
    }
  };

  const handleOpenNewTab = () => {
    const queryHTML = queryRef.current?.innerHTML || '';
    const htmlContent = `
      <!DOCTYPE html>
      <html>
        <head>
          <title>Query View</title>
          <meta charset="utf-8">
          <style>
            * { margin: 0; padding: 0; box-sizing: border-box; }
            body { 
              margin: 0; 
              padding: 20px; 
              font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', 'Roboto', sans-serif; 
              background: #f5f5f5; 
            }
            .tab-query-container {
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
          <div class="tab-query-container">
            <h2>${title || 'Query'}</h2>
            ${queryHTML}
          </div>
        </body>
      </html>
    `;
    
    // Open in new tab (full browser tab)
    const newTab = window.open('', '_blank');
    if (newTab) {
      newTab.document.open();
      newTab.document.write(htmlContent);
      newTab.document.close();
    }
  };

  return (
    <div ref={queryRef} className="query-block-wrapper">
      <div className="query-block-header">
        <div className="query-block-header-left">
          {title && <div className="query-block-title">{title}</div>}
        </div>
        <div className="query-block-header-right">
          {!isEditing ? (
            <>
              <button
                className="query-edit-button"
                onClick={handleEdit}
                title="Edit query"
              >
                ✏️ Edit
              </button>
              <button
                className="query-execute-button"
                onClick={handleExecute}
                disabled={isExecuting}
              >
                {isExecuting ? '⏳ Executing...' : '▶️ Run Query'}
              </button>
            </>
          ) : (
            <>
              <button
                className="query-save-button"
                onClick={handleSaveEdit}
                title="Save changes"
              >
                💾 Save
              </button>
              <button
                className="query-execute-button"
                onClick={handleExecute}
                disabled={isExecuting}
              >
                {isExecuting ? '⏳ Executing...' : '▶️ Run Edited Query'}
              </button>
              <button
                className="query-cancel-button"
                onClick={handleCancelEdit}
                title="Cancel editing"
              >
                ✕ Cancel
              </button>
            </>
          )}
          <button className="query-action-button" onClick={handleOpenPopup} title="Open in popup">
            🔲
          </button>
          <button className="query-action-button" onClick={handleOpenNewTab} title="Open in new tab">
            📑
          </button>
        </div>
      </div>
      
      {isEditing ? (
        <div className="query-editor-container">
          <textarea
            className="query-editor"
            value={editedQuery}
            onChange={(e) => setEditedQuery(e.target.value)}
            placeholder="Enter your query..."
            spellCheck={false}
          />
          <div className="query-editor-info">
            <span>Editing query - Click "Run Edited Query" to execute</span>
          </div>
        </div>
      ) : (
        <CodeBlock code={query} language={language} showCopyButton={true} />
      )}
      
      {isExecuting && (
        <div className="query-loading">
          <div className="loading-dots">
            <div className="loading-dot"></div>
            <div className="loading-dot"></div>
            <div className="loading-dot"></div>
          </div>
          <span>Executing query...</span>
        </div>
      )}
      
      {error && (
        <div className="query-error">
          ❌ Error: {error}
        </div>
      )}
      
      {result && !isExecuting && (
        <div className="query-results">
          <div className="query-results-header">
            <span>Results: {result.rowCount} row{result.rowCount !== 1 ? 's' : ''}</span>
            {result.executionTime && (
              <span className="query-execution-time">
                ⏱️ {result.executionTime.toFixed(0)}ms
              </span>
            )}
          </div>
          
          {/* Render visualization based on type */}
          {result.visualizationType === 'chart' && (result as any).chartData && (
            <div className="query-chart-container">
              {/* Chart type selector for time series data and other charts */}
              {((result as any).isTimeSeries || (result as any).allowChartTypeSwitch) && (
                <div className="chart-type-selector">
                  <span className="chart-type-label">Chart Type:</span>
                  <div className="chart-type-buttons">
                    <button
                      className={`chart-type-btn ${selectedChartType === 'line' ? 'active' : ''}`}
                      onClick={() => setSelectedChartType('line')}
                      title="Line Chart"
                    >
                      <svg xmlns="http://www.w3.org/2000/svg" width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
                        <polyline points="3 12 7 8 11 12 15 8 19 12 21 10"/>
                      </svg>
                      Line
                    </button>
                    <button
                      className={`chart-type-btn ${selectedChartType === 'bar' ? 'active' : ''}`}
                      onClick={() => setSelectedChartType('bar')}
                      title="Bar Chart"
                    >
                      <svg xmlns="http://www.w3.org/2000/svg" width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
                        <line x1="12" y1="20" x2="12" y2="10"/>
                        <line x1="18" y1="20" x2="18" y2="4"/>
                        <line x1="6" y1="20" x2="6" y2="16"/>
                      </svg>
                      Bar
                    </button>
                    <button
                      className={`chart-type-btn ${selectedChartType === 'area' ? 'active' : ''}`}
                      onClick={() => setSelectedChartType('area')}
                      title="Area Chart"
                    >
                      <svg xmlns="http://www.w3.org/2000/svg" width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
                        <polyline points="3 12 7 8 11 12 15 8 19 12 21 10"/>
                        <line x1="3" y1="20" x2="21" y2="20"/>
                      </svg>
                      Area
                    </button>
                    <button
                      className={`chart-type-btn ${selectedChartType === 'column' ? 'active' : ''}`}
                      onClick={() => setSelectedChartType('column')}
                      title="Column Chart"
                    >
                      <svg xmlns="http://www.w3.org/2000/svg" width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
                        <line x1="18" y1="20" x2="18" y2="10"/>
                        <line x1="12" y1="20" x2="12" y2="4"/>
                        <line x1="6" y1="20" x2="6" y2="14"/>
                      </svg>
                      Column
                    </button>
                  </div>
                </div>
              )}
              <SplunkChart
                type={((result as any).isTimeSeries || (result as any).allowChartTypeSwitch) ? selectedChartType : ((result.visualizationConfig?.chartType as any) || 'line')}
                data={(result as any).chartData}
                title={title || 'Query Results'}
                xAxis={result.visualizationConfig?.xAxis || 'name'}
                yAxis={result.visualizationConfig?.yAxis || 'value'}
                series={result.visualizationConfig?.series}
                height={300}
              />
            </div>
          )}
          
          {result.visualizationType === 'single-value' && (
            <div className="single-value-display">
              <div className="single-value-label">Total Count</div>
              <div className="single-value-number">
                {(result as any).singleValue?.toLocaleString() || result.rows[0]?.[0]}
                {result.visualizationConfig?.unit && (
                  <span className="single-value-unit">{result.visualizationConfig.unit}</span>
                )}
              </div>
            </div>
          )}
          
          {result.visualizationType === 'gauge' && (
            <div className="gauge-display">
              <div className="gauge-container">
                <div className="gauge-label">Percentage</div>
                <div className="gauge-circle">
                  <svg viewBox="0 0 120 120" className="gauge-svg">
                    <circle
                      cx="60"
                      cy="60"
                      r="50"
                      fill="none"
                      stroke="#e5e5e6"
                      strokeWidth="10"
                    />
                    <circle
                      cx="60"
                      cy="60"
                      r="50"
                      fill="none"
                      stroke="#19c37d"
                      strokeWidth="10"
                      strokeDasharray={`${2 * Math.PI * 50}`}
                      strokeDashoffset={`${2 * Math.PI * 50 * (1 - ((result as any).gaugeValue / 100))}`}
                      strokeLinecap="round"
                      transform="rotate(-90 60 60)"
                    />
                    <text
                      x="60"
                      y="65"
                      textAnchor="middle"
                      fontSize="24"
                      fontWeight="600"
                      fill="#353740"
                    >
                      {(result as any).gaugeValue}%
                    </text>
                  </svg>
                </div>
              </div>
            </div>
          )}
          
          {/* Always show table as fallback or for table type */}
          {(result.visualizationType === 'table' || !result.visualizationType || 
            (result.visualizationType !== 'chart' && result.visualizationType !== 'single-value' && result.visualizationType !== 'gauge')) && (
            <DataTable columns={result.columns} rows={result.rows} />
          )}
        </div>
      )}
    </div>
  );
};

export default QueryBlock;

