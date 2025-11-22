export default function NetworkTimeline({ events }) {
  return (
    <section className="glass-panel">
      <div className="flex items-center justify-between mb-4">
        <h2 className="text-xl font-semibold text-white">Network Timeline</h2>
        <span className="text-xs uppercase tracking-[0.3em] text-white/60">Chronology</span>
      </div>
      <ol className="space-y-3 max-h-64 overflow-y-auto pr-2">
        {events.map((evt) => (
          <li key={`${evt.event?.step}-${evt.event?.timestamp}-timeline`} className="flex items-center gap-3">
            <span className="timeline-dot" />
            <div className="flex-1 border-b border-white/10 pb-2">
              <div className="flex items-center justify-between text-sm text-white/75">
                <span>
                  STEP {evt.event?.step} · {evt.event?.action?.action_type} {evt.event?.action?.target_url}
                </span>
                <span className="text-white/50 text-xs">{evt.event?.timestamp}</span>
              </div>
              <p className="text-xs text-white/50">{evt.event?.response_summary}</p>
            </div>
          </li>
        ))}
        {events.length === 0 && <li className="text-white/60 text-sm">No events yet.</li>}
      </ol>
    </section>
  );
}

