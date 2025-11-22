const honeypots = [
  { path: "/admin-v2", description: "Decoy admin console", color: "#e0b1ff" },
  { path: "/backup-db", description: "Phantom dump node", color: "#82f5ff" },
  { path: "/config-prod", description: "Synthetic config surface", color: "#ffb8d2" }
];

const layers = [
  { title: "Honeypot Manager", detail: "Decoy rotation online" },
  { title: "Payload Analysis", detail: "LLM heuristics warmed" },
  { title: "Attack Classifier", detail: "Intent modeling ready" },
  { title: "Defense Memory", detail: "Last 128 steps cached" }
];

export default function PreAttackView() {
  return (
    <section className="glass-panel hero-grid">
      <div className="space-y-6">
        <div className="space-y-1">
          <div className="pill inline-flex items-center gap-2 text-sm text-white/80">
            <span className="w-2 h-2 rounded-full bg-emerald-300" /> baseline readiness
          </div>
          <h2 className="text-3xl font-semibold text-white">Honeypots primed · sensors synchronized</h2>
          <p className="text-white/65 text-sm">
            All defensive micro-services report nominal state. Synthetic admin surfaces are emitting believable traffic
            to lure autonomous attackers.
          </p>
        </div>

        <div className="grid sm:grid-cols-2 gap-3">
          {layers.map((layer) => (
            <article
              key={layer.title}
              className="rounded-2xl border border-white/10 bg-white/5 p-4 text-sm text-white/80 shadow-inner"
            >
              <p className="text-white font-semibold">{layer.title}</p>
              <p className="text-white/60">{layer.detail}</p>
            </article>
          ))}
        </div>
      </div>

      <div className="space-y-4">
        <h3 className="text-white/80 text-sm uppercase tracking-[0.35em]">Decoy endpoints</h3>
        <div className="grid gap-4">
          {honeypots.map((hp) => (
            <div
              key={hp.path}
              style={{
                background: `linear-gradient(135deg, ${hp.color}33, rgba(5,8,30,0.7))`,
                borderColor: `${hp.color}55`
              }}
              className="flex items-center justify-between rounded-2xl border px-4 py-3 shadow-lg"
            >
              <div>
                <p className="text-xs uppercase tracking-widest text-white/70">{hp.description}</p>
                <p className="text-lg font-semibold">{hp.path}</p>
              </div>
              <div className="text-right text-xs text-white/70">
                <p>Status</p>
                <p className="text-white font-semibold">ARMED</p>
              </div>
            </div>
          ))}
        </div>
      </div>
    </section>
  );
}

