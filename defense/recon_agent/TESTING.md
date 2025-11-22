# Testing the Recon Agent

## Prerequisites

1. **Install dependencies:**

   ```bash
   pip install openai-agents
   pip install "mcp[cli]"
   ```

2. **Set OpenAI API key:**

   ```bash
   export OPENAI_API_KEY="your-api-key-here"
   ```

3. **Ensure logs exist:**
   - Make sure your vulnerable app is running and logging to `vulnerable-app/attack_log.json`
   - Start the vulnerable app: `cd vulnerable-app && npm start`
   - The log file should contain JSONL entries (one JSON object per line)

## Running the Test

```bash
cd defense/defense_agents
python test_recon_agent.py
```

## Expected Output

The test script will:

1. Check for required environment variables
2. Verify log file exists
3. Initialize the recon agent
4. Start the custom MCP server
5. Run investigation
6. Display the recon report

## Troubleshooting

### ModuleNotFoundError: No module named 'agents'

- Install: `pip install openai-agents`

### OPENAI_API_KEY not set

- Set it: `export OPENAI_API_KEY="your-key"`

### Log file not found

- Start the vulnerable app: `cd vulnerable-app && npm start`
- Ensure vulnerable app logs to `vulnerable-app/attack_log.json`
- The log file is automatically created when the app receives requests

## Example Log Format

Your `vulnerable-app/attack_log.json` should contain JSONL entries like:

```json
{"timestamp": "2024-01-15T10:30:00Z", "ip": "127.0.0.1", "method": "GET", "endpoint": "/", "query": {}, "body": {}}
{"timestamp": "2024-01-15T10:30:01Z", "ip": "127.0.0.1", "method": "POST", "endpoint": "/login", "query": {}, "body": {"email": "admin' OR '1'='1", "password": "test"}}
```
