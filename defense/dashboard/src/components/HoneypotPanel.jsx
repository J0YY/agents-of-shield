const defaultItems = [
  { path: "/admin-v2", status: "armed", color: "#ffb5d6", description: "Executive decoy" },
  { path: "/backup-db", status: "armed", color: "#a5f0ff", description: "Snapshot lure" },
  { path: "/config-prod", status: "armed", color: "#c0b8ff", description: "Secrets mirage" }
];

export default function HoneypotPanel({ honeypotTrigger }) {
  return (
    <section className="glass-panel h-full">
      <div className="flex items-center justify-between mb-4">
        <h2 className="text-xl font-semibold text-white">Honeypot Telemetry</h2>
        <span className="pill text-xs">{honeypotTrigger ? "Alert" : "Armed"}</span>
      </div>
      <ul className="space-y-3 text-sm">
        {defaultItems.map((item) => {
          const triggered = honeypotTrigger?.endpoint === item.path;
          return (
            <li
              key={item.path}
              style={{ borderColor: triggered ? "#ff7aa3" : "rgba(255,255,255,0.1)" }}
              className={`rounded-2xl border px-4 py-3 bg-white/5 shadow-lg ${
                triggered ? "text-danger" : "text-white/80"
              }`}
            >
              <div className="flex items-center justify-between">
                <div>
                  <p className="text-xs uppercase tracking-widest text-white/50">{item.description}</p>
                  <p className="font-semibold text-lg">{item.path}</p>
                </div>
                <div
                  style={{ background: triggered ? "rgba(255,137,164,0.15)" : "rgba(255,255,255,0.08)" }}
                  className="px-3 py-1 rounded-full text-xs font-semibold"
                >
                  {triggered ? "TRIGGERED" : item.status.toUpperCase()}
                </div>
              </div>
              {triggered && honeypotTrigger?.payload && (
                <pre className="mt-2 text-xs whitespace-pre-wrap text-white/70">
                  {JSON.stringify(honeypotTrigger.payload, null, 2)}
                </pre>
              )}
            </li>
          );
        })}
      </ul>
    </section>
  );
}

