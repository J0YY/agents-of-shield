import { useEffect, useMemo, useRef } from "react";

export default function LiveAttackFeed({ events }) {
  const listRef = useRef(null);
  const feed = useMemo(() => events.slice().reverse(), [events]);

  useEffect(() => {
    if (listRef.current) {
      listRef.current.scrollTop = 0;
    }
  }, [feed]);

  return (
    <section className="glass-panel h-full flex flex-col">
      <div className="flex items-center justify-between mb-6">
        <div>
          <p className="text-xs uppercase tracking-[0.4em] text-white/50">Live Attack Feed</p>
          <h2 className="text-2xl font-semibold text-white">Autonomous probes in flight</h2>
        </div>
        <span className="pill">{feed.length.toString().padStart(2, "0")} events</span>
      </div>
      <div ref={listRef} className="space-y-3 flex-1 overflow-y-auto pr-1">
        {feed.map((evt) => {
          const risk = evt.payload?.payload_risk_score ?? 0;
          const badge =
            risk > 60 ? "text-red-300 bg-red-400/10" : risk > 30 ? "text-amber-200 bg-amber-300/10" : "text-emerald-200 bg-emerald-400/10";
          return (
            <article key={`${evt.event?.step}-${evt.event?.timestamp}`} className="feed-card">
              <div className="flex items-center justify-between text-xs uppercase tracking-[0.3em] text-white/60">
                <span>step {evt.event?.step}</span>
                <span>{evt.event?.timestamp}</span>
              </div>
              <div className="flex flex-wrap items-center justify-between gap-3 mt-2">
                <div>
                  <p className="text-lg font-semibold text-white">
                    {evt.event?.action?.action_type} <span className="text-white/70">{evt.event?.action?.target_url}</span>
                  </p>
                  <p className="text-sm text-white/60">{evt.event?.response_summary}</p>
                </div>
                <span className={`px-3 py-1 rounded-full text-xs font-semibold ${badge}`}>Risk {risk}</span>
              </div>
              <div className="mt-3 grid grid-cols-3 text-xs text-white/60">
                <span>Status · {evt.event?.status}</span>
                <span>Class · {evt.classification?.label || "unknown"}</span>
                <span>Honeypot · {evt.honeypot?.triggered ? evt.honeypot?.honeypot : "—"}</span>
              </div>
            </article>
          );
        })}
        {feed.length === 0 && (
          <p className="text-center text-sm text-white/60">Waiting for attacker telemetry…</p>
        )}
      </div>
    </section>
  );
}

