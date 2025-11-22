# Agents of Shield – Attack Agent

An autonomous, LLM-driven red-team bot that continuously probes the intentionally vulnerable “Pet Grooming by Sofia” app at `http://localhost:3000`. The agent observes only HTTP responses, maintains its own internal memory, and loops through a cognition pipeline of **Perception → World Model → Planner** to decide each next step.

## Features
- Fully black-box: no code introspection, only raw HTTP bodies.
- Three-agent cognition loop backed by OpenAI models.
- Structured memory persisted to `state/memory.json` between runs.
- Dynamic payload generation (SQLi, traversal, backup probing) guided by planner prompts.
- Terminal-style output with color-coded step summaries for demos.

## Quickstart
```bash
export OPENAI_API_KEY=yourkey
cd /Users/joyyang/Projects/agents-of-shield/agents-of-shield-attacker
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
python agent_attack.py
```
(Optional) set `OPENAI_ATTACK_MODEL` to override the default `gpt-4o-mini`.

## Architecture
```
agent_attack.py  # orchestrates 20-step loop
  ├── agents/perception.py    # extracts links/forms/errors from responses
  ├── agents/world_model.py   # updates persistent memory + goals
  ├── agents/planner.py       # selects next HTTP action JSON
  ├── utils/http_executor.py  # runs GET/POST with truncation
  └── state/memory.json       # evolving knowledge base
```
Prompts for each LLM role live in `prompts/` so you can tune behavior easily.

## Example Output
```
============================================================
     Agents of Shield – Attack Agent
     autonomous offensive ops demo
============================================================
Using OpenAI model: gpt-4o-mini

──────────── STEP 3 ────────────
ACTION: GET http://localhost:3000/admin
STATUS: 200
SUMMARY: Exposed admin table with plaintext passwords.
NEXT-GOALS: ['dump_db', 'download_db_file']
──────────────────────────────
```
(The real run continues for 20 steps, showing payloads and reasoning along the way.)

## Safety & Containment
- Only targets `http://localhost:3000` and times out after 5 seconds per request.
- Stores every bit of memory in `state/memory.json` for auditability.
- Designed for local hackathon demos; disable or air-gap before pointing at anything sensitive.
