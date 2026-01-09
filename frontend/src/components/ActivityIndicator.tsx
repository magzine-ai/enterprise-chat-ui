/**
 * ActivityIndicator Component
 * 
 * Displays real-time activity status during conversation processing.
 * Shows which agent is invoked, RAG calls, and response building steps.
 * 
 * Location: Above message input area
 * Auto-hides when assistant message arrives
 */
import React from 'react';
import { useAppSelector } from '@/store/hooks';
import './ActivityIndicator.css';

interface ActivityIndicatorProps {
  conversationId: number | null;
}

const ActivityIndicator: React.FC<ActivityIndicatorProps> = ({ conversationId }) => {
  const activity = useAppSelector((state) => {
    if (!conversationId) {
      return null;
    }
    return state.activity.currentActivity[conversationId] || null;
  });

  // Don't render if no activity
  if (!activity) {
    return null;
  }

  // Extract activity details for display
  const { activity: activityText, details } = activity;
  const agent = details.agent;
  const step = details.step;

  // Build display text with icons/indicators
  let displayText = activityText;
  
  // Add step indicators for better UX
  if (step) {
    const stepIcons: Record<string, string> = {
      'intent_classification': '🔍',
      'opensearch_retrieval': '📚',
      'query_generation': '⚙️',
      'query_execution': '▶️',
      'llm_generation': '🤖',
      'block_extraction': '📦',
      'code_rag_search': '🔎',
      'exhaustive_search_detection': '🎯',
    };
    
    const icon = stepIcons[step] || '⚡';
    displayText = `${icon} ${activityText}`;
  }

  return (
    <div className="activity-indicator">
      <div className="activity-indicator-content">
        <div className="activity-spinner">
          <div className="spinner-dot"></div>
          <div className="spinner-dot"></div>
          <div className="spinner-dot"></div>
        </div>
        <span className="activity-text">{displayText}</span>
      </div>
    </div>
  );
};

export default ActivityIndicator;

