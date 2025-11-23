# Agents of Shield – Defensive Ops

Autonomous defensive stack that observes the intentionally vulnerable “Pet Grooming by Sofia” app and the “Agents of Shield Attack Agent”. The suite consists of a FastAPI-based orchestrator, modular defense agents, persistent memory, and a real-time React dashboard.

## Project Layout

```
agents-of-shield-defense/
├── orchestrator/              # FastAPI app + router + WS server
├── defense_agents/            # Modular defensive AI agents
├── state/                     # Persistent memories + honeypot state
├── reports/                   # Generated incident reports
└── dashboard/                 # Vite + React + Tailwind live UI
```

## Getting Started

1. **Install orchestrator deps**

   ```bash
   cd agents-of-shield/defense/orchestrator
   python3 -m venv .venv && source .venv/bin/activate
   pip install -r requirements.txt
   ```

2. **Run the orchestrator**
   From the agents-of-shield/defense folder:
   ```bash
   uvicorn orchestrator.orchestrator:app --reload --port 7700 --host 0.0.0.0
   ```

   - Receives attacker events via `POST http://localhost:7700/attack-event`
   - Broadcasts WebSocket updates on `ws://localhost:7700/ws` (set `VITE_WS_URL` if you relocate it)
   - Persists events to `state/attacker_events.jsonl`

3. **Start the dashboard**

   ```bash
   cd ../dashboard
   npm install
   npm run dev
   ```

   Visit `http://localhost:5173` to see pre-attack view, live feed, and summary panels.

4. **Point attacker at the orchestrator**

   Ensure the attacker agent POSTs each step to `http://localhost:7700/attack-event`. The orchestrator will route the event to every defensive agent, update honeypot memory, and stream telemetry to the dashboard.

### Bridging Cowrie SSH events into the dashboard

Run the Cowrie bridge alongside the orchestrator to mirror every honeypot line (`tpotce/data/cowrie/log/cowrie.json`) into the same `/attack-event` feed:

```bash
python defense/tools/cowrie_bridge.py
```

It tails the log, remembers its offset in `defense/state/cowrie_bridge_state.json`, and POSTs each entry with `action_type=COWRIE_*`. Override defaults if you run T-Pot elsewhere:

```bash
COWRIE_LOG_PATH=/path/to/cowrie.json \
COWRIE_BRIDGE_DEFENSE_API=http://localhost:7700 \
python defense/tools/cowrie_bridge.py
```

Leave it running to see Cowrie payloads and login attempts show up live on the dashboard.

## Defensive Agents Overview

| Agent | Purpose |
| --- | --- |
| Honeypot Manager | Tracks hits on `/admin-v2`, `/backup-db`, `/config-prod`, updates `honeypot_state.json`, emits `HONEYPOT_TRIGGERED`. |
| Network Monitor | Mirrors attacker actions, logs payloads and timings, emits `NETWORK_EVENT`. |
| Payload Analysis | Heuristically scores risk for SQLi, traversal, suspicious headers. |
| Attack Classification | Tags each step (recon, brute force, SQLi, path traversal, admin exposure, config leak, honeypot). |
| Defense Memory | Maintains `state/defense_memory.json` (patterns, suspicious endpoints, future recommendations). |
| Report Generator | Builds JSON + HTML incident reports in `reports/incident_report_<timestamp>.*`. |

## Dashboard Panels

1. **Pre-Attack View** – Honeypot inventory, system diagram, baseline status.
2. **Live Attack Feed** – WebSocket-driven stream of steps, payload risk, honeypot indicators.
3. **Post-Attack Summary** – Attack chain graph, honeypot detail, defense learnings, report download button.

## Environment Variables

Create `.env` files (loaded via `python-dotenv`) for secrets:

```
OPENAI_API_KEY=sk-...
DEFENSE_MEMORY_PATH=../state/defense_memory.json
```

## Hackathon Notes

- All components are scaffolds with clear extension points (TODO comments).
- Agents are modular Python classes to encourage rapid experimentation.
- Dashboard consumes the same WS events that the orchestrator broadcasts to logs, ensuring parity between CLI + UI views.

Happy defending! 🛡️

