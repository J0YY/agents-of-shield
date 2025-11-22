import AttackChainGraph from "./AttackChainGraph.jsx";
import DefenseMemoryInsights from "./DefenseMemoryInsights.jsx";

export default function PostAttackSummary({ events, honeypotTrigger, defenseMemory }) {
  const downloadReport = async () => {
    const res = await fetch("http://localhost:7000/reports/latest?fmt=html");
    if (res.ok) {
      const blob = await res.blob();
      const url = window.URL.createObjectURL(blob);
      const link = document.createElement("a");
      link.href = url;
      link.download = "incident_report.html";
      link.click();
      window.URL.revokeObjectURL(url);
    }
  };

  return (
    <section className="glass-panel">
      <div className="flex flex-wrap items-center justify-between gap-4 mb-6">
        <div>
          <p className="text-xs uppercase tracking-[0.35em] text-white/60">Post-Attack Summary</p>
          <h2 className="text-2xl font-semibold text-white">Chain reconstruction & defensive learnings</h2>
        </div>
        <button
          onClick={downloadReport}
          className="px-5 py-2 rounded-full bg-gradient-to-r from-[#9d8bff] to-[#6ef5ff] text-slate-900 font-semibold text-sm shadow-lg"
        >
          Download Incident Report
        </button>
      </div>

      <div className="space-y-6">
        <div>
          <h3 className="text-white/80 font-semibold mb-2">Attack Chain</h3>
          <AttackChainGraph events={events} />
        </div>

        <div>
          <h3 className="text-white/80 font-semibold mb-2">Honeypot Trigger</h3>
          {honeypotTrigger ? (
            <div className="rounded-2xl border border-danger/40 bg-danger/10 p-4 text-sm text-white/80">
              <p>
                Honeypot <span className="font-semibold">{honeypotTrigger.endpoint}</span> tripped at step{" "}
                {honeypotTrigger.step}.
              </p>
              <p className="text-white/60 mt-1">
                Payload sample: {JSON.stringify(honeypotTrigger.payload, null, 2)}
              </p>
            </div>
          ) : (
            <p className="text-white/60 text-sm">No decoys engaged yet.</p>
          )}
        </div>

        <DefenseMemoryInsights defenseMemory={defenseMemory} />
      </div>
    </section>
  );
}

