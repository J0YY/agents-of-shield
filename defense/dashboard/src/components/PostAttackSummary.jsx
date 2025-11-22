import { useEffect, useState } from "react";
import AttackChainGraph from "./AttackChainGraph.jsx";
import DefenseMemoryInsights from "./DefenseMemoryInsights.jsx";
import { fetchReconReport } from "../utils/api.js";

export default function PostAttackSummary({ events, honeypotTrigger, defenseMemory }) {
  const [reconReport, setReconReport] = useState(null);

  useEffect(() => {
    const loadReconReport = async () => {
      try {
        console.log("[PostAttackSummary] Fetching recon report...");
        const report = await fetchReconReport();
        console.log("[PostAttackSummary] Recon report loaded:", report);
        if (report && report.attack_assessment) {
          setReconReport(report);
        } else {
          console.warn("[PostAttackSummary] Report missing attack_assessment:", report);
          setReconReport(null);
        }
      } catch (err) {
        // Report not available yet - this is fine
        console.log("[PostAttackSummary] Recon report not available:", err.message, err.status || err);
        setReconReport(null);
      }
    };

    loadReconReport();
    // Poll for updates every 10 seconds
    const interval = setInterval(loadReconReport, 10000);
    return () => clearInterval(interval);
  }, []);

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
        {reconReport ? (
          <div>
            <h3 className="text-white/80 font-semibold mb-2">Recon Assessment</h3>
            <div className="rounded-2xl border border-white/10 bg-white/5 p-4 text-sm">
              <div className="grid md:grid-cols-2 gap-4 mb-4">
                <div>
                  <p className="text-white/60 text-xs uppercase tracking-wide mb-1">Attack Type</p>
                  <p className="text-white font-semibold capitalize">
                    {reconReport.attack_assessment?.attack_type?.replace(/_/g, " ") || "Unknown"}
                  </p>
                </div>
                <div>
                  <p className="text-white/60 text-xs uppercase tracking-wide mb-1">Severity</p>
                  <p className={`font-semibold ${
                    reconReport.attack_assessment?.severity === "critical" ? "text-red-300" :
                    reconReport.attack_assessment?.severity === "high" ? "text-orange-300" :
                    reconReport.attack_assessment?.severity === "medium" ? "text-yellow-300" :
                    "text-white/70"
                  }`}>
                    {reconReport.attack_assessment?.severity?.toUpperCase() || "UNKNOWN"}
                  </p>
                </div>
                <div>
                  <p className="text-white/60 text-xs uppercase tracking-wide mb-1">Target</p>
                  <p className="text-white/80">{reconReport.attack_assessment?.target || "Unknown"}</p>
                </div>
                <div>
                  <p className="text-white/60 text-xs uppercase tracking-wide mb-1">Confidence</p>
                  <p className="text-white/80 capitalize">{reconReport.attack_assessment?.confidence || "Unknown"}</p>
                </div>
              </div>
              {reconReport.evidence && reconReport.evidence.length > 0 && (
                <div className="mt-4 pt-4 border-t border-white/10">
                  <p className="text-white/60 text-xs uppercase tracking-wide mb-2">Evidence</p>
                  <ul className="space-y-1 text-white/70">
                    {reconReport.evidence.map((ev, idx) => (
                      <li key={idx} className="flex items-start gap-2">
                        <span className="w-1.5 h-1.5 rounded-full bg-white/40 mt-1.5 flex-shrink-0" />
                        <span className="text-sm">{ev}</span>
                      </li>
                    ))}
                  </ul>
                </div>
              )}
              {reconReport.intelligence && Object.keys(reconReport.intelligence).length > 0 && (
                <div className="mt-4 pt-4 border-t border-white/10">
                  <p className="text-white/60 text-xs uppercase tracking-wide mb-2">Intelligence</p>
                  <div className="grid grid-cols-3 gap-4 text-sm text-white/70">
                    {reconReport.intelligence.total_requests !== undefined && (
                      <div>
                        <span className="text-white/50">Total Requests:</span>{" "}
                        <span className="text-white font-semibold">{reconReport.intelligence.total_requests}</span>
                      </div>
                    )}
                    {reconReport.intelligence.unique_endpoints !== undefined && (
                      <div>
                        <span className="text-white/50">Unique Endpoints:</span>{" "}
                        <span className="text-white font-semibold">{reconReport.intelligence.unique_endpoints}</span>
                      </div>
                    )}
                    {reconReport.intelligence.attack_count !== undefined && (
                      <div>
                        <span className="text-white/50">Attack Count:</span>{" "}
                        <span className="text-white font-semibold">{reconReport.intelligence.attack_count}</span>
                      </div>
                    )}
                  </div>
                </div>
              )}
            </div>
          </div>
        ) : (
          <div>
            <h3 className="text-white/80 font-semibold mb-2">Recon Assessment</h3>
            <p className="text-white/60 text-sm">No recon report available yet. Run an investigation to generate a report.</p>
          </div>
        )}

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

