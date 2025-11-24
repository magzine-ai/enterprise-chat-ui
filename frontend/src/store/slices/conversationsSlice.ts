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
      state.conversations = action.payload;
    },
    addConversation: (state, action: PayloadAction<Conversation>) => {
      state.conversations.unshift(action.payload);
      state.currentConversationId = action.payload.id;
    },
    setCurrentConversation: (state, action: PayloadAction<number | null>) => {
      state.currentConversationId = action.payload;
    },
    updateConversation: (
      state,
      action: PayloadAction<{ id: number; title?: string }>
    ) => {
      const index = state.conversations.findIndex(
        (c) => c.id === action.payload.id
      );
      if (index !== -1) {
        if (action.payload.title !== undefined) {
          state.conversations[index].title = action.payload.title;
        }
        state.conversations[index].updated_at = new Date().toISOString();
      }
    },
    deleteConversation: (state, action: PayloadAction<number>) => {
      state.conversations = state.conversations.filter(
        (c) => c.id !== action.payload
      );
      if (state.currentConversationId === action.payload) {
        state.currentConversationId =
          state.conversations.length > 0 ? state.conversations[0].id! : null;
      }
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

