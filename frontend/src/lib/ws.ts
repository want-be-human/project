import type { EventPayloadMap } from './events';

type EventHandler<T = any> = (data: T) => void;

class WSClient {
  private listeners: Record<string, EventHandler[]> = {};
  private ws: WebSocket | null = null;
  private reconnectTimer: any = null;

  connect(url: string) {
    if (this.ws) return;

    this.ws = new WebSocket(url);

    this.ws.onmessage = (event) => {
      try {
        const msg = JSON.parse(event.data);
        if (msg.event && this.listeners[msg.event]) {
          this.listeners[msg.event].forEach(cb => cb(msg.data));
        }
      } catch (e) {
        console.error("Failed to parse WS message", e);
      }
    };

    this.ws.onclose = () => {
      this.ws = null;
      // 简单重连逻辑
      this.reconnectTimer = setTimeout(() => this.connect(url), 5000);
    };
  }

  disconnect() {
    if (this.reconnectTimer) clearTimeout(this.reconnectTimer);
    if (this.ws) {
      this.ws.close();
      this.ws = null;
    }
  }

  /** 类型安全的事件订阅（已知事件名自动推导 payload 类型） */
  onEvent<K extends keyof EventPayloadMap>(
    event: K,
    callback: EventHandler<EventPayloadMap[K]>
  ): () => void;
  /** 兜底重载：未知事件名使用 any */
  onEvent(event: string, callback: EventHandler): () => void;
  onEvent(event: string, callback: EventHandler): () => void {
    if (!this.listeners[event]) {
      this.listeners[event] = [];
    }
    this.listeners[event].push(callback);

    // 返回取消订阅函数
    return () => {
      this.listeners[event] = this.listeners[event].filter(cb => cb !== callback);
    };
  }
}

export const wsClient = new WSClient();
