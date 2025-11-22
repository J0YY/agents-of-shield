export default function DefenseMemoryInsights({ defenseMemory = {} }) {
  const { attack_patterns = [], suspicious_endpoints = [], future_recommendations = [] } = defenseMemory;

  return (
    <div className="grid md:grid-cols-3 gap-4 text-sm">
      <InsightCard
        title="Attack Patterns"
        items={attack_patterns.map((p) => `${p.label?.toUpperCase?.() ?? "UNKNOWN"} · ${p.path}`)}
      />
      <InsightCard title="Suspicious Endpoints" items={suspicious_endpoints} />
      <InsightCard
        title="Future Recommendations"
        items={future_recommendations}
        placeholder="No recommendations yet."
      />
    </div>
  );
}

function InsightCard({ title, items = [], placeholder = "No data yet." }) {
  return (
    <div className="rounded-2xl border border-white/10 bg-white/5 p-4 shadow-lg">
      <h4 className="text-white font-semibold mb-3">{title}</h4>
      {items.length ? (
        <ul className="space-y-2 text-white/70">
          {items.map((item) => (
            <li key={item} className="flex items-center gap-2">
              <span className="w-2 h-2 rounded-full bg-white/40" /> {item}
            </li>
          ))}
        </ul>
      ) : (
        <p className="text-white/50">{placeholder}</p>
      )}
    </div>
  );
}

