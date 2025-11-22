export function createDefenseSocket(onMessage) {
  const wsUrl = import.meta.env.VITE_WS_URL || "ws://localhost:7000/ws";
  const socket = new WebSocket(wsUrl);
  socket.onmessage = (event) => {
    try {
      const payload = JSON.parse(event.data);
      onMessage?.(payload);
    } catch (err) {
      console.error("Failed to parse WS payload", err);
    }
  };
  socket.onopen = () => console.info("Dashboard connected to defense orchestrator.");
  socket.onerror = (err) => console.error("WebSocket error", err);
  return socket;
}

