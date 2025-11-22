# Attack Recon Agent

A self-contained reconnaissance agent that investigates suspicious activity by analyzing network traffic from the vulnerable server's log files.

## Files

- `recon_agent.py` - Main recon agent that uses MCP to read logs and analyze attacks
- `log_reader_mcp_server.py` - Custom MCP server that provides tools to read network traffic logs
- `test_recon_agent.py` - Test script to run the agent
- `requirements.txt` - Python dependencies

## Architecture

The recon agent follows a **simple, tool-based** architecture:

1. **Agent Trigger** → Orchestrator (or manual call) tells recon agent "Go do your thing"
2. **Intelligence Gathering** → Agent uses network traffic tool to read from vulnerable app's log file
3. **Analysis** → Agent analyzes traffic patterns to identify attacks
4. **Report** → Agent produces structured assessment report
5. **Response** → Report sent back to orchestrator for defensive actions

## MCP Server

The recon agent uses a **custom MCP server** (`log_reader_mcp_server.py`) to read network traffic logs from the vulnerable app.

### MCP Server Tools

The custom MCP server provides two tools:

- **`read_network_logs(lines=50, working_dir=None, log_path=None)`** - Reads the last N lines from the log file
- **`get_all_network_logs(working_dir=None, log_path=None)`** - Reads all log entries

The server reads from `vulnerable-app/attack_log.json` by default (relative to the working directory).

### Log Format

The vulnerable app logs in JSONL format (one JSON object per line):

```json
{
  "timestamp": "2024-06-01T12:34:56.789Z",
  "ip": "127.0.0.1",
  "method": "GET",
  "endpoint": "/",
  "query": {},
  "body": {}
}
```

Each entry contains:

- `timestamp` - ISO 8601 timestamp
- `ip` - Client IP address
- `method` - HTTP method (GET, POST, etc.)
- `endpoint` - Request endpoint/URL
- `query` - Query parameters (object)
- `body` - Request body (object, optional)

## Usage

### Basic Usage

```python
from pathlib import Path
from defense_agents.recon_agent import ReconAgent

# Initialize agent - expects vulnerable-app/attack_log.json in working directory
working_dir = Path(".")  # or Path("/path/to/your/project")
agent = ReconAgent(working_dir=working_dir)

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
      "most_accessed": { "/login": 5, "/admin": 3 },
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

1. **Vulnerable Server Logging**: The Express server logs all requests to `vulnerable-app/attack_log.json` (JSONL format)

2. **MCP Server**: The custom `log_reader_mcp_server.py` provides tools to read the log file via MCP protocol

   - The MCP server is automatically started as a subprocess when the agent runs
   - No manual setup required

3. **Recon Agent**: The agent uses the MCP server to retrieve network traffic, then analyzes it to detect:

   - **SQL Injection**: Looks for SQL keywords in request bodies and query parameters
   - **Path Traversal**: Detects `../` patterns in endpoints
   - **Reconnaissance**: Identifies probing of suspicious endpoints (admin, config, etc.)
   - **Honeypot Hits**: Detects access to honeypot endpoints

4. **Report Generation**: The agent produces a structured report with attack assessment, evidence, and recommendations

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

- `recon_agent.py` - Main recon agent that uses the custom MCP server to read logs and analyze attacks
- `log_reader_mcp_server.py` - Custom MCP server that provides tools to read network traffic logs
- `vulnerable-app/attack_log.json` - Network traffic log (JSONL format) - automatically created by the vulnerable server

The agent does not write any files (read-only intelligence gathering).

## Log File Location

The agent expects logs at `vulnerable-app/attack_log.json` relative to the working directory. The vulnerable app automatically logs all HTTP requests to this file.

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
