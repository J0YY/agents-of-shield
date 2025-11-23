import { Fragment } from "react";

const heroStats = [
  { label: "LLM attack bursts / indie app", value: "3x daily" },
  { label: "Deploy time with agent", value: "3 minutes" },
  { label: "Decoy templates live", value: "8+" },
];

const heroPanels = [
  {
    title: "AI containment",
    badge: "Sandbox",
    detail: "Let autonomous attackers live inside believable decoys while prod stays cold.",
    theme: "cyan",
  },
  {
    title: "Defense that scales",
    badge: "Serverless",
    detail: "Spin up fake twins of every critical surface with copy-on-write storage + per-tenant keys.",
    theme: "violet",
  },
  {
    title: "Signal, not panic",
    badge: "LLM briefings",
    detail: "Realtime summaries translate payloads into downtime, billing, and Stripe risk for founders.",
    theme: "amber",
  },
];

const trustedBy = ["Retool", "Outfront", "DoorDash", "BCG X", "Meta", "Stripe Labs"];

const stackTabs = ["Next.js", "Drizzle", "Prisma", "Django", "FastAPI", "Rails", "Go"];

const stackSnippet = [
  'import { deployDefense } from "@aos/serverless";',
  "",
  "export async function POST(req) {",
  "  const payload = await req.json();",
  "  const agent = await deployDefense({",
  '    repo: payload.repo,',
  '    runtime: payload.runtime,',
  "    telemetry: payload.telemetry,",
  "  });",
  "",
  "  const radar = await agent.scanSurface(\"/admin\");",
  "  await agent.armDecoy({ preset: \"phantom-admin\" });",
  "  await agent.notify({ channel: \"slack\", payload: radar });",
  "",
  "  return Response.json({ protected: true });",
  "}",
];

const terminalLines = [
  "➜  ingest cloning github.com/pet-grooming/app ...",
  "→  detected Express + SQLite · attack_log stream wired",
  "→  LLM swarm: 1,320 req/min vs /download-db /backup-db",
  "→  honeypots armed: phantom-admin, honey-db, config-mirage",
  "✓  slack://#security notified · Stripe risk now green",
];

const incentives = [
  {
    title: "Stop downtime (money on fire)",
    detail: "LLM attackers spike CPU, corrupt databases, lock admin panels, and trigger rate limits that suffocate real customers.",
    pitch: "“Our tool stops the automated attacks that take your site offline and cost you sales.”",
  },
  {
    title: "Protect Stripe & PayPal",
    detail: "Payment processors freeze accounts after suspicious flows or fraud spikes—no transactions, no revenue.",
    pitch: "“Honeypots catch attackers before they reach anything that would get your Stripe/PayPal account flagged.”",
  },
  {
    title: "Qualify for cyber insurance",
    detail: "Underwriters now ask for logging, decoys, and incident response before issuing sane premiums.",
    pitch: "“Use our product → show required controls → keep premiums low instead of getting rejected.”",
  },
  {
    title: "Rein in cloud bills",
    detail: "Mass recon spins up extra containers, bandwidth, and logs—hundreds in surprise charges after a single weekend.",
    pitch: "“Our decoy endpoints block the traffic that makes your services scale unnecessarily.”",
  },
  {
    title: "Clear audits + app stores",
    detail: "Even solo devs face GDPR/CCPA/PCI clauses plus vendor questionnaires that expect real telemetry.",
    pitch: "“Secure enough to pass audits without hiring a security team.”",
  },
  {
    title: "Protect reputation & churn",
    detail: "Customers only notice outages, leaks, and phishing. Trust evaporates faster than you can ship fixes.",
    pitch: "“Security = trust = conversion. A safe app keeps paying users.”",
  },
  {
    title: "Neutralize nonstop LLM bots",
    detail: "Automated agents never sleep and target you because you are small, not because you are interesting.",
    pitch: "“Let the attackers waste their time in our sandbox, not your real system.”",
  },
  {
    title: "Set it and forget it",
    detail: "Founders are allergic to toil—security must feel like flipping a switch.",
    pitch: "“Enterprise security → zero effort. No setup, no expertise, one-click protection.”",
  },
];

const founderBeliefs = [
  {
    myth: "“We’re too small to target.”",
    reality: "LLM botnets scan for weak apps in bulk; being small makes you the cheapest, highest-ROI target.",
  },
  {
    myth: "“If we get hacked, it’s embarrassing but not fatal.”",
    reality: "Downtime, frozen payments, and churned users stack real revenue losses within hours.",
  },
  {
    myth: "“Security is expensive and not my job.”",
    reality: "Enterprise-grade defense now runs as a managed agent + dashboard—cheaper than a single outage.",
  },
  {
    myth: "“Our users losing data ≠ us losing money.”",
    reality: "Leaks trigger refunds, fines, search downgrades, and insurance hikes that hit cash flow immediately.",
  },
];

const customerInputs = [
  { title: "Source of truth", detail: "GitHub/GitLab link (or zip) so we read frameworks, routes, and package manifests." },
  {
    title: "Runtime snapshot",
    detail: "Hosting tier + datastore so agents know how to branch your prod environment into believable mirrors.",
  },
  {
    title: "Telemetry tap",
    detail: "Optional read-only API key or log feed so we detect LLM scanners without touching prod data.",
  },
  {
    title: "Perimeter knobs",
    detail: "DNS/Cloudflare access if you want us to auto-provision decoy subdomains + SSL in your tenant.",
  },
];

const deliverables = [
  {
    title: "Defense Command (hosted)",
    bullets: [
      "Enterprise telemetry—radar, live logs, honeypot status—down to each payload an LLM drops.",
      "No SOC required: browser dashboard + per-tenant auth tokens do the heavy lifting.",
    ],
  },
  {
    title: "Drop-in Agent",
    bullets: [
      "Middleware for Express/Django/Rails that mirrors traffic, writes attack_log.json, and injects decoys.",
      "Hosted reverse proxy when teams can’t modify brittle monoliths.",
    ],
  },
  {
    title: "Click-to-deploy honeypots",
    bullets: [
      "Fake admin portals, backup downloaders, config dumps, printer queues, SMTP relays.",
      "Each preset routes attackers into detectors + payload funnels so real systems stay boring.",
    ],
  },
  {
    title: "Automated reporting",
    bullets: [
      "LLM summaries translate incidents into downtime, billing, and compliance impact.",
      "One-click packets for insurers, auditors, or customer updates.",
    ],
  },
];

const flowSteps = [
  { title: "Link code or logs", detail: "Founder signs in, connects GitHub or attack logs, and we fingerprint real routes." },
  { title: "Watch AI attackers hit decoys", detail: "Scanner lights up radar + timeline so you see what LLM bots try in real time." },
  { title: "One-click deploy", detail: "Accept the recommended honeypots—agent or hosted proxy branches prod instantly." },
  { title: "Stay ahead with alerts", detail: "Slack/email/LLM digests explain what was attempted, what we trapped, and what to patch." },
];

const roadmap = [
  "Managed SaaS API with per-tenant auth + zero-config onboarding.",
  "CLI / GitHub App that auto-injects middleware and honeypot presets.",
  "Hosted telemetry sink (S3/Supabase) with HTTPS ingestion + retention policies.",
  "Docker / Heroku button for the orchestrator (no manual uvicorn).",
  "Framework adapters for Flask, FastAPI, Rails, Laravel, and more.",
  "Automated remediation hints alongside every vulnerable surface.",
  "Multi-tenant billing, seat controls, and exportable incident packets.",
];

const marketingBullets = [
  "LLM attackers operate at botnet scale. Indie founders finally have a countermeasure.",
  "Enterprise-grade honeypots, packaged so a one-person team can deploy in minutes.",
  "Turn mass exploitation into a dead end by letting bots waste days in our sandbox.",
];

const heroParticles = Array.from({ length: 12 }, (_, index) => index);

export default function LandingPage() {
  return (
    <div className="landing-shell">
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
          <a href="/launch" className="ghost-link">
            Try the workflow
          </a>
          <a href="#waitlist" className="primary-link">
            Join waitlist
          </a>
        </div>
      </header>

      <section className="hero-stage glass-panel">
        <div className="hero-matrix" />
        <div className="hero-holo hero-holo--one" aria-hidden="true" />
        <div className="hero-holo hero-holo--two" aria-hidden="true" />
        <div className="hero-sparks" aria-hidden="true">
          {heroParticles.map((particle) => (
            <span key={`spark-${particle}`} style={{ "--i": particle }} />
          ))}
        </div>
        <div className="hero-copy">
          <p className="hero-badge">AI safety for indie infra</p>
          <h1>Agents of Shield</h1>
          <p className="hero-subheadline">
            LLM-powered attackers now scan thousands of weak apps a minute. We democratize enterprise defense so founders without a security team stay online.
          </p>
          <div className="hero-actions">
            <a href="/launch" className="primary-link">
              Set up your defense
            </a>
            <a href="/dashboard" className="ghost-link">
              See the flow
            </a>
          </div>
          <div className="hero-metrics">
            {heroStats.map((stat) => (
              <div key={stat.label} className="hero-metric">
                <p className="hero-stat-value">{stat.value}</p>
                <p className="hero-stat-label">{stat.label}</p>
              </div>
            ))}
          </div>
          <p className="hero-context">
            Attackers use AI to scale offense. Agents of Shield scales defense faster—turning every small business into an AI safety win.
          </p>
        </div>

        <div className="hero-canvas">
          <div className="hero-radar-card floating-card delay-1">
            <div className="radar-grid radar-grid--hero">
              <div className="radar-beam" />
              <div className="radar-pulse" />
            </div>
            <p className="radar-caption">We scan and place decoys for your small business in seconds.</p>
          </div>
          <div className="hero-terminal-card floating-card delay-2">
            <div className="terminal-header">
              <span className="dot red" />
              <span className="dot yellow" />
              <span className="dot green" />
              <span className="terminal-title">founder@defense:~</span>
            </div>
            <div className="terminal-body">
              {terminalLines.map((line) => (
                <p key={line} className="terminal-line">
                  {line}
                </p>
              ))}
            </div>
          </div>
          <div className="hero-panel-stack">
            {heroPanels.map((panel) => (
              <article key={panel.title} className={`hero-panel hero-panel--${panel.theme}`}>
                <p className="hero-panel-badge">{panel.badge}</p>
                <h3>{panel.title}</h3>
                <p>{panel.detail}</p>
              </article>
            ))}
          </div>
        </div>
      </section>

      <section className="trust-section glass-panel">
        <div>
          <p className="section-pill">Trusted in production</p>
          <h2>Proof that AI safety isn’t just for the big clouds.</h2>
          <p>Teams ship us their code because they need enterprise containment without enterprise headcount.</p>
        </div>
        <div className="trust-logos">
          {trustedBy.map((logo) => (
            <span key={logo}>{logo}</span>
          ))}
        </div>
      </section>

      <section className="landing-section glass-panel split-section kinetic-panel">
        <div className="why-left">
          <div className="section-heading">
            <p className="section-pill">Now...</p>
            <h2>Why should you care?</h2>
            <p>90% of today’s small businesses ship code and deploy web apps. Security lands only when it protects uptime, payments, and cost.</p>
          </div>
          <ul className="belief-list">
            {founderBeliefs.map((item) => (
              <li key={item.myth} className="belief-item">
                <p className="belief-myth">{item.myth}</p>
                <p className="belief-reality">{item.reality}</p>
              </li>
            ))}
          </ul>
        </div>
        <div className="why-right">
          <div className="grid-aurora" aria-hidden="true" />
          <div className="landing-grid incentives-grid">
            {incentives.map((item) => (
              <article key={item.title} className="landing-card incentive-card">
                <h3>{item.title}</h3>
                <p>{item.detail}</p>
                <p className="incentive-pitch">{item.pitch}</p>
              </article>
            ))}
          </div>
        </div>
      </section>

      <section className="landing-section glass-panel">
        <div className="section-heading">
          <p className="section-pill">What you plug in</p>
          <h2>Minimal inputs → full AI attack containment.</h2>
        </div>
        <div className="landing-grid grid-2">
          {customerInputs.map((card) => (
            <article key={card.title} className="landing-card">
              <p className="landing-card-title">{card.title}</p>
              <p className="landing-card-body">{card.detail}</p>
            </article>
          ))}
        </div>
      </section>

      <section className="landing-section glass-panel stack-section kinetic-panel">
        <div>
          <p className="section-pill">Works with your stack</p>
          <h2>Defense that scales faster than the attackers.</h2>
          <p>Drop the orchestrator next to your API or let us host the whole thing. Framework adapters keep pace with whatever your LLM agents built.</p>
          <div className="stack-tabs">
            {stackTabs.map((tab) => (
              <span key={tab}>{tab}</span>
            ))}
          </div>
        </div>
        <div className="stack-console spectral-console">
          <div className="stack-console-header">
            <span className="dot green" />
            <span className="dot yellow" />
            <span className="dot red" />
            <p>agents-of-shield/app/api/defense.ts</p>
          </div>
          <pre className="stack-console-body">
            {stackSnippet.map((line, index) => (
              <code key={`${index}-${line}`}>{line || "\u00a0"}</code>
            ))}
          </pre>
        </div>
      </section>

      <section className="landing-section glass-panel">
        <div className="section-heading">
          <p className="section-pill">What you get</p>
          <h2>Enterprise-grade honeypots, finally accessible.</h2>
        </div>
        <div className="landing-grid grid-2">
          {deliverables.map((item) => (
            <article key={item.title} className="landing-card deliverable-card">
              <p className="landing-card-title">{item.title}</p>
              <ul>
                {item.bullets.map((line) => (
                  <li key={line}>{line}</li>
                ))}
              </ul>
            </article>
          ))}
        </div>
      </section>

      <section id="flow" className="landing-section">
        <div className="section-heading">
          <p className="section-pill">How it works</p>
          <h2>From repo link to AI-safe honeypots in four moves.</h2>
        </div>
        <div className="landing-timeline">
          {flowSteps.map((step, index) => (
            <Fragment key={step.title}>
              <div className="timeline-node">
                <span>{index + 1}</span>
                <div>
                  <p className="timeline-title">{step.title}</p>
                  <p className="timeline-detail">{step.detail}</p>
                </div>
              </div>
              {index < flowSteps.length - 1 && <div className="timeline-connector" />}
            </Fragment>
          ))}
        </div>
      </section>

      <section className="landing-section glass-panel">
        <div className="section-heading">
          <p className="section-pill">Roadmap</p>
          <h2>Everything we’re shipping to keep scaling defense for the little guys.</h2>
        </div>
        <div className="landing-grid grid-2">
          <article className="landing-card">
            <p className="landing-card-title">In progress</p>
            <ul>
              {roadmap.slice(0, 4).map((item) => (
                <li key={item}>{item}</li>
              ))}
            </ul>
          </article>
          <article className="landing-card">
            <p className="landing-card-title">Next up</p>
            <ul>
              {roadmap.slice(4).map((item) => (
                <li key={item}>{item}</li>
              ))}
            </ul>
          </article>
        </div>
      </section>

      <section className="landing-section">
        <div className="section-heading">
          <p className="section-pill">Why it matters</p>
          <h2>LLM attackers don’t sleep—your defense shouldn’t either.</h2>
        </div>
        <div className="landing-grid grid-3">
          {marketingBullets.map((line) => (
            <article key={line} className="landing-quote">
              <p>{line}</p>
            </article>
          ))}
        </div>
      </section>

      <section id="waitlist" className="cta-bar glass-panel">
        <div>
          <p className="section-pill">Founders’ edition</p>
          <h3>Enterprise-grade cybersecurity for small businesses and indie founders. AI-powered honeypots that waste attackers’ time—not yours.</h3>
        </div>
        <div className="cta-actions">
          <a href="mailto:defense@agentsofshield.dev" className="primary-link">
            Request early access
          </a>
          <a href="/launch" className="ghost-link">
            Go
          </a>
        </div>
      </section>
    </div>
  );
}
