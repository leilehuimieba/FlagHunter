"""Compatibility exports for the shared composition root.

The real assembly code lives in :mod:`flaghunter.session.initializer` so the
session facade does not import the entry/interface layer.  Keep this module as
a stable import path for older entrypoints and tests.
"""

from ..session.initializer import (
    activate_workspace_for_target,
    build_agent_components,
    build_runtime,
    has_ssh_runtime_config,
)

__all__ = [
    "activate_workspace_for_target",
    "build_agent_components",
    "build_runtime",
    "has_ssh_runtime_config",
]
