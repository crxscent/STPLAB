// CryptoMonitor Stream backend (FastAPI). On a real device set EXPO_PUBLIC_API_URL
// to your machine's LAN address, e.g. http://192.168.1.10:8000
export const API_URL = (process.env.EXPO_PUBLIC_API_URL || 'http://localhost:8000').replace(/\/$/, '');
export const WS_URL = API_URL.replace(/^http/, 'ws') + '/ws/alerts';

async function get(path) {
  const res = await fetch(API_URL + path);
  if (!res.ok) throw new Error(`API ${res.status}`);
  return res.json();
}

export const fetchAlerts = (limit = 50) => get(`/api/alerts?limit=${limit}`);
export const fetchStats = () => get('/api/stats');

// Subscribes to live anomalies; reconnects automatically. Returns an unsubscribe fn.
export function subscribeAlerts(onAlert, onStatus) {
  let ws;
  let closed = false;
  let timer;
  const connect = () => {
    ws = new WebSocket(WS_URL);
    ws.onopen = () => onStatus && onStatus(true);
    ws.onmessage = (e) => {
      try {
        const msg = JSON.parse(e.data);
        if (msg.type === 'anomaly') onAlert(msg.data);
      } catch {}
    };
    ws.onclose = () => {
      onStatus && onStatus(false);
      if (!closed) timer = setTimeout(connect, 3000);
    };
    ws.onerror = () => ws.close();
  };
  connect();
  return () => {
    closed = true;
    clearTimeout(timer);
    ws && ws.close();
  };
}
