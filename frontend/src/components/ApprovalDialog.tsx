/**
 * ApprovalDialog Component
 * 
 * Displays human-in-the-loop approval requests from agent workflows.
 * Supports review, confirmation, and feedback approval types.
 */
import React, { useState, useEffect } from 'react';
import BlockRenderer from './BlockRenderer';
import './ApprovalDialog.css';

export interface ApprovalRequest {
  approval_id: string;
  conversation_id: number;
  approval_type: 'review' | 'confirmation' | 'feedback';
  title: string;
  content: string;
  blocks?: any[];
  options?: {
    require_feedback?: boolean;
    can_reject?: boolean;
  };
  timeout?: number;
}

interface ApprovalDialogProps {
  request: ApprovalRequest;
  onApprove: (approvalId: string, approved: boolean, feedback?: string) => void;
  onClose: () => void;
}

const ApprovalDialog: React.FC<ApprovalDialogProps> = ({ request, onApprove, onClose }) => {
  const [feedback, setFeedback] = useState('');
  const [timeRemaining, setTimeRemaining] = useState<number | null>(null);
  const [isSubmitting, setIsSubmitting] = useState(false);

  useEffect(() => {
    // Start countdown timer if timeout is specified
    if (request.timeout) {
      setTimeRemaining(request.timeout);
      
      const interval = setInterval(() => {
        setTimeRemaining((prev) => {
          if (prev === null || prev <= 1) {
            clearInterval(interval);
            // Auto-reject on timeout
            if (prev !== null && prev <= 1) {
              onApprove(request.approval_id, false, 'Approval request timed out');
            }
            return 0;
          }
          return prev - 1;
        });
      }, 1000);

      return () => clearInterval(interval);
    }
  }, [request.timeout, request.approval_id, onApprove]);

  const handleApprove = async () => {
    setIsSubmitting(true);
    try {
      await onApprove(request.approval_id, true, feedback || undefined);
    } finally {
      setIsSubmitting(false);
    }
  };

  const handleReject = async () => {
    if (!request.options?.can_reject) return;
    
    setIsSubmitting(true);
    try {
      await onApprove(request.approval_id, false, feedback || undefined);
    } finally {
      setIsSubmitting(false);
    }
  };

  const formatTimeRemaining = (seconds: number): string => {
    const mins = Math.floor(seconds / 60);
    const secs = seconds % 60;
    return `${mins}:${secs.toString().padStart(2, '0')}`;
  };

  const getApprovalTypeIcon = () => {
    switch (request.approval_type) {
      case 'review':
        return '👁️';
      case 'confirmation':
        return '✓';
      case 'feedback':
        return '💬';
      default:
        return '❓';
    }
  };

  const getApprovalTypeLabel = () => {
    switch (request.approval_type) {
      case 'review':
        return 'Review Required';
      case 'confirmation':
        return 'Confirmation Required';
      case 'feedback':
        return 'Feedback Required';
      default:
        return 'Approval Required';
    }
  };

  return (
    <div className="approval-dialog-overlay" onClick={onClose}>
      <div className="approval-dialog" onClick={(e) => e.stopPropagation()}>
        <div className="approval-dialog-header">
          <div className="approval-dialog-title">
            <span className="approval-type-icon">{getApprovalTypeIcon()}</span>
            <div>
              <h3>{request.title || getApprovalTypeLabel()}</h3>
              <span className="approval-type-label">{getApprovalTypeLabel()}</span>
            </div>
          </div>
          {timeRemaining !== null && (
            <div className="approval-timer">
              ⏱️ {formatTimeRemaining(timeRemaining)}
            </div>
          )}
          <button className="approval-dialog-close" onClick={onClose} aria-label="Close">
            ×
          </button>
        </div>

        <div className="approval-dialog-content">
          {request.content && (
            <div className="approval-content-text">
              <p>{request.content}</p>
            </div>
          )}

          {request.blocks && request.blocks.length > 0 && (
            <div className="approval-content-blocks">
              <h4>Additional Information:</h4>
              {request.blocks.map((block, index) => (
                <div key={index} className="approval-block">
                  <BlockRenderer block={block} />
                </div>
              ))}
            </div>
          )}

          {(request.options?.require_feedback || request.approval_type === 'feedback') && (
            <div className="approval-feedback-section">
              <label htmlFor="approval-feedback">
                {request.approval_type === 'feedback' ? 'Your Feedback:' : 'Optional Feedback:'}
              </label>
              <textarea
                id="approval-feedback"
                className="approval-feedback-input"
                value={feedback}
                onChange={(e) => setFeedback(e.target.value)}
                placeholder={
                  request.approval_type === 'feedback'
                    ? 'Please provide your feedback...'
                    : 'Add any comments or feedback (optional)...'
                }
                rows={4}
                required={request.approval_type === 'feedback'}
              />
            </div>
          )}
        </div>

        <div className="approval-dialog-actions">
          {request.options?.can_reject !== false && (
            <button
              className="approval-button rejection-button"
              onClick={handleReject}
              disabled={isSubmitting}
            >
              Reject
            </button>
          )}
          <button
            className="approval-button approval-button-primary"
            onClick={handleApprove}
            disabled={
              isSubmitting ||
              (request.options?.require_feedback && !feedback.trim()) ||
              (request.approval_type === 'feedback' && !feedback.trim())
            }
          >
            {isSubmitting ? 'Processing...' : 'Approve'}
          </button>
        </div>
      </div>
    </div>
  );
};

export default ApprovalDialog;

