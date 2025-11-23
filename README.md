# ⭐ Agents of Shield — Push-Button Enterprise Defense for Small Teams

*def/acc Hackathon • London • Nov 21–23, 2025 *

---

# 🚀 Democratizing Defense

LLM-powered botnets can now sweep thousands of vibe-coded apps in minutes. Founders without security teams have become high-ROI targets, yet enterprise tools are still locked behind six-figure deployments.

**Agents of Shield** delivers the opposite experience: plug-and-lure protection that behaves like an elite SOC, but is packaged for a two-person startup. We read your repo, drop in a lightweight agent, light up honeypots, and run a hosted “Defense Command” so you see attacks — and misdirect them — in real time.

![1b (1)](https://github.com/user-attachments/assets/e483c763-462e-4b3d-8287-b9b8060fd179)


---

# 🧰 Super-Simple, Self Hosted (Fully Scalable!) Setup

* User uploads their GitHub/GitLab link or zip so we can parse frameworks, routes, and package manifests  
* Minimal infra details: hosting surface (Render, Fly.io, EC2, etc.), datastore flavor, and optionally a read-only log/API key  
* Optional Cloudflare/DNS access if they want auto-issued decoy subdomains

That’s it. No SIEM plumbing, no security headcount.

---

# 🎯 What We Deliver Back

* **Hosted Defense Command** — zero-setup dashboard with radar scans, live attack feed, and remediation nudges  
* **Drop-in mirror agent** (Express middleware, Django app, or reverse proxy module) that clones traffic, streams attack_log.json, and surfaces decoys like `/admin-v2`, `/backup-db`, `/printer-queue` automatically  
* **Click-to-deploy honeypots** — fake admin consoles, backup zips, config dumps, printer queues — each with detectors, payload capture, and funnels for follow-up  
* **Alerting fabric** — email, Slack, or LLM summaries (“Botnet-from-VN hit /download-db; Honey DB triggered, payload captured…”)  
* **Enterprise playbook, democratized** — tuned to tireless, automated adversaries so founders can stay focused on shipping

---

# 🔄 Flow in Three Steps

1. **Founder links the repo or log source** — scanner ingests frameworks, routes, and dependency fingerprints.  
2. **Defense Command animates a radar sweep** — highlights exploitable surfaces, recommends honeypots tailored to their code, and shows live attacker hits.  
3. **One-click deployment** — suggested decoys ship via our agent or our hosted reverse proxy. Alerts follow, along with a structured report for investors, auditors, or judges.

---

# 🧱 System Architecture

```
            ┌──────────────────────────────┐
            │ Vulnerable Web App           │
            │ (Pet Grooming by Sofia)      │
            └──────────────┬───────────────┘
                           │ mirrored traffic
                           ▼
            ┌──────────────────────────────┐
            │ Mirror Agent                 │
            │ (Express / Django / proxy)   │
            └──────────────┬───────────────┘
                           │ attack events + decoy hits
                           ▼
            ┌──────────────────────────────┐
            │ Defense Command Orchestrator │
            └──────┬────────┬────────┬─────┘
                   │        │        │
   ┌───────────────▼──┐ ┌───▼────────▼───┐ ┌───────────────▼──────┐
   │ Honeypot Agent    │ │ Obfuscation     │ │ Investigation Agent  │
   │ (decoys & lures)  │ │ Agent           │ │ + Report Generator   │
   └───────────────┬───┘ └────────────────┘ └───────────────┬──────┘
                   │                                        │
                   ▼                                        ▼
       ┌──────────────────────┐                   ┌───────────────────────┐
       │ Hosted honeypots     │                   │ Defense Command UI    │
       │ & decoy subdomains   │                   │ + Slack/Email/LLM bots│
       └──────────────────────┘                   └───────────────────────┘
```

Founders see attacker pressure heatmaps, token cost asymmetry plots, and recommended fixes instantly — no terminal spelunking required.

---

# 🧠 Why This Matters

* **AI-native offense** — Automated recon + exploitation loops are cheap; we raise their cost curve by feeding them believable traps and throttling their context.  
* **Security without a security team** — Attach the repo, drop in our middleware, and defense shows up as a hosted experience.  
* **Defensive acceleration** — Every honeypot hit adds training data for our investigation agent, shrinking response time and improving detection without human toil.  
* **Scales with founders, not headcount** — Agents don’t sleep, instrumentation is scripted, and the same pipeline can safeguard hundreds of small shops.

---

# 🧩 Core Modules

* **Vulnerable small-business sandbox** — “Pet Grooming by Sofia” replicates the messy stack we’re protecting: plaintext creds, debug routes, leaked API keys, path traversal bugs, etc.  
* **LLM Red Team** — Attacker that scans, generates payloads, iterates scripts, tries to SSH in, and benchmarks our defenses. Strictly sandboxed for ethical testing.  
* **Honeypot Generator** — Fabricates admin panels, database dumps, backup zips, and config leaks with embedded detectors to capture payloads and dial up attacker token spend.  
* **Obfuscation & Flow Agent** — Dynamically rotates routes, injects delays, and modulates responses to jam automated scripts.  
* **Investigation + Report Agent** — Classifies each attempt (SQLi, XSS, auth bypass, etc.), scores severity, recommends mitigations, and compiles PDF/HTML evidence with token economics.  
* **Defense Command UI** — Radar scan, live logs, honeypot toggles, and alert routing in one place.

---

# 📊 Token Economics Snapshot

We track every prompt and response for both attacker and defender. Honeypots and obfuscation deliberately increase attacker token spend while keeping defender analysis flat — showcasing the defensive cost asymmetry judges care about.

---

# 📂 Repository Map
```
/
├── vulnerable-app/              # Pet Grooming by Sofia sandbox
├── attacker-agent/              # LLM attacker scripts & prompts
├── defense-orchestrator/        # Routes telemetry to agents
├── defensive-agents/
│   ├── honeypot-generator/
│   ├── obfuscation-agent/
│   ├── investigation-agent/
│   └── report-generator/
├── defense/dashboard/           # Defense Command frontend
├── attack_logs/                 # attack_log.json artifacts
├── reports/                     # PDF/HTML security reports
├── plots/                       # Token usage + heatmaps
└── README.md
```

---

# ▶️ Quickstart (Hackathon Demo Flow)

1. **Boot the vulnerable app**
```
cd vulnerable-app
npm install
node server.js
```
2. **Start the orchestrator + agents**
```
cd defense-orchestrator
npm install
node index.js
```
3. **Launch the LLM attacker**
```
python attacker-agent/attack_loop.py
```
4. **Open Defense Command**
```
cd defense/dashboard
npm install
npm run dev
```
5. **Review reports & alerts**
```
open reports/latest_report.html
```

---

# ⚖️ Ethics & Safety

All offensive tooling stays inside this sandbox and exists solely to benchmark defenses. We do not encourage or support real-world exploitation. If you adapt this code, only target systems you own and operate.

---

# 🙌 Credits

Built for the def/acc hackathon in London by Team Security Track to demonstrate that enterprise-grade defense can be push-button accessible for every founder.
