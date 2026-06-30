from __future__ import annotations

import json

from flaghunter.knowledge.repertoire_radar import (
    candidate_id,
    list_candidates,
    move_candidate,
    record_repertoire_miss,
)


def _read(path):
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


def test_record_creates_inbox_candidate(tmp_path):
    record = record_repertoire_miss(
        target="http://bestphp.ctf.local/",
        detected_type="web",
        triggered_probes=["web", "sqli"],
        hypothesis_kinds=["generic_web_recon", "llm_driven_exploration"],
        observation_kinds=["framework_detected", "recon_url"],
        reason="all closed-set probes negative",
        root=tmp_path,
        now="2026-06-30T12:00:00",
    )

    assert record is not None
    assert record["status"] == "inbox"
    assert record["kind"] == "repertoire_miss"
    assert record["host"] == "bestphp.ctf.local"
    assert record["hit_count"] == 1
    assert record["triggered_probes"] == ["web", "sqli"]
    assert record["status_history"][0]["to"] == "inbox"

    on_disk = _read(tmp_path / "inbox.jsonl")
    assert len(on_disk) == 1
    assert on_disk[0]["id"] == record["id"]


def test_record_carries_nearest_patterns(tmp_path):
    # 设计 §2②③: a captured miss records its nearest 曲库 patterns (deterministic
    # retrieval) for human triage — but they must NOT affect the dedup identity.
    rec = record_repertoire_miss(
        target="http://novel.ctf.local/",
        detected_type="web",
        triggered_probes=["web"],
        nearest_patterns=["jwt_manipulation", "tornado_ssti"],
        root=tmp_path,
        now="t1",
    )
    assert rec["nearest_patterns"] == ["jwt_manipulation", "tornado_ssti"]

    # Same shape but different nearest_patterns → same id (dedup ignores them).
    again = record_repertoire_miss(
        target="http://novel.ctf.local/",
        detected_type="web",
        triggered_probes=["web"],
        nearest_patterns=["lfi"],
        root=tmp_path,
        now="t2",
    )
    assert again["id"] == rec["id"]
    assert again["hit_count"] == 2


def test_candidate_id_is_order_independent_on_signals(tmp_path):
    # Probe ordering must not change identity — sorted signals.
    a = record_repertoire_miss(
        target="http://x.local/", detected_type="web",
        triggered_probes=["web", "sqli"], root=tmp_path, now="t1",
    )
    b = record_repertoire_miss(
        target="http://x.local/", detected_type="web",
        triggered_probes=["sqli", "web"], root=tmp_path, now="t2",
    )
    # Same shape, reordered → same id → second call bumps, not duplicates.
    assert a["id"] == b["id"]
    assert b["hit_count"] == 2
    assert len(_read(tmp_path / "inbox.jsonl")) == 1


def test_dedup_bumps_hit_count_not_duplicate(tmp_path):
    record_repertoire_miss(
        target="http://x.local/", detected_type="web",
        triggered_probes=["web"], root=tmp_path, now="2026-06-30T12:00:00",
    )
    again = record_repertoire_miss(
        target="http://x.local/", detected_type="web",
        triggered_probes=["web"], root=tmp_path, now="2026-06-30T13:00:00",
    )
    assert again["hit_count"] == 2
    assert again["last_seen"] == "2026-06-30T13:00:00"
    assert again["first_seen"] == "2026-06-30T12:00:00"
    assert len(list_candidates(root=tmp_path, status="inbox")) == 1


def test_settled_candidate_is_not_reopened(tmp_path):
    rec = record_repertoire_miss(
        target="http://x.local/", detected_type="web",
        triggered_probes=["web"], root=tmp_path, now="t1",
    )
    # Promote it, then re-seeing the same miss must NOT re-open an inbox entry.
    move_candidate(candidate_id=rec["id"], to_status="promoted", reason="distilled", root=tmp_path, now="t2")

    reseen = record_repertoire_miss(
        target="http://x.local/", detected_type="web",
        triggered_probes=["web"], root=tmp_path, now="t3",
    )
    assert reseen is None
    assert list_candidates(root=tmp_path, status="inbox") == []
    assert len(list_candidates(root=tmp_path, status="promoted")) == 1


def test_rejected_candidate_is_not_reopened(tmp_path):
    rec = record_repertoire_miss(
        target="http://x.local/", detected_type="web",
        triggered_probes=["web"], root=tmp_path, now="t1",
    )
    move_candidate(candidate_id=rec["id"], to_status="rejected", reason="not exploitable", root=tmp_path, now="t2")
    assert record_repertoire_miss(
        target="http://x.local/", detected_type="web",
        triggered_probes=["web"], root=tmp_path, now="t3",
    ) is None


def test_move_candidate_records_history_and_relocates(tmp_path):
    rec = record_repertoire_miss(
        target="http://x.local/", detected_type="web",
        triggered_probes=["web"], root=tmp_path, now="t1",
    )
    moved = move_candidate(
        candidate_id=rec["id"], to_status="deferred", reason="revisit later", root=tmp_path, now="t2",
    )
    assert moved["status"] == "deferred"
    transition = moved["status_history"][-1]
    assert transition["from"] == "inbox" and transition["to"] == "deferred"
    assert transition["reason"] == "revisit later"
    assert list_candidates(root=tmp_path, status="inbox") == []
    assert len(list_candidates(root=tmp_path, status="deferred")) == 1


def test_move_unknown_candidate_returns_none(tmp_path):
    assert move_candidate(candidate_id="deadbeef", to_status="rejected", root=tmp_path) is None


def test_candidate_id_excludes_timestamp_stable_across_calls():
    # Identity is content-only — no volatile timestamp leaks into the id.
    first = candidate_id("h.local", "web", ["web", "sqli"])
    second = candidate_id("h.local", "web", ["sqli", "web"])
    assert first == second
    assert len(first) == 16
