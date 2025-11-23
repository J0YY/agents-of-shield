# Attacking the Vulnerable App with RedTeamAgent

This guide shows you how to run RedTeamAgent in Docker to attack the vulnerable app running on your host machine.

## Prerequisites

1. **Configure the RedTeamAgent config file** (REQUIRED):

   Edit `attacker3/src/redteamagent/config/config.json` and set your API key:

   ```json
   {
       "api_key": "your-openai-api-key-here",
       "model_name": "gpt-4o",
       ...
   }
   ```

   **Important:**

   - You **must** set a valid `api_key` (OpenAI or other LLM provider)
   - **All fields must be present** - the agent will error if any are missing
   - Edit this **before building** the Docker image, as it gets copied into the image
   - The current config file has all other fields pre-configured, you only need to update `api_key`

   **Config file location:** `attacker3/src/redteamagent/config/config.json`

   **Config fields:**

   - `api_key` (required): Your LLM provider API key
   - `model_name` (required): Model to use (e.g., `gpt-4o`, `gpt-4-turbo`)
   - `activate_summary` (required): `true` to summarize long outputs, `false` to keep full text
   - `reason_time` (required): `0` = no reasoning, `>0` = number of reasoning iterations
   - System prompts: Pre-configured, can be customized if needed

2. **Start the vulnerable app** on your host machine:
   ```bash
   cd vulnerable-app
   npm install
   npm start
   ```
   The app will be running on `http://localhost:3000`

## Building the Docker Image

From the `attacker3` directory:

```bash
docker build -t redteamagent .
```

## Running the Agent

**⚠️ Important for macOS users:** `--network host` does NOT work on macOS with Docker Desktop because Docker runs in a VM. Use one of the options below instead.

### Option 1: Use Your Host's IP Address (Recommended for macOS) ✅

**This is the most reliable solution for macOS!** Find your host's IP address and use it in the attack task.

**Step 1: Find your host IP address**

On macOS, run:

```bash
ifconfig | grep "inet " | grep -v 127.0.0.1
```

You'll see something like:

```
inet 192.168.64.1 netmask 0xffffff00 broadcast 192.168.64.255
inet 172.16.1.240 netmask 0xfffffc00 broadcast 172.16.3.255
```

Use the first one (usually `192.168.64.1` or similar).

**Step 2: Run the container normally (no special network flags needed)**

```bash
docker run -it --rm redteamagent
```

**Step 3: Inside the container, run ReAct and use your host IP**

```bash
ReAct
```

Then enter a task like (replace `192.168.64.1` with your actual IP):

```
Attack the web application running on http://192.168.64.1:3000. Find vulnerabilities and extract sensitive information from the Pet Grooming by Sofia application.
```

**Test it works:**

```bash
# From inside the container:
curl http://192.168.64.1:3000
# You should see HTML from your vulnerable app!
```

### Option 2: Use host.docker.internal (macOS/Windows)

On macOS and Windows, Docker provides `host.docker.internal` to access the host machine:

```bash
docker run -it --rm redteamagent
```

Then when prompted, enter:

```
Attack the web application running on http://host.docker.internal:3000. Find vulnerabilities and extract sensitive information from the Pet Grooming by Sofia application.
```

**Note:** Sometimes `host.docker.internal` doesn't work reliably. If it fails, use Option 1 (host IP address) instead.

### Option 3: Use Host Network (Linux only)

**⚠️ This only works on Linux, NOT macOS!**

On Linux (not macOS), you can use:

```bash
docker run -it --rm --network host redteamagent
```

Then use `http://localhost:3000` in your task.

### Option 4: Use Your Host's IP Address (Alternative method)

## Example Attack Tasks

Here are some example tasks you can give the agent:

1. **General reconnaissance:**

   ```
   Perform reconnaissance on the web application at http://localhost:3000. Identify all endpoints, find vulnerabilities, and extract any sensitive data.
   ```

2. **SQL injection focus:**

   ```
   Test the web application at http://localhost:3000 for SQL injection vulnerabilities. Exploit any found vulnerabilities to extract user credentials from the database.
   ```

3. **Comprehensive attack:**
   ```
   Conduct a full penetration test on http://localhost:3000. Scan for open ports, enumerate web directories, test for SQL injection, path traversal, and other common vulnerabilities. Extract all sensitive information you can find.
   ```

## Running ReAct vs RedTeamAgent

### ⚠️ Important: Use ReAct (RedTeamAgent is incomplete)

- **ReAct** ✅ **WORKING**: Fully functional agent that executes tasks

  ```bash
  ReAct
  ```

  This is the agent you should use. It will:

  - Accept your task
  - Execute commands to attack the target
  - Continue until the task is complete

- **RedTeamAgent** ❌ **NOT WORKING**: Only creates plans, doesn't execute
  ```bash
  RedTeamAgent
  ```
  **Note:** RedTeamAgent appears to be incomplete/beta. It only creates a hierarchical plan but doesn't actually execute it. The execution code is missing. Use **ReAct** instead.

Both will prompt you for a task after launching, but only ReAct will actually perform the attack.

## Verifying Connectivity

Before running the agent, you can test connectivity from inside the container:

```bash
docker run -it --rm --network host redteamagent
# Inside container:
curl http://localhost:3000
# or with host.docker.internal:
curl http://host.docker.internal:3000
```

If you see HTML output, the connection works!

## Quick Start Summary (macOS)

1. **Edit config** (`attacker3/src/redteamagent/config/config.json`) - set your `api_key`
2. **Build image**: `cd attacker3 && docker build -t redteamagent .`
3. **Start vulnerable app**: `cd vulnerable-app && npm start` (runs on `localhost:3000`)
4. **Find your host IP**: `ifconfig | grep "inet " | grep -v 127.0.0.1` (use the first IP, usually `192.168.64.1`)
5. **Run agent**: `docker run -it --rm redteamagent`
6. **Inside container, run**: `ReAct`
7. **Enter task**: `Attack the web application running on http://192.168.64.1:3000...` (use your actual IP)

## Notes

- **Use `--network host`** to access `localhost:3000` from inside Docker
- **Use ReAct**, not RedTeamAgent (RedTeamAgent doesn't execute, only plans)
- The agent will create a `saved_<N>` folder with logs of all actions
- Make sure the vulnerable app is running before starting the agent
- The agent uses tools like `nmap`, `curl`, `dirb`, etc. which are available in the Kali-based container
