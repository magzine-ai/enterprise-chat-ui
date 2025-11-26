/** Conversations Redux slice. */
import { createSlice, PayloadAction } from '@reduxjs/toolkit';
import type { Conversation } from '@/types';

interface ConversationsState {
  conversations: Conversation[];
  currentConversationId: number | null;
  loading: boolean;
}

const initialState: ConversationsState = {
  conversations: [],
  currentConversationId: null,
  loading: false,
};

const conversationsSlice = createSlice({
  name: 'conversations',
  initialState,
  reducers: {
    setConversations: (state, action: PayloadAction<Conversation[]>) => {
      // Create a completely new array with new objects to avoid mutation issues
      // Deep copy each conversation to ensure no shared references
      const newConversations = action.payload.map(conv => ({
        id: conv.id,
        title: conv.title,
        created_at: conv.created_at,
        updated_at: conv.updated_at,
      }));
      
      // Return new state object to ensure immutability
      return {
        ...state,
        conversations: newConversations,
      };
    },
    addConversation: (state, action: PayloadAction<Conversation>) => {
      // Create a new conversation object from payload
      const newConversation: Conversation = {
        id: action.payload.id,
        title: action.payload.title,
        created_at: action.payload.created_at,
        updated_at: action.payload.updated_at,
      };
      // Create new objects for all existing conversations and prepend the new one
      const newConversations = [
        newConversation,
        ...state.conversations.map(conv => ({
          id: conv.id,
          title: conv.title,
          created_at: conv.created_at,
          updated_at: conv.updated_at,
        }))
      ];
      
      // Return new state object to ensure immutability
      return {
        ...state,
        conversations: newConversations,
        currentConversationId: action.payload.id,
      };
    },
    setCurrentConversation: (state, action: PayloadAction<number | null>) => {
      // Return new state object to ensure immutability
      // This prevents mutation detection issues
      return {
        ...state,
        currentConversationId: action.payload,
      };
    },
    updateConversation: (
      state,
      action: PayloadAction<{ id: number; title?: string }>
    ) => {
      // Find and update the conversation
      const index = state.conversations.findIndex(
        (c) => c.id === action.payload.id
      );
      if (index !== -1) {
        // Create a new array with the updated conversation
        state.conversations = state.conversations.map((conv, i) => {
          if (i === index) {
            return {
              id: conv.id,
              title: action.payload.title !== undefined ? action.payload.title : conv.title,
              created_at: conv.created_at,
              updated_at: new Date().toISOString(),
            };
          }
          return {
            id: conv.id,
            title: conv.title,
            created_at: conv.created_at,
            updated_at: conv.updated_at,
          };
        });
      }
    },
    deleteConversation: (state, action: PayloadAction<number>) => {
      // Filter out the conversation to delete and create new objects
      const newConversations = state.conversations
        .filter(conv => conv.id !== action.payload)
        .map(conv => ({
          id: conv.id,
          title: conv.title,
          created_at: conv.created_at,
          updated_at: conv.updated_at,
        }));
      
      // Update current conversation ID if the deleted one was selected
      if (state.currentConversationId === action.payload) {
        state.currentConversationId = newConversations.length > 0 ? newConversations[0].id! : null;
      }
      
      state.conversations = newConversations;
    },
    setLoading: (state, action: PayloadAction<boolean>) => {
      state.loading = action.payload;
    },
  },
});

export const {
  setConversations,
  addConversation,
  setCurrentConversation,
  updateConversation,
  deleteConversation,
  setLoading,
} = conversationsSlice.actions;
export default conversationsSlice.reducer;

