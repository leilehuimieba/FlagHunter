"""Compatibility exports for the shared composition root.

The real assembly code lives in :mod:`flaghunter.session.initializer` so the
session facade does not import the entry/interface layer.  Keep this module as
a stable import path for older entrypoints and tests.

Retention note (H14): this shim is intentionally kept, not deleted. It is a
load-bearing test seam — the web_server suite patches the agent build by
swapping ``sys.modules["flaghunter.interface.initializer"]`` (and web_server
itself resolves the builder via ``importlib.import_module`` on this path so the
patch takes effect). Removing the shim would force rewriting ~15 monkeypatch
sites and break the stable injection point, for no architectural gain: the real
composition root already lives below the interface layer in session.initializer,
and this module only re-exports it. The "path-name归位" the card imagined is a
no-op here — the seam is the value.
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
