/**
 * SplunkChart Component
 * 
 * Displays data visualizations similar to Splunk's charting capabilities.
 * Supports multiple chart types: line, bar, area, pie, and timechart.
 * Uses Chart.js instead of recharts for enterprise compatibility.
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
 */
import React, { useState, useRef } from 'react';
import {
  Chart as ChartJS,
  CategoryScale,
  LinearScale,
  PointElement,
  LineElement,
  BarElement,
  ArcElement,
  Title,
  Tooltip,
  Legend,
  Filler,
} from 'chart.js';
import { Line, Bar, Pie } from 'react-chartjs-2';

// Register Chart.js components
ChartJS.register(
  CategoryScale,
  LinearScale,
  PointElement,
  LineElement,
  BarElement,
  ArcElement,
  Title,
  Tooltip,
  Legend,
  Filler
);

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

const COLORS = [
  'rgba(25, 195, 125, 1)',   // #19c37d
  'rgba(0, 136, 254, 1)',    // #0088FE
  'rgba(0, 196, 159, 1)',    // #00C49F
  'rgba(255, 187, 40, 1)',   // #FFBB28
  'rgba(255, 128, 66, 1)',   // #FF8042
  'rgba(136, 132, 216, 1)',  // #8884d8
];

const COLORS_TRANSPARENT = [
  'rgba(25, 195, 125, 0.6)',
  'rgba(0, 136, 254, 0.6)',
  'rgba(0, 196, 159, 0.6)',
  'rgba(255, 187, 40, 0.6)',
  'rgba(255, 128, 66, 0.6)',
  'rgba(136, 132, 216, 0.6)',
];

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
  const containerRef = useRef<HTMLDivElement>(null);

  // Use selected type if switching is allowed, otherwise use initial type
  const type = (allowChartTypeSwitch || isTimeSeries) ? selectedChartType : initialType;

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

  // Prepare Chart.js data structure
  const prepareChartData = () => {
    const renderType = (allowChartTypeSwitch || isTimeSeries) && type !== 'pie' 
      ? (selectedChartType === 'column' ? 'bar' : selectedChartType)
      : (type === 'column' ? 'bar' : type);

    // For pie charts, different data structure
    if (renderType === 'pie') {
      return {
        labels: data.map((item) => item[xAxisKey] || item.name || String(item[yAxis || 'value'])),
        datasets: [{
          label: yAxis || 'value',
          data: data.map((item) => item[yAxis || 'value'] || 0),
          backgroundColor: COLORS_TRANSPARENT.slice(0, data.length),
          borderColor: COLORS.slice(0, data.length),
          borderWidth: 2,
        }],
      };
    }

    // For other chart types
    // For time series, ensure we use the formatted time field
    const labels = data.map((item) => {
      if (isTimeSeries && item['time']) {
        return String(item['time']);  // Use formatted time field
      }
      return String(item[xAxisKey] || item.name || '');
    });

    const datasets = dataKeys.map((key, idx) => {
      const isArea = renderType === 'area';
      return {
        label: key,
        data: data.map((item) => item[key] || 0),
        borderColor: COLORS[idx % COLORS.length],
        backgroundColor: isArea 
          ? COLORS_TRANSPARENT[idx % COLORS.length]
          : COLORS[idx % COLORS.length],
        fill: isArea,
        tension: 0.4, // Smooth curves
        borderWidth: 2,
      };
    });

    return { labels, datasets };
  };

  const chartData = prepareChartData();

  const chartOptions = {
    responsive: true,
    maintainAspectRatio: false,
    plugins: {
      legend: {
        display: showLegend && type !== 'pie',
        position: 'top' as const,
      },
      title: {
        display: !!title,
        text: title,
      },
      tooltip: {
        mode: 'index' as const,
        intersect: false,
      },
    },
    scales: type !== 'pie' ? {
      x: {
        type: isTimeSeries ? 'category' : 'linear',  // Use category for time series to show labels as-is
        display: true,
        title: {
          display: true,
          text: xAxisKey,
        },
        ticks: isTimeSeries ? {
          maxRotation: 45,
          minRotation: 0,
        } : undefined,
      },
      y: {
        display: true,
        title: {
          display: true,
          text: yAxis || 'Value',
        },
        beginAtZero: true,
      },
    } : undefined,
  };

  const renderChart = () => {
    const renderType = (allowChartTypeSwitch || isTimeSeries) && type !== 'pie' 
      ? (selectedChartType === 'column' ? 'bar' : selectedChartType)
      : (type === 'column' ? 'bar' : type);

    const chartProps = {
      data: chartData,
      options: {
        ...chartOptions,
        indexAxis: (renderType === 'bar' && selectedChartType === 'column') ? 'y' as const : undefined,
      },
    };

    switch (renderType) {
      case 'line':
      case 'timechart':
        return <Line {...chartProps} />;
      case 'bar':
        return <Bar {...chartProps} />;
      case 'area':
        return <Line {...chartProps} data={{
          ...chartData,
          datasets: chartData.datasets.map(ds => ({ ...ds, fill: true })),
        }} />;
      case 'pie':
        return <Pie {...chartProps} />;
      default:
        return <div>Unsupported chart type: {type}</div>;
    }
  };

  const handleOpenPopup = () => {
    const left = Math.round((window.screen.width - 1200) / 2);
    const top = Math.round((window.screen.height - 800) / 2);
    
    const htmlContent = `
      <!DOCTYPE html>
      <html>
        <head>
          <title>${title || 'Chart'}</title>
          <meta charset="utf-8">
          <script src="https://cdn.jsdelivr.net/npm/chart.js@4.4.0/dist/chart.umd.min.js"></script>
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
            canvas { max-width: 100% !important; }
          </style>
        </head>
        <body>
          <div class="popup-chart-container">
            <h2>${title || 'Chart'}</h2>
            <canvas id="chartCanvas"></canvas>
            <script>
              const data = ${JSON.stringify(chartData)};
              const ctx = document.getElementById('chartCanvas').getContext('2d');
              new Chart(ctx, {
                type: '${type === 'pie' ? 'pie' : type === 'area' ? 'line' : type}',
                data: data,
                options: ${JSON.stringify(chartOptions)}
              });
            </script>
          </div>
        </body>
      </html>
    `;
    
    const popup = window.open(
      '',
      'chartPopup',
      `width=1200,height=800,left=${left},top=${top},resizable=yes,scrollbars=yes`
    );
    
    if (popup) {
      popup.document.open();
      popup.document.write(htmlContent);
      popup.document.close();
      popup.focus();
    }
  };

  const handleOpenNewTab = () => {
    const htmlContent = `
      <!DOCTYPE html>
      <html>
        <head>
          <title>${title || 'Chart'}</title>
          <meta charset="utf-8">
          <script src="https://cdn.jsdelivr.net/npm/chart.js@4.4.0/dist/chart.umd.min.js"></script>
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
            canvas { max-width: 100% !important; }
          </style>
        </head>
        <body>
          <div class="tab-chart-container">
            <h2>${title || 'Chart'}</h2>
            <canvas id="chartCanvas"></canvas>
            <script>
              const data = ${JSON.stringify(chartData)};
              const ctx = document.getElementById('chartCanvas').getContext('2d');
              new Chart(ctx, {
                type: '${type === 'pie' ? 'pie' : type === 'area' ? 'line' : type}',
                data: data,
                options: ${JSON.stringify(chartOptions)}
              });
            </script>
          </div>
        </body>
      </html>
    `;
    
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
      
      <div 
        ref={containerRef} 
        className="chart-container" 
        style={{ width: '100%', height: `${height}px`, position: 'relative' }}
      >
        {renderChart()}
      </div>
    </div>
  );
};

export default SplunkChart;
