#!/usr/bin/env node
/**
 * Deception Proxy Server
 *
 * A standalone reverse proxy that intercepts requests and serves deceptions
 * WITHOUT modifying the target application.
 *
 * Usage:
 *   node deception_proxy.js --target http://localhost:3000 --port 8000
 *
 * Then attackers connect to: http://localhost:8000
 * Proxy forwards legitimate requests to: http://localhost:3000
 */

const http = require('http');
const httpProxy = require('http-proxy');
const fs = require('fs');
const path = require('path');
const url = require('url');

class DeceptionProxy {
    constructor(options = {}) {
        this.targetUrl = options.target || 'http://localhost:3000';
        this.proxyPort = options.port || 8000;
        this.stateDir = options.stateDir || path.join(__dirname, '../state');

        this.deceptionCachePath = path.join(this.stateDir, 'live_deceptions.json');
        this.suspiciousIpsPath = path.join(this.stateDir, 'suspicious_ips.json');
        this.servedLog = path.join(this.stateDir, 'served_deceptions.log');
        this.proxyLogPath = path.join(this.stateDir, 'proxy_requests.log');

        // Configuration
        this.config = {
            trustedIps: options.trustedIps || [],
            onlySuspiciousIps: options.onlySuspiciousIps !== undefined ? options.onlySuspiciousIps : true,
            logAllRequests: options.logAllRequests !== undefined ? options.logAllRequests : true,
        };

        // Create reverse proxy
        this.proxy = httpProxy.createProxyServer({
            target: this.targetUrl,
            changeOrigin: true,
            preserveHeaderKeyCase: true,
        });

        // Handle proxy errors
        this.proxy.on('error', (err, req, res) => {
            console.error('❌ Proxy error:', err.message);
            if (!res.headersSent) {
                res.writeHead(502, { 'Content-Type': 'text/plain' });
                res.end('Bad Gateway - Target application not available');
            }
        });

        console.log('🎭 Deception Proxy initialized');
        console.log(`   Target: ${this.targetUrl}`);
        console.log(`   Port: ${this.proxyPort}`);
    }

    loadDeceptionCache() {
        try {
            if (fs.existsSync(this.deceptionCachePath)) {
                const data = fs.readFileSync(this.deceptionCachePath, 'utf8');
                return JSON.parse(data);
            }
        } catch (err) {
            console.error('Failed to load deception cache:', err.message);
        }
        return { endpoints: {} };
    }

    loadSuspiciousIps() {
        try {
            if (fs.existsSync(this.suspiciousIpsPath)) {
                const data = fs.readFileSync(this.suspiciousIpsPath, 'utf8');
                const parsed = JSON.parse(data);
                return new Set(parsed.ips || []);
            }
        } catch (err) {
            console.error('Failed to load suspicious IPs:', err.message);
        }
        return new Set();
    }

    normalizeIp(ip) {
        // Normalize IPv6 localhost
        if (ip === '::1' || ip === '::ffff:127.0.0.1') {
            return '127.0.0.1';
        }
        // Remove IPv6 prefix if present
        if (ip.startsWith('::ffff:')) {
            return ip.substring(7);
        }
        return ip;
    }

    isTrustedIp(ip) {
        ip = this.normalizeIp(ip);

        // Only trust IPs explicitly in the whitelist
        return this.config.trustedIps.includes(ip);
    }

    isSuspiciousIp(ip) {
        ip = this.normalizeIp(ip);
        const suspiciousIps = this.loadSuspiciousIps();
        return suspiciousIps.has(ip);
    }

    shouldServeDeception(ip) {
        if (this.isTrustedIp(ip)) {
            return false;
        }

        if (this.config.onlySuspiciousIps) {
            return this.isSuspiciousIp(ip);
        }

        return true;
    }

    getDeception(endpoint) {
        const cache = this.loadDeceptionCache();

        // Exact match
        if (cache.endpoints[endpoint]) {
            return cache.endpoints[endpoint];
        }

        // Partial match - only if endpoint is longer and starts with registered path
        // This prevents "/" from matching "/.env"
        for (const [registeredEndpoint, deception] of Object.entries(cache.endpoints)) {
            // Only match if the request path starts with the registered path
            // AND the registered path is more specific (not just "/")
            if (registeredEndpoint !== '/' && endpoint.startsWith(registeredEndpoint)) {
                return deception;
            }
        }

        return null;
    }

    logRequest(req, action, details = {}) {
        if (!this.config.logAllRequests) return;

        const logEntry = {
            timestamp: new Date().toISOString(),
            ip: req.socket.remoteAddress,
            method: req.method,
            url: req.url,
            action: action,
            ...details
        };

        try {
            fs.appendFileSync(this.proxyLogPath, JSON.stringify(logEntry) + '\n');
        } catch (err) {
            console.error('Failed to log request:', err.message);
        }
    }

    logDeceptionServed(endpoint, deception, ip) {
        const logEntry = {
            timestamp: new Date().toISOString(),
            endpoint: endpoint,
            response_type: deception.response_type,
            ip: this.normalizeIp(ip),
        };

        try {
            fs.appendFileSync(this.servedLog, JSON.stringify(logEntry) + '\n');
        } catch (err) {
            console.error('Failed to log deception serve:', err.message);
        }
    }

    handleRequest(req, res) {
        const clientIp = req.socket.remoteAddress;
        const parsedUrl = url.parse(req.url);
        const endpoint = parsedUrl.pathname;

        // Check for deception
        const deception = this.getDeception(endpoint);

        if (deception && this.shouldServeDeception(clientIp)) {
            // Serve deception
            console.log(`🎭 [DECEPTION] Serving fake ${deception.response_type} for ${endpoint} to ${clientIp}`);

            this.logRequest(req, 'deception_served', {
                response_type: deception.response_type
            });
            this.logDeceptionServed(endpoint, deception, clientIp);

            res.writeHead(200, {
                'Content-Type': deception.content_type || 'text/plain',
                'X-Deception-ID': deception.response_type,
            });
            res.end(deception.content);
            return;
        }

        if (deception && this.isTrustedIp(clientIp)) {
            console.log(`🛡️  [DECEPTION] Skipping deception for ${endpoint} - IP ${clientIp} is trusted`);
        }

        // Forward to target application
        this.logRequest(req, 'proxied');
        this.proxy.web(req, res);
    }

    start() {
        const server = http.createServer((req, res) => {
            this.handleRequest(req, res);
        });

        server.listen(this.proxyPort, () => {
            console.log('');
            console.log('═══════════════════════════════════════════════════════════════════');
            console.log('  🎭 DECEPTION PROXY SERVER STARTED');
            console.log('═══════════════════════════════════════════════════════════════════');
            console.log('');
            console.log(`  Proxy listening on:  http://localhost:${this.proxyPort}`);
            console.log(`  Forwarding to:       ${this.targetUrl}`);
            console.log('');
            console.log('  Configuration:');
            console.log(`    Only suspicious:   ${this.config.onlySuspiciousIps}`);
            console.log(`    Trusted IPs:       ${this.config.trustedIps.length > 0 ? this.config.trustedIps.join(', ') : 'none'}`);
            console.log('');
            console.log('  State files:');
            console.log(`    Deceptions:        ${this.deceptionCachePath}`);
            console.log(`    Suspicious IPs:    ${this.suspiciousIpsPath}`);
            console.log(`    Serve log:         ${this.servedLog}`);
            console.log(`    Proxy log:         ${this.proxyLogPath}`);
            console.log('');
            console.log('  👉 Attackers should connect to the PROXY port, not the target!');
            console.log('');
            console.log('═══════════════════════════════════════════════════════════════════');
        });

        // Handle HTTPS upgrade requests
        server.on('upgrade', (req, socket, head) => {
            this.proxy.ws(req, socket, head);
        });

        return server;
    }
}

// CLI interface
if (require.main === module) {
    const args = process.argv.slice(2);
    const options = {
        target: 'http://localhost:3000',
        port: 8000,
        stateDir: path.join(__dirname, '../state'),
        trustedIps: [],
        onlySuspiciousIps: true,
    };

    // Parse command line arguments
    for (let i = 0; i < args.length; i++) {
        switch (args[i]) {
            case '--target':
            case '-t':
                options.target = args[++i];
                break;
            case '--port':
            case '-p':
                options.port = parseInt(args[++i]);
                break;
            case '--state-dir':
            case '-s':
                options.stateDir = args[++i];
                break;
            case '--trust':
                options.trustedIps.push(args[++i]);
                break;
            case '--aggressive':
                options.onlySuspiciousIps = false;
                break;
            case '--help':
            case '-h':
                console.log(`
Deception Proxy Server - Zero-modification deception for any web application

Usage:
  node deception_proxy.js [options]

Options:
  -t, --target <url>      Target application URL (default: http://localhost:3000)
  -p, --port <port>       Proxy port (default: 8000)
  -s, --state-dir <dir>   State directory path (default: ../state)
  --trust <ip>            Add IP to trusted list (can be used multiple times)
  --aggressive            Serve deceptions to all non-trusted IPs
  -h, --help              Show this help

Examples:
  # Basic usage
  node deception_proxy.js

  # Custom target and port
  node deception_proxy.js --target http://localhost:3000 --port 8080

  # Trust specific admin IP
  node deception_proxy.js --trust 10.0.0.5 --trust 10.0.0.10

Workflow:
  1. Start your application on its normal port (e.g., 3000)
  2. Start the deception proxy on a different port (e.g., 8000)
  3. Point attackers/internet traffic to the proxy port
  4. Run DeceptionAgent to detect enumeration and generate fakes
  5. Proxy serves deceptions to suspicious IPs, forwards others normally
                `);
                process.exit(0);
        }
    }

    const proxy = new DeceptionProxy(options);
    proxy.start();
}

module.exports = DeceptionProxy;
