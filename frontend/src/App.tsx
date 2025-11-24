/**
 * Main Application Component
 * 
 * This is the root component of the chat application. It handles:
 * - Authentication and token management
 * - WebSocket connection setup
 * - Initial conversation loading
 * - Redux store provider
 * 
 * The app supports two modes:
 * - Mock mode (default): Uses mockApi and mockWebSocket for frontend-only development
 * - Production mode: Connects to FastAPI backend
 * 
 * Mode is controlled by VITE_MOCK_SERVICES environment variable.
 */
import React, { useEffect } from 'react';
import { Provider } from 'react-redux';
import { store } from './store';
import { useAppDispatch, useAppSelector } from './store/hooks';
import {
  setConversations,
  addConversation,
  setCurrentConversation,
} from './store/slices/conversationsSlice';
import { setMessages, addMessage } from './store/slices/messagesSlice';
import { updateJob } from './store/slices/jobsSlice';
// Use mock services for frontend-only development
import { mockApiService as apiService } from './services/mockApi';
import { mockWsService as wsService } from './services/mockWebSocket';
import ConversationSidebar from './components/ConversationSidebar';
import MessageList from './components/MessageList';
import MessageInput from './components/MessageInput';
import './App.css';

const AppContent: React.FC = () => {
  const dispatch = useAppDispatch();
  const currentConversationId = useAppSelector(
    (state) => state.conversations.currentConversationId
  );

  useEffect(() => {
    // Auto-login for dev (using mocks)
    console.log('🚀 Using Mock API Services - Frontend-only mode');
    const initApp = async () => {
      try {
        await apiService.login('dev', 'dev');
        const token = apiService.getToken();
        if (token) {
          wsService.connect(token);
        }

        // Load existing conversations
        try {
          const conversations = await apiService.getConversations();
          if (conversations.length > 0) {
            dispatch(setConversations(conversations));
            // Select the most recent conversation
            const latestConv = conversations[0];
            dispatch(setCurrentConversation(latestConv.id));
            // Load messages for selected conversation
            const messages = await apiService.getMessages(latestConv.id);
            dispatch(setMessages({ conversationId: latestConv.id, messages }));
          } else {
            // Create initial conversation if none exist
            const conv = await apiService.createConversation('Main Chat');
            dispatch(addConversation(conv));
            dispatch(setCurrentConversation(conv.id));
            // Load messages for initial conversation
            const messages = await apiService.getMessages(conv.id);
            dispatch(setMessages({ conversationId: conv.id, messages }));
          }
        } catch (error) {
          console.error('Error loading conversations:', error);
          // Fallback: create a new conversation
          const conv = await apiService.createConversation('Main Chat');
          dispatch(addConversation(conv));
          dispatch(setCurrentConversation(conv.id));
        }
      } catch (error) {
        console.error('Error initializing app:', error);
      }
    };

    initApp();

    // WebSocket listeners (these handle messages from mock API)
    const unsubscribeMessage = wsService.on('message.new', (data) => {
      // Add all messages from WebSocket (both user and assistant)
      dispatch(addMessage(data));
    });

    const unsubscribeJob = wsService.on('job.update', (data) => {
      dispatch(updateJob(data));
    });
    
    // Listen for mock events directly (for all messages)
    const handleMockMessage = ((e: CustomEvent) => {
      // Dispatch all messages from mock events
      dispatch(addMessage(e.detail));
    }) as EventListener;
    
    const handleMockJob = ((e: CustomEvent) => {
      dispatch(updateJob(e.detail));
    }) as EventListener;
    
    window.addEventListener('mock:message.new', handleMockMessage);
    window.addEventListener('mock:job.update', handleMockJob);

    return () => {
      unsubscribeMessage();
      unsubscribeJob();
      wsService.disconnect();
      window.removeEventListener('mock:message.new', handleMockMessage);
      window.removeEventListener('mock:job.update', handleMockJob);
    };
  }, [dispatch]);

  return (
    <div className="app">
      <ConversationSidebar />
      <div className="app-main-content">
        <header className="app-header">
          <h1>Enterprise Chat</h1>
          <div style={{ display: 'flex', gap: '0.5rem' }}>
            <button
              className="admin-button"
              onClick={() => {
                const url = window.location.origin + '/developer-tools.html';
                window.open(url, '_blank', 'width=1400,height=900');
              }}
              title="Open Developer Tools"
            >
              <svg
                xmlns="http://www.w3.org/2000/svg"
                width="18"
                height="18"
                viewBox="0 0 24 24"
                fill="none"
                stroke="currentColor"
                strokeWidth="2"
                strokeLinecap="round"
                strokeLinejoin="round"
              >
                <path d="M14.7 6.3a1 1 0 0 0 0 1.4l1.6 1.6a1 1 0 0 0 1.4 0l3.77-3.77a6 6 0 0 1-7.94 7.94l-6.91 6.91a2.12 2.12 0 0 1-3-3l6.91-6.91a6 6 0 0 1 7.94-7.94l-3.76 3.76z" />
              </svg>
              Developer Tools
            </button>
            <button
              className="admin-button"
              onClick={() => {
                const url = window.location.origin + '/marketplace.html';
                window.open(url, '_blank', 'width=1400,height=900');
              }}
              title="Open Administration Marketplace"
            >
              <svg
                xmlns="http://www.w3.org/2000/svg"
                width="18"
                height="18"
                viewBox="0 0 24 24"
                fill="none"
                stroke="currentColor"
                strokeWidth="2"
                strokeLinecap="round"
                strokeLinejoin="round"
              >
                <path d="M12 20h9" />
                <path d="M16.5 3.5a2.121 2.121 0 0 1 3 3L7 19l-4 1 1-4L16.5 3.5z" />
              </svg>
              Administration
            </button>
          </div>
        </header>
        <main className="app-main">
          <MessageList />
          <MessageInput />
        </main>
      </div>
    </div>
  );
};

const App: React.FC = () => {
  return (
    <Provider store={store}>
      <AppContent />
    </Provider>
  );
};

export default App;
