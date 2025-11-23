import { useEffect, useMemo, useState } from "react";
import { fetchHoneypots } from "../utils/api";

const REFRESH_MS = 2000;

function formatTimestamp(value) {
  if (!value) return "—";
  try {
    return new Date(value).toLocaleTimeString([], {
      hour: "2-digit",
      minute: "2-digit",
    });
  } catch {
    return value;
  }
}

export default function HoneypotPanel({ honeypotTrigger }) {
  const [inventory, setInventory] = useState({
    managed: [],
    tpot: { services: [] },
    generated_at: null,
  });
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
  // Normalize TarpetSSH snapshot so we can drop it in once the JSON feed is wired.
  const tarpetSnapshot = useMemo(() => {
    const candidate =
      inventory?.tarpetssh ??
      inventory?.tarpetSSH ??
      inventory?.tarpitssh ??
      inventory?.tarpitSSH ??
      null;
    if (!candidate) {
      return null;
    }
    const sessions = Array.isArray(candidate.sessions)
      ? candidate.sessions
      : Array.isArray(candidate.logs)
      ? candidate.logs
      : Array.isArray(candidate.events)
      ? candidate.events
      : [];
    const metadata = candidate.meta || candidate.metadata || candidate.state || {};
    return {
      raw: candidate,
      sessions,
      metadata,
      error: candidate.error,
      lastUpdated:
        candidate.generated_at ||
        candidate.updated_at ||
        metadata.updated_at ||
        metadata.timestamp ||
        null,
    };
  }, [inventory]);
  const panelStatus = useMemo(() => {
    if (honeypotTrigger) {
      return { label: "Alert", tone: "alert" };
    }
    if (error) {
      return { label: "Degraded", tone: "warn" };
    }
    return {
      label: loading ? "Syncing" : "Ready",
      tone: loading ? "idle" : "ready",
    };
  }, [honeypotTrigger, loading, error]);

  const triggeredHoneypots = useMemo(
    () => managedHoneypots.filter((hp) => hp.status === "triggered"),
    [managedHoneypots]
  );
  const armedHoneypots = useMemo(
    () => managedHoneypots.filter((hp) => hp.status === "armed"),
    [managedHoneypots]
  );
  const [showArmed, setShowArmed] = useState(false);
  const [expandedId, setExpandedId] = useState(null);

  const summary = useMemo(() => {
    const total = managedHoneypots.length || 1;
    const triggered = managedHoneypots.filter(
      (hp) => hp.status === "triggered"
    ).length;
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
          <h2 className="text-xl font-semibold text-white">
            Honeypot readiness
          </h2>
          <p className="text-white/60 text-xs mt-1">
            {inventory?.generated_at
              ? `Updated ${formatTimestamp(inventory.generated_at)}`
              : "Awaiting sync"}
          </p>
        </div>
        <span
          className={`pill text-xs honeypot-status-pill--${panelStatus.tone}`}
        >
          {panelStatus.label}
        </span>
      </div>

      {error ? (
        <p className="text-xs text-rose-200">Inventory unavailable — {error}</p>
      ) : null}

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
        {triggeredHoneypots.length ? (
          triggeredHoneypots.map((item) => {
            const isExpanded = expandedId === item.id;
            const cardStatus = "alert";
            return (
              <article
                key={item.id}
                className={`honeypot-status-card is-alert${
                  isExpanded ? " is-expanded" : ""
                }`}
                style={{ borderColor: "rgba(255,137,164,0.5)" }}
                role="button"
                tabIndex={0}
                onClick={() =>
                  setExpandedId((prev) => (prev === item.id ? null : item.id))
                }
                onKeyPress={(event) => {
                  if (event.key === "Enter" || event.key === " ") {
                    setExpandedId((prev) =>
                      prev === item.id ? null : item.id
                    );
                  }
                }}
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
                <div
                  className={`honeypot-status-chip honeypot-status-chip--${cardStatus}`}
                >
                  {isExpanded ? "Hide log" : "Triggered"}
                </div>
                <div className="honeypot-status-meta">
                  <div>
                    <p className="meta-label">triggered</p>
                    <p className="meta-value">
                      {formatTimestamp(item.last_trigger_at)}
                    </p>
                  </div>
                  <div>
                    <p className="meta-label">step</p>
                    <p className="meta-value">
                      {item.last_trigger_step ?? "—"}
                    </p>
                  </div>
                </div>
                {isExpanded ? (
                  <div className="honeypot-status-details">
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
                    {item.id === "cowrie" && item.cowrie_logs?.length ? (
                      <div className="honeypot-log mt-4">
                        <p className="meta-label">Cowrie activity log</p>
                        <div className="space-y-2 max-h-[400px] overflow-y-auto">
                          {item.cowrie_logs
                            .slice(-30)
                            .reverse()
                            .map((log, idx) => {
                              const eventType =
                                log.eventid
                                  ?.replace("cowrie.", "")
                                  .replace(/\./g, " ") || "Unknown";
                              const isLoginSuccess =
                                log.eventid?.includes("login.success");
                              const isLoginFailed =
                                log.eventid?.includes("login.failed");
                              const isCommand =
                                log.eventid?.includes("command.input");
                              const isConnect =
                                log.eventid?.includes("session.connect");
                              return (
                                <div
                                  key={idx}
                                  className="bg-white/5 rounded p-2 text-xs border border-white/10"
                                >
                                  <div className="flex items-start justify-between gap-2 mb-1">
                                    <span
                                      className={`font-medium ${
                                        isLoginSuccess
                                          ? "text-emerald-400"
                                          : isLoginFailed
                                          ? "text-rose-400"
                                          : isCommand
                                          ? "text-yellow-400"
                                          : isConnect
                                          ? "text-cyan-400"
                                          : "text-white/70"
                                      }`}
                                    >
                                      {eventType}
                                    </span>
                                    {log.timestamp && (
                                      <span className="text-white/40 whitespace-nowrap">
                                        {new Date(
                                          log.timestamp
                                        ).toLocaleTimeString([], {
                                          hour: "2-digit",
                                          minute: "2-digit",
                                          second: "2-digit",
                                        })}
                                      </span>
                                    )}
                                  </div>
                                  {log.message && (
                                    <p className="text-white/80 mb-1">
                                      {log.message}
                                    </p>
                                  )}
                                  {log.input && (
                                    <p className="text-yellow-300 font-mono">
                                      $ {log.input}
                                    </p>
                                  )}
                                  {log.username && (
                                    <p className="text-white/60">
                                      User: {log.username}
                                      {log.password &&
                                        ` (password: ${log.password})`}
                                    </p>
                                  )}
                                  {log.src_ip && (
                                    <p className="text-white/50 font-mono text-[10px] mt-1">
                                      {log.src_ip}
                                    </p>
                                  )}
                                </div>
                              );
                            })}
                        </div>
                      </div>
                    ) : item.id === "cowrie" ? (
                      <p className="text-xs text-white/60 mt-3">
                        No Cowrie logs available yet.
                      </p>
                    ) : null}
                  </div>
                ) : null}
              </article>
            );
          })
        ) : (
          <p className="text-xs text-white/60">
            No honeypots have been tripped yet.
          </p>
        )}
      </div>

      <TarpetSSHPanel
        snapshot={tarpetSnapshot}
        expandedId={expandedId}
        setExpandedId={setExpandedId}
      />

      {armedHoneypots.length ? (
        <div className="honeypot-armed-section">
          <button
            type="button"
            className="honeypot-armed-toggle"
            onClick={() => setShowArmed((prev) => !prev)}
          >
            <span>Armed loadout · {armedHoneypots.length}</span>
            <span
              className={`chevron ${showArmed ? "open" : ""}`}
              aria-hidden="true"
            >
              ▾
            </span>
          </button>
          {showArmed ? (
            <div className="honeypot-status-grid armed-grid">
              {armedHoneypots.map((item) => {
                const isExpanded = expandedId === item.id;
                return (
                  <article
                    key={item.id}
                    className={`honeypot-status-card armed-card${
                      isExpanded ? " is-expanded" : ""
                    }`}
                    role="button"
                    tabIndex={0}
                    onClick={() =>
                      setExpandedId((prev) =>
                        prev === item.id ? null : item.id
                      )
                    }
                    onKeyPress={(event) => {
                      if (event.key === "Enter" || event.key === " ") {
                        setExpandedId((prev) =>
                          prev === item.id ? null : item.id
                        );
                      }
                    }}
                  >
                    <div
                      className="honeypot-status-orb"
                      style={{
                        background: `radial-gradient(circle at 30% 30%, ${item.color}40, rgba(255,255,255,0.02))`,
                      }}
                    >
                      <span>{item.emoji}</span>
                    </div>
                    <div className="honeypot-status-body">
                      <p className="honeypot-label">{item.label}</p>
                      <p className="honeypot-vector">{item.vector}</p>
                    </div>
                    <div className="honeypot-status-meta">
                      <div>
                        <p className="meta-label">armed</p>
                        <p className="meta-value">
                          {formatTimestamp(item.armed_at)}
                        </p>
                      </div>
                      <div>
                        <p className="meta-label">last Δ</p>
                        <p className="meta-value">
                          {item.last_delta != null
                            ? `+${item.last_delta}`
                            : "—"}
                        </p>
                      </div>
                    </div>
                    {isExpanded &&
                    item.id === "cowrie" &&
                    item.cowrie_logs?.length ? (
                      <div className="honeypot-status-details">
                        <div className="honeypot-log mt-4">
                          <p className="meta-label">Cowrie activity log</p>
                          <div className="space-y-2 max-h-[400px] overflow-y-auto">
                            {item.cowrie_logs
                              .slice(-30)
                              .reverse()
                              .map((log, idx) => {
                                const eventType =
                                  log.eventid
                                    ?.replace("cowrie.", "")
                                    .replace(/\./g, " ") || "Unknown";
                                const isLoginSuccess =
                                  log.eventid?.includes("login.success");
                                const isLoginFailed =
                                  log.eventid?.includes("login.failed");
                                const isCommand =
                                  log.eventid?.includes("command.input");
                                const isConnect =
                                  log.eventid?.includes("session.connect");
                                return (
                                  <div
                                    key={idx}
                                    className="bg-white/5 rounded p-2 text-xs border border-white/10"
                                  >
                                    <div className="flex items-start justify-between gap-2 mb-1">
                                      <span
                                        className={`font-medium ${
                                          isLoginSuccess
                                            ? "text-emerald-400"
                                            : isLoginFailed
                                            ? "text-rose-400"
                                            : isCommand
                                            ? "text-yellow-400"
                                            : isConnect
                                            ? "text-cyan-400"
                                            : "text-white/70"
                                        }`}
                                      >
                                        {eventType}
                                      </span>
                                      {log.timestamp && (
                                        <span className="text-white/40 whitespace-nowrap">
                                          {new Date(
                                            log.timestamp
                                          ).toLocaleTimeString([], {
                                            hour: "2-digit",
                                            minute: "2-digit",
                                            second: "2-digit",
                                          })}
                                        </span>
                                      )}
                                    </div>
                                    {log.message && (
                                      <p className="text-white/80 mb-1">
                                        {log.message}
                                      </p>
                                    )}
                                    {log.input && (
                                      <p className="text-yellow-300 font-mono">
                                        $ {log.input}
                                      </p>
                                    )}
                                    {log.username && (
                                      <p className="text-white/60">
                                        User: {log.username}
                                        {log.password &&
                                          ` (password: ${log.password})`}
                                      </p>
                                    )}
                                    {log.src_ip && (
                                      <p className="text-white/50 font-mono text-[10px] mt-1">
                                        {log.src_ip}
                                      </p>
                                    )}
                                  </div>
                                );
                              })}
                          </div>
                        </div>
                      </div>
                    ) : null}
                  </article>
                );
              })}
            </div>
          ) : null}
        </div>
      ) : null}

      <div className="honeypot-secondary-panel">
        <div className="honeypot-secondary-header">
          <div>
            <p className="text-xs text-white/60 uppercase tracking-[0.35em]">
              T-Pot services
            </p>
            <p className="text-white font-semibold text-sm">
              Auxiliary honeypot network
            </p>
          </div>
          <span className="text-xs text-white/45">
            {tpotServices.length} detected
          </span>
        </div>
        {tpotError ? (
          <p className="text-xs text-rose-200 mt-1">{tpotError}</p>
        ) : null}
        <div className="honeypot-service-chips">
          {tpotServices.length ? (
            tpotServices.map((service) => (
              <span key={service.id} className="honeypot-service-chip">
                {service.label}
              </span>
            ))
          ) : (
            <p className="text-xs text-white/50">
              No external honeypots discovered yet.
            </p>
          )}
        </div>
      </div>
    </section>
  );
}

function TarpetSSHPanel({ snapshot, expandedId, setExpandedId }) {
  const sessions = snapshot?.sessions ?? [];
  const metadata = snapshot?.metadata ?? {};
  const raw = snapshot?.raw ?? {};
  const rawServices =
    (Array.isArray(raw.services) && raw.services) ||
    (Array.isArray(metadata.services) && metadata.services) ||
    [];
  const formattedServices = rawServices.map((service) => {
    if (typeof service === "string") return service;
    if (service?.label) return service.label;
    if (service?.name) return service.name;
    if (service?.id) return service.id;
    return "service";
  });
  const serviceSummary = formattedServices.length
    ? formattedServices.slice(0, 3).join(", ") +
      (formattedServices.length > 3 ? ` +${formattedServices.length - 3}` : "")
    : "—";
  const armedValue =
    metadata.armed ?? raw.armed ?? (sessions.length ? "likely" : "—");
  const lastAttacker =
    metadata.last_attacker ??
    metadata.client_ip ??
    metadata.attacker ??
    raw.last_attacker ??
    raw.client_ip ??
    "—";
  const lastUpdated = snapshot?.lastUpdated;
  const statusTone = sessions.length ? "ready" : snapshot ? "idle" : "warn";
  const statusLabel = sessions.length
    ? "Collecting"
    : snapshot
    ? "Standby"
    : "Awaiting feed";

  const formatWithSeconds = (value) => {
    if (!value) return null;
    try {
      return new Date(value).toLocaleTimeString([], {
        hour: "2-digit",
        minute: "2-digit",
        second: "2-digit",
      });
    } catch {
      return value;
    }
  };

  const normalizeEntry = (entry, idx) => {
    if (!entry) {
      return {
        key: `tarpet-empty-${idx}`,
        title: "session",
        message: "—",
      };
    }
    if (typeof entry === "string") {
      return {
        key: `tarpet-str-${idx}-${entry.slice(0, 12)}`,
        title: "session",
        message: entry,
      };
    }
    if (Array.isArray(entry)) {
      return {
        key: `tarpet-arr-${idx}`,
        title: entry[0] || "session",
        message: entry.slice(1).join(" ").trim(),
      };
    }
    const title =
      entry.event ||
      entry.stage ||
      entry.status ||
      entry.type ||
      entry.phase ||
      "session";
    const message =
      entry.message ||
      entry.output ||
      entry.response ||
      entry.detail ||
      entry.text ||
      entry.raw ||
      "";
    const command = entry.command || entry.input || entry.cmd;
    const username = entry.username || entry.user;
    const password = entry.password;
    const ip =
      entry.client_ip ||
      entry.src_ip ||
      entry.remote_ip ||
      entry.attacker ||
      entry.host ||
      entry.ip;
    const timestamp = entry.timestamp || entry.time || entry.ts || entry.at;
    return {
      key: entry.id || entry.uuid || `${timestamp || "tarpet"}-${idx}`,
      title,
      message: message || (command ? "" : JSON.stringify(entry)),
      command,
      username,
      password,
      ip,
      timestamp,
    };
  };

  const renderEntryTone = (title) => {
    if (!title) return "text-white/70";
    const lower = title.toLowerCase();
    if (lower.includes("error") || lower.includes("fail")) {
      return "text-rose-400";
    }
    if (lower.includes("command") || lower.includes("input")) {
      return "text-yellow-400";
    }
    if (lower.includes("vm") || lower.includes("session")) {
      return "text-cyan-400";
    }
    if (lower.includes("connect") || lower.includes("handshake")) {
      return "text-emerald-400";
    }
    return "text-white/70";
  };

  const cardId = "tarpetssh";
  const isExpanded = expandedId === cardId;
  const cardStatus = sessions.length ? "alert" : snapshot ? "idle" : "warn";
  const borderColor = "rgba(255,137,164,0.5)";

  return (
    <article
      className={`honeypot-status-card is-alert tarpet-card${
        isExpanded ? " is-expanded" : ""
      }`}
      style={{ borderColor }}
      role="button"
      tabIndex={0}
      onClick={() =>
        setExpandedId((prev) => (prev === cardId ? null : cardId))
      }
      onKeyPress={(event) => {
        if (event.key === "Enter" || event.key === " ") {
          setExpandedId((prev) => (prev === cardId ? null : cardId));
        }
      }}
    >
      <div
        className="honeypot-status-orb"
        style={{
          background: "radial-gradient(circle at 30% 30%, #ff89a455, rgba(255,255,255,0.05))",
        }}
      >
        <span>🪤</span>
      </div>
      <div className="honeypot-status-body">
        <p className="honeypot-label">TarpetSSH</p>
        <p className="honeypot-method">SSH tarpit mirroring Cowrie log view.</p>
        <p className="honeypot-vector">SSH · VM-backed tarpit</p>
      </div>
      <div
        className={`honeypot-status-chip honeypot-status-chip--${cardStatus}`}
      >
        {isExpanded ? "Hide log" : statusLabel}
      </div>
      <div className="honeypot-status-meta">
        <div>
          <p className="meta-label">updated</p>
          <p className="meta-value">{formatWithSeconds(lastUpdated) ?? "—"}</p>
        </div>
        <div>
          <p className="meta-label">armed</p>
          <p className="meta-value">
            {typeof armedValue === "boolean"
              ? armedValue
                ? "yes"
                : "no"
              : armedValue}
          </p>
        </div>
        <div>
          <p className="meta-label">last attacker</p>
          <p className="meta-value truncate">{lastAttacker}</p>
        </div>
      </div>
      {isExpanded ? (
        <div className="honeypot-status-details">
          {snapshot?.error ? (
            <p className="text-xs text-rose-300 mb-3">{snapshot.error}</p>
          ) : null}
          <div className="grid grid-cols-3 gap-3 text-xs text-white/80 mb-3">
            <div>
              <p className="meta-label">services</p>
              <p className="meta-value">{serviceSummary}</p>
            </div>
            <div>
              <p className="meta-label">sessions</p>
              <p className="meta-value">
                {sessions.length ? sessions.length : "—"}
              </p>
            </div>
            <div>
              <p className="meta-label">status</p>
              <p className="meta-value">{statusLabel}</p>
            </div>
          </div>
          <div className="honeypot-log">
            <p className="meta-label">TarpetSSH activity log</p>
            <div className="space-y-2 max-h-[400px] overflow-y-auto mt-3">
              {sessions.length ? (
                sessions
                  .slice(-30)
                  .reverse()
                  .map((entry, idx) => {
                    const normalized = normalizeEntry(entry, idx);
                    return (
                      <div
                        key={normalized.key}
                        className="bg-white/5 rounded p-2 text-xs border border-white/10"
                      >
                        <div className="flex items-start justify-between gap-2 mb-1">
                          <span
                            className={`font-medium ${renderEntryTone(
                              normalized.title
                            )}`}
                          >
                            {normalized.title}
                          </span>
                          {normalized.timestamp && (
                            <span className="text-white/40 whitespace-nowrap">
                              {formatWithSeconds(normalized.timestamp)}
                            </span>
                          )}
                        </div>
                        {normalized.message && (
                          <p className="text-white/80 mb-1 whitespace-pre-wrap">
                            {normalized.message}
                          </p>
                        )}
                        {normalized.command && (
                          <p className="text-yellow-300 font-mono break-all">
                            $ {normalized.command}
                          </p>
                        )}
                        {normalized.username && (
                          <p className="text-white/60 mt-1">
                            User: {normalized.username}
                            {normalized.password
                              ? ` (password: ${normalized.password})`
                              : ""}
                          </p>
                        )}
                        {normalized.ip && (
                          <p className="text-white/50 font-mono text-[10px] mt-1">
                            {normalized.ip}
                          </p>
                        )}
                      </div>
                    );
                  })
              ) : (
                <p className="text-xs text-white/60 italic">
                  TarpetSSH telemetry will appear here once the JSON stream is
                  wired up.
                </p>
              )}
            </div>
          </div>
        </div>
      ) : null}
    </article>
  );
}
