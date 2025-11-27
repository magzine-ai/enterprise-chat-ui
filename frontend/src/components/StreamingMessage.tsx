/**
 * StreamingMessage Component
 * 
 * Displays a message that is being streamed in real-time.
 * Shows content as tokens arrive and displays a typing indicator
 * while streaming is in progress.
 * 
 * Features:
 * - Real-time token display as they arrive
 * - Typing indicator while streaming
 * - Smooth animation for token appearance
 * - Block rendering after streaming completes
 * 
 * @example
 * ```tsx
 * <StreamingMessage
 *   message={streamingMessage}
 *   isStreaming={true}
 * />
 * ```
 */

import React, { useEffect, useRef } from 'react';
import BlockRenderer from './BlockRenderer';
import type { Message } from '@/types';

interface StreamingMessageProps {
  /**
   * The message being streamed
   * Content will be updated as tokens arrive
   */
  message: Message;
  
  /**
   * Whether the message is currently being streamed
   * When false, shows final message with blocks
   */
  isStreaming: boolean;
}

const StreamingMessage: React.FC<StreamingMessageProps> = ({ message, isStreaming }) => {
  /**
   * Reference to the message content element for auto-scrolling
   * Automatically scrolls to show new content as it arrives
   */
  const contentRef = useRef<HTMLDivElement>(null);
  
  /**
   * Reference to track if we should auto-scroll
   * Prevents scrolling if user has scrolled up to read previous messages
   */
  const shouldScrollRef = useRef(true);
  
  /**
   * Effect to auto-scroll as new content arrives during streaming
   * Only scrolls if user hasn't manually scrolled up
   */
  useEffect(() => {
    if (isStreaming && contentRef.current && shouldScrollRef.current) {
      // Check if user is near bottom of scroll container
      const container = contentRef.current.closest('.message-list');
      if (container) {
        const isNearBottom = 
          container.scrollHeight - container.scrollTop - container.clientHeight < 100;
        
        if (isNearBottom) {
          contentRef.current.scrollIntoView({ behavior: 'smooth', block: 'end' });
        }
      }
    }
  }, [message.content, isStreaming]);
  
  /**
   * Handle scroll events to detect if user manually scrolled
   * If user scrolls up, disable auto-scroll
   */
  useEffect(() => {
    const container = contentRef.current?.closest('.message-list');
    if (!container) return;
    
    const handleScroll = () => {
      const isNearBottom = 
        container.scrollHeight - container.scrollTop - container.clientHeight < 100;
      shouldScrollRef.current = isNearBottom;
    };
    
    container.addEventListener('scroll', handleScroll);
    return () => container.removeEventListener('scroll', handleScroll);
  }, []);
  
  return (
    <div className="message-container">
      <div className="message message-assistant">
        <div className="message-avatar">AI</div>
        <div className="message-content-wrapper">
          <div className="message-content" ref={contentRef}>
            {/* Display message content as it streams */}
            {message.content && (
              <div className="message-text streaming-text">
                {message.content}
                {/* Show blinking cursor while streaming */}
                {isStreaming && (
                  <span className="streaming-cursor">▊</span>
                )}
              </div>
            )}
            
            {/* Show typing indicator if no content yet */}
            {!message.content && isStreaming && (
              <div className="loading-dots">
                <div className="loading-dot"></div>
                <div className="loading-dot"></div>
                <div className="loading-dot"></div>
              </div>
            )}
            
            {/* Render blocks after streaming completes or if blocks are available */}
            {!isStreaming && message.blocks && message.blocks.length > 0 && (
              <div className="message-blocks">
                {message.blocks.map((block, idx) => (
                  <BlockRenderer key={`${message.id}-block-${idx}`} block={block} />
                ))}
              </div>
            )}
            
            {/* Show blocks that arrive during streaming (if supported) */}
            {isStreaming && message.blocks && message.blocks.length > 0 && (
              <div className="message-blocks">
                {message.blocks.map((block, idx) => (
                  <BlockRenderer key={`${message.id}-block-${idx}`} block={block} />
                ))}
              </div>
            )}
          </div>
        </div>
      </div>
    </div>
  );
};

export default StreamingMessage;

