/**
 * API Service Factory
 * 
 * Exports the appropriate API service based on configuration.
 * Switches between real API and mock API based on USE_MOCK_API flag.
 */
import { USE_MOCK_API } from '@/config';
import { apiService as realApiService } from './api';
import { mockApiService } from './mockApi';

// Export the appropriate service based on configuration
export const apiService = USE_MOCK_API ? mockApiService : realApiService;

// Log which service is being used
if (USE_MOCK_API) {
  console.log('📦 Using MOCK API service');
} else {
  console.log('🌐 Using REAL API service');
}

