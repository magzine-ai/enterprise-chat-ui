/**
 * Dialog Component
 * 
 * Reusable modal dialog component for alerts, confirmations, and prompts.
 * Replaces native browser dialogs (alert, confirm, prompt) with a custom UI.
 * 
 * Features:
 * - Alert: Simple message with OK button
 * - Confirm: Yes/No confirmation dialog
 * - Prompt: Text input dialog
 * - Keyboard support (Escape to close, Enter to confirm)
 * - Portal rendering (renders outside component tree)
 * 
 * @example
 * ```tsx
 * <Dialog
 *   isOpen={isOpen}
 *   onClose={() => setIsOpen(false)}
 *   title="Delete Conversation"
 *   message="Are you sure?"
 *   type="confirm"
 *   onConfirm={handleConfirm}
 * />
 * ```
 */
import React, { useEffect, useRef } from 'react';

interface DialogProps {
  isOpen: boolean;
  onClose: () => void;
  title: string;
  message?: string;
  type?: 'confirm' | 'prompt' | 'alert';
  defaultValue?: string;
  confirmLabel?: string;
  cancelLabel?: string;
  onConfirm?: (value?: string) => void;
  placeholder?: string;
}

const Dialog: React.FC<DialogProps> = ({
  isOpen,
  onClose,
  title,
  message,
  type = 'alert',
  defaultValue = '',
  confirmLabel = 'OK',
  cancelLabel = 'Cancel',
  onConfirm,
  placeholder = '',
}) => {
  const inputRef = useRef<HTMLInputElement>(null);
  const [inputValue, setInputValue] = React.useState(defaultValue);

  useEffect(() => {
    if (isOpen && type === 'prompt' && inputRef.current) {
      inputRef.current.focus();
      inputRef.current.select();
    }
    if (isOpen) {
      setInputValue(defaultValue);
    }
  }, [isOpen, type, defaultValue]);

  useEffect(() => {
    const handleEscape = (e: KeyboardEvent) => {
      if (e.key === 'Escape' && isOpen) {
        onClose();
      }
    };
    if (isOpen) {
      document.addEventListener('keydown', handleEscape);
      document.body.style.overflow = 'hidden';
    }
    return () => {
      document.removeEventListener('keydown', handleEscape);
      document.body.style.overflow = '';
    };
  }, [isOpen, onClose]);

  const handleConfirm = () => {
    if (type === 'prompt') {
      onConfirm?.(inputValue);
    } else {
      onConfirm?.();
    }
  };

  const handleKeyDown = (e: React.KeyboardEvent) => {
    if (e.key === 'Enter' && type === 'prompt') {
      handleConfirm();
    }
  };

  if (!isOpen) return null;

  return (
    <div className="dialog-overlay" onClick={onClose}>
      <div className="dialog-container" onClick={(e) => e.stopPropagation()}>
        <div className="dialog-header">
          <h3 className="dialog-title">{title}</h3>
          <button className="dialog-close" onClick={onClose} title="Close">
            <svg xmlns="http://www.w3.org/2000/svg" width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
              <line x1="18" y1="6" x2="6" y2="18"/>
              <line x1="6" y1="6" x2="18" y2="18"/>
            </svg>
          </button>
        </div>
        
        <div className="dialog-body">
          {message && <p className="dialog-message">{message}</p>}
          {type === 'prompt' && (
            <input
              ref={inputRef}
              type="text"
              className="dialog-input"
              value={inputValue}
              onChange={(e) => setInputValue(e.target.value)}
              onKeyDown={handleKeyDown}
              placeholder={placeholder}
            />
          )}
        </div>

        <div className="dialog-footer">
          {type !== 'alert' && (
            <button className="dialog-button dialog-button-cancel" onClick={onClose}>
              {cancelLabel}
            </button>
          )}
          <button className="dialog-button dialog-button-confirm" onClick={handleConfirm}>
            {confirmLabel}
          </button>
        </div>
      </div>
    </div>
  );
};

export default Dialog;

