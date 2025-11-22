import { useEffect, useMemo, useRef, useState } from "react";
import { fetchAttackLog } from "../utils/api";

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
}) {
  const [series, setSeries] = useState(() => buildSeries([], bucketSeconds, samplePoints));
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);
  const [spikeAlert, setSpikeAlert] = useState(null);
  const lastAlertBucketRef = useRef(null);
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
    return Array.from({ length: GRID_STEPS }, (_, idx) => {
      const ratio = idx / GRID_STEPS;
      const value = Math.max(0, Math.round(chartCeiling * (1 - ratio)));
      const lineY = PADDING_TOP + ratio * INNER_HEIGHT;
      const topPercent = (lineY / CHART_HEIGHT) * 100;
      return {
        value,
        key: `${idx}-${chartCeiling}`,
        topPercent,
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

  return (
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
              className="request-chart-axis-label"
              style={{ top: `${tick.topPercent}%` }}
            >
              {tick.value}
            </span>
          ))}
          <span className="request-chart-axis-label request-chart-axis-label--zero">0</span>
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
  );
}

