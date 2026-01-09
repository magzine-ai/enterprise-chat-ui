/**
 * Activity Redux Slice
 * 
 * Manages real-time activity status for conversations.
 * Tracks what's currently happening during conversation processing:
 * - Agent selection
 * - RAG calls
 * - Query generation
 * - Response building
 * 
 * Edge Cases Handled:
 * - Multiple rapid activity updates
 * - Conversation switching
 * - Activity clearing when message arrives
 */
import { createSlice, PayloadAction } from '@reduxjs/toolkit';

interface ActivityInfo {
  activity: string;
  details: Record<string, any>;
  timestamp: number;
}

interface ActivityState {
  // Map conversation ID to current activity
  currentActivity: Record<number, ActivityInfo>;
}

const initialState: ActivityState = {
  currentActivity: {},
};

const activitySlice = createSlice({
  name: 'activity',
  initialState,
  reducers: {
    /**
     * Set current activity for a conversation
     */
    setActivity: (
      state,
      action: PayloadAction<{
        conversationId: number;
        activity: string;
        details: Record<string, any>;
      }>
    ) => {
      const { conversationId, activity, details } = action.payload;
      
      // Create new activity info
      const activityInfo: ActivityInfo = {
        activity,
        details,
        timestamp: Date.now(),
      };
      
      // Create new state object to ensure immutability
      const newCurrentActivity: Record<number, ActivityInfo> = {
        ...state.currentActivity,
        [conversationId]: activityInfo,
      };
      
      return {
        ...state,
        currentActivity: newCurrentActivity,
      };
    },
    
    /**
     * Clear activity for a conversation
     * Called when assistant message arrives or conversation completes
     */
    clearActivity: (state, action: PayloadAction<number>) => {
      const conversationId = action.payload;
      
      // Create new state without this conversation's activity
      const newCurrentActivity: Record<number, ActivityInfo> = {};
      for (const [id, activity] of Object.entries(state.currentActivity)) {
        const convId = Number(id);
        if (convId !== conversationId) {
          newCurrentActivity[convId] = activity;
        }
      }
      
      return {
        ...state,
        currentActivity: newCurrentActivity,
      };
    },
  },
});

export const { setActivity, clearActivity } = activitySlice.actions;
export default activitySlice.reducer;

