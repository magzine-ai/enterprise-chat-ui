/**
 * Checklist Component
 * 
 * Interactive checklist for task management with checkboxes, completion tracking,
 * and optional due dates and priorities. Useful for tracking action items, 
 * deployment checklists, and multi-step processes.
 * 
 * @example
 * ```tsx
 * <Checklist
 *   title="Deployment Checklist"
 *   items={[
 *     { id: '1', text: 'Backup database', checked: false, priority: 'high' },
 *     { id: '2', text: 'Run tests', checked: true, dueDate: '2024-01-15' },
 *     { id: '3', text: 'Deploy to staging', checked: false },
 *   ]}
 *   onToggle={(id) => console.log('Toggled:', id)}
 *   showProgress={true}
 * />
 * ```
 */
import React, { useState, useEffect } from 'react';

export interface ChecklistItem {
  id: string;
  text: string;
  checked?: boolean;
  priority?: 'low' | 'medium' | 'high' | 'critical';
  dueDate?: string;
  assignee?: string;
  notes?: string;
  subItems?: ChecklistItem[];
}

interface ChecklistProps {
  title?: string;
  items: ChecklistItem[];
  onToggle?: (id: string, checked: boolean) => void;
  onItemUpdate?: (item: ChecklistItem) => void;
  showProgress?: boolean;
  showPriority?: boolean;
  showDueDate?: boolean;
  allowEdit?: boolean;
  collapsible?: boolean;
}

const Checklist: React.FC<ChecklistProps> = ({
  title,
  items,
  onToggle,
  onItemUpdate,
  showProgress = true,
  showPriority = true,
  showDueDate = true,
  allowEdit = false,
  collapsible = false,
}) => {
  const [localItems, setLocalItems] = useState<ChecklistItem[]>(items);
  const [expandedItems, setExpandedItems] = useState<Set<string>>(new Set());

  useEffect(() => {
    setLocalItems(items);
  }, [items]);

  const calculateProgress = (itemsList: ChecklistItem[]): number => {
    if (itemsList.length === 0) return 0;
    const checkedCount = itemsList.reduce((count, item) => {
      const itemChecked = item.checked ? 1 : 0;
      const subItemsChecked = item.subItems
        ? calculateProgress(item.subItems) / 100 * item.subItems.length
        : 0;
      return count + itemChecked + subItemsChecked;
    }, 0);
    return Math.round((checkedCount / itemsList.length) * 100);
  };

  const getTotalItems = (itemsList: ChecklistItem[]): number => {
    return itemsList.reduce((total, item) => {
      return total + 1 + (item.subItems ? getTotalItems(item.subItems) : 0);
    }, 0);
  };

  const getCheckedItems = (itemsList: ChecklistItem[]): number => {
    return itemsList.reduce((count, item) => {
      const itemCount = item.checked ? 1 : 0;
      const subItemsCount = item.subItems ? getCheckedItems(item.subItems) : 0;
      return count + itemCount + subItemsCount;
    }, 0);
  };

  const handleToggle = (id: string, checked: boolean) => {
    const updateItem = (itemsList: ChecklistItem[]): ChecklistItem[] => {
      return itemsList.map((item) => {
        if (item.id === id) {
          const updated = { ...item, checked };
          if (onToggle) {
            onToggle(id, checked);
          }
          if (onItemUpdate) {
            onItemUpdate(updated);
          }
          return updated;
        }
        if (item.subItems) {
          return { ...item, subItems: updateItem(item.subItems) };
        }
        return item;
      });
    };

    setLocalItems(updateItem(localItems));
  };

  const handleToggleExpand = (id: string) => {
    setExpandedItems((prev) => {
      const newSet = new Set(prev);
      if (newSet.has(id)) {
        newSet.delete(id);
      } else {
        newSet.add(id);
      }
      return newSet;
    });
  };

  const getPriorityColor = (priority?: string): string => {
    switch (priority) {
      case 'critical':
        return '#dc2626';
      case 'high':
        return '#ea580c';
      case 'medium':
        return '#f59e0b';
      case 'low':
        return '#10b981';
      default:
        return 'transparent';
    }
  };

  const formatDate = (dateString?: string): string => {
    if (!dateString) return '';
    try {
      const date = new Date(dateString);
      const now = new Date();
      const diffTime = date.getTime() - now.getTime();
      const diffDays = Math.ceil(diffTime / (1000 * 60 * 60 * 24));

      if (diffDays < 0) {
        return `Overdue (${Math.abs(diffDays)} days)`;
      } else if (diffDays === 0) {
        return 'Due today';
      } else if (diffDays === 1) {
        return 'Due tomorrow';
      } else {
        return `Due in ${diffDays} days`;
      }
    } catch {
      return dateString;
    }
  };

  const isOverdue = (dateString?: string): boolean => {
    if (!dateString) return false;
    try {
      return new Date(dateString) < new Date();
    } catch {
      return false;
    }
  };

  const renderItem = (item: ChecklistItem, depth: number = 0): React.ReactNode => {
    const hasSubItems = item.subItems && item.subItems.length > 0;
    const isExpanded = expandedItems.has(item.id);
    const indent = depth * 24;

    return (
      <div key={item.id} className="checklist-item" style={{ paddingLeft: `${indent}px` }}>
        <div className="checklist-item-content">
          <label className="checklist-checkbox-label">
            <input
              type="checkbox"
              checked={item.checked || false}
              onChange={(e) => handleToggle(item.id, e.target.checked)}
              className="checklist-checkbox"
            />
            <span className={`checklist-checkmark ${item.checked ? 'checked' : ''}`} />
            <span className={`checklist-item-text ${item.checked ? 'checked' : ''}`}>
              {item.text}
            </span>
          </label>

          <div className="checklist-item-meta">
            {showPriority && item.priority && (
              <span
                className="checklist-priority"
                style={{ borderLeftColor: getPriorityColor(item.priority) }}
              >
                {item.priority}
              </span>
            )}
            {showDueDate && item.dueDate && (
              <span
                className={`checklist-due-date ${isOverdue(item.dueDate) ? 'overdue' : ''}`}
              >
                {formatDate(item.dueDate)}
              </span>
            )}
            {item.assignee && (
              <span className="checklist-assignee">@{item.assignee}</span>
            )}
            {hasSubItems && collapsible && (
              <button
                className="checklist-expand-button"
                onClick={() => handleToggleExpand(item.id)}
              >
                <svg
                  width="16"
                  height="16"
                  viewBox="0 0 24 24"
                  fill="none"
                  stroke="currentColor"
                  strokeWidth="2"
                  style={{
                    transform: isExpanded ? 'rotate(90deg)' : 'rotate(0deg)',
                    transition: 'transform 0.2s',
                  }}
                >
                  <polyline points="9 18 15 12 9 6" />
                </svg>
              </button>
            )}
          </div>
        </div>

        {item.notes && (
          <div className="checklist-item-notes">{item.notes}</div>
        )}

        {hasSubItems && (!collapsible || isExpanded) && (
          <div className="checklist-subitems">
            {item.subItems!.map((subItem) => renderItem(subItem, depth + 1))}
          </div>
        )}
      </div>
    );
  };

  const progress = calculateProgress(localItems);
  const totalItems = getTotalItems(localItems);
  const checkedItems = getCheckedItems(localItems);

  return (
    <div className="checklist-wrapper">
      {title && <h3 className="checklist-title">{title}</h3>}

      {showProgress && (
        <div className="checklist-progress">
          <div className="checklist-progress-bar">
            <div
              className="checklist-progress-fill"
              style={{ width: `${progress}%` }}
            />
          </div>
          <div className="checklist-progress-text">
            {checkedItems} of {totalItems} completed ({progress}%)
          </div>
        </div>
      )}

      <div className="checklist-items">
        {localItems.map((item) => renderItem(item))}
      </div>

      {localItems.length === 0 && (
        <div className="checklist-empty">No items in checklist</div>
      )}
    </div>
  );
};

export default Checklist;

