# ⭐ **Agents of Shield: Autonomous Defensive Agents for Web App Security**

*A def/acc hackathon project (London, Nov 21–23, 2025)*
**Team: Security Track**

---

# 🚀 Overview

**Agents of Shield** is a proof-of-concept defensive AI system designed to protect vulnerable web applications from *LLM-enabled attackers*.
We build:

* A deliberately hackable **vibe-coded small business web app**
* A **simulated AI attacker** that uses an LLM to produce scripts & payloads
* A suite of **autonomous defensive agents** that detect, investigate, misdirect, and analyze attacks in real time
* A final **automated security report**, including a visualization of token consumption on both sides

The aim is to explore how defensive AI can keep pace with — and ideally *stay ahead of* — automated attackers that are increasingly empowered by large foundation models.

This project directly aligns with the **defensive acceleration (def/acc)** mission: *accelerate defensive technologies faster than offensive ones and build societal resilience against AI-enabled threats.*

---

# 🧠 Motivation

Small businesses and independent developers increasingly rely on “vibe-coded,” quick-to-deploy web apps — often built without security expertise. Unfortunately:

* These apps are **highly vulnerable**
* Attackers now have access to **LLMs that generate exploits automatically**
* Traditional security tools are too heavy, slow, or expensive for most small teams

Meanwhile, LLM attackers can perform:

* Instant directory enumeration
* Automated SQL injection crafting
* Script orchestration
* Credential-stuffing logic
* Multi-step exploitation loops

**We are entering a world where automated offensive cyber capability is free and nearly limitless.**

*But defensive capability is not.*
This project seeks to close that gap.

---

# ✨ Vision

Our team asked:

> **What does web security look like in a world where attackers are LLM agents?**

And:

> **Can defensive agents meet attackers at their own speed — or faster?**

Our vision:
**defensive agents that act autonomously, adaptively, and creatively**, working alongside or *in place of* human security engineers.

This project demonstrates the early prototype of such a system.

---

# 🛡️ Core Components

The system consists of four major layers:

---

## **1. Vulnerable Web App (Sandbox Target)**

We built a deliberately vulnerable “small business” app:
**Pet Grooming by Sofia** — a typical vibe-coded service website.

It includes intentionally insecure features:

* Plaintext password storage
* SQL injection points
* Exposed /debug and /env routes
* Frontend JS leaking API keys
* Insecure admin panel with no auth
* Path traversal vulnerabilities
* Honeypot endpoints that seem real

This reflects exactly the type of software that:

* Solo founders
* Students
* Small shops
* Local services
  …often deploy.

The web app provides a realistic attack surface for our agents.

---

## **2. AI Attacker (Simulated Adversary)**

This is a fully autonomous LLM-powered attacker that:

* Scans the app
* Generates exploitation payloads
* Writes Python/Node/cURL scripts to run
* Attempts SQLi, path traversal, credential guessing
* Iteratively refines its strategies
* Explores the vulnerable attack surface

We do *not* encourage real malicious use.
This attacker exists solely to benchmark our defensive system.

---

## **3. Defensive Agent Suite (Main Innovation)**

### 🔷 **Honeypot Generator Agent**

Generates fake:

* admin panels
* database dumps
* backup routes
* configuration files

Used to:

* waste attacker cycles
* misdirect automated exploit loops
* collect high-signal telemetry on attacker behavior

---

### 🔶 **Obfuscation Agent**

Introduces dynamic obstacles:

* rotates endpoint names
* injects timing delays
* modulates responses
* scrambles HTML comments
* disables certain routes on the fly

Goal:
Increase attacker token cost, reduce defender token cost.

---

### 🟩 **Anti-Phishing / Payload Sanitizer**

Analyzes suspicious inbound content:

* rewrites dangerous HTML
* detects injection attempts
* sanitizes or neutralizes scripts
* warns investigation agent

---

### 🟥 **Attack Investigation Agent**

Classifies and analyzes each attack:

* SQLi / XSS / CSRF / auth bypass / enumeration
* Attack severity scoring
* Whether exploit succeeded
* What data would have been compromised
* Recommended fixes

Each attempt is logged as structured JSON, e.g.:

```json
{
  "attack_type": "SQL Injection",
  "payload": "' OR 1=1 --",
  "severity": "high",
  "endpoint": "/login",
  "was_successful": false,
  "recommended_fix": "Use parameterized queries"
}
```

---

### 🟪 **Security Report Generator Agent**

Creates:

* An automated security report
* A timeline of attacks
* A taxonomy of exploit attempts
* Visualizations (heatmap & token-usage plot)
* Executive summary

**This is what judges will see during your demo.**

---

## **4. Orchestrator (Agent Router)**

A small backend layer that:

* Receives attacker actions
* Routes them to defensive agents
* Collects outputs
* Updates the global attack log
* Produces the PDF/HTML final report

This is the "brain" that ties the entire system together.

---

# 🧩 Technical Architecture

```
            ┌──────────────────────────────┐
            │ Vulnerable Web App           │
            │ (Pet Grooming by Sofia)      │
            └──────────────┬───────────────┘
                           │
                           ▼
            ┌──────────────────────────────┐
            │ AI Attacker Agent            │
            │ (LLM ⇨ payloads/scripts)     │
            └──────────────┬───────────────┘
                           │ attack events
                           ▼
            ┌──────────────────────────────┐
            │ Orchestrator                 │
            │ (routes to defense agents)   │
            └──────┬────────┬────────┬─────┘
                   │        │        │
   ┌───────────────▼──┐ ┌───▼────────▼───┐ ┌───────────────▼──────┐
   │ Honeypot Agent    │ │ Obfuscation     │ │ Investigation Agent  │
   └───────────────┬───┘ │ Agent           │ └───────────────┬──────┘
                   │     └────────────────┘                 │
                   ▼                                        ▼
       ┌──────────────────────┐                   ┌───────────────────────┐
       │ Honeypot endpoints   │                   │ Security Report Agent │
       └──────────────────────┘                   └───────────────────────┘
```

---

# 🧪 Experimental Result: Token Usage Plot

One of the novel aspects of this project is an **economic framing of cyber offense vs defense**:

> How many tokens does an attacker spend vs how many tokens a defender must spend to identify, classify, and mitigate?

We produce a graph showing:

* Defender token cost stays roughly constant
* Attacker token cost grows significantly due to honeypots & misdirection

This is a **defensive cost asymmetry** — the holy grail of defensive AI.

---

# 🏆 Why This Project Matters (Impact)

## **1. AI attackers change the game**

LLMs dramatically reduce the skill level required to launch cyberattacks.

This is inevitable.
Defensive acceleration is about meeting this reality with resilient infrastructure.

---

## **2. Small organizations are the most at-risk**

Most security breaches don’t happen at Fortune 500 companies.
They happen to:

* individuals
* small shops
* side projects
* local businesses

Our system protects them.

---

## **3. Defensive agents scale infinitely**

Unlike human security engineers, defensive agents:

* never sleep
* never forget
* operate 24/7
* scale cheaply
* adapt instantly

This is how we democratize safety.

---

## **4. This approach shifts security left**

Instead of securing apps *after* they are deployed, our system:

* identifies misconfigurations immediately
* deploys honeypots in minutes
* logs attempts right away

Defense becomes embedded, autonomous, and proactive.

---

## **5. This project is the beginning of a whole new paradigm**

A world where:

* web apps defend themselves
* attackers waste compute in infinite honeypots
* automated agents generate actionable reports
* security becomes composable and model-driven

This aligns deeply with the def/acc vision.
**Build defensive technologies so powerful and ubiquitous that offense becomes uncompetitive.**

---

# 📦 Repository Structure

```
/
├── vulnerable-app/              # Intentionally hackable web app
├── attacker-agent/              # LLM attacker scripts & prompts
├── defense-orchestrator/        # Router for all defensive actions
├── defensive-agents/
│   ├── honeypot-generator/
│   ├── obfuscation-agent/
│   ├── investigation-agent/
│   └── report-generator/
├── attack_logs/                 # Logged events
├── reports/                     # Final security reports (PDF/HTML)
├── plots/                       # Token-usage visualizations
└── README.md                    # (this file)
```

---

# 🧪 How to Run (High-Level)

**1. Start the vulnerable web app**

```
cd vulnerable-app
npm install
node server.js
```

**2. Start the orchestrator**

```
cd defense-orchestrator
npm install
node index.js
```

**3. Run attacker agent**

```
python attack_loop.py
```

**4. View logs & generated report**

```
open reports/latest_report.html
```

---

# ⚠️ Ethics & Safety Disclaimer

This project is meant for:

* academic demonstration
* defensive research
* hackathon prototyping

It is *not* intended for real-world exploitation.

All attack demonstrations occur only in our contained sandbox environment.

---

# 🙌 Acknowledgments

Built during the **def/acc hackathon – London, 2025**, with the mission of accelerating AI safety and building a resilient future for humanity.

---