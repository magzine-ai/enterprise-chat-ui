/**
 * AlertBlock Component
 * 
 * Displays alert/notification messages with different severity levels.
 * Useful for warnings, errors, success messages, and important information.
 * 
 * @example
 * ```tsx
 * <AlertBlock
 *   type="error"
 *   title="Error occurred"
 *   message="Failed to process request"
 *   dismissible={true}
 * />
 * ```
 * 
 * @param type - Alert type: 'info' | 'success' | 'warning' | 'error'
 * @param title - Alert title
 * @param message - Alert message/content
 * @param dismissible - Whether alert can be dismissed (default: false)
 * @param onDismiss - Callback when alert is dismissed
 */
import React, { useState } from 'react';

interface AlertBlockProps {
  type?: 'info' | 'success' | 'warning' | 'error';
  title?: string;
  message: string;
  dismissible?: boolean;
  onDismiss?: () => void;
}

const AlertBlock: React.FC<AlertBlockProps> = ({
  type = 'info',
  title,
  message,
  dismissible = false,
  onDismiss,
}) => {
  const [isDismissed, setIsDismissed] = useState(false);

  const handleDismiss = () => {
    setIsDismissed(true);
    if (onDismiss) {
      onDismiss();
    }
  };

  if (isDismissed) {
    return null;
  }

  const icons = {
    info: 'ℹ️',
    success: '✓',
    warning: '⚠️',
    error: '✗',
  };

  const colors = {
    info: '#0088FE',
    success: '#19c37d',
    warning: '#FFBB28',
    error: '#ef4444',
  };

  return (
    <div className={`alert-block alert-${type}`} style={{ borderLeftColor: colors[type] }}>
      <div className="alert-icon">{icons[type]}</div>
      <div className="alert-content">
        {title && <div className="alert-title">{title}</div>}
        <div className="alert-message">{message}</div>
      </div>
      {dismissible && (
        <button className="alert-dismiss" onClick={handleDismiss} title="Dismiss">
          ×
        </button>
      )}
    </div>
  );
};

export default AlertBlock;


