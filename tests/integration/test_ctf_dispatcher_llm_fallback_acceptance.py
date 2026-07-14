"""Acceptance coverage for Phase 5.7 LLM-driven fallback on unknown web surfaces."""

from __future__ import annotations

import json
import threading
import urllib.request
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from types import SimpleNamespace
from urllib.parse import urlparse

import pytest

import flaghunter.tools.notes as notes_module
from flaghunter.agents.pa_agent.chains.base import _ChainOutcome
from flaghunter.agents.pa_agent.ctf_dispatcher import CTFTaskDispatcher
from flaghunter.runtime.runtime import LocalRuntime
from flaghunter.tools.notes import set_notes_file


FLAG_VALUE = "flag{llm_unknown_web_acceptance_ok}"


class _FakeLLM:
    def __init__(self, replies: list[dict]):
        self._replies = list(replies)
        self.calls: list[str] = []

    async def generate(self, prompt: str) -> str:
        self.calls.append(prompt)
        if not self._replies:
            return "{}"
        return json.dumps(self._replies.pop(0), ensure_ascii=False)


@pytest.fixture
def isolated_notes(tmp_path: Path):
    notes_file = tmp_path / "notes.json"
    set_notes_file(notes_file)
    notes_module._notes.clear()
    notes_module._loaded_notes_file = None
    yield notes_file
    notes_module._notes.clear()
    notes_module._custom_notes_file = None
    notes_module._loaded_notes_file = None


@pytest.fixture
def unknown_web_server():
    recorded: list[dict] = []

    class _Handler(BaseHTTPRequestHandler):
        def log_message(self, format, *args):  # noqa: A003
            pass

        def do_GET(self):  # noqa: N802
            parsed = urlparse(self.path)
            recorded.append(
                {
                    "method": "GET",
                    "path": parsed.path,
                    "query": parsed.query,
                    "headers": dict(self.headers),
                }
            )

            if parsed.path == "/":
                self.send_response(200)
                self.send_header("Content-Type", "text/html; charset=utf-8")
                self.end_headers()
                self.wfile.write(
                    b"""
                    <html><body>
                      <h1>mystery portal</h1>
                      <p>no forms, no upload, no obvious backup, no standard challenge shape</p>
                      <a href="/about">about</a>
                    </body></html>
                    """
                )
                return

            if parsed.path == "/about":
                self.send_response(200)
                self.send_header("Content-Type", "text/plain; charset=utf-8")
                self.end_headers()
                self.wfile.write(b"just a boring page")
                return

            if parsed.path == "/admin/secret.txt":
                self.send_response(200)
                self.send_header("Content-Type", "text/plain; charset=utf-8")
                self.end_headers()
                self.wfile.write(FLAG_VALUE.encode("utf-8"))
                return

            self.send_response(404)
            self.end_headers()
            self.wfile.write(b"not found")

    server = ThreadingHTTPServer(("127.0.0.1", 0), _Handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()

    base_url = f"http://127.0.0.1:{server.server_port}"
    for _ in range(20):
        try:
            with urllib.request.urlopen(base_url, timeout=2):
                break
        except Exception:
            continue

    yield {"base_url": base_url, "requests": recorded}

    server.shutdown()
    thread.join(timeout=5)
    server.server_close()


def _playwright_missing_error() -> dict[str, str]:
    return {
        "error": "Playwright not installed. Install with:\n  pip install playwright\n  playwright install chromium"
    }


@pytest.mark.asyncio
async def test_ctf_dispatcher_acceptance_unknown_web_uses_llm_fallback(
    tmp_path: Path, monkeypatch, isolated_notes, unknown_web_server
):
    # This is a characterization test of the chain-order harness's LLM-exploration
    # fallback (Phase 5.7). The 5b cutover flipped FLAGHUNTER_BLACKBOARD_LOOP default
    # ON (30a55ac), routing the with-LLM path through the blackboard loop, whose
    # proposal schema (Intent/Hint) and state fields differ from the artifacts this
    # test asserts (llm_exploration_steps / pre_action_reasonings / http_request
    # exploration replies). The chain-order path is the permanent no-LLM substrate
    # (7f134e0) and stays exercisable behind the escape hatch — so pin this legacy
    # path characterization to =false. (Coverage of unknown-web LLM fallback under
    # the DEFAULT blackboard loop is a separate follow-up, not covered here.)
    monkeypatch.setenv("FLAGHUNTER_BLACKBOARD_LOOP", "false")
    monkeypatch.chdir(tmp_path)

    runtime = LocalRuntime()
    await runtime.start()
    try:
        async def _browser_missing(action: str, **kwargs):
            return _playwright_missing_error()

        monkeypatch.setattr(runtime, "browser_action", _browser_missing)

        llm = _FakeLLM(
            [
                {
                    "action_type": "http_request",
                    "tool_name": "http_request",
                    "rationale": "known strategies found no anchor; probe secret-looking admin text file directly",
                    "payload": {"method": "GET", "url": f"{unknown_web_server['base_url']}/admin/secret.txt"},
                    "expected_signal": "200 且 body 含 flag",
                    "next_if_fail": "switch chain",
                }
            ]
        )

        dispatcher = CTFTaskDispatcher(
            runtime=runtime,
            llm=llm,
            progress_callback=None,
            verification_callback=lambda flag: "yes",
        )
        result = await dispatcher.run(
            target=unknown_web_server["base_url"],
            goal="拿到flag",
            type="auto",
            hint="",
        )

        assert result.success is True
        assert result.flag == FLAG_VALUE
        assert dispatcher.state is not None
        assert dispatcher.state.llm_exploration_steps >= 1
        assert any(item.value == FLAG_VALUE for item in dispatcher.state.verified_flags)
        assert any(
            isinstance(item, dict)
            and item.get("type") == "llm_pre_action_reasoning"
            and item.get("approve") is True
            for item in dispatcher.state.pre_action_reasonings
        )
        assert any(
            item.kind == "llm_exploration_step"
            and item.metadata.get("verifier_decision") == "verified"
            for item in dispatcher.state.observations
        )
        assert any(entry["path"] == "/admin/secret.txt" for entry in unknown_web_server["requests"])
        assert llm.calls, "LLM fallback should be invoked on unknown web surfaces"
    finally:
        await runtime.stop()


class _ChainDrivingLLM:
    """Conforms to the real ``LLM.generate`` signature (the blackboard brain calls
    ``generate(system, messages, max_tokens=…, task_hint=…)``) and scripts the brain to
    call a chain then stop. Records each rendered user prompt so the test can prove the
    model — not the deterministic harness — actually drove the fallback."""

    def __init__(self, replies: list[str]):
        self._replies = list(replies)
        self.calls: list[str] = []

    async def generate(self, system_prompt, messages, *, tools=None, max_tokens=None, task_hint="default"):
        self.calls.append(" ".join(str(m.get("content", "")) for m in (messages or [])))
        content = self._replies.pop(0) if self._replies else '{"kind":"stop","rationale":"exhausted"}'
        return SimpleNamespace(content=content, tool_calls=None, usage={"total_tokens": 1}, finish_reason="stop")


@pytest.mark.asyncio
async def test_ctf_dispatcher_acceptance_unknown_web_blackboard_llm_fallback(
    tmp_path: Path, monkeypatch, isolated_notes, unknown_web_server
):
    # Blackboard-loop equivalent of the chain-order acceptance test above, for the
    # DEFAULT driver. The 5b cutover (30a55ac) routes an unknown web surface with an LLM
    # present into the model-driven blackboard loop, NOT the chain-order fallback. Pins
    # that path end-to-end through the REAL dispatcher.run() / detect / finalize against
    # a real server + LocalRuntime — the coverage the unit-level
    # test_blackboard_loop_bypass.py cannot give (it drives _run_blackboard_loop directly
    # with a fake dispatcher and monkeypatched seams). The mechanism differs materially
    # from the chain-order path: the brain drives CHAINS-as-tools (not a raw http_request),
    # so the assertions below track the blackboard contract (goal_met reason + terminal
    # flag promotion), not the old path's llm_exploration_step / pre_action_reasoning
    # artifacts.
    #
    # The chain's INTERNAL exploitation is stubbed with a winning _ChainOutcome — not to
    # fake the solve but to stop the real "web" chain escalating to gobuster/ffuf brute
    # force (a minutes-long hang) on a surface it cannot crack. WHICH chain cracks the box
    # is not what this test pins; the routing + brain-drive + terminal-success contract is.
    monkeypatch.setenv("FLAGHUNTER_BLACKBOARD_LOOP", "true")
    monkeypatch.chdir(tmp_path)

    runtime = LocalRuntime()
    await runtime.start()
    try:
        async def _browser_missing(action: str, **kwargs):
            return _playwright_missing_error()

        monkeypatch.setattr(runtime, "browser_action", _browser_missing)

        llm = _ChainDrivingLLM(
            [
                json.dumps(
                    {
                        "kind": "call_tool",
                        "tool": "web",
                        "input": {},
                        "expected_signal": "flag{",
                        "rationale": "no anchor on this surface — sweep the generic web route",
                    }
                ),
                json.dumps({"kind": "stop", "rationale": "solved"}),
            ]
        )

        dispatcher = CTFTaskDispatcher(
            runtime=runtime,
            llm=llm,
            progress_callback=None,
            verification_callback=lambda flag: "yes",
        )

        # Stub only the chain's internal run: the "web" chain "reads" the secret file and
        # asserts the flag (as a real winning chain would via its terminal-success
        # contract), without live brute force. The bypass's on_outcome promotion turns the
        # asserted flag into a runtime flag so goal() reports solved (5b cut-1 wiring).
        async def _winning_chain(*, chain_name, target, page_features, hint):
            if chain_name == "web":
                return _ChainOutcome(progress=True, flag=FLAG_VALUE, reason="read /admin/secret.txt")
            return _ChainOutcome(progress=False, reason="no-op")

        monkeypatch.setattr(dispatcher, "_execute_chain", _winning_chain)

        result = await dispatcher.run(
            target=unknown_web_server["base_url"],
            goal="拿到flag",
            type="auto",
            hint="",
        )

        # Routed through the model-driven blackboard loop (not the chain-order harness):
        # the goal_met reason is the loop's own terminal mapping.
        assert result.reason == "blackboard_loop:goal_met"
        assert result.success is True
        assert result.flag == FLAG_VALUE
        # The brain — the model — genuinely drove the fallback: at least one generate call
        # carried the rendered board (render_user_prompt's closing marker), proving it was
        # the blackboard brain, not an incidental detect-phase call.
        assert any(
            "Respond with one JSON action object" in call for call in llm.calls
        ), "blackboard brain should be invoked on unknown web surfaces"
        # The brain's chain choice ran as a tool and its terminal flag was promoted to a
        # runtime flag that goal() could see.
        assert "web" in result.chain_used
        assert dispatcher.state is not None
        assert any(f.value == FLAG_VALUE for f in dispatcher.state.runtime_flags)
        # The real detect pipeline probed the live target before dispatching the solve.
        assert any(entry["path"] == "/" for entry in unknown_web_server["requests"])
    finally:
        await runtime.stop()
