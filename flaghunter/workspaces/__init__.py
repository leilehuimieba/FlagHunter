"""Workspace package exports.

Keep imports lazy so callers that only need lightweight helpers (for example
``workspaces.validation``) do not require optional YAML-related dependencies at
package import time.
"""

from __future__ import annotations

from importlib import import_module
from typing import Any

__all__ = ["WorkspaceManager", "TargetManager", "WorkspaceError"]

_LAZY_EXPORTS = {
    "WorkspaceManager": (".manager", "WorkspaceManager"),
    "TargetManager": (".manager", "TargetManager"),
    "WorkspaceError": (".manager", "WorkspaceError"),
}


def __getattr__(name: str) -> Any:
    try:
        module_name, attr_name = _LAZY_EXPORTS[name]
    except KeyError as exc:
        raise AttributeError(name) from exc

    value = getattr(import_module(module_name, __name__), attr_name)
    globals()[name] = value
    return value
