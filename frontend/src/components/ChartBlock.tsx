/** Chart block component with popup support. */
import React, { useState } from 'react';
import { LineChart, Line, XAxis, YAxis, CartesianGrid, Tooltip, ResponsiveContainer } from 'recharts';

interface ChartBlockProps {
  data?: {
    chartId?: string;
    dataset?: Array<{ date: string; value: number }>;
  };
}

const ChartBlock: React.FC<ChartBlockProps> = ({ data }) => {
  const [popupWindow, setPopupWindow] = useState<Window | null>(null);

  if (!data?.dataset) {
    return <div>No chart data available</div>;
  }

  const handleOpenPopup = () => {
    const width = 800;
    const height = 600;
    const left = (window.screen.width - width) / 2;
    const top = (window.screen.height - height) / 2;

    const popup = window.open(
      '',
      'chartPopup',
      `width=${width},height=${height},left=${left},top=${top}`
    );

    if (popup) {
      popup.document.write(`
        <!DOCTYPE html>
        <html>
          <head>
            <title>Chart View</title>
            <script src="https://unpkg.com/recharts@2.10.3/umd/Recharts.js"></script>
            <style>
              body { margin: 0; padding: 20px; font-family: sans-serif; }
            </style>
          </head>
          <body>
            <h2>Chart Data</h2>
            <div id="chart-container"></div>
            <script>
              const data = ${JSON.stringify(data.dataset)};
              // Simplified chart rendering in popup
              document.getElementById('chart-container').innerHTML = 
                '<pre>' + JSON.stringify(data, null, 2) + '</pre>';
            </script>
          </body>
        </html>
      `);
      popup.document.close();
      setPopupWindow(popup);
    }
  };

  return (
    <div className="chart-block">
      <div className="chart-container" style={{ width: '100%', height: '300px' }}>
        <ResponsiveContainer>
          <LineChart data={data.dataset}>
            <CartesianGrid strokeDasharray="3 3" />
            <XAxis dataKey="date" />
            <YAxis />
            <Tooltip />
            <Line type="monotone" dataKey="value" stroke="#8884d8" />
          </LineChart>
        </ResponsiveContainer>
      </div>
      <button onClick={handleOpenPopup} className="chart-popup-btn">
        Open in Popup
      </button>
    </div>
  );
};

export default ChartBlock;


