# Attack Recon Agent

A self-contained reconnaissance agent that investigates suspicious activity by analyzing network traffic from the vulnerable server's log files.

## Architecture

The recon agent follows a **simple, tool-based** architecture:

1. **Agent Trigger** → Orchestrator (or manual call) tells recon agent "Go do your thing"
2. **Intelligence Gathering** → Agent uses network traffic tool to read from vulnerable app's log file
3. **Analysis** → Agent analyzes traffic patterns to identify attacks
4. **Report** → Agent produces structured assessment report
5. **Response** → Report sent back to orchestrator for defensive actions

## MCP Server

The recon agent uses the **log-reader-mcp** library ([GitHub](https://github.com/hassansaadfr/log-reader-mcp)) to read network traffic.

### Installation

Install and initialize log-reader-mcp:

```bash
npx log-reader-mcp init
```

This sets up the MCP configuration in `.cursor/mcp.json`.

### MCP Server Tools

The log-reader-mcp server provides tools to read logs. However, note that:

- **log-reader-mcp expects logs at**: `logs/logs.log` (in your working directory)
- **Our vulnerable app logs to**: `vulnerable-app/attack_log.json`

The agent will attempt to use log-reader-mcp via the MCP protocol, but falls back to direct file reading if:
- The agents framework is not available
- The log file location doesn't match log-reader-mcp's expectations
- The MCP server is not properly configured

### Log Format

Both formats use JSONL (one JSON object per line):

**log-reader-mcp expected format** (`logs/logs.log`):
```json
{"level": "INFO", "timestamp": "2024-06-01T12:34:56.789Z", "message": "..."}
```

**Our vulnerable app format** (`vulnerable-app/attack_log.json`):
```json
{"timestamp": "2024-06-01T12:34:56.789Z", "ip": "127.0.0.1", "method": "GET", "endpoint": "/", "query": {}, "body": {}}
```

## Usage

### Basic Usage

```python
from pathlib import Path
from defense_agents.recon_agent import ReconAgent

# Initialize agent - log-reader-mcp expects logs/logs.log in working directory
working_dir = Path(".")  # or Path("/path/to/your/project")
agent = ReconAgent(working_dir=working_dir)

# Or specify log file path directly
agent = ReconAgent(log_file_path=Path("logs/logs.log"))

# Run investigation
report = agent.investigate(context={"trigger": "manual"})

# Access report
print(f"Attack Type: {report['attack_assessment']['attack_type']}")
print(f"Severity: {report['attack_assessment']['severity']}")
print(f"Evidence: {report['evidence']}")
```

### Testing

Run the test script:

```bash
cd defense/defense_agents
python test_recon_agent.py
```

Make sure the vulnerable app is running and has generated some log entries in `vulnerable-app/attack_log.json`.

## Report Structure

The agent returns a comprehensive report:

```json
{
  "timestamp": "2024-01-15T10:30:00",
  "investigation_trigger": "suspicious_activity_detection",
  "attack_assessment": {
    "attack_type": "sql_injection",
    "target": "/login",
    "severity": "high",
    "confidence": "high"
  },
  "evidence": [
    "Detected 3 SQL injection attempts",
    "SQL keywords found: SELECT, UNION, OR",
    "Honeypot triggered 1 time(s)"
  ],
  "intelligence": {
    "network_events_analyzed": 50,
    "attacker_events_analyzed": 50,
    "sql_injection_attempts": 3,
    "endpoint_analysis": {
      "unique_endpoints": 12,
      "total_requests": 50,
      "most_accessed": {"/login": 5, "/admin": 3},
      "recon_indicators": 8
    },
    "temporal_analysis": {
      "pattern": "automated",
      "automation_likelihood": 75,
      "avg_interval_seconds": 1.2
    },
    "honeypot_triggers": 1
  },
  "recommendations": [
    "Implement parameterized queries for all database operations",
    "Deploy WAF rules to block SQL injection patterns",
    "Honeypot triggered - attacker is actively probing sensitive endpoints"
  ],
  "next_steps": [
    "Immediate: Block or rate-limit source IP",
    "Action: Review database logs for successful queries",
    "Monitor: Continue tracking attacker behavior"
  ]
}
```

## Attack Types Detected

The agent can identify:

- **sql_injection** - SQL injection attempts
- **path_traversal** - Directory traversal attempts
- **admin_enumeration** - Admin endpoint probing
- **reconnaissance** - General reconnaissance activity
- **unknown** - Unclassified activity

## Severity Levels

- **critical** - Immediate action required
- **high** - Urgent attention needed
- **medium** - Monitor closely
- **low** - Continue observation

## How It Works

1. **Vulnerable Server Logging**: The Express server logs all requests to `logs/logs.log` (JSONL format)
   - This matches log-reader-mcp's expected location

2. **MCP Server**: The log-reader-mcp library provides tools to read the log file via MCP protocol

3. **Recon Agent**: The agent uses log-reader-mcp to retrieve network traffic, then analyzes it to detect:
   - **SQL Injection**: Looks for SQL keywords in request bodies and query parameters
   - **Path Traversal**: Detects `../` patterns in endpoints
   - **Reconnaissance**: Identifies probing of suspicious endpoints (admin, config, etc.)
   - **Honeypot Hits**: Detects access to honeypot endpoints

4. **Report Generation**: The agent produces a structured report with attack assessment, evidence, and recommendations

5. **Fallback**: If MCP is not available, the agent falls back to direct file reading from `logs/logs.log`

## Integration (Future)

When integrated with the orchestrator, the report will be used to:

1. **Determine defensive actions** based on attack type and severity
2. **Broadcast alerts** via WebSocket to the dashboard
3. **Log findings** for post-incident analysis
4. **Trigger automated responses** (e.g., IP blocking, rate limiting)

## Example Workflow

```
1. Vulnerable server receives: POST /login with body {"email": "admin' OR '1'='1", "password": "test"}
2. Server logs request to vulnerable-app/attack_log.json
3. Recon agent is triggered: agent.investigate()
4. Agent:
   - Reads recent entries from attack_log.json
   - Analyzes request bodies for SQL injection patterns
   - Detects SQL keywords in the login request
   - Produces report: "sql_injection attack on /login, high severity"
5. Report contains evidence, recommendations, and next steps
```

## File Structure

- `recon_agent.py` - Main recon agent that uses log-reader-mcp to read logs and analyze attacks
- `logs/logs.log` - Network traffic log (JSONL format) - automatically created by the vulnerable server
  - This is the location log-reader-mcp expects by default

The agent does not write any files (read-only intelligence gathering).

## Log File Location

The agent expects logs at `logs/logs.log` in the working directory, which matches log-reader-mcp's default location. Make sure your vulnerable server is configured to log to this location.

## Extending the Agent

To add more tools or analysis:

1. Add a new tool method (e.g., `get_database_queries()`)
2. Call it in `investigate()`
3. Use the data in analysis methods
4. Include findings in the report

Example:

```python
def get_database_queries(self) -> List[Dict]:
    """Tool: Retrieve recent database queries from logs."""
    # Your implementation
    pass

# In investigate():
db_queries = self.get_database_queries()
# Use in analysis...
```

