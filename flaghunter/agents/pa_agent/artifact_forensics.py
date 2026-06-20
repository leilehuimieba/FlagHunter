"""Artifact / attachment forensics strategy executor.

P5 / nineteenth cut: the artifact-forensics cluster (6 methods, ~810 lines)
is physically moved out of CTFTaskDispatcher into a behaviour-preserving
mixin — the misc/forensics attachment strategy, candidate collection,
local-challenge artifact ingestion, directory-page candidate expansion,
attachment research-context gathering, and the per-artifact analyzer that
runs an out-of-process zip/sqlite/base64 forensic script.

One only-this-cluster constant travels with the cluster: ``_ATTACHMENT_CLUE_RE``
(used solely by ``_expand_artifact_candidates_from_directory_pages``) moves
into this module and is deleted from the top of ctf_dispatcher.py. Every
other module-level symbol is already exported from acyclic
``dispatcher_helpers`` (``_base_target``, ``_normalize_exploration_url``,
``_resolve_compose_file``, ``_iter_local_challenge_key_files``,
``_build_local_challenge_root_summary_metadata``,
``_extract_local_challenge_root_from_local_archive``, ``_pick_python_command``)
plus ``_ChainOutcome`` (chains.base) and stdlib.

Nested-def audit: ``add_flag`` / ``scan_text`` / ``scan_bytes`` /
``analyze_sqlite_bytes`` live inside the embedded analysis ``script = r\"\"\"..."``
string literal (remote code, not real Python); the only genuine inner
function is ``_add`` in ``_collect_artifact_candidates``, which uses only
``_normalize_exploration_url`` plus closure locals. The ~810-line block was
extracted from source by script and py_compile-verified before deletion.

All ``self.*`` access resolves via the MRO of the dispatcher that mixes this
in: ``_register_artifact_record`` (AuditInfraMixin), ``_extract_flag``
(FlagParserMixin), ``_observe_flag`` (FlagObserverMixin), ``_store_note``
(NoteStoreMixin), and the dispatcher-resident ``_scan_and_store`` /
``_extract_embedded_links`` / ``_ingest_discovered_links``. Method-local
imports (``shlex`` / ``subprocess`` / ``tempfile``, plus the knowledge-search
/ ctf-hint-searcher dynamic imports) stay inline. Call sites unchanged. Pure
code relocation, near-zero risk.
"""

from __future__ import annotations

import json
import os
import re
from pathlib import Path
from typing import Any
from urllib.parse import urljoin, urlparse

from .chains.base import _ChainOutcome
from .dispatcher_helpers import (
    _base_target,
    _build_local_challenge_root_summary_metadata,
    _extract_local_challenge_root_from_local_archive,
    _iter_local_challenge_key_files,
    _normalize_exploration_url,
    _pick_python_command,
    _resolve_compose_file,
)

_ATTACHMENT_CLUE_RE = re.compile(
    r"(sqlite|\.db\b|\.sqlite\b|\.sqlite3\b|\.wal\b|write-ahead log|forensics|附件|压缩包|archive|directory listing)",
    re.IGNORECASE,
)


class ArtifactForensicsMixin:
    """Attachment/artifact forensics: discovery, local ingestion and out-of-process analysis."""

    async def _run_artifact_forensics_strategy(
        self,
        target: str,
        page_features: dict[str, Any],
        hint: str,
    ) -> _ChainOutcome:
        self.tool_guard.require(["http_request", "terminal"])

        candidates = self._collect_artifact_candidates(target, page_features)
        candidates = await self._expand_artifact_candidates_from_directory_pages(
            target=target,
            page_features=page_features,
            candidates=candidates,
        )
        if not candidates:
            return _ChainOutcome(progress=False, reason="artifact_forensics: no candidate attachments discovered")

        await self._collect_attachment_research_context(
            target=target,
            page_features=page_features,
            candidates=candidates,
            hint=hint,
        )

        progress = False
        reasons: list[str] = []
        for artifact_url in candidates[:12]:
            analysis = await self._analyze_attachment_artifact(artifact_url, target)
            progress = progress or analysis.progress
            if analysis.flag:
                return analysis
            if analysis.reason:
                reasons.append(analysis.reason)

        return _ChainOutcome(progress=progress, reason="; ".join(dict.fromkeys(reasons[:6])) or "artifact_forensics exhausted")

    def _collect_artifact_candidates(
        self,
        target: str,
        page_features: dict[str, Any],
    ) -> list[str]:
        base = _base_target(target)
        candidates: list[str] = []
        seen: set[str] = set()

        def _add(url: str) -> None:
            absolute = _normalize_exploration_url(str(url or "").strip())
            if not absolute:
                return
            lowered = absolute.lower()
            if not any(
                token in lowered
                for token in (
                    ".zip",
                    ".tar.gz",
                    ".tgz",
                    ".tar",
                    ".gz",
                    ".db",
                    ".sqlite",
                    ".sqlite3",
                    ".wal",
                    ".pcap",
                    ".cap",
                    ".7z",
                    ".rar",
                )
            ):
                return
            if absolute in seen:
                return
            seen.add(absolute)
            candidates.append(absolute)

        for raw in list(page_features.get("raw_links") or []):
            _add(str(raw))

        for rel_path in (
            "/challenge.zip",
            "/attachments.zip",
            "/source.zip",
            "/backup.zip",
            "/www.zip",
            "/app.db",
            "/app.db-wal",
        ):
            _add(urljoin(base + "/", rel_path.lstrip("/")))

        for artifact_path in (self._challenge_context or {}).get("artifactPaths") or []:
            path_value = str(artifact_path or "").strip()
            if not path_value:
                continue
            try:
                absolute_path = Path(path_value).resolve()
            except Exception:
                continue
            if not absolute_path.exists() or not absolute_path.is_file():
                continue
            _add(absolute_path.as_uri())

        return candidates

    def _ingest_local_challenge_artifacts(self, target: str) -> None:
        if self.state is None:
            return
        if self._local_challenge_artifacts_loaded:
            return

        target_label = urlparse(target).netloc or target
        challenge_path_value = str((self._challenge_context or {}).get("challengePath") or "").strip()
        if challenge_path_value:
            challenge_path = Path(challenge_path_value)
            if challenge_path.exists() and challenge_path.is_dir():
                challenge_artifact = self.state.add_artifact(
                    challenge_path.name or challenge_path_value,
                    location=str(challenge_path),
                    source="local_challenge_context",
                    metadata={
                        "target": target_label,
                        "kind": "challenge_path_root",
                    },
                )
                self._register_artifact_record(
                    kind="local_challenge_root",
                    title=challenge_path.name or challenge_path_value,
                    path=str(challenge_path),
                    location=str(challenge_path),
                    producer="local_challenge_context",
                    metadata={
                        "target": target_label,
                        "kind": "challenge_path_root",
                    },
                )
                self.state.add_observation(
                    "local_challenge_root",
                    str(challenge_path),
                    source="local_challenge_context",
                    metadata={
                        "artifact_name": challenge_artifact.name,
                        "target": target_label,
                    },
                )
                compose_file = _resolve_compose_file(challenge_path)
                if compose_file is not None and compose_file.exists() and compose_file.is_file():
                    compose_artifact = self.state.add_artifact(
                        compose_file.name or str(compose_file),
                        location=str(compose_file),
                        source="local_challenge_context",
                        metadata={
                            "target": target_label,
                            "kind": "challenge_compose_file",
                            "source_root_path": str(challenge_path),
                        },
                    )
                    self._register_artifact_record(
                        kind="local_challenge_compose_file",
                        title=compose_file.name or str(compose_file),
                        path=str(compose_file),
                        location=str(compose_file),
                        producer="local_challenge_context",
                        metadata={
                            "target": target_label,
                            "kind": "challenge_compose_file",
                            "source_root_path": str(challenge_path),
                        },
                    )
                    self.state.add_observation(
                        "local_challenge_compose_file",
                        str(compose_file),
                        source="local_challenge_context",
                        metadata={
                            "artifact_name": compose_artifact.name,
                            "target": target_label,
                            "source_root_path": str(challenge_path),
                        },
                    )
                for key_file in _iter_local_challenge_key_files(challenge_path):
                    key_artifact = self.state.add_artifact(
                        key_file.name or str(key_file),
                        location=str(key_file),
                        source="local_challenge_context",
                        metadata={
                            "target": target_label,
                            "kind": "challenge_key_file",
                            "source_root_path": str(challenge_path),
                        },
                    )
                    self._register_artifact_record(
                        kind="local_challenge_key_file",
                        title=key_file.name or str(key_file),
                        path=str(key_file),
                        location=str(key_file),
                        producer="local_challenge_context",
                        metadata={
                            "target": target_label,
                            "kind": "challenge_key_file",
                            "source_root_path": str(challenge_path),
                        },
                    )
                    self.state.add_observation(
                        "local_challenge_key_file",
                        str(key_file),
                        source="local_challenge_context",
                        metadata={
                            "artifact_name": key_artifact.name,
                            "target": target_label,
                            "source_root_path": str(challenge_path),
                        },
                    )
                summary_metadata = _build_local_challenge_root_summary_metadata(challenge_path)
                summary_artifact = self.state.add_artifact(
                    f"{challenge_path.name or challenge_path_value} summary",
                    location=str(challenge_path),
                    source="local_challenge_context",
                    metadata={
                        "target": target_label,
                        "kind": "challenge_root_summary",
                        **summary_metadata,
                    },
                )
                self._register_artifact_record(
                    kind="local_challenge_root_summary",
                    title=f"{challenge_path.name or challenge_path_value} summary",
                    path=str(challenge_path),
                    location=str(challenge_path),
                    producer="local_challenge_context",
                    metadata={
                        "target": target_label,
                        "kind": "challenge_root_summary",
                        **summary_metadata,
                    },
                )
                self.state.add_observation(
                    "local_challenge_root_summary",
                    str(challenge_path),
                    source="local_challenge_context",
                    metadata={
                        "artifact_name": summary_artifact.name,
                        "target": target_label,
                        **summary_metadata,
                    },
                )

        artifact_paths = list((self._challenge_context or {}).get("artifactPaths") or [])
        if not artifact_paths:
            return

        for artifact_path in artifact_paths:
            path_value = str(artifact_path or "").strip()
            if not path_value:
                continue
            path = Path(path_value)
            artifact = self.state.add_artifact(
                path.name or path_value,
                location=str(path),
                source="local_challenge_context",
                metadata={
                    "target": target_label,
                    "kind": "local_artifact_path",
                },
            )
            self._register_artifact_record(
                kind="local_challenge_artifact",
                title=path.name or path_value,
                path=str(path),
                location=str(path),
                producer="local_challenge_context",
                metadata={
                    "target": target_label,
                    "kind": "local_artifact_path",
                },
            )
            self.state.add_observation(
                "local_challenge_artifact",
                str(path),
                source="local_challenge_context",
                metadata={
                    "artifact_name": artifact.name,
                    "target": target_label,
                },
            )
            extracted_root = _extract_local_challenge_root_from_local_archive(path)
            if extracted_root is not None and extracted_root.exists() and extracted_root.is_dir():
                extracted_artifact = self.state.add_artifact(
                    extracted_root.name or str(extracted_root),
                    location=str(extracted_root),
                    source="local_challenge_context",
                    metadata={
                        "target": target_label,
                        "kind": "extracted_challenge_root",
                        "source_artifact_path": str(path),
                    },
                )
                self._register_artifact_record(
                    kind="local_challenge_extracted_root",
                    title=extracted_root.name or str(extracted_root),
                    path=str(extracted_root),
                    location=str(extracted_root),
                    producer="local_challenge_context",
                    metadata={
                        "target": target_label,
                        "kind": "extracted_challenge_root",
                        "source_artifact_path": str(path),
                    },
                )
                self.state.add_observation(
                    "local_challenge_extracted_root",
                    str(extracted_root),
                    source="local_challenge_context",
                    metadata={
                        "artifact_name": extracted_artifact.name,
                        "target": target_label,
                        "source_artifact_path": str(path),
                    },
                )
                compose_file = _resolve_compose_file(extracted_root)
                if compose_file is not None and compose_file.exists() and compose_file.is_file():
                    compose_artifact = self.state.add_artifact(
                        compose_file.name or str(compose_file),
                        location=str(compose_file),
                        source="local_challenge_context",
                        metadata={
                            "target": target_label,
                            "kind": "challenge_compose_file",
                            "source_root_path": str(extracted_root),
                            "source_artifact_path": str(path),
                        },
                    )
                    self._register_artifact_record(
                        kind="local_challenge_compose_file",
                        title=compose_file.name or str(compose_file),
                        path=str(compose_file),
                        location=str(compose_file),
                        producer="local_challenge_context",
                        metadata={
                            "target": target_label,
                            "kind": "challenge_compose_file",
                            "source_root_path": str(extracted_root),
                            "source_artifact_path": str(path),
                        },
                    )
                    self.state.add_observation(
                        "local_challenge_compose_file",
                        str(compose_file),
                        source="local_challenge_context",
                        metadata={
                            "artifact_name": compose_artifact.name,
                            "target": target_label,
                            "source_root_path": str(extracted_root),
                            "source_artifact_path": str(path),
                        },
                    )
                for key_file in _iter_local_challenge_key_files(extracted_root):
                    key_artifact = self.state.add_artifact(
                        key_file.name or str(key_file),
                        location=str(key_file),
                        source="local_challenge_context",
                        metadata={
                            "target": target_label,
                            "kind": "challenge_key_file",
                            "source_root_path": str(extracted_root),
                            "source_artifact_path": str(path),
                        },
                    )
                    self._register_artifact_record(
                        kind="local_challenge_key_file",
                        title=key_file.name or str(key_file),
                        path=str(key_file),
                        location=str(key_file),
                        producer="local_challenge_context",
                        metadata={
                            "target": target_label,
                            "kind": "challenge_key_file",
                            "source_root_path": str(extracted_root),
                            "source_artifact_path": str(path),
                        },
                    )
                    self.state.add_observation(
                        "local_challenge_key_file",
                        str(key_file),
                        source="local_challenge_context",
                        metadata={
                            "artifact_name": key_artifact.name,
                            "target": target_label,
                            "source_root_path": str(extracted_root),
                            "source_artifact_path": str(path),
                        },
                    )
                summary_metadata = _build_local_challenge_root_summary_metadata(extracted_root)
                summary_artifact = self.state.add_artifact(
                    f"{extracted_root.name or str(extracted_root)} summary",
                    location=str(extracted_root),
                    source="local_challenge_context",
                    metadata={
                        "target": target_label,
                        "kind": "challenge_root_summary",
                        "source_artifact_path": str(path),
                        **summary_metadata,
                    },
                )
                self._register_artifact_record(
                    kind="local_challenge_root_summary",
                    title=f"{extracted_root.name or str(extracted_root)} summary",
                    path=str(extracted_root),
                    location=str(extracted_root),
                    producer="local_challenge_context",
                    metadata={
                        "target": target_label,
                        "kind": "challenge_root_summary",
                        "source_artifact_path": str(path),
                        **summary_metadata,
                    },
                )
                self.state.add_observation(
                    "local_challenge_root_summary",
                    str(extracted_root),
                    source="local_challenge_context",
                    metadata={
                        "artifact_name": summary_artifact.name,
                        "target": target_label,
                        "source_artifact_path": str(path),
                        **summary_metadata,
                    },
                )
        self._local_challenge_artifacts_loaded = True

    async def _expand_artifact_candidates_from_directory_pages(
        self,
        *,
        target: str,
        page_features: dict[str, Any],
        candidates: list[str],
    ) -> list[str]:
        if self.runtime is None or not hasattr(self.runtime, "proxy_action"):
            return candidates

        expanded = list(candidates)
        seen_candidates = set(expanded)
        seen_dirs: set[str] = set()
        queue: list[tuple[str, int]] = []

        current_url = str(page_features.get("url") or target or "").strip()
        current_blob = (
            str(page_features.get("html") or "")
            + "\n"
            + str(page_features.get("content") or "")
        )
        if _ATTACHMENT_CLUE_RE.search(current_blob) and current_url.endswith("/"):
            queue.append((current_url, 0))

        for raw in list(page_features.get("raw_links") or []):
            absolute = _normalize_exploration_url(str(raw or "").strip())
            if not absolute or not absolute.endswith("/"):
                continue
            queue.append((absolute, 0))

        while queue:
            directory_url, depth = queue.pop(0)
            if directory_url in seen_dirs or depth > 1:
                continue
            seen_dirs.add(directory_url)
            try:
                resp = await self.runtime.proxy_action(
                    "get",
                    url=directory_url,
                    timeout=12,
                )
            except Exception:
                continue
            if not isinstance(resp, dict) or resp.get("error"):
                continue
            if int(resp.get("status_code") or 0) != 200:
                continue

            body = str(resp.get("body") or "")
            if not body:
                continue
            links = self._extract_embedded_links(body, directory_url)
            if links:
                self._ingest_discovered_links(
                    links,
                    page_features=page_features,
                    discovery_source="artifact_directory_listing",
                )
            for link in links:
                lowered = link.lower()
                if link.endswith("/") and depth < 1:
                    queue.append((link, depth + 1))
                    continue
                if not any(
                    token in lowered
                    for token in (
                        ".zip",
                        ".tar.gz",
                        ".tgz",
                        ".tar",
                        ".gz",
                        ".db",
                        ".sqlite",
                        ".sqlite3",
                        ".wal",
                        ".pcap",
                        ".cap",
                        ".7z",
                        ".rar",
                    )
                ):
                    continue
                if link in seen_candidates:
                    continue
                seen_candidates.add(link)
                expanded.append(link)

        return expanded

    async def _collect_attachment_research_context(
        self,
        *,
        target: str,
        page_features: dict[str, Any],
        candidates: list[str],
        hint: str,
    ) -> None:
        if self.state is None:
            return

        challenge_summary = " ".join(
            part
            for part in [
                str(page_features.get("content") or "")[:500],
                str(page_features.get("html") or "")[:500],
                " ".join(candidates[:6]),
                str(hint or ""),
            ]
            if part
        ).strip()
        if not challenge_summary:
            return

        try:
            from ...tools.knowledge_search import knowledge_search as _knowledge_search

            knowledge_result = await _knowledge_search(
                {
                    "query": f"CTF misc forensics attachment analysis {challenge_summary[:200]}",
                    "k": 3,
                    "threshold": 0.25,
                    "max_tokens": 1000,
                },
                self.runtime,
            )
            if knowledge_result and not str(knowledge_result).lower().startswith("knowledge search failed"):
                self.state.add_observation(
                    "knowledge_hint",
                    str(knowledge_result)[:1200],
                    source="knowledge_search",
                    metadata={"target": target, "category": "artifact_forensics"},
                )
        except Exception:
            pass

        try:
            from ...knowledge.ctf_hint_searcher import search_ctf_hints

            if self.llm is not None:
                hints = await search_ctf_hints("misc", challenge_summary[:220], self.llm, max_results=2)
                if hints:
                    self.state.add_observation(
                        "web_search_hint",
                        " | ".join(hints[:5]),
                        source="ctf_hint_searcher",
                        metadata={"target": target, "category": "artifact_forensics"},
                    )
        except Exception:
            pass

    async def _analyze_attachment_artifact(
        self,
        artifact_url: str,
        target: str,
    ) -> _ChainOutcome:
        import shlex
        import subprocess
        import tempfile

        python_cmd = _pick_python_command(self.runtime)
        script = r"""
import base64, binascii, io, json, os, re, sqlite3, sys, tempfile, urllib.request, zipfile

url = sys.argv[1]
flag_re = re.compile(r'([A-Za-z][A-Za-z0-9_]{1,20}\{[A-Za-z0-9_!@#$%^&*+=:.,?\-]{3,200}\})')
part_re = re.compile(r'part[:\s_\-]*0*(\d+).*?\[([A-Za-z0-9+/=]{4,})\]', re.IGNORECASE)
b64_re = re.compile(r'(?<![A-Za-z0-9+/=])([A-Za-z0-9+/]{8,}={0,2})(?![A-Za-z0-9+/=])')

data = urllib.request.urlopen(url, timeout=8).read()
result = {
    "url": url,
    "kind": "raw",
    "entries": [],
    "interesting": [],
    "flags": [],
    "decoded_hits": [],
    "part_fragments": [],
    "table_samples": [],
}

seen_flags = set()

def add_flag(candidate):
    candidate = str(candidate or "").strip()
    if candidate and candidate not in seen_flags:
        seen_flags.add(candidate)
        result["flags"].append(candidate)

def scan_text(name, text):
    if not text:
        return
    for match in flag_re.finditer(text):
        add_flag(match.group(1))
    for index, blob in part_re.findall(text):
        result["part_fragments"].append({"index": int(index), "blob": blob, "name": name})
    for blob in b64_re.findall(text):
        if len(blob) < 12:
            continue
        try:
            decoded = base64.b64decode(blob + "=" * ((4 - len(blob) % 4) % 4), validate=False)
        except Exception:
            continue
        decoded_text = decoded.decode("utf-8", errors="ignore")
        for match in flag_re.finditer(decoded_text):
            add_flag(match.group(1))
            result["decoded_hits"].append({"name": name, "source": blob[:48], "decoded": decoded_text[:180]})

def scan_bytes(name, raw):
    if raw is None:
        return
    text = raw.decode("utf-8", errors="ignore")
    if not text:
        text = raw.decode("latin-1", errors="ignore")
    scan_text(name, text)

def analyze_sqlite_bytes(name, raw):
    fd, path = tempfile.mkstemp(suffix=".db")
    os.close(fd)
    try:
        with open(path, "wb") as handle:
            handle.write(raw)
        conn = None
        try:
            conn = sqlite3.connect(path)
            cur = conn.cursor()
            tables = [row[0] for row in cur.execute("select name from sqlite_master where type='table' order by name").fetchall()]
            result["table_samples"].append({"name": name, "tables": tables[:10]})
            for table in tables[:8]:
                try:
                    rows = cur.execute(f"select * from \"{table}\" limit 8").fetchall()
                except Exception:
                    continue
                joined = "\n".join(" | ".join("" if item is None else str(item) for item in row) for row in rows)
                scan_text(f"{name}:{table}", joined)
        except Exception as exc:
            result["table_samples"].append({"name": name, "error": str(exc)[:160]})
        finally:
            if conn is not None:
                conn.close()
    finally:
        try:
            os.remove(path)
        except Exception:
            pass

scan_bytes(url, data)

if zipfile.is_zipfile(io.BytesIO(data)):
    result["kind"] = "zip"
    with zipfile.ZipFile(io.BytesIO(data)) as zf:
        for info in zf.infolist():
            result["entries"].append(info.filename)
            if info.is_dir() or info.file_size > 1048576:
                continue
            raw = zf.read(info.filename)
            lowered = info.filename.lower()
            if any(token in lowered for token in (".db", ".sqlite", ".sqlite3", ".wal", ".txt", ".log", ".md", ".php", ".env", ".bak")):
                result["interesting"].append(info.filename)
            scan_bytes(info.filename, raw)
            if lowered.endswith((".db", ".sqlite", ".sqlite3")):
                analyze_sqlite_bytes(info.filename, raw)
else:
    lowered_url = url.lower()
    if lowered_url.endswith((".db", ".sqlite", ".sqlite3")):
        result["kind"] = "sqlite"
        analyze_sqlite_bytes(url, data)
    elif lowered_url.endswith(".wal"):
        result["kind"] = "wal"

if result["part_fragments"]:
    ordered = []
    seen_indexes = set()
    for item in sorted(result["part_fragments"], key=lambda item: item["index"]):
        idx = int(item["index"])
        if idx in seen_indexes:
            continue
        seen_indexes.add(idx)
        ordered.append(item["blob"])
    joined = "".join(ordered)
    try:
        decoded = base64.b64decode(joined + "=" * ((4 - len(joined) % 4) % 4), validate=False)
        decoded_text = decoded.decode("utf-8", errors="ignore")
        for match in flag_re.finditer(decoded_text):
            add_flag(match.group(1))
            result["decoded_hits"].append({"name": "joined_fragments", "source": joined[:80], "decoded": decoded_text[:180]})
    except (ValueError, binascii.Error):
        pass

print(json.dumps(result, ensure_ascii=False))
""".strip()

        fd, script_path = tempfile.mkstemp(
            suffix=".py",
            prefix="flaghunter_artifact_forensics_",
        )
        os.close(fd)
        try:
            with open(script_path, "w", encoding="utf-8", newline="\n") as handle:
                handle.write(script)

            args = [python_cmd, script_path, artifact_url]
            if os.name == "nt":
                command = subprocess.list2cmdline(args)
            else:
                command = " ".join(shlex.quote(arg) for arg in args)

            result = await self.runtime.execute_command(command, timeout=90)
        finally:
            try:
                os.remove(script_path)
            except Exception:
                pass
        text = "\n".join(
            part
            for part in [getattr(result, "stdout", ""), getattr(result, "stderr", "")]
            if part
        ).strip()
        if not text or getattr(result, "exit_code", 1) != 0:
            return _ChainOutcome(progress=False, reason=f"artifact_forensics failed: {artifact_url}")

        await self._scan_and_store(text, target, evidence_source="command-output")
        try:
            analysis = json.loads(text.splitlines()[-1])
        except Exception:
            if flag := self._extract_flag(text):
                verification = await self._observe_flag(
                    flag,
                    target,
                    evidence_source="command-output",
                    rationale=f"attachment analysis recovered runtime flag via {artifact_url}",
                )
                if verification.decision in {"verified", "runtime"}:
                    return _ChainOutcome(progress=True, flag=verification.flag, reason=f"artifact_forensics flag: {artifact_url}")
            return _ChainOutcome(progress=True, reason=f"artifact_forensics analyzed: {artifact_url}")

        await self._store_note(
            key="ctf_artifact_forensics",
            value=json.dumps(
                {
                    "url": analysis.get("url"),
                    "kind": analysis.get("kind"),
                    "entries": (analysis.get("entries") or [])[:20],
                    "interesting": (analysis.get("interesting") or [])[:20],
                    "decoded_hits": (analysis.get("decoded_hits") or [])[:5],
                    "tables": (analysis.get("table_samples") or [])[:5],
                },
                ensure_ascii=False,
            ),
            category="artifact",
            target=urlparse(target).netloc or target,
            url=artifact_url,
            strategy_kind="artifact_forensics",
        )
        if self.state is not None:
            self.state.add_observation(
                "artifact_forensics_summary",
                json.dumps(
                    {
                        "url": analysis.get("url"),
                        "kind": analysis.get("kind"),
                        "interesting": (analysis.get("interesting") or [])[:10],
                        "entries": (analysis.get("entries") or [])[:10],
                    },
                    ensure_ascii=False,
                ),
                source="artifact_forensics",
                metadata={"url": artifact_url},
            )

        for flag in list(analysis.get("flags") or []):
            verification = await self._observe_flag(
                str(flag),
                target,
                evidence_source="command-output",
                rationale=f"attachment analysis recovered runtime flag via {artifact_url}",
            )
            if verification.decision in {"verified", "runtime"}:
                return _ChainOutcome(
                    progress=True,
                    flag=verification.flag,
                    reason=f"artifact_forensics flag: {artifact_url}",
                )
        return _ChainOutcome(progress=True, reason=f"artifact_forensics analyzed: {artifact_url}")
