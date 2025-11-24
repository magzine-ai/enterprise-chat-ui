/**
 * SplunkChart Component
 * 
 * Displays data visualizations similar to Splunk's charting capabilities.
 * Supports multiple chart types: line, bar, area, pie, and timechart.
 * 
 * @example
 * ```tsx
 * <SplunkChart
 *   type="timechart"
 *   data={[
 *     { time: '10:00', value: 100 },
 *     { time: '11:00', value: 150 },
 *   ]}
 *   title="Request Rate Over Time"
 * />
 * ```
 * 
 * @param type - Chart type: 'line' | 'bar' | 'area' | 'pie' | 'timechart'
 * @param data - Array of data points
 * @param title - Chart title
 * @param xAxis - X-axis label
 * @param yAxis - Y-axis label
 * @param series - Series configuration for multi-series charts
 * @param showLegend - Whether to show legend (default: true)
 * @param height - Chart height in pixels (default: 300)
 */
import React, { useState } from 'react';
import {
  LineChart,
  Line,
  BarChart,
  Bar,
  AreaChart,
  Area,
  PieChart,
  Pie,
  Cell,
  XAxis,
  YAxis,
  CartesianGrid,
  Tooltip,
  Legend,
} from 'recharts';

interface ChartDataPoint {
  [key: string]: any;
  time?: string;
  name?: string;
  value?: number;
}

interface SplunkChartProps {
  type: 'line' | 'bar' | 'area' | 'pie' | 'timechart' | 'column';
  data: ChartDataPoint[];
  title?: string;
  xAxis?: string;
  yAxis?: string;
  series?: string[];
  showLegend?: boolean;
  height?: number;
  allowChartTypeSwitch?: boolean;
  isTimeSeries?: boolean;
}

const COLORS = ['#19c37d', '#0088FE', '#00C49F', '#FFBB28', '#FF8042', '#8884d8'];

const SplunkChart: React.FC<SplunkChartProps> = ({
  type: initialType,
  data,
  title,
  xAxis = 'name',
  yAxis = 'value',
  series,
  showLegend = true,
  height = 300,
  allowChartTypeSwitch = false,
  isTimeSeries = false,
}) => {
  const [selectedChartType, setSelectedChartType] = useState<'line' | 'bar' | 'area' | 'column' | 'pie'>(() => {
    if (initialType === 'timechart') return 'line';
    if (initialType === 'pie') return 'pie';
    return initialType as 'line' | 'bar' | 'area' | 'column';
  });
  const [chartWidth, setChartWidth] = useState(988);
  const containerRef = React.useRef<HTMLDivElement>(null);

  // Use selected type if switching is allowed, otherwise use initial type
  const type = (allowChartTypeSwitch || isTimeSeries) ? selectedChartType : initialType;

  // Measure container width on mount and resize
  React.useEffect(() => {
    const updateWidth = () => {
      if (containerRef.current) {
        setChartWidth(containerRef.current.offsetWidth);
      }
    };
    updateWidth();
    window.addEventListener('resize', updateWidth);
    return () => window.removeEventListener('resize', updateWidth);
  }, []);
  if (!data || data.length === 0) {
    return <div className="chart-empty">No data available for chart</div>;
  }

  // For timechart, use 'time' as x-axis
  const xAxisKey = (initialType === 'timechart' || isTimeSeries) ? 'time' : (xAxis || 'name');

  // Determine series keys
  let dataKeys: string[] = [];
  if (series && series.length > 0) {
    dataKeys = series;
  } else if (data.length > 0) {
    // Get all keys except x-axis keys
    const excludeKeys = [xAxis, 'time', 'name'];
    dataKeys = Object.keys(data[0]).filter(key => !excludeKeys.includes(key));
  }

  // Debug logging (remove in production)
  if (process.env.NODE_ENV === 'development') {
    console.log('SplunkChart render:', { type, dataLength: data.length, dataKeys, xAxisKey });
  }

  const renderChart = () => {
    // Use selectedChartType for rendering when switching is enabled
    const renderType = (allowChartTypeSwitch || isTimeSeries) && type !== 'pie' 
      ? (selectedChartType === 'column' ? 'bar' : selectedChartType)
      : (type === 'column' ? 'bar' : type);
    
    switch (renderType) {
      case 'line':
      case 'timechart':
        return (
          <LineChart width={chartWidth} height={height} data={data} margin={{ top: 5, right: 30, left: 20, bottom: 5 }}>
            <CartesianGrid strokeDasharray="3 3" />
            <XAxis dataKey={xAxisKey} />
            <YAxis />
            <Tooltip />
            {showLegend && <Legend />}
            {dataKeys.map((key, idx) => (
              <Line
                key={key}
                type="monotone"
                dataKey={key}
                stroke={COLORS[idx % COLORS.length]}
                strokeWidth={2}
              />
            ))}
          </LineChart>
        );

      case 'bar':
        return (
          <BarChart 
            width={chartWidth} 
            height={height}
            data={data} 
            margin={{ top: 5, right: 30, left: 20, bottom: 5 }}
            layout={((allowChartTypeSwitch || isTimeSeries) && selectedChartType === 'column') ? 'vertical' : 'horizontal'}
          >
            <CartesianGrid strokeDasharray="3 3" />
            {((allowChartTypeSwitch || isTimeSeries) && selectedChartType === 'column') ? (
              <>
                <XAxis type="number" />
                <YAxis dataKey={xAxisKey} type="category" width={80} />
              </>
            ) : (
              <>
                <XAxis dataKey={xAxisKey} />
                <YAxis />
              </>
            )}
            <Tooltip />
            {showLegend && <Legend />}
            {dataKeys.map((key, idx) => (
              <Bar
                key={key}
                dataKey={key}
                fill={COLORS[idx % COLORS.length]}
              />
            ))}
          </BarChart>
        );

      case 'area':
        return (
          <AreaChart width={chartWidth} height={height} data={data} margin={{ top: 5, right: 30, left: 20, bottom: 5 }}>
            <CartesianGrid strokeDasharray="3 3" />
            <XAxis dataKey={xAxisKey} />
            <YAxis />
            <Tooltip />
            {showLegend && <Legend />}
            {dataKeys.map((key, idx) => (
              <Area
                key={key}
                type="monotone"
                dataKey={key}
                stroke={COLORS[idx % COLORS.length]}
                fill={COLORS[idx % COLORS.length]}
                fillOpacity={0.6}
              />
            ))}
          </AreaChart>
        );

      case 'pie':
        return (
          <PieChart width={chartWidth} height={height}>
            <Pie
              data={data}
              cx="50%"
              cy="50%"
              labelLine={false}
              label={({ name, percent }) => `${name}: ${(percent * 100).toFixed(0)}%`}
              outerRadius={Math.min(height * 0.3, 120)}
              fill="#8884d8"
              dataKey={yAxis || 'value'}
            >
              {data.map((entry, index) => (
                <Cell key={`cell-${index}`} fill={COLORS[index % COLORS.length]} />
              ))}
            </Pie>
            <Tooltip />
            {showLegend && <Legend />}
          </PieChart>
        );

      default:
        return <div>Unsupported chart type: {type}</div>;
    }
  };

  const chartRef = React.useRef<HTMLDivElement>(null);

  const handleOpenPopup = () => {
    const left = Math.round((window.screen.width - 1200) / 2);
    const top = Math.round((window.screen.height - 800) / 2);
    
    // Create a data URL with the chart content
    const chartHTML = chartRef.current?.innerHTML || '';
    const htmlContent = `
      <!DOCTYPE html>
      <html>
        <head>
          <title>${title || 'Chart'}</title>
          <meta charset="utf-8">
          <style>
            * { margin: 0; padding: 0; box-sizing: border-box; }
            body { 
              margin: 0; 
              padding: 20px; 
              font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', 'Roboto', sans-serif; 
              background: #f5f5f5; 
            }
            .popup-chart-container {
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
          <div class="popup-chart-container">
            <h2>${title || 'Chart'}</h2>
            ${chartHTML}
          </div>
        </body>
      </html>
    `;
    
    // Open as popup window with specific features
    const popup = window.open(
      '',
      'chartPopup',
      `width=1200,height=800,left=${left},top=${top},resizable=yes,scrollbars=yes,toolbar=no,menubar=no,location=no,status=no`
    );
    
    if (popup) {
      popup.document.open();
      popup.document.write(htmlContent);
      popup.document.close();
      popup.focus();
    } else {
      // Fallback if popup blocked - open in new tab
      alert('Popup blocked. Opening in new tab instead.');
      handleOpenNewTab();
    }
  };

  const handleOpenNewTab = () => {
    const chartHTML = chartRef.current?.innerHTML || '';
    const htmlContent = `
      <!DOCTYPE html>
      <html>
        <head>
          <title>${title || 'Chart'}</title>
          <meta charset="utf-8">
          <style>
            * { margin: 0; padding: 0; box-sizing: border-box; }
            body { 
              margin: 0; 
              padding: 20px; 
              font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', 'Roboto', sans-serif; 
              background: #f5f5f5; 
            }
            .tab-chart-container {
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
          <div class="tab-chart-container">
            <h2>${title || 'Chart'}</h2>
            ${chartHTML}
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
    <div className="splunk-chart-wrapper">
      <div className="chart-header">
        {title && <div className="chart-title">{title}</div>}
        <div className="chart-actions">
          <button className="chart-action-button" onClick={handleOpenPopup} title="Open in popup">
            🔲 Popup
          </button>
          <button className="chart-action-button" onClick={handleOpenNewTab} title="Open in new tab">
            📑 New Tab
          </button>
        </div>
      </div>
      
      {/* Chart type selector for time series and charts that allow switching */}
      {(allowChartTypeSwitch || isTimeSeries) && initialType !== 'pie' && (
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
      
      <div ref={containerRef} className="chart-container" style={{ width: '100%', height: `${height}px`, overflow: 'auto' }}>
        <div ref={chartRef}>
          {renderChart()}
        </div>
      </div>
    </div>
  );
};

export default SplunkChart;

