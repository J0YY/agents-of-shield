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

3. **Initialize log-reader-mcp:**
   ```bash
   npx log-reader-mcp init
   ```

4. **Ensure logs exist:**
   - Make sure your vulnerable app is logging to `logs/logs.log`
   - Create the directory if needed: `mkdir -p logs`
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
4. Connect to log-reader-mcp server
5. Run investigation
6. Display the recon report

## Troubleshooting

### ModuleNotFoundError: No module named 'agents'
- Install: `pip install openai-agents`

### OPENAI_API_KEY not set
- Set it: `export OPENAI_API_KEY="your-key"`

### Log file not found
- Create logs directory: `mkdir -p logs`
- Ensure vulnerable app logs to `logs/logs.log`

### log-reader-mcp not found
- Initialize it: `npx log-reader-mcp init`
- Or install globally: `npm install -g log-reader-mcp`

## Example Log Format

Your `logs/logs.log` should contain JSONL entries like:

```json
{"timestamp": "2024-01-15T10:30:00Z", "ip": "127.0.0.1", "method": "GET", "endpoint": "/", "query": {}, "body": {}}
{"timestamp": "2024-01-15T10:30:01Z", "ip": "127.0.0.1", "method": "POST", "endpoint": "/login", "query": {}, "body": {"email": "admin' OR '1'='1", "password": "test"}}
```

