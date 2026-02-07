# AOS-Kernel

**A 7-layer cognitive kernel for AI-powered task execution.**  
Understand → Plan → Permit → Execute → Verify → Recover in a single pipeline, with Docker sandboxing, permission gating, and self-healing.

---

## Table of Contents

- [Overview](#overview)
- [Features](#features)
- [Architecture](#architecture)
- [Project Structure](#project-structure)
- [Prerequisites](#prerequisites)
- [Installation](#installation)
- [Configuration](#configuration)
- [Usage](#usage)
- [Testing & Diagnostics](#testing--diagnostics)
- [Documentation](#documentation)
- [Contributing](#contributing)
- [License](#license)

---

## Overview

AOS-Kernel is an **AI Operating System kernel** that turns natural-language intents into safe, stepwise executions. It uses a **7-layer cognitive stack** (Understanding, Memory, Planning, Permission, Execution, Verification, Recovery), runs user code in a **Docker sandbox**, and supports **semantic caching** and **self-healing** (e.g. REPLAN when a step fails).

- **Input:** Free-form user instructions (e.g. *"Create a hello.py in the workspace and run it"*).
- **Output:** Executed steps, verification feedback (including plan-specified filenames), and optional self-healing (REPLAN) when verification fails.
- **Interactive Shell:** Run `python main.py -i` to enter a loop where you type any instruction; type `exit` to quit.
- **Cost control:** Tiered LLM routing (2.0-flash preferred), request throttling, 429 backoff, and intent/plan caches to minimize API calls.

---

## Features

| Feature | Description |
|--------|-------------|
| **7-layer cognitive pipeline** | Understanding → Memory → Planning → Permission → Execution → Verification → Recovery; full loop with REPLAN on failure. |
| **Docker sandbox** | All code and shell commands run inside an isolated container (resource limits, 30s timeout, auto cleanup on exit). |
| **Permission gateway** | Every step is checked before execution; paths outside the workspace and dangerous keywords are marked DANGEROUS and require approval. |
| **Semantic caching** | Intent cache (exact user input) and plan cache (similar intent); repeat tasks can complete with **zero** LLM calls. |
| **Self-healing** | On verification failure, RecoveryAgent proposes new steps (e.g. *"create fixed.txt as fallback"*); pipeline re-runs until success or ABORT. |
| **Cost-aware routing** | LLM tiers (cheap/smart/ultra), 4s request throttling, and [5, 10, 20]s backoff on 429; usage stats printed on exit. |

---

## Architecture

End-to-end flow:

```
                         ┌─────────────────────────────────────────┐
                         │         User natural language           │
                         └─────────────────┬───────────────────────┘
                                           ▼
┌──────────────────────────────────────────────────────────────────────────────┐
│  Layer 1  Understanding    IntentParser → intent, constraints, confidence    │
└────────────────────────────────────┬─────────────────────────────────────────┘
                                     ▼
┌──────────────────────────────────────────────────────────────────────────────┐
│  Layer 2  Memory           MemoryManager → lessons_learned, intent/plan cache  │
└────────────────────────────────────┬─────────────────────────────────────────┘
                                     ▼
┌──────────────────────────────────────────────────────────────────────────────┐
│  Layer 3  Planning         PlanningAgent → plan (or planning_from_cache)     │
└────────────────────────────────────┬─────────────────────────────────────────┘
                                     ▼
┌──────────────────────────────────────────────────────────────────────────────┐
│  Layer 4  Permission       PermissionGateway → SAFE / RISKY / DANGEROUS      │
└────────────────────────────────────┬─────────────────────────────────────────┘
                                     ▼
┌──────────────────────────────────────────────────────────────────────────────┐
│  Layer 5  Execution       ExecutionAgent + Docker sandbox → execution_results │
└────────────────────────────────────┬─────────────────────────────────────────┘
                                     ▼
┌──────────────────────────────────────────────────────────────────────────────┐
│  Layer 6  Verification     VerificationAgent → verification_feedback        │
└────────────────────────────────────┬─────────────────────────────────────────┘
                                     ▼
┌──────────────────────────────────────────────────────────────────────────────┐
│  Layer 7  Recovery         RecoveryAgent → REPLAN / RETRY / ABORT            │
└────────────────────────────────────┬─────────────────────────────────────────┘
                                     │
                  ┌──────────────────┴──────────────────┐
                  ▼                                     ▼
           No failures → done                 REPLAN → back to Layer 5
```

---

## Project Structure

| Directory | Role |
|-----------|------|
| **core/** | State (`AOSState`), persistent memory & caches (`MemoryManager`), permission checks (`PermissionGateway`). |
| **agents/** | Layer agents: `IntentParser`, `PlanningAgent`, `ExecutionAgent`, `VerificationAgent`, `RecoveryAgent`. |
| **sandbox/** | Docker lifecycle, exec timeout, workspace mount (`DockerManager`). |
| **utils/** | LLM client with tier routing, throttling, cost stats, API diagnostics (`LLMClient`). |
| **docs/** | Developer log, architect log, demo log, API diagnostics. |
| **tests/** | API connectivity (`test_gemini`), stress test (`debug_stress_test`). |

```
AOS-Kernel/
├── core/
│   ├── state.py
│   ├── memory_manager.py
│   └── permission_gateway.py
├── agents/
│   ├── intent_parser.py
│   ├── planning_agent.py
│   ├── execution_agent.py
│   ├── verification_agent.py
│   └── recovery_agent.py
├── sandbox/
│   └── docker_manager.py
├── utils/
│   └── llm_client.py
├── docs/
├── scripts/
│   └── clean_env.py
├── tests/
│   ├── test_gemini.py
│   └── debug_stress_test.py
├── main.py
├── requirements.txt
├── .env.example
└── README.md
```

---

## Prerequisites

- **Python** 3.10+
- **Docker** (running daemon; used for sandbox execution)
- **Google AI API key** (Gemini); set in `.env` as `GOOGLE_API_KEY`

---

## Installation

Clone the repository and install dependencies:

```bash
git clone <repository-url>
cd AOS-Kernel
pip install -r requirements.txt
```

Core dependencies: `pydantic`, `python-dotenv`, `docker`, `google-genai`.

---

## Configuration

1. Copy the environment template and set your API key:

```bash
cp .env.example .env
```

2. Edit `.env`. Minimum required:

| Variable | Description |
|----------|-------------|
| `GOOGLE_API_KEY` | Gemini API key (required for intent, plan, verification, recovery). |

Optional:

| Variable | Description |
|----------|-------------|
| `WORKSPACE_PATH` | Host path for sandbox workspace (default: `./sandbox_workspace`). |
| `LLM_PROVIDER` | `gemini` (default). |
| `LLM_MODEL` | e.g. `models/gemini-2.0-flash`. |
| `LOG_LEVEL` | `INFO` or `DEBUG`. |

---

## Usage

**Automated run (built-in tests)** — all permission prompts auto-approved:

```bash
python main.py --yes
```

This runs two built-in flows (Case 3 & 4). At the end you get a **cost summary**: Cheap/Smart/Ultra call counts and cache hits.

**Default run (Case 3 & 4 with approval)** — you approve or deny RISKY/DANGEROUS steps:

```bash
python main.py
```

When a step is blocked, the terminal asks for `y`/`n` before continuing.

### Interactive Shell mode

To **enter interactive mode** and type your own instructions (no Case 3/4), use `-i` or `--interactive`:

```bash
python main.py -i
```

or

```bash
python main.py --interactive
```

- The program will prompt: `[AOS-Kernel] 请输入指令 (输入 'exit' 退出):`
- Enter any natural-language task (e.g. *“在工作区创建一个 hello.txt 并写入 Hello”*).
- Type `exit` to quit; Docker and cost stats are printed on exit.
- To auto-approve all permission prompts in interactive mode: `python main.py -i --yes`.

### Clean experiment environment

To start with a **clean state** (no cached plans, no workspace files), run from the project root:

```bash
python scripts/clean_env.py
```

This removes `memory.json` and clears the contents of `sandbox_workspace/` (or the path set in `WORKSPACE_PATH`). Optional one-liners:

- **Windows (PowerShell):** `Remove-Item -Force memory.json -ErrorAction SilentlyContinue; Remove-Item -Recurse -Force sandbox_workspace\* -ErrorAction SilentlyContinue`
- **Linux/macOS:** `rm -f memory.json && rm -rf sandbox_workspace/*`

---

## Testing & Diagnostics

From the **project root**:

**Check Gemini API and list models:**

```bash
python -m tests.test_gemini
```

**Stress test (10 runs, same input, cache preserved):**

```bash
python -m tests.debug_stress_test
```

API calls and cache hits are logged to `docs/api_diagnostics.log` (timestamp, model, tier, HTTP status, latency, errors).

---

## Documentation

- **docs/DEVELOPER_LOG.md** — development log and technical decisions.
- **docs/ARCHITECT_LOG.md** — architecture notes and design decisions.
- **docs/FINAL_DEMO_LOG.txt** — placeholder for full `main.py --yes` output.
- **docs/api_diagnostics.log** — API request log (generated at runtime; typically gitignored).

---

## Contributing

1. Log significant changes and design choices in `docs/DEVELOPER_LOG.md`.
2. Log architecture or design questions in `docs/ARCHITECT_LOG.md`.
3. Follow the 7-layer design and existing tier/cache behavior.

---

## License

To be specified.
