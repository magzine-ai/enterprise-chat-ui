/**
 * Redux slice for managing approval requests and state.
 */
import { createSlice, PayloadAction } from '@reduxjs/toolkit';
import type { ApprovalRequest } from '@/components/ApprovalDialog';

interface ApprovalState {
  pendingApprovals: Record<string, ApprovalRequest>; // approval_id -> request
  currentApprovalId: string | null;
}

const initialState: ApprovalState = {
  pendingApprovals: {},
  currentApprovalId: null,
};

const approvalSlice = createSlice({
  name: 'approval',
  initialState,
  reducers: {
    addApprovalRequest: (state, action: PayloadAction<ApprovalRequest>) => {
      const request = action.payload;
      state.pendingApprovals[request.approval_id] = request;
      state.currentApprovalId = request.approval_id;
    },
    removeApprovalRequest: (state, action: PayloadAction<string>) => {
      const approvalId = action.payload;
      delete state.pendingApprovals[approvalId];
      
      // Clear current approval if it was removed
      if (state.currentApprovalId === approvalId) {
        state.currentApprovalId = null;
        // Set to next pending approval if any
        const remainingIds = Object.keys(state.pendingApprovals);
        state.currentApprovalId = remainingIds.length > 0 ? remainingIds[0] : null;
      }
    },
    setCurrentApproval: (state, action: PayloadAction<string | null>) => {
      state.currentApprovalId = action.payload;
    },
    clearAllApprovals: (state) => {
      state.pendingApprovals = {};
      state.currentApprovalId = null;
    },
  },
});

export const {
  addApprovalRequest,
  removeApprovalRequest,
  setCurrentApproval,
  clearAllApprovals,
} = approvalSlice.actions;

export default approvalSlice.reducer;

