import { useEffect, useMemo, useState } from "react";
import { fetchHoneypots } from "../utils/api";

const REFRESH_MS = 20000;

function formatTimestamp(value) {
  if (!value) return "—";
  try {
    return new Date(value).toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" });
  } catch {
    return value;
  }
}

export default function HoneypotPanel({ honeypotTrigger }) {
  const [inventory, setInventory] = useState({ managed: [], tpot: { services: [] }, generated_at: null });
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);

  useEffect(() => {
    let timer;
    const controller = new AbortController();

    const load = async () => {
      try {
        const payload = await fetchHoneypots(controller.signal);
        setInventory(payload ?? { managed: [], tpot: { services: [] } });
        setError(null);
      } catch (err) {
        if (err.name === "AbortError") {
          return;
        }
        setError(err.message || "Unable to load honeypot inventory");
      } finally {
        setLoading(false);
        timer = window.setTimeout(load, REFRESH_MS);
      }
    };

    load();
    return () => {
      controller.abort();
      if (timer) window.clearTimeout(timer);
    };
  }, []);

  const managedHoneypots = inventory?.managed ?? [];
  const tpotServices = inventory?.tpot?.services ?? [];
  const tpotError = inventory?.tpot?.error;
  const panelStatus = useMemo(() => {
    if (honeypotTrigger) {
      return { label: "Alert", tone: "alert" };
    }
    if (error) {
      return { label: "Degraded", tone: "warn" };
    }
    return { label: loading ? "Syncing" : "Ready", tone: loading ? "idle" : "ready" };
  }, [honeypotTrigger, loading, error]);

  const deployedHoneypots = useMemo(() => managedHoneypots.filter((hp) => hp.status !== "idle"), [managedHoneypots]);

  const summary = useMemo(() => {
    const total = managedHoneypots.length || 1;
    const triggered = managedHoneypots.filter((hp) => hp.status === "triggered").length;
    const armed = managedHoneypots.filter((hp) => hp.status === "armed").length;
    const idle = total - triggered - armed;
    return [
      { label: "Triggered", value: triggered, color: "#ff89a4" },
      { label: "Armed", value: armed, color: "#82f5ff" },
      { label: "Idle", value: idle, color: "#9da1ff" },
    ].map((slice) => ({
      ...slice,
      percent: Math.round((slice.value / total) * 100),
    }));
  }, [managedHoneypots]);

  return (
    <section className="glass-panel h-full honeypot-status-panel">
      <div className="honeypot-panel-header">
        <div>
          <h2 className="text-xl font-semibold text-white">Honeypot readiness</h2>
          <p className="text-white/60 text-xs mt-1">
            {inventory?.generated_at ? `Updated ${formatTimestamp(inventory.generated_at)}` : "Awaiting sync"}
          </p>
        </div>
        <span className={`pill text-xs honeypot-status-pill--${panelStatus.tone}`}>{panelStatus.label}</span>
      </div>

      {error ? <p className="text-xs text-rose-200">Inventory unavailable — {error}</p> : null}

      <div className="honeypot-rings-row">
        {summary.map((slice) => (
          <div key={slice.label} className="honeypot-ring-card">
            <div
              className="honeypot-ring"
              style={{
                background: `conic-gradient(${slice.color} ${slice.percent}%, rgba(255,255,255,0.12) 0)`,
              }}
            >
              <div className="honeypot-ring-core">
                <strong>{slice.value.toString().padStart(2, "0")}</strong>
                <p>{slice.label}</p>
              </div>
            </div>
            <span className="honeypot-ring-percent">{slice.percent}%</span>
          </div>
        ))}
        <div className="honeypot-ring-card">
          <div className="honeypot-ring honeypot-ring--pulse">
            <div className="honeypot-ring-core">
              <strong>{tpotServices.length.toString().padStart(2, "0")}</strong>
              <p>T-Pot</p>
            </div>
          </div>
          <span className="honeypot-ring-percent">external</span>
        </div>
      </div>

      <div className="honeypot-status-grid">
        {deployedHoneypots.length ? (
          deployedHoneypots.map((item) => {
          const triggered = honeypotTrigger?.endpoint === item.id;
          const statusLabel = triggered ? "Triggered" : item.status?.toUpperCase() ?? "IDLE";
          return (
            <article
              key={item.id}
              className={`honeypot-status-card${triggered ? " is-alert" : ""}`}
              style={{ borderColor: triggered ? "rgba(255,137,164,0.5)" : "rgba(255,255,255,0.08)" }}
            >
              <div
                className="honeypot-status-orb"
                style={{
                  background: `radial-gradient(circle at 30% 30%, ${item.color}55, rgba(255,255,255,0.05))`,
                }}
              >
                <span>{item.emoji}</span>
              </div>
              <div className="honeypot-status-body">
                <p className="honeypot-label">{item.label}</p>
                <p className="honeypot-method">{item.method}</p>
                <p className="honeypot-vector">{item.vector}</p>
              </div>
              <div className={`honeypot-status-chip honeypot-status-chip--${triggered ? "alert" : item.status}`}>
                {statusLabel}
              </div>
              <div className="honeypot-status-meta">
                <div>
                  <p className="meta-label">armed</p>
                  <p className="meta-value">{formatTimestamp(item.armed_at)}</p>
                </div>
                <div>
                  <p className="meta-label">last Δ</p>
                  <p className="meta-value">{item.last_delta != null ? `+${item.last_delta}` : "—"}</p>
                </div>
              </div>
              {triggered && honeypotTrigger?.payload ? (
                <pre className="honeypot-status-payload">
                  {JSON.stringify(honeypotTrigger.payload, null, 2)}
                </pre>
              ) : null}
              {item.recent_commands?.length ? (
                <div className="honeypot-log">
                  <p className="meta-label">ssh log</p>
                  <ul>
                    {item.recent_commands.map((cmd) => (
                      <li key={cmd}>{cmd}</li>
                    ))}
                  </ul>
                </div>
              ) : null}
            </article>
          );
        })
        ) : (
          <p className="text-xs text-white/60">No honeypots armed yet — deploy a loadout to populate this view.</p>
        )}
      </div>

      <div className="honeypot-secondary-panel">
        <div className="honeypot-secondary-header">
          <div>
            <p className="text-xs text-white/60 uppercase tracking-[0.35em]">T-Pot services</p>
            <p className="text-white font-semibold text-sm">Auxiliary honeypot network</p>
          </div>
          <span className="text-xs text-white/45">{tpotServices.length} detected</span>
        </div>
        {tpotError ? <p className="text-xs text-rose-200 mt-1">{tpotError}</p> : null}
        <div className="honeypot-service-chips">
          {tpotServices.length ? (
            tpotServices.map((service) => (
              <span key={service.id} className="honeypot-service-chip">
                {service.label}
              </span>
            ))
          ) : (
            <p className="text-xs text-white/50">No external honeypots discovered yet.</p>
          )}
        </div>
      </div>
    </section>
  );
}

