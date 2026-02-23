type EventHandler = (data: any) => void;

class WSClient {
  private listeners: Record<string, EventHandler[]> = {};
  private ws: WebSocket | null = null;
  private reconnectTimer: any = null;

  constructor() {
    // In a real app, we'd connect here if mode === 'real'
    // For mock mode, we just provide the pub/sub interface
  }

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
      // Simple reconnect logic
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

  onEvent(event: string, callback: EventHandler) {
    if (!this.listeners[event]) {
      this.listeners[event] = [];
    }
    this.listeners[event].push(callback);

    // Return unsubscribe function
    return () => {
      this.listeners[event] = this.listeners[event].filter(cb => cb !== callback);
    };
  }

  // Helper for mock mode to trigger events manually
  simulateEvent(event: string, data: any) {
    if (this.listeners[event]) {
      this.listeners[event].forEach(cb => cb(data));
    }
  }
}

export const wsClient = new WSClient();
