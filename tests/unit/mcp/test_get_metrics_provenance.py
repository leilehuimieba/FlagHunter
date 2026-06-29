"""P6 — MCP ``get_metrics`` surfaces mined emergent chains from provenance.

The metrics tool appends a read-only provenance/emergent-chain summary. Wiring
is verified end-to-end against a temp provenance log; the append must be
fail-safe (an empty/corrupt log can never break the metrics call).
"""

from __future__ import annotations

import pytest

from flaghunter.mcp.server.mcp_tools import get_metrics
from flaghunter.tools import provenance


@pytest.mark.asyncio
async def test_get_metrics_appends_provenance_summary(tmp_path):
    provenance.set_provenance_file(tmp_path / "provenance.jsonl")
    try:
        provenance.record_call_sync(tool_name="a", run_id="r1")
        provenance.record_call_sync(tool_name="b", run_id="r1")
        provenance.record_call_sync(tool_name="a", run_id="r2")
        provenance.record_call_sync(tool_name="b", run_id="r2", found_flag=True)

        out = await get_metrics({})
        # base metrics still present
        assert "total_tasks:" in out
        # P6 provenance section appended
        assert "provenance_calls: 4" in out
        assert "provenance_runs:  2" in out
        assert "flag_runs:        1" in out
        # the recurring a→b chain surfaces
        assert "chain:" in out and "a -> b" in out
    finally:
        provenance.clear()


@pytest.mark.asyncio
async def test_get_metrics_fail_safe_on_empty_log(tmp_path):
    provenance.set_provenance_file(tmp_path / "empty.jsonl")
    try:
        out = await get_metrics({})
        # never raises; base metrics still returned; no chain lines for empty log
        assert "total_tasks:" in out
        assert "provenance_calls: 0" in out
        assert "chain:" not in out
    finally:
        provenance.clear()
