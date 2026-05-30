from __future__ import annotations

import pytest

pytest.importorskip("textual")
from textual import events

from pentestagent.interface.tui import ChatInputTextArea, PentestAgentTUI


def test_chat_input_text_area_enter_posts_submitted_message(monkeypatch):
    widget = ChatInputTextArea("line1\nline2")
    posted = []

    monkeypatch.setattr(widget, "post_message", lambda message: posted.append(message))

    widget.action_submit_input()

    assert len(posted) == 1
    assert isinstance(posted[0], ChatInputTextArea.Submitted)
    assert posted[0].text == "line1\nline2"
    assert posted[0].control is widget


def test_chat_input_text_area_shift_enter_inserts_newline():
    widget = ChatInputTextArea("line1")
    widget.move_cursor((0, len("line1")))

    widget.action_insert_newline()

    assert widget.text == "line1\n"


@pytest.mark.asyncio
async def test_chat_input_text_area_enter_key_submits(monkeypatch):
    widget = ChatInputTextArea("hello")
    posted = []

    monkeypatch.setattr(widget, "post_message", lambda message: posted.append(message))

    await widget._on_key(events.Key("enter", None))

    assert len(posted) == 1
    assert isinstance(posted[0], ChatInputTextArea.Submitted)
    assert posted[0].text == "hello"


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        ("/help", True),
        ("   /agent scan target", True),
        ("/agent first line\nsecond line", False),
        ("plain text", False),
        ("", False),
    ],
)
def test_command_suggestions_only_for_single_line_slash_input(value, expected):
    assert PentestAgentTUI._should_offer_command_suggestions(value) is expected


def _make_tui_stub():
    tui = object.__new__(PentestAgentTUI)
    tui._last_ctf_state = {
        "candidate_flags": [
            {"value": "flag{candidate_only}"},
        ],
        "runtime_flags": [
            {"value": "flag{runtime_pending}"},
        ],
        "verified_flags": [],
        "rejected_flags": [
            {"value": "flag{rejected_old}"},
        ],
        "pre_action_reasonings": [
            {
                "id": "par_1",
                "experiment_id": "exp_1",
                "current_belief": "当前最强假设是 auth_form_sqli",
                "action_rationale": "优先执行链路 sqli，使用能力实现 manual_payload_via_requests（quality=medium）",
                "expected_success_signal": "看到登录成功提示",
                "expected_failure_signal": "看到错误提示",
            },
            {
                "id": "par_2",
                "experiment_id": "exp_2",
                "current_belief": "当前次强假设是 backup_source_leak",
                "action_rationale": "继续下载源码包验证 candidate flag 是否只是 source-only",
                "expected_success_signal": "发现压缩包或源码泄露",
                "expected_failure_signal": "无源码相关端点",
            }
        ],
        "stop_report": {
            "reason": "runtime_pending_verification",
            "strongest_remaining_hypothesis": "auth_form_sqli",
            "memory_explanations": [
                "当前题目原子事实：type:sqli, signal:login_form",
                "假设 `auth_form_sqli` 因原子事实支持获得记忆增强：signal:login_form",
            ],
            "memory_focus_entry_ids": ["mem_1"],
            "memory_quick_commands": [
                "/ctf memory panel filter=audit sort=correlation",
                "/ctf memory show mem_1",
                "/ctf memory mute mem_2",
            ],
            "user_next_steps": ["提交 runtime flag", "如错误则标 wrong"],
        },
        "surprises": [
            {
                "id": "surprise_1",
                "actual_result_summary": "发现未知 portal signature",
            },
            {
                "id": "surprise_2",
                "actual_result_summary": "回显结构与预期 SQLi 行为不一致",
            },
        ],
        "capabilities": {
            "primitives": {
                "sql_injection_test": {
                    "best_available": {
                        "method": "manual_payload_via_requests",
                        "quality": "medium",
                    }
                }
            }
        },
        "meta_reasonings": [
            {
                "type": "platform_profile_snapshot",
                "platform_type": "ctfd",
                "base_url": "https://ctf.example.com",
                "challenge_id": "42",
                "auto_submit": True,
            },
            {
                "type": "platform_sync_snapshot",
                "success": True,
                "challenge_count": 12,
                "scoreboard_keys": ["data"],
            },
            {
                "type": "platform_challenge_alignment",
                "matched": True,
                "match_reason": "challenge_id_exact",
                "challenge_id": "42",
                "challenge_name": "EasySQL",
                "already_solved": False,
                "confidence": 1.0,
            },
            {
                "type": "submit_gate_decision",
                "flag": "flag{runtime_pending}",
                "evidence_source": "http-response",
                "allow": True,
                "reason": "strong runtime evidence source",
            },
            {
                "type": "platform_task_queue_snapshot",
                "platform_type": "ctfd",
                "total": 3,
                "unsolved_count": 2,
                "solved_count": 1,
                "next_challenge_id": "42",
                "next_challenge_name": "EasySQL",
                "rate_limited_until": 0.0,
                "tasks": [
                    {
                        "challenge_id": "42",
                        "name": "EasySQL",
                        "solved": False,
                        "priority_score": 1100.0,
                        "priority_reason": "unsolved, points=100",
                    }
                ],
            },
            {
                "type": "platform_queue_switch_decision",
                "switch_reason": "next_unsolved_highest_priority",
                "switch_source": "platform_queue",
                "next_challenge_id": "42",
                "next_url": "https://ctf.example.com/challenges/42",
                "skipped_candidates": [{"challenge_id": "1", "skip_reason": "solved"}],
            },
            {
                "type": "platform_autonomy_run_summary",
                "config": {"mode": "switch"},
                "challenge_count": 2,
                "solved_count": 1,
                "blocked_count": 0,
                "skipped_count": 0,
                "switched_count": 1,
                "consecutive_stops": 0,
                "elapsed_seconds": 3.2,
                "end_reason": "continue",
                "resume_count": 1,
                "resumed_from_record_count": 1,
                "resume_reason": "operator_hint_restart",
                "last_switch_reason": "next_unsolved_highest_priority",
                "last_switch_source": "platform_queue",
            },
            {
                "type": "platform_run_stop_summary",
                "end_reason": "continue",
                "blocked_reasons": ["wrong_flag_feedback"],
                "skip_reasons": [],
                "resume_count": 1,
                "resume_reason": "operator_hint_restart",
                "last_record": {
                    "challenge_id": "42",
                    "outcome": "blocked",
                    "reason": "wrong_flag_feedback",
                },
            },
            {
                "type": "strategy_memory_audit",
                "current_atomic_facts": ["type:sqli", "signal:login_form", "auth:form_login"],
                "matched_entries": [
                    {
                        "id": "mem_1",
                        "similarity": 0.88,
                        "atomic_facts": ["type:sqli", "signal:login_form", "auth:form_login"],
                        "winning_hypothesis_kinds": ["auth_form_sqli"],
                        "failed_hypothesis_kinds": ["generic_web_recon"],
                    }
                ],
                "adjustments": {"auth_form_sqli": 0.15},
            },
            {
                "type": "hypothesis_memory_adjustment",
                "kind": "auth_form_sqli",
                "applied_adjustment": 0.15,
                "metadata": {
                    "reason": "atomic_fact_supported",
                    "matched_atomic_facts": ["signal:login_form", "auth:form_login"],
                    "required_atomic_facts": ["signal:login_form", "auth:form_login", "type:sqli"],
                    "matched_entry_ids": ["mem_1"],
                },
            },
            {
                "type": "strategy_memory_outcome_audit",
                "matched_entry_ids": ["mem_1"],
                "solved": True,
            },
        ],
        "retrospectives": [
            {
                "id": "retro_1",
                "failure_root_cause": "runtime flag but no verification",
            },
            {
                "id": "retro_2",
                "failure_root_cause": "source-only flag was treated as terminal too early",
            },
        ],
    }
    tui._last_ctf_context = {}
    tui.runtime = None
    tui.agent = None
    tui.target = "ctf"
    tui._is_running = False
    tui._should_stop = False
    tui._current_worker = None
    messages = []
    tui._add_system = lambda message: messages.append(message)
    tui._captured_messages = messages
    return tui


@pytest.mark.asyncio
async def test_ctf_reasoning_subcommand_works_without_cpa_module():
    tui = _make_tui_stub()

    await PentestAgentTUI._parse_ctf_command(tui, "/ctf reasoning")

    assert tui._captured_messages
    assert "[CTF reasoning]" in tui._captured_messages[-1]
    assert "latest_surprise" in tui._captured_messages[-1]
    assert "[CTF flags]" in tui._captured_messages[-1]
    assert "candidate: flag{candidate_only}" in tui._captured_messages[-1]
    assert "memory_focus_entry_ids" in tui._captured_messages[-1]
    assert "memory_quick_commands" in tui._captured_messages[-1]


def test_render_last_ctf_stop_report_shows_standard_flag_buckets():
    tui = _make_tui_stub()

    rendered = PentestAgentTUI._render_last_ctf_stop_report(tui)

    assert "[CTF StopReport]" in rendered
    assert "candidate_flags: flag{candidate_only}" in rendered
    assert "runtime_flags: flag{runtime_pending}" in rendered
    assert "rejected_flags: flag{rejected_old}" in rendered
    assert "memory_explanations:" in rendered
    assert "memory_focus_entry_ids:" in rendered
    assert "memory_quick_commands:" in rendered
    assert "user_next_steps:" in rendered


@pytest.mark.asyncio
async def test_ctf_capabilities_subcommand_renders_best_implementation():
    tui = _make_tui_stub()

    await PentestAgentTUI._parse_ctf_command(tui, "/ctf capabilities")

    assert "sql_injection_test" in tui._captured_messages[-1]
    assert "manual_payload_via_requests" in tui._captured_messages[-1]


@pytest.mark.asyncio
async def test_ctf_reasoning_subcommand_supports_limit_and_filters():
    tui = _make_tui_stub()

    await PentestAgentTUI._parse_ctf_command(tui, "/ctf reasoning -n 2")
    assert "[pre_action_reasoning 1/2]" in tui._captured_messages[-1]
    assert "backup_source_leak" in tui._captured_messages[-1]

    await PentestAgentTUI._parse_ctf_command(tui, "/ctf reasoning surprises")
    assert "[CTF reasoning surprises]" in tui._captured_messages[-1]
    assert "surprise_2" in tui._captured_messages[-1]

    await PentestAgentTUI._parse_ctf_command(tui, "/ctf reasoning postmortem")
    assert "[CTF reasoning postmortem]" in tui._captured_messages[-1]
    assert "retro_2" in tui._captured_messages[-1]


@pytest.mark.asyncio
async def test_ctf_status_subcommand_renders_platform_snapshot():
    tui = _make_tui_stub()

    await PentestAgentTUI._parse_ctf_command(tui, "/ctf status")

    assert "[CTF status]" in tui._captured_messages[-1]
    assert "platform_type: ctfd" in tui._captured_messages[-1]
    assert "challenge_id: 42" in tui._captured_messages[-1]
    assert "challenge_name: EasySQL" in tui._captured_messages[-1]
    assert "last_switch: reason=next_unsolved_highest_priority source=platform_queue" in tui._captured_messages[-1]
    assert "[queue switch]" in tui._captured_messages[-1]
    assert "[platform run stop]" in tui._captured_messages[-1]
    assert "resumed: count=1 from_records=1 reason=operator_hint_restart" in tui._captured_messages[-1]
    assert "last_record: 42 outcome=blocked reason=wrong_flag_feedback" in tui._captured_messages[-1]


@pytest.mark.asyncio
async def test_ctf_queue_subcommand_renders_platform_queue():
    tui = _make_tui_stub()

    await PentestAgentTUI._parse_ctf_command(tui, "/ctf queue")

    assert "[CTF queue]" in tui._captured_messages[-1]
    assert "next: 42 EasySQL" in tui._captured_messages[-1]


def test_ctf_auto_switch_policy_allows_success_and_exhausted_stop():
    tui = _make_tui_stub()

    allow_success = PentestAgentTUI._should_auto_switch_ctf_task(
        tui,
        state={"stop_report": {"reason": "flag_verified"}},
        result=type("Result", (), {"success": True, "reason": "ok"})(),
        auto_switch_depth=0,
    )
    allow_exhausted = PentestAgentTUI._should_auto_switch_ctf_task(
        tui,
        state={"stop_report": {"reason": "all_hypotheses_exhausted"}},
        result=type("Result", (), {"success": False, "reason": "未命中 flag"})(),
        auto_switch_depth=0,
    )
    deny_deep = PentestAgentTUI._should_auto_switch_ctf_task(
        tui,
        state={"stop_report": {"reason": "all_hypotheses_exhausted"}},
        result=type("Result", (), {"success": False, "reason": "未命中 flag"})(),
        auto_switch_depth=3,
    )

    assert allow_success is True
    assert allow_exhausted is True
    assert deny_deep is False


def test_ctf_resolve_next_queue_url_rewrites_query_challenge_id():
    tui = _make_tui_stub()

    next_url = PentestAgentTUI._resolve_next_ctf_queue_url(
        tui,
        current_url="https://ctf.example.com/challenges/view?cid=42",
        current_submit_profile={"base_url": "https://ctf.example.com"},
        current_challenge_id="42",
        next_task={"challenge_id": "99", "url": ""},
    )

    assert "cid=99" in next_url


def test_ctf_auto_switch_context_selects_next_unsolved_queue_task():
    tui = _make_tui_stub()
    tui._last_ctf_state["meta_reasonings"] = [
        {
            "type": "platform_profile_snapshot",
            "platform_type": "ctfd",
            "base_url": "https://ctf.example.com",
            "challenge_id": "42",
            "auto_submit": True,
        },
        {
            "type": "platform_task_queue_snapshot",
            "platform_type": "ctfd",
            "tasks": [
                {"challenge_id": "1", "name": "Solved", "solved": True, "url": "/challenges/1"},
                {"challenge_id": "42", "name": "Current", "solved": False, "url": "/challenges/42"},
                {"challenge_id": "98", "name": "Visited", "solved": False, "url": "/challenges/98"},
                {"challenge_id": "99", "name": "NextOne", "solved": False, "url": "/challenges/99"},
            ],
        },
    ]

    ctx = PentestAgentTUI._resolve_ctf_auto_switch_context(
        tui,
        result=type("Result", (), {"success": True, "reason": "flag verified"})(),
        current_url="https://ctf.example.com/challenges/42",
        current_goal="拿到flag",
        current_type="web",
        current_hint="",
        current_submit_profile={"base_url": "https://ctf.example.com", "challenge_id": "42"},
        auto_switch_depth=0,
        visited_keys={"98|/challenges/98"},
    )

    assert ctx is not None
    assert ctx["url"].endswith("/challenges/99")
    assert ctx["submit_profile"]["challenge_id"] == "99"
    assert ctx["switch_reason"] == "next_unsolved_highest_priority"
    assert ctx["switch_source"] == "platform_queue"
    assert len(ctx["skipped_candidates"]) == 3


def test_ctf_crew_stop_reason_prefers_wrong_flag_feedback_over_generic_completion():
    tui = _make_tui_stub()

    reason = PentestAgentTUI._derive_ctf_crew_stop_reason(
        tui,
        type(
            "CrewSummary",
            (),
            {
                "stop_reason": "workers_completed",
                "worker_results": {
                    "worker-1": {"reason": "wrong flag feedback: flag{bad}"},
                    "worker-2": {"reason": "all_hypotheses_exhausted"},
                },
            },
        )(),
    )

    assert reason == "wrong_flag_feedback"


def test_ctf_crew_stop_reason_maps_missing_tools_to_capability_ceiling():
    tui = _make_tui_stub()

    reason = PentestAgentTUI._derive_ctf_crew_stop_reason(
        tui,
        type(
            "CrewSummary",
            (),
            {
                "stop_reason": "workers_completed",
                "worker_results": {
                    "worker-1": {"reason": "侦察依赖缺失: browser", "missing_tools": ["browser"]},
                },
            },
        )(),
    )

    assert reason == "capability_ceiling"


@pytest.mark.asyncio
async def test_ctf_memory_subcommand_renders_audit_and_recent_entries(monkeypatch):
    tui = _make_tui_stub()

    class _FakeEntry:
        def __init__(self):
            self.id = "mem_1"
            self.winning_hypothesis_kinds = ["auth_form_sqli"]
            self.failed_hypothesis_kinds = ["generic_web_recon"]
            self.fingerprint = type("FP", (), {"detected_type": "sqli"})()
            self.metadata = type(
                "Meta",
                (),
                {"applied_count": 2, "success_correlation": 1.0},
            )()

    class _FakeStore:
        def __init__(self, *args, **kwargs):
            pass

        async def list_entries(self, limit: int = 3):
            return [_FakeEntry()]

    monkeypatch.setattr(
        "pentestagent.agents.pa_agent.strategy_memory.StrategyMemoryStore",
        _FakeStore,
    )

    await PentestAgentTUI._parse_ctf_command(tui, "/ctf memory")

    assert "[CTF strategy_memory]" in tui._captured_messages[-1]
    assert "adjustments" in tui._captured_messages[-1]
    assert "[recent entries]" in tui._captured_messages[-1]


@pytest.mark.asyncio
async def test_providers_command_alias_reuses_api_status(monkeypatch):
    tui = _make_tui_stub()

    class _FakeStatus:
        def __init__(self, state):
            self.state = state

        def state_emoji(self):
            return "🟢"

    class _FakeProvider:
        def __init__(self):
            self.id = "primary"
            self.model = "gpt-4o"

    class _FakeProviderManager:
        def list_providers(self):
            return [_FakeProvider()]

        def get_status(self, provider_id: str):
            return _FakeStatus(type("State", (), {"value": "healthy"})())

    class _FakeCostTracker:
        def get_provider_usage(self, provider_id: str):
            return {
                "requests": 3,
                "tokens": 42,
                "cost": 0.12,
                "avg_latency_ms": 123.0,
            }

    monkeypatch.setattr(
        "cpa_modules.m1_api_hub.get_provider_manager",
        lambda: _FakeProviderManager(),
    )
    monkeypatch.setattr(
        "cpa_modules.m1_api_hub.get_cost_tracker",
        lambda: _FakeCostTracker(),
    )

    await PentestAgentTUI._parse_api_command(tui, "/providers")

    assert "[CPA M1] Provider Status" in tui._captured_messages[-1]
    assert "primary" in tui._captured_messages[-1]


@pytest.mark.asyncio
async def test_handle_command_routes_providers_alias_to_api_parser():
    tui = _make_tui_stub()
    seen = []

    async def _fake_parse_api_command(cmd: str):
        seen.append(cmd)

    tui._parse_api_command = _fake_parse_api_command

    await PentestAgentTUI._handle_command(tui, "/providers")

    assert seen == ["/providers"]


@pytest.mark.asyncio
async def test_ctf_hint_subcommand_records_hint_and_restarts_dispatcher(monkeypatch):
    tui = _make_tui_stub()
    tui.runtime = object()
    tui._last_ctf_context = {
        "url": "http://ctf.local",
        "goal": "拿到flag",
        "type": "web",
        "hint": "先看登录口",
        "submit_profile": {"base_url": "https://ctf.example.com"},
        "runner_config": {"mode": "single"},
    }

    notes_calls = []

    async def _fake_notes(payload, runtime=None):
        notes_calls.append((payload, runtime))
        return {"ok": True}

    monkeypatch.setattr(
        "pentestagent.tools.notes.notes",
        _fake_notes,
    )

    captured = {}

    def _fake_run(url, goal, chtype, hint, submit_profile, runner_config):
        captured.update(
            {
                "url": url,
                "goal": goal,
                "type": chtype,
                "hint": hint,
                "submit_profile": submit_profile,
                "runner_config": runner_config,
            }
        )
        return "worker"

    tui._run_ctf_dispatcher_mode = _fake_run

    await PentestAgentTUI._parse_ctf_command(tui, '/ctf hint "试试 PHP 反序列化"')

    assert notes_calls
    assert captured["url"] == "http://ctf.local"
    assert "先看登录口" in captured["hint"]
    assert "试试 PHP 反序列化" in captured["hint"]
    assert tui._current_worker == "worker"
    assert any("已记录 hint" in message for message in tui._captured_messages)


@pytest.mark.asyncio
async def test_ctf_crew_command_uses_crew_execution_mode(monkeypatch):
    tui = _make_tui_stub()
    tui.runtime = object()
    tui._set_status = lambda *args, **kwargs: None
    tui._update_header = lambda *args, **kwargs: None
    tui._add_user = lambda *args, **kwargs: None
    tui._set_target = lambda *args, **kwargs: None
    tui._show_sidebar = lambda *args, **kwargs: None
    tui._hide_sidebar = lambda *args, **kwargs: None
    tui._auto_detect_ctf_src = lambda url: ""

    captured = {}

    def _fake_run(url, goal, chtype, hint, submit_profile, runner_config):
        captured.update(
            {
                "url": url,
                "goal": goal,
                "type": chtype,
                "hint": hint,
                "submit_profile": submit_profile,
                "runner_config": runner_config,
            }
        )
        return "crew-worker"

    tui._run_ctf_crew_dispatcher_mode = _fake_run

    await PentestAgentTUI._parse_ctf_command(
        tui,
        '/ctf crew http://ctf.local type=sqli goal="拿到flag"',
    )

    assert captured["url"] == "http://ctf.local"
    assert captured["type"] == "sqli"
    assert tui._last_ctf_context["execution_mode"] == "crew"
    assert tui._last_ctf_context["url"] == "http://ctf.local"
    assert tui._current_worker == "crew-worker"
    assert any("CTF Crew Mode" in message for message in tui._captured_messages)


@pytest.mark.asyncio
async def test_ctf_hint_subcommand_restarts_crew_when_last_mode_is_crew(monkeypatch):
    tui = _make_tui_stub()
    tui.runtime = object()
    tui._last_ctf_context = {
        "url": "http://ctf.local",
        "goal": "拿到flag",
        "type": "web",
        "hint": "先看入口",
        "submit_profile": {"base_url": "https://ctf.example.com"},
        "runner_config": {"mode": "single"},
        "execution_mode": "crew",
        "autonomy_state": {
            "config": {"mode": "single", "max_challenges": 1, "timebox_seconds": 900, "max_consecutive_stops": 2},
            "started_at": 1.0,
            "visited_keys": ["42|http://ctf.local"],
            "records": [{"challenge_id": "42", "challenge_name": "demo", "url": "http://ctf.local", "outcome": "stopped", "reason": "all_hypotheses_exhausted", "success": False, "started_at": 1.0, "ended_at": 2.0, "chain_used": [], "missing_tools": [], "blocked_reason": "", "skip_reason": "", "stop_reason_class": "stopped", "visit_key": "42|http://ctf.local", "switch_reason": "", "switch_source": ""}],
            "consecutive_stops": 1,
            "switched_count": 0,
            "switch_events": [],
            "last_switch_reason": "",
            "last_switch_source": "",
        },
    }

    notes_calls = []

    async def _fake_notes(payload, runtime=None):
        notes_calls.append((payload, runtime))
        return {"ok": True}

    monkeypatch.setattr("pentestagent.tools.notes.notes", _fake_notes)

    captured = {}

    def _fake_crew_run(url, goal, chtype, hint, submit_profile, runner_config):
        captured.update(
            {
                "url": url,
                "goal": goal,
                "type": chtype,
                "hint": hint,
                "submit_profile": submit_profile,
                "runner_config": runner_config,
            }
        )
        return "crew-worker"

    def _unexpected_dispatcher(*args, **kwargs):
        raise AssertionError("dispatcher path should not be used for crew restart")

    tui._run_ctf_crew_dispatcher_mode = _fake_crew_run
    tui._run_ctf_dispatcher_mode = _unexpected_dispatcher

    await PentestAgentTUI._parse_ctf_command(tui, '/ctf hint "继续测 /admin"')

    assert notes_calls
    assert captured["url"] == "http://ctf.local"
    assert "继续测 /admin" in captured["hint"]
    assert captured["runner_config"]["_autonomy_resume_reason"] == "operator_hint_restart"
    assert captured["runner_config"]["_autonomy_resume_state"]["records"][0]["challenge_id"] == "42"
    assert tui._current_worker == "crew-worker"


@pytest.mark.asyncio
async def test_ctf_hint_subcommand_restarts_from_session_context_resume_payload_when_autonomy_state_missing(monkeypatch):
    tui = _make_tui_stub()
    tui.runtime = object()
    tui._last_ctf_context = {
        "url": "http://ctf.local/challenges/42",
        "goal": "拿到flag",
        "type": "web",
        "hint": "先看登录口",
        "submit_profile": {
            "base_url": "https://ctf.example.com",
            "challenge_id": "42",
        },
        "runner_config": {"mode": "single"},
        "sessionContext": {
            "resumeContext": {
                "runId": "run-session-context-1",
                "checkpointId": "checkpoint-1",
                "checkpointLabel": "task_finished",
                "stopReason": "flag_verified",
                "verifiedFlags": ["flag{ctx_ok}"],
                "runtimeFlags": [],
                "recentEventTypes": [
                    "dispatcher_started",
                    "verification_decision",
                    "task_finished",
                ],
                "artifactRefs": [
                    {
                        "artifactId": "artifact-1",
                        "kind": "artifact",
                        "title": "ctf_backup_candidate",
                        "location": "http://ctf.local/www.zip",
                        "path": None,
                    }
                ],
                "summary": (
                    "run_id=run-session-context-1; latest_checkpoint=task_finished; "
                    "stop_reason=flag_verified; verified_flags=flag{ctx_ok}; "
                    "recent_events=dispatcher_started, verification_decision, task_finished; "
                    "artifacts=ctf_backup_candidate"
                ),
            }
        },
    }

    notes_calls = []

    async def _fake_notes(payload, runtime=None):
        notes_calls.append((payload, runtime))
        return {"ok": True}

    monkeypatch.setattr(
        "pentestagent.tools.notes.notes",
        _fake_notes,
    )

    captured = {}

    def _fake_run(url, goal, chtype, hint, submit_profile, runner_config):
        captured.update(
            {
                "url": url,
                "goal": goal,
                "type": chtype,
                "hint": hint,
                "submit_profile": submit_profile,
                "runner_config": runner_config,
            }
        )
        return "worker"

    tui._run_ctf_dispatcher_mode = _fake_run

    await PentestAgentTUI._parse_ctf_command(tui, '/ctf hint "试试 PHP 反序列化"')

    assert notes_calls
    assert captured["url"] == "http://ctf.local/challenges/42"
    assert "试试 PHP 反序列化" in captured["hint"]
    resume_state = captured["runner_config"]["_autonomy_resume_state"]
    assert resume_state["records"][0]["challenge_id"] == "42"
    assert resume_state["records"][0]["reason"] == "flag_verified"
    assert resume_state["records"][0]["success"] is True
    assert captured["runner_config"]["_autonomy_resume_reason"] == "operator_hint_restart"
    assert tui._current_worker == "worker"


@pytest.mark.asyncio
async def test_ctf_wrong_subcommand_restarts_crew_when_last_mode_is_crew(monkeypatch):
    tui = _make_tui_stub()
    tui.runtime = object()
    tui._last_ctf_context = {
        "url": "http://ctf.local",
        "goal": "拿到flag",
        "type": "web",
        "hint": "已有基础线索",
        "submit_profile": {},
        "runner_config": {"mode": "single"},
        "execution_mode": "crew",
        "autonomy_state": {
            "config": {"mode": "single", "max_challenges": 1, "timebox_seconds": 900, "max_consecutive_stops": 2},
            "started_at": 1.0,
            "visited_keys": ["42|http://ctf.local"],
            "records": [{"challenge_id": "42", "challenge_name": "demo", "url": "http://ctf.local", "outcome": "blocked", "reason": "wrong_flag_feedback", "success": False, "started_at": 1.0, "ended_at": 2.0, "chain_used": [], "missing_tools": [], "blocked_reason": "wrong_flag_feedback", "skip_reason": "", "stop_reason_class": "blocked", "visit_key": "42|http://ctf.local", "switch_reason": "", "switch_source": ""}],
            "consecutive_stops": 1,
            "switched_count": 0,
            "switch_events": [],
            "last_switch_reason": "",
            "last_switch_source": "",
        },
    }

    async def _fake_notes(payload, runtime=None):
        return {"ok": True}

    async def _fake_wrong_feedback(flag: str):
        return f"wrong-flag recovery: {flag}"

    monkeypatch.setattr("pentestagent.tools.notes.notes", _fake_notes)
    tui._apply_ctf_wrong_flag_feedback = _fake_wrong_feedback
    tui._show_ctf_memory_panel = lambda *args, **kwargs: None

    captured = {}

    def _fake_crew_run(url, goal, chtype, hint, submit_profile, runner_config):
        captured.update(
            {
                "url": url,
                "goal": goal,
                "type": chtype,
                "hint": hint,
                "runner_config": runner_config,
            }
        )
        return "crew-worker"

    def _unexpected_dispatcher(*args, **kwargs):
        raise AssertionError("dispatcher path should not be used for crew wrong-flag restart")

    tui._run_ctf_crew_dispatcher_mode = _fake_crew_run
    tui._run_ctf_dispatcher_mode = _unexpected_dispatcher

    await PentestAgentTUI._parse_ctf_command(tui, "/ctf wrong flag{bad}")

    assert captured["url"] == "http://ctf.local"
    assert "Rejected flag feedback" in captured["hint"]
    assert captured["runner_config"]["_autonomy_resume_reason"] == "wrong_flag_feedback_restart"
    assert captured["runner_config"]["_autonomy_resume_state"]["records"][0]["reason"] == "wrong_flag_feedback"
    assert tui._current_worker == "crew-worker"


@pytest.mark.asyncio
async def test_ctf_override_subcommand_promotes_flag_to_verified(monkeypatch):
    tui = _make_tui_stub()
    tui.runtime = object()

    notes_calls = []

    async def _fake_notes(payload, runtime=None):
        notes_calls.append((payload, runtime))
        return {"ok": True}

    monkeypatch.setattr(
        "pentestagent.tools.notes.notes",
        _fake_notes,
    )

    await PentestAgentTUI._parse_ctf_command(tui, "/ctf override flag{candidate_only}")

    assert notes_calls
    assert all(
        (item.get("value") if isinstance(item, dict) else item) != "flag{candidate_only}"
        for item in tui._last_ctf_state["candidate_flags"]
    )
    assert any(
        (item.get("value") if isinstance(item, dict) else item) == "flag{candidate_only}"
        for item in tui._last_ctf_state["verified_flags"]
    )
    assert tui._last_ctf_state["stop_report"]["reason"] == "flag_verified"
    assert any(
        isinstance(item, dict) and item.get("type") == "user_flag_override"
        for item in tui._last_ctf_state["meta_reasonings"]
    )
    assert "[CTF override]" in tui._captured_messages[-1]


@pytest.mark.asyncio
async def test_ctf_capabilities_refresh_rechecks_registry():
    tui = _make_tui_stub()

    class _FakeRegistry:
        def __init__(self):
            self.refreshed = False

        async def full_check(self):
            self.refreshed = True
            return self

        def to_dict(self):
            return {
                "last_full_check": 123.0,
                "primitives": {
                    "sql_injection_test": {
                        "best_available": {
                            "method": "sqlmap",
                            "quality": "high",
                        }
                    }
                },
            }

    fake_registry = _FakeRegistry()
    tui._last_ctf_dispatcher = type(
        "Dispatcher",
        (),
        {
            "capability_registry": fake_registry,
            "state": type("State", (), {"capabilities": {}})(),
        },
    )()

    await PentestAgentTUI._parse_ctf_command(tui, "/ctf capabilities --refresh")

    assert fake_registry.refreshed is True
    assert tui._last_ctf_state["capabilities"]["last_full_check"] == 123.0
    assert any("snapshot refreshed" in message for message in tui._captured_messages)


@pytest.mark.asyncio
async def test_ctf_memory_list_show_mute_commands(monkeypatch):
    tui = _make_tui_stub()

    class _FakeEntry:
        def __init__(self, status="active"):
            self.id = "mem_1"
            self.winning_hypothesis_kinds = ["auth_form_sqli"]
            self.failed_hypothesis_kinds = ["generic_web_recon"]
            self.winning_primitive_sequence = ["sqli"]
            self.learned_rules = ["源码 flag 只算 candidate"]
            self.challenge_url = "http://ctf.local"
            self.fingerprint = type(
                "FP",
                (),
                {"detected_type": "sqli", "tech_stack": ["php"], "auth_mechanism": "form_login"},
            )()
            self.metadata = type(
                "Meta",
                (),
                {
                    "manual_status": status,
                    "applied_count": 2,
                    "success_correlation": 1.0,
                    "successful_applications": 2,
                    "failed_applications": 0,
                    "confidence_decay_factor": 1.0,
                },
            )()

    class _FakeStore:
        def __init__(self, *args, **kwargs):
            pass

        async def list_entries(self, limit: int = 10, manual_status=None):
            return [_FakeEntry()]

        async def get_entry(self, entry_id: str):
            return _FakeEntry()

        async def mute_entry(self, entry_id: str):
            return _FakeEntry(status="muted")

        async def activate_entry(self, entry_id: str):
            return _FakeEntry(status="active")

        async def audit_entries(self, threshold: float = 0.3, min_applied: int = 1):
            return [_FakeEntry(status="muted")]

    monkeypatch.setattr(
        "pentestagent.agents.pa_agent.strategy_memory.StrategyMemoryStore",
        _FakeStore,
    )

    await PentestAgentTUI._parse_ctf_command(tui, "/ctf memory list")
    assert "[CTF memory list]" in tui._captured_messages[-1]
    assert "facts=" in tui._captured_messages[-1]

    await PentestAgentTUI._parse_ctf_command(tui, "/ctf memory show mem_1")
    assert "[CTF memory show] mem_1" in tui._captured_messages[-1]
    assert "atomic_facts:" in tui._captured_messages[-1]

    await PentestAgentTUI._parse_ctf_command(tui, "/ctf memory mute mem_1")
    assert "muted mem_1" in tui._captured_messages[-1]

    await PentestAgentTUI._parse_ctf_command(tui, "/ctf memory audit")
    assert "[CTF memory audit]" in tui._captured_messages[-1]


@pytest.mark.asyncio
async def test_ctf_memory_activate_rollback_delete_export_clear_and_panel(monkeypatch):
    tui = _make_tui_stub()
    panel_calls = []

    class _FakeEntry:
        def __init__(self, status="active"):
            self.id = "mem_1"
            self.winning_hypothesis_kinds = ["auth_form_sqli"]
            self.failed_hypothesis_kinds = ["generic_web_recon"]
            self.winning_primitive_sequence = ["sqli"]
            self.learned_rules = ["源码 flag 只算 candidate"]
            self.challenge_url = "http://ctf.local"
            self.fingerprint = type(
                "FP",
                (),
                {
                    "detected_type": "sqli",
                    "tech_stack": ["php"],
                    "auth_mechanism": "form_login",
                },
            )()
            self.metadata = type(
                "Meta",
                (),
                {
                    "manual_status": status,
                    "applied_count": 2,
                    "success_correlation": 0.4,
                    "successful_applications": 2,
                    "failed_applications": 1,
                    "confidence_decay_factor": 0.9,
                },
            )()

    class _FakeStore:
        def __init__(self, *args, **kwargs):
            pass

        async def activate_entry(self, entry_id: str):
            assert entry_id == "mem_1"
            return _FakeEntry(status="active")

        async def rollback_mute(self, entry_id: str):
            assert entry_id == "mem_1"
            return _FakeEntry(status="active")

        async def delete_entry(self, entry_id: str):
            assert entry_id == "mem_1"
            return True

        async def export_entries(self, path: str):
            assert path == "D:/tmp/memory.json"
            return path

        async def clear_entries(self):
            return 3

    monkeypatch.setattr(
        "pentestagent.agents.pa_agent.strategy_memory.StrategyMemoryStore",
        _FakeStore,
    )
    tui._show_ctf_memory_panel = (
        lambda filter_mode="all", sort_by="recent", threshold=0.3, preferred_entry_ids=None: panel_calls.append(
            {
                "filter_mode": filter_mode,
                "sort_by": sort_by,
                "threshold": threshold,
                "preferred_entry_ids": preferred_entry_ids,
            }
        )
    )

    await PentestAgentTUI._parse_ctf_command(tui, "/ctf memory activate mem_1")
    assert "activated mem_1" in tui._captured_messages[-1]

    await PentestAgentTUI._parse_ctf_command(tui, "/ctf memory rollback mem_1")
    assert "rollback applied to mem_1" in tui._captured_messages[-1]

    await PentestAgentTUI._parse_ctf_command(tui, "/ctf memory delete mem_1")
    assert "deleted mem_1" in tui._captured_messages[-1]

    await PentestAgentTUI._parse_ctf_command(tui, "/ctf memory export D:/tmp/memory.json")
    assert "exported to D:/tmp/memory.json" in tui._captured_messages[-1]

    await PentestAgentTUI._parse_ctf_command(tui, "/ctf memory clear confirm")
    assert "cleared 3 entries" in tui._captured_messages[-1]

    await PentestAgentTUI._parse_ctf_command(
        tui,
        "/ctf memory panel filter=muted sort=correlation threshold=0.6",
    )
    assert tui._captured_messages[-1] == "[CTF memory] panel mounted."
    assert panel_calls == [
        {
            "filter_mode": "muted",
            "sort_by": "correlation",
            "threshold": 0.6,
            "preferred_entry_ids": None,
        }
    ]


@pytest.mark.asyncio
async def test_ctf_wrong_flag_feedback_updates_stop_report_and_memory(monkeypatch):
    tui = _make_tui_stub()
    tui._last_ctf_context = {
        "url": "http://ctf.local",
        "goal": "拿到flag",
        "type": "sqli",
        "hint": "",
    }
    tui._last_ctf_state["meta_reasonings"].append(
        {
            "type": "strategy_memory_session_entry",
            "entry_id": "mem_session",
            "solved": True,
            "chain_used": ["sqli"],
        }
    )

    class _FakeStore:
        def __init__(self, *args, **kwargs):
            pass

        async def apply_rejected_feedback(self, entry_ids, *, session_entry_id=None):
            assert entry_ids == ["mem_1"]
            assert session_entry_id == "mem_session"
            return {
                "affected_entry_ids": ["mem_1"],
                "auto_muted_entry_ids": ["mem_2"],
                "deprecated_entry_id": "mem_session",
                "entries": [],
            }

    monkeypatch.setattr(
        "pentestagent.agents.pa_agent.strategy_memory.StrategyMemoryStore",
        _FakeStore,
    )

    summary = await PentestAgentTUI._apply_ctf_wrong_flag_feedback(
        tui,
        "flag{wrong_one}",
    )

    stop_report = tui._last_ctf_state["stop_report"]
    assert "wrong-flag recovery" in summary
    assert "matched_atomic_facts" in summary
    assert stop_report["reason"] == "wrong_flag_feedback"
    assert "flag{wrong_one}" in stop_report["rejected_flags"]
    assert any("原子事实" in item for item in stop_report.get("memory_explanations") or [])
    assert "mem_1" in list(stop_report.get("memory_focus_entry_ids") or [])
    assert any(
        command == "/ctf memory panel filter=audit sort=correlation threshold=0.60"
        for command in list(stop_report.get("memory_quick_commands") or [])
    )
    assert any(
        item.get("type") == "strategy_memory_wrong_flag_audit"
        for item in tui._last_ctf_state["meta_reasonings"]
        if isinstance(item, dict)
    )
    wrong_audit = next(
        item
        for item in reversed(tui._last_ctf_state["meta_reasonings"])
        if isinstance(item, dict) and item.get("type") == "strategy_memory_wrong_flag_audit"
    )
    assert "signal:login_form" in list(wrong_audit.get("matched_atomic_facts") or [])
    assert wrong_audit.get("memory_trace")
    assert "mem_1" in list(tui._ctf_memory_preferred_entry_ids())


def test_ctf_memory_entry_detail_shows_wrong_flag_trace():
    tui = _make_tui_stub()
    tui._last_ctf_state["meta_reasonings"].append(
        {
            "type": "strategy_memory_wrong_flag_audit",
            "wrong_flag": "flag{wrong_one}",
            "affected_entry_ids": ["mem_1"],
            "auto_muted_entry_ids": ["mem_2"],
            "deprecated_entry_id": "mem_session",
            "matched_atomic_facts": ["signal:login_form", "auth:form_login"],
            "memory_trace": ["auto_muted:mem_2", "deprecated:mem_session"],
        }
    )

    entry = type(
        "Entry",
        (),
        {
            "id": "mem_1",
            "winning_hypothesis_kinds": ["auth_form_sqli"],
            "failed_hypothesis_kinds": ["generic_web_recon"],
            "winning_primitive_sequence": ["sqli"],
            "learned_rules": ["源码 flag 只算 candidate"],
            "challenge_url": "http://ctf.local",
            "atomic_facts": ["type:sqli", "signal:login_form"],
            "fingerprint": type(
                "FP",
                (),
                {
                    "detected_type": "sqli",
                    "tech_stack": ["php"],
                    "auth_mechanism": "form_login",
                },
            )(),
            "metadata": type(
                "Meta",
                (),
                {
                    "manual_status": "active",
                    "applied_count": 2,
                    "success_correlation": 0.4,
                    "successful_applications": 2,
                    "failed_applications": 1,
                    "confidence_decay_factor": 0.9,
                },
            )(),
        },
    )()

    rendered = tui._format_ctf_memory_entry_detail(entry)

    assert "related_wrong_flag: flag{wrong_one}" in rendered
    assert "related_atomic_facts: ['signal:login_form', 'auth:form_login']" in rendered
    assert "related_memory_trace: ['auto_muted:mem_2', 'deprecated:mem_session']" in rendered
    assert "last_similarity: 0.88" in rendered
    assert "matched_atomic_facts: ['type:sqli', 'signal:login_form', 'auth:form_login']" in rendered


@pytest.mark.asyncio
async def test_ctf_crew_dispatcher_mode_carries_platform_switch_context_across_auto_switch(
    monkeypatch,
):
    tui = _make_tui_stub()
    tui.runtime = object()
    tui.agent = type("Agent", (), {"llm": None, "runtime": None})()
    tui._set_status = lambda *args, **kwargs: None
    tui._show_sidebar = lambda *args, **kwargs: None
    tui._show_ctf_memory_panel = lambda *args, **kwargs: None
    tui._add_crew_worker = lambda *args, **kwargs: None
    tui._update_crew_worker = lambda *args, **kwargs: None
    tui._render_last_ctf_stop_report = lambda *args, **kwargs: "[stop-report]"
    tui._render_last_ctf_reasoning = lambda *args, **kwargs: "[reasoning]"
    tui._current_crew = None

    async def _fake_save():
        return None

    async def _fast_sleep(_seconds):
        return None

    tui._save_current_conversation = _fake_save
    monkeypatch.setattr("pentestagent.interface.tui.asyncio.sleep", _fast_sleep)

    from pentestagent.agents.pa_agent.ctf_state import CTFState

    class _FakeCapabilityRegistry:
        async def full_check(self):
            return None

        def to_dict(self):
            return {"primitives": {}}

    class _FakeReasoningLayer:
        def generate_stop_report(self, state, *, reason, missing_capabilities):
            state.stop_report = {
                "reason": reason,
                "missing_capabilities": list(missing_capabilities or []),
                "user_next_steps": [],
            }

    class _FakeDispatcher:
        def __init__(self, *args, **kwargs):
            self.state = None
            self.capability_registry = _FakeCapabilityRegistry()
            self.reasoning_layer = _FakeReasoningLayer()

        def _apply_submit_profile(self, submit_profile):
            if self.state is None:
                return
            profile = dict(submit_profile or {})
            self.state.submit_base_url = str(profile.get("base_url") or "")
            self.state.submit_challenge_id = str(profile.get("challenge_id") or "")
            self.state.submit_auto = bool(profile.get("auto_submit", True))

        async def _snapshot_platform_context(self, current_url):
            challenge_id = str(self.state.submit_challenge_id or "").strip()
            queue_tasks = [
                {
                    "challenge_id": challenge_id,
                    "name": f"Challenge-{challenge_id}",
                    "solved": True,
                    "url": current_url,
                }
            ]
            if challenge_id == "42":
                queue_tasks.append(
                    {
                        "challenge_id": "99",
                        "name": "Challenge-99",
                        "solved": False,
                        "url": "/challenges/99",
                    }
                )
            self.state.meta_reasonings.extend(
                [
                    {
                        "type": "platform_profile_snapshot",
                        "platform_type": "ctfd",
                        "base_url": "https://ctf.example.com",
                        "challenge_id": challenge_id,
                        "auto_submit": True,
                    },
                    {
                        "type": "platform_task_queue_snapshot",
                        "platform_type": "ctfd",
                        "total": len(queue_tasks),
                        "unsolved_count": sum(1 for item in queue_tasks if not item.get("solved")),
                        "solved_count": sum(1 for item in queue_tasks if item.get("solved")),
                        "next_challenge_id": "99" if challenge_id == "42" else "",
                        "next_challenge_name": "Challenge-99" if challenge_id == "42" else "",
                        "rate_limited_until": 0.0,
                        "tasks": queue_tasks,
                    },
                ]
            )

        async def _phase_recon(self, current_url):
            return {"html": "", "content": current_url}

        def _align_platform_challenge(self, current_url, page_features):
            challenge_id = str(self.state.submit_challenge_id or "").strip()
            return {
                "matched": True,
                "match_reason": "challenge_id_exact",
                "challenge_id": challenge_id,
                "challenge_name": f"Challenge-{challenge_id}",
                "already_solved": True,
                "confidence": 1.0,
            }

        def _build_already_solved_reason(self):
            return "platform challenge already solved"

    monkeypatch.setattr(
        "pentestagent.agents.pa_agent.ctf_dispatcher.CTFTaskDispatcher",
        _FakeDispatcher,
    )

    await PentestAgentTUI._run_ctf_crew_dispatcher_mode.__wrapped__(
        tui,
        url="https://ctf.example.com/challenges/42",
        goal="拿到flag",
        chtype="auto",
        hint="",
        submit_profile={"base_url": "https://ctf.example.com", "challenge_id": "42"},
        runner_config={"mode": "switch", "max_challenges": 2, "timebox_seconds": 60},
    )

    assert tui._last_ctf_context["execution_mode"] == "crew"
    assert tui._last_ctf_context["url"].endswith("/challenges/99")
    assert tui._last_ctf_context["autonomy_end_reason"] == "challenge_budget_exhausted"
    meta_reasonings = tui._last_ctf_state["meta_reasonings"]
    assert any(
        isinstance(item, dict)
        and item.get("type") == "platform_switch_carryover_context"
        and item.get("challenge_id") == "99"
        for item in meta_reasonings
    )
    assert any(
        isinstance(item, dict)
        and item.get("type") == "platform_queue_switch_decision"
        and item.get("next_challenge_id") == "99"
        for item in meta_reasonings
    )
    rendered = PentestAgentTUI._render_last_ctf_status(tui)
    assert "[queue switch]" in rendered
    assert "next_challenge_id: 99" in rendered


@pytest.mark.asyncio
async def test_ctf_crew_dispatcher_mode_writes_platform_stop_summary_for_blocked_run(
    monkeypatch,
):
    tui = _make_tui_stub()
    tui.runtime = object()
    tui.agent = type("Agent", (), {"llm": None, "runtime": None})()
    tui._set_status = lambda *args, **kwargs: None
    tui._show_sidebar = lambda *args, **kwargs: None
    tui._show_ctf_memory_panel = lambda *args, **kwargs: None
    tui._add_crew_worker = lambda *args, **kwargs: None
    tui._update_crew_worker = lambda *args, **kwargs: None
    tui._render_last_ctf_stop_report = lambda *args, **kwargs: "[stop-report]"
    tui._render_last_ctf_reasoning = lambda *args, **kwargs: "[reasoning]"
    tui._current_crew = None

    async def _fake_save():
        return None

    async def _fast_sleep(_seconds):
        return None

    tui._save_current_conversation = _fake_save
    monkeypatch.setattr("pentestagent.interface.tui.asyncio.sleep", _fast_sleep)

    class _FakeCapabilityRegistry:
        async def full_check(self):
            return None

        def to_dict(self):
            return {"primitives": {}}

    class _FakeReasoningLayer:
        def generate_stop_report(self, state, *, reason, missing_capabilities):
            state.stop_report = {
                "reason": reason,
                "missing_capabilities": list(missing_capabilities or []),
                "user_next_steps": [],
            }

    class _FakeDispatcher:
        def __init__(self, *args, **kwargs):
            self.state = None
            self.hypothesis_engine = type(
                "HypothesisEngine",
                (),
                {"generate": lambda *args, **kwargs: []},
            )()
            self.capability_registry = _FakeCapabilityRegistry()
            self.reasoning_layer = _FakeReasoningLayer()

        def _apply_submit_profile(self, submit_profile):
            if self.state is None:
                return
            profile = dict(submit_profile or {})
            self.state.submit_base_url = str(profile.get("base_url") or "")
            self.state.submit_challenge_id = str(profile.get("challenge_id") or "")
            self.state.submit_auto = bool(profile.get("auto_submit", True))

        async def _snapshot_platform_context(self, current_url):
            challenge_id = str(self.state.submit_challenge_id or "").strip() or "42"
            self.state.meta_reasonings.extend(
                [
                    {
                        "type": "platform_profile_snapshot",
                        "platform_type": "ctfd",
                        "base_url": "https://ctf.example.com",
                        "challenge_id": challenge_id,
                        "auto_submit": True,
                    },
                    {
                        "type": "platform_task_queue_snapshot",
                        "platform_type": "ctfd",
                        "total": 1,
                        "unsolved_count": 1,
                        "solved_count": 0,
                        "next_challenge_id": challenge_id,
                        "next_challenge_name": "Challenge-42",
                        "rate_limited_until": 0.0,
                        "tasks": [
                            {
                                "challenge_id": challenge_id,
                                "name": "Challenge-42",
                                "solved": False,
                                "url": current_url,
                            }
                        ],
                    },
                ]
            )

        async def _phase_recon(self, current_url):
            return {"html": "<form></form>", "content": current_url}

        def _align_platform_challenge(self, current_url, page_features):
            return {
                "matched": True,
                "match_reason": "challenge_id_exact",
                "challenge_id": "42",
                "challenge_name": "Challenge-42",
                "already_solved": False,
                "confidence": 1.0,
            }

    class _WorkerSpec:
        def __init__(self):
            self.worker_id = "worker-1"
            self.worker_type = "exploit"
            self.task = "Try auth bypass"

    class _CrewSummary:
        started_workers = ["worker-1"]
        completed_workers = ["worker-1"]
        cancelled_workers = []
        verified_flag = None
        stop_reason = "workers_completed"
        worker_results = {
            "worker-1": {
                "reason": "wrong flag feedback: flag{bad}",
                "missing_tools": [],
            }
        }

    class _FakeCoordinator:
        def __init__(self, *args, **kwargs):
            self.state = kwargs["state"]

        def build_worker_specs(self, *args, **kwargs):
            return [_WorkerSpec()]

        async def run_with_shadow_graph(self, *args, **kwargs):
            return _CrewSummary()

    monkeypatch.setattr(
        "pentestagent.agents.pa_agent.ctf_dispatcher.CTFTaskDispatcher",
        _FakeDispatcher,
    )
    monkeypatch.setattr(
        "pentestagent.agents.pa_agent.ctf_crew_coordinator.CTFCrewCoordinator",
        _FakeCoordinator,
    )
    monkeypatch.setattr(
        "pentestagent.agents.pa_agent.ctf_planner.detect_type",
        lambda page_source, url: "web",
    )

    await PentestAgentTUI._run_ctf_crew_dispatcher_mode.__wrapped__(
        tui,
        url="https://ctf.example.com/challenges/42",
        goal="拿到flag",
        chtype="auto",
        hint="",
        submit_profile={"base_url": "https://ctf.example.com", "challenge_id": "42"},
        runner_config={"mode": "single", "max_challenges": 1, "timebox_seconds": 60},
    )

    meta_reasonings = tui._last_ctf_state["meta_reasonings"]
    stop_summary = next(
        item
        for item in reversed(meta_reasonings)
        if isinstance(item, dict) and item.get("type") == "platform_run_stop_summary"
    )
    assert stop_summary["blocked_reasons"] == ["wrong_flag_feedback"]
    assert stop_summary["last_record"]["outcome"] == "blocked"
    assert stop_summary["last_record"]["reason"] == "wrong_flag_feedback"
    rendered = PentestAgentTUI._render_last_ctf_status(tui)
    assert "[platform run stop]" in rendered
    assert "blocked_reasons: ['wrong_flag_feedback']" in rendered
