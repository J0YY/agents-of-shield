const DEFAULT_ORCHESTRATOR_PORT = import.meta.env.VITE_DEFENSE_PORT || "7700";

function buildWebSocketUrl() {
  const override = import.meta.env.VITE_WS_URL;
  if (override) return override;
  const path = import.meta.env.VITE_WS_PATH || "/ws";
  const base =
    window.location.origin.replace(/^http/, "ws").replace(/:\d+$/, `:${DEFAULT_ORCHESTRATOR_PORT}`);
  return `${base}${path}`;
}

export function createDefenseSocket(onMessage, { onOpen, onError } = {}) {
  const socket = new WebSocket(buildWebSocketUrl());
  socket.onmessage = (event) => {
    try {
      const payload = JSON.parse(event.data);
      onMessage?.(payload);
    } catch (err) {
      console.error("Failed to parse WS payload", err);
    }
  };
  socket.onopen = () => {
    console.info("Dashboard connected to defense orchestrator.");
    onOpen?.();
  };
  socket.onerror = (err) => {
    console.error("WebSocket error", err);
    onError?.(err);
  };
  return socket;
}