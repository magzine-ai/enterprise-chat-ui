/**
 * Popup Utilities
 * 
 * Utility functions for opening content in popup windows or new browser tabs.
 * 
 * Functions:
 * - openInPopup: Opens content in a minimal popup window
 * - openInNewTab: Opens content in a full browser tab
 * - renderComponentToHTML: Renders React component to HTML (placeholder)
 * 
 * @example
 * ```typescript
 * openInPopup('<h1>Hello</h1>', 'Title');
 * openInNewTab('<h1>Hello</h1>', 'Title');
 * ```
 */

/**
 * Opens content in a popup window
 */
export function openInPopup(
  content: string | HTMLElement,
  title: string = 'View',
  width: number = 1200,
  height: number = 800
): Window | null {
  const left = (window.screen.width - width) / 2;
  const top = (window.screen.height - height) / 2;

  const popup = window.open(
    '',
    title,
    `width=${width},height=${height},left=${left},top=${top},resizable=yes,scrollbars=yes`
  );

  if (popup) {
    const htmlContent = typeof content === 'string' 
      ? content 
      : content.outerHTML;

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
            .popup-container {
              background: white;
              border-radius: 8px;
              padding: 20px;
              box-shadow: 0 2px 8px rgba(0,0,0,0.1);
              max-width: 100%;
              overflow: auto;
            }
          </style>
        </head>
        <body>
          <div class="popup-container">
            ${htmlContent}
          </div>
        </body>
      </html>
    `);
    popup.document.close();
  }

  return popup;
}

/**
 * Opens content in a new browser tab
 */
export function openInNewTab(
  content: string | HTMLElement,
  title: string = 'View'
): Window | null {
  const newTab = window.open('', '_blank');
  
  if (newTab) {
    const htmlContent = typeof content === 'string' 
      ? content 
      : content.outerHTML;

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
            .tab-container {
              background: white;
              border-radius: 8px;
              padding: 20px;
              box-shadow: 0 2px 8px rgba(0,0,0,0.1);
              max-width: 100%;
              overflow: auto;
            }
          </style>
        </head>
        <body>
          <div class="tab-container">
            ${htmlContent}
          </div>
        </body>
      </html>
    `);
    newTab.document.close();
  }

  return newTab;
}

/**
 * Renders a React component to HTML string for popup/tab display
 */
export function renderComponentToHTML(element: React.ReactElement): Promise<string> {
  // This is a simplified version - in production, you'd use ReactDOMServer.renderToString
  // For now, we'll use a ref-based approach
  return new Promise((resolve) => {
    const div = document.createElement('div');
    // In a real implementation, you'd render the component here
    resolve(div.innerHTML);
  });
}

