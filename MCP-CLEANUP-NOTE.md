This branch `mcp-cleanup` contains a focused cleanup that disables automatic
installation and auto-start of vendored MCP adapters (HexStrike, MetasploitMCP,
etc.). Operators should manually run installer scripts under `third_party/` and
configure `mcp_servers.json` when they want to enable MCP-backed tools.

Files changed (summary):
- `pentestagent/mcp/manager.py` — removed LAUNCH_* auto-start overrides and vendored auto-start logic.
- `pentestagent/interface/tui.py` and `pentestagent/interface/cli.py` — disabled automatic MCP auto-connect.
- `scripts/setup.sh` and `scripts/setup.ps1` — removed automatic vendored MCP install/start steps and added manual instructions.
- `README.md` — documented the manual MCP install workflow.

This commit is intentionally small and only intended to make the branch visible
for review. The functional changes are in the files listed above.

If you want a different summary or formatting, tell me and I'll update it.
