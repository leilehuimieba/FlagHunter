"""Guard tests for flaghunter.playbooks.base_playbook.

Regression: BasePlaybook used dataclasses.field(default_factory=list) for
`phases` despite NOT being a @dataclass, so the class attribute was a
dataclasses.Field object. Any subclass that did NOT override `phases` would
iterate that Field object in get_task() and crash.
"""

from flaghunter.playbooks import get_playbook, list_playbooks
from flaghunter.playbooks.base_playbook import BasePlaybook, Phase


class _BarePlaybook(BasePlaybook):
    """A playbook that deliberately does NOT override `phases`."""

    name = "_bare_test_playbook"
    description = "Bare playbook for regression test"


def test_phases_default_is_a_real_list_not_a_field():
    # The default must be an actual iterable list, not a dataclasses.Field.
    assert isinstance(BasePlaybook.phases, list)
    assert BasePlaybook.phases == []


def test_get_task_does_not_crash_without_phases_override():
    pb = _BarePlaybook()
    # Must not raise (previously iterated a Field object and crashed).
    task = pb.get_task()
    # With no phases, output is just the description block, no "Phase:" lines.
    assert task == f"{pb.description}\n\n"
    assert "Phase:" not in task


def test_get_task_renders_overridden_phases():
    class _WithPhases(BasePlaybook):
        name = "_with_phases_test"
        description = "Has phases"
        phases = [
            Phase(name="Recon", objective="Map surface", techniques=["enum", "scan"])
        ]

    task = _WithPhases().get_task()
    assert "Phase: Recon" in task
    assert "Objective: Map surface" in task
    assert "  1. enum" in task
    assert "  2. scan" in task


def test_existing_playbooks_still_resolve():
    # Smoke: discovery + get_playbook still work and produce non-trivial tasks.
    names = list_playbooks()
    for name in ("thp3_web", "thp3_recon", "thp3_network"):
        assert name in names
        task = get_playbook(name).get_task()
        assert "Phase:" in task
