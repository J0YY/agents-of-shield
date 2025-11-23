# Attacker2: How It Works and Honeypot Interaction

## 🎯 Goal of Attacker2

**Attacker2** is an autonomous red-team agent designed to:
1. **Attack the vulnerable web application** (`http://localhost:3000` by default)
2. **Execute reconnaissance and exploitation** using real Kali Linux tools
3. **Interact with honeypots** that the defense system deploys
4. **Demonstrate how attackers can be lured into honeypot traps**

The agent is designed to be **unaware** that certain endpoints are honeypots - it treats them as legitimate targets, which is exactly how real attackers behave.

---

## 🏗️ How Attacker2 Works

### Architecture Overview

```
┌─────────────────────────────────────────────────────────┐
│  agent_attack.py (Main Loop)                            │
│  ├─ Kali MCP Session (kali_mcp/session.py)             │
│  │  └─ Connects to kali-server-mcp (Kali tools bridge)  │
│  ├─ Memory System (memory.py)                           │
│  │  └─ Persists findings, targets, steps                │
│  └─ Specialist Agents                                   │
│     ├─ WebProbe (WEB channel)                            │
│     └─ SystemSweep (SYSTEM channel)                     │
└─────────────────────────────────────────────────────────┘
         │
         ├─→ Executes via MCP tools (curl, nmap, etc.)
         ├─→ Queries defense API for active honeypots
         └─→ Reports attack events back to defense
```

### Key Components

#### 1. **Kali MCP Integration** (`kali_mcp/session.py`)
- Connects to `kali-server-mcp` which exposes Kali Linux tools (curl, nmap, gobuster, etc.)
- All commands must go through MCP tools - no direct shell access
- Provides a safe sandbox for running offensive tools

#### 2. **Memory System** (`memory.py`)
- **Persists state** between runs in `state/memory.json`
- Tracks:
  - **Steps**: All attack steps executed
  - **Findings**: Discovered endpoints, vulnerabilities, credentials
  - **Pending targets**: URLs/endpoints to explore next
- Builds context for each new step from previous findings

#### 3. **Specialist Agents**
Two specialized agents run in parallel:

- **WebProbe** (WEB channel):
  - Focus: HTTP probes, auth bypass, file download traps
  - Targets: The vulnerable web app (`http://localhost:3000`)
  - Uses: `curl`, `gobuster`, `python3` for web exploitation

- **SystemSweep** (SYSTEM channel):
  - Focus: Port sweeps, SSH banner grabs, filesystem pokes
  - Targets: SSH/system services (`ssh://localhost:22`)
  - Uses: `nmap`, SSH tools

#### 4. **Attack Loop** (`agent_attack.py`)

```python
for step in range(1, max_steps + 1):
    # 1. Check what honeypots are active
    active_honeypots = await get_active_honeypots()
    
    # 2. For each specialist (WEB, SYSTEM):
    for specialist in SPECIALISTS:
        # 3. Build task with context + honeypot info
        task = build_task(step, memory, specialist, active_honeypots)
        
        # 4. Run the agent
        result = await Runner.run(agent, task)
        
        # 5. Record step in memory
        memory.record_step(step, task, result)
        
        # 6. Report to defense system
        post_attack_event(result, specialist)
```

### How Each Step Works

1. **Task Building**: Creates a prompt that includes:
   - Current step number
   - Target URL/IP
   - **Active honeypots list** (from defense API)
   - Previous findings from memory
   - Specialist's focus area

2. **Agent Execution**: The LLM agent:
   - Analyzes the task
   - **Must call at least one MCP tool** (curl, nmap, etc.)
   - Returns structured JSON with:
     - `commands_executed`: What tools were run
     - `findings`: Discovered endpoints, vulnerabilities
     - `next_targets`: URLs to explore next
     - `warnings`: Honeypot suspicions, risks

3. **Memory Update**: Findings and targets are saved for next steps

4. **Defense Reporting**: Attack events are sent to defense orchestrator

---

## 🍯 How Attacker2 Encounters Honeypots

### Honeypot Endpoints in Vulnerable App

The vulnerable app (`vulnerable-app/app.js`) has **intentional honeypot endpoints**:

```javascript
// These look like legitimate admin/debug endpoints
app.get('/admin-v2', ...)      // Honeypot endpoint
app.get('/backup-db', ...)      // Honeypot endpoint  
app.get('/config-prod', ...)    // Honeypot endpoint
app.get('/debug', ...)          // Honeypot endpoint
app.get('/env', ...)            // Honeypot endpoint
```

These endpoints return **tempting data** that looks valuable:
- Admin tokens
- Database backup locations
- API keys
- Configuration secrets

### Honeypot Mapping

The defense system (`defense/defense_agents/honeypot_manager.py`) maps these endpoints to real T-Pot honeypot services:

```python
SERVICE_ENDPOINTS = {
    "cowrie": ["/admin-v2", "/admin", "/admin/", "/admin/login"],      # SSH/Telnet trap
    "dionaea": ["/backup-db", "/backup-db/", "/download-db"],           # Malware catcher
    "elasticpot": ["/config-prod", "/config-prod/", "/debug", "/env"],  # Data exfiltration trap
}
```

### Attack Flow Leading to Honeypots

1. **Reconnaissance Phase**:
   ```
   Attacker2 → curl http://localhost:3000/
   Attacker2 → nmap -p80 localhost
   Attacker2 → gobuster dir http://localhost:3000
   ```
   Discovers endpoints like `/admin-v2`, `/backup-db`, `/config-prod`

2. **Exploration Phase**:
   ```
   Attacker2 → curl http://localhost:3000/admin-v2
   Response: {"adminToken": "demo-admin-token", ...}
   ```
   Agent sees this as a valuable finding and adds it to `next_targets`

3. **Honeypot Trigger**:
   - When attacker2 accesses `/admin-v2`, the defense system can:
     - **Arm the corresponding honeypot** (e.g., Cowrie for SSH)
     - **Log the interaction** as a honeypot hit
     - **Track the attacker's behavior**

4. **Escalation**:
   ```
   Attacker2 → curl http://localhost:3000/backup-db
   Response: {"backupLocation": "s3://pet-grooming-prod/backups/..."}
   ```
   Agent might try to:
   - Access the backup location
   - Use credentials found in `/config-prod`
   - Follow links to honeypot services

### Defense System Integration

Attacker2 **queries the defense API** before each step:

```python
# In agent_attack.py, line 197
active = await _get_active_honeypots(cfg)

# This calls: http://localhost:7700/honeypots
# Returns list of active honeypots like:
[
    {"label": "Cowrie", "vector": "SSH", "status": "armed"},
    {"label": "Dionaea", "vector": "FTP", "status": "armed"}
]
```

The agent is **informed** about active honeypots in its task prompt:
```
Active honeypots: Cowrie[SSH], Dionaea[FTP]
```

However, the agent may still:
- **Not recognize** that certain endpoints are honeypots
- **Follow tempting leads** (admin tokens, backup URLs) that lead to honeypots
- **Escalate attacks** that trigger honeypot services

### Example Attack Sequence

```
Step 1: WEB channel
  → curl http://localhost:3000/
  → Finding: "Homepage with login/signup links"
  → Next targets: ["/login", "/signup", "/admin"]

Step 2: WEB channel  
  → curl http://localhost:3000/admin
  → Finding: "Admin panel accessible"
  → Next targets: ["/admin-v2", "/admin/login"]

Step 3: WEB channel
  → curl http://localhost:3000/admin-v2
  → Finding: "Admin token found: demo-admin-token"
  → Warning: "Possible honeypot - endpoint returns token without auth"
  → Next targets: ["/backup-db", "/config-prod"]
  
Step 4: WEB channel
  → curl http://localhost:3000/backup-db
  → Finding: "Database backup location exposed"
  → Defense system: Honeypot triggered! (Dionaea)
```

---

## 🔍 Key Features

### 1. **Autonomous Operation**
- Runs for `ATTACKER2_MAX_STEPS` iterations (default: 5)
- Each step builds on previous findings
- No human intervention needed

### 2. **Persistent Memory**
- State saved in `state/memory.json`
- Can resume attacks across runs
- Tracks discovered endpoints, credentials, vulnerabilities

### 3. **Structured Output**
- Every step returns JSON:
  ```json
  {
    "action_summary": "Probed /admin-v2 endpoint",
    "commands_executed": ["curl -i http://localhost:3000/admin-v2"],
    "findings": ["Admin token exposed", "Legacy admin route"],
    "next_targets": ["/backup-db", "/config-prod"],
    "warnings": ["Possible honeypot - too easy"],
    "raw_output_snippet": "Found admin token: demo-admin-token"
  }
  ```

### 4. **Defense Integration**
- Reports all attack events to defense orchestrator
- Receives active honeypot status
- Enables real-time defense/attack interaction

### 5. **Honeypot Awareness (Limited)**
- Agent is **told** about active honeypots
- But may still:
  - Not recognize honeypot endpoints
  - Follow tempting leads anyway
  - Escalate to honeypot services

---

## 🎭 Why This Design?

This setup demonstrates:
1. **Realistic attacker behavior**: Agents explore endpoints without knowing they're honeypots
2. **Honeypot effectiveness**: Tempting data (tokens, backups) lures attackers
3. **Defense visibility**: All interactions are logged and tracked
4. **Autonomous red-teaming**: No manual intervention needed

The agent is designed to be **greedy** - it follows leads, explores endpoints, and tries to exploit findings, which makes it perfect for testing honeypot effectiveness!

