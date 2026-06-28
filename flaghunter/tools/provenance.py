"""Tool-call provenance store (P3 — operating-model地基层).

Records every tool execution to a persisted, queryable call log so higher
layers can reconstruct *what ran, in what order, with what outcome*. This is the
geological foundation for "调用链可见" (visible call chains), P6 emergent-chain
mining, and orchestration decisions — see
``docs/dev/FlagHunter_运行方式愿景与上线问题清单_2026-06-28_V1.md`` (P3).

Design (mirrors ``token_tracker.py``):
  * append-only JSONL under the active workspace's ``loot/provenance.jsonl``;
  * workspace-aware path resolution (``get_loot_file``) computed at use;
  * thread-locked synchronous helpers usable from sync or async callers;
  * a swappable backend (``ProvenanceStore`` protocol) so the JSONL store can be
    replaced by SQLite / a graph DB later without touching the executor seam;
  * a ``set_provenance_file`` test seam mirroring ``token_tracker.set_data_file``.

Honest v1 boundary: this layer only *records + basic-queries*. Classifying calls
as "used alone vs chained" and mining emergent tool sequences into reusable
chains is **P6**, not P3 — but the ``run_id`` + ``seq`` captured here are exactly
what make that mining possible later.

Layer note (I1): this module lives in the CAPABILITY layer (``tools/``) and imports
only stdlib + ``workspaces.utils``. It must never import ``agents/``.
"""

from __future__ import annotations

import json
import threading
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional, Protocol, runtime_checkable

# ── Redaction ──────────────────────────────────────────────────────────────
# Tool arguments can carry secrets (passwords, cookies, keys). Provenance is a
# durable on-disk log, so we MUST redact sensitive values before persisting —
# the same discipline as "credentials never echoed in plaintext".
_SENSITIVE_KEYS = {
    "password",
    "passwd",
    "pass",
    "cookie",
    "cookies",
    "key",
    "keys",
    "secret",
    "token",
    "authorization",
    "auth",
    "candidate_passwords",
    "api_key",
    "apikey",
    "private_key",
    "credential",
    "credentials",
    "session",
    "sessionid",
}
_REDACTED = "***"
_MAX_STR = 2000  # truncate long string values so the log stays bounded
_MAX_LIST = 50
_MAX_DEPTH = 5


def _redact(value: Any, _depth: int = 0) -> Any:
    """Recursively redact sensitive keys and truncate oversized values."""
    if _depth > _MAX_DEPTH:
        return "...(depth)"
    if isinstance(value, dict):
        out: Dict[str, Any] = {}
        for k, v in value.items():
            if isinstance(k, str) and k.lower() in _SENSITIVE_KEYS:
                out[k] = _REDACTED
            else:
                out[k] = _redact(v, _depth + 1)
        return out
    if isinstance(value, (list, tuple)):
        return [_redact(v, _depth + 1) for v in list(value)[:_MAX_LIST]]
    if isinstance(value, str):
        return value if len(value) <= _MAX_STR else value[:_MAX_STR] + "...(truncated)"
    if isinstance(value, (int, float, bool)) or value is None:
        return value
    # Unknown type → stringify (and truncate)
    s = str(value)
    return s if len(s) <= _MAX_STR else s[:_MAX_STR] + "...(truncated)"


# ── Swappable backend ──────────────────────────────────────────────────────
@runtime_checkable
class ProvenanceStore(Protocol):
    """Pluggable provenance backend. Default = JSONL; swap freely."""

    def append(self, record: Dict[str, Any]) -> None: ...
    def read_all(self) -> List[Dict[str, Any]]: ...
    def clear(self) -> None: ...


class JsonlProvenanceStore:
    """Append-only JSONL store with best-effort size capping.

    One JSON object per line. Corrupt/half-written lines are skipped on read.
    Every ``trim_interval`` appends the file is trimmed to the last
    ``max_records`` entries so the log cannot grow unbounded (no silent
    unbounded growth).
    """

    def __init__(
        self,
        path: Path,
        *,
        max_records: int = 5000,
        trim_interval: int = 200,
    ) -> None:
        self._path = Path(path)
        self._max_records = max_records
        self._trim_interval = trim_interval
        self._since_trim = 0

    def append(self, record: Dict[str, Any]) -> None:
        self._path.parent.mkdir(parents=True, exist_ok=True)
        line = json.dumps(record, ensure_ascii=False, default=str)
        with self._path.open("a", encoding="utf-8") as fh:
            fh.write(line + "\n")
        self._since_trim += 1
        if self._since_trim >= self._trim_interval:
            self._since_trim = 0
            self._trim()

    def _trim(self) -> None:
        try:
            if not self._path.exists():
                return
            lines = self._path.read_text(encoding="utf-8").splitlines()
            if len(lines) <= self._max_records:
                return
            kept = lines[-self._max_records :]
            self._path.write_text("\n".join(kept) + "\n", encoding="utf-8")
        except Exception:
            # Trimming is best-effort; never let it disrupt recording.
            pass

    def read_all(self) -> List[Dict[str, Any]]:
        if not self._path.exists():
            return []
        out: List[Dict[str, Any]] = []
        try:
            for line in self._path.read_text(encoding="utf-8").splitlines():
                line = line.strip()
                if not line:
                    continue
                try:
                    out.append(json.loads(line))
                except Exception:
                    continue  # tolerate a corrupt/half-written line
        except Exception:
            return out
        return out

    def clear(self) -> None:
        try:
            if self._path.exists():
                self._path.unlink()
        except Exception:
            pass


# ── Module state ───────────────────────────────────────────────────────────
_lock = threading.Lock()
_seq = 0
_store: Optional[ProvenanceStore] = None


def _get_store() -> ProvenanceStore:
    """Resolve the active store, defaulting to workspace-routed loot JSONL.

    Computed at use (not import) so it respects the active workspace, exactly
    like ``token_tracker``'s path resolution.
    """
    global _store
    if _store is None:
        from ..workspaces.utils import get_loot_file

        _store = JsonlProvenanceStore(get_loot_file("provenance.jsonl"))
    return _store


def set_provenance_store(store: ProvenanceStore) -> None:
    """Swap the backend (production hook for SQLite/graph; also used by tests)."""
    global _store
    _store = store


def set_provenance_file(path: Path) -> None:
    """Test seam: route provenance to a temp JSONL file and reset the sequence.

    Mirrors ``token_tracker.set_data_file``. Resets the in-process sequence so
    each test gets deterministic ``seq`` values starting at 1.
    """
    global _store, _seq
    with _lock:
        _store = JsonlProvenanceStore(Path(path))
        _seq = 0


def record_call_sync(
    *,
    tool_name: str,
    run_id: str = "",
    category: str = "",
    arguments: Optional[dict] = None,
    target: str = "",
    status: Optional[str] = None,
    error_class: Optional[str] = None,
    success: bool = True,
    duration_ms: float = 0.0,
    found_flag: bool = False,
    cache_hit: bool = False,
    timestamp: Optional[str] = None,
) -> Dict[str, Any]:
    """Record one tool call. Returns the stored record (with assigned seq/ts).

    Caller is expected to wrap this in a fail-safe try/except (the executor
    does) — but the store's own writes are best-effort too.
    """
    global _seq
    with _lock:
        _seq += 1
        record: Dict[str, Any] = {
            "seq": _seq,
            "ts": timestamp or datetime.now().isoformat(),
            "run_id": run_id,
            "tool": tool_name,
            "category": category,
            "target": target,
            "status": status or ("success" if success else "error"),
            "error_class": error_class or ("none" if success else "transient"),
            "success": bool(success),
            "duration_ms": round(float(duration_ms or 0.0), 2),
            "found_flag": bool(found_flag),
            "cache_hit": bool(cache_hit),
            "args": _redact(arguments or {}),
        }
        _get_store().append(record)
        return record


# ── Queries (basic v1 — feed the展示层 / P6 later) ──────────────────────────
def get_all_calls() -> List[Dict[str, Any]]:
    """All recorded calls, in stored (chronological) order."""
    with _lock:
        return _get_store().read_all()


def recent(n: int = 20) -> List[Dict[str, Any]]:
    """The last ``n`` recorded calls."""
    calls = get_all_calls()
    return calls[-n:] if n > 0 else []


def get_run_calls(run_id: str) -> List[Dict[str, Any]]:
    """All calls in one executor run, ordered by ``seq`` (the call sequence)."""
    calls = [c for c in get_all_calls() if c.get("run_id") == run_id]
    return sorted(calls, key=lambda c: c.get("seq", 0))


def get_tool_stats(tool_name: str) -> Dict[str, Any]:
    """Usage stats for one tool: count, success/fail, runs it appeared in, flags."""
    calls = [c for c in get_all_calls() if c.get("tool") == tool_name]
    successes = sum(1 for c in calls if c.get("success"))
    runs = sorted({c.get("run_id", "") for c in calls if c.get("run_id")})
    return {
        "tool": tool_name,
        "count": len(calls),
        "success": successes,
        "failed": len(calls) - successes,
        "runs": runs,
        "run_count": len(runs),
        "found_flag_count": sum(1 for c in calls if c.get("found_flag")),
        "last_status": calls[-1].get("status") if calls else None,
    }


def summary() -> Dict[str, Any]:
    """Aggregate snapshot across all recorded calls."""
    calls = get_all_calls()
    tools: Dict[str, int] = {}
    runs = set()
    flags = 0
    for c in calls:
        tools[c.get("tool", "?")] = tools.get(c.get("tool", "?"), 0) + 1
        if c.get("run_id"):
            runs.add(c["run_id"])
        if c.get("found_flag"):
            flags += 1
    return {
        "total": len(calls),
        "tools": tools,
        "run_count": len(runs),
        "flags_found": flags,
    }


def clear() -> None:
    """Wipe the provenance log (test/maintenance helper)."""
    global _seq
    with _lock:
        _get_store().clear()
        _seq = 0
