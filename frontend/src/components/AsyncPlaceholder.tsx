/** Async placeholder component with modern loading UI. */
import React, { useEffect } from 'react';
import { useAppSelector, useAppDispatch } from '@/store/hooks';
import { updateJob } from '@/store/slices/jobsSlice';
import BlockRenderer from './BlockRenderer';
import type { Block } from '@/types';

interface AsyncPlaceholderProps {
  jobId?: string;
}

const AsyncPlaceholder: React.FC<AsyncPlaceholderProps> = ({ jobId }) => {
  const dispatch = useAppDispatch();
  const job = useAppSelector((state) => (jobId ? state.jobs.jobs[jobId] : null));

  useEffect(() => {
    if (jobId && !job) {
      // Fetch job status - typically handled by WebSocket updates
    }
  }, [jobId, job]);

  if (!job) {
    return (
      <div className="async-placeholder">
        <div className="loading-dots">
          <div className="loading-dot"></div>
          <div className="loading-dot"></div>
          <div className="loading-dot"></div>
        </div>
      </div>
    );
  }

  if (job.status === 'completed' && job.result?.blocks) {
    // Render final blocks
    return (
      <div className="async-completed">
        {job.result.blocks.map((block: Block, idx: number) => (
          <BlockRenderer key={idx} block={block} />
        ))}
      </div>
    );
  }

  if (job.status === 'failed') {
    return (
      <div className="async-error">
        ❌ Job failed: {job.error || 'Unknown error'}
      </div>
    );
  }

  return (
    <div className="async-placeholder">
      <div className="progress-bar">
        <div
          className="progress-fill"
          style={{ width: `${job.progress}%` }}
        />
      </div>
      <div className="progress-text">
        {job.status === 'queued' && 'Queued...'}
        {job.status === 'started' && 'Starting...'}
        {job.status === 'progress' && `Processing... ${job.progress}%`}
      </div>
    </div>
  );
};

export default AsyncPlaceholder;
