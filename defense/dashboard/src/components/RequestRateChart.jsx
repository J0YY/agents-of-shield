import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { armHoneypots, fetchAttackLog } from "../utils/api";

const DEFAULT_BUCKET_SECONDS = 4;
const DEFAULT_SAMPLE_POINTS = 20;
const DEFAULT_POLL_MS = 4000;
const ATTACK_LOG_LIMIT = 200;
const DEFAULT_SPIKE_THRESHOLD = 8;
const GRID_STEPS = 4;
const CHART_HEIGHT = 100;
const PADDING_TOP = 12;
const PADDING_BOTTOM = 2;
const INNER_HEIGHT = CHART_HEIGHT - PADDING_TOP - PADDING_BOTTOM;
const MAX_TERMINAL_LOGS = 30;
const TERMINAL_TIME_FORMAT = { hour: "2-digit", minute: "2-digit", second: "2-digit" };
const MIN_TERMINAL_WIDTH = 520;
const MAX_TERMINAL_WIDTH = 1400;
const MIN_TERMINAL_HEIGHT = 280;
const MAX_TERMINAL_HEIGHT = 900;
const DEFAULT_EXPANDED_WIDTH = 720;
const DEFAULT_EXPANDED_HEIGHT = 360;

function clamp(value, min, max) {
  return Math.min(Math.max(value, min), max);
}

function createTerminalLog(message, level = "info", timestamp = Date.now()) {
  let date;
  try {
    date = timestamp ? new Date(timestamp) : new Date();
    if (Number.isNaN(date.getTime())) {
      date = new Date();
    }
  } catch {
    date = new Date();
  }

  return {
    id: `${Date.now()}-${Math.random().toString(16).slice(2, 7)}`,
    timestamp: date.toLocaleTimeString([], TERMINAL_TIME_FORMAT),
    level,
    message,
  };
}

function buildSeries(entries, bucketSeconds, samplePoints) {
  const bucketMs = bucketSeconds * 1000;
  const now = Date.now();
  const latestBucket = Math.floor(now / bucketMs) * bucketMs;
  const earliestBucket = latestBucket - (samplePoints - 1) * bucketMs;
  const counts = new Map();

  entries.forEach((entry) => {
    const ts = Date.parse(entry.timestamp ?? entry.time ?? entry.ts);
    if (Number.isNaN(ts) || ts < earliestBucket) {
      return;
    }
    const bucket = Math.floor(ts / bucketMs) * bucketMs;
    counts.set(bucket, (counts.get(bucket) ?? 0) + 1);
  });

  const series = [];
  for (let bucket = earliestBucket; bucket <= latestBucket; bucket += bucketMs) {
    series.push({ timestamp: bucket, count: counts.get(bucket) ?? 0 });
  }
  return series;
}

function formatTimestamp(ts) {
  return new Date(ts).toLocaleTimeString([], { hour: "2-digit", minute: "2-digit", second: "2-digit" });
}

export default function RequestRateChart({
  bucketSeconds = DEFAULT_BUCKET_SECONDS,
  samplePoints = DEFAULT_SAMPLE_POINTS,
  pollMs = DEFAULT_POLL_MS,
  spikeThreshold = DEFAULT_SPIKE_THRESHOLD,
  defenseLogs = [],
}) {
  const [series, setSeries] = useState(() => buildSeries([], bucketSeconds, samplePoints));
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);
  const [spikeAlert, setSpikeAlert] = useState(null);
  const lastAlertBucketRef = useRef(null);
  const terminalBodyRef = useRef(null);
  const terminalCardRef = useRef(null);
  const [terminalLogs, setTerminalLogs] = useState(() => [
    createTerminalLog("Network sentinel idle — awaiting anomalies.", "idle"),
  ]);
  const [terminalExpanded, setTerminalExpanded] = useState(false);
  const [terminalDimensions, setTerminalDimensions] = useState({
    width: DEFAULT_EXPANDED_WIDTH,
    height: DEFAULT_EXPANDED_HEIGHT,
  });
  const [activeResize, setActiveResize] = useState(null);
  const defenseLogIndexRef = useRef(0);
  const chartCeiling = useMemo(() => {
    let peak = 0;
    series.forEach((point) => {
      if (point.count > peak) peak = point.count;
    });
    const safe = Math.max(5, peak);
    const remainder = safe % 5;
    return remainder === 0 ? safe : safe + (5 - remainder);
  }, [series]);
  const yAxisTicks = useMemo(() => {
    return Array.from({ length: GRID_STEPS + 1 }, (_, idx) => {
      const ratio = idx / GRID_STEPS;
      const isBottom = idx === GRID_STEPS;
      const value = isBottom ? 0 : Math.max(0, Math.round(chartCeiling * (1 - ratio)));
      const lineY = PADDING_TOP + ratio * INNER_HEIGHT;
      const topPercent = (lineY / CHART_HEIGHT) * 100;
      return {
        value,
        key: `${idx}-${chartCeiling}`,
        topPercent,
        isBottom,
      };
    });
  }, [chartCeiling]);

  useEffect(() => {
    let timer;
    let abortController;

    const load = async () => {
      abortController?.abort();
      abortController = new AbortController();
      try {
        const payload = await fetchAttackLog(ATTACK_LOG_LIMIT, abortController.signal);
        const entries = payload?.entries ?? [];
        setSeries(buildSeries(entries, bucketSeconds, samplePoints));
        setError(null);
      } catch (err) {
        if (err.name !== "AbortError") {
          setError(err.message || "Unable to read attack log");
        }
      } finally {
        setLoading(false);
        timer = window.setTimeout(load, pollMs);
      }
    };

    load();
    return () => {
      abortController?.abort();
      if (timer) {
        window.clearTimeout(timer);
      }
    };
  }, [bucketSeconds, samplePoints, pollMs]);

  useEffect(() => {
    if (series.length < 2) {
      return;
    }
    const last = series[series.length - 1];
    const prev = series[series.length - 2];
    const delta = last.count - prev.count;
    if (delta >= spikeThreshold && lastAlertBucketRef.current !== last.timestamp) {
      lastAlertBucketRef.current = last.timestamp;
      setSpikeAlert({
        delta,
        current: last.count,
        timestamp: last.timestamp,
      });
    }
  }, [series, spikeThreshold]);

  useEffect(() => {
    if (!spikeAlert) {
      return undefined;
    }
    const timer = window.setTimeout(() => setSpikeAlert(null), 6500);
    return () => window.clearTimeout(timer);
  }, [spikeAlert]);

  const stats = useMemo(() => {
    if (!series.length) {
      return { current: 0, peak: 0, avg: 0 };
    }
    const counts = series.map((point) => point.count);
    const sum = counts.reduce((acc, value) => acc + value, 0);
    return {
      current: counts[counts.length - 1],
      peak: Math.max(...counts),
      avg: sum / counts.length,
    };
  }, [series]);

  const { linePath, areaPath, coordinates } = useMemo(() => {
    if (!series.length) {
      return { linePath: "", areaPath: "", coordinates: [] };
    }
    const chartWidth = 100;
    const coords = series.map((point, idx) => {
      const x =
        series.length === 1 ? chartWidth : (idx / (series.length - 1 || 1)) * chartWidth;
      const y =
        CHART_HEIGHT - PADDING_BOTTOM - (point.count / Math.max(chartCeiling, 1)) * INNER_HEIGHT;
      return { ...point, x: Number(x.toFixed(2)), y: Number(y.toFixed(2)) };
    });
    const line = coords.reduce(
      (acc, point, idx) => `${acc}${idx === 0 ? "M" : "L"}${point.x},${point.y}`,
      "",
    );
    const lastPoint = coords[coords.length - 1];
    const firstPoint = coords[0];
    const baselineY = CHART_HEIGHT - PADDING_BOTTOM;
    const area = `${line} L${lastPoint.x},${baselineY} L${firstPoint.x},${baselineY} Z`;
    return { linePath: line, areaPath: area, coordinates: coords };
  }, [series, chartCeiling]);

  const tickLabels = useMemo(() => {
    if (!series.length) {
      return [];
    }
    const indexSet = new Set([0, Math.floor(series.length / 2), series.length - 1]);
    return Array.from(indexSet).map((idx) => ({
      label: formatTimestamp(series[idx].timestamp),
      key: series[idx].timestamp,
      align: idx === 0 ? "start" : idx === series.length - 1 ? "end" : "center",
    }));
  }, [series]);

  const pushTerminalLog = useCallback((message, level = "info", timestamp = Date.now()) => {
    setTerminalLogs((prev) => {
      const entry = createTerminalLog(message, level, timestamp);
      const next = [...prev, entry];
      return next.length > MAX_TERMINAL_LOGS ? next.slice(next.length - MAX_TERMINAL_LOGS) : next;
    });
  }, []);

  const handleTerminalToggle = useCallback(() => {
    setTerminalExpanded((prev) => {
      if (!prev && typeof window !== "undefined") {
        const desiredWidth = clamp(
          Math.min(window.innerWidth - 180, DEFAULT_EXPANDED_WIDTH),
          MIN_TERMINAL_WIDTH,
          MAX_TERMINAL_WIDTH,
        );
        const desiredHeight = clamp(
          Math.min(window.innerHeight - 260, DEFAULT_EXPANDED_HEIGHT),
          MIN_TERMINAL_HEIGHT,
          MAX_TERMINAL_HEIGHT,
        );
        setTerminalDimensions({
          width: desiredWidth,
          height: desiredHeight,
        });
      }
      return !prev;
    });
  }, []);

  const handleResizeStart = useCallback(
    (direction) => (event) => {
      if (!terminalExpanded) return;
      event.preventDefault();
      event.stopPropagation();
      setActiveResize({
        direction,
        startX: event.clientX,
        startY: event.clientY,
        startWidth: terminalDimensions.width,
        startHeight: terminalDimensions.height,
      });
    },
    [terminalExpanded, terminalDimensions],
  );

  useEffect(() => {
    const bodyEl = terminalBodyRef.current;
    if (bodyEl) {
      bodyEl.scrollTop = bodyEl.scrollHeight;
    }
  }, [terminalLogs]);

  useEffect(() => {
    if (!defenseLogs?.length) {
      return;
    }
    const nextLogs = defenseLogs.slice(defenseLogIndexRef.current);
    nextLogs.forEach((log) => {
      pushTerminalLog(log.message, log.level || "info", log.timestamp);
    });
    defenseLogIndexRef.current = defenseLogs.length;
  }, [defenseLogs, pushTerminalLog]);

  useEffect(() => {
    if (!terminalExpanded || typeof document === "undefined") {
      return undefined;
    }
    const previousOverflow = document.body.style.overflow;
    document.body.style.overflow = "hidden";
    return () => {
      document.body.style.overflow = previousOverflow;
    };
  }, [terminalExpanded]);

  useEffect(() => {
    if (!terminalExpanded || typeof window === "undefined") {
      return undefined;
    }
    const handleKeyDown = (event) => {
      if (event.key === "Escape") {
        setTerminalExpanded(false);
      }
    };
    window.addEventListener("keydown", handleKeyDown);
    return () => window.removeEventListener("keydown", handleKeyDown);
  }, [terminalExpanded]);

  useEffect(() => {
    if (!activeResize) {
      return undefined;
    }
    const handleMove = (event) => {
      setTerminalDimensions(() => {
        const deltaX = event.clientX - activeResize.startX;
        const deltaY = event.clientY - activeResize.startY;
        let width = activeResize.startWidth;
        let height = activeResize.startHeight;

        if (activeResize.direction.includes("east")) {
          width = clamp(activeResize.startWidth + deltaX, MIN_TERMINAL_WIDTH, MAX_TERMINAL_WIDTH);
        }
        if (activeResize.direction.includes("west")) {
          width = clamp(activeResize.startWidth - deltaX, MIN_TERMINAL_WIDTH, MAX_TERMINAL_WIDTH);
        }
        if (activeResize.direction.includes("south")) {
          height = clamp(activeResize.startHeight + deltaY, MIN_TERMINAL_HEIGHT, MAX_TERMINAL_HEIGHT);
        }
        if (activeResize.direction.includes("north")) {
          height = clamp(activeResize.startHeight - deltaY, MIN_TERMINAL_HEIGHT, MAX_TERMINAL_HEIGHT);
        }

        return { width, height };
      });
    };
    const stop = () => setActiveResize(null);
    window.addEventListener("pointermove", handleMove);
    window.addEventListener("pointerup", stop);
    return () => {
      window.removeEventListener("pointermove", handleMove);
      window.removeEventListener("pointerup", stop);
    };
  }, [activeResize]);

  useEffect(() => {
    if (!spikeAlert) {
      return undefined;
    }
    pushTerminalLog(
      `Suspicious velocity detected: Δ +${spikeAlert.delta} requests.`,
      "warn",
      spikeAlert.timestamp,
    );
    pushTerminalLog("Dispatching defense orchestrator to arm honeypots...", "info");

    const controller = new AbortController();
    armHoneypots(
      {
        reason: "traffic_spike",
        delta: spikeAlert.delta,
        bucket: spikeAlert.timestamp,
        source: "request_rate_chart",
      },
      controller.signal,
    )
      .then((response) => {
        const records = Array.isArray(response?.honeypots) ? response.honeypots : [];
        if (!records.length) {
          pushTerminalLog("Honeypots armed.", "success");
          return;
        }
        records.forEach((hp) => {
          pushTerminalLog(
            `Armed ${hp.label ?? hp.endpoint} — ${hp.description ?? "decoy route"}.`,
            "success",
            spikeAlert.timestamp,
          );
        });
      })
      .catch((err) => {
        if (err?.name === "AbortError") {
          return;
        }
        pushTerminalLog(`Honeypot orchestration failed — ${err?.message || "unknown error"}.`, "error");
      });

    return () => controller.abort();
  }, [spikeAlert, pushTerminalLog]);

  return (
    <>
    <section className="request-chart-panel">
      <div className="request-chart-header">
        <div>
          <p className="chart-pill">Request velocity</p>
          <h3>Requests per {bucketSeconds}s window</h3>
          <p className="chart-subtitle">
            Tracking last {samplePoints} intervals (~{Math.round((samplePoints * bucketSeconds) / 6) / 10} min)
          </p>
        </div>
        <div className="request-chart-metrics">
          <div>
            <p>Current</p>
            <strong>{stats.current}</strong>
          </div>
          <div>
            <p>Peak</p>
            <strong>{stats.peak}</strong>
          </div>
          <div>
            <p>Avg</p>
            <strong>{stats.avg.toFixed(1)}</strong>
          </div>
        </div>
      </div>

      <div className="request-chart-canvas">
        <div className="request-chart-axis">
          {yAxisTicks.map((tick) => (
            <span
              key={tick.key}
              className={`request-chart-axis-label${tick.isBottom ? " request-chart-axis-label--bottom" : ""}`}
              style={{ top: `${tick.topPercent}%` }}
            >
              {tick.value}
            </span>
          ))}
        </div>
        <div className="request-chart-plot">
          <svg viewBox="0 0 100 100" preserveAspectRatio="none" role="img" aria-label="Requests per interval trend">
            {Array.from({ length: GRID_STEPS + 1 }, (_, row) => {
              const lineY = PADDING_TOP + (row / GRID_STEPS) * INNER_HEIGHT;
              const pos = (lineY / CHART_HEIGHT) * 100;
              return (
                <line
                  key={`grid-${row}`}
                  x1="0"
                  x2="100"
                  y1={pos}
                  y2={pos}
                  className="request-chart-grid-line"
                />
              );
            })}
            {areaPath ? <path d={areaPath} className="request-chart-area" /> : null}
            {linePath ? <path d={linePath} className="request-chart-line" /> : null}
            {coordinates.map((point) => (
              <circle key={point.timestamp} cx={point.x} cy={point.y} r="1.2" className="request-chart-dot" />
            ))}
          </svg>
        </div>
      </div>

      <div className="request-chart-labels">
        {tickLabels.map((tick) => (
          <span key={tick.key} className={`request-chart-label request-chart-label--${tick.align}`}>
            {tick.label}
          </span>
        ))}
      </div>

      {loading && (
        <p className="chart-hint text-white/60 text-sm mt-4">Booting telemetry window...</p>
      )}
      {error && (
        <p className="chart-error text-rose-200 text-sm mt-2">Request graph offline — {error}</p>
      )}

      {spikeAlert ? (
        <div className="chart-alert" role="alert">
          <div>
            <p className="chart-alert-title">Traffic spike detected</p>
            <p className="chart-alert-body">
              Δ +{spikeAlert.delta} requests vs previous bucket ({formatTimestamp(spikeAlert.timestamp)}).
            </p>
          </div>
          <button type="button" className="chart-alert-dismiss" onClick={() => setSpikeAlert(null)}>
            Dismiss
          </button>
        </div>
      ) : null}
    </section>
      <div
        ref={terminalCardRef}
        className={`request-terminal${terminalExpanded ? " request-terminal--expanded" : ""}`}
        style={terminalExpanded ? { width: `${terminalDimensions.width}px`, height: `${terminalDimensions.height}px` } : undefined}
      >
        <div className="request-terminal-header">
          <div>
            <p className="request-terminal-pill">Incident console</p>
            <p className="request-terminal-title">Defensive events stream</p>
          </div>
          <div className="request-terminal-controls">
            {!terminalExpanded ? (
              <button
                type="button"
                className="request-terminal-zoom"
                onClick={handleTerminalToggle}
                aria-label="Enlarge incident console"
              >
                Enlarge
              </button>
            ) : (
              <button
                type="button"
                className="request-terminal-close"
                onClick={() => setTerminalExpanded(false)}
                aria-label="Exit incident console focus"
              >
                Exit
              </button>
            )}
          </div>
        </div>
        <div ref={terminalBodyRef} className="request-terminal-body">
          {terminalLogs.map((log) => (
            <p key={log.id} className={`request-terminal-line level-${log.level || "info"}`}>
              <span className="request-terminal-timestamp">{log.timestamp}</span>
              <span className="request-terminal-message">{log.message}</span>
            </p>
          ))}
        </div>
        {terminalExpanded ? (
          <>
            <p className="request-terminal-resize-hint">Drag any edge or corner to resize.</p>
            {["north", "south", "east", "west", "north-east", "north-west", "south-east", "south-west"].map((direction) => (
              <span
                key={direction}
                className={`request-terminal-resizer request-terminal-resizer--${direction}`}
                onPointerDown={handleResizeStart(direction)}
                role="presentation"
              />
            ))}
          </>
        ) : null}
      </div>
      {terminalExpanded ? (
        <div
          className="request-terminal-overlay"
          role="presentation"
          onClick={() => setTerminalExpanded(false)}
        />
      ) : null}
    </>
  );
}

