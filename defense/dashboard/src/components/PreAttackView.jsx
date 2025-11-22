import { useEffect, useMemo, useState } from "react";
import { fetchDefenseScan } from "../utils/api";
import RequestRateChart from "./RequestRateChart.jsx";

const SYSTEM_LAYERS = [
  { title: "Honeypot Manager", detail: "Decoy rotation online" },
  { title: "Payload Analysis", detail: "LLM heuristics warmed" },
  { title: "Attack Classifier", detail: "Intent modeling ready" },
  { title: "Defense Memory", detail: "Last 128 steps cached" }
];

const DEFAULT_CHECKPOINTS = [
  { id: "boot", title: "Repository root", detail: "Waiting for orchestrator", summary: "Bootstrap ready" },
  {
    id: "manifest",
    title: "package.json",
    detail: "Enumerating dependencies",
    summary: "Manifest parsed"
  },
  { id: "routes", title: "Express routes", detail: "Indexing handlers", summary: "Routes catalogued" },
  { id: "storage", title: "Storage", detail: "Probing SQLite + attack logs", summary: "Data stores mapped" },
  { id: "secrets", title: "Secrets surfaces", detail: "Hunting leaked env vars", summary: "Config audited" }
];

const LOG_REVEAL_INTERVAL = 650;

export default function PreAttackView() {
  const [scanData, setScanData] = useState(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);
  const [pendingLogs, setPendingLogs] = useState([]);
  const [visibleLogs, setVisibleLogs] = useState([]);
  const [activeStep, setActiveStep] = useState(0);
  const [scanComplete, setScanComplete] = useState(false);
  const [selectedBlueprints, setSelectedBlueprints] = useState([]);
  const [confirmation, setConfirmation] = useState(null);

  useEffect(() => {
    const controller = new AbortController();
    async function runScan() {
      setLoading(true);
      setError(null);
      setVisibleLogs([]);
      setPendingLogs([]);
      setScanComplete(false);
      setActiveStep(0);
      setConfirmation(null);

      try {
        const payload = await fetchDefenseScan(controller.signal);
        setScanData(payload);
        const logs = payload.logs ?? [];
        setPendingLogs(logs);
        const autoPick = (payload.suggestions ?? []).filter((bp) => bp.auto_select).map((bp) => bp.id);
        setSelectedBlueprints(autoPick);
        if (!logs.length) {
          setScanComplete(true);
        }
      } catch (err) {
        if (err.name === "AbortError") return;
        setError(err.message || "Unable to run scan");
      } finally {
        setLoading(false);
      }
    }

    runScan();
    return () => controller.abort();
  }, []);

  useEffect(() => {
    if (!pendingLogs.length) {
      return undefined;
    }
    const timer = setTimeout(() => {
      setVisibleLogs((prev) => [...prev, pendingLogs[0]]);
      setPendingLogs((prev) => prev.slice(1));
    }, LOG_REVEAL_INTERVAL);
    return () => clearTimeout(timer);
  }, [pendingLogs]);

  useEffect(() => {
    if (!scanData) return;
    const totalLogs = scanData.logs?.length ?? 0;
    if (totalLogs === 0) {
      setScanComplete(true);
      return;
    }

    if (visibleLogs.length >= totalLogs) {
      setScanComplete(true);
    }

    const checkpoints = scanData.checkpoints?.length ? scanData.checkpoints : DEFAULT_CHECKPOINTS;
    if (checkpoints.length === 0) return;
    const nextIndex = Math.min(
      checkpoints.length - 1,
      Math.floor((visibleLogs.length / Math.max(totalLogs, 1)) * checkpoints.length)
    );
    setActiveStep(nextIndex);
  }, [visibleLogs, scanData]);

  const checkpoints = scanData?.checkpoints?.length ? scanData.checkpoints : DEFAULT_CHECKPOINTS;
  const totalLogs = scanData?.logs?.length ?? 0;
  const scanPercent = totalLogs ? Math.round((visibleLogs.length / totalLogs) * 100) : scanComplete ? 100 : 0;
  const activeScanStep = checkpoints[Math.min(activeStep, checkpoints.length - 1)] ?? checkpoints[0];
  const services = scanData?.services ?? [];
  const existingDecoys = scanData?.existing_decoys ?? [];
  const blueprintOptions = scanData?.suggestions ?? [];

  const blueprintLookup = useMemo(() => {
    const map = {};
    blueprintOptions.forEach((bp) => {
      map[bp.id] = bp;
    });
    return map;
  }, [blueprintOptions]);

  const recommendedSet = useMemo(() => {
    return new Set(blueprintOptions.filter((bp) => bp.recommended).map((bp) => bp.id));
  }, [blueprintOptions]);

  const pickedNames = selectedBlueprints
    .map((id) => blueprintLookup[id]?.short ?? blueprintLookup[id]?.name ?? id)
    .join(", ");

  const handleBlueprintToggle = (id) => {
    if (!blueprintLookup[id]) return;
    setSelectedBlueprints((prev) => {
      if (prev.includes(id)) {
        return prev.filter((item) => item !== id);
      }
      return [...prev, id];
    });
    setConfirmation(null);
  };

  const handleConfirm = () => {
    setConfirmation({
      time: new Date().toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" }),
      traps: selectedBlueprints.length
    });
  };

  return (
    <section className="glass-panel hero-grid">
      <div className="space-y-6">
        <div className="space-y-1">
          <div className="pill inline-flex items-center gap-2 text-sm text-white/80">
            <span className="w-2 h-2 rounded-full bg-emerald-300 animate-pulse" /> vulnerable-app recon sweep
          </div>
          <h2 className="text-3xl font-semibold text-white">We actually scan the repo · you pick the traps</h2>
          <p className="text-white/65 text-sm">
            Running a live crawl of <span className="text-accent">{scanData?.target ?? "vulnerable-app"}</span>, parsing
            Express routes, honeypots, SQLite stores, and leaked secrets. Logs stream in the console below — nothing is
            faked.
          </p>
        </div>

        <div className="scan-visor">
          <div className="scan-visor-grid">
            <div className="scan-radar">
              <div className="radar-grid">
                <div className="radar-beam" />
                <div className="radar-pulse" />
                <span className="radar-label top-left">agents_example</span>
                <span className="radar-label top-right">attacker</span>
                <span className="radar-label bottom-left">defense</span>
                <span className="radar-label bottom-right">vulnerable-app</span>
              </div>
              <div className="scan-percent">
                <p className="text-xs uppercase tracking-[0.3em] text-white/60">scan progress</p>
                <p className="text-3xl font-semibold text-white">{scanPercent}%</p>
                <p className="text-xs text-white/50">
                  {scanComplete ? "Recon locked" : loading ? "Initializing..." : "Live crawl"}
                </p>
              </div>
            </div>

            <div className="scan-feed">
              <div className="scan-progress">
                <div className="scan-progress-track">
                  <div className="scan-progress-thumb" style={{ width: `${scanPercent}%` }} />
                </div>
                <p className="text-xs text-white/70">
                  Now inspecting: {activeScanStep?.title ?? "—"} · {activeScanStep?.detail ?? ""}
                </p>
              </div>

              <ul className="scan-step-list">
                {checkpoints.map((step, index) => (
                  <li key={step.id} className={`scan-step ${index <= activeStep ? "scan-step--done" : ""}`}>
                    <span className="scan-step-index">{index + 1}</span>
                    <div>
                      <p className="text-sm font-semibold text-white">{step.title}</p>
                      <p className="text-xs text-white/65">{index === activeStep ? step.detail : step.summary}</p>
                    </div>
                  </li>
                ))}
              </ul>
            </div>
          </div>
        </div>

        <div className="scan-terminal">
          <div className="scan-terminal-header">
            <p className="text-xs uppercase tracking-[0.35em] text-white/60">Live scan log</p>
            <p className="text-xs text-white/60">
              {scanData?.duration_ms ? `${scanData.duration_ms}ms` : loading ? "..." : "queued"}
            </p>
          </div>
          <div className="scan-terminal-body">
            {visibleLogs.map((log, idx) => (
              <p key={`${log.timestamp}-${idx}`} className={`terminal-line level-${log.level || "info"}`}>
                <span className="terminal-timestamp">{log.timestamp}</span>
                <span className="terminal-message">{log.message}</span>
              </p>
            ))}
            {!visibleLogs.length && loading && (
              <p className="terminal-line text-white/50">Booting scanner · waiting for orchestrator...</p>
            )}
            {error && <p className="terminal-line text-rose-300">Scan error: {error}</p>}
          </div>
        </div>

        <div className="grid sm:grid-cols-2 gap-3">
          {SYSTEM_LAYERS.map((layer) => (
            <article
              key={layer.title}
              className="rounded-2xl border border-white/10 bg-white/5 p-4 text-sm text-white/80 shadow-inner"
            >
              <p className="text-white font-semibold">{layer.title}</p>
              <p className="text-white/60">{layer.detail}</p>
            </article>
          ))}
        </div>

        <RequestRateChart />
      </div>

      <div className="space-y-6">
        <div className="space-y-3">
          <h3 className="text-white/80 text-sm uppercase tracking-[0.35em]">Surface inventory</h3>
          <div className="space-y-3">
            {services.map((srv) => (
              <article
                key={srv.id}
                style={{
                  borderColor: `${srv.accent ?? "#fff"}44`,
                  background: `linear-gradient(135deg, ${srv.accent ?? "#fff"}22, rgba(8,10,40,0.85))`
                }}
                className="server-card"
              >
                <div className="flex items-start justify-between gap-4">
                  <div>
                    <p className="text-xs uppercase tracking-[0.35em] text-white/60">{srv.role}</p>
                    <p className="text-lg font-semibold text-white">{srv.name}</p>
                  </div>
                  <div className="text-right">
                    <p className="text-xs text-white/60">status</p>
                    <p className="text-sm font-semibold text-white">{srv.status}</p>
                  </div>
                </div>
                <p className="text-sm text-white/70">{srv.detail}</p>
                {srv.issues?.length ? (
                  <ul className="service-issues">
                    {srv.issues.map((issue) => (
                      <li key={issue}>{issue}</li>
                    ))}
                  </ul>
                ) : null}
              </article>
            ))}
          </div>
        </div>

        {existingDecoys.length ? (
          <div className="space-y-3">
            <h3 className="text-white/80 text-sm uppercase tracking-[0.35em]">Detected honeypots</h3>
            <div className="grid gap-3">
              {existingDecoys.map((hp) => (
                <div key={hp.path} className="decoy-chip">
                  <div>
                    <p className="text-xs uppercase tracking-[0.35em] text-white/50">Decoy</p>
                    <p className="text-white font-semibold">{hp.path}</p>
                  </div>
                  <p className="text-xs text-white/70">{hp.detail}</p>
                </div>
              ))}
            </div>
          </div>
        ) : null}

        <div className="space-y-3">
          <h3 className="text-white/80 text-sm uppercase tracking-[0.35em]">Choose your traps</h3>
          <p className="text-white/70 text-sm">
            {scanComplete
              ? "Scan complete — pick which mirages to deploy next. Recommended blueprints glow neon."
              : "Scanning in progress — we pre-selected traps that align with the surfaces we just found."}
          </p>
          <div className="grid gap-3">
            {blueprintOptions.map((hp) => {
              const active = selectedBlueprints.includes(hp.id);
              const recommended = recommendedSet.has(hp.id);
              return (
                <button
                  key={hp.id}
                  type="button"
                  onClick={() => handleBlueprintToggle(hp.id)}
                  className={`honeypot-card ${active ? "is-active" : ""}`}
                  aria-pressed={active}
                >
                  <div className="flex items-start gap-3">
                    <div className="honeypot-icon" aria-hidden="true">
                      {hp.emoji}
                    </div>
                    <div className="text-left">
                      <div className="flex items-center gap-2 flex-wrap">
                        <p className="font-semibold text-white">{hp.name}</p>
                        {recommended && scanComplete && <span className="recommend-pill">Recommended</span>}
                      </div>
                      <p className="text-xs uppercase tracking-[0.35em] text-white/60">{hp.vector}</p>
                      <p className="text-sm text-white/70">{hp.description}</p>
                      {hp.reasons?.length ? (
                        <p className="text-xs text-white/50 mt-1">Because: {hp.reasons[0]}</p>
                      ) : null}
                    </div>
                  </div>
                </button>
              );
            })}
          </div>

          <div className="honeypot-cta">
            <div>
              <p className="text-xs uppercase tracking-[0.35em] text-white/60">Loadout</p>
              <p className="text-sm text-white">
                {pickedNames.length ? pickedNames : "No honeypots selected yet"}
              </p>
            </div>
            <button
              type="button"
              className="honeypot-cta-button"
              onClick={handleConfirm}
              disabled={!selectedBlueprints.length}
            >
              Arm selected decoys
            </button>
          </div>

          {confirmation ? (
            <p className="text-emerald-300 text-sm">
              Loadout locked at {confirmation.time}. {confirmation.traps} trap(s) will go live once the attack sim
              starts.
            </p>
          ) : (
            <p className="text-white/60 text-xs">
              We&apos;ll queue deployments the moment you click arm — no backend refresh required.
            </p>
          )}
        </div>
      </div>
    </section>
  );
}

