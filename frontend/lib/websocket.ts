export class ProjectWebSocket {
  private ws: WebSocket | null = null;
  private projectId: string;
  private onMessage: (data: Record<string, unknown>) => void;
  private reconnectAttempts = 0;
  private maxReconnects = 5;

  constructor(projectId: string, onMessage: (data: Record<string, unknown>) => void) {
    this.projectId = projectId;
    this.onMessage = onMessage;
  }

  connect() {
    const protocol = typeof window !== 'undefined' && window.location.protocol === 'https:' ? 'wss:' : 'ws:';
    const host = typeof window !== 'undefined' ? window.location.host : 'localhost:3000';
    const token = typeof window !== 'undefined' ? localStorage.getItem('access_token') : '';
    this.ws = new WebSocket(`${protocol}//${host}/ws/projects/${this.projectId}/?token=${token}`);

    this.ws.onopen = () => {
      this.reconnectAttempts = 0;
    };

    this.ws.onmessage = (event) => {
      try {
        const data = JSON.parse(event.data);
        this.onMessage(data);
      } catch (e) {
        console.error('WebSocket parse error:', e);
      }
    };

    this.ws.onclose = () => {
      if (this.reconnectAttempts < this.maxReconnects) {
        this.reconnectAttempts++;
        setTimeout(() => this.connect(), 2000 * this.reconnectAttempts);
      }
    };

    this.ws.onerror = (error) => {
      console.error('WebSocket error:', error);
    };
  }

  send(message: string) {
    if (this.ws?.readyState === WebSocket.OPEN) {
      this.ws.send(JSON.stringify({ message }));
    }
  }

  disconnect() {
    this.maxReconnects = 0;
    this.ws?.close();
  }
}
