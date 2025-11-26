/**
 * ConversationSidebar Component
 * 
 * Left sidebar for managing conversations. Provides:
 * - Conversation list with search functionality
 * - Folder organization (All Chats, Recent, Favorites)
 * - Conversation actions (create, rename, delete)
 * - User profile section
 * 
 * Features:
 * - Real-time search across all conversations
 * - Scrollable conversation list
 * - Custom dialog for rename/delete (no browser prompts)
 * - Auto-title generation from first message
 * 
 * State Management:
 * - Uses Redux for conversation list (conversationsSlice)
 * - Local state for search query and folder selection
 * 
 * @example
 * ```tsx
 * <ConversationSidebar />
 * ```
 */
import React, { useState, useMemo, useEffect } from 'react';
import { useAppDispatch, useAppSelector } from '@/store/hooks';
import {
  setCurrentConversation,
  addConversation,
  updateConversation,
  deleteConversation,
  setConversations,
} from '@/store/slices/conversationsSlice';
import { setMessages } from '@/store/slices/messagesSlice';
import { apiService } from '@/services/apiService';
import Dialog from './Dialog';

interface Folder {
  id: string;
  name: string;
  icon?: string;
}

const ConversationSidebar: React.FC = () => {
  const dispatch = useAppDispatch();
  const conversations = useAppSelector((state) => state.conversations.conversations);
  const currentConversationId = useAppSelector(
    (state) => state.conversations.currentConversationId
  );
  
  const [searchQuery, setSearchQuery] = useState('');
  const [selectedFolder, setSelectedFolder] = useState<string | null>('all');
  const [isCreating, setIsCreating] = useState(false);
  const [folders, setFolders] = useState<Folder[]>([
    { id: 'all', name: 'All Chats' },
    { id: 'recent', name: 'Recent' },
    { id: 'favorites', name: 'Favorites' },
  ]);
  const [conversationFolders, setConversationFolders] = useState<Record<number, string>>({});
  
  // Dialog states
  const [deleteDialog, setDeleteDialog] = useState<{ isOpen: boolean; conversationId: number | null }>({
    isOpen: false,
    conversationId: null,
  });
  const [renameDialog, setRenameDialog] = useState<{ isOpen: boolean; conversationId: number | null; currentTitle: string }>({
    isOpen: false,
    conversationId: null,
    currentTitle: '',
  });

  // Don't load conversations here - App.tsx handles initial loading
  // This component just displays conversations from Redux store

  // Filter conversations based on search and folder
  const filteredConversations = useMemo(() => {
    let filtered = conversations;

    // Filter by folder
    if (selectedFolder && selectedFolder !== 'all') {
      if (selectedFolder === 'recent') {
        // Show conversations from last 7 days
        const sevenDaysAgo = new Date();
        sevenDaysAgo.setDate(sevenDaysAgo.getDate() - 7);
        filtered = filtered.filter(
          (conv) => new Date(conv.updated_at) > sevenDaysAgo
        );
      } else if (selectedFolder === 'favorites') {
        // Show favorited conversations (can be extended with favorite flag)
        filtered = filtered.filter((conv) => conv.id && conversationFolders[conv.id] === 'favorites');
      } else {
        filtered = filtered.filter(
          (conv) => conv.id && conversationFolders[conv.id] === selectedFolder
        );
      }
    }

    // Filter by search query
    if (searchQuery.trim()) {
      const query = searchQuery.toLowerCase();
      filtered = filtered.filter(
        (conv) =>
          conv.title?.toLowerCase().includes(query) ||
          conv.id?.toString().includes(query)
      );
    }

    // Sort by updated_at (most recent first)
    return [...filtered].sort((a, b) => {
      const dateA = new Date(a.updated_at).getTime();
      const dateB = new Date(b.updated_at).getTime();
      return dateB - dateA;
    });
  }, [conversations, searchQuery, selectedFolder, conversationFolders]);

  const handleCreateConversation = async () => {
    setIsCreating(true);
    try {
      const conv = await apiService.createConversation('New Chat');
      // addConversation already sets currentConversationId, but we'll set it explicitly to ensure it's set
      dispatch(addConversation(conv));
      // Ensure current conversation is set (addConversation sets it, but this ensures it's set)
      dispatch(setCurrentConversation(conv.id));
      // Load messages for the new conversation (will be empty for a new conversation)
      const messages = await apiService.getMessages(conv.id);
      dispatch(setMessages({ conversationId: conv.id, messages }));
      // Force a small delay to ensure state updates are processed
      await new Promise(resolve => setTimeout(resolve, 0));
    } catch (error: any) {
      console.error('Error creating conversation:', error);
      alert(`Failed to create conversation: ${error.message || 'Unknown error'}`);
    } finally {
      setIsCreating(false);
    }
  };

  const handleSelectConversation = async (id: number) => {
    if (id === currentConversationId) return;
    console.log('Selecting conversation:', id);
    // Set conversation first
    dispatch(setCurrentConversation(id));
    // Load messages for selected conversation
    // Note: MessageList will also load messages as a fallback, but we load here for immediate display
    try {
      console.log('Loading messages for conversation:', id);
      const messages = await apiService.getMessages(id);
      console.log(`Loaded ${messages.length} messages for conversation ${id}:`, messages);
      dispatch(setMessages({ conversationId: id, messages }));
      console.log('Messages dispatched to Redux store');
    } catch (error) {
      console.error('Error loading messages:', error);
      // Even if loading fails here, MessageList will try to load as fallback
    }
  };

  const handleDeleteClick = (id: number, e: React.MouseEvent) => {
    e.stopPropagation();
    setDeleteDialog({ isOpen: true, conversationId: id });
  };

  const handleDeleteConfirm = async () => {
    if (!deleteDialog.conversationId) return;
    
    const id = deleteDialog.conversationId;
    try {
      // Delete from mock API storage
      await apiService.deleteConversation(id);
      // Delete from Redux state
      dispatch(deleteConversation(id));
      if (currentConversationId === id) {
        // Select first conversation or create new one
        const remaining = conversations.filter((c) => c.id !== id);
        if (remaining.length > 0) {
          dispatch(setCurrentConversation(remaining[0].id!));
        }
      }
    } catch (error) {
      console.error('Error deleting conversation:', error);
    } finally {
      setDeleteDialog({ isOpen: false, conversationId: null });
    }
  };

  const handleRenameClick = (id: number, currentTitle: string, e: React.MouseEvent) => {
    e.stopPropagation();
    setRenameDialog({ isOpen: true, conversationId: id, currentTitle });
  };

  const handleRenameConfirm = async (newTitle?: string) => {
    if (!renameDialog.conversationId || !newTitle || !newTitle.trim()) {
      setRenameDialog({ isOpen: false, conversationId: null, currentTitle: '' });
      return;
    }
    
    try {
      // In a real app, call API to update
      dispatch(updateConversation({ id: renameDialog.conversationId, title: newTitle.trim() }));
    } catch (error) {
      console.error('Error renaming conversation:', error);
    } finally {
      setRenameDialog({ isOpen: false, conversationId: null, currentTitle: '' });
    }
  };

  const getConversationTitle = (conv: any) => {
    return conv.title || `Chat ${conv.id}`;
  };

  const truncateTitle = (title: string, maxLength: number = 30) => {
    if (title.length <= maxLength) return title;
    return title.substring(0, maxLength) + '...';
  };

  return (
    <div className="conversation-sidebar">
      {/* Top Navigation */}
      <div className="sidebar-header">
        <div className="sidebar-nav">
          <button
            className="sidebar-nav-item"
            onClick={handleCreateConversation}
            disabled={isCreating}
            title="New chat"
          >
            <span className="nav-icon">
              <svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
                <path d="M12 5v14M5 12h14"/>
              </svg>
            </span>
            <span className="nav-label">New chat</span>
          </button>
          <button className="sidebar-nav-item" title="Projects">
            <span className="nav-icon">
              <svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
                <path d="M22 19a2 2 0 0 1-2 2H4a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h5l2 3h9a2 2 0 0 1 2 2z"/>
                <line x1="12" y1="11" x2="12" y2="17"/>
                <line x1="9" y1="14" x2="15" y2="14"/>
              </svg>
            </span>
            <span className="nav-label">Projects</span>
          </button>
        </div>
      </div>

      {/* Search Bar */}
      <div className="sidebar-search">
        <input
          type="text"
          className="search-input"
          placeholder="Search chats..."
          value={searchQuery}
          onChange={(e) => setSearchQuery(e.target.value)}
        />
        {searchQuery && (
          <button
            className="search-clear"
            onClick={() => setSearchQuery('')}
            title="Clear search"
          >
            ✕
          </button>
        )}
      </div>


      {/* Conversations List */}
      <div className="sidebar-conversations">
        <div className="conversations-header">
          <span className="conversations-title">Chats</span>
          <span className="conversations-count">
            {filteredConversations.length}
          </span>
        </div>
        <div className="conversations-list">
          {filteredConversations.length === 0 ? (
            <div className="conversations-empty">
              {searchQuery ? 'No conversations found' : 'No conversations yet'}
            </div>
          ) : (
            filteredConversations.map((conv, index) => (
              <div
                key={conv.id ? `conv-${conv.id}` : `conv-temp-${index}`}
                className={`conversation-item ${
                  currentConversationId === conv.id ? 'active' : ''
                }`}
                onClick={() => handleSelectConversation(conv.id!)}
              >
                <div className="conversation-content">
                  <div className="conversation-title">
                    {truncateTitle(getConversationTitle(conv))}
                  </div>
                  <div className="conversation-meta">
                    {new Date(conv.updated_at).toLocaleDateString()}
                  </div>
                </div>
                <div className="conversation-actions">
                  <button
                    className="conversation-action-btn"
                    onClick={(e) => handleRenameClick(conv.id!, getConversationTitle(conv), e)}
                    title="Rename"
                  >
                    <svg xmlns="http://www.w3.org/2000/svg" width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
                      <path d="M11 4H4a2 2 0 0 0-2 2v14a2 2 0 0 0 2 2h14a2 2 0 0 0 2-2v-7"/>
                      <path d="M18.5 2.5a2.121 2.121 0 0 1 3 3L12 15l-4 1 1-4 9.5-9.5z"/>
                    </svg>
                  </button>
                  <button
                    className="conversation-action-btn"
                    onClick={(e) => handleDeleteClick(conv.id!, e)}
                    title="Delete"
                  >
                    <svg xmlns="http://www.w3.org/2000/svg" width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
                      <polyline points="3 6 5 6 21 6"/>
                      <path d="M19 6v14a2 2 0 0 1-2 2H7a2 2 0 0 1-2-2V6m3 0V4a2 2 0 0 1 2-2h4a2 2 0 0 1 2 2v2"/>
                    </svg>
                  </button>
                </div>
              </div>
            ))
          )}
        </div>
      </div>

      {/* User Profile Section */}
      <div className="sidebar-footer">
        <div className="user-profile">
          <div className="user-avatar">
            <svg xmlns="http://www.w3.org/2000/svg" width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
              <path d="M20 21v-2a4 4 0 0 0-4-4H8a4 4 0 0 0-4 4v2"/>
              <circle cx="12" cy="7" r="4"/>
            </svg>
          </div>
          <div className="user-info">
            <div className="user-name">User</div>
            <div className="user-plan">Free</div>
          </div>
          <button className="upgrade-button">Upgrade</button>
        </div>
      </div>

      {/* Delete Confirmation Dialog */}
      <Dialog
        isOpen={deleteDialog.isOpen}
        onClose={() => setDeleteDialog({ isOpen: false, conversationId: null })}
        title="Delete Conversation"
        message="Are you sure you want to delete this conversation? This action cannot be undone."
        type="confirm"
        confirmLabel="Delete"
        cancelLabel="Cancel"
        onConfirm={handleDeleteConfirm}
      />

      {/* Rename Dialog */}
      <Dialog
        isOpen={renameDialog.isOpen}
        onClose={() => setRenameDialog({ isOpen: false, conversationId: null, currentTitle: '' })}
        title="Rename Conversation"
        type="prompt"
        defaultValue={renameDialog.currentTitle}
        confirmLabel="Save"
        cancelLabel="Cancel"
        onConfirm={handleRenameConfirm}
        placeholder="Enter conversation name"
      />
    </div>
  );
};

export default ConversationSidebar;
