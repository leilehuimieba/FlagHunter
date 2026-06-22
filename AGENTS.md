# FlagHunter — AGENTS.md

## Project overview

**FlagHunter** (v0.4.x) is a self-developed, AI-powered offensive-security automation
framework built in Python, focused on CTF and authorised penetration testing. It wraps
LiteLLM to support any provider (Anthropic, OpenAI, etc.) and exposes a TUI, a CLI, and an
MCP server interface. The agent can run tools locally or inside a Docker sandbox (base or
Kali image).

> **Naming note:** the project, Python package, and entry-point command are all named
> `flaghunter`. Some configuration still accepts the historical `PENTESTAGENT_*` environment
> variables as backward-compatible aliases (auto-mapped onto `FLAGHUNTER_*` at startup), so
> existing `.env` files keep working. FlagHunter is an independent project and does **not**
> depend on or derive from any external upstream project.

## Tech stack

- **Python 3.10+**, packaged with Hatchling (`pyproject.toml`)
- **LiteLLM** — provider-agnostic LLM wrapper
- **Textual** — TUI framework (`flaghunter/interface/`)
- **Typer** — CLI framework
- **Playwright** — browser tool
- **MCP (Model Context Protocol)** — both client (consuming external servers) and server
  (exposing FlagHunter to Claude Desktop / Cursor / etc.)
- **sentence-transformers + rank-bm25** — optional RAG engine: dense (NumPy cosine) + BM25, RRF fusion (`pip install -e ".[rag]"`)

## Repository layout

```
flaghunter/
  agents/
    crew/           # Multi-agent mode: orchestrator + worker pool + shadow graph
    pa_agent/       # Single-agent implementation (includes CTF dispatcher subsystem)
    state.py        # Shared agent state machine (AgentStateManager)
  config/
    settings.py     # Global Settings dataclass (singleton via get_settings())
    constants.py    # Model defaults, iteration limits, etc.
    env.py          # FLAGHUNTER_* env access + legacy PENTESTAGENT_* aliasing
  interface/
    cli.py          # Typer CLI entry-point
    tui.py          # Textual TUI (chat, rewind/fork, embedded terminals)
    notifier.py     # Event bus between agent and UI
    utils.py        # Shared UI helpers
    initializer.py  # Shared component bootstrap (TUI / CLI / MCP server)
    conversation_store.py  # Persistent conversation snapshots
  knowledge/
    graph.py        # ShadowGraph — derives strategic insights from notes
    indexer.py      # Indexes knowledge sources for RAG
    rag.py          # Hybrid dense (NumPy cosine) + BM25 retrieval, RRF fusion
    embeddings.py   # OpenAI & local sentence-transformer embeddings
  llm/
    config.py       # LiteLLM configuration
    llm.py          # LLM wrapper with M1 provider failover
    memory.py       # Conversation/token management with auto-summarization
    utils.py        # Streaming helpers, JSON parsing, token counting
  mcp/
    manager.py      # MCP client manager (connects to external MCP servers)
    transport.py    # Transport abstractions (stdio / SSE / FIFO / WebSocket)
    tools.py        # Wraps MCP tools into FlagHunter Tool objects
    mcp_rag_optimizer.py  # Meta-tool when MCP server exposes >128 tools
    server/         # FlagHunter as MCP server
  playbooks/
    base_playbook.py
    thp3_recon.py / thp3_network.py / thp3_web.py
  runtime/
    runtime.py      # LocalRuntime (Playwright + subprocess)
    docker_runtime.py   # DockerRuntime (container exec)
    ssh_runtime.py      # SSHRuntime (Kali VM)
  tools/
    registry.py     # Tool dataclass & global _tools registry
    loader.py       # Discovers & dynamically imports tool modules
    executor.py     # Executes tool calls, tracks tokens, flag scanning, scope checks
    token_tracker.py
    tool_guard.py   # Pre-execution tool availability probe
    _tool_env.py    # Local binary PATH discovery & install hints
    mcp_agent.py    # spawn_mcp_agent / despawn_mcp_agent dynamic tools
    terminal/       # Shell execution tool
    browser/        # Playwright browser tool
    web_search/     # Tavily/Brave/OpenCLI web search
    notes/          # Persistent findings store → loot/notes.json
    finish/         # Signals task completion, plan step tracking
    http_request/   # HTTP proxy via httpx
    nmap/           # Nmap scanner wrapper
    sqlmap/         # SQLMap wrapper
    dirscan/        # Directory brute-force (ffuf/gobuster/dirsearch)
    nuclei/         # Nuclei scanner wrapper
    subfinder/      # Subdomain enumeration
    afrog/          # Afrog vulnerability scanner
    fscan/          # Fscan network scanner
    waf/            # WAF detection & bypass config
    binary/         # Binary static analysis (strings, checksec, r2)
    pwn/            # Pwntools wrapper
    msf/            # Metasploit RPC wrapper
    login_flow/     # Browser-based login automation
    opencli_browser/# OpenCLI browser bridge
    katana/         # Modern web crawler (JS rendering, endpoint discovery)
    dalfox/         # XSS scanner (reflected/stored/DOM, WAF evasion)
    gau/            # Historical URL discovery (Wayback/OTX/CommonCrawl)
    knowledge_search/  # RAG-powered knowledge base search
    shadowgraph/    # ShadowGraph strategic insights & attack paths
    gf/             # Pattern matcher for security-relevant strings
    ...
  workspaces/       # Workspace isolation helpers
  cpa_modules/      # CPA feature modules (subpackage of flaghunter)
    m1_api_hub/     # M1: Multi-provider API hub with failover
    m2_ctf_kit/     # M2: CTF toolkit (playbook engine, crypto, pwn, reverse, flag submitter)
    m3_reporter/    # M3: Report generation (auto-triggered by finish tool)
    m4_audit_guard/ # M4: Scope enforcement & audit logging
    m5_swarm_link/  # M5: Swarm bridge & pheromone routing
    m6_turbo/       # M6: Performance optimizations
loot/               # Persisted notes, token usage, strategy memory (git-ignored)
mcp_examples/       # Example MCP configs and adapters
scripts/            # setup.sh / setup.ps1
tests/              # pytest suite
```

## Configuration

Create `.env` in the project root:

```
ANTHROPIC_API_KEY=sk-ant-...
FLAGHUNTER_MODEL=claude-sonnet-4-20250514

# Optional
TAVILY_API_KEY=...          # web_search tool
OPENAI_API_KEY=sk-...       # if using OpenAI

# CPA Module switches
CPA_M1_API_HUB=true
CPA_M2_CTF_KIT=true
CPA_M2_PWN_TOOLS=true
CPA_M2_CRYPTO_TOOLS=true
CPA_M2_REVERSE_TOOLS=true
CPA_M2_FLAG_SUBMITTER=true
CPA_M5_SWARM_LINK=true
```

> Legacy `PENTESTAGENT_*` variable names (e.g. `PENTESTAGENT_MODEL`) are still honoured as
> aliases for the corresponding `FLAGHUNTER_*` names.

Settings are managed by `flaghunter/config/settings.py` (`get_settings()` singleton).
The MCP external-server config lives in `mcp_servers.json` (Claude Desktop format).

## Running the project

```bash
source .venv/bin/activate
flaghunter                    # TUI
flaghunter -t 192.168.1.1     # TUI with pre-set target
flaghunter tui --docker       # Use Docker sandbox for tool execution
flaghunter run -t example.com --playbook thp3_web   # Run a playbook
flaghunter mcp_server --type stdio   # Expose as MCP server (STDIO)
flaghunter mcp_server --type sse     # Expose as MCP server (HTTP/SSE, port 8080)
```

## FlagHunter as MCP server

FlagHunter can expose itself as an MCP server so any MCP-compatible client
(Claude Desktop, Cursor, etc.) can drive it programmatically.

### Transports

```bash
# STDIO — for local clients
flaghunter mcp_server --type stdio
flaghunter mcp_server --type stdio --target 192.168.1.1 --scope 192.168.1.0/24 --docker

# SSE (HTTP) — for remote/networked clients (default: 0.0.0.0:8080)
flaghunter mcp_server --type sse
flaghunter mcp_server --type sse --host 0.0.0.0 --port 8080 --target 10.0.0.1
```

### Claude Desktop config (`claude_desktop_config.json`)

```json
{
  "mcpServers": {
    "flaghunter": {
      "command": "flaghunter",
      "args": ["mcp_server", "--type", "stdio"]
    }
  }
}
```

### Tools exposed by the MCP server

| Category | Tools |
|----------|-------|
| Status / config | `get_server_status`, `get_config`, `update_config` |
| Task execution | `run_task` (blocking), `run_task_async` (returns task_id) |
| Task inspection | `list_tasks`, `get_task_status`, `get_task_result`, `await_tasks` |
| Task control | `cancel_task` |
| Tool management | `list_tools`, `enable_tool`, `disable_tool` |
| Conversation | `get_conversation_history`, `reset_conversation` |
| Memory | `store_memory`, `retrieve_memory`, `clear_memory` |
| Observability | `get_logs`, `get_metrics` |

### Async task pattern

```
run_task_async  task="Enumerate subdomains of example.com"
run_task_async  task="Run nmap SYN scan on example.com"
await_tasks     task_ids=["<id1>", "<id2>"]  timeout_seconds=300
get_task_result task_id="<id1>"
get_task_result task_id="<id2>"
```

### `mcp_server` flags

| Flag | Default | Description |
|------|---------|-------------|
| `--type` | *(required)* | `stdio` or `sse` |
| `--host` | `0.0.0.0` | SSE bind host |
| `--port` | `8080` | SSE bind port |
| `--target` | none | Primary pentest target |
| `--scope` | `[]` | In-scope CIDRs (space-separated) |
| `--model` | env var | Overrides `FLAGHUNTER_MODEL` |
| `--docker` | false | Use DockerRuntime |
| `--no-rag` | false | Skip RAG initialisation |
| `--no-mcp` | false | Skip external MCP connections |

---

## TUI commands (quick reference)

| Command | Description |
|---------|-------------|
| `/assist <task>` | Single-shot instruction with tool execution |
| `/agent <task>` | Autonomous single-agent loop |
| `/crew <task>` | Multi-agent: orchestrator spawns specialised workers |
| `/interact <task>` | Guided interactive chat |
| `/target <host>` | Set target |
| `/tools` | List available tools |
| `/notes` | Show saved findings |
| `/report` | Generate report from session |
| `/mcp list/add` | Manage MCP servers |
| `/api` | M1 API Hub status panel |
| `/ctf list` | List CTF playbooks |
| `/ctf run <playbook> <target>` | Execute CTF playbook |
| `/ctf next` | Advance to next playbook phase |
| `/ctf flag <flag>` | Submit flag to platform |
| `/ctf decode <ciphertext>` | Auto crypto solve |
| `/ctf rev <binary>` | Quick reverse analysis |
| `Esc` | Stop running agent |

## Conversation history controls (TUI)

Each user message in the TUI exposes two inline buttons: **rewind** and **fork**.

### Rewind

Clicking **rewind** on a user message opens a confirmation dialog and then truncates the
conversation back to just before that message — both in the UI and in the agent's
in-memory history. Use it to retry a query from scratch without saving the discarded path.

### Fork

Clicking **>> fork** on a user message:

1. **Saves** the current full conversation to the conversation store
   (`ConversationStore`, persisted under the workspaces base directory) and reports
   the short ID of the saved snapshot.
2. **Truncates** the conversation to just before the selected message (same as rewind).

This lets you branch off from any point while keeping the original conversation
retrievable. Typical use-case: try an alternative approach from a given message without
losing the thread you had so far.

Both controls are implemented in `flaghunter/interface/tui.py` via
`RewindButton` / `ForkButton` widgets and their corresponding `*ConfirmScreen` modals.

---

## Key architectural patterns

### Agent core loop (`BaseAgent._run_loop`)

All agents (single, crew worker, MCP task) inherit from `BaseAgent` and share the same
state-machine-driven loop:

```text
agent_loop()
  ├── reset()
  ├── state_manager.transition_to(THINKING)
  ├── _auto_generate_plan()   # Round 1 forces a plan
  └── _run_loop()             # Core iterator
        ├── LLM.generate()    # With tool-calling
        ├── _execute_tools()  # Concurrent execution
        ├── _expand_plan()    # Discovery-driven plan expansion
        ├── _replan()         # Tactical replanning on failure
        └── plan.is_complete() → summary → COMPLETE
```

States (`agents/state.py`): `IDLE → THINKING → EXECUTING → (THINKING|COMPLETE|ERROR)`.
Illegal transitions are rejected; `force_transition()` exists for recovery paths.

### Tool registration

Tools self-register via decorators in `flaghunter/tools/registry.py`:

```python
@register_tool(name="nmap", description="...", schema=ToolSchema(...), category="scanner")
async def nmap(arguments: dict, runtime: Runtime) -> str:
    ...
```

`loader.py` walks `flaghunter/tools/` subdirectories and `importlib.import_module`s
them, triggering registration into the global `_tools` dict. No explicit `register()`
calls are required.

### CTF solving engine (`CTFTaskDispatcher`)

The CTF subsystem (`agents/pa_agent/ctf_dispatcher.py`) is **not** an LLM free-for-all.
It is a deterministic dispatcher wrapped around LLM-assisted strategy selection:

1. **Recon** — browser fingerprinting extracts HTML, forms, endpoints, cookies.
2. **HypothesisEngine** (`hypothesis_engine.py`) — rule-based generation of attack
   hypotheses (e.g. `/visit + /admin + auth_form → xss_admin_bot_sid`).
   Includes *Observation Floor* (hypotheses without evidence cannot outrank supported
   ones) and *Devil's Advocate* abort conditions.
3. **StrategyRegistry** (`strategy_registry.py`) — 15+ `StrategyDefinition`s with
   preconditions, execute lambdas, success/failure signals, escalation conditions.
4. **CapabilityRegistry** (`capability_registry.py`) — each primitive has multiple
   implementations ranked by quality. Auto-degrades (e.g. `sqlmap → manual_payload`).
5. **CTFVerifier** (`verifier.py`) — four-tier flag evidence:
   `candidate → runtime → verified → rejected`.
   Runtime flags hit an auto-submit gate; verified flags stop all workers.
6. **RecoveryController** (`recovery.py`) — post-chain rule-based decisions:
   `explore_agenda`, `switch_chain`, `stop_no_progress`, `wait_for_verification`.
7. **StrategyMemory** (`strategy_memory.py`) — cross-challenge persistent memory
   (NDJSON at `loot/strategy_memory.json`). Fingerprints are matched for similarity
   scoring; entries auto-mute after ≥5 uses with <20% success.

### Multi-agent / Crew mode

`CrewOrchestrator` (`agents/crew/orchestrator.py`) spawns typed workers via
`WorkerPool` (`agents/crew/worker_pool.py`):

- Worker types: `default`, `web`, `recon`, `exploit`, `crypto`.
- Each worker gets a **filtered tool set** and an **isolated `LocalRuntime`**.
- Dependencies (`depends_on`) are awaited before spawning.
- ShadowGraph (`knowledge/graph.py`) builds a NetworkX DiGraph from notes to derive
  strategic insights (unused credentials, high-value targets, multi-hop attack paths).
- M5 Swarm bridge (`agents/crew/swarm_bridge.py`) deposits pheromone routes when
  `CPA_M5_SWARM_LINK=true`.

### M1 API failover (`flaghunter/cpa_modules/m1_api_hub`)

`LLM._call_with_provider_failover()` integrates M1 transparently:

- `ProviderManager` selects the healthiest provider matching the `task_hint` tier
  (`planning` → heavy, `tool_parse` → light) via `model_router.route()`.
- `FailoverMonitor` runs two concurrent loops per provider:
  - `_health_check_loop()` (30s) — marks DOWN after 3 consecutive failures.
  - `_recovery_loop()` (60s) — confirms recovery with a real request before marking
    HEALTHY again.
- Error classification: `PERMANENT`, `TRANSIENT_NETWORK`, `TRANSIENT_REMOTE` (rate-limit),
  `LOGIC` (context length). Rate-limits get local jittered backoff; logic errors are
  thrown immediately.
- `CostTracker` enforces daily budgets and auto-rolls over at midnight.

### MCP client & server

**Client** (`mcp/manager.py`, `mcp/transport.py`):
- Reads `mcp_servers.json`; supports `stdio`, `SSE`, `FIFO`, `WebSocket` transports.
- Each `MCPServer` serialises communication via `asyncio.Lock` to prevent message-ID
  collisions.
- If a server exposes >128 tools, a single `mcp_{server}_rag_optimizer` meta-tool
  replaces them. It embeds tool names+descriptions and retrieves relevant subsets on
  demand (`mcp/mcp_rag_optimizer.py`).

**Server** (`mcp/server/`):
- `MCPRouter` handles JSON-RPC: `initialize`, `tools/list`, `tools/call`.
- Each task spawns a **fresh** `FlagHunterAgent` + **fresh** `Runtime` to avoid
  state pollution (`mcp/server/mcp_tools.py::_make_agent()`).
- `spawn_mcp_agent` / `despawn_mcp_agent` tools (`tools/mcp_agent.py`) launch child
  agents over FIFO/PTY, inject their tools into the parent, and forward notifications.

### RAG & ShadowGraph

**RAG** (`knowledge/rag.py`):
- Indexes `.txt`/`.md`/`.json` under `knowledge/` (chunk_size=1000, overlap=200).
- Supports OpenAI embeddings or local `sentence-transformers` (`all-MiniLM-L6-v2`).
- Cosine-similarity search with threshold 0.35; results truncated to token budget.
- Persistent index at `embeddings/index.pkl` (pickle).

**ShadowGraph** (`knowledge/graph.py`):
- Incremental NetworkX DiGraph built from `notes.json`.
- Node types: `cred:*`, `service:{host}:{port}`, `endpoint:{host}:{path}`,
  `tech:{host}:{name}`, `vuln:{key}`.
- Edge types: `CONTAINS`, `AUTH_ACCESS`, `HAS_SERVICE`, `HAS_ENDPOINT`, `USES_TECH`,
  `AFFECTED_BY`.
- Strategic insights: unused credentials, high-value targets (degree counting), and
  multi-hop attack paths (`nx.shortest_path`).

### Runtime environments

Three interchangeable runtimes:

| Runtime | Commands | Browser | Proxy | Use case |
|---------|----------|---------|-------|----------|
| `LocalRuntime` | `asyncio.subprocess_shell` | Playwright (with fallback to system Chrome/Edge) | `httpx.AsyncClient` | Local development |
| `DockerRuntime` | `container.exec_run` | `curl` + regex (no GUI) | `mitmdump` | Isolated sandbox |
| `SSHRuntime` | `ssh` subprocess | `curl` + regex | Embedded Python | Kali VM |

`DockerRuntime` supports VPN via `.ovpn` upload + `openvpn --daemon`.
`SSHRuntime` supports key auth (batch) and password auth (askpass script).

### Tool executor guards (`tools/executor.py`)

Before every tool execution:
1. **M4 scope check** — `flaghunter.cpa_modules.m4_audit_guard.get_scope_enforcer().validate_sync()`.
2. **Cookie auto-inject** — for `sqlmap`, `dirscan`, `nuclei`, `afrog`: reads the latest
   `credential` note with `cookie_string` and injects it into arguments.
3. **Stealth mode** — if `FLAGHUNTER_STEALTH=1` or a `waf_detected` note exists,
   adds random delays and random User-Agent rotation.
4. **Flag scanning** — regex `flag{...}` / `CTF{...}` on stdout; auto-writes to notes.
5. **Missing-tool detection** — heuristic error matching triggers install suggestions.

### Conversation memory (`llm/memory.py`)

`ConversationMemory` prevents context-window overflow:
- Budget: `max_tokens * reserve_ratio` (default 128k * 0.8 = 102.4k).
- Trigger: when history exceeds 60% of budget.
- Strategy: keep the most recent 10 messages intact; summarise older messages in
  chunks of 10 via `_summarize_call()`, prepend as a system message.
- Token counting: `tiktoken` (cl100k_base) preferred; falls back to word-count
  estimation.

### LLM special handling

- **Anthropic prefill sanitisation** (`llm/llm.py`): if the message list ends with an
  `assistant` message, it is stripped because Claude rejects prefill.
- **LiteLLM drop_params**: `litellm.drop_params = True` so unsupported kwargs are
  silently discarded rather than causing errors.

## Development

```bash
pip install -e ".[dev]"
pytest                       # Run tests
pytest --cov=flaghunter      # With coverage
black flaghunter             # Format
ruff check flaghunter        # Lint
```

Test config: `pytest.ini_options` in `pyproject.toml`, asyncio mode = auto.

## Docker

```bash
docker compose build
docker compose run --rm flaghunter          # Base image
docker compose --profile kali run --rm flaghunter-kali   # Kali image
```

## Legal

Only use against systems you have **explicit written authorisation** to test.
Unauthorised access is illegal. MIT licence.
