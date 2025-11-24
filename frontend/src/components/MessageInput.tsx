/**
 * MessageInput Component
 * 
 * Input field for sending messages in the chat interface.
 * 
 * Features:
 * - Multi-line text input with auto-resize
 * - Send button (Enter to send, Shift+Enter for new line)
 * - Loading state during message submission
 * - Handles message creation and job requests
 * - Integrates with mock API service
 * 
 * State:
 * - Local state for input value and submission status
 * - Reads current conversation ID from Redux
 * - Dispatches Redux actions for new messages
 * 
 * @example
 * ```tsx
 * <MessageInput />
 * ```
 */
import React, { useState, useRef, useEffect } from 'react';
import { useAppDispatch, useAppSelector } from '@/store/hooks';
import { addMessage } from '@/store/slices/messagesSlice';
import { setJob } from '@/store/slices/jobsSlice';
import { mockApiService as apiService } from '@/services/mockApi';

const MessageInput: React.FC = () => {
  const [input, setInput] = useState('');
  const [isSubmitting, setIsSubmitting] = useState(false);
  const textareaRef = useRef<HTMLTextAreaElement>(null);
  const dispatch = useAppDispatch();
  const conversationId = useAppSelector(
    (state) => state.conversations.currentConversationId
  );

  // Auto-resize textarea
  useEffect(() => {
    if (textareaRef.current) {
      textareaRef.current.style.height = '24px';
      textareaRef.current.style.height = `${textareaRef.current.scrollHeight}px`;
    }
  }, [input]);

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!input.trim() || !conversationId || isSubmitting) return;

    const messageText = input.trim();
    setInput('');
    setIsSubmitting(true);

    try {
      const message = await apiService.createMessage(conversationId, messageText);
      // Don't dispatch user message here - it's already in the mock store
      // The assistant response will come via WebSocket/mock events
      // dispatch(addMessage(message)); // Commented out to prevent duplicates
    } catch (error: any) {
      console.error('Error sending message:', error);
      alert(`Failed to send message: ${error.message || 'Unknown error'}`);
      setInput(messageText); // Restore input on error
    } finally {
      setIsSubmitting(false);
      if (textareaRef.current) {
        textareaRef.current.focus();
      }
    }
  };

  const handleKeyDown = (e: React.KeyboardEvent<HTMLTextAreaElement>) => {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault();
      handleSubmit(e);
    }
  };

  const handleCreateJob = async () => {
    if (!conversationId || isSubmitting) return;
    setIsSubmitting(true);

    try {
      const job = await apiService.createJob('chart', { range: 30 }, conversationId);
      // Add job to store immediately
      dispatch(setJob(job));
      
      const placeholderMessage = await apiService.createMessage(
        conversationId,
        'Generating chart data...',
        'assistant',
        [{ type: 'async-placeholder', data: { jobId: job.job_id } }]
      );
      dispatch(addMessage(placeholderMessage));
    } catch (error: any) {
      console.error('Error creating job:', error);
      alert(`Failed to create job: ${error.message || 'Unknown error'}`);
    } finally {
      setIsSubmitting(false);
    }
  };

  if (!conversationId) {
    return null;
  }

  return (
    <div className="message-input-container">
      <div className="message-input-wrapper">
        <form onSubmit={handleSubmit} className="message-input-form">
          <textarea
            ref={textareaRef}
            value={input}
            onChange={(e) => setInput(e.target.value)}
            onKeyDown={handleKeyDown}
            placeholder="Message..."
            className="message-input-field"
            rows={1}
            disabled={isSubmitting}
          />
          <div className="message-input-actions">
            <button
              type="button"
              onClick={handleCreateJob}
              className="action-button"
              disabled={isSubmitting}
              title="Generate Chart"
            >
              📊
            </button>
            <button
              type="submit"
              className="send-button"
              disabled={!input.trim() || isSubmitting}
              title="Send message"
            >
              <svg
                viewBox="0 0 24 24"
                fill="none"
                stroke="currentColor"
                strokeWidth="2"
                strokeLinecap="round"
                strokeLinejoin="round"
              >
                <line x1="22" y1="2" x2="11" y2="13"></line>
                <polygon points="22 2 15 22 11 13 2 9 22 2"></polygon>
              </svg>
            </button>
          </div>
        </form>
      </div>
    </div>
  );
};

export default MessageInput;
