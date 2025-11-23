# Monitoring When Attacker3 Hits the SSH Honeypot

## ✅ Yes, Attacker3 Will Encounter the Honeypot!

Since Cowrie is running on port 22, when attacker3 scans your host IP (`192.168.64.1`), it will:
1. **Discover port 22** is open (SSH service)
2. **Attempt SSH attacks** (brute force, login attempts)
3. **Trigger the honeypot** - all interactions will be logged

---

## 🔍 How to Monitor Honeypot Activity

### Method 1: Real-Time Log Monitoring (Recommended)

**Watch Cowrie logs in real-time:**

```bash
# In one terminal, watch the logs
cd /Users/mopeace/Documents/LISA-hack-shield/agents-of-shield/tpotce
tail -f data/cowrie/log/cowrie.json
```

This will show you:
- Login attempts
- Commands executed
- IP addresses
- Timestamps
- All attacker activity

### Method 2: Check Docker Logs

```bash
# View Cowrie container logs
docker logs -f cowrie
```

### Method 3: Check Log Files

```bash
cd /Users/mopeace/Documents/LISA-hack-shield/agents-of-shield/tpotce

# View JSON log (structured, easy to parse)
cat data/cowrie/log/cowrie.json | tail -20

# View text log
cat data/cowrie/log/cowrie.log | tail -20

# View TTY logs (interactive sessions)
ls -la data/cowrie/log/tty/
```

---

## 📊 What You'll See When Attacker3 Connects

### Example Log Entry

When attacker3 attempts SSH login, you'll see entries like:

```json
{
  "eventid": "cowrie.login.success",
  "username": "root",
  "password": "password123",
  "message": "login attempt [root/password123] succeeded",
  "sensor": "cowrie",
  "src_ip": "192.168.64.1",
  "timestamp": "2025-11-23T12:00:00.000000Z"
}
```

Or for brute force attempts:

```json
{
  "eventid": "cowrie.login.failed",
  "username": "root",
  "password": "admin",
  "message": "login attempt [root/admin] failed",
  "src_ip": "192.168.64.1"
}
```

### Commands Executed

If attacker3 successfully "logs in" and runs commands:

```json
{
  "eventid": "cowrie.command.input",
  "input": "whoami",
  "message": "CMD: whoami",
  "src_ip": "192.168.64.1"
}
```

---

## 🎯 Step-by-Step: Testing the Honeypot

### 1. Start Monitoring (Before Running Attacker3)

**Terminal 1 - Watch logs:**
```bash
cd /Users/mopeace/Documents/LISA-hack-shield/agents-of-shield/tpotce
tail -f data/cowrie/log/cowrie.json
```

### 2. Run Attacker3

**Terminal 2 - Run attacker:**
```bash
cd attacker3
docker run -it --rm --network host redteamagent
# Inside container:
ReAct
# Enter task:
Perform a penetration test on 192.168.64.1. Scan all ports, 
enumerate SSH service on port 22, and attempt brute force 
attacks to gain unauthorized access.
```

### 3. Watch the Logs

In Terminal 1, you'll see:
- Port scan detection (when nmap hits port 22)
- SSH connection attempts
- Login attempts (brute force)
- Commands executed (if login "succeeds")

---

## 🔍 Quick Verification Commands

### Check if Cowrie is Receiving Connections

```bash
# Count login attempts
cd /Users/mopeace/Documents/LISA-hack-shield/agents-of-shield/tpotce
grep -c "login" data/cowrie/log/cowrie.json

# See recent activity
tail -50 data/cowrie/log/cowrie.json | grep -E "login|command|connection"
```

### Check Specific IP (Your Attacker)

```bash
# Filter by your attacker's IP
grep "192.168.64" data/cowrie/log/cowrie.json | tail -20
```

### See All Commands Executed

```bash
# Extract all commands
grep "command.input" data/cowrie/log/cowrie.json | jq -r '.input' 2>/dev/null || \
grep "command.input" data/cowrie/log/cowrie.json
```

---

## 📈 What Attacker3 Will Do

Based on typical behavior, attacker3 will:

1. **Port Scan:**
   ```
   nmap -p- 192.168.64.1
   # Discovers port 22 (SSH)
   ```

2. **SSH Banner Grab:**
   ```
   nc 192.168.64.1 22
   # or
   ssh -v root@192.168.64.1
   ```

3. **Brute Force:**
   ```
   hydra -l root -P /usr/share/wordlists/rockyou.txt ssh://192.168.64.1
   ```

4. **Login Attempts:**
   ```
   ssh root@192.168.64.1
   # Tries various credentials
   ```

5. **Command Execution (if "login succeeds"):**
   ```
   whoami
   ls -la
   cat /etc/passwd
   # etc.
   ```

**All of this will be logged in Cowrie!**

---

## 🎯 Quick Test: Manual Verification

Before running attacker3, you can manually test the honeypot:

```bash
# Try to SSH into the honeypot
ssh root@localhost
# or
ssh root@192.168.64.1

# Try a password (any password)
# Password: test123

# Run a command
whoami
ls
```

Then check the logs:
```bash
tail -20 /Users/mopeace/Documents/LISA-hack-shield/agents-of-shield/tpotce/data/cowrie/log/cowrie.json
```

You should see your connection attempt logged!

---

## 📝 Summary

**Will attacker3 hit the honeypot?** ✅ **YES!**
- Port 22 is open and running Cowrie
- Attacker3 will discover it during port scanning
- It will attempt SSH attacks
- All interactions will be logged

**How to tell if it does:**
1. ✅ **Watch logs in real-time** - `tail -f tpotce/data/cowrie/log/cowrie.json`
2. ✅ **Check Docker logs** - `docker logs -f cowrie`
3. ✅ **Search log files** - `grep "192.168.64" data/cowrie/log/cowrie.json`

**What you'll see:**
- Login attempts (successful/failed)
- Commands executed
- IP addresses
- Timestamps
- Full attack timeline

---

## 🚀 Ready to Test!

1. **Start monitoring:**
   ```bash
   cd /Users/mopeace/Documents/LISA-hack-shield/agents-of-shield/tpotce
   tail -f data/cowrie/log/cowrie.json
   ```

2. **Run attacker3** in another terminal with an SSH attack task

3. **Watch the logs** - you'll see all the attack activity in real-time!

