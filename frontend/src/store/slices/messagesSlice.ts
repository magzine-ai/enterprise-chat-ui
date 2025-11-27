/**
 * Messages Redux Slice
 * 
 * Manages messages state for all conversations.
 * 
 * Key Principles:
 * - Complete immutability - never mutate state directly
 * - Optimistic updates for instant UI feedback
 * - Duplicate prevention
 * - Proper cleanup of optimistic messages
 * 
 * Edge Cases Handled:
 * - Multiple rapid messages
 * - Network failures
 * - Duplicate WebSocket messages
 * - Conversation switching during message send
 * - State mutations
 */
import { createSlice, PayloadAction } from '@reduxjs/toolkit';
import type { Message, Block } from '@/types';

interface MessagesState {
  // Messages organized by conversation ID
  messagesByConversation: Record<number, Message[]>;
  // Track if waiting for assistant response per conversation
  waitingForResponse: Record<number, boolean>;
  // Track streaming messages (conversationId -> messageId)
  streamingMessages: Record<number, number | null>;
}

const initialState: MessagesState = {
  messagesByConversation: {},
  waitingForResponse: {},
  streamingMessages: {},
};

/**
 * Creates a deep clone of a message to prevent reference sharing
 */
function cloneMessage(msg: Message): Message {
  return {
    id: msg.id,
    content: msg.content,
    role: msg.role,
    conversation_id: msg.conversation_id,
    created_at: msg.created_at,
    blocks: msg.blocks ? msg.blocks.map(block => {
      try {
        // Deep clone using JSON serialization
        return JSON.parse(JSON.stringify(block));
      } catch {
        // Fallback to shallow copy if JSON fails
        return { ...block };
      }
    }) : [],
  };
}

const messagesSlice = createSlice({
  name: 'messages',
  initialState,
  reducers: {
    /**
     * Set all messages for a conversation (from API fetch)
     * Preserves optimistic messages that haven't been replaced yet
     */
    setMessages: (
      state,
      action: PayloadAction<{ conversationId: number; messages: Message[] }>
    ) => {
      const { conversationId, messages } = action.payload;
      
      // Get existing optimistic messages (negative IDs)
      const existingOptimistic = (state.messagesByConversation[conversationId] || [])
        .filter(msg => msg.id < 0);
      
      // Clone all server messages to prevent reference sharing
      const serverMessages = messages.map(cloneMessage);
      
      // Create completely new messagesByConversation object
      // Copy all existing conversations except the one we're updating
      const newMessagesByConversation: Record<number, Message[]> = {};
      
      // Copy all existing conversations
      for (const [id, msgs] of Object.entries(state.messagesByConversation)) {
        const convId = Number(id);
        if (convId !== conversationId) {
          // Copy existing conversation arrays
          newMessagesByConversation[convId] = msgs;
        }
      }
      
      // Set the updated conversation with merged messages
      newMessagesByConversation[conversationId] = [
        ...existingOptimistic,
        ...serverMessages
      ];
      
      // Return new state object to ensure immutability
      // Explicitly preserve waitingForResponse to prevent it from being lost
      return {
        ...state,
        messagesByConversation: newMessagesByConversation,
        waitingForResponse: { ...state.waitingForResponse },
      };
    },
    
    /**
     * Add a single message to a conversation
     * 
     * Edge Cases Handled:
     * - Prevents duplicates by checking message ID
     * - Removes optimistic messages when real message arrives
     * - Creates new array references to prevent mutations
     */
    addMessage: (state, action: PayloadAction<Message>) => {
      const convId = action.payload.conversation_id;
      const messageId = action.payload.id;
      
      // Get current messages - create a copy immediately to avoid reference issues
      const currentMessages = state.messagesByConversation[convId] || [];
      
      // Check for duplicates - prevent adding same message twice
      const exists = currentMessages.some(msg => msg.id === messageId);
      if (exists) {
        return; // Message already exists, skip
      }
      
      // Clone the new message to prevent reference sharing
      const newMessage = cloneMessage(action.payload);
      
      // Determine which messages to keep - always create new arrays
      let messagesToKeep: Message[];
      
      if (messageId > 0) {
        // Real message (positive ID) - remove all optimistic messages
        // Filter creates a new array automatically
        messagesToKeep = currentMessages.filter(msg => msg.id > 0);
      } else {
        // Optimistic message (negative ID) - keep all existing messages
        // Create new array copy to prevent mutation
        messagesToKeep = currentMessages.map(msg => cloneMessage(msg));
      }
      
      // Create completely new messagesByConversation object
      // Copy all existing conversations except the one we're updating
      const newMessagesByConversation: Record<number, Message[]> = {};
      
      // Copy all existing conversations
      for (const [id, msgs] of Object.entries(state.messagesByConversation)) {
        const existingConvId = Number(id);
        if (existingConvId !== convId) {
          // Copy existing conversation arrays
          newMessagesByConversation[existingConvId] = msgs;
        }
      }
      
      // Set the updated conversation with new message
      newMessagesByConversation[convId] = [...messagesToKeep, newMessage];
      
      // Return new state object to ensure immutability
      return {
        ...state,
        messagesByConversation: newMessagesByConversation,
      };
    },
    
    /**
     * Remove a specific message by ID
     * Used for cleaning up optimistic messages on error
     */
    removeMessage: (state, action: PayloadAction<{ conversationId: number; messageId: number }>) => {
      const { conversationId, messageId } = action.payload;
      const messages = state.messagesByConversation[conversationId];
      
      if (!messages) {
        // No messages for this conversation, nothing to remove
        return state;
      }
      
      // Create new array without the removed message
      const filteredMessages = messages.filter((msg) => msg.id !== messageId);
      
      // Create completely new messagesByConversation object
      const newMessagesByConversation: Record<number, Message[]> = {};
      
      // Copy all existing conversations
      for (const [id, msgs] of Object.entries(state.messagesByConversation)) {
        const convId = Number(id);
        if (convId !== conversationId) {
          newMessagesByConversation[convId] = msgs;
        }
      }
      
      // Set the updated conversation with filtered messages
      newMessagesByConversation[conversationId] = filteredMessages;
      
      // Return new state object to ensure immutability
      return {
        ...state,
        messagesByConversation: newMessagesByConversation,
      };
    },
    
    /**
     * Clear all messages for a conversation
     * Used when conversation is deleted
     */
    clearMessages: (state, action: PayloadAction<number>) => {
      const conversationId = action.payload;
      
      // Create new messagesByConversation object without this conversation
      const newMessagesByConversation: Record<number, Message[]> = {};
      for (const [id, msgs] of Object.entries(state.messagesByConversation)) {
        const convId = Number(id);
        if (convId !== conversationId) {
          newMessagesByConversation[convId] = msgs;
        }
      }
      
      // Create new waitingForResponse object without this conversation
      const newWaitingForResponse: Record<number, boolean> = {};
      for (const [id, value] of Object.entries(state.waitingForResponse)) {
        const convId = Number(id);
        if (convId !== conversationId) {
          newWaitingForResponse[convId] = value;
        }
      }
      
      // Return new state object to ensure immutability
      return {
        ...state,
        messagesByConversation: newMessagesByConversation,
        waitingForResponse: newWaitingForResponse,
      };
    },
    
    /**
     * Set waiting for response state
     * Blocks input while waiting for assistant response
     */
    setWaitingForResponse: (state, action: PayloadAction<{ conversationId: number; waiting: boolean }>) => {
      const { conversationId, waiting } = action.payload;
      
      console.log(`🔧 setWaitingForResponse: conversationId=${conversationId}, waiting=${waiting}`);
      console.log(`🔧 Current waitingForResponse state:`, state.waitingForResponse);
      
      // Create new object to ensure immutability
      const newWaitingForResponse: Record<number, boolean> = {};
      
      // Copy all existing waiting states
      for (const [id, value] of Object.entries(state.waitingForResponse)) {
        const convId = Number(id);
        if (convId !== conversationId) {
          newWaitingForResponse[convId] = value;
        }
      }
      
      // Set the new waiting state if waiting is true
      if (waiting) {
        newWaitingForResponse[conversationId] = true;
      }
      // If waiting is false, we don't add it, effectively removing it
      
      console.log(`🔧 New waitingForResponse state:`, newWaitingForResponse);
      
      // Return new state object to ensure immutability
      return {
        ...state,
        waitingForResponse: newWaitingForResponse,
      };
    },
    
    /**
     * Start streaming a message
     * Initializes a placeholder message that will be updated as tokens arrive
     */
    startStreamingMessage: (
      state,
      action: PayloadAction<{ conversationId: number; messageId: number }>
    ) => {
      const { conversationId, messageId } = action.payload;
      
      // Create placeholder message for streaming
      const streamingMessage: Message = {
        id: messageId,
        content: '',
        role: 'assistant',
        conversation_id: conversationId,
        created_at: new Date().toISOString(),
        blocks: [],
      };
      
      // Add the placeholder message
      const currentMessages = state.messagesByConversation[conversationId] || [];
      const exists = currentMessages.some(msg => msg.id === messageId);
      
      if (!exists) {
        // Create new messagesByConversation with streaming message
        const newMessagesByConversation: Record<number, Message[]> = {};
        for (const [id, msgs] of Object.entries(state.messagesByConversation)) {
          const convId = Number(id);
          if (convId !== conversationId) {
            newMessagesByConversation[convId] = msgs;
          }
        }
        newMessagesByConversation[conversationId] = [...currentMessages, streamingMessage];
        
        // Track streaming message
        const newStreamingMessages: Record<number, number | null> = { ...state.streamingMessages };
        newStreamingMessages[conversationId] = messageId;
        
        return {
          ...state,
          messagesByConversation: newMessagesByConversation,
          streamingMessages: newStreamingMessages,
        };
      }
      
      return state;
    },
    
    /**
     * Append a token to a streaming message
     * Updates the content of the message being streamed
     */
    appendStreamToken: (
      state,
      action: PayloadAction<{ conversationId: number; messageId: number; token: string }>
    ) => {
      const { conversationId, messageId, token } = action.payload;
      
      const messages = state.messagesByConversation[conversationId];
      if (!messages) {
        return state;
      }
      
      // Find and update the streaming message
      const updatedMessages = messages.map(msg => {
        if (msg.id === messageId) {
          return {
            ...msg,
            content: msg.content + token,
          };
        }
        return msg;
      });
      
      // Create new messagesByConversation with updated message
      const newMessagesByConversation: Record<number, Message[]> = {};
      for (const [id, msgs] of Object.entries(state.messagesByConversation)) {
        const convId = Number(id);
        if (convId !== conversationId) {
          newMessagesByConversation[convId] = msgs;
        }
      }
      newMessagesByConversation[conversationId] = updatedMessages;
      
      return {
        ...state,
        messagesByConversation: newMessagesByConversation,
      };
    },
    
    /**
     * Append a chunk to a streaming message
     * More efficient for batching multiple tokens
     */
    appendStreamChunk: (
      state,
      action: PayloadAction<{ conversationId: number; messageId: number; chunk: string }>
    ) => {
      const { conversationId, messageId, chunk } = action.payload;
      
      const messages = state.messagesByConversation[conversationId];
      if (!messages) {
        return state;
      }
      
      // Find and update the streaming message
      const updatedMessages = messages.map(msg => {
        if (msg.id === messageId) {
          return {
            ...msg,
            content: msg.content + chunk,
          };
        }
        return msg;
      });
      
      // Create new messagesByConversation with updated message
      const newMessagesByConversation: Record<number, Message[]> = {};
      for (const [id, msgs] of Object.entries(state.messagesByConversation)) {
        const convId = Number(id);
        if (convId !== conversationId) {
          newMessagesByConversation[convId] = msgs;
        }
      }
      newMessagesByConversation[conversationId] = updatedMessages;
      
      return {
        ...state,
        messagesByConversation: newMessagesByConversation,
      };
    },
    
    /**
     * Complete streaming message
     * Finalizes the message with blocks and marks streaming as complete
     */
    completeStreamingMessage: (
      state,
      action: PayloadAction<{ conversationId: number; messageId: number; blocks?: Block[] }>
    ) => {
      const { conversationId, messageId, blocks } = action.payload;
      
      const messages = state.messagesByConversation[conversationId];
      if (!messages) {
        return state;
      }
      
      // Update message with blocks
      const updatedMessages = messages.map(msg => {
        if (msg.id === messageId) {
          return {
            ...msg,
            blocks: blocks || [],
          };
        }
        return msg;
      });
      
      // Create new messagesByConversation with updated message
      const newMessagesByConversation: Record<number, Message[]> = {};
      for (const [id, msgs] of Object.entries(state.messagesByConversation)) {
        const convId = Number(id);
        if (convId !== conversationId) {
          newMessagesByConversation[convId] = msgs;
        }
      }
      newMessagesByConversation[conversationId] = updatedMessages;
      
      // Clear streaming message tracking
      const newStreamingMessages: Record<number, number | null> = { ...state.streamingMessages };
      if (newStreamingMessages[conversationId] === messageId) {
        delete newStreamingMessages[conversationId];
      }
      
      return {
        ...state,
        messagesByConversation: newMessagesByConversation,
        streamingMessages: newStreamingMessages,
      };
    },
  },
});

export const { 
  setMessages, 
  addMessage, 
  removeMessage, 
  clearMessages, 
  setWaitingForResponse,
  startStreamingMessage,
  appendStreamToken,
  appendStreamChunk,
  completeStreamingMessage
} = messagesSlice.actions;

export default messagesSlice.reducer;
