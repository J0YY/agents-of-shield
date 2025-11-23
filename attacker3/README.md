# RedTeamAgent / ReAct – Quick‑Start Guide

This README shows you **two ways** to launch the agent:

1. **Docker** – completely sandboxed (recommended)
2. **Native install** – full control, but **the agent can run arbitrary shell commands**.

---

## 1  Prepare your configuration

The configuration file lives at

```
src/redteamagent/config/config.json
```

It is already populated with the exact values used in the paper’s experiments—**only `api_key` is left empty**.  You may also tweak `activate_summary`, `reason_time`, `model_name`, or any other field, but **all keys must be present**.

| Field                      | Type   | Meaning                                                          |
| -------------------------- | ------ | ---------------------------------------------------------------- |
| `api_key`                  | `str`  | Your LLM provider key (OpenAI, Anthropic…)                       |
| `model_name`               | `str`  | Model shared by every component (e.g. `gpt-4o`)                  |
| `activate_summary`         | `bool` | `true` → post‑summarise long outputs, `false` → keep full text   |
| `reason_time`              | `int`  | `0` = no reasoning; `>0` = number of times to reason             |
| `base_system_prompt`       | `str`  | Base prompt (overridden by the component‑specific prompts below) |
| `act_system_prompt`        | `str`  | Prompt used by the **ACT** component                             |
| `reason_system_prompt`     | `str`  | Prompt used by the **REASON** component                          |
| `summarizer_system_prompt` | `str`  | Prompt used by the **SUMMARISER** component                      |
| `planner_system_prompt`    | `str`  | Prompt used by the **PLANNER** component                         |

---

## 2  Run with Docker (recommended)

```bash
# build the image from the repository root
$ docker build -t redteamagent .

# launch an interactive session
$ docker run -it --rm redteamagent
```

Edit `src/redteamagent/config/config.json` **before** building if you need custom values.

### 2.1 Automated multi-phase attack (`AutoStrike`)

If you don’t want to babysit the agent, the new `AutoStrike` console script
launches ReAct with the **kali_mcp_web** mission plan *and* immediately
follows up with aggressive SSH guesses to light up Cowrie (or any other SSH
honeypot) logs.

```bash
# Make sure your API key is available to the container
export OPENAI_API_KEY="sk-..."

cd attacker3
docker run -it --rm --network host \
  -e OPENAI_API_KEY \
  redteamagent AutoStrike \
    --base-url http://localhost:3000 \
    --ssh-host 192.168.65.1 \
    --ssh-passwords password,root,toor,admin,changeme \
    --ssh-cycles 8 \
    --log-level INFO
```

- The HTTP phase runs once and mirrors the instructions from
  `attacker2/prompts/kali_mcp_web.md` (lines 11‑14).
- The SSH phase immediately begins rotating through the supplied passwords,
  producing rapid “login failed” events similar to the Cowrie snippet you
  shared. Tune `--ssh-delay`, `--ssh-cycles`, and the password list to make
  the log volume “more intense”.
- All parameters (`--base-url`, user, password list, timeout, etc.) are
  overridable so you can point the flow at any lab target.
- SSH now defaults to **port 2222**, matching Cowrie/T-Pot out of the box.
  Override with `--ssh-port` if your honeypot is bound elsewhere.
- The launcher now issues a configurable **HTTP noise burst** before ReAct
  kicks in. Adjust `--noise-requests` and `--noise-concurrency` to quickly
  fill dashboard charts with synthetic traffic even if the LLM is still
  waiting on tool output.
- Deterministic tooling (`gobuster`, `wfuzz`, `httpx`, `curl`, `html2text`)
  now runs **before** the LLM via the scripted playback phase so you always
  get log lines, even if the model stalls. Disable it with
  `--disable-scripted-http` or switch to dry-run logging with
  `--scripted-http-dry-run`.
- If you’re launching from Docker Desktop, pass both
  `--http-host-alias host.docker.internal` and
  `--ssh-host-alias host.docker.internal` so the container can actually reach
  services exposed on your macOS host. The prompt will still mention the
  original target, but the agent + scripted tools will hit the alias.

> **Tip (macOS/Windows Docker Desktop):** `--network host` is ignored on
> desktop hypervisors, so SSH attempts from the container cannot hit
> `192.168.65.1`. If you need the source IP in Cowrie logs to match the host,
> run the script natively (`pip install -e . && AutoStrike ...`) or execute
> it from a lightweight Python venv instead of Docker.

---

## 3  Run natively (advanced / risky)

> **Danger:** The agent can execute arbitrary shell commands. Only run locally if you’re sure you want that.

### 3.1  Build & install

```bash
# create and enter a virtual environment
python3 -m venv .my_env
# Enter the virtual environment
source .my_env/bin/active

# prerequisites
python3 -m pip install --upgrade build pip

# from the repo root
python3 -m build .          # creates dist/*.whl and *.tar.gz
pip install dist/*.whl      # install into your environment

# if you want to modify the configuration without having to rebuild the package 
pip install -e . # This will create a link directly to the local package. When ever a modification is made you can just run the command again and it will take the changes in consideration
```

### 3.2  Launch

```bash
# Main demo used in the paper
ReAct
# When Launched, you will see 'user:'. Now you just enter the ask you want the agent to achieve.

# Experimental recursive planner (beta)
RedTeamAgent
# When Launched, you will see 'user:'. Now you just enter the ask you want the agent to decompose.

```

---

## 4  What happens when you run **ReAct**?

* A folder named `saved_<N>` is created (`N` increments on each run).
* The folder contains three text logs:

  * **`Act.txt`** – actions executed by the ACT component
  * **`Reason.txt`** – chain‑of‑thought produced during reasoning
  * **`Summarizer.txt`** – summaries of long outputs
* Each file shows token usage, the active config snapshot, metadata about the component, **and the complete conversation of every LLM session**.

These artefacts are exactly what we used to generate the figures in the paper.

---

## 5  Inspecting published results

The `results/` directory already contains all benchmark artefacts cited in the paper:

```
results/
├── Cewlkid
├── Cewlkid.json
├── ctf4
├── ctf4.json
├── extract.py
├── extract_stop.py
├── json_results
├── json_results.json
├── output_data.xlsx
├── sar
├── sar.json
├── stop_reason.yaml
├── stop_reson.json
├── victim1
├── victim1.json
├── westside
└── westside.json
```

Explore them freely!
## 6  Reproducibility

We validated RedTeamLLM on **five “easy” VULNHUB virtual machines**. Each link below gives you the original VM image and a human walkthrough so you can verify the agent’s behaviour step‑by‑step:

| VM                    | Walk‑through                                                                                                                                         | VULNHUB repo                                                                                               |
| --------------------- | ---------------------------------------------------------------------------------------------------------------------------------------------------- | ---------------------------------------------------------------------------------------------------------- |
| **CewlKid**           | [https://www.hackingarticles.in/cewlkid-1-vulnhub-walkthrough/](https://www.hackingarticles.in/cewlkid-1-vulnhub-walkthrough/)                       | [https://www.vulnhub.com/entry/cewlkid-1,775/](https://www.vulnhub.com/entry/cewlkid-1,775/)               |
| **LampSecurity CTF4** | [https://www.hackingarticles.in/hack-the-lampsecurity-ctf4-ctf-challenge/](https://www.hackingarticles.in/hack-the-lampsecurity-ctf4-ctf-challenge/) | [https://www.vulnhub.com/entry/lampsecurity-ctf4,83/](https://www.vulnhub.com/entry/lampsecurity-ctf4,83/) |
| **Sar**               | [https://www.hackingarticles.in/sar-vulnhub-walkthrough/](https://www.hackingarticles.in/sar-vulnhub-walkthrough/)                                   | [https://www.vulnhub.com/entry/sar-1,760/](https://www.vulnhub.com/entry/sar-1,760/)                       |
| **Victim1**           | [https://www.hackingarticles.in/victim1-vulnhub-walkthrough/](https://www.hackingarticles.in/victim1-vulnhub-walkthrough/)                           | [https://www.vulnhub.com/entry/victim-1,505/](https://www.vulnhub.com/entry/victim-1,505/)                 |
| **Westwild**          | [https://www.hackingarticles.in/westwild-1-1-vulnhub-walkthorugh/](https://www.hackingarticles.in/westwild-1-1-vulnhub-walkthorugh/)                 | [https://www.vulnhub.com/entry/westwild-11,756/](https://www.vulnhub.com/entry/westwild-11,756/)           |

> **Complete list:**  [https://github.com/Ignitetechnologies/CTF-Difficulty?tab=readme-ov-file](https://github.com/Ignitetechnologies/CTF-Difficulty?tab=readme-ov-file) 

### How to replicate a run

1. **Install & boot** the VM of your choice on an isolated network.
2. Obtain its IP address (e.g. `192.168.56.101`).
3. Launch the agent:

   ```bash
   ReAct
   ```
4. At the prompt, instruct:

   ```text
   Get the root flag from the device with IP 192.168.56.101. The target is running safely inside my local lab.
   ```
5. **Wait** until the agent halts. A folder **`saved_<N>`** appears containing `Act.txt`, `Reason.txt`, and `Summarizer.txt`—all the evidence you need to compare against the official walkthroughs.

---
