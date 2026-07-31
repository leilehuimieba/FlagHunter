"""A-01 — the canonical task lifecycle contract makes every entry synonymous.

These guards pin the properties the control surfaces (A-03/A-04) will rely on:
full dialect coverage (no raw status escapes the contract), lossless
canonicalization, the cross-entry synonym relation, and legal-transition rules.
"""

from __future__ import annotations

import pytest

from flaghunter.domain import task_lifecycle as tl
from flaghunter.domain.task_lifecycle import Dialect, TaskState


# --- the three legacy vocabularies, verbatim from their source modules -------
_WEB_STATUSES = {"queued", "running", "success", "failed", "stopped"}
_MCP_STATUSES = {"pending", "running", "done", "error", "cancelled"}
_REGISTRY_STATUSES = {"created", "running", "completed", "failed", "stopped"}


def test_every_dialect_status_canonicalizes():
    # Coverage: each raw status a surface can emit maps to a canonical state,
    # so a new status can never silently fall outside the contract.
    for raw in _WEB_STATUSES:
        assert isinstance(tl.canonicalize(Dialect.WEB, raw), TaskState)
    for raw in _MCP_STATUSES:
        assert isinstance(tl.canonicalize(Dialect.MCP, raw), TaskState)
    for raw in _REGISTRY_STATUSES:
        assert isinstance(tl.canonicalize(Dialect.REGISTRY, raw), TaskState)


def test_canonicalize_is_case_and_space_insensitive():
    assert tl.canonicalize(Dialect.WEB, "  RUNNING ") is TaskState.RUNNING
    assert tl.canonicalize(Dialect.MCP, "Cancelled") is TaskState.CANCELLED


def test_unknown_status_raises_rather_than_guessing():
    with pytest.raises(tl.UnknownTaskStatus):
        tl.canonicalize(Dialect.WEB, "done")  # 'done' is MCP-only, not Web
    with pytest.raises(tl.UnknownTaskStatus):
        tl.canonicalize(Dialect.MCP, "success")  # 'success' is Web-only


def test_stop_and_cancel_are_the_same_canonical_state():
    # The headline synonym: Web "stop" and MCP "cancel" are one abort.
    assert tl.canonicalize(Dialect.WEB, "stopped") is TaskState.CANCELLED
    assert tl.canonicalize(Dialect.MCP, "cancelled") is TaskState.CANCELLED
    assert tl.canonicalize(Dialect.REGISTRY, "stopped") is TaskState.CANCELLED


def test_done_is_completion_not_verified_success():
    # A-06 honesty: MCP "done" is loop-ended, NOT a verified solve.
    assert tl.canonicalize(Dialect.MCP, "done") is TaskState.COMPLETED
    # Web "success" is proof-backed (post A-05) and is the verified terminal.
    assert tl.canonicalize(Dialect.WEB, "success") is TaskState.SUCCEEDED
    assert TaskState.COMPLETED is not TaskState.SUCCEEDED


def test_synonyms_relation_groups_cross_entry_spellings():
    cancelled = tl.synonyms(TaskState.CANCELLED)
    assert cancelled == {
        Dialect.WEB: "stopped",
        Dialect.MCP: "cancelled",
        Dialect.REGISTRY: "stopped",
    }
    failed = tl.synonyms(TaskState.FAILED)
    assert failed == {
        Dialect.WEB: "failed",
        Dialect.MCP: "error",
        Dialect.REGISTRY: "failed",
    }


def test_render_round_trips_native_states():
    # For a status a dialect natively emits, canonicalize -> render is identity.
    for dialect, statuses in (
        (Dialect.WEB, _WEB_STATUSES),
        (Dialect.MCP, _MCP_STATUSES),
        (Dialect.REGISTRY, _REGISTRY_STATUSES),
    ):
        for raw in statuses:
            state = tl.canonicalize(dialect, raw)
            assert tl.render(dialect, state) == raw


def test_render_returns_none_for_foreign_states():
    # Web has no native spelling for the outcome-neutral COMPLETED.
    assert tl.render(Dialect.WEB, TaskState.COMPLETED) is None
    # MCP has no native spelling for the verified SUCCEEDED.
    assert tl.render(Dialect.MCP, TaskState.SUCCEEDED) is None


def test_terminal_and_active_partition_all_states():
    assert tl.TERMINAL_STATES | tl.ACTIVE_STATES == set(TaskState)
    assert not (tl.TERMINAL_STATES & tl.ACTIVE_STATES)
    assert tl.is_active(TaskState.RUNNING)
    assert tl.is_terminal(TaskState.CANCELLED)
    assert not tl.is_terminal(TaskState.PENDING)


def test_legal_transitions():
    assert tl.can_transition(TaskState.PENDING, TaskState.RUNNING)
    assert tl.can_transition(TaskState.RUNNING, TaskState.SUCCEEDED)
    assert tl.can_transition(TaskState.PENDING, TaskState.CANCELLED)  # abort before start


def test_terminal_states_are_sinks():
    for terminal in tl.TERMINAL_STATES:
        for dst in TaskState:
            assert not tl.can_transition(terminal, dst)


def test_assert_transition_rejects_illegal_moves():
    with pytest.raises(tl.IllegalTaskTransition):
        tl.assert_transition(TaskState.SUCCEEDED, TaskState.RUNNING)
    with pytest.raises(tl.IllegalTaskTransition):
        tl.assert_transition(TaskState.RUNNING, TaskState.PENDING)  # no going back
