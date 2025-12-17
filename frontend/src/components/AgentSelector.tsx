import React, { useEffect, useState } from 'react';
import { apiService } from '@/services/api';
import './AgentSelector.css';

interface AgentSelectorProps {
  conversationId: number | null;
  currentAgent?: string;
  onAgentChange?: (agent: string) => void;
}

const AGENT_OPTIONS = [
  { value: 'ask', label: 'Ask', hint: 'Fast answers' },
  { value: 'plan', label: 'Plan', hint: 'Steps and actions' },
  { value: 'observability_ag', label: 'Observability-Ag', hint: 'Logs/metrics/traces first' },
  { value: 'analysis_ag', label: 'Analysis-Ag', hint: 'Deep, multi-hop code analysis' },
];

const AgentSelector: React.FC<AgentSelectorProps> = ({
  conversationId,
  currentAgent = 'ask',
  onAgentChange,
}) => {
  const [agent, setAgent] = useState<string>(currentAgent);
  const [isUpdating, setIsUpdating] = useState(false);

  useEffect(() => {
    setAgent(currentAgent);
  }, [currentAgent]);

  const handleChange = async (newAgent: string) => {
    if (!conversationId || newAgent === agent || isUpdating) {
      return;
    }
    setIsUpdating(true);
    try {
      await apiService.updateAgent(conversationId, newAgent);
      setAgent(newAgent);
      onAgentChange?.(newAgent);
    } catch (error) {
      console.error('Failed to update agent:', error);
    } finally {
      setIsUpdating(false);
    }
  };

  if (!conversationId) {
    return null;
  }

  return (
    <div className="agent-selector">
      <div className="agent-selector-label">Agent:</div>
      <div className="agent-selector-options">
        {AGENT_OPTIONS.map((opt) => (
          <button
            key={opt.value}
            className={`agent-btn ${agent === opt.value ? 'active' : ''}`}
            onClick={() => handleChange(opt.value)}
            disabled={isUpdating}
            title={opt.hint}
          >
            <span className="agent-text">{opt.label}</span>
          </button>
        ))}
      </div>
      <div className="agent-selector-hint">
        {AGENT_OPTIONS.find((o) => o.value === agent)?.hint || ''}
      </div>
    </div>
  );
};

export default AgentSelector;

