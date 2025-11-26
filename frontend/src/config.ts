/**
 * Application Configuration
 * 
 * Controls feature flags and environment settings.
 * Can be overridden via environment variables.
 */

// Use mock API instead of real API
// Set VITE_USE_MOCK_API=true in .env file or override here
export const USE_MOCK_API = import.meta.env.VITE_USE_MOCK_API === 'true' || false;

// Log configuration on load
console.log(`🔧 Configuration: USE_MOCK_API=${USE_MOCK_API}`);

