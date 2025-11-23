import { useEffect, useMemo, useState } from "react";
import AttackChainGraph from "./AttackChainGraph.jsx";
import DefenseMemoryInsights from "./DefenseMemoryInsights.jsx";
import { fetchReconReport, runRecon } from "../utils/api.js";

export default function PostAttackSummary({ events, honeypotTrigger, defenseMemory }) {
  const [reconReport, setReconReport] = useState(null);
  const [reconRunning, setReconRunning] = useState(false);
  const [runError, setRunError] = useState(null);
  const [lastRun, setLastRun] = useState(null);

  useEffect(() => {
    const controller = new AbortController();
    const loadReconReport = async () => {
      try {
        const report = await fetchReconReport(controller.signal);
        if (report && report.attack_assessment) {
          setReconReport(report);
        } else {
          setReconReport(null);
        }
      } catch (err) {
        setReconReport(null);
      }
    };

    loadReconReport();
    return () => controller.abort();
  }, []);

  const handleRunRecon = async () => {
    setReconRunning(true);
    setRunError(null);
    try {
      const report = await runRecon({ trigger: "dashboard_run" });
      setReconReport(report);
      setLastRun(new Date());
    } catch (err) {
      setRunError(err.message || "Recon agent failed");
    } finally {
      setReconRunning(false);
    }
  };

  // Merge recon report data with defense memory
  const enhancedDefenseMemory = { ...defenseMemory };
  if (reconReport) {
    const assessment = reconReport.attack_assessment || {};
    const intelligence = reconReport.intelligence || {};
    
    // Map attack patterns from recon report
    if (assessment.attack_type && assessment.attack_type !== "unknown") {
      const attackPatterns = enhancedDefenseMemory.attack_patterns || [];
      const reconPattern = {
        label: assessment.attack_type,
        path: assessment.target || "unknown",
        severity: assessment.severity,
        confidence: assessment.confidence,
      };
      // Only add if not already present
      if (!attackPatterns.some(p => p.label === reconPattern.label && p.path === reconPattern.path)) {
        enhancedDefenseMemory.attack_patterns = [...attackPatterns, reconPattern];
      }
    }

    // Add suspicious endpoints from recon report
    if (assessment.target) {
      const suspiciousEndpoints = enhancedDefenseMemory.suspicious_endpoints || [];
      if (!suspiciousEndpoints.includes(assessment.target)) {
        enhancedDefenseMemory.suspicious_endpoints = [...suspiciousEndpoints, assessment.target];
      }
    }

    // Merge recommendations from recon report
    if (reconReport.recommendations && reconReport.recommendations.length > 0) {
      const recommendations = enhancedDefenseMemory.future_recommendations || [];
      reconReport.recommendations.forEach(rec => {
        if (!recommendations.includes(rec)) {
          recommendations.push(rec);
        }
      });
      enhancedDefenseMemory.future_recommendations = recommendations;
    }
  }

  const assessment = reconReport?.attack_assessment;
  const evidence = reconReport?.evidence || [];
  const recommendations = reconReport?.recommendations || [];
  const nextSteps = reconReport?.next_steps || [];
  const intelligence = reconReport?.intelligence || {};

  return (
    <section className="glass-panel">
      <div className="flex flex-wrap items-center justify-between gap-4 mb-6">
        <div>
          <p className="text-xs uppercase tracking-[0.35em] text-white/60">Post-Attack Summary</p>
          <h2 className="text-2xl font-semibold text-white">Chain reconstruction & defensive learnings</h2>
        </div>
        <button
          onClick={handleRunRecon}
          disabled={reconRunning}
          className="px-5 py-2 rounded-full bg-gradient-to-r from-[#9d8bff] to-[#6ef5ff] text-slate-900 font-semibold text-sm shadow-lg disabled:opacity-50"
        >
          {reconRunning ? "Running recon..." : "Run Recon Agent"}
        </button>
      </div>

      {runError ? <p className="text-rose-300 text-sm mb-4">{runError}</p> : null}
      {lastRun ? (
        <p className="text-white/60 text-xs mb-4">Last investigation triggered {lastRun.toLocaleTimeString()}</p>
      ) : null}

      <div className="space-y-6">
        <div className="grid gap-6 lg:grid-cols-2">
          <div>
            <h3 className="text-white/80 font-semibold mb-2">Recon Assessment</h3>
            {assessment ? (
              <div className="rounded-2xl border border-white/10 bg-white/5 p-4 text-sm space-y-4">
                <div className="grid grid-cols-2 gap-4">
                  <InfoTile label="Attack type" value={assessment.attack_type?.replace(/_/g, " ") || "Unknown"} />
                  <InfoTile
                    label="Severity"
                    value={assessment.severity?.toUpperCase() || "UNKNOWN"}
                    emphasis={assessment.severity || "unknown"}
                  />
                  <InfoTile label="Target" value={assessment.target || "Unknown"} />
                  <InfoTile label="Confidence" value={assessment.confidence || "Unknown"} />
                </div>
                {Object.keys(intelligence).length ? (
                  <div className="grid grid-cols-3 gap-4 text-sm text-white/80">
                    {intelligence.total_requests !== undefined && (
                      <InfoTile label="Requests" value={intelligence.total_requests} />
                    )}
                    {intelligence.unique_endpoints !== undefined && (
                      <InfoTile label="Endpoints" value={intelligence.unique_endpoints} />
                    )}
                    {intelligence.attack_count !== undefined && (
                      <InfoTile label="Attack count" value={intelligence.attack_count} />
                    )}
                  </div>
                ) : null}
              </div>
            ) : (
              <p className="text-white/60 text-sm">No recon report available yet.</p>
            )}
          </div>

          <div>
            <h3 className="text-white/80 font-semibold mb-2">Evidence & Recommendations</h3>
            <div className="rounded-2xl border border-white/10 bg-white/5 p-4 text-sm space-y-4">
              {evidence.length ? (
                <ListBlock title="Evidence" items={evidence} />
              ) : (
                <p className="text-white/60 text-sm">No evidence collected yet.</p>
              )}
              {recommendations.length ? <ListBlock title="Recommendations" items={recommendations} /> : null}
              {nextSteps.length ? <ListBlock title="Next steps" items={nextSteps} /> : null}
            </div>
          </div>
        </div>

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

        <DefenseMemoryInsights defenseMemory={enhancedDefenseMemory} />
      </div>
    </section>
  );
}

function InfoTile({ label, value, emphasis }) {
  const color =
    emphasis === "critical"
      ? "text-red-300"
      : emphasis === "high"
      ? "text-orange-300"
      : emphasis === "medium"
      ? "text-yellow-300"
      : "text-white";
  return (
    <div>
      <p className="text-white/60 text-xs uppercase tracking-wide mb-1">{label}</p>
      <p className={`font-semibold ${color}`}>{value}</p>
    </div>
  );
}

function ListBlock({ title, items }) {
  return (
    <div>
      <p className="text-white/60 text-xs uppercase tracking-wide mb-2">{title}</p>
      <ul className="space-y-1 text-white/80">
        {items.map((item, idx) => (
          <li key={`${title}-${idx}`} className="flex items-start gap-2">
            <span className="w-1.5 h-1.5 rounded-full bg-white/40 mt-1.5 flex-shrink-0" />
            <span className="text-sm">{item}</span>
          </li>
        ))}
      </ul>
    </div>
  );
}

