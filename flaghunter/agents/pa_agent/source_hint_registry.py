"""Local source-hint registry accessors, extracted from ctf_dispatcher.

Twenty-second P5 cut (closeout phase): a physically-contiguous, cohesive
cluster of eight read/write accessors over the dispatcher's
``local_challenge_source_hint`` state observations (originally ctf_dispatcher
lines ~897-1069). Methods are pure relocations; ``self.*`` resolves at runtime
via the dispatcher's MRO, so call sites are unchanged.
"""

from __future__ import annotations

import re
from pathlib import Path
from urllib.parse import urlparse

from .dispatcher_helpers import _looks_like_inline_source_leak

# only-this-cluster constant, moved here with the cluster (was ctf_dispatcher top)
_SOURCE_HINT_BACKUP_PROBES = {
    "app.py": ("/app.py.bak", "/app.py~", "/app.py.swp"),
    "index.php": ("/index.php.bak", "/index.php~", "/index.phps"),
    "package.json": ("/package.json.bak", "/package.json~"),
    "requirements.txt": ("/requirements.txt.bak", "/requirements.txt~"),
    "README.md": ("/README.md.bak", "/README.md~"),
}



class SourceHintRegistryMixin:
    """Read/write accessors over local_challenge_source_hint observations."""

    def _has_recent_local_source_hint(self, *, limit: int = 6) -> bool:
        if self.state is None:
            return False
        return bool(
            self.state.recent_observations(
                "local_challenge_source_hint",
                limit=limit,
            )
        )

    def _recent_local_source_hint_count(self, *, limit: int = 12) -> int:
        if self.state is None:
            return 0
        return len(
            self.state.recent_observations(
                "local_challenge_source_hint",
                limit=limit,
            )
        )

    def _recent_source_hint_backup_probe_paths(self, *, limit: int = 6) -> list[str]:
        if self.state is None:
            return []

        discovered_names: list[str] = []
        seen_names: set[str] = set()
        for observation in self.state.recent_observations(
            "local_challenge_source_hint",
            limit=limit,
        ):
            metadata = getattr(observation, "metadata", None)
            file_name = ""
            if isinstance(metadata, dict):
                file_name = str(metadata.get("file_name") or "").strip()
                if not file_name:
                    path_value = str(metadata.get("path") or "").strip()
                    if path_value:
                        file_name = Path(path_value).name
            if not file_name:
                value = str(getattr(observation, "value", "") or "")
                match = re.match(r"([A-Za-z0-9_.-]+):", value.strip())
                if match:
                    file_name = match.group(1).strip()
            if file_name and file_name not in seen_names:
                seen_names.add(file_name)
                discovered_names.append(file_name)

        probe_paths: list[str] = []
        seen_paths: set[str] = set()
        for name in discovered_names:
            for rel_path in _SOURCE_HINT_BACKUP_PROBES.get(name, ()):
                if rel_path not in seen_paths:
                    seen_paths.add(rel_path)
                    probe_paths.append(rel_path)
        return probe_paths

    def _recent_local_source_hint_text(self, *, limit: int = 6) -> str:
        if self.state is None:
            return ""
        return "\n".join(
            str(getattr(observation, "value", "") or "")
            for observation in self.state.recent_observations(
                "local_challenge_source_hint",
                limit=limit,
            )
        )

    def _recent_local_source_hint_routes(self, *, limit: int = 6) -> set[str]:
        text = self._recent_local_source_hint_text(limit=limit)
        if not text:
            return set()
        routes: set[str] = set()
        for match in re.findall(r"['\"](\/[A-Za-z0-9_./-]+)['\"]", text):
            normalized = str(match or "").strip()
            if normalized.startswith("/"):
                routes.add(normalized)
        return routes

    def _recent_local_source_hint_secret_candidates(self, *, limit: int = 6) -> list[str]:
        text = self._recent_local_source_hint_text(limit=limit)
        if not text:
            return []
        candidates: list[str] = []
        patterns = (
            r"(?i)(?:jwt_secret|secret_key|token_secret|signing_secret)\s*[:=]\s*['\"]([^'\"]+)['\"]",
            r"(?i)(?:jwt_secret|secret_key|token_secret|signing_secret)\s*[:=]\s*([A-Za-z0-9_.:/@\-]{6,})",
        )
        for pattern in patterns:
            for match in re.findall(pattern, text):
                value = str(match or "").strip()
                if value:
                    candidates.append(value)
        ordered: list[str] = []
        seen: set[str] = set()
        for item in candidates:
            if item not in seen:
                seen.add(item)
                ordered.append(item)
        return ordered

    def _looks_like_source_code_blob(self, text: str) -> bool:
        blob = str(text or "").strip()
        if not blob:
            return False
        if _looks_like_inline_source_leak(blob):
            return True
        lowered = blob.lower()
        strong_markers = (
            "<?php",
            "$_get",
            "$_post",
            "shell_exec(",
            "highlight_file(",
            "@app.route(",
            "from flask import",
            "express(",
            "app.get(",
            "app.post(",
        )
        if any(marker in lowered for marker in strong_markers):
            return True
        if ("def " in lowered and "import " in lowered) or ("class " in lowered and "function " in lowered):
            return True
        return False

    def _register_runtime_source_hint(
        self,
        text: str,
        hint_path: str,
        *,
        evidence_source: str,
        max_chars: int = 1600,
    ) -> bool:
        if self.state is None:
            return False
        if not self._looks_like_source_code_blob(text):
            return False

        normalized_path = str(hint_path or "").strip()
        parsed = urlparse(normalized_path)
        candidate_name = Path(parsed.path).name if parsed.path else ""
        if not candidate_name and parsed.netloc:
            candidate_name = parsed.netloc
        file_name = candidate_name or "runtime_source"

        snippet = str(text or "").strip()
        if len(snippet) > max_chars:
            snippet = snippet[: max_chars - 3].rstrip() + "..."
        value = f"{file_name}: {snippet}"

        for observation in reversed(
            self.state.recent_observations(
                "local_challenge_source_hint",
                limit=12,
            )
        ):
            if str(getattr(observation, "value", "") or "").strip() == value:
                return False
            metadata = getattr(observation, "metadata", None)
            if isinstance(metadata, dict) and str(metadata.get("path") or "").strip() == normalized_path:
                return False

        self.state.add_observation(
            "local_challenge_source_hint",
            value,
            source="runtime_source_leak",
            metadata={
                "path": normalized_path,
                "file_name": file_name,
                "evidence_source": evidence_source,
            },
        )
        return True

