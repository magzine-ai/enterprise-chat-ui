/**
 * MessageList Component
 * 
 * Displays messages for the current conversation in a chat-like interface.
 * 
 * Features:
 * - Auto-scrolls to bottom on new messages
 * - Renders user and assistant messages with different styling
 * - Uses BlockRenderer to render message content blocks
 * - Handles empty state (no messages)
 * 
 * State:
 * - Reads messages from Redux store (messagesSlice)
 * - Reads current conversation from Redux store (conversationsSlice)
 * 
 * @example
 * ```tsx
 * <MessageList />
 * ```
 */
import React, { useEffect, useRef, useMemo } from 'react';
import { useAppSelector } from '@/store/hooks';
import type { Message } from '@/types';
import BlockRenderer from './BlockRenderer';

const MessageList: React.FC = () => {
  const currentConversationId = useAppSelector(
    (state) => state.conversations.currentConversationId
  );
  
  // Get messagesByConversation object (stable reference)
  const messagesByConversation = useAppSelector(
    (state) => state.messages.messagesByConversation
  );
  
  // Memoize messages array to prevent unnecessary rerenders
  const messages = useMemo(() => {
    if (!currentConversationId) return [];
    return messagesByConversation[currentConversationId] || [];
  }, [currentConversationId, messagesByConversation]);
  const messagesEndRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    // Auto-scroll to bottom when new messages arrive
    messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' });
  }, [messages]);

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

  return (
    <div className="message-list">
      {messages.map((message: Message, index: number) => (
        <div key={`${message.id}-${message.created_at}-${index}`} className="message-container">
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
                  <BlockRenderer key={idx} block={block} />
                ))}
              </div>
            </div>
          </div>
        </div>
      ))}
      <div ref={messagesEndRef} />
    </div>
  );
};

export default MessageList;
