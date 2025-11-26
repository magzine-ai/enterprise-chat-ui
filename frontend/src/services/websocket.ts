/** WebSocket service for real-time updates. */
import type { WebSocketMessage } from '@/types';

// Construct WebSocket URL from API URL
const getWebSocketUrl = () => {
  if (import.meta.env.VITE_WS_URL) {
    // If VITE_WS_URL is explicitly set, use it as-is (it should already include /ws)
    return import.meta.env.VITE_WS_URL;
  }
  const apiUrl = import.meta.env.VITE_API_URL || 'http://localhost:8000';
  // Convert http:// to ws:// and https:// to wss://, then append /ws
  return apiUrl.replace(/^http/, 'ws') + '/ws';
};

const WS_BASE_URL = getWebSocketUrl();

export class WebSocketService {
  private ws: WebSocket | null = null;
  private reconnectAttempts = 0;
  private maxReconnectAttempts = 5;
  private listeners: Map<string, Set<(data: any) => void>> = new Map();

  connect(token?: string): void {
    // Don't reconnect if already connected
    if (this.ws && this.ws.readyState === WebSocket.OPEN) {
      console.log('WebSocket already connected');
      return;
    }

    // WS_BASE_URL already includes /ws if derived from API_URL, or is complete if from VITE_WS_URL
    // So we use it directly without appending /ws again
    const url = token ? `${WS_BASE_URL}?token=${token}` : WS_BASE_URL;
    console.log('Connecting to WebSocket:', url);
    this.ws = new WebSocket(url);

    this.ws.onopen = () => {
      console.log('✅ WebSocket connected successfully');
      this.reconnectAttempts = 0;
    };

    this.ws.onmessage = (event) => {
      try {
        const message: WebSocketMessage = JSON.parse(event.data);
        console.log('📨 WebSocket message received:', message.type);
        console.log('📨 WebSocket message data:', message.data);
        this.notifyListeners(message.type, message.data);
      } catch (error) {
        console.error('❌ Error parsing WebSocket message:', error);
        console.error('❌ Raw message data:', event.data);
      }
    };

    this.ws.onerror = (error) => {
      console.error('❌ WebSocket error:', error);
      // WebSocket errors are often connection issues - the onclose handler will handle reconnection
      // Don't throw or show alerts here as it's expected during initial connection attempts
    };

    this.ws.onclose = (event) => {
      console.log('WebSocket disconnected', event.code, event.reason);
      this.reconnect(token);
    };
  }

  private reconnect(token?: string): void {
    if (this.reconnectAttempts < this.maxReconnectAttempts) {
      this.reconnectAttempts++;
      setTimeout(() => {
        console.log(`Reconnecting... (attempt ${this.reconnectAttempts})`);
        this.connect(token);
      }, 1000 * this.reconnectAttempts);
    }
  }

  on(event: string, callback: (data: any) => void): () => void {
    if (!this.listeners.has(event)) {
      this.listeners.set(event, new Set());
    }
    this.listeners.get(event)!.add(callback);

    // Return unsubscribe function
    return () => {
      this.listeners.get(event)?.delete(callback);
    };
  }

  private notifyListeners(event: string, data: any): void {
    this.listeners.get(event)?.forEach((callback) => {
      try {
        callback(data);
      } catch (error) {
        console.error('Error in WebSocket listener:', error);
      }
    });
  }

  disconnect(): void {
    if (this.ws) {
      this.ws.close();
      this.ws = null;
    }
    this.listeners.clear();
  }

  send(data: any): void {
    if (this.ws && this.ws.readyState === WebSocket.OPEN) {
      this.ws.send(JSON.stringify(data));
    }
  }

  /**
   * Check if WebSocket is currently connected
   */
  isConnected(): boolean {
    return this.ws !== null && this.ws.readyState === WebSocket.OPEN;
  }

  /**
   * Get current WebSocket connection state
   */
  getConnectionState(): 'connecting' | 'connected' | 'disconnected' {
    if (!this.ws) return 'disconnected';
    if (this.ws.readyState === WebSocket.OPEN) return 'connected';
    if (this.ws.readyState === WebSocket.CONNECTING) return 'connecting';
    return 'disconnected';
  }
}

export const wsService = new WebSocketService();


