"""Canonical task lifecycle contract (A-01 · §1.2 ① · F-01/F-02).

Three entry points historically invented their own status vocabularies for the
*same* underlying lifecycle:

    Web console   queued  | running | success   | failed | stopped
    MCP server    pending | running | done      | error  | cancelled
    task_registry created | running | completed | failed | stopped

Nothing tied them together, so "stopped" (Web) and "cancelled" (MCP) — the same
user-initiated abort — read as different states, and success/verified semantics
drifted per surface. This module is the single source of truth: one canonical
:class:`TaskState` vocabulary, a lossless mapping for every dialect, and a
transition service. It is a pure DOMAIN contract — it imports nothing from the
rest of FlagHunter and changes no runtime behaviour on its own; the control
surfaces (A-03/A-04) consume it to make their statuses genuinely synonymous.

Lifecycle disposition is kept honest with respect to proof authority (A-05/A-06):
``SUCCEEDED`` is a *verified* positive terminal (Web ``success`` is proof-backed
post-A-05), while ``COMPLETED`` is an outcome-neutral "the loop ended" terminal
(MCP ``done``, which A-06 deliberately separated from verified success).
"""

from __future__ import annotations

from enum import Enum


SCHEMA_VERSION = "task.lifecycle.v1"


class TaskState(str, Enum):
    """The canonical lifecycle states, shared by every entry point."""

    PENDING = "pending"      # accepted, not yet executing
    RUNNING = "running"      # executing now
    SUCCEEDED = "succeeded"  # terminal: finished with a proof-backed positive outcome
    COMPLETED = "completed"  # terminal: execution finished, outcome-neutral (no verified solve)
    FAILED = "failed"        # terminal: ended in an error / exception
    CANCELLED = "cancelled"  # terminal: user-initiated abort (Web "stop" / MCP "cancel")
    TIMED_OUT = "timed_out"  # terminal: deadline exceeded


class Dialect(str, Enum):
    """The per-entry status vocabularies mapped onto :class:`TaskState`."""

    WEB = "web"
    MCP = "mcp"
    REGISTRY = "registry"


#: States after which no further work runs. Everything else is "active".
TERMINAL_STATES: frozenset[TaskState] = frozenset(
    {
        TaskState.SUCCEEDED,
        TaskState.COMPLETED,
        TaskState.FAILED,
        TaskState.CANCELLED,
        TaskState.TIMED_OUT,
    }
)
ACTIVE_STATES: frozenset[TaskState] = frozenset({TaskState.PENDING, TaskState.RUNNING})


#: The only legal state transitions. A terminal state transitions to nothing.
_ALLOWED_TRANSITIONS: dict[TaskState, frozenset[TaskState]] = {
    TaskState.PENDING: frozenset(
        {TaskState.RUNNING, TaskState.CANCELLED, TaskState.TIMED_OUT, TaskState.FAILED}
    ),
    TaskState.RUNNING: frozenset(
        {
            TaskState.SUCCEEDED,
            TaskState.COMPLETED,
            TaskState.FAILED,
            TaskState.CANCELLED,
            TaskState.TIMED_OUT,
        }
    ),
    TaskState.SUCCEEDED: frozenset(),
    TaskState.COMPLETED: frozenset(),
    TaskState.FAILED: frozenset(),
    TaskState.CANCELLED: frozenset(),
    TaskState.TIMED_OUT: frozenset(),
}


#: dialect raw-string -> canonical state. Every raw status a surface can emit
#: MUST appear here; the coverage is asserted by the guard tests so a new raw
#: status can never silently escape the contract.
_CANONICAL_BY_DIALECT: dict[Dialect, dict[str, TaskState]] = {
    Dialect.WEB: {
        "queued": TaskState.PENDING,
        "running": TaskState.RUNNING,
        "success": TaskState.SUCCEEDED,
        "failed": TaskState.FAILED,
        "stopped": TaskState.CANCELLED,
    },
    Dialect.MCP: {
        "pending": TaskState.PENDING,
        "running": TaskState.RUNNING,
        "done": TaskState.COMPLETED,
        "error": TaskState.FAILED,
        "cancelled": TaskState.CANCELLED,
    },
    Dialect.REGISTRY: {
        "created": TaskState.PENDING,
        "running": TaskState.RUNNING,
        "completed": TaskState.COMPLETED,
        "failed": TaskState.FAILED,
        "stopped": TaskState.CANCELLED,
    },
}


def _reverse(mapping: dict[str, TaskState]) -> dict[TaskState, str]:
    """Native canonical -> raw for a dialect (first raw wins on collision)."""
    out: dict[TaskState, str] = {}
    for raw, state in mapping.items():
        out.setdefault(state, raw)
    return out


#: canonical state -> the raw string a dialect natively emits for it. Only the
#: states that dialect actually produces are present (a dialect is not forced to
#: invent a spelling for a state it never reaches).
_RAW_BY_DIALECT: dict[Dialect, dict[TaskState, str]] = {
    dialect: _reverse(mapping) for dialect, mapping in _CANONICAL_BY_DIALECT.items()
}


class UnknownTaskStatus(ValueError):
    """Raised when a raw status is not part of a dialect's vocabulary."""


def canonicalize(dialect: Dialect, raw_status: str) -> TaskState:
    """Map a surface's raw status string to the canonical :class:`TaskState`.

    Case- and whitespace-insensitive. Raises :class:`UnknownTaskStatus` for a
    status outside the dialect's known vocabulary rather than guessing, so drift
    surfaces loudly instead of silently collapsing to a wrong state.
    """
    key = (raw_status or "").strip().lower()
    table = _CANONICAL_BY_DIALECT[dialect]
    try:
        return table[key]
    except KeyError as exc:
        raise UnknownTaskStatus(
            f"{dialect.value!r} has no status {raw_status!r}; "
            f"known: {sorted(table)}"
        ) from exc


def render(dialect: Dialect, state: TaskState) -> str | None:
    """Render a canonical state back to a dialect's native raw string.

    Returns ``None`` when the dialect has no native spelling for the state (for
    example, the Web vocabulary never emits the outcome-neutral ``COMPLETED``).
    Callers that must show a foreign state decide their own fallback; the
    contract does not fabricate a lossy spelling here.
    """
    return _RAW_BY_DIALECT[dialect].get(state)


def synonyms(state: TaskState) -> dict[Dialect, str]:
    """All dialect spellings that map to ``state`` — the cross-entry synonym set.

    This is the concrete "所有入口状态同义" relation: e.g. ``CANCELLED`` yields
    ``{WEB: 'stopped', MCP: 'cancelled', REGISTRY: 'stopped'}``.
    """
    return {
        dialect: raw
        for dialect, table in _RAW_BY_DIALECT.items()
        if (raw := table.get(state)) is not None
    }


def is_terminal(state: TaskState) -> bool:
    return state in TERMINAL_STATES


def is_active(state: TaskState) -> bool:
    return state in ACTIVE_STATES


def can_transition(src: TaskState, dst: TaskState) -> bool:
    """Whether ``src`` -> ``dst`` is a legal lifecycle transition."""
    return dst in _ALLOWED_TRANSITIONS[src]


class IllegalTaskTransition(ValueError):
    """Raised when an illegal lifecycle transition is attempted."""


def assert_transition(src: TaskState, dst: TaskState) -> None:
    """Raise :class:`IllegalTaskTransition` if ``src`` -> ``dst`` is not allowed."""
    if not can_transition(src, dst):
        raise IllegalTaskTransition(
            f"illegal task transition {src.value!r} -> {dst.value!r}"
        )
