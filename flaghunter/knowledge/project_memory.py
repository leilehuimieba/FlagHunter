"""Project-level pentest knowledge loader.

Loads METHODOLOGY.md, target profiles, and strategy-memory learned rules.
Injects structured context into agent system prompts via get_context_for_prompt().
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any


@dataclass
class ProjectContext:
    methodology: str = ""
    target_profiles: dict[str, dict[str, Any]] = field(default_factory=dict)
    learned_rules: list[str] = field(default_factory=list)


def _find_project_root() -> Path:
    """Walk upward from this file to find the project root (where pyproject.toml lives)."""
    candidate = Path(__file__).resolve().parent.parent
    for _ in range(4):
        if (candidate / "pyproject.toml").exists():
            return candidate
        candidate = candidate.parent
    return Path.cwd()


class ProjectMemory:
    """Loads project-level pentest knowledge and injects into system prompts."""

    def __init__(self, project_root: Path | None = None):
        self._root = Path(project_root) if project_root else _find_project_root()
        self._context = ProjectContext()
        self._refresh()

    def _refresh(self) -> None:
        self._context.methodology = self.load_methodology()
        self._context.learned_rules = self._load_learned_rules()

    def load_methodology(self) -> str:
        """Read METHODOLOGY.md from project root. Returns empty string if absent."""
        path = self._root / "METHODOLOGY.md"
        if not path.exists():
            return ""
        try:
            text = path.read_text(encoding="utf-8")
            return text[:2000] if len(text) > 2000 else text
        except OSError:
            return ""

    @staticmethod
    def _safe_filename(name: str) -> str:
        safe = name.replace("\\", "_").replace("/", "_").replace(":", "_")
        while ".." in safe:
            safe = safe.replace("..", "_")
        safe = safe.strip("._") or "unknown"
        return safe[:120]

    def load_target_profile(self, target: str) -> dict[str, Any]:
        """Load target-specific profile from loot/target_profiles/{target}.json."""
        profile_dir = self._root / "loot" / "target_profiles"
        safe_name = self._safe_filename(target)
        path = profile_dir / f"{safe_name}.json"
        if not path.exists():
            return {}
        try:
            return json.loads(path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            return {}

    def save_target_profile(self, target: str, profile: dict[str, Any]) -> None:
        """Persist a target profile for future sessions."""
        profile_dir = self._root / "loot" / "target_profiles"
        profile_dir.mkdir(parents=True, exist_ok=True)
        safe_name = self._safe_filename(target)
        path = profile_dir / f"{safe_name}.json"
        path.write_text(json.dumps(profile, indent=2, ensure_ascii=False), encoding="utf-8")

    def _load_learned_rules(self) -> list[str]:
        """Extract learned rules from strategy memory store.

        The writer (StrategyMemoryStore.save) appends JSONL — one entry dict
        per line. Parse line-by-line so a multi-line file is read correctly,
        while staying tolerant of a legacy single-blob file (a JSON list, or a
        wrapper dict with an ``entries`` key).
        """
        rules: list[str] = []
        sm_path = self._root / "loot" / "strategy_memory.json"
        if not sm_path.exists():
            return rules
        try:
            text = sm_path.read_text(encoding="utf-8")
        except OSError:
            return rules

        entries: list[Any] = []
        for line in text.splitlines():
            line = line.strip()
            if not line:
                continue
            try:
                parsed = json.loads(line)
            except json.JSONDecodeError:
                continue
            if isinstance(parsed, list):
                # Legacy single-blob: a JSON array of entry dicts.
                entries.extend(parsed)
            elif isinstance(parsed, dict) and isinstance(parsed.get("entries"), list):
                # Legacy wrapper: {"entries": [...]}.
                entries.extend(parsed["entries"])
            else:
                # JSONL path: a bare entry dict.
                entries.append(parsed)

        for entry in entries[-5:]:
            if not isinstance(entry, dict):
                continue
            for rule in entry.get("learned_rules", []):
                if rule and rule not in rules:
                    rules.append(rule)
        return rules[-5:]

    def get_context_for_prompt(self, target: str = "", phase: str = "") -> str:
        """Assemble a context fragment for system-prompt injection (≤600 chars)."""
        parts: list[str] = []

        if target:
            parts.append(f"Target: {target}")
            profile = self.load_target_profile(target)
            if profile:
                known = profile.get("known_services", [])
                if known:
                    parts.append(f"Known services: {', '.join(str(s) for s in known[:5])}")
                notes_field = profile.get("notes", "")
                if notes_field:
                    parts.append(str(notes_field)[:150])

        if self._context.methodology:
            parts.append("[Methodology]\n" + self._context.methodology[:300])

        if self._context.learned_rules:
            rules_text = "\n".join(f"- {r}" for r in self._context.learned_rules[:3])
            parts.append(f"[Learned Rules]\n{rules_text}")

        if phase:
            parts.append(f"Current phase: {phase}")

        result = "\n\n".join(parts)
        return result[:800] if len(result) > 800 else result
