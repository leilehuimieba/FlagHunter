<div align="center">

<img src="assets/pentestagent-logo.png" alt="PentestAgent Logo" width="220" style="margin-bottom: 20px;"/>

# PentestAgent
### AI Penetration Testing

[![Python](https://img.shields.io/badge/Python-3.10%2B-blue.svg)](https://www.python.org/) [![License](https://img.shields.io/badge/License-MIT-green.svg)](LICENSE.txt) [![Version](https://img.shields.io/badge/Version-0.2.0-orange.svg)](https://github.com/GH05TCREW/pentestagent/releases) [![Security](https://img.shields.io/badge/Security-Penetration%20Testing-red.svg)](https://github.com/GH05TCREW/pentestagent) [![MCP](https://img.shields.io/badge/MCP-Compatible-purple.svg)](https://github.com/GH05TCREW/pentestagent)

</div>

https://github.com/user-attachments/assets/a67db2b5-672a-43df-b709-149c8eaee975

## Requirements

- Python 3.10+
- API key for OpenAI, Anthropic, or other LiteLLM-supported provider

## Install

```bash
# Clone
git clone https://github.com/GH05TCREW/pentestagent.git
cd pentestagent

# Setup (creates venv, installs deps)
.\scripts\setup.ps1   # Windows
./scripts/setup.sh    # Linux/macOS

# Or manual
python -m venv venv
.\venv\Scripts\Activate.ps1  # Windows
source venv/bin/activate     # Linux/macOS
pip install -e ".[all]"
playwright install chromium  # Required for browser tool
```

## Configure

Create `.env` in the project root:

```
ANTHROPIC_API_KEY=sk-ant-...
PENTESTAGENT_MODEL=claude-sonnet-4-20250514
```

Or for OpenAI:

```
OPENAI_API_KEY=sk-...
PENTESTAGENT_MODEL=gpt-5
```

Any [LiteLLM-supported model](https://docs.litellm.ai/docs/providers) works.

## Run

```bash
pentestagent                    # Launch TUI
pentestagent -t 192.168.1.1     # Launch with target
pentestagent --docker           # Run tools in Docker container
```

## Docker

Run tools inside a Docker container for isolation and pre-installed pentesting tools.

### Option 1: Pull pre-built image (fastest)

```bash
# Base image with nmap, netcat, curl
docker run -it --rm \
  -e ANTHROPIC_API_KEY=your-key \
  -e PENTESTAGENT_MODEL=claude-sonnet-4-20250514 \
  ghcr.io/gh05tcrew/pentestagent:latest

# Kali image with metasploit, sqlmap, hydra, etc.
docker run -it --rm \
  -e ANTHROPIC_API_KEY=your-key \
  ghcr.io/gh05tcrew/pentestagent:kali
```

### Option 2: Build locally

```bash
# Build
docker compose build

# Run
docker compose run --rm pentestagent

# Or with Kali
docker compose --profile kali build
docker compose --profile kali run --rm pentestagent-kali
```

The container runs PentestAgent with access to Linux pentesting tools. The agent can use `nmap`, `msfconsole`, `sqlmap`, etc. directly via the terminal tool.

Requires Docker to be installed and running.

## Modes

PentestAgent has three modes, accessible via commands in the TUI:

| Mode | Command | Description |
|------|---------|-------------|
| Assist | `/assist <task>` | One single-shot instruction, with tool execution |
| Agent | `/agent <task>` | Autonomous execution of a single task. |
| Crew | `/crew <task>` | Multi-agent mode. Orchestrator spawns specialized workers. |
| Interact | `/interact <task>` | Interactive mode. Chat with the agent, it will help you and guide during the pentesting procedure |

### TUI Commands

```
/assist <task>    One single-shot instruction.
/agent <task>     Run autonomous agent on task
/crew <task>      Run multi-agent crew on task
/interact <task> Chat with the agent in guided mode
/target <host>    Set target
/tools            List available tools
/notes            Show saved notes
/report           Generate report from session
/memory           Show token/memory usage
/prompt           Show system prompt
/mcp <list/add>   Visualizes or adds a new MCP server.
/clear            Clear chat and history
/quit             Exit (also /exit, /q)
/help             Show help (also /h, /?)
```

Press `Esc` to stop a running agent. `Ctrl+Q` to quit.

## Playbooks

PentestAgent includes prebuilt **attack playbooks** for black-box security testing. Playbooks define a structured approach to specific security assessments.

**Run a playbook:**

```bash
pentestagent run -t example.com --playbook thp3_web
```

![Playbook Demo](assets/playbook.gif)

## Tools

PentestAgent includes built-in tools and supports MCP (Model Context Protocol) for extensibility.

**Built-in tools:** `terminal`, `browser`, `notes`, `web_search` (requires `TAVILY_API_KEY`)

### MCP Integration

PentestAgent supports MCP (Model Context Protocol) in two directions: **consuming** external MCP servers as tool sources, and **exposing itself** as an MCP server so external clients (Claude Desktop, Cursor, etc.) can drive PentestAgent programmatically.

---

#### Consuming External MCP Servers (Client Mode)

Configure `mcp_servers.json` to connect PentestAgent to any external MCP servers. Example config:

```json
{
  "mcpServers": {
    "nmap": {
      "command": "npx",
      "args": ["-y", "gc-nmap-mcp"],
      "env": {
        "NMAP_PATH": "/usr/bin/nmap"
      }
    }
  }
}
```

---

#### Exposing PentestAgent as an MCP Server (Server Mode)

PentestAgent can run as an MCP server, allowing any MCP-compatible client to submit tasks, inspect results, and control the agent remotely. Two transports are supported:

**STDIO** — for local clients (e.g. Claude Desktop, Cursor):

```bash
pentestagent mcp_server --type stdio
pentestagent mcp_server --type stdio --target 192.168.1.1 --scope 192.168.1.0/24
pentestagent mcp_server --type stdio --model claude-sonnet-4-20250514 --docker
```

**SSE (HTTP)** — for remote or networked clients:

```bash
pentestagent mcp_server --type sse
pentestagent mcp_server --type sse --host 0.0.0.0 --port 8080
pentestagent mcp_server --type sse --target 10.0.0.1 --scope 10.0.0.0/24 --docker
```

The SSE transport exposes a single `/mcp` endpoint supporting `POST` (requests), `GET` (persistent SSE stream for server-initiated push), and `DELETE` (session teardown). Sessions are tracked via the `Mcp-Session-Id` header.

**All `mcp_server` flags:**

| Flag | Default | Description |
|------|---------|-------------|
| `--type` | *(required)* | Transport: `stdio` or `sse` |
| `--host` | `0.0.0.0` | SSE bind host |
| `--port` | `8080` | SSE bind port |
| `--target` | none | Primary pentest target (IP / hostname) |
| `--scope` | `[]` | In-scope targets/CIDRs (space-separated) |
| `--model` | env var | Model identifier, overrides `PENTESTAGENT_MODEL` |
| `--docker` | false | Use DockerRuntime instead of LocalRuntime |
| `--no-rag` | false | Skip RAG engine initialisation |
| `--no-mcp` | false | Skip external MCP server connections |

##### Example: Claude Desktop config (`claude_desktop_config.json`)

```json
{
  "mcpServers": {
    "pentestagent": {
      "command": "pentestagent",
      "args": ["mcp_server", "--type", "stdio"]
    }
  }
}
```

---

#### MCP Server Tools Reference

When acting as an MCP server, PentestAgent exposes the following tools:

**Server Status & Config**

| Tool | Description |
|------|-------------|
| `get_server_status` | Live server status: readiness, task counts by state, primary target/scope, memory store size |
| `get_config` | Primary agent configuration: target, scope, max iterations, tool list |
| `update_config` | Update target, scope, or max iterations for all subsequent tasks |

**Task Execution**

| Tool | Description |
|------|-------------|
| `run_task` | Submit a task and **block** until it completes. Returns full result, tools used, and notes snapshot |
| `run_task_async` | Submit a task and **return immediately** with a `task_id`. Poll with `get_task_status` |

**Task Inspection**

| Tool | Description |
|------|-------------|
| `list_tasks` | List all tasks with status, target, and summary. Filterable by status |
| `get_task_status` | Poll the current status and result preview of a task |
| `get_task_result` | Full task result: final output, thinking steps, all tool calls and results, notes snapshot |
| `await_tasks` | Block until a set of async task IDs have all finished (polls every 500 ms, configurable timeout) |

**Task Control**

| Tool | Description |
|------|-------------|
| `cancel_task` | Cancel a running or pending task by ID |

**Tool Management**

| Tool | Description |
|------|-------------|
| `list_tools` | List all tools available to the agent |
| `enable_tool` | Enable a named tool on the primary agent |
| `disable_tool` | Disable a named tool on the primary agent |

**Conversation History**

| Tool | Description |
|------|-------------|
| `get_conversation_history` | Return message history for a task or the primary agent. Supports a `limit` parameter |
| `reset_conversation` | Clear conversation history for a task or the primary agent |

**Memory**

| Tool | Description |
|------|-------------|
| `store_memory` | Persist a key-value pair to the in-process memory store |
| `retrieve_memory` | Retrieve by exact key, search by substring, or list all keys |
| `clear_memory` | Delete a specific key or wipe all memory with `scope='all'` |

**Observability**

| Tool | Description |
|------|-------------|
| `get_logs` | Return recent execution logs, optionally filtered by level (`info` / `warning` / `error`) |
| `get_metrics` | Runtime metrics: task counts, success rate, total tool calls, memory and log sizes |

---

#### Async Task Workflow Example

For long-running recon tasks, use the async pattern:

```
# 1. Submit tasks without blocking
run_task_async  task="Enumerate subdomains of example.com"  target="example.com"
run_task_async  task="Run nmap SYN scan on example.com"     target="example.com"

# 2. Block until both finish (up to 5 minutes)
await_tasks  task_ids=["<id1>", "<id2>"]  timeout_seconds=300

# 3. Retrieve full results
get_task_result  task_id="<id1>"
get_task_result  task_id="<id2>"
```

---

### CLI Tool Management

```bash
pentestagent tools list         # List all tools
pentestagent tools info <name>  # Show tool details
pentestagent mcp list           # List MCP servers
pentestagent mcp add <name> <command> [args...]  # Add MCP server
pentestagent mcp test <name>    # Test MCP connection
```

## Knowledge

- **RAG:** Place methodologies, CVEs, or wordlists in `pentestagent/knowledge/sources/` for automatic context injection.
- **Notes:** Agents save findings to `loot/notes.json` with categories (`credential`, `vulnerability`, `finding`, `artifact`). Notes persist across sessions and are injected into agent context.
- **Shadow Graph:** In Crew mode, the orchestrator builds a knowledge graph from notes to derive strategic insights (e.g., "We have credentials for host X").

## Project Structure

```
pentestagent/
  agents/         # Agent implementations
  config/         # Settings and constants
  interface/      # TUI and CLI
  knowledge/      # RAG system and shadow graph
  llm/            # LiteLLM wrapper
  mcp/            # MCP client and server configs
  playbooks/      # Attack playbooks
  runtime/        # Execution environment
  tools/          # Built-in tools
```

## Development

```bash
pip install -e ".[dev]"
pytest                       # Run tests
pytest --cov=pentestagent    # With coverage
black pentestagent           # Format
ruff check pentestagent      # Lint
```

## Legal

Only use against systems you have explicit authorization to test. Unauthorized access is illegal.

## License

MIT