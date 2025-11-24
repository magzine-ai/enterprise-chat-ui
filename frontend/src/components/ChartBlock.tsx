/** Chart block component with popup support. */
import React from 'react';
import {
  Chart as ChartJS,
  CategoryScale,
  LinearScale,
  PointElement,
  LineElement,
  Title,
  Tooltip,
  Legend,
} from 'chart.js';
import { Line } from 'react-chartjs-2';

// Register Chart.js components
ChartJS.register(
  CategoryScale,
  LinearScale,
  PointElement,
  LineElement,
  Title,
  Tooltip,
  Legend
);

interface ChartBlockProps {
  data?: {
    chartId?: string;
    dataset?: Array<{ date: string; value: number }>;
  };
}

const ChartBlock: React.FC<ChartBlockProps> = ({ data }) => {

  if (!data?.dataset) {
    return <div>No chart data available</div>;
  }

  const chartData = {
    labels: data.dataset.map(item => item.date),
    datasets: [{
      label: 'Value',
      data: data.dataset.map(item => item.value),
      borderColor: 'rgba(136, 132, 216, 1)',
      backgroundColor: 'rgba(136, 132, 216, 0.2)',
      tension: 0.4,
    }],
  };

  const chartOptions = {
    responsive: true,
    maintainAspectRatio: false,
    plugins: {
      legend: {
        display: true,
        position: 'top' as const,
      },
      tooltip: {
        mode: 'index' as const,
        intersect: false,
      },
    },
    scales: {
      x: {
        display: true,
        title: {
          display: true,
          text: 'Date',
        },
      },
      y: {
        display: true,
        title: {
          display: true,
          text: 'Value',
        },
        beginAtZero: true,
      },
    },
  };

  const handleOpenPopup = () => {
    const width = 800;
    const height = 600;
    const left = (window.screen.width - width) / 2;
    const top = (window.screen.height - height) / 2;

    const htmlContent = `
      <!DOCTYPE html>
      <html>
        <head>
          <title>Chart View</title>
          <script src="https://cdn.jsdelivr.net/npm/chart.js@4.4.0/dist/chart.umd.min.js"></script>
          <style>
            body { margin: 0; padding: 20px; font-family: sans-serif; }
            canvas { max-width: 100% !important; }
          </style>
        </head>
        <body>
          <h2>Chart Data</h2>
          <canvas id="chartCanvas"></canvas>
          <script>
            const data = ${JSON.stringify(chartData)};
            const ctx = document.getElementById('chartCanvas').getContext('2d');
            new Chart(ctx, {
              type: 'line',
              data: data,
              options: ${JSON.stringify(chartOptions)}
            });
          </script>
        </body>
      </html>
    `;

    const popup = window.open(
      '',
      'chartPopup',
      `width=${width},height=${height},left=${left},top=${top}`
    );

    if (popup) {
      popup.document.write(htmlContent);
      popup.document.close();
    }
  };

  return (
    <div className="chart-block">
      <div className="chart-container" style={{ width: '100%', height: '300px', position: 'relative' }}>
        <Line data={chartData} options={chartOptions} />
      </div>
      <button onClick={handleOpenPopup} className="chart-popup-btn">
        Open in Popup
      </button>
    </div>
  );
};

export default ChartBlock;
