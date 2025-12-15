/**
 * Thinking Mode Toggle Component
 * 
 * Allows users to switch between "thinking" and "deep_thinking" modes
 * for code analysis. Mode persists per conversation.
 */
import React, { useState, useEffect } from 'react';
import { apiService } from '@/services/api';
import './ThinkingModeToggle.css';

interface ThinkingModeToggleProps {
  conversationId: number | null;
  currentMode?: string;
  onModeChange?: (mode: string) => void;
}

const ThinkingModeToggle: React.FC<ThinkingModeToggleProps> = ({
  conversationId,
  currentMode = 'thinking',
  onModeChange,
}) => {
  const [mode, setMode] = useState<string>(currentMode);
  const [isUpdating, setIsUpdating] = useState(false);

  useEffect(() => {
    setMode(currentMode);
  }, [currentMode]);

  const handleModeChange = async (newMode: string) => {
    if (!conversationId || newMode === mode || isUpdating) {
      return;
    }

    setIsUpdating(true);
    try {
      await apiService.updateThinkingMode(conversationId, newMode);
      setMode(newMode);
      if (onModeChange) {
        onModeChange(newMode);
      }
    } catch (error) {
      console.error('Failed to update thinking mode:', error);
    } finally {
      setIsUpdating(false);
    }
  };

  if (!conversationId) {
    return null;
  }

  return (
    <div className="thinking-mode-toggle">
      <div className="thinking-mode-label">Thinking Mode:</div>
      <div className="thinking-mode-buttons">
        <button
          className={`thinking-mode-btn ${mode === 'thinking' ? 'active' : ''}`}
          onClick={() => handleModeChange('thinking')}
          disabled={isUpdating}
          title="Fast, intelligent analysis (default)"
        >
          <span className="mode-icon">⚡</span>
          <span className="mode-text">Thinking</span>
        </button>
        <button
          className={`thinking-mode-btn ${mode === 'deep_thinking' ? 'active' : ''}`}
          onClick={() => handleModeChange('deep_thinking')}
          disabled={isUpdating}
          title="Exhaustive, comprehensive analysis"
        >
          <span className="mode-icon">🔍</span>
          <span className="mode-text">Deep Thinking</span>
        </button>
      </div>
      <div className="thinking-mode-hint">
        {mode === 'thinking' 
          ? 'Fast responses with intelligent analysis'
          : 'Comprehensive analysis with exhaustive search'}
      </div>
    </div>
  );
};

export default ThinkingModeToggle;

