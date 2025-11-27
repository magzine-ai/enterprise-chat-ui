/**
 * Main Application Component
 * 
 * This is the root component of the chat application. It handles:
 * - Authentication and token management
 * - WebSocket connection setup
 * - Initial conversation loading
 * - Redux store provider
 * 
 * Connects to FastAPI backend API.
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
import { 
  setMessages, 
  addMessage, 
  clearMessages, 
  setWaitingForResponse,
  startStreamingMessage,
  appendStreamToken,
  appendStreamChunk,
  completeStreamingMessage
} from './store/slices/messagesSlice';
import { updateJob } from './store/slices/jobsSlice';
// Use API service (switches between real and mock based on config)
import { apiService } from './services/apiService';
import { wsService } from './services/wsService';
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
    console.log('🚀 Connecting to Python API backend');
    const initApp = async () => {
      try {
        // Try to login if auth is enabled, otherwise skip
        const token = apiService.getToken();
        if (!token) {
          try {
            await apiService.login('dev', 'dev');
          } catch (loginError: any) {
            // If login fails (e.g., auth disabled), continue without token
            console.log('Login skipped or failed (auth may be disabled):', loginError?.message || loginError);
            // Clear any partial token state
            apiService.setToken('');
          }
        }

        // Connect WebSocket (with or without token)
        const currentToken = apiService.getToken();
        if (currentToken) {
          wsService.connect(currentToken);
        } else {
          // Connect without token when auth is disabled
          wsService.connect();
        }
        
        // Log WebSocket connection status after a short delay
        setTimeout(() => {
          const wsState = wsService.getConnectionState();
          console.log(`🔌 WebSocket connection state: ${wsState}`);
          if (wsState === 'connected') {
            console.log('✅ WebSocket ready for assistant messages');
          } else {
            console.warn('⚠️ WebSocket not connected - assistant messages may not arrive');
          }
        }, 1000); // Check after 1 second to allow connection to establish

        // Load existing conversations
        try {
          console.log('Loading conversations...');
          const conversations = await apiService.getConversations();
          console.log(`Loaded ${conversations.length} conversations:`, conversations);
          if (conversations.length > 0) {
            dispatch(setConversations(conversations));
            // Select the most recent conversation
            const latestConv = conversations[0];
            console.log('Selecting conversation:', latestConv.id);
            dispatch(setCurrentConversation(latestConv.id));
            // Load messages for selected conversation
            console.log('Loading messages for conversation:', latestConv.id);
            const messages = await apiService.getMessages(latestConv.id);
            console.log(`Loaded ${messages.length} messages:`, messages);
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
          // Don't create fallback conversation here to avoid duplicates
          // User can create one manually if needed
        }
      } catch (error) {
        console.error('Error initializing app:', error);
        // Show user-friendly error message
        alert('Failed to connect to backend API. Please ensure the server is running at ' + (import.meta.env.VITE_API_URL || 'http://localhost:8000'));
      }
    };

    initApp();

    // WebSocket listeners for real-time updates
    // 
    // Edge Cases Handled:
    // - Duplicate message prevention
    // - Conversation switching during message receive
    // - Missing conversation_id validation
    // - Race conditions with API calls
    // - Error handling for message reload
    const unsubscribeMessage = wsService.on('message.new', (data) => {
      console.log('📨 WebSocket message.new received:', data);
      
      // Validation: Check required fields
      if (!data || typeof data !== 'object') {
        console.warn('WebSocket message is not a valid object, skipping', data);
        return;
      }
      
      if (!data.conversation_id || !data.id || !data.role) {
        console.warn('WebSocket message missing required fields (conversation_id, id, or role), skipping', {
          conversation_id: data.conversation_id,
          id: data.id,
          role: data.role
        });
        return;
      }
      
      const conversationId = data.conversation_id;
      const messageId = data.id;
      
      // Get current state
      const currentState = store.getState();
      const currentMessages = currentState.messages.messagesByConversation[conversationId] || [];
      
      // Check if message already exists (prevent duplicates)
      // This handles cases where:
      // - WebSocket receives duplicate messages
      // - API response and WebSocket message arrive for same message
      const messageExists = currentMessages.some(msg => msg.id === messageId);
      if (messageExists) {
        console.log(`📨 WebSocket: Message ${messageId} already exists, skipping`);
        return;
      }
      
      // Handle assistant messages
      if (data.role === 'assistant') {
        console.log('✅ Assistant response received via WebSocket');
        console.log('📊 Current waitingForResponse state BEFORE clearing:', store.getState().messages.waitingForResponse);
        
        // Add the assistant message
        dispatch(addMessage(data));
        
        // Clear waiting state to unblock input IMMEDIATELY
        console.log(`🔓 Clearing waiting state for conversation ${conversationId}`);
        dispatch(setWaitingForResponse({ conversationId, waiting: false }));
        
        // Verify it was cleared
        const stateAfterClear = store.getState();
        console.log('📊 Current waitingForResponse state AFTER clearing:', stateAfterClear.messages.waitingForResponse);
        if (stateAfterClear.messages.waitingForResponse[conversationId]) {
          console.error('❌ ERROR: Waiting state still true after clear!');
        } else {
          console.log('✅ Waiting state successfully cleared');
        }
        
        // Reload all messages to ensure consistency
        // This is a safety measure to handle any edge cases:
        // - Messages arriving out of order
        // - State inconsistencies
        // - Multiple WebSocket connections
        apiService.getMessages(conversationId)
          .then(messages => {
            // Double-check: conversation hasn't changed during async operation
            const latestState = store.getState();
            if (latestState.conversations.currentConversationId === conversationId) {
              dispatch(setMessages({ conversationId, messages }));
              
              // Double-check: ensure waiting state is still cleared after setMessages
              // This handles any edge cases where setMessages might have affected the state
              const stateAfterSetMessages = store.getState();
              if (stateAfterSetMessages.messages.waitingForResponse[conversationId]) {
                console.log('⚠️ Waiting state still true after setMessages, clearing again...');
                dispatch(setWaitingForResponse({ conversationId, waiting: false }));
              } else {
                console.log('✅ Waiting state cleared successfully after setMessages');
              }
            }
          })
          .catch(error => {
            console.error('Error reloading messages after WebSocket:', error);
            // Even if getMessages fails, ensure waiting state is cleared
            const errorState = store.getState();
            if (errorState.messages.waitingForResponse[conversationId]) {
              console.log('⚠️ Error occurred, but ensuring waiting state is cleared...');
              dispatch(setWaitingForResponse({ conversationId, waiting: false }));
            }
          });
      } 
      // Ignore user messages from WebSocket - we already have them from API response
      // This matches mock API behavior where only assistant messages come via WebSocket
      else if (data.role === 'user') {
        console.log('📨 WebSocket: Ignoring user message (already have from API response)');
        // Skip - user messages are already in state from API response
        return;
      } else {
        console.warn('WebSocket message with unknown role:', data.role);
      }
    });

    const unsubscribeJob = wsService.on('job.update', (data) => {
      dispatch(updateJob(data));
    });

    // WebSocket listeners for streaming responses
    // 
    // Handles real-time token streaming from LLM:
    // - message.stream.start: Initializes streaming message
    // - message.stream.token: Appends individual token
    // - message.stream.chunk: Appends chunk of tokens (more efficient)
    // - message.stream.end: Finalizes message with blocks
    
    const unsubscribeStreamStart = wsService.on('message.stream.start', (data) => {
      console.log('🌊 Streaming started:', data);
      
      if (!data || !data.conversation_id) {
        console.warn('Invalid stream.start data:', data);
        return;
      }
      
      const conversationId = data.conversation_id;
      const messageId = data.message_id;
      
      if (!messageId) {
        console.warn('Stream start missing message_id:', data);
        return;
      }
      
      // Initialize streaming message
      dispatch(startStreamingMessage({ conversationId, messageId }));
      
      // Ensure waiting state is set (streaming means we're waiting)
      dispatch(setWaitingForResponse({ conversationId, waiting: true }));
    });
    
    const unsubscribeStreamToken = wsService.on('message.stream.token', (data) => {
      if (!data || !data.conversation_id || !data.token) {
        console.warn('Invalid stream.token data:', data);
        return;
      }
      
      const conversationId = data.conversation_id;
      const messageId = data.message_id;
      const token = data.token;
      
      if (!messageId) {
        console.warn('Stream token missing message_id:', data);
        return;
      }
      
      // Append token to streaming message
      dispatch(appendStreamToken({ conversationId, messageId, token }));
    });
    
    const unsubscribeStreamChunk = wsService.on('message.stream.chunk', (data) => {
      if (!data || !data.conversation_id || !data.chunk) {
        console.warn('Invalid stream.chunk data:', data);
        return;
      }
      
      const conversationId = data.conversation_id;
      const messageId = data.message_id;
      const chunk = data.chunk;
      
      if (!messageId) {
        console.warn('Stream chunk missing message_id:', data);
        return;
      }
      
      // Append chunk to streaming message (more efficient than individual tokens)
      dispatch(appendStreamChunk({ conversationId, messageId, chunk }));
    });
    
    const unsubscribeStreamEnd = wsService.on('message.stream.end', (data) => {
      console.log('🌊 Streaming ended:', data);
      
      if (!data || !data.conversation_id) {
        console.warn('Invalid stream.end data:', data);
        return;
      }
      
      const conversationId = data.conversation_id;
      const messageId = data.message_id;
      const blocks = data.blocks || [];
      
      if (!messageId) {
        console.warn('Stream end missing message_id:', data);
        return;
      }
      
      // Complete streaming message with blocks
      dispatch(completeStreamingMessage({ conversationId, messageId, blocks }));
      
      // Clear waiting state
      dispatch(setWaitingForResponse({ conversationId, waiting: false }));
      
      // Reload messages to ensure consistency
      apiService.getMessages(conversationId)
        .then(messages => {
          const latestState = store.getState();
          if (latestState.conversations.currentConversationId === conversationId) {
            dispatch(setMessages({ conversationId, messages }));
            // Ensure waiting state is cleared after reload
            dispatch(setWaitingForResponse({ conversationId, waiting: false }));
          }
        })
        .catch(error => {
          console.error('Error reloading messages after stream end:', error);
          // Ensure waiting state is cleared even on error
          dispatch(setWaitingForResponse({ conversationId, waiting: false }));
        });
    });

    // Monitor WebSocket connection and auto-reconnect if disconnected
    const connectionMonitor = setInterval(() => {
      if (!wsService.isConnected()) {
        console.warn('⚠️ WebSocket disconnected, attempting reconnect...');
        const token = apiService.getToken();
        wsService.connect(token || undefined);
      }
    }, 5000); // Check every 5 seconds

    return () => {
      clearInterval(connectionMonitor);
      unsubscribeMessage();
      unsubscribeJob();
      unsubscribeStreamStart();
      unsubscribeStreamToken();
      unsubscribeStreamChunk();
      unsubscribeStreamEnd();
      wsService.disconnect();
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
