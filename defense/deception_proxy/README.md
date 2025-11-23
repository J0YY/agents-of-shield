# Deception Proxy

**Zero-modification deception for ANY web application**

Instead of modifying your application code, run this standalone reverse proxy in front of it. The proxy intercepts suspicious requests and serves deceptions, while forwarding legitimate traffic normally.

- **Zero code changes** to your application
- Works with **any** web app (Node, Python, Java, PHP, etc.)
- Easy to deploy/remove
- Can protect multiple apps
- Change deception config without restarting app

## Architecture

```
           Internet/Attackers
                  ↓
         Deception Proxy :8000
         ┌────────────────────┐
         │ IP Filtering       │
         │ Deception Check    │
         │ Suspicious? → Fake │
         │ Trusted? → Forward │
         └────────────────────┘
                  ↓
         Your Application :3000
         (unchanged!)
```

## Quick Start

### 1. Install Dependencies

```bash
cd /Users/harriet/agents-of-shield/defense/deception_proxy
npm install
```

### 2. Start Your Application (Unchanged)

```bash
# Your app runs on its normal port
cd /Users/harriet/agents-of-shield/vulnerable-app
npm start
# Running on http://localhost:3000
```

### 3. Start the Deception Proxy

```bash
cd /Users/harriet/agents-of-shield/defense/deception_proxy

# Basic usage (proxies localhost:3000 on port 8000)
node deception_proxy.js

# With options
node deception_proxy.js --target http://localhost:3000 --port 8000 --testing-mode
```

### 4. Connect Attackers to the Proxy

Attackers should connect to `http://localhost:8000` (proxy), not `http://localhost:3000` (real app).

### 5. Run DeceptionAgent to Generate Fakes

```bash
cd /Users/harriet/agents-of-shield/defense/deception_agent
export OPENAI_API_KEY='your-key'
python activate_live_deception.py
```

## Command Line Options

```bash
node deception_proxy.js [options]

Options:
  -t, --target <url>      Target application URL (default: http://localhost:3000)
  -p, --port <port>       Proxy port (default: 8000)
  -s, --state-dir <dir>   State directory path (default: ../state)
  --testing-mode          Enable testing mode (don't auto-trust localhost)
  --trust <ip>            Add IP to trusted list (can be used multiple times)
  --aggressive            Serve deceptions to all non-trusted IPs
  -h, --help              Show help
```

## Usage Examples

### Example 1: Basic Proxy

```bash
node deception_proxy.js
```

**Behavior**:
- Listens on port 8000
- Forwards to http://localhost:3000
- Serves deceptions only to suspicious IPs
- Auto-trusts private IPs (production mode)

### Example 2: Red Team Testing

```bash
node deception_proxy.js --testing-mode
```

**Behavior**:
- Testing mode enabled
- Localhost can be flagged as suspicious
- Perfect for local red team testing

### Example 3: Custom Configuration

```bash
node deception_proxy.js \
  --target http://localhost:3000 \
  --port 8080 \
  --trust 10.0.0.5 \
  --trust 10.0.0.10
```

**Behavior**:
- Proxy on port 8080
- IPs 10.0.0.5 and 10.0.0.10 are trusted
- Other IPs can be flagged

### Example 4: Multiple Applications

```bash
# Proxy for App 1
node deception_proxy.js --target http://localhost:3000 --port 8000 &

# Proxy for App 2
node deception_proxy.js --target http://localhost:4000 --port 8001 &

# Proxy for App 3 (Python Flask)
node deception_proxy.js --target http://localhost:5000 --port 8002 &
```

All three apps share the same deception cache and suspicious IP list!

## Deployment Scenarios

### Scenario 1: Development/Testing

```
Developer Machine
├── Your App :3000 (normal operation)
├── Deception Proxy :8000 (intercepts attacks)
└── Localhost attacks get deceptions
```

**Setup**:
```bash
# Terminal 1: Your app
npm start

# Terminal 2: Proxy (testing mode)
node deception_proxy.js --testing-mode
```

### Scenario 2: Production Single App

```
Production Server
├── Your App :3000 (internal only)
├── Deception Proxy :80 (public facing)
└── Firewall blocks direct access to :3000
```

**Setup**:
```bash
# Your app (internal)
npm start

# Proxy (public)
sudo node deception_proxy.js --target http://localhost:3000 --port 80
```

### Scenario 3: Production Multiple Apps

```
Production Server
├── App 1 :3000 → Proxy :8001
├── App 2 :4000 → Proxy :8002
├── App 3 :5000 → Proxy :8003
└── Nginx reverse proxy routes by domain
```

**Nginx config**:
```nginx
server {
    server_name app1.example.com;
    location / {
        proxy_pass http://localhost:8001;  # Deception proxy, not app!
    }
}

server {
    server_name app2.example.com;
    location / {
        proxy_pass http://localhost:8002;  # Deception proxy
    }
}
```

## How It Works

### Request Flow

```
1. Attacker sends: GET /.env
   ↓
2. Proxy receives request
   ↓
3. Check IP: Is it trusted?
   ├─ YES → Forward to app (step 7)
   └─ NO → Continue to step 4
   ↓
4. Check IP: Is it suspicious?
   ├─ NO → Forward to app (step 7)
   └─ YES → Continue to step 5
   ↓
5. Check deception cache: Is /.env registered?
   ├─ NO → Forward to app (step 7)
   └─ YES → Continue to step 6
   ↓
6. Serve fake .env content
   ↓
   Attacker gets honeypot credentials!
   ↓
7. Forward to real app
   ↓
   App sees normal request
```

### Logging

The proxy creates comprehensive logs:

**`state/proxy_requests.log`** - All requests through proxy:
```jsonl
{"timestamp":"2024-11-22T21:00:00Z","ip":"127.0.0.1","method":"GET","url":"/.env","action":"deception_served","response_type":"fake_env"}
{"timestamp":"2024-11-22T21:00:05Z","ip":"10.0.0.5","method":"GET","url":"/admin","action":"proxied"}
```

**`state/served_deceptions.log`** - Only deceptions served:
```jsonl
{"timestamp":"2024-11-22T21:00:00Z","endpoint":"/.env","response_type":"fake_env","ip":"127.0.0.1"}
```

## Attack Log Collection

The proxy doesn't write attack logs itself (only the app does that). You have two options:

### Option 1: Modify Attack Logging

Add logging middleware to your app to capture requests forwarded by the proxy.

### Option 2: Use Proxy Logs

Modify the DeceptionAgent to read `proxy_requests.log` instead of `attack_log.json`:

```python
# In deception_agent.py
attack_log = repo_root / "defense" / "state" / "proxy_requests.log"
```

## Advantages Over Middleware

| Feature | Middleware | Proxy |
|---------|-----------|-------|
| Modify app code | ❌ Required | ✅ Not needed |
| Works with any language | ❌ Node.js only | ✅ Any app |
| Deploy to multiple apps | ❌ Hard | ✅ Easy |
| Change config | ❌ Restart app | ✅ Restart proxy only |
| Remove protection | ❌ Code changes | ✅ Stop proxy |
| Shared deceptions | ❌ Per app | ✅ Cross-app |

## Production Checklist

- [ ] Set `--testing-mode` to false (or omit it)
- [ ] Add admin IPs to `--trust` list
- [ ] Run proxy on standard port (80/443) or behind nginx
- [ ] Block direct access to target app port
- [ ] Monitor `served_deceptions.log` for alerts
- [ ] Set up process manager (PM2, systemd)
- [ ] Configure log rotation

## Process Management

### Using PM2

```bash
# Install PM2
npm install -g pm2

# Start proxy
pm2 start deception_proxy.js --name "deception-proxy" -- --target http://localhost:3000 --port 8000

# Monitor
pm2 logs deception-proxy

# Restart
pm2 restart deception-proxy

# Auto-start on boot
pm2 startup
pm2 save
```

### Using systemd

```ini
# /etc/systemd/system/deception-proxy.service
[Unit]
Description=Deception Proxy Server
After=network.target

[Service]
Type=simple
User=www-data
WorkingDirectory=/path/to/defense/deception_proxy
ExecStart=/usr/bin/node deception_proxy.js --target http://localhost:3000 --port 8000
Restart=on-failure

[Install]
WantedBy=multi-user.target
```

```bash
sudo systemctl enable deception-proxy
sudo systemctl start deception-proxy
```

## Security Considerations

### ✅ Safe:
- Proxy only forwards HTTP, doesn't modify responses
- Deceptions are read from cache (no code execution)
- IP filtering prevents friendly fire
- All actions are logged

### ⚠️  Be Aware:
- Proxy is a single point of failure
- Adds minimal latency (~1-2ms)
- Doesn't encrypt traffic (use nginx with SSL in front)
- State files must be readable by proxy

## Troubleshooting

### Proxy won't start
```bash
# Check if port is in use
lsof -i :8000

# Use different port
node deception_proxy.js --port 8001
```

### Target app not reachable
```bash
# Verify app is running
curl http://localhost:3000

# Check proxy error logs
```

### Deceptions not served
```bash
# Verify cache exists
cat ../state/live_deceptions.json

# Check if IP is flagged
cat ../state/suspicious_ips.json

# Enable testing mode
node deception_proxy.js --testing-mode
```

## Migration from Middleware

If you were using the middleware approach:

1. **Remove middleware from app.js**:
   ```javascript
   // DELETE these lines:
   // const DeceptionIntegration = require('./deception_integration');
   // const deception = new DeceptionIntegration(...);
   // app.use(deception.middleware());
   ```

2. **Restart your app** (now clean, no deception code)

3. **Start the proxy**:
   ```bash
   node deception_proxy.js
   ```

4. **Update attack sources** to connect to proxy port (8000) instead of app port (3000)

Done! Same functionality, zero app modifications.

## Summary

The **Deception Proxy** gives you:

✅ Zero code changes to your application
✅ Works with any web app (Node, Python, Java, PHP, etc.)
✅ Easy to deploy and remove
✅ Share deceptions across multiple apps
✅ Change configuration without restarting app
✅ Production-ready with proper process management

**Perfect for:**
- Protecting legacy apps you can't modify
- Microservices architecture (one proxy per service)
- Multi-tenant environments
- Quick PoC deployments
- Apps in different languages
