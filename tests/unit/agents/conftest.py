"""Test fixtures scoped to ``tests/unit/agents``.

Isolates the audit stores' default loot base dir per test (cf. L3g).
"""

from pathlib import Path

import pytest

from flaghunter.agents.pa_agent import audit_infra


@pytest.fixture(autouse=True)
def _isolate_audit_loot_root(tmp_path):
    """Redirect root-less audit-store constructions into a tmp dir.

    Many ``await dispatcher.run(...)`` calls in these tests omit ``ledger_root``
    (and the sibling ``*_root`` kwargs), so ``AuditStore.build_*`` falls back to
    the process-level default loot base dir. By default that is ``Path("loot")``,
    which makes those calls write ``ctf-<uuid>.jsonl`` into the **real** loot
    tree — intermittently tripping
    ``test_replay_does_not_touch_real_loot_stores`` when the whole suite runs in
    one process. Point the default at ``tmp_path`` for the duration of each test
    and restore ``Path("loot")`` in teardown so no global state leaks to other
    tests. Tests that pass explicit ``*_root`` kwargs are unaffected.
    """
    previous = audit_infra.get_default_loot_root()
    audit_infra.set_default_loot_root(tmp_path / "loot")
    try:
        yield
    finally:
        audit_infra.set_default_loot_root(previous)
