import { useEffect, useMemo, useState } from "react";
import PreAttackView from "./components/PreAttackView.jsx";
import LiveAttackFeed from "./components/LiveAttackFeed.jsx";
import PostAttackSummary from "./components/PostAttackSummary.jsx";
import NetworkTimeline from "./components/NetworkTimeline.jsx";
import HoneypotPanel from "./components/HoneypotPanel.jsx";
import { createDefenseSocket } from "./utils/websocket.js";
import { fetchAttackLog } from "./utils/api.js";

const WS_ENABLED = import.meta.env.VITE_DEFENSE_WS_ENABLED === "true";
const ATTACK_LOG_POLL_MS = 4000;

export default function App() {
  const [events, setEvents] = useState([]);
  const [defenseMemory, setDefenseMemory] = useState({});
  const [honeypotTrigger, setHoneypotTrigger] = useState(null);
  const [attackLog, setAttackLog] = useState([]);
  const [wsActive, setWsActive] = useState(false);
  const [wsError, setWsError] = useState(null);

  useEffect(() => {
    if (!WS_ENABLED) {
      setWsActive(false);
      setWsError("websocket-disabled");
      return undefined;
    }

    const socket = createDefenseSocket(
      (payload) => {
        if (!payload || payload.type !== "ATTACK_EVENT") return;
        setEvents((prev) => [...prev.slice(-49), payload]);
        if (payload.defense_memory) {
          setDefenseMemory(payload.defense_memory);
        }
        if (payload.honeypot?.triggered) {
          setHoneypotTrigger({
            step: payload.event?.step,
            endpoint: payload.honeypot?.honeypot,
            timestamp: payload.event?.timestamp,
            payload: payload.event?.action?.payload,
          });
        }
      },
      {
        onOpen: () => {
          setWsActive(true);
          setWsError(null);
        },
        onError: (err) => {
          console.warn("WebSocket bridge unavailable, falling back to attack log polling.", err);
          setWsActive(false);
          setWsError(err?.message ?? "WebSocket unavailable");
        },
      },
    );
    return () => socket?.close();
  }, []);

  useEffect(() => {
    let timer;
    let abortController;

    const loadAttackLog = async () => {
      abortController = new AbortController();
      try {
        const payload = await fetchAttackLog(60, abortController.signal);
        setAttackLog(payload.entries ?? []);
      } catch (err) {
        if (err.name !== "AbortError") {
          console.warn("Failed to load attack log", err);
        }
      } finally {
        timer = setTimeout(loadAttackLog, ATTACK_LOG_POLL_MS);
      }
    };

    loadAttackLog();
    return () => {
      abortController?.abort();
      if (timer) clearTimeout(timer);
    };
  }, []);

  useEffect(() => {
    if (wsActive || events.length || attackLog.length === 0) {
      return;
    }
    // Populate the UI with derived events synthesized from attack_log.json when websockets are unavailable.
    const derived = attackLog.map((entry, idx) => ({
      type: "ATTACK_EVENT",
      event: {
        step: entry.step ?? idx + 1,
        timestamp: entry.timestamp,
        action: {
          action_type: entry.method,
          target_url: entry.endpoint,
          payload: entry.body || entry.query,
        },
      },
      classification: { label: entry.method ?? "HTTP" },
      honeypot: {},
    }));
    setEvents(derived.slice(-50));
  }, [attackLog, wsActive, events.length]);

  const chain = useMemo(
    () =>
      events.map((evt) => ({
        step: evt.event?.step,
        endpoint: evt.event?.action?.target_url,
        classification: evt.classification?.label,
        honeypot: evt.honeypot?.triggered,
      })),
    [events]
  );

  const pulseEvents = events.slice(-3).reverse();

  return (
    <div className="app-shell pb-16">
      <main className="max-w-6xl mx-auto px-4 lg:px-0 space-y-10 relative z-10">
        <header className="hero-heading mt-10 space-y-8">
          <div className="flex flex-wrap items-start justify-between gap-8">
            <div className="space-y-4 max-w-2xl">
              <div className="pill inline-flex gap-2 items-center">
                <span className="w-2.5 h-2.5 rounded-full bg-emerald-300 animate-pulse" /> Live defense posture
              </div>
              <h1 className="text-4xl md:text-5xl font-semibold leading-snug text-white">
                Agents of Shield — <span className="text-accent">Defense Command</span>
              </h1>
              <p className="text-white/70 text-lg">
                Tracking autonomous attacker activity, honeypot engagement, and real-time mitigation signals across the
                sandbox environment.
              </p>
            </div>
            <div className="hero-planet" />
          </div>

          <div className="grid gap-4 md:grid-cols-3">
            <div className="stat-card">
              <h4>Active telemetry</h4>
              <strong>{events.length.toString().padStart(2, "0")}</strong>
              <p className="text-sm text-white/60">events ingested this session</p>
            </div>
            <div className="stat-card">
              <h4>Latest classifiers</h4>
              <strong>{pulseEvents[0]?.classification?.label ?? "—"}</strong>
              <p className="text-sm text-white/60">last detected intent</p>
            </div>
            <div className="stat-card">
              <h4>Honeypot status</h4>
              <strong>{honeypotTrigger ? "TRIPPED" : "ARMED"}</strong>
              <p className="text-sm text-white/60">
                {honeypotTrigger ? `Step ${honeypotTrigger.step}` : "Awaiting intrusion"}
              </p>
              {!WS_ENABLED && (
                <p className="text-[11px] text-white/45 mt-2">
                  WebSocket feed disabled. Showing synthesized data from attack_log.json.
                </p>
              )}
              {wsError && WS_ENABLED && (
                <p className="text-[11px] text-rose-200 mt-2">Live feed unavailable: {wsError}</p>
              )}
            </div>
          </div>
        </header>

        <PreAttackView />

        <div className="grid gap-6 lg:grid-cols-3">
          <div className="lg:col-span-2 space-y-6">
            <LiveAttackFeed events={events} />
            <NetworkTimeline events={events} />
          </div>
          <HoneypotPanel honeypotTrigger={honeypotTrigger} />
        </div>

        <PostAttackSummary events={chain} honeypotTrigger={honeypotTrigger} defenseMemory={defenseMemory} />
      </main>
    </div>
  );
}
