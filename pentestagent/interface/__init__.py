"""User interface module for PentestAgent.

Keep package imports lazy so non-UI callers can reuse light helpers such as
``interface.initializer`` without pulling in optional UI/server dependencies
(``aiohttp``, Textual, etc.) at import time.
"""

from __future__ import annotations

from importlib import import_module
from typing import Any

__all__ = [
    "main",
    "run_cli",
    "run_tui",
    "PentestAgentTUI",
    "print_banner",
    "format_finding",
    "print_status",
]

_LAZY_EXPORTS = {
    "run_cli": (".cli", "run_cli"),
    "main": (".main", "main"),
    "PentestAgentTUI": (".tui", "PentestAgentTUI"),
    "run_tui": (".tui", "run_tui"),
    "format_finding": (".utils", "format_finding"),
    "print_banner": (".utils", "print_banner"),
    "print_status": (".utils", "print_status"),
}


def __getattr__(name: str) -> Any:
    try:
        module_name, attr_name = _LAZY_EXPORTS[name]
    except KeyError as exc:
        raise AttributeError(name) from exc

    value = getattr(import_module(module_name, __name__), attr_name)
    globals()[name] = value
    return value
