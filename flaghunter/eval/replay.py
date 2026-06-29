"""Deterministic replay harness for solved CTF challenges.

A ``ReplayFixture`` captures everything needed to re-drive a solve without a live
target or LLM: the recon browser responses, a list of scripted proxy rules, and
the expected flag. ``run_replay`` builds a real ``CTFTaskDispatcher`` over a
``ReplayRuntime`` that serves those scripted responses, runs the dispatch loop,
and reports whether the recorded flag is reproduced.

This is intentionally minimal (the skeleton): fixtures are hand-authored JSON.
A future ``record.py`` can capture fixtures automatically from a real run.
"""

from __future__ import annotations

import copy
import json
import tempfile
from dataclasses import dataclass
from pathlib import Path
from types import SimpleNamespace
from typing import Any

_FIXTURES_DIR = Path(__file__).parent / "fixtures"


@dataclass
class ReplayFixture:
    name: str
    target: str
    goal: str
    type: str
    hint: str
    expected_flag: str
    browser: dict[str, Any]
    proxy_rules: list[dict[str, Any]]
    default_proxy: dict[str, Any]
    # Optional project-type profile (ctf / pentest / code_audit). None → the
    # dispatcher default (CTF, byte-identical to every existing fixture). Lets a
    # fixture be re-driven under a different profile (e.g. conservative pentest)
    # to prove the profile覆盖 does not break a recorded solve.
    profile: str | None = None

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "ReplayFixture":
        return cls(
            name=data["name"],
            target=data["target"],
            goal=data.get("goal", "拿到flag"),
            type=data.get("type", "web"),
            hint=data.get("hint", ""),
            expected_flag=data["expected_flag"],
            browser=data.get("browser", {}),
            proxy_rules=data.get("proxy_rules", []),
            default_proxy=data.get("default_proxy", {"status_code": 404, "body": "not found"}),
            profile=data.get("profile"),
        )


def load_fixture(name: str) -> ReplayFixture:
    path = _FIXTURES_DIR / f"{name}.json"
    return ReplayFixture.from_dict(json.loads(path.read_text(encoding="utf-8")))


def list_fixtures() -> list[str]:
    if not _FIXTURES_DIR.exists():
        return []
    return sorted(p.stem for p in _FIXTURES_DIR.glob("*.json"))


class ReplayRuntime:
    """Deterministic runtime: serves scripted browser + proxy responses."""

    def __init__(self, fixture: ReplayFixture):
        self._fixture = fixture
        self.environment = SimpleNamespace(available_tools=[])
        self.requests: list[tuple[str, str]] = []

    async def browser_action(self, action: str, **kwargs) -> dict:
        # Advertise a usable browser so recon takes the browser path (navigate/
        # get_content) instead of falling back to the proxy 404 body as page
        # content. Hits the dispatcher recon happy-path (ctf_dispatcher.py:1654);
        # avoids relying on the legacy-probe error-string heuristic.
        if action == "diagnose":
            return {
                "available": True,
                "rendered_dom": False,
                "supports_actions": ["navigate", "get_content", "get_forms", "get_cookies"],
            }
        # Deep-copy so a recon consumer that mutates the result can't deplete the
        # fixture's shared dict across repeated calls.
        scripted = self._fixture.browser.get(action)
        if scripted is None:
            return {"error": f"no scripted browser action: {action}"}
        return copy.deepcopy(scripted)

    async def proxy_action(self, action: str, **kwargs) -> dict:
        url = str(kwargs.get("url") or "")
        self.requests.append((action, url))

        json_body = kwargs.get("json")
        data = kwargs.get("data")
        body_blob = ""
        if json_body is not None:
            body_blob += json.dumps(json_body)
        if isinstance(data, dict):
            body_blob += " " + json.dumps(data)
        elif data:
            body_blob += " " + str(data)

        operator_injection = False
        if isinstance(json_body, dict):
            operator_injection = any(isinstance(value, dict) for value in json_body.values())
        if isinstance(data, dict):
            operator_injection = operator_injection or any("[$" in str(key) for key in data)

        for rule in self._fixture.proxy_rules:
            when = rule.get("when", {})
            if "url_contains" in when and when["url_contains"] not in url:
                continue
            if "body_contains" in when and when["body_contains"] not in body_blob:
                continue
            if when.get("requires_operator_injection") and not operator_injection:
                continue
            return copy.deepcopy(rule.get("response", {}))
        return copy.deepcopy(self._fixture.default_proxy)

    async def execute_command(self, command: str, timeout: int = 180):
        return SimpleNamespace(exit_code=0, stdout="", stderr="")


@dataclass
class ReplayResult:
    name: str
    expected_flag: str
    actual_flag: str | None
    success: bool
    reproduced: bool


async def run_replay(
    fixture: ReplayFixture, *, profile: str | None = None
) -> ReplayResult:
    """Re-drive a fixture deterministically and report flag reproduction.

    Neutralizes tool gating and isolates the notes store for the duration so the
    replay is side-effect-free. Restores both in a finally block.

    ``profile`` overrides ``fixture.profile`` (which itself defaults to None →
    the dispatcher's byte-identical CTF default). Pass e.g. ``"pentest"`` to
    re-drive a recorded solve under the conservative profile and prove the
    profile覆盖 does not break it.
    """
    # Local imports avoid an import cycle at package load time.
    from ..agents.pa_agent import ctf_dispatcher as _disp_mod
    from ..agents.pa_agent.ctf_dispatcher import CTFTaskDispatcher
    from ..tools import notes as notes_module

    original_require = _disp_mod.ToolGuard.require
    prev_custom = getattr(notes_module, "_custom_notes_file", None)
    prev_loaded = getattr(notes_module, "_loaded_notes_file", None)

    _disp_mod.ToolGuard.require = lambda self, tools: {}  # type: ignore[assignment]
    try:
        with tempfile.TemporaryDirectory() as tmp:
            notes_module.set_notes_file(Path(tmp) / "notes.json")
            notes_module._notes.clear()
            runtime = ReplayRuntime(fixture)
            effective_profile = profile if profile is not None else fixture.profile
            dispatcher = CTFTaskDispatcher(
                runtime=runtime,
                progress_callback=None,
                verification_callback=lambda flag: "yes",
                profile=effective_profile,
            )
            result = await dispatcher.run(
                target=fixture.target,
                goal=fixture.goal,
                type=fixture.type,
                hint=fixture.hint,
                ledger_root=Path(tmp) / "session_ledgers",
                registry_root=Path(tmp) / "artifact_registry",
                checkpoint_root=Path(tmp) / "checkpoints",
            )
            actual = result.flag
            return ReplayResult(
                name=fixture.name,
                expected_flag=fixture.expected_flag,
                actual_flag=actual,
                success=bool(result.success),
                reproduced=(actual == fixture.expected_flag),
            )
    finally:
        _disp_mod.ToolGuard.require = original_require  # type: ignore[assignment]
        notes_module._notes.clear()
        notes_module._custom_notes_file = prev_custom
        notes_module._loaded_notes_file = prev_loaded
