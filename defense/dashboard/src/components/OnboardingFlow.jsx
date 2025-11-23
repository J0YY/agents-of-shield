import { useEffect, useMemo, useState } from "react";

const heroPhases = [
  { id: "source", label: "Step 1", detail: "Drop repo or zip" },
  { id: "scanning", label: "Scan", detail: "We fingerprint frameworks" },
  { id: "environment", label: "Step 2", detail: "Add runtime context" },
  { id: "connecting", label: "Connect", detail: "Agent + honeypots arm" },
];

const envFields = [
  {
    label: "Hosting provider",
    placeholder: "Render · Fly.io · Railway · EC2",
    helper: "So we know how to mirror prod safely.",
  },
  {
    label: "Primary datastore",
    placeholder: "Postgres · PlanetScale · SQLite",
    helper: "Used to fabricate believable decoy data.",
  },
  {
    label: "Read-only log/API key",
    placeholder: "Paste token · e.g. Logtail, BetterStack",
    helper: "Lets the agent stream attack telemetry only.",
  },
];

function SourceStep({ fileName, onFileSelect, onNext }) {
  return (
    <section className="launch-panel glass-panel launch-step-card">
      <div className="step-header">
        <span className="step-number">Step 1</span>
        <h2>Where should we look?</h2>
        <p>Upload a source ZIP or paste a GitHub/GitLab repo. We only read framework + route metadata.</p>
      </div>

      <div className="input-stack">
        <label className="upload-box">
          <input id="source-upload" type="file" accept=".zip" onChange={onFileSelect} />
          <p className="upload-title">Drop your source ZIP</p>
          <p className="upload-helper">{fileName ?? "No file selected"}</p>
          <span className="upload-trigger">Choose file</span>
        </label>

        <label className="text-field">
          <span className="text-label">GitHub / GitLab repo</span>
          <input type="text" className="text-input" placeholder="https://github.com/acme/saas-app" />
          <span className="text-helper">We fingerprint package.json, frameworks, and exposed routes automatically.</span>
        </label>
      </div>

      <div className="step-actions">
        <button type="button" className="primary-link step-button" onClick={onNext}>
          Next
        </button>
        <p className="step-note">Demo only — nothing actually uploads. We’re showcasing the workflow.</p>
      </div>
    </section>
  );
}

function EnvironmentStep({ onSubmit }) {
  return (
    <section className="launch-panel glass-panel launch-step-card">
      <div className="step-header">
        <span className="step-number">Step 2</span>
        <h2>Give us the runtime snapshot.</h2>
        <p>Hosting, datastore, and a read-only log key are enough to spin up believable mirrors + honeypots.</p>
      </div>

      <div className="input-stack">
        {envFields.map((field) => (
          <label key={field.label} className="text-field">
            <span className="text-label">{field.label}</span>
            <input type="text" className="text-input" placeholder={field.placeholder} />
            <span className="text-helper">{field.helper}</span>
          </label>
        ))}

        <label className="text-field optional-field">
          <span className="text-label">Optional: DNS / Cloudflare access</span>
          <input type="text" className="text-input" placeholder="decoy.yourdomain.com" />
          <span className="text-helper">Let us auto-provision fake admin portals and backup routes per tenant.</span>
        </label>
      </div>

      <div className="step-actions">
        <button type="button" className="primary-link step-button" onClick={onSubmit}>
          Simulate secure scan
        </button>
        <p className="step-note">We use this info to suggest honeypots that match your actual stack.</p>
      </div>
    </section>
  );
}

function ProgressScreen({ title, subtitle, progress, label }) {
  return (
    <section className="launch-panel glass-panel launch-step-card">
      <div className="step-header">
        <span className="step-number">{label}</span>
        <h2>{title}</h2>
        <p>{subtitle}</p>
      </div>
      <div className="simple-progress">
        <div className="simple-progress-track">
          <div className="simple-progress-thumb" style={{ width: `${progress}%` }} />
        </div>
        <div className="progress-caption">
          <span>{Math.round(progress)}%</span>
          <p>~5 seconds in this demo</p>
        </div>
      </div>
    </section>
  );
}

export default function OnboardingFlow() {
  const [phase, setPhase] = useState("source");
  const [progress, setProgress] = useState(0);
  const [fileName, setFileName] = useState(null);

  useEffect(() => {
    if (phase !== "scanning" && phase !== "connecting") {
      return undefined;
    }

    setProgress(8);
    const tick = setInterval(() => {
      setProgress((prev) => Math.min(100, prev + 6 + Math.random() * 8));
    }, 350);

    const done = setTimeout(() => {
      if (phase === "scanning") {
        setPhase("environment");
      } else if (typeof window !== "undefined") {
        window.location.href = "/dashboard";
      }
    }, 5000);

    return () => {
      clearInterval(tick);
      clearTimeout(done);
    };
  }, [phase]);

  const phaseIndex = useMemo(() => heroPhases.findIndex((entry) => entry.id === phase), [phase]);

  return (
    <div className="launch-shell">
      <div className="cyber-background" />
      <header className="landing-nav">
        <div className="brand">
          <span className="brand-logo">⛨</span>
          <div>
            <p className="brand-title">Agents of Shield</p>
            <p className="brand-subtitle">Defense Command</p>
          </div>
        </div>
        <div className="landing-nav-actions">
          <a href="/" className="ghost-link">
            Back to pitch
          </a>
          <a href="/dashboard" className="ghost-link">
            Skip to dashboard
          </a>
        </div>
      </header>

      <section className="launch-hero glass-panel">
        <div className="launch-hero-copy">
          <p className="hero-badge">AI defense workflow</p>
          <h1>Plug-and-lure defense in two simple moves.</h1>
          <p>
            Step through the same intake every small business owner sees: share code, share runtime, watch the agent spin
            up honeypots, then land in Defense Command.
          </p>
        </div>
        <div className="launch-progress">
          {heroPhases.map((step, index) => (
            <div key={step.id} className={`launch-progress-step ${index <= phaseIndex ? "is-active" : ""}`}>
              <div className="launch-progress-icon">{index + 1}</div>
              <div>
                <p className="launch-progress-label">{step.label}</p>
                <p className="launch-progress-detail">{step.detail}</p>
              </div>
            </div>
          ))}
        </div>
      </section>

      {phase === "source" && (
        <SourceStep
          fileName={fileName}
          onFileSelect={(event) => {
            const file = event.target.files?.[0];
            setFileName(file ? file.name : null);
          }}
          onNext={() => setPhase("scanning")}
        />
      )}

      {phase === "scanning" && (
        <ProgressScreen
          title="Scanning your surface."
          subtitle="Fingerprinting frameworks, package manifests, and exposed routes before we suggest decoys."
          progress={progress}
          label="Scanning"
        />
      )}

      {phase === "environment" && <EnvironmentStep onSubmit={() => setPhase("connecting")} />}

      {phase === "connecting" && (
        <ProgressScreen
          title="Connecting your agent + honeypots."
          subtitle="Wiring telemetry, mirroring traffic, and arming decoys before we hand you the dashboard."
          progress={progress}
          label="Connecting"
        />
      )}
    </div>
  );
}

