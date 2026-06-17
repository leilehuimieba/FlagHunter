"""Agent system for FlagHunter.

Avoid importing the full agent stack eagerly so narrow submodules such as the
deterministic CTF dispatcher can be imported without dragging in optional
workspace/runtime dependencies.
"""

from __future__ import annotations

from importlib import import_module
from typing import Any

__all__ = [
    "BaseAgent",
    "AgentMessage",
    "AgentState",
    "CrewOrchestrator",
    "CrewState",
    "AgentWorker",
    "AgentStatus",
]

_LAZY_EXPORTS = {
    "AgentMessage": (".base_agent", "AgentMessage"),
    "BaseAgent": (".base_agent", "BaseAgent"),
    "AgentStatus": (".crew", "AgentStatus"),
    "AgentWorker": (".crew", "AgentWorker"),
    "CrewOrchestrator": (".crew", "CrewOrchestrator"),
    "CrewState": (".crew", "CrewState"),
    "AgentState": (".state", "AgentState"),
}


def __getattr__(name: str) -> Any:
    try:
        module_name, attr_name = _LAZY_EXPORTS[name]
    except KeyError as exc:
        raise AttributeError(name) from exc

    value = getattr(import_module(module_name, __name__), attr_name)
    globals()[name] = value
    return value
