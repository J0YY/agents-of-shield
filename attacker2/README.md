# Attacker 2 – Kali MCP Offensive Agent

`attacker2` is a fresh offensive agent that mirrors the autonomous loop from
`attacker/` but executes every action through the
[Kali MCP bridge](https://www.kali.org/tools/mcp-kali-server/).  
Instead of issuing HTTP requests directly, the agent launches the `mcp-server`
CLI, connects it to a running `kali-server-mcp` instance, and delegates all
reconnaissance/exploitation commands through MCP tools.

## Features
- **Full MCP bootstrapping** – optionally starts `kali-server-mcp` locally and
  always launches the CLI `mcp-server` bridge via `agents.mcp.MCPServerStdio`.
- **LLM-guided loop** – OpenAI Agents orchestrate multi-step attacks while
  persisting context in `state/memory.json`.
- **Structured outputs** – each step returns machine-parseable JSON so the loop
  can track findings, warnings, and next targets automatically.
- **Operation log** – step transcripts persist to
  `state/operations.jsonl` for later replay/debugging.

## Requirements
1. Python 3.11+ (same interpreter as the root project).
2. `OPENAI_API_KEY` exported in the environment.
3. `pip install -r requirements.txt`
4. Access to the Kali MCP tooling:
   - `kali-server-mcp` (APT package on Kali/WSL) or a remote host exposing it.
   - `mcp-server` CLI (included with the package) available on `$PATH`.

> 💡 If you do not run Kali locally, point `KALI_MCP_SERVER_URL` at a remote
> bridge where `kali-server-mcp` is already running.

## Quickstart
```bash
cd /Users/joyyang/Projects/agents-of-shield/attacker2
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
export OPENAI_API_KEY=sk-...
export ATTACKER2_TARGET_BASE="http://localhost:3000"
# Optional: automatically launch the HTTP bridge locally
export KALI_MCP_AUTO_START=1
python agent_attack.py
```

During execution you will see each step, the MCP commands that ran, findings,
warnings, and the updated queue of next targets. Memory persists between runs.

## Configuration

| Variable | Default | Description |
| --- | --- | --- |
| `ATTACKER2_TARGET_BASE` | `http://localhost:3000` | Base URL for the vulnerable app. |
| `ATTACKER2_MAX_STEPS` | `8` | Max loop iterations. |
| `ATTACKER2_MODEL` | `OPENAI_ATTACK_MODEL` or `gpt-4o-mini` | LLM used for orchestration. |
| `KALI_MCP_SERVER_URL` | `http://127.0.0.1:5000` | URL of the running `kali-server-mcp`. |
| `KALI_MCP_AUTO_START` | `0` | When `1`, spawn `kali-server-mcp` locally. |
| `KALI_MCP_API_COMMAND` | `kali-server-mcp` | Override path to the API binary. |
| `KALI_MCP_CLIENT_COMMAND` | `mcp-server` | Override the CLI MCP client. |
| `KALI_MCP_CLIENT_TIMEOUT` | `300` | Seconds before MCP client times out. |

## Architecture Overview

```
agent_attack.py
  ├─ kali_mcp/session.py        # starts/stops Kali MCP processes
  ├─ memory.py                  # persists step summaries + findings
  ├─ prompts/kali_mcp_attacker  # system prompt for the agent
  └─ state/                     # memory + operations log
```

1. `KaliMCPSession` optionally boots the HTTP API, then launches the CLI client
   via `MCPServerStdio`, exposing its tools to the LLM.
2. The agent prompt enforces that every step must call at least one MCP tool and
   must return JSON summarizing `commands_executed`, `findings`, etc.
3. Each iteration builds a task string with memory context, runs the agent, then
   records both the structured JSON and raw output into persistent storage.

## Troubleshooting
- **`FileNotFoundError: 'mcp-server'`** – ensure the Kali MCP package is
  installed and the CLI binary is on your `$PATH`.
- **Timeout waiting for port** – when `KALI_MCP_AUTO_START=1`, the script waits
  for the API to open its TCP port. Increase `KALI_MCP_API_PORT`/`SERVER_URL`
  or start the service manually.
- **Agent refuses to run commands** – confirm the MCP tools are listed when the
  agent starts; the CLI prints tool metadata to stderr if `--debug` is enabled.

All persistent artifacts live in `attacker2/state/`.

