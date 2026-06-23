from __future__ import annotations

import time

import pytest

from flaghunter.agents.pa_agent.ctf_state import CTFState
from flaghunter.agents.pa_agent.strategy_memory import (
    ChallengeFingerprint,
    StrategyMemoryEntry,
    StrategyMemoryEntryMetadata,
    StrategyMemoryStore,
    validate_learned_rule,
)


@pytest.mark.asyncio
async def test_strategy_memory_save_and_query(tmp_path):
    store = StrategyMemoryStore(tmp_path / "strategy_memory.json")
    fingerprint = ChallengeFingerprint(
        tech_stack=["php", "mysql"],
        auth_mechanism="form_login",
        detected_type="sqli",
        has_login_form=True,
        has_admin_panel=False,
        has_source_hint=False,
        response_error_types=["sql_error"],
        platform="buuoj",
    )
    entry = StrategyMemoryEntry(
        id="mem_1",
        fingerprint=fingerprint,
        winning_hypothesis_kinds=["auth_form_sqli"],
        failed_hypothesis_kinds=["generic_web_recon"],
        solved=True,
        metadata=StrategyMemoryEntryMetadata(
            created_at=time.time(),
            manual_status="active",
        ),
    )

    await store.save(entry)
    matches = await store.query(fingerprint)

    assert matches
    matched_entry, similarity = matches[0]
    assert matched_entry.id == "mem_1"
    assert similarity > 0.7


@pytest.mark.asyncio
async def test_strategy_memory_audit_writeback_updates_metadata(tmp_path):
    store = StrategyMemoryStore(tmp_path / "strategy_memory.json")
    fingerprint = ChallengeFingerprint(
        tech_stack=["php"],
        auth_mechanism="form_login",
        detected_type="sqli",
        has_login_form=True,
    )
    entry = StrategyMemoryEntry(
        id="mem_audit",
        fingerprint=fingerprint,
        winning_hypothesis_kinds=["auth_form_sqli"],
        solved=True,
        metadata=StrategyMemoryEntryMetadata(
            created_at=time.time(),
            manual_status="active",
        ),
    )

    await store.save(entry)
    await store.record_query_usage(["mem_audit"])
    await store.record_outcome(["mem_audit"], solved=False)

    entries = await store.list_entries(limit=5)
    target = next(item for item in entries if item.id == "mem_audit")

    assert target.metadata.applied_count == 1
    assert target.metadata.failed_applications == 1
    assert target.metadata.success_correlation == 0.0


@pytest.mark.asyncio
async def test_strategy_memory_manage_entry_status_and_lookup(tmp_path):
    store = StrategyMemoryStore(tmp_path / "strategy_memory.json")
    fingerprint = ChallengeFingerprint(detected_type="web")
    entry = StrategyMemoryEntry(
        id="mem_manage",
        fingerprint=fingerprint,
        solved=False,
        metadata=StrategyMemoryEntryMetadata(
            created_at=time.time(),
            manual_status="active",
        ),
    )

    await store.save(entry)
    muted = await store.mute_entry("mem_manage")
    shown = await store.get_entry("mem_manage")
    active = await store.activate_entry("mem_manage")

    assert muted is not None
    assert muted.metadata.manual_status == "muted"
    assert shown is not None
    assert shown.id == "mem_manage"
    assert active is not None
    assert active.metadata.manual_status == "active"


@pytest.mark.asyncio
async def test_strategy_memory_delete_export_and_clear(tmp_path):
    store = StrategyMemoryStore(tmp_path / "strategy_memory.json")
    entry = StrategyMemoryEntry(
        id="mem_ops",
        fingerprint=ChallengeFingerprint(detected_type="web"),
        solved=False,
        metadata=StrategyMemoryEntryMetadata(
            created_at=time.time(),
            manual_status="active",
        ),
    )
    await store.save(entry)

    exported = await store.export_entries(tmp_path / "memory_export.json")
    assert exported.exists()
    assert "mem_ops" in exported.read_text(encoding="utf-8")

    deleted = await store.delete_entry("mem_ops")
    assert deleted is True
    assert await store.get_entry("mem_ops") is None

    await store.save(entry)
    cleared = await store.clear_entries()
    assert cleared >= 1
    assert await store.list_entries() == []


@pytest.mark.asyncio
async def test_strategy_memory_list_entries_supports_sorting_and_stats(tmp_path):
    store = StrategyMemoryStore(tmp_path / "strategy_memory.json")
    now = time.time()
    entries = [
        StrategyMemoryEntry(
            id="mem_recent",
            fingerprint=ChallengeFingerprint(detected_type="web"),
            solved=False,
            metadata=StrategyMemoryEntryMetadata(
                created_at=now - 10,
                last_promoted_at=now,
                last_used_at=now - 5,
                applied_count=1,
                successful_applications=1,
                success_correlation=1.0,
                manual_status="active",
            ),
        ),
        StrategyMemoryEntry(
            id="mem_applied",
            fingerprint=ChallengeFingerprint(detected_type="web"),
            solved=False,
            metadata=StrategyMemoryEntryMetadata(
                created_at=now - 20,
                last_promoted_at=now - 20,
                last_used_at=now - 1,
                applied_count=7,
                failed_applications=6,
                success_correlation=0.14,
                manual_status="muted",
            ),
        ),
        StrategyMemoryEntry(
            id="mem_corr",
            fingerprint=ChallengeFingerprint(detected_type="web"),
            solved=False,
            metadata=StrategyMemoryEntryMetadata(
                created_at=now - 30,
                last_promoted_at=now - 30,
                last_used_at=now - 2,
                applied_count=5,
                successful_applications=4,
                failed_applications=1,
                success_correlation=0.80,
                manual_status="deprecated",
            ),
        ),
    ]
    for entry in entries:
        await store.save(entry)

    recent = await store.list_entries(limit=3, sort_by="recent")
    applied = await store.list_entries(limit=3, sort_by="applied")
    correlation = await store.list_entries(limit=3, sort_by="correlation")
    audit = await store.audit_entries(threshold=0.3, sort_by="correlation")
    stats = await store.stats(threshold=0.3)

    assert recent[0].id == "mem_recent"
    assert applied[0].id == "mem_applied"
    assert correlation[0].id == "mem_recent"
    assert [item.id for item in audit] == ["mem_applied"]
    assert stats == {
        "total": 3,
        "active": 1,
        "muted": 1,
        "deprecated": 1,
        "audit_candidates": 1,
    }


@pytest.mark.asyncio
async def test_strategy_memory_apply_rejected_feedback_deprecates_session_and_recomputes_stats(
    tmp_path,
):
    store = StrategyMemoryStore(tmp_path / "strategy_memory.json")
    entry = StrategyMemoryEntry(
        id="mem_seed",
        fingerprint=ChallengeFingerprint(detected_type="sqli"),
        solved=True,
        metadata=StrategyMemoryEntryMetadata(
            created_at=time.time(),
            manual_status="active",
            applied_count=6,
            successful_applications=1,
            failed_applications=0,
            success_correlation=1.0,
        ),
    )
    session_entry = StrategyMemoryEntry(
        id="mem_session",
        fingerprint=ChallengeFingerprint(detected_type="sqli"),
        solved=True,
        metadata=StrategyMemoryEntryMetadata(
            created_at=time.time(),
            manual_status="active",
        ),
    )
    await store.save(entry)
    await store.save(session_entry)

    audit = await store.apply_rejected_feedback(
        ["mem_seed"],
        session_entry_id="mem_session",
    )

    updated = await store.get_entry("mem_seed")
    downgraded = await store.get_entry("mem_session")

    assert audit["affected_entry_ids"] == ["mem_seed"]
    assert audit["deprecated_entry_id"] == "mem_session"
    assert updated is not None
    assert updated.metadata.successful_applications == 0
    assert updated.metadata.failed_applications == 1
    assert updated.metadata.success_correlation == 0.0
    assert updated.metadata.manual_status == "muted"
    assert downgraded is not None
    assert downgraded.metadata.manual_status == "deprecated"


def test_strategy_memory_adjustments_bonus_penalty_and_clamp():
    store = StrategyMemoryStore()
    fingerprint = ChallengeFingerprint(detected_type="sqli")
    active = StrategyMemoryEntry(
        id="mem_a",
        fingerprint=fingerprint,
        winning_hypothesis_kinds=["auth_form_sqli"],
        failed_hypothesis_kinds=["generic_web_recon"],
        solved=True,
        metadata=StrategyMemoryEntryMetadata(manual_status="active"),
    )
    duplicate = StrategyMemoryEntry(
        id="mem_b",
        fingerprint=fingerprint,
        winning_hypothesis_kinds=["auth_form_sqli"],
        failed_hypothesis_kinds=[],
        solved=True,
        metadata=StrategyMemoryEntryMetadata(manual_status="active"),
    )

    adjustments = store.compute_hypothesis_adjustments(
        [(active, 0.9), (duplicate, 0.9), (duplicate, 0.9)]
    )

    assert adjustments["auth_form_sqli"] == 0.25
    assert adjustments["generic_web_recon"] == -0.10


def test_recall_failed_payloads_aggregates_above_threshold_with_dedup_and_limit():
    store = StrategyMemoryStore()
    fp = ChallengeFingerprint(detected_type="sqli")
    similar = StrategyMemoryEntry(
        id="mem_similar",
        fingerprint=fp,
        failed_payloads=["' OR 1=1 -- ", "admin' --", "' OR 1=1 -- "],
        metadata=StrategyMemoryEntryMetadata(manual_status="active"),
    )
    other_similar = StrategyMemoryEntry(
        id="mem_other",
        fingerprint=fp,
        failed_payloads=["ADMIN' --", "{{7*7}}"],  # case-dup of admin' -- + new
        metadata=StrategyMemoryEntryMetadata(manual_status="active"),
    )
    dissimilar = StrategyMemoryEntry(
        id="mem_low",
        fingerprint=fp,
        failed_payloads=["below-threshold-should-be-ignored"],
        metadata=StrategyMemoryEntryMetadata(manual_status="active"),
    )

    recalled = store.recall_failed_payloads(
        [(similar, 0.9), (other_similar, 0.6), (dissimilar, 0.30)]
    )

    # below-similarity entry excluded; payloads normalized (stripped, matching
    # the record_failure write side); case-insensitive dedup keeps first form;
    # order preserved across entries.
    assert recalled == ["' OR 1=1 --", "admin' --", "{{7*7}}"]
    assert "below-threshold-should-be-ignored" not in recalled

    limited = store.recall_failed_payloads([(similar, 0.9)], limit=1)
    assert limited == ["' OR 1=1 --"]


def test_recall_failed_payloads_empty_on_cold_or_low_similarity():
    store = StrategyMemoryStore()
    fp = ChallengeFingerprint(detected_type="sqli")
    assert store.recall_failed_payloads([]) == []
    no_failures = StrategyMemoryEntry(id="mem_nf", fingerprint=fp, failed_payloads=[])
    assert store.recall_failed_payloads([(no_failures, 0.9)]) == []
    has_failures = StrategyMemoryEntry(
        id="mem_low_sim", fingerprint=fp, failed_payloads=["x' OR '1'='1"]
    )
    assert store.recall_failed_payloads([(has_failures, 0.44)]) == []


def test_strategy_memory_build_entry_filters_non_generalizable_rules():
    store = StrategyMemoryStore()
    state = CTFState(target="http://ctf.local", goal="拿到flag", detected_type="sqli")
    state.retrospectives.append(
        {
            "id": "retro_1",
            "learned_rule": "源码中的 flag 只能视为 candidate，必须继续追运行时证据。",
        }
    )
    state.retrospectives.append(
        {
            "id": "retro_2",
            "learned_rule": "在 buuoj 上这个题直接看 http://example.com 就行。",
        }
    )
    fingerprint = store.build_fingerprint(state, target=state.target)

    entry = store.build_entry(
        state=state,
        fingerprint=fingerprint,
        chain_used=["sqli"],
        solved=False,
    )

    assert entry.learned_rules == ["源码中的 flag 只能视为 candidate，必须继续追运行时证据。"]
    assert "type:sqli" in entry.atomic_facts


def test_strategy_memory_validate_learned_rule_rejects_platform_url_and_bad_length():
    assert (
        validate_learned_rule("源码中的 flag 只能视为 candidate，必须继续追运行时证据。")
        is True
    )
    assert validate_learned_rule("太短了") is False
    assert validate_learned_rule("在 buuoj 上直接访问 http://example.com 即可。") is False


def test_strategy_memory_build_atomic_facts_captures_runtime_signals():
    store = StrategyMemoryStore()
    state = CTFState(
        target="http://ctf.local/file?filename=/flag.txt&filehash=deadbeef",
        goal="拿到flag",
        detected_type="web",
    )
    state.add_observation(
        "recon_url",
        "http://ctf.local/file?filename=/flag.txt&filehash=deadbeef",
        source="phase_recon",
        metadata={"endpoints": ["/admin", "/visit", "/hints.txt"]},
    )
    state.add_artifact(
        "backup_hint",
        location="http://ctf.local/www.zip",
        source="phase_recon",
        metadata={"content": "discovered www.zip / Tornado welcome page"},
    )
    fingerprint = store.build_fingerprint(
        state,
        page_features={
            "url": state.target,
            "endpoints": ["/admin", "/visit", "/hints.txt"],
            "content": "TornadoServer/6.5",
            "html": "<html>backup source code</html>",
        },
        target=state.target,
    )

    facts = store.build_atomic_facts(state=state, fingerprint=fingerprint)

    assert "type:web" in facts
    assert "platform:ctf.local" in facts
    assert "route:admin" in facts
    assert "route:visit" in facts
    assert "route:hint_file" in facts
    assert "surface:file_hash_guard" in facts
    assert "artifact:backup_archive" in facts
    assert "framework:tornado" in facts


@pytest.mark.asyncio
async def test_strategy_memory_web_subtype_affects_similarity_and_fingerprint(tmp_path):
    store = StrategyMemoryStore(tmp_path / "strategy_memory.json")
    state = CTFState(target="http://ctf.local/file?filename=/flag.txt&filehash=deadbeef", goal="拿到flag", detected_type="web")
    state.add_observation(
        "recon_url",
        "http://ctf.local/file?filename=/flag.txt&filehash=deadbeef",
        source="phase_recon",
        metadata={"endpoints": ["/file?filename=/flag.txt&filehash=deadbeef", "/hints.txt"]},
    )
    fingerprint = store.build_fingerprint(
        state,
        page_features={
            "url": "http://ctf.local/file?filename=/flag.txt&filehash=deadbeef",
            "endpoints": ["/file?filename=/flag.txt&filehash=deadbeef", "/hints.txt"],
            "content": "TornadoServer/6.5 hints",
            "html": "<html></html>",
        },
        target=state.target,
    )
    entry = StrategyMemoryEntry(
        id="mem_web_subtype",
        fingerprint=ChallengeFingerprint(
            detected_type="web",
            tech_stack=["web"],
            web_subtype=["file_hash_guard", "hint_file", "tornado"],
        ),
        solved=True,
        metadata=StrategyMemoryEntryMetadata(
            created_at=time.time(),
            manual_status="active",
        ),
    )
    await store.save(entry)

    matches = await store.query(fingerprint)

    assert set(fingerprint.web_subtype) >= {"file_hash_guard", "hint_file", "tornado"}
    assert state.observations[-1].metadata["web_subtype"] == fingerprint.web_subtype
    assert matches
    assert matches[0][0].id == "mem_web_subtype"
    assert matches[0][1] > 0.45
    assert "web_subtype:file_hash_guard" in matches[0][0].atomic_facts


@pytest.mark.asyncio
async def test_recall_shortest_winning_chain_prefers_shortest_solved(tmp_path):
    store = StrategyMemoryStore(tmp_path / "strategy_memory.json")
    fp = ChallengeFingerprint(detected_type="web", tech_stack=["php"])

    await store.save(StrategyMemoryEntry(
        id="mem_long",
        fingerprint=fp,
        winning_primitive_sequence=["sqli", "web"],
        avg_turns_to_flag=8,
        solved=True,
        metadata=StrategyMemoryEntryMetadata(
            created_at=time.time(), manual_status="active", success_correlation=0.9
        ),
    ))
    await store.save(StrategyMemoryEntry(
        id="mem_short",
        fingerprint=fp,
        winning_primitive_sequence=["web"],
        avg_turns_to_flag=3,
        solved=True,
        metadata=StrategyMemoryEntryMetadata(
            created_at=time.time(), manual_status="active", success_correlation=0.8
        ),
    ))
    await store.save(StrategyMemoryEntry(
        id="mem_unsolved",
        fingerprint=fp,
        winning_primitive_sequence=["misc"],
        avg_turns_to_flag=1,
        solved=False,
        metadata=StrategyMemoryEntryMetadata(created_at=time.time(), manual_status="active"),
    ))
    await store.save(StrategyMemoryEntry(
        id="mem_other",
        fingerprint=ChallengeFingerprint(detected_type="pwn"),
        winning_primitive_sequence=["pwn"],
        avg_turns_to_flag=1,
        solved=True,
        metadata=StrategyMemoryEntryMetadata(created_at=time.time(), manual_status="active"),
    ))

    # shortest solved chain among similar (web) entries; unsolved + dissimilar ignored
    assert store.recall_shortest_winning_chain(fp) == ["web"]


@pytest.mark.asyncio
async def test_recall_shortest_winning_chain_empty_when_no_solved_match(tmp_path):
    store = StrategyMemoryStore(tmp_path / "strategy_memory.json")
    fp = ChallengeFingerprint(detected_type="web")
    await store.save(StrategyMemoryEntry(
        id="mem_u",
        fingerprint=fp,
        winning_primitive_sequence=["web"],
        solved=False,
        metadata=StrategyMemoryEntryMetadata(created_at=time.time(), manual_status="active"),
    ))
    assert store.recall_shortest_winning_chain(fp) == []


@pytest.mark.asyncio
async def test_recall_chain_pheromone_shorter_chain_gets_more(tmp_path):
    store = StrategyMemoryStore(tmp_path / "strategy_memory.json")
    fp = ChallengeFingerprint(detected_type="web", tech_stack=["php"])
    now = time.time()

    # single-step winning chain ['web'] -> deposits 1.0 on web
    await store.save(StrategyMemoryEntry(
        id="mem_web",
        fingerprint=fp,
        winning_primitive_sequence=["web"],
        solved=True,
        created_at=now,
        metadata=StrategyMemoryEntryMetadata(
            created_at=now, last_used_at=now, manual_status="active",
            confidence_decay_factor=1.0, success_correlation=1.0,
        ),
    ))
    # two-step winning chain ['sqli','web'] -> deposits 0.5 on each
    await store.save(StrategyMemoryEntry(
        id="mem_sqli_web",
        fingerprint=fp,
        winning_primitive_sequence=["sqli", "web"],
        solved=True,
        created_at=now,
        metadata=StrategyMemoryEntryMetadata(
            created_at=now, last_used_at=now, manual_status="active",
            confidence_decay_factor=1.0, success_correlation=1.0,
        ),
    ))

    pher = store.recall_chain_pheromone(fp)
    assert pher.get("web", 0) > pher.get("sqli", 0) > 0  # web accumulates from both, sqli only the long path


@pytest.mark.asyncio
async def test_recall_chain_pheromone_empty_without_similar_solved(tmp_path):
    store = StrategyMemoryStore(tmp_path / "strategy_memory.json")
    fp = ChallengeFingerprint(detected_type="web")
    now = time.time()
    # dissimilar type -> below threshold; unsolved -> ignored
    await store.save(StrategyMemoryEntry(
        id="mem_pwn",
        fingerprint=ChallengeFingerprint(detected_type="pwn"),
        winning_primitive_sequence=["pwn"],
        solved=True,
        created_at=now,
        metadata=StrategyMemoryEntryMetadata(created_at=now, manual_status="active", confidence_decay_factor=1.0),
    ))
    assert store.recall_chain_pheromone(fp) == {}
