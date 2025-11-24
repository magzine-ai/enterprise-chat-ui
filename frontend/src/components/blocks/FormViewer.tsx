/**
 * FormViewer Component
 * 
 * Displays structured form data, particularly useful for ServiceNow change requests,
 * tickets, and other enterprise form data. Supports grouping, sections, and field types.
 * 
 * @example
 * ```tsx
 * <FormViewer
 *   title="Change Request CR12345"
 *   fields={[
 *     { label: 'Number', value: 'CR12345', type: 'text' },
 *     { label: 'State', value: 'In Progress', type: 'badge', badgeType: 'info' },
 *     { label: 'Priority', value: 'High', type: 'badge', badgeType: 'warning' },
 *   ]}
 *   sections={[
 *     { title: 'Details', fields: ['Number', 'State', 'Priority'] },
 *     { title: 'Description', fields: ['Description'] },
 *   ]}
 * />
 * ```
 * 
 * @param title - Form title (e.g., Change Request number)
 * @param fields - Array of field definitions
 * @param sections - Optional sections to group fields
 * @param metadata - Additional metadata (created date, updated date, etc.)
 * @param actions - Optional action buttons
 */
import React, { useState, useRef } from 'react';

export interface FormField {
  name: string;
  label: string;
  value: any;
  type?: 'text' | 'badge' | 'link' | 'date' | 'number' | 'boolean' | 'multiline' | 'json';
  badgeType?: 'info' | 'success' | 'warning' | 'error';
  link?: string;
  icon?: string;
  tooltip?: string;
}

export interface FormSection {
  title: string;
  fields: string[]; // Field names to include in this section
  collapsed?: boolean;
}

interface FormViewerProps {
  title?: string;
  fields: FormField[];
  sections?: FormSection[];
  metadata?: {
    created?: string;
    updated?: string;
    createdBy?: string;
    updatedBy?: string;
  };
  actions?: Array<{
    label: string;
    actionId?: string;
    onClick?: () => void;
    variant?: 'primary' | 'secondary' | 'danger';
  }>;
}

const FormViewer: React.FC<FormViewerProps> = ({
  title,
  fields,
  sections,
  metadata,
  actions,
}) => {
  const [collapsedSections, setCollapsedSections] = useState<Record<string, boolean>>({});
  const formRef = useRef<HTMLDivElement>(null);

  const toggleSection = (sectionTitle: string) => {
    setCollapsedSections((prev) => ({
      ...prev,
      [sectionTitle]: !prev[sectionTitle],
    }));
  };

  const getFieldByName = (name: string): FormField | undefined => {
    return fields.find((f) => f.name === name);
  };

  const renderFieldValue = (field: FormField) => {
    switch (field.type) {
      case 'badge':
        const badgeColors = {
          info: '#0088FE',
          success: '#19c37d',
          warning: '#FFBB28',
          error: '#ef4444',
        };
        return (
          <span
            className="form-badge"
            style={{
              backgroundColor: badgeColors[field.badgeType || 'info'],
              color: 'white',
            }}
          >
            {field.value}
          </span>
        );

      case 'link':
        return (
          <a
            href={field.link || '#'}
            target="_blank"
            rel="noopener noreferrer"
            className="form-link"
          >
            {field.value} {field.link && '↗'}
          </a>
        );

      case 'date':
        return (
          <span className="form-date">
            {new Date(field.value).toLocaleString()}
          </span>
        );

      case 'boolean':
        return (
          <span className={`form-boolean ${field.value ? 'true' : 'false'}`}>
            {field.value ? '✓ Yes' : '✗ No'}
          </span>
        );

      case 'number':
        return <span className="form-number">{field.value?.toLocaleString()}</span>;

      case 'multiline':
        return (
          <div className="form-multiline">
            {String(field.value).split('\n').map((line, idx) => (
              <div key={idx}>{line}</div>
            ))}
          </div>
        );

      case 'json':
        return (
          <pre className="form-json">
            {JSON.stringify(field.value, null, 2)}
          </pre>
        );

      default:
        return <span className="form-text">{String(field.value || '-')}</span>;
    }
  };

  const renderFields = (fieldNames: string[]) => {
    return fieldNames.map((fieldName) => {
      const field = getFieldByName(fieldName);
      if (!field) return null;

      return (
        <div key={field.name} className="form-field-row">
          <div className="form-field-label">
            {field.icon && <span className="form-field-icon">{field.icon}</span>}
            {field.label}
            {field.tooltip && (
              <span className="form-field-tooltip" title={field.tooltip}>
                ℹ️
              </span>
            )}
            :
          </div>
          <div className="form-field-value">{renderFieldValue(field)}</div>
        </div>
      );
    });
  };

  const handleOpenPopup = () => {
    const left = Math.round((window.screen.width - 1200) / 2);
    const top = Math.round((window.screen.height - 800) / 2);
    const formHTML = formRef.current?.innerHTML || '';
    const htmlContent = `
      <!DOCTYPE html>
      <html>
        <head>
          <title>${title || 'Form View'}</title>
          <meta charset="utf-8">
          <style>
            * { margin: 0; padding: 0; box-sizing: border-box; }
            body { 
              margin: 0; 
              padding: 20px; 
              font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', 'Roboto', sans-serif; 
              background: #f5f5f5; 
            }
            .popup-form-container {
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
          <div class="popup-form-container">
            <h2>${title || 'Form View'}</h2>
            ${formHTML}
          </div>
        </body>
      </html>
    `;
    
    const popup = window.open(
      '',
      'formPopup',
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
    const formHTML = formRef.current?.innerHTML || '';
    const htmlContent = `
      <!DOCTYPE html>
      <html>
        <head>
          <title>${title || 'Form View'}</title>
          <meta charset="utf-8">
          <style>
            * { margin: 0; padding: 0; box-sizing: border-box; }
            body { 
              margin: 0; 
              padding: 20px; 
              font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', 'Roboto', sans-serif; 
              background: #f5f5f5; 
            }
            .tab-form-container {
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
          <div class="tab-form-container">
            <h2>${title || 'Form View'}</h2>
            ${formHTML}
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

  // If sections provided, use them; otherwise render all fields
  const fieldsToRender = sections
    ? sections.flatMap((section) => section.fields)
    : fields.map((f) => f.name);

  return (
    <div ref={formRef} className="form-viewer-wrapper">
      <div className="form-viewer-header">
        <div className="form-viewer-title-section">
          {title && <div className="form-viewer-title">{title}</div>}
          {metadata && (
            <div className="form-viewer-metadata">
              {metadata.created && (
                <span>Created: {new Date(metadata.created).toLocaleDateString()}</span>
              )}
              {metadata.updated && (
                <span>Updated: {new Date(metadata.updated).toLocaleDateString()}</span>
              )}
            </div>
          )}
        </div>
        <div className="form-viewer-actions">
          {actions?.map((action, idx) => {
            const handleAction = () => {
              if (action.onClick) {
                action.onClick();
              } else if (action.actionId) {
                // Handle action by ID - can be extended to dispatch Redux actions or API calls
                console.log(`Action clicked: ${action.actionId}`, { title, action });
                // TODO: Integrate with Redux or API service for actual action handling
                // Example: dispatch(handleFormAction({ formId: title, actionId: action.actionId }));
              }
            };
            
            return (
              <button
                key={idx}
                className={`form-action-button form-action-${action.variant || 'secondary'}`}
                onClick={handleAction}
              >
                {action.label}
              </button>
            );
          })}
          <button className="form-action-button" onClick={handleOpenPopup} title="Open in popup">
            🔲
          </button>
          <button className="form-action-button" onClick={handleOpenNewTab} title="Open in new tab">
            📑
          </button>
        </div>
      </div>

      <div className="form-viewer-content">
        {sections ? (
          sections.map((section, sectionIdx) => {
            const isCollapsed = collapsedSections[section.title] ?? section.collapsed ?? false;
            return (
              <div key={sectionIdx} className="form-section">
                <button
                  className="form-section-header"
                  onClick={() => toggleSection(section.title)}
                >
                  <span className="form-section-icon">{isCollapsed ? '▶' : '▼'}</span>
                  <span className="form-section-title">{section.title}</span>
                </button>
                {!isCollapsed && (
                  <div className="form-section-content">
                    {renderFields(section.fields)}
                  </div>
                )}
              </div>
            );
          })
        ) : (
          <div className="form-fields">
            {renderFields(fieldsToRender)}
          </div>
        )}
      </div>
    </div>
  );
};

export default FormViewer;

