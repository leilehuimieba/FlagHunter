# MCP: Add Metasploit integration, HexStrike parity, auto-start flags and SSETransport improvements

## Summary
This PR adds a vendored Metasploit MCP integration and brings it to parity with the existing HexStrike MCP integration. It also improves the MCP transport layer (SSE) to reliably handle HTTP/SSE MCP servers that return 202/async responses.

## Key changes
- Add Metasploit MCP support via a `MetasploitAdapter` that can start/stop the vendored `MetasploitMCP` server and optionally start `msfrpcd` for local testing.
- Make MCP tool registration automatic: MCP tools are discovered and registered at startup so they appear in the TUI `/tools` view.
- Add environment flags to control vendored servers and subtree updates:
  - `LAUNCH_HEXTRIKE` / `LAUNCH_HEXSTRIKE` — control HexStrike vendored server auto-start behavior
  - `LAUNCH_METASPLOIT_MCP` — control Metasploit vendored server auto-start behavior
  - `FORCE_SUBTREE_PULL` — helper for scripts that add/update vendored `third_party` subtrees
- Improve HTTP/SSE transport (`SSETransport`) to:
  - Discover the server's POST endpoint announced over `/sse`
  - Maintain a persistent SSE listener instead of transient GETs
  - Correlate pending requests with SSE-delivered responses (supporting 202 Accepted flows)
  - Wait for endpoint discovery on connect to avoid writer races
- Add/update helper scripts (`scripts/add_metasploit_subtree.sh`, `scripts/setup.sh`) to vendor/update the Metasploit subtree and provide optional msfrpcd auto-start during setup.

## Files touched (high level)
- `pentestagent/mcp/metasploit_adapter.py` — new adapter to manage vendored Metasploit MCP and optional msfrpcd.
- `pentestagent/mcp/transport.py` — SSETransport enhancements and robustness fixes.
- `pentestagent/mcp/manager.py` — LAUNCH env handling, auto-start wiring and connection logic (fixes applied so LAUNCH_* works as expected).
- `pentestagent/mcp/mcp_servers.json` — added/updated `metasploit-local` entry in HexStrike-style (`--server http://...`).
- `.env.example` — grouped MCP settings; documents `FORCE_SUBTREE_PULL` and LAUNCH flags.
- `scripts/add_metasploit_subtree.sh`, `scripts/setup.sh` — vendoring helpers and optional msfrpcd startup.

(See the full commit set on this branch for exact diffs and additional smaller edits.)

## Behavior / Usage
- Default: vendored MCP entries are present in `pentestagent/mcp/mcp_servers.json` but not started unless configured.
- To allow PentestAgent to auto-start vendored MCPs at runtime, set the corresponding `LAUNCH_*` environment variable to a truthy value (e.g. `true`, `1`, `yes`):

```bash
export LAUNCH_METASPLOIT_MCP=true
export LAUNCH_HEXTRIKE=true
pentestagent
```

When `LAUNCH_METASPLOIT_MCP` is truthy and the manager is started, the manager will attempt to auto-start the vendored Metasploit adapter and connect to it so its tools are registered automatically.

If you prefer to run the vendored MCP server manually (recommended for debugging), start it separately and then run PentestAgent/TUI. Example:

```bash
python third_party/MetasploitMCP/MetasploitMCP.py --server http://127.0.0.1:7777 \
  > loot/artifacts/metasploit_mcp.log 2>&1 & disown
pentestagent mcp test metasploit-local
```

## How to test
1. Pull this branch and install dependencies (see `scripts/setup.sh`).
2. Manual test:
   - Start msfrpcd (or configure `MSF_*` envs to point to an existing Metasploit RPC)
   - Start the vendored MCP server:

     ```bash
     python third_party/MetasploitMCP/MetasploitMCP.py --server http://127.0.0.1:7777
     ```

   - Run the manager test:

     ```bash
     pentestagent mcp test metasploit-local
     ```

   - Expected: `+ Connected successfully!` and a list of available Metasploit tools.

3. Auto-start test:
   - Export `LAUNCH_METASPLOIT_MCP=true` and run `pentestagent` (or the TUI). The manager should auto-start the adapter and register tools so they appear in `/tools`.

## Security / Notes
- Do not commit real passwords or API keys. Use a local `.env` (never committed) to provide secrets like `MSF_PASSWORD`.
- The setup helper that may start `msfrpcd` will never invoke `sudo` — it only starts a local msfrpcd process if credentials are present and auto-start is enabled.

## Follow-ups / Optional improvements
- Add `scripts/start_metasploit.sh` to start the vendored MCP detached and capture logs (I can add this in a follow-up PR if desired).
- Add a short README section documenting the MCP vendoring workflow and recommended `.env` values for local testing.

---

If you'd like any edits to wording or additional testing instructions, tell me what to change and I will update the PR body.
