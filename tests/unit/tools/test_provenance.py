"""Tests for flaghunter.tools.provenance (P3 tool-call provenance store).

Covers: field capture, secret redaction, sequence ordering, per-tool/per-run
queries, oversized-value truncation, corrupt-line tolerance, and — at the
ToolExecutor seam — that every execution path records provenance and that a
recording failure never breaks tool execution (fail-safe discipline).

All state is isolated to a temp JSONL file per test (autouse fixture) so the
suite stays hermetic and the real loot/ directory is untouched.
"""

import asyncio
import json

import pytest

from flaghunter.tools import provenance
from flaghunter.tools.executor import ToolExecutor
from flaghunter.tools.registry import Tool, ToolSchema


@pytest.fixture(autouse=True)
def _isolate_provenance(tmp_path):
    orig_store = provenance._store
    orig_seq = provenance._seq
    provenance.set_provenance_file(tmp_path / "provenance.jsonl")
    yield
    provenance._store = orig_store
    provenance._seq = orig_seq


def _make_tool(name="t", success=True, category="general", required=None) -> Tool:
    async def fn(arguments: dict, runtime) -> str:
        if not success:
            raise RuntimeError("simulated failure")
        return f"result:{arguments}"

    schema = ToolSchema(properties={"cmd": {"type": "string"}}, required=required or [])
    return Tool(name=name, description="", schema=schema, execute_fn=fn, category=category)


# ---------------------------------------------------------------------------
# Recording + queries (data layer)
# ---------------------------------------------------------------------------

class TestRecordAndQuery:
    def test_record_captures_core_fields(self):
        provenance.record_call_sync(
            tool_name="dirscan",
            run_id="r1",
            category="recon",
            arguments={"url": "http://t/"},
            target="http://t/",
            status="success",
            error_class="none",
            success=True,
            duration_ms=12.3,
        )
        calls = provenance.get_all_calls()
        assert len(calls) == 1
        c = calls[0]
        assert c["tool"] == "dirscan"
        assert c["run_id"] == "r1"
        assert c["category"] == "recon"
        assert c["seq"] == 1
        assert c["success"] is True
        assert c["duration_ms"] == 12.3
        assert c["args"] == {"url": "http://t/"}
        assert "ts" in c

    def test_seq_increments_across_calls(self):
        for _ in range(3):
            provenance.record_call_sync(tool_name="t")
        assert [c["seq"] for c in provenance.get_all_calls()] == [1, 2, 3]

    def test_get_tool_stats_aggregates(self):
        provenance.record_call_sync(tool_name="nmap", run_id="r1", success=True)
        provenance.record_call_sync(tool_name="nmap", run_id="r1", success=False)
        provenance.record_call_sync(
            tool_name="nmap", run_id="r2", success=True, found_flag=True
        )
        s = provenance.get_tool_stats("nmap")
        assert s["count"] == 3
        assert s["success"] == 2
        assert s["failed"] == 1
        assert s["run_count"] == 2
        assert s["found_flag_count"] == 1

    def test_get_run_calls_ordered_by_seq(self):
        provenance.record_call_sync(tool_name="a", run_id="rX")
        provenance.record_call_sync(tool_name="b", run_id="other")
        provenance.record_call_sync(tool_name="c", run_id="rX")
        calls = provenance.get_run_calls("rX")
        assert [c["tool"] for c in calls] == ["a", "c"]
        assert calls[0]["seq"] < calls[1]["seq"]

    def test_summary(self):
        provenance.record_call_sync(tool_name="a", run_id="r1")
        provenance.record_call_sync(tool_name="a", run_id="r1")
        provenance.record_call_sync(tool_name="b", run_id="r2", found_flag=True)
        s = provenance.summary()
        assert s["total"] == 3
        assert s["tools"] == {"a": 2, "b": 1}
        assert s["run_count"] == 2
        assert s["flags_found"] == 1

    def test_recent(self):
        for i in range(5):
            provenance.record_call_sync(tool_name=f"t{i}")
        last2 = provenance.recent(2)
        assert [c["tool"] for c in last2] == ["t3", "t4"]


# ---------------------------------------------------------------------------
# Redaction + bounding (security / robustness)
# ---------------------------------------------------------------------------

class TestRedactionAndBounding:
    def test_sensitive_args_redacted(self):
        provenance.record_call_sync(
            tool_name="remote_service_login",
            arguments={
                "username": "root",
                "password": "hunter2",
                "candidate_passwords": ["a", "b"],
                "headers": {"Cookie": "sid=topsecretvalue", "X-Foo": "ok"},
            },
        )
        c = provenance.get_all_calls()[-1]
        args = c["args"]
        assert args["username"] == "root"          # non-sensitive kept
        assert args["password"] == "***"           # redacted
        assert args["candidate_passwords"] == "***"  # whole list redacted
        assert args["headers"]["Cookie"] == "***"  # nested redacted
        assert args["headers"]["X-Foo"] == "ok"    # nested non-sensitive kept
        # the raw secrets must not survive anywhere in the persisted record
        blob = json.dumps(c)
        assert "hunter2" not in blob
        assert "topsecretvalue" not in blob

    def test_long_string_truncated(self):
        provenance.record_call_sync(tool_name="t", arguments={"data": "x" * 5000})
        c = provenance.get_all_calls()[-1]
        assert c["args"]["data"].endswith("...(truncated)")
        assert len(c["args"]["data"]) < 5000

    def test_corrupt_line_tolerated(self):
        provenance.record_call_sync(tool_name="ok")
        store = provenance._get_store()
        with store._path.open("a", encoding="utf-8") as fh:
            fh.write("{not valid json\n")
        calls = provenance.get_all_calls()
        assert len(calls) == 1
        assert calls[0]["tool"] == "ok"

    def test_trim_caps_record_count(self, tmp_path):
        # Small cap + interval to exercise trimming deterministically.
        provenance.set_provenance_store(
            provenance.JsonlProvenanceStore(
                tmp_path / "p.jsonl", max_records=10, trim_interval=5
            )
        )
        for _ in range(40):
            provenance.record_call_sync(tool_name="spam")
        # After trimming, the file holds at most max_records entries.
        assert len(provenance.get_all_calls()) <= 10


# ---------------------------------------------------------------------------
# Executor seam — provenance is recorded on every path; failure is safe
# ---------------------------------------------------------------------------

class TestExecutorIntegration:
    @pytest.mark.asyncio
    async def test_success_call_recorded_with_run_id(self):
        ex = ToolExecutor(runtime=None, timeout=5)
        tool = _make_tool("myscan", category="recon")
        await ex.execute(tool, {"url": "http://t/", "password": "p"})
        calls = provenance.get_all_calls()
        assert len(calls) == 1
        c = calls[0]
        assert c["tool"] == "myscan"
        assert c["run_id"] == ex.run_id
        assert c["category"] == "recon"
        assert c["target"] == "http://t/"
        assert c["args"]["password"] == "***"
        assert c["success"] is True

    @pytest.mark.asyncio
    async def test_failed_call_recorded(self):
        ex = ToolExecutor(runtime=None, timeout=5)
        await ex.execute(_make_tool("boom", success=False), {"cmd": "x"})
        c = provenance.get_all_calls()[-1]
        assert c["success"] is False
        assert c["status"] == "error"

    @pytest.mark.asyncio
    async def test_validation_failure_recorded(self):
        ex = ToolExecutor(runtime=None, timeout=5)
        tool = _make_tool("needs_cmd", required=["cmd"])
        await ex.execute(tool, {})  # missing required → validation fail path
        calls = provenance.get_all_calls()
        assert len(calls) == 1
        assert calls[0]["success"] is False

    @pytest.mark.asyncio
    async def test_cache_hit_recorded_with_flag(self):
        ex = ToolExecutor(runtime=None, timeout=5)
        tool = _make_tool("cacheme")
        await ex.execute(tool, {"cmd": "same"})
        await ex.execute(tool, {"cmd": "same"})  # served from cache
        calls = provenance.get_all_calls()
        assert len(calls) == 2
        assert calls[0]["cache_hit"] is False
        assert calls[1]["cache_hit"] is True

    @pytest.mark.asyncio
    async def test_same_executor_shares_run_id(self):
        ex = ToolExecutor(runtime=None, timeout=5)
        await ex.execute(_make_tool("a"), {"cmd": "1"})
        await ex.execute(_make_tool("b"), {"cmd": "2"})
        assert len(provenance.get_run_calls(ex.run_id)) == 2

    @pytest.mark.asyncio
    async def test_recording_failure_does_not_break_execution(self, monkeypatch):
        def _boom(**kwargs):
            raise RuntimeError("disk full")

        monkeypatch.setattr(provenance, "record_call_sync", _boom)
        ex = ToolExecutor(runtime=None, timeout=5)
        result = await ex.execute(_make_tool("t"), {"cmd": "x"})
        assert result.success is True
        assert len(ex.execution_history) == 1  # history still tracked
