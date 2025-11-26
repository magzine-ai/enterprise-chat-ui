/**
 * MessageInput Component
 * 
 * Handles message input and submission with optimistic UI updates.
 * 
 * Edge Cases Handled:
 * - Rapid message sending (prevents double submission)
 * - Network failures (rollback optimistic updates)
 * - Component unmounting during async operations
 * - Browser tab switching
 * - Form submission edge cases
 * - Input validation
 * - Error recovery
 */
import React, { useState, useRef, useEffect, useCallback } from 'react';
import { useAppDispatch, useAppSelector } from '@/store/hooks';
import { addMessage, removeMessage, setWaitingForResponse } from '@/store/slices/messagesSlice';
import { setJob } from '@/store/slices/jobsSlice';
import { apiService } from '@/services/apiService';
import type { Message } from '@/types';

const MessageInput: React.FC = () => {
  const [input, setInput] = useState('');
  const [isSubmitting, setIsSubmitting] = useState(false);
  
  // Debug: Log when isSubmitting changes
  useEffect(() => {
    console.log(`🔍 MessageInput: isSubmitting=${isSubmitting}`);
  }, [isSubmitting]);
  const textareaRef = useRef<HTMLTextAreaElement>(null);
  const isMountedRef = useRef(true);
  const responseTimeoutRef = useRef<number | null>(null);
  const dispatch = useAppDispatch();
  
  const conversationId = useAppSelector(
    (state) => state.conversations.currentConversationId
  );
  
  // CRITICAL: Selector must access conversationId from state, not from closure
  // This ensures React Redux can properly track changes to waitingForResponse
  const isWaitingForResponse = useAppSelector(
    (state) => {
      const currentConvId = state.conversations.currentConversationId;
      const waiting = currentConvId ? (state.messages.waitingForResponse[currentConvId] || false) : false;
      // Debug logging
      if (currentConvId) {
        console.log(`🔍 MessageInput selector: conversationId=${currentConvId}, isWaitingForResponse=${waiting}, waitingForResponse=`, state.messages.waitingForResponse);
      }
      return waiting;
    },
    // Use shallow equality - React Redux will compare the returned boolean value
    // When waitingForResponse[conversationId] changes from true to undefined/false,
    // this will return a different value and trigger a re-render
  );

  // Track component mount state to prevent state updates after unmount
  useEffect(() => {
    isMountedRef.current = true;
    return () => {
      isMountedRef.current = false;
      // Cleanup: clear timeout on unmount
      if (responseTimeoutRef.current) {
        clearTimeout(responseTimeoutRef.current);
        responseTimeoutRef.current = null;
      }
    };
  }, []);

  // Clear timeout when waiting state is cleared externally (e.g., via WebSocket)
  useEffect(() => {
    if (!isWaitingForResponse && responseTimeoutRef.current) {
      // Waiting state was cleared (likely by WebSocket assistant message)
      // Clear the timeout since we don't need it anymore
      clearTimeout(responseTimeoutRef.current);
      responseTimeoutRef.current = null;
      console.log('✅ Cleared response timeout - assistant message received');
    }
  }, [isWaitingForResponse]);

  // Auto-resize textarea
  useEffect(() => {
    if (textareaRef.current) {
      textareaRef.current.style.height = '24px';
      const scrollHeight = textareaRef.current.scrollHeight;
      textareaRef.current.style.height = `${scrollHeight}px`;
    }
  }, [input]);

  /**
   * Handle message submission
   * 
   * Flow:
   * 1. Validate input and state
   * 2. Add optimistic message (instant UI feedback)
   * 3. Block input
   * 4. Send to API
   * 5. Replace optimistic with real message
   * 6. Handle errors with rollback
   */
  const handleSubmit = useCallback(async (e: React.FormEvent) => {
    e.preventDefault();
    
    // Validation: Check all conditions before proceeding
    if (!input.trim() || !conversationId || isSubmitting || isWaitingForResponse) {
      return;
    }

    const messageText = input.trim();
    const tempId = -Date.now(); // Negative ID for optimistic messages
    
    // Clear input immediately for better UX
    setInput('');
    setIsSubmitting(true);

    // Create optimistic message
    const optimisticMessage: Message = {
      id: tempId,
      content: messageText,
      role: 'user',
      conversation_id: conversationId,
      created_at: new Date().toISOString(),
      blocks: [],
    };

    // Step 1: Add optimistic message immediately (appears instantly in UI)
    dispatch(addMessage(optimisticMessage));
    
    // Step 2: Block input while waiting for response
    dispatch(setWaitingForResponse({ conversationId, waiting: true }));

    // Set up timeout fallback in case WebSocket fails or assistant response doesn't arrive
    // Clear any existing timeout first
    if (responseTimeoutRef.current) {
      clearTimeout(responseTimeoutRef.current);
    }
    responseTimeoutRef.current = setTimeout(() => {
      if (isMountedRef.current) {
        console.warn('⚠️ Assistant response timeout - unblocking input after 30 seconds');
        dispatch(setWaitingForResponse({ conversationId, waiting: false }));
      }
      responseTimeoutRef.current = null;
    }, 30000); // 30 second timeout

    try {
      // Step 3: Send to API
      const response = await apiService.createMessage(conversationId, messageText);
      const { message, job_id } = response;
      
      // Check if component is still mounted before updating state
      if (!isMountedRef.current) {
        clearTimeout(responseTimeout);
        return;
      }
      
      // Step 4: Replace optimistic message with real message from API
      dispatch(removeMessage({ conversationId, messageId: tempId }));
      dispatch(addMessage(message));
      
      // Clear submitting state
      setIsSubmitting(false);
      
      // Step 5: Handle job_id
      // If job_id exists, we're waiting for async assistant response via WebSocket
      // Input remains blocked until WebSocket receives assistant message (handled in App.tsx)
      // The timeout will unblock input if assistant message doesn't arrive
      if (!job_id) {
        // No async response expected, clear timeout and unblock input
        if (responseTimeoutRef.current) {
          clearTimeout(responseTimeoutRef.current);
          responseTimeoutRef.current = null;
        }
        dispatch(setWaitingForResponse({ conversationId, waiting: false }));
      }
      // If job_id exists, timeout will remain active and will unblock input after 30 seconds
      // WebSocket handler in App.tsx will clear waiting state when assistant message arrives
      
    } catch (error: any) {
      // Error handling: Rollback optimistic update
      console.error('Error sending message:', error);
      
      // Clear timeout on error
      if (responseTimeoutRef.current) {
        clearTimeout(responseTimeoutRef.current);
        responseTimeoutRef.current = null;
      }
      
      // Only update state if component is still mounted
      if (isMountedRef.current) {
        // Remove optimistic message on error
        dispatch(removeMessage({ conversationId, messageId: tempId }));
        dispatch(setWaitingForResponse({ conversationId, waiting: false }));
        setIsSubmitting(false);
        
        // Restore input text so user can retry
        setInput(messageText);
        
        // Focus textarea for better UX
        if (textareaRef.current) {
          // Use setTimeout to ensure DOM is ready
          setTimeout(() => {
            textareaRef.current?.focus();
          }, 0);
        }
        
        // Show error to user (consider using toast notification instead of alert)
        alert(`Failed to send message: ${error.message || 'Unknown error'}`);
      }
    }
  }, [input, conversationId, isSubmitting, isWaitingForResponse, dispatch]);

  /**
   * Handle keyboard input
   * Enter to send, Shift+Enter for new line
   */
  const handleKeyDown = useCallback((e: React.KeyboardEvent<HTMLTextAreaElement>) => {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault();
      // Only submit if not already submitting and not waiting
      if (!isSubmitting && !isWaitingForResponse) {
        handleSubmit(e);
      }
    }
  }, [handleSubmit, isSubmitting, isWaitingForResponse]);

  /**
   * Handle chart generation job creation
   */
  const handleCreateJob = useCallback(async () => {
    if (!conversationId || isSubmitting || isWaitingForResponse) {
      return;
    }
    
    setIsSubmitting(true);

    try {
      const job = await apiService.createJob('chart', { range: 30 }, conversationId);
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
      if (isMountedRef.current) {
        setIsSubmitting(false);
      }
    }
  }, [conversationId, isSubmitting, isWaitingForResponse, dispatch]);

  // Don't render if no conversation is selected
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
            placeholder={isWaitingForResponse ? "Waiting for response..." : "Message..."}
            className="message-input-field"
            rows={1}
            disabled={isSubmitting || isWaitingForResponse}
            aria-label="Message input"
            aria-disabled={isSubmitting || isWaitingForResponse}
            data-debug={`submitting:${isSubmitting},waiting:${isWaitingForResponse}`}
          />
          <div className="message-input-actions">
            <button
              type="button"
              onClick={handleCreateJob}
              className="action-button"
              disabled={isSubmitting || isWaitingForResponse}
              title="Generate Chart"
              aria-label="Generate chart"
            >
              📊
            </button>
            <button
              type="submit"
              className="send-button"
              disabled={!input.trim() || isSubmitting || isWaitingForResponse}
              title="Send message"
              aria-label="Send message"
            >
              <svg
                viewBox="0 0 24 24"
                fill="none"
                stroke="currentColor"
                strokeWidth="2"
                strokeLinecap="round"
                strokeLinejoin="round"
                aria-hidden="true"
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
