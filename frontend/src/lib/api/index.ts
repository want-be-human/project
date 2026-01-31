// Export types
export * from './types';

import { mockApi } from './mock';
import { realApi } from './real';
import { API_MODE_TYPE } from './types';

// Determine mode from environment variable
const mode: API_MODE_TYPE = (process.env.NEXT_PUBLIC_API_MODE as API_MODE_TYPE) || 'mock';

// Export the API client
export const api = mode === 'real' ? realApi : mockApi;

// Helper to check mode
export const isMock = () => mode === 'mock';
