/**
 * WebSocket Service Factory
 * 
 * Exports the appropriate WebSocket service based on configuration.
 * Switches between real WebSocket and mock WebSocket based on USE_MOCK_API flag.
 */
import { USE_MOCK_API } from '@/config';
import { wsService as realWsService } from './websocket';
import { mockWsService } from './mockWebSocket';

// Export the appropriate service based on configuration
export const wsService = USE_MOCK_API ? mockWsService : realWsService;

// Log which service is being used
if (USE_MOCK_API) {
  console.log('📦 Using MOCK WebSocket service');
} else {
  console.log('🌐 Using REAL WebSocket service');
}

