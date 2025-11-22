export default function AttackChainGraph({ events }) {
  if (!events.length) {
    return <p className="text-sm text-white/60">Attack chain will populate after telemetry arrives.</p>;
  }

  return (
    <div className="flex flex-wrap gap-2">
      {events.map((node) => (
        <div
          key={`chain-${node.step}`}
          className={`chain-node text-xs ${
            node.honeypot ? "bg-gradient-to-r from-rose-400/30 to-purple-400/20 text-white" : "text-white/80"
          }`}
        >
          <span className="font-bold mr-2">#{node.step}</span>
          {node.endpoint}{" "}
          <span className="text-white/60">({node.classification?.toUpperCase?.() ?? "UNKNOWN"})</span>
        </div>
      ))}
    </div>
  );
}

