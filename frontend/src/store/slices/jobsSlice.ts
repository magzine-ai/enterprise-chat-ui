/** Jobs Redux slice. */
import { createSlice, PayloadAction } from '@reduxjs/toolkit';
import type { Job } from '@/types';

interface JobsState {
  jobs: Record<string, Job>;
}

const initialState: JobsState = {
  jobs: {},
};

const jobsSlice = createSlice({
  name: 'jobs',
  initialState,
  reducers: {
    setJob: (state, action: PayloadAction<Job>) => {
      state.jobs[action.payload.job_id] = action.payload;
    },
    updateJob: (state, action: PayloadAction<Partial<Job> & { job_id: string }>) => {
      const { job_id, ...updates } = action.payload;
      if (state.jobs[job_id]) {
        state.jobs[job_id] = { ...state.jobs[job_id], ...updates };
      }
    },
    removeJob: (state, action: PayloadAction<string>) => {
      delete state.jobs[action.payload];
    },
  },
});

export const { setJob, updateJob, removeJob } = jobsSlice.actions;
export default jobsSlice.reducer;


