import { useMemo } from "react";

const QUEUE_COLUMNS = ["Monitoring", "Responding", "Resolved"];
const SIGNAL_BUCKET_SECONDS = 5;
const SIGNAL_BUCKET_COUNT = 12;
const BUCKET_DURATION_MS = SIGNAL_BUCKET_SECONDS * 1000;

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

function buildSignalBuckets(events) {
  if (!events.length) {
    const nowBucket = Math.floor(Date.now() / BUCKET_DURATION_MS);
    return Array.from({ length: SIGNAL_BUCKET_COUNT }, (_, idx) => ({
      id: nowBucket - (SIGNAL_BUCKET_COUNT - 1 - idx),
      events: 0,
      honeypot: 0,
      system: 0,
      riskSum: 0,
      riskCount: 0,
    }));
  }

  const enriched = events
    .filter((evt) => evt?.event?.timestamp)
    .map((evt) => ({
      ref: evt,
      ts: Date.parse(evt.event.timestamp) || Date.now(),
    }))
    .sort((a, b) => a.ts - b.ts);
  if (!enriched.length) {
    const nowBucket = Math.floor(Date.now() / BUCKET_DURATION_MS);
    return Array.from({ length: SIGNAL_BUCKET_COUNT }, (_, idx) => ({
      id: nowBucket - (SIGNAL_BUCKET_COUNT - 1 - idx),
      events: 0,
      honeypot: 0,
      system: 0,
      riskSum: 0,
      riskCount: 0,
    }));
  }

  const latestBucketId = Math.floor(enriched[enriched.length - 1].ts / BUCKET_DURATION_MS);
  const earliestBucketId = latestBucketId - (SIGNAL_BUCKET_COUNT - 1);
  const buckets = Array.from({ length: SIGNAL_BUCKET_COUNT }, (_, idx) => ({
    id: earliestBucketId + idx,
    events: 0,
    honeypot: 0,
    system: 0,
    riskSum: 0,
    riskCount: 0,
  }));

  enriched.forEach(({ ref, ts }) => {
    const bucketId = Math.floor(ts / BUCKET_DURATION_MS);
    if (bucketId < earliestBucketId) {
      return;
    }
    const index = Math.min(SIGNAL_BUCKET_COUNT - 1, bucketId - earliestBucketId);
    const bucket = buckets[index];
    bucket.events += 1;
    if (ref.honeypot?.triggered) {
      bucket.honeypot += 1;
    }
    if ((ref.event?.action?.action_type || "").toUpperCase().includes("SYSTEM")) {
      bucket.system += 1;
    }
    const riskCandidate = ref.payload?.payload_risk_score ?? ref.event?.status;
    if (typeof riskCandidate === "number" && Number.isFinite(riskCandidate)) {
      bucket.riskSum += riskCandidate;
      bucket.riskCount += 1;
    }
  });

  return buckets;
}

function normalizeSeries(series) {
  const peak = Math.max(...series, 0);
  if (!peak) {
    return series.map(() => 0);
  }
  return series.map((value) => Math.round((value / peak) * 100));
}

function buildSignals(events) {
  const buckets = buildSignalBuckets(events);
  const eventSeries = buckets.map((bucket) => bucket.events);
  const honeypotSeries = buckets.map((bucket) => bucket.honeypot);
  const systemSeries = buckets.map((bucket) => bucket.system);
  const riskSeries = buckets.map((bucket) =>
    bucket.riskCount ? Math.round(bucket.riskSum / bucket.riskCount) : 0,
  );

  const sumSeries = (series) => series.reduce((total, value) => total + value, 0);
  const lastValue = (series) => (series.length ? series[series.length - 1] : 0);

  const totalRiskSum = buckets.reduce((total, bucket) => total + bucket.riskSum, 0);
  const totalRiskCount = buckets.reduce((total, bucket) => total + bucket.riskCount, 0);
  const avgRiskValue = totalRiskCount ? Math.round(totalRiskSum / totalRiskCount) : lastValue(riskSeries);

  return [
    { label: "Events/5s", value: lastValue(eventSeries), trend: normalizeSeries(eventSeries) },
    { label: "Honeypot trips", value: sumSeries(honeypotSeries), trend: normalizeSeries(honeypotSeries) },
    { label: "System probes", value: sumSeries(systemSeries), trend: normalizeSeries(systemSeries) },
    { label: "Avg risk", value: avgRiskValue, trend: riskSeries },
  ];
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

export default function NetworkTimeline({ events, operations = [], signals = [] }) {
  const ops = useMemo(() => {
    if (operations?.length) {
      return operations;
    }
    return buildOps(events);
  }, [operations, events]);
  const signalCards = useMemo(() => {
    if (signals?.length) {
      return signals;
    }
    return buildSignals(events);
  }, [signals, events]);
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
          {signalCards.map((signal) => (
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

