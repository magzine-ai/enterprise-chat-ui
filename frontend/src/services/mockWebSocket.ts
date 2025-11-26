/** Mock WebSocket service for frontend-only development. */
class MockWebSocketService {
  private listeners: Map<string, Set<(data: any) => void>> = new Map();
  private connected = false;

  connect(token?: string) {
    if (token) {
      console.log('[Mock WS] Connected with token:', token.substring(0, 20) + '...');
    } else {
      console.log('[Mock WS] Connected without token (auth disabled)');
    }
    this.connected = true;

    // Listen for mock events from mockApi
    window.addEventListener('mock:message.new', ((e: CustomEvent) => {
      this.handleEvent('message.new', e.detail);
    }) as EventListener);

    window.addEventListener('mock:job.update', ((e: CustomEvent) => {
      this.handleEvent('job.update', e.detail);
    }) as EventListener);
  }

  private handleEvent(eventType: string, data: any) {
    const handlers = this.listeners.get(eventType);
    if (handlers) {
      handlers.forEach((handler) => {
        try {
          handler(data);
        } catch (error) {
          console.error(`Error in ${eventType} handler:`, error);
        }
      });
    }
  }

  on(eventType: string, handler: (data: any) => void): () => void {
    if (!this.listeners.has(eventType)) {
      this.listeners.set(eventType, new Set());
    }
    this.listeners.get(eventType)!.add(handler);

    // Return unsubscribe function
    return () => {
      const handlers = this.listeners.get(eventType);
      if (handlers) {
        handlers.delete(handler);
      }
    };
  }

  disconnect() {
    console.log('[Mock WS] Disconnected');
    this.connected = false;
    this.listeners.clear();
  }

  isConnected(): boolean {
    return this.connected;
  }

  getConnectionState(): 'connecting' | 'connected' | 'disconnected' {
    if (this.connected) return 'connected';
    return 'disconnected';
  }
}

export const mockWsService = new MockWebSocketService();


