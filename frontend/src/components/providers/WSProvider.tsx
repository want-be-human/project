'use client';

import { useEffect } from 'react';
import { wsClient } from '@/lib/ws';

/**
 * 初始化 WebSocket 连接，订阅后端实时事件流。
 */
export default function WSProvider({ children }: { children: React.ReactNode }) {
  useEffect(() => {
    const wsBase = process.env.NEXT_PUBLIC_WS_URL
      || process.env.NEXT_PUBLIC_API_BASE_URL?.replace(/^http/, 'ws')
      || 'ws://localhost:8000';
    wsClient.connect(`${wsBase}/api/v1/stream`);
    return () => {
      wsClient.disconnect();
    };
  }, []);

  return <>{children}</>;
}
