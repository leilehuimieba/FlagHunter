"""FlagHunter main agent implementation.

Keep package exports lazy so submodules such as ``ctf_dispatcher`` can be
imported without forcing the full agent stack and its optional dependencies.
"""

from __future__ import annotations

from importlib import import_module
from typing import Any

__all__ = ["FlagHunterAgent"]


def __getattr__(name: str) -> Any:
    if name != "FlagHunterAgent":
        raise AttributeError(name)

    value = getattr(import_module(".pa_agent", __name__), name)
    globals()[name] = value
    return value
