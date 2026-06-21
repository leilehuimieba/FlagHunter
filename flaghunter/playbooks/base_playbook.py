from dataclasses import dataclass
from typing import List


@dataclass
class Phase:
    name: str
    objective: str
    techniques: List[str]


class BasePlaybook:
    """Base class for all playbooks."""

    name: str = "base_playbook"
    description: str = "Base playbook description"
    mode: str = "agent"  # "agent" or "crew"
    max_loops: int = 50
    # BasePlaybook is a plain class (not a @dataclass), so dataclasses.field()
    # cannot be used here — it would leave `phases` bound to a Field object that
    # get_task() then tries to iterate. Concrete playbooks override this with their
    # own list; get_task() only reads it, so the shared default is never mutated.
    phases: List[Phase] = []

    def get_task(self) -> str:
        """Convert playbook into a structured task description."""
        task = f"{self.description}\n\n"

        for phase in self.phases:
            task += f"Phase: {phase.name}\n"
            task += f"Objective: {phase.objective}\n"
            task += "Techniques:\n"
            for i, technique in enumerate(phase.techniques, 1):
                task += f"  {i}. {technique}\n"
            task += "\n"

        return task
