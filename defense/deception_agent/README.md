# DeceptionAgent

AI-powered agent that detects directory enumeration attacks and generates realistic fake content to mislead attackers.

## What It Does

1. **Detects** directory enumeration by analyzing attack logs
2. **Identifies** which paths attackers are probing (/.env, /admin, /backup.sql, etc.)
3. **Generates** realistic but completely fake responses for each probed endpoint
4. **Outputs** deception cache ready to be served by the deception proxy

## Files Needed for Sub-Agent Usage

Only **5 files** are required to use DeceptionAgent as a sub-agent:

1. `defense/deception_agent/__init__.py` - Package initialization
2. `defense/deception_agent/deception_agent.py` - Main agent class
3. `defense/deception_agent/deception_response_mcp_server.py` - MCP server for fake content generation
4. `defense/deception_agent/requirements.txt` - Python dependencies
5. `defense/recon_agent/log_reader_mcp_server.py` - MCP server for log reading (external dependency)

All state files are created automatically at runtime in the `state_dir` you provide.

## Quick Start

### Installation

```bash
cd defense/deception_agent
pip install -r requirements.txt
export OPENAI_API_KEY='your-key-here'
```

### Standalone Usage

```python
from deception_agent import DeceptionAgent
from pathlib import Path

# Initialize
agent = DeceptionAgent(
    working_dir=Path("/path/to/repo"),
    state_dir=Path("/path/to/state")
)

# Run analysis (synchronous wrapper)
result = agent.analyze_and_deceive()

# Or use async directly
result = await agent.analyze_and_deceive_async()

# Check results
if result["enumeration_detected"]:
    print(f"Generated {len(result['deception_responses'])} deceptions")
    for deception in result["deception_responses"]:
        print(f"  {deception['endpoint']} → {deception['response_type']}")
```

### Sub-Agent Usage (Agents-as-Tools)

Use DeceptionAgent as a tool in an orchestrator agent:

```python
import asyncio
from agents import Agent, Runner
from deception_agent import DeceptionAgent
from pathlib import Path

async def main():
    # 1. Create wrapper
    wrapper = DeceptionAgent(
        working_dir=Path("/path/to/repo"),
        state_dir=Path("/path/to/state")
    )

    # 2. Get MCP servers (async context managers)
    log_server, dec_server = await wrapper.get_mcp_servers_async()

    # 3. Use in async context
    async with log_server, dec_server:
        # 4. Get agent instance
        agent = wrapper.get_agent(log_server, dec_server)

        # 5. Wrap as tool
        tool = agent.as_tool(
            tool_name="detect_and_deceive",
            tool_description="Analyzes network logs for directory enumeration and generates fake responses to mislead attackers"
        )

        # 6. Use in orchestrator
        orchestrator = Agent(
            name="DefenseOrchestrator",
            instructions="You coordinate defense agents to protect the application.",
            tools=[tool]
        )

        # 7. Run
        result = await Runner.run(orchestrator, "Check for directory enumeration attacks")
        print(result)

asyncio.run(main())
```

See [example_as_subagent.py](example_as_subagent.py) for a complete working example.

## API Reference

### DeceptionAgent Class

#### `__init__(working_dir: Path, state_dir: Path)`
Initialize the agent wrapper.

**Parameters:**
- `working_dir` - Repository root (where `vulnerable-app/` is located)
- `state_dir` - Directory for storing agent state and deception cache

#### `analyze_and_deceive() -> Dict`
Synchronous wrapper for analysis. Returns detection results.

**Returns:**
```python
{
    "enumeration_detected": bool,
    "confidence": str,
    "deception_responses": [
        {
            "endpoint": str,
            "response_type": str,
            "content": str,
            "content_type": str,
            "purpose": str
        }
    ],
    "attacker_intelligence": {...}
}
```

#### `async analyze_and_deceive_async(context: Optional[Dict] = None) -> Dict`
Async analysis method. Same return format as above.

#### `async get_mcp_servers_async() -> Tuple[MCPServerStdio, MCPServerStdio]`
Get MCP server instances for this agent.

**Returns:** `(log_reader_server, deception_server)`

**Usage:**
```python
log_server, dec_server = await wrapper.get_mcp_servers_async()
async with log_server, dec_server:
    # Use servers
```

#### `get_agent(log_reader_server, deception_server) -> Agent`
Get the underlying Agent instance.

**Returns:** Configured `Agent` instance ready to be wrapped with `.as_tool()`

## Deception Types Generated

### Fake Environment Files
```
DB_HOST=192.168.99.99
DB_USERNAME=honeypot_user
DB_PASSWORD=FakePassword123!
API_KEY=sk_test_fake_key_12345
```

### Fake Admin Panels (HTML)
Realistic login forms with fake JavaScript validation.

### Fake Config Files (JSON/YAML)
```json
{
  "database": {
    "host": "192.168.12.45",
    "username": "dbadmin",
    "password": "FakeSecret123"
  }
}
```

### Fake Database Backups (SQL)
```sql
INSERT INTO users VALUES
(1,'admin','admin@fake.com','$2b$10$fakehash','admin');
```

### Fake API Responses (JSON)
```json
{
  "token": "Bearer fake_jwt_token_123",
  "user": {"role": "admin"}
}
```

## Detection Criteria

The agent detects enumeration when it sees:

- **High volume**: 15+ requests in a short time
- **Common patterns**: Tools like gobuster, dirbuster, dirb
- **Predictable paths**: /.env, /admin, /backup, /config.php, etc.
- **404 clusters**: Many requests to non-existent endpoints
- **Sequential scanning**: Alphabetical or dictionary-based patterns

## Integration with Deception Proxy

After the agent generates deceptions, they are saved to `state_dir/live_deceptions.json`:

```json
{
  "endpoints": {
    "/.env": {
      "response_type": "fake_env",
      "content": "DB_HOST=192.168.99.99...",
      "content_type": "text/plain"
    }
  }
}
```

The **deception proxy** reads this cache and serves fake content to suspicious IPs.

### Starting the Proxy

```bash
cd defense/deception_proxy
node deception_proxy.js --port 8000
```

The proxy will:
1. Read `../state/live_deceptions.json`
2. Read `../state/suspicious_ips.json`
3. Serve fake content to suspicious IPs
4. Forward normal traffic to the real app

### Complete Workflow

```bash
# 1. Run the agent to generate deceptions
cd defense/deception_agent
python activate_live_deception.py

# 2. Start the proxy to serve them
cd ../deception_proxy
node deception_proxy.js --port 8000

# 3. Monitor serves
tail -f ../state/served_deceptions.log
```

## MCP Tools Available

### From log_reader_mcp_server
- **read_network_logs** - Reads and analyzes attack logs

### From deception_response_mcp_server
- **generate_fake_env_file** - Creates fake .env files
- **generate_fake_admin_panel** - Creates fake HTML admin panels
- **generate_fake_config_file** - Creates fake JSON/YAML configs
- **generate_fake_database_backup** - Creates fake SQL dumps
- **generate_fake_api_response** - Creates fake API responses

## Dependencies

From `requirements.txt`:

```
agents>=0.1.0
openai>=1.0.0
mcp>=0.1.0
fastmcp>=0.1.0
```

Install with:
```bash
pip install -r requirements.txt
```

**Environment Requirements:**
- Python 3.10+
- `OPENAI_API_KEY` environment variable
- Attack logs at `vulnerable-app/attack_log.json` (JSONL format)

## Security Considerations

✅ **Safe Practices:**
- All credentials are completely fake
- All IPs point to honeypots (192.168.x.x, 10.x.x.x ranges)
- All API keys should trigger alerts when used
- IP filtering prevents serving deceptions to legitimate users

❌ **Don't:**
- Include any real credentials or secrets
- Use real internal IPs or hostnames
- Expose actual system architecture
- Serve deceptions to legitimate users (use IP whitelisting)

## Production Deployment

### 1. Generate Deceptions (after attack detected)

```bash
cd defense/deception_agent
python activate_live_deception.py
```

### 2. Start Proxy (with IP whitelisting)

```bash
cd defense/deception_proxy
pm2 start deception_proxy.js --name deception-proxy -- \
  --target http://localhost:3000 \
  --port 80 \
  --trust 203.0.113.5 \
  --trust 203.0.113.10
```

### 3. Monitor Activity

```bash
# Watch deception serves
tail -f defense/state/served_deceptions.log

# Watch proxy requests
tail -f defense/state/deception_proxy_requests.log
```

### 4. Periodic Re-analysis (cron)

```bash
# Re-run every 6 hours to catch new enumeration patterns
0 */6 * * * cd /path/to/defense/deception_agent && python activate_live_deception.py
```

## Architecture

```
Attack Logs (JSONL)
        ↓
   DeceptionAgent (AI)
   - Analyzes patterns
   - Detects enumeration
   - Generates fakes
        ↓
   State Files
   - live_deceptions.json
   - suspicious_ips.json
        ↓
   Deception Proxy
   - Reads cache
   - Serves to suspicious IPs
   - Forwards normal traffic
        ↓
   Attacker receives fakes
   Legitimate users get real app
```

## Troubleshooting

### No Enumeration Detected
- Verify `vulnerable-app/attack_log.json` exists
- Check log format is valid JSONL
- Ensure at least 15+ scan requests in logs

### Deceptions Not Generated
- Check `OPENAI_API_KEY` is set
- Verify MCP servers start successfully (check console output)
- Review agent analysis output for errors

### Proxy Not Serving Deceptions
- Verify `state_dir/live_deceptions.json` exists
- Check IP is flagged in `suspicious_ips.json`
- Ensure proxy reads the correct state directory
- Restart proxy after generating new deceptions

### MCP Server Errors
- Ensure Python paths are correct (log_reader_mcp_server.py location)
- Check virtual environment has all dependencies
- Verify `fastmcp` and `mcp` packages are installed

## Files Reference

### Core Agent Files (Required)
- `__init__.py` - Package exports
- `deception_agent.py` - Main agent class
- `deception_response_mcp_server.py` - Fake content generator
- `requirements.txt` - Dependencies

### External Dependencies (Required)
- `../recon_agent/log_reader_mcp_server.py` - Log reading tools

### Helper Files (Optional)
- `activate_live_deception.py` - CLI activation script
- `suspicious_ip_tracker.py` - IP tracking utilities
- `example_as_subagent.py` - Sub-agent usage example

### Documentation
- `README.md` - This file
- `QUICKSTART.md` - 5-minute getting started guide
- `FILES_FOR_SUBAGENT.txt` - Minimum file list

### State Files (Auto-created)
- `state_dir/deception_state.json` - Agent state
- `state_dir/live_deceptions.json` - Deception cache (read by proxy)
- `state_dir/suspicious_ips.json` - Flagged IPs (read by proxy)
- `state_dir/served_deceptions.log` - Serve logs (written by proxy)

## License

Part of the Agents of Shield defense framework.
