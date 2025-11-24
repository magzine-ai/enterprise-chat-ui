/** Redux store configuration. */
/**
 * Redux Store Configuration
 * 
 * Configures the Redux store with all slice reducers.
 * Uses Redux Toolkit for simplified store setup.
 * 
 * Store Structure:
 * - conversations: Conversation list and current conversation
 * - messages: Messages organized by conversation ID
 * - jobs: Async job states
 * 
 * The store is configured with Redux DevTools support for debugging.
 */
import { configureStore } from '@reduxjs/toolkit';
import messagesReducer from './slices/messagesSlice';
import jobsReducer from './slices/jobsSlice';
import conversationsReducer from './slices/conversationsSlice';

export const store = configureStore({
  reducer: {
    messages: messagesReducer,
    jobs: jobsReducer,
    conversations: conversationsReducer,
  },
});

export type RootState = ReturnType<typeof store.getState>;
export type AppDispatch = typeof store.dispatch;
