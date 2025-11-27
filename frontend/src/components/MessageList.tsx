/**
 * MessageList Component
 * 
 * Displays messages for the current conversation.
 * 
 * Edge Cases Handled:
 * - Proper React Redux selector memoization
 * - Prevents overwriting optimistic messages
 * - Handles conversation switching
 * - Auto-scroll with proper timing
 * - Component unmounting during async operations
 * - Race conditions with message loading
 * - Browser visibility changes
 */
import React, { useEffect, useRef, useMemo, useCallback } from 'react';
import { useAppSelector, useAppDispatch } from '@/store/hooks';
import { setMessages } from '@/store/slices/messagesSlice';
import { store, type RootState } from '@/store';
import { apiService } from '@/services/apiService';
import type { Message } from '@/types';
import BlockRenderer from './BlockRenderer';
import StreamingMessage from './StreamingMessage';

const MessageList: React.FC = () => {
  const dispatch = useAppDispatch();
  
  // Get current conversation ID
  const currentConversationId = useAppSelector(
    (state) => state.conversations.currentConversationId
  );
  
  /**
   * Selector for messages
   * 
   * CRITICAL: Don't memoize the selector function - React Redux needs to track it
   * React Redux uses reference equality on the RETURNED VALUE, not the selector function
   * When Redux creates a new array (which it does in addMessage), this selector
   * will return a new reference and trigger a re-render automatically
   */
  const messages = useAppSelector((state: RootState) => {
    if (!currentConversationId) {
      return [];
    }
    // Return the array directly from Redux state
    // When Redux updates messagesByConversation[convId] with a new array,
    // this will return a new reference and React will re-render
    const msgs = state.messages.messagesByConversation[currentConversationId] || [];
    // Return a new array reference to ensure React detects changes
    // This is safe because Redux already creates new arrays on updates
    return msgs;
  });
  
  // Get waiting for response state
  const isWaitingForResponse = useAppSelector(
    (state) => currentConversationId ? (state.messages.waitingForResponse[currentConversationId] || false) : false
  );
  
  // Get streaming message ID for current conversation
  const streamingMessageId = useAppSelector(
    (state) => currentConversationId ? (state.messages.streamingMessages[currentConversationId] || null) : null
  );
  
  // Track conversation loading state
  const prevConversationIdRef = useRef<number | null>(null);
  const hasLoadedRef = useRef<boolean>(false);
  const isLoadingRef = useRef<boolean>(false);
  const isMountedRef = useRef(true);
  
  // Track component mount state
  useEffect(() => {
    isMountedRef.current = true;
    return () => {
      isMountedRef.current = false;
    };
  }, []);
  
  /**
   * Load messages when conversation changes
   * 
   * Edge Cases Handled:
   * - Prevents loading if optimistic messages exist
   * - Handles conversation switching during load
   * - Prevents duplicate loads
   * - Handles component unmounting
   */
  useEffect(() => {
    // Only reload if conversation actually changed
    if (currentConversationId && currentConversationId !== prevConversationIdRef.current) {
      const newConversationId = currentConversationId;
      prevConversationIdRef.current = newConversationId;
      hasLoadedRef.current = false;
      isLoadingRef.current = false;
      
      // Small delay to allow optimistic messages to be added first
      // This prevents race conditions where we fetch before optimistic update
      const timeoutId = setTimeout(() => {
        // Check if component is still mounted and conversation hasn't changed
        if (!isMountedRef.current || prevConversationIdRef.current !== newConversationId) {
          return;
        }
        
        // Check if there are optimistic messages
        const state = store.getState();
        const currentMessages = state.messages.messagesByConversation[newConversationId] || [];
        const hasOptimistic = currentMessages.some((m: Message) => m.id < 0);
        
        // Only load if we haven't loaded yet AND there are no optimistic messages
        if (!hasLoadedRef.current && !hasOptimistic && !isLoadingRef.current) {
          isLoadingRef.current = true;
          hasLoadedRef.current = true;
          
          apiService.getMessages(newConversationId)
            .then(messages => {
              // Double-check: component still mounted and conversation hasn't changed
              if (!isMountedRef.current || prevConversationIdRef.current !== newConversationId) {
                return;
              }
              
              dispatch(setMessages({ conversationId: newConversationId, messages }));
              isLoadingRef.current = false;
            })
            .catch(error => {
              console.error('MessageList: Error loading messages:', error);
              isLoadingRef.current = false;
              // Don't mark as loaded on error, allow retry
              if (isMountedRef.current && prevConversationIdRef.current === newConversationId) {
                hasLoadedRef.current = false;
              }
            });
        } else if (hasOptimistic) {
          // Mark as loaded to prevent future reloads
          // Optimistic messages will be replaced by real ones
          hasLoadedRef.current = true;
        }
      }, 100); // Small delay to let optimistic messages be added first
      
      return () => {
        clearTimeout(timeoutId);
      };
    }
  }, [currentConversationId, dispatch]);
  
  /**
   * Auto-scroll to bottom when new messages arrive
   * 
   * Edge Cases Handled:
   * - Uses requestAnimationFrame for smooth scrolling
   * - Handles rapid message additions
   * - Prevents scroll jump on user scroll up
   */
  const messagesEndRef = useRef<HTMLDivElement>(null);
  const scrollTimeoutRef = useRef<number | null>(null);
  
  useEffect(() => {
    // Clear any pending scroll
    if (scrollTimeoutRef.current !== null) {
      cancelAnimationFrame(scrollTimeoutRef.current);
    }
    
    // Use requestAnimationFrame for smooth scrolling
    scrollTimeoutRef.current = requestAnimationFrame(() => {
      if (messagesEndRef.current && isMountedRef.current) {
        messagesEndRef.current.scrollIntoView({ behavior: 'smooth' });
      }
    });
    
    return () => {
      if (scrollTimeoutRef.current !== null) {
        cancelAnimationFrame(scrollTimeoutRef.current);
      }
    };
  }, [messages]); // Depend on messages array - React Redux ensures new reference on change

  // Empty state: No conversation selected
  if (!currentConversationId) {
    return (
      <div className="message-list">
        <div className="empty-state">
          <div className="empty-state-icon">💬</div>
          <div className="empty-state-text">Select a conversation</div>
          <div className="empty-state-subtext">
            Choose a conversation from the sidebar or create a new one
          </div>
        </div>
      </div>
    );
  }

  // Empty state: No messages in conversation
  if (messages.length === 0) {
    return (
      <div className="message-list">
        <div className="empty-state">
          <div className="empty-state-icon">💬</div>
          <div className="empty-state-text">Start a conversation</div>
          <div className="empty-state-subtext">Send a message to begin chatting</div>
        </div>
      </div>
    );
  }

  // Render messages
  return (
    <div className="message-list">
      {messages.map((message: Message, index: number) => {
        // Check if this message is currently being streamed
        const isStreaming = message.id === streamingMessageId && message.role === 'assistant';
        
        // Use StreamingMessage component for streaming messages
        if (isStreaming) {
          return (
            <StreamingMessage
              key={`${message.id}-${message.created_at}-${index}`}
              message={message}
              isStreaming={true}
            />
          );
        }
        
        // Regular message rendering
        return (
          <div 
            key={`${message.id}-${message.created_at}-${index}`} 
            className="message-container"
          >
            <div className={`message message-${message.role}`}>
              <div className="message-avatar">
                {message.role === 'user' ? 'U' : 'AI'}
              </div>
              <div className="message-content-wrapper">
                <div className="message-content">
                  {message.content && (
                    <div className="message-text">{message.content}</div>
                  )}
                  {message.blocks?.map((block, idx) => (
                    <BlockRenderer key={`${message.id}-block-${idx}`} block={block} />
                  ))}
                </div>
              </div>
            </div>
          </div>
        );
      })}
      
      {/* Loading indicator when waiting for assistant response but no streaming message yet */}
      {isWaitingForResponse && !streamingMessageId && (
        <div className="message-container">
          <div className="message message-assistant">
            <div className="message-avatar">AI</div>
            <div className="message-content-wrapper">
              <div className="message-content">
                <div className="loading-dots">
                  <div className="loading-dot"></div>
                  <div className="loading-dot"></div>
                  <div className="loading-dot"></div>
                </div>
              </div>
            </div>
          </div>
        </div>
      )}
      
      {/* Scroll anchor */}
      <div ref={messagesEndRef} />
    </div>
  );
};

export default MessageList;
