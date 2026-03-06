'use client';

import { useEffect } from 'react';
import { wsClient } from '@/lib/ws';
import { isMock } from '@/lib/api';

/**
 * Initializes WebSocket connection in real mode.
 * In mock mode, wsClient.simulateEvent() is used instead.
 */
export default function WSProvider({ children }: { children: React.ReactNode }) {
  useEffect(() => {
    if (!isMock()) {
      const wsBase = process.env.NEXT_PUBLIC_WS_URL
        || process.env.NEXT_PUBLIC_API_BASE_URL?.replace(/^http/, 'ws')
        || 'ws://localhost:8000';
      wsClient.connect(`${wsBase}/api/v1/ws`);
    }
    return () => {
      wsClient.disconnect();
    };
  }, []);

  return <>{children}</>;
}
