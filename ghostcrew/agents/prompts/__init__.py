"""Prompt templates for GhostCrew agents."""

from pathlib import Path

from jinja2 import Template

PROMPTS_DIR = Path(__file__).parent


def load_prompt(name: str) -> Template:
    """Load a prompt template by name.

    Args:
        name: Prompt name without extension (e.g., 'ghost_agent', 'ghost_assist')

    Returns:
        Jinja2 Template object
    """
    path = PROMPTS_DIR / f"{name}.jinja"
    return Template(path.read_text(encoding="utf-8"))


# Pre-loaded templates for convenience
ghost_agent = load_prompt("ghost_agent")
ghost_assist = load_prompt("ghost_assist")
ghost_crew = load_prompt("ghost_crew")
