/**
 * PopupWindow Component
 * 
 * Utility component for opening content in popup windows or new tabs.
 * Supports both popup windows and new browser tabs with postMessage communication.
 * 
 * @example
 * ```tsx
 * <PopupWindow
 *   content={<MyComponent />}
 *   title="Chart View"
 *   width={1200}
 *   height={800}
 * />
 * ```
 * 
 * @param content - React component or element to render in popup
 * @param title - Window/tab title
 * @param width - Popup width in pixels (default: 1200)
 * @param height - Popup height in pixels (default: 800)
 * @param mode - 'popup' or 'tab' (default: 'popup')
 */
import React, { useEffect, useRef } from 'react';

interface PopupWindowProps {
  content: React.ReactNode;
  title?: string;
  width?: number;
  height?: number;
  mode?: 'popup' | 'tab';
  onClose?: () => void;
}

const PopupWindow: React.FC<PopupWindowProps> = ({
  content,
  title = 'View',
  width = 1200,
  height = 800,
  mode = 'popup',
  onClose,
}) => {
  const popupRef = useRef<Window | null>(null);
  const contentRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (mode === 'popup') {
      // Calculate center position
      const left = (window.screen.width - width) / 2;
      const top = (window.screen.height - height) / 2;

      // Open popup window
      const popup = window.open(
        '',
        title,
        `width=${width},height=${height},left=${left},top=${top},resizable=yes,scrollbars=yes`
      );

      if (popup) {
        popupRef.current = popup;
        
        // Write HTML content
        popup.document.write(`
          <!DOCTYPE html>
          <html>
            <head>
              <title>${title}</title>
              <style>
                * { margin: 0; padding: 0; box-sizing: border-box; }
                body {
                  font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', 'Roboto', sans-serif;
                  padding: 20px;
                  background: #f5f5f5;
                }
                #popup-content { 
                  background: white;
                  border-radius: 8px;
                  padding: 20px;
                  box-shadow: 0 2px 8px rgba(0,0,0,0.1);
                }
              </style>
            </head>
            <body>
              <div id="popup-content"></div>
              <script>
                // Listen for content updates via postMessage
                window.addEventListener('message', function(event) {
                  if (event.data.type === 'popup-content') {
                    document.getElementById('popup-content').innerHTML = event.data.html;
                  }
                });
              </script>
            </body>
          </html>
        `);
        popup.document.close();

        // Send content via postMessage
        setTimeout(() => {
          if (contentRef.current && popup) {
            const html = contentRef.current.innerHTML;
            popup.postMessage({ type: 'popup-content', html }, '*');
          }
        }, 100);

        // Handle popup close
        const checkClosed = setInterval(() => {
          if (popup.closed) {
            clearInterval(checkClosed);
            if (onClose) onClose();
          }
        }, 100);

        return () => {
          clearInterval(checkClosed);
          if (!popup.closed) {
            popup.close();
          }
        };
      }
    } else {
      // Open in new tab
      const newTab = window.open('', '_blank');
      if (newTab) {
        newTab.document.write(`
          <!DOCTYPE html>
          <html>
            <head>
              <title>${title}</title>
              <style>
                * { margin: 0; padding: 0; box-sizing: border-box; }
                body {
                  font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', 'Roboto', sans-serif;
                  padding: 20px;
                  background: #f5f5f5;
                }
                #tab-content { 
                  background: white;
                  border-radius: 8px;
                  padding: 20px;
                  box-shadow: 0 2px 8px rgba(0,0,0,0.1);
                }
              </style>
            </head>
            <body>
              <div id="tab-content"></div>
            </body>
          </html>
        `);
        newTab.document.close();

        setTimeout(() => {
          if (contentRef.current && newTab) {
            newTab.document.getElementById('tab-content')!.innerHTML = contentRef.current.innerHTML;
          }
        }, 100);
      }
    }
  }, [mode, title, width, height, onClose]);

  return (
    <div ref={contentRef} style={{ display: 'none' }}>
      {content}
    </div>
  );
};

export default PopupWindow;


