import { Fragment, useMemo } from "react";

const QUEUE_COLUMNS = ["Monitoring", "Responding", "Resolved"];

function buildOps(events) {
  return events.slice(-8).map((evt) => {
    const status = evt.honeypot?.triggered
      ? "Responding"
      : evt.classification?.label
      ? "Monitoring"
      : "Monitoring";
    return {
      id: `${evt.event?.step}-${evt.event?.timestamp}`,
      title: evt.classification?.label || evt.event?.action?.action_type || "Event",
      detail: evt.event?.action?.target_url || evt.event?.response_summary || "",
      status,
    };
  });
}

function buildSignals(events) {
  const recent = events.slice(-10);
  const velocity = recent.length;
  const honeypotTrips = recent.filter((evt) => evt.honeypot?.triggered).length;
  const systemEvents = recent.filter((evt) => (evt.event?.action?.action_type || "").includes("SYSTEM")).length;
  const classifierScores = recent
    .map((evt) => evt.payload?.payload_risk_score ?? evt.event?.status ?? 0)
    .filter((value) => typeof value === "number");
  const risk =
    classifierScores.length > 0 ? Math.round(classifierScores.reduce((a, b) => a + b, 0) / classifierScores.length) : 0;

  return [
    { label: "Events/5s", value: velocity, trend: generateTrend(velocity) },
    { label: "Honeypot trips", value: honeypotTrips, trend: generateTrend(honeypotTrips) },
    { label: "System probes", value: systemEvents, trend: generateTrend(systemEvents) },
    { label: "Avg risk", value: risk, trend: generateTrend(risk) },
  ];
}

function generateTrend(seed) {
  const points = [];
  for (let idx = 0; idx < 12; idx += 1) {
    points.push(Math.max(0, (Math.sin(idx / 1.8 + seed) + 1) * 50));
  }
  return points;
}

function Sparkline({ data }) {
  const path = data
    .map((value, idx) => `${idx === 0 ? "M" : "L"}${(idx / (data.length - 1)) * 100},${100 - value}`)
    .join(" ");
  return (
    <svg viewBox="0 0 100 100" preserveAspectRatio="none" className="sparkline">
      <path d={path} />
    </svg>
  );
}

export default function NetworkTimeline({ events }) {
  const ops = useMemo(() => buildOps(events), [events]);
  const signals = useMemo(() => buildSignals(events), [events]);
  const grouped = useMemo(() => {
    return QUEUE_COLUMNS.map((column) => ({
      title: column,
      items: ops.filter((item) => item.status === column),
    }));
  }, [ops]);

  return (
    <div className="space-y-6">
      <section className="glass-panel">
        <div className="flex items-center justify-between mb-4">
          <h2 className="text-xl font-semibold text-white">Active defense ops</h2>
          <span className="text-xs uppercase tracking-[0.3em] text-white/60">Orchestrator status</span>
        </div>
        <div className="grid gap-4 md:grid-cols-3">
          {grouped.map((column) => (
            <div key={column.title} className="ops-column">
              <header>
                <h3>{column.title}</h3>
                <span>{column.items.length}</span>
              </header>
              <div className="ops-list">
                {column.items.length ? (
                  column.items.map((item) => (
                    <article key={item.id} className="ops-card">
                      <p className="ops-title">{item.title}</p>
                      <p className="ops-detail">{item.detail}</p>
                    </article>
                  ))
                ) : (
                  <p className="ops-empty">No tasks</p>
                )}
              </div>
            </div>
          ))}
        </div>
      </section>

      <section className="glass-panel">
        <div className="flex items-center justify-between mb-4">
          <h2 className="text-xl font-semibold text-white">Signal heatmap</h2>
          <span className="text-xs uppercase tracking-[0.3em] text-white/60">Health snapshot</span>
        </div>
        <div className="grid gap-4 md:grid-cols-4">
          {signals.map((signal) => (
            <article key={signal.label} className="signal-card">
              <div>
                <p className="signal-label">{signal.label}</p>
                <p className="signal-value">{signal.value}</p>
              </div>
              <Sparkline data={signal.trend} />
            </article>
          ))}
        </div>
      </section>
    </div>
  );
}

