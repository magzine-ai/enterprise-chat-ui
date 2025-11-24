/**
 * TimelineViewer Component
 * 
 * Displays events or data points on a timeline visualization.
 * Useful for showing logs, events, or time-series data in chronological order.
 * Supports opening in popup or new tab for better viewing.
 * 
 * @example
 * ```tsx
 * <TimelineViewer
 *   events={[
 *     { time: '10:00', title: 'Event 1', description: 'Description', type: 'info' },
 *     { time: '11:00', title: 'Event 2', description: 'Description', type: 'error' },
 *   ]}
 *   title="Event Timeline"
 * />
 * ```
 * 
 * @param events - Array of event objects with time, title, description, type
 * @param title - Optional title for the timeline
 * @param showTime - Whether to show time labels (default: true)
 * @param orientation - 'vertical' or 'horizontal' (default: 'vertical')
 */
import React, { useState, useRef } from 'react';

interface TimelineEvent {
  time: string;
  title: string;
  description?: string;
  type?: 'info' | 'success' | 'warning' | 'error';
  metadata?: Record<string, any>;
}

interface TimelineViewerProps {
  events: TimelineEvent[];
  title?: string;
  showTime?: boolean;
  orientation?: 'vertical' | 'horizontal';
}

const TimelineViewer: React.FC<TimelineViewerProps> = ({
  events,
  title,
  showTime = true,
  orientation = 'vertical',
}) => {
  const [selectedEvent, setSelectedEvent] = useState<number | null>(null);
  const timelineRef = useRef<HTMLDivElement>(null);

  const handleOpenPopup = () => {
    const left = Math.round((window.screen.width - 1200) / 2);
    const top = Math.round((window.screen.height - 800) / 2);
    const timelineHTML = timelineRef.current?.innerHTML || '';
    const htmlContent = `
      <!DOCTYPE html>
      <html>
        <head>
          <title>${title || 'Timeline'}</title>
          <meta charset="utf-8">
          <style>
            * { margin: 0; padding: 0; box-sizing: border-box; }
            body { 
              margin: 0; 
              padding: 20px; 
              font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', 'Roboto', sans-serif; 
              background: #f5f5f5; 
            }
            .popup-timeline-container {
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
          <div class="popup-timeline-container">
            <h2>${title || 'Timeline'}</h2>
            ${timelineHTML}
          </div>
        </body>
      </html>
    `;
    
    const popup = window.open(
      '',
      'timelinePopup',
      `width=1200,height=800,left=${left},top=${top},resizable=yes,scrollbars=yes,toolbar=no,menubar=no,location=no,status=no`
    );
    
    if (popup) {
      popup.document.open();
      popup.document.write(htmlContent);
      popup.document.close();
      popup.focus();
    }
  };

  const handleOpenNewTab = () => {
    const timelineHTML = timelineRef.current?.innerHTML || '';
    const htmlContent = `
      <!DOCTYPE html>
      <html>
        <head>
          <title>${title || 'Timeline'}</title>
          <meta charset="utf-8">
          <style>
            * { margin: 0; padding: 0; box-sizing: border-box; }
            body { 
              margin: 0; 
              padding: 20px; 
              font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', 'Roboto', sans-serif; 
              background: #f5f5f5; 
            }
            .tab-timeline-container {
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
          <div class="tab-timeline-container">
            <h2>${title || 'Timeline'}</h2>
            ${timelineHTML}
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

  const getEventIcon = (type?: string) => {
    switch (type) {
      case 'success':
        return '✓';
      case 'warning':
        return '⚠';
      case 'error':
        return '✗';
      default:
        return '●';
    }
  };

  const getEventColor = (type?: string) => {
    switch (type) {
      case 'success':
        return '#19c37d';
      case 'warning':
        return '#FFBB28';
      case 'error':
        return '#ef4444';
      default:
        return '#0088FE';
    }
  };

  if (!events || events.length === 0) {
    return <div className="timeline-empty">No events to display</div>;
  }

  return (
    <div ref={timelineRef} className={`timeline-viewer timeline-${orientation}`}>
      <div className="timeline-header">
        {title && <div className="timeline-title">{title}</div>}
        <div className="timeline-actions">
          <button className="timeline-action-button" onClick={handleOpenPopup} title="Open in popup">
            🔲
          </button>
          <button className="timeline-action-button" onClick={handleOpenNewTab} title="Open in new tab">
            📑
          </button>
        </div>
      </div>
      <div className="timeline-container">
        {events.map((event, index) => (
          <div
            key={index}
            className={`timeline-event ${selectedEvent === index ? 'selected' : ''}`}
            onClick={() => setSelectedEvent(selectedEvent === index ? null : index)}
          >
            <div className="timeline-marker" style={{ color: getEventColor(event.type) }}>
              {getEventIcon(event.type)}
            </div>
            <div className="timeline-content">
              {showTime && <div className="timeline-time">{event.time}</div>}
              <div className="timeline-event-title">{event.title}</div>
              {event.description && (
                <div className="timeline-event-description">{event.description}</div>
              )}
              {selectedEvent === index && event.metadata && (
                <div className="timeline-event-metadata">
                  <pre>{JSON.stringify(event.metadata, null, 2)}</pre>
                </div>
              )}
            </div>
          </div>
        ))}
      </div>
    </div>
  );
};

export default TimelineViewer;

