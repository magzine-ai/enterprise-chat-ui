/**
 * CollapsibleSection Component
 * 
 * Collapsible/expandable section for organizing content.
 * Useful for hiding/showing detailed information, logs, or nested content.
 * 
 * @example
 * ```tsx
 * <CollapsibleSection
 *   title="Details"
 *   defaultExpanded={false}
 * >
 *   <p>Hidden content here</p>
 * </CollapsibleSection>
 * ```
 * 
 * @param title - Section title
 * @param defaultExpanded - Whether section starts expanded (default: false)
 * @param children - Content to show/hide
 * @param icon - Optional icon to display
 */
import React, { useState } from 'react';

interface CollapsibleSectionProps {
  title: string;
  defaultExpanded?: boolean;
  children: React.ReactNode;
  icon?: string;
}

const CollapsibleSection: React.FC<CollapsibleSectionProps> = ({
  title,
  defaultExpanded = false,
  children,
  icon,
}) => {
  const [isExpanded, setIsExpanded] = useState(defaultExpanded);

  return (
    <div className="collapsible-section">
      <button
        className="collapsible-header"
        onClick={() => setIsExpanded(!isExpanded)}
      >
        <span className="collapsible-icon">
          {isExpanded ? '▼' : '▶'}
        </span>
        {icon && <span className="collapsible-title-icon">{icon}</span>}
        <span className="collapsible-title">{title}</span>
      </button>
      {isExpanded && (
        <div className="collapsible-content">
          {children}
        </div>
      )}
    </div>
  );
};

export default CollapsibleSection;


