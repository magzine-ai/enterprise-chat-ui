/** Messages Redux slice - stores messages per conversation. */
import { createSlice, PayloadAction } from '@reduxjs/toolkit';
import type { Message } from '@/types';

interface MessagesState {
  messagesByConversation: Record<number, Message[]>;
}

const initialState: MessagesState = {
  messagesByConversation: {},
};

const messagesSlice = createSlice({
  name: 'messages',
  initialState,
  reducers: {
    setMessages: (
      state,
      action: PayloadAction<{ conversationId: number; messages: Message[] }>
    ) => {
      state.messagesByConversation[action.payload.conversationId] =
        action.payload.messages;
    },
    addMessage: (state, action: PayloadAction<Message>) => {
      const convId = action.payload.conversation_id;
      if (!state.messagesByConversation[convId]) {
        state.messagesByConversation[convId] = [];
      }
      // Check if message already exists to prevent duplicates
      const existingIndex = state.messagesByConversation[convId].findIndex(
        (msg) => msg.id === action.payload.id
      );
      if (existingIndex === -1) {
        // Sanitize message to remove non-serializable values (functions, etc.)
        const sanitizedMessage = {
          ...action.payload,
          blocks: action.payload.blocks?.map((block) => {
            if (block.type === 'form-viewer' && block.data?.actions) {
              // Remove onClick functions from actions
              return {
                ...block,
                data: {
                  ...block.data,
                  actions: block.data.actions.map((action: any) => {
                    const { onClick, ...sanitizedAction } = action;
                    return sanitizedAction;
                  }),
                },
              };
            }
            return block;
          }),
        };
        state.messagesByConversation[convId].push(sanitizedMessage);
      }
    },
    clearMessages: (state, action: PayloadAction<number>) => {
      delete state.messagesByConversation[action.payload];
    },
  },
});

export const { setMessages, addMessage, clearMessages } = messagesSlice.actions;
export default messagesSlice.reducer;
