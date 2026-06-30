"""Repertoire-miss candidate radar — turn曲库外 misses into accumulable assets.

When a CTF challenge falls outside FlagHunter's closed exploit repertoire, the run
gives up without a flag and sets the ``CTFState.repertoire_miss`` signal at the
terminal convergence-stop (give-up 点法 — see ``recovery.RecoveryController.finalize``).
Historically the miss evaporated: nothing recorded it, so the same kind of gap got
rediscovered run after run.

This module is the mirror of ``ctf_experience.save_ctf_experience`` (which backfills
*successful* solves into the ``ctf_sessions`` draft box): it backfills *unsolved
repertoire misses* into a candidate radar so each miss becomes a durable candidate
that a human can later distill into a new attack-pattern (轴 A 设计文档 §2④;
docs/dev/曲库与探索循环..._2026-06-30_V1.md).

The design is a 1:1 port of the reference knowledge base's candidate lifecycle
(D:\\newwork\\AI-Agents\\aiagentstudy\\knowledge\\raw\\manage_candidates.py):
a four-file deterministic state machine over JSONL —

    inbox → promoted | deferred | rejected

with a dedup gate (a miss of the same *shape* bumps a hit counter instead of
duplicating) and a ``status_history`` audit trail. Everything here is **pure +
deterministic**: the candidate ``id`` is a content hash that deliberately excludes
volatile timestamps (per the reference schema's "stable across rebuilds" rule), and
``now`` is injectable so tests are reproducible. Writing happens at the CLI entry
(never inside the dispatcher) to avoid polluting unit-test runs — same placement
rationale as the success backfill in ``interface/cli.py``.

The radar lives under the ``ctf_sessions`` draft box (git-ignored local 草稿箱) —
``knowledge.sources`` (the human-distilled library) is reached only via the manual
promotion step, honouring the data-governance 铁律 ([[project_data_governance]]).
"""

from __future__ import annotations

import hashlib
import json
import re
from datetime import datetime
from pathlib import Path
from typing import Any, Iterable
from urllib.parse import urlparse


# Four-file deterministic state machine — mirrors the reference radar's
# inbox/promoted/deferred/rejected.jsonl (manage_candidates.py:21-24).
STATUSES = ("inbox", "promoted", "deferred", "rejected")

_DEFAULT_RADAR_DIR = Path("flaghunter/knowledge/ctf_sessions/repertoire_radar")


def _radar_dir(root: str | Path | None) -> Path:
    return Path(root) if root is not None else _DEFAULT_RADAR_DIR


def _file_for(root: str | Path | None, status: str) -> Path:
    if status not in STATUSES:
        raise ValueError(f"unknown candidate status: {status!r}")
    return _radar_dir(root) / f"{status}.jsonl"


def _now_iso(now: str | None) -> str:
    if now is not None:
        return str(now)
    return datetime.now().isoformat(timespec="seconds")


def _host_of(target: str) -> str:
    netloc = urlparse(str(target or "")).netloc
    return re.sub(r"[^\w.:-]", "_", netloc or "unknown")


def _norm_list(values: Iterable[Any] | None) -> list[str]:
    """Deterministic, de-duplicated, order-stable list of non-empty strings."""
    out: list[str] = []
    seen: set[str] = set()
    for value in values or []:
        text = str(value or "").strip()
        if text and text not in seen:
            seen.add(text)
            out.append(text)
    return out


def candidate_id(host: str, detected_type: str, signals: Iterable[Any]) -> str:
    """Deterministic identity for a repertoire-miss *shape*.

    Identity = (host, detected_type, sorted signals). Excludes timestamps so the
    same gap re-seen across runs maps to one candidate (dedup gate). Sorting the
    signals makes the id independent of probe ordering.
    """
    canonical = "|".join(
        [
            str(host or "").strip().lower(),
            str(detected_type or "").strip().lower(),
            ",".join(sorted(_norm_list(signals))),
        ]
    )
    return hashlib.sha1(canonical.encode("utf-8")).hexdigest()[:16]


def _read_jsonl(path: Path) -> list[dict[str, Any]]:
    if not path.exists():
        return []
    records: list[dict[str, Any]] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            obj = json.loads(line)
        except Exception:
            continue
        if isinstance(obj, dict):
            records.append(obj)
    return records


def _write_jsonl(path: Path, records: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    body = "\n".join(json.dumps(record, ensure_ascii=False, sort_keys=True) for record in records)
    path.write_text(body + ("\n" if body else ""), encoding="utf-8")


def list_candidates(*, root: str | Path | None = None, status: str = "inbox") -> list[dict[str, Any]]:
    """All candidate records currently in ``status``'s file."""
    return _read_jsonl(_file_for(root, status))


def _index_by_id(records: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    return {str(record.get("id") or ""): record for record in records if record.get("id")}


def record_repertoire_miss(
    *,
    target: str,
    detected_type: str,
    triggered_probes: Iterable[Any] | None = None,
    hypothesis_kinds: Iterable[Any] | None = None,
    observation_kinds: Iterable[Any] | None = None,
    evidence_paths: Iterable[Any] | None = None,
    nearest_patterns: Iterable[Any] | None = None,
    reason: str = "",
    root: str | Path | None = None,
    now: str | None = None,
) -> dict[str, Any] | None:
    """Append (or bump) an inbox candidate for an unsolved 曲库外 miss.

    Dedup gate (mirrors the reference promote pipeline's ``item_url_exists`` guard):
    - already promoted or rejected → return ``None`` (the gap is handled / dismissed;
      do not re-open it). This is what makes "miss 不白 miss" — a settled signal is
      not re-evaluated every run.
    - already in inbox/deferred → bump ``hit_count`` + ``last_seen`` in place.
    - otherwise → create a fresh inbox record.

    Returns the written/updated record, or ``None`` when skipped.
    """
    host = _host_of(target)
    probes = _norm_list(triggered_probes)
    kinds = _norm_list(hypothesis_kinds)
    obs_kinds = _norm_list(observation_kinds)
    # The dedup signal set is the challenge *shape* — its detected type + the chains
    # we tried + the fallback hypotheses that fired. Two misses with the same shape
    # are the same gap.
    signals = probes + kinds
    cid = candidate_id(host, detected_type, signals)
    stamp = _now_iso(now)

    # A candidate already promoted or rejected is settled — never re-open it.
    for settled in ("promoted", "rejected"):
        if cid in _index_by_id(_read_jsonl(_file_for(root, settled))):
            return None

    # Bump an existing live candidate (inbox or deferred) rather than duplicating.
    for live in ("inbox", "deferred"):
        path = _file_for(root, live)
        records = _read_jsonl(path)
        index = _index_by_id(records)
        if cid in index:
            record = index[cid]
            record["hit_count"] = int(record.get("hit_count", 1) or 1) + 1
            record["last_seen"] = stamp
            _write_jsonl(path, records)
            return record

    record: dict[str, Any] = {
        "id": cid,
        "status": "inbox",
        "kind": "repertoire_miss",
        "target": str(target or ""),
        "host": host,
        "detected_type": str(detected_type or "").strip(),
        "triggered_probes": probes,
        "hypothesis_kinds": kinds,
        "observation_kinds": obs_kinds,
        "evidence_paths": _norm_list(evidence_paths),
        # 设计 §2②③ —— 该 miss 最近的曲库模式 kind(确定性检索召回),供人工 triage
        # 判断"扩现有模式 vs 蒸馏新模式"。不参与 dedup id(id 只认 host+type+signals)。
        "nearest_patterns": _norm_list(nearest_patterns),
        "reason": str(reason or "").strip() or "repertoire_miss",
        "hit_count": 1,
        "first_seen": stamp,
        "last_seen": stamp,
        "status_history": [{"to": "inbox", "reason": "repertoire_miss radar capture", "at": stamp}],
    }
    inbox_path = _file_for(root, "inbox")
    records = _read_jsonl(inbox_path)
    records.append(record)
    _write_jsonl(inbox_path, records)
    return record


def move_candidate(
    *,
    candidate_id: str,
    to_status: str,
    reason: str = "",
    root: str | Path | None = None,
    now: str | None = None,
) -> dict[str, Any] | None:
    """Move a candidate between status files, appending a ``status_history`` entry.

    Deterministic state-machine transition (mirrors ``move_candidate_to_*`` in the
    reference radar). Returns the moved record, or ``None`` if not found. Promotion
    to a durable attack-pattern (the distillation step) is a *separate*, human/
    half-auto stage (design §2① / ②) — this primitive only relocates the record.
    """
    if to_status not in STATUSES:
        raise ValueError(f"unknown target status: {to_status!r}")
    cid = str(candidate_id or "")
    stamp = _now_iso(now)

    for from_status in STATUSES:
        if from_status == to_status:
            continue
        src_path = _file_for(root, from_status)
        records = _read_jsonl(src_path)
        index = _index_by_id(records)
        if cid not in index:
            continue
        record = index[cid]
        remaining = [item for item in records if str(item.get("id") or "") != cid]
        _write_jsonl(src_path, remaining)

        history = list(record.get("status_history") or [])
        history.append(
            {"from": from_status, "to": to_status, "reason": str(reason or "").strip(), "at": stamp}
        )
        record["status"] = to_status
        record["status_history"] = history
        record["last_seen"] = stamp

        dst_path = _file_for(root, to_status)
        dst_records = _read_jsonl(dst_path)
        dst_records = [item for item in dst_records if str(item.get("id") or "") != cid]
        dst_records.append(record)
        _write_jsonl(dst_path, dst_records)
        return record

    return None


__all__ = [
    "STATUSES",
    "candidate_id",
    "list_candidates",
    "record_repertoire_miss",
    "move_candidate",
]
