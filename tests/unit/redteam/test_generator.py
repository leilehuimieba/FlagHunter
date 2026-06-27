"""Generator produces well-formed, deterministic, correctly-labelled batches."""

from __future__ import annotations

import json

from flaghunter.redteam import generate, payloads_to_jsonl, write_batch
from flaghunter.redteam.seeds import seed_categories
from flaghunter.redteam.transforms import apply_chain


def test_generate_default_is_nonempty_and_deterministic():
    a = generate()
    b = generate()
    assert a, "default generation produced nothing"
    assert [p.pid for p in a] == [p.pid for p in b]
    assert [p.text for p in a] == [p.text for p in b]


def test_pids_are_unique():
    payloads = generate()
    pids = [p.pid for p in payloads]
    assert len(pids) == len(set(pids))


def test_category_filter_restricts_output():
    only_jb = generate(categories=["jailbreak"])
    assert only_jb
    assert {p.category for p in only_jb} == {"jailbreak"}


def test_text_equals_chain_applied_to_seed():
    for p in generate(categories=["injection"]):
        assert p.text == apply_chain(p.seed, p.transform_chain)


def test_raw_chain_is_passthrough():
    raw = [p for p in generate(categories=["injection"]) if not p.transform_chain]
    assert raw
    for p in raw:
        assert p.text == p.seed


def test_benign_seeds_are_not_expected_to_block():
    benign = generate(categories=["benign"])
    assert benign
    assert all(p.expected_block is False for p in benign)
    assert all("false positive" in p.bypass_hypothesis.lower() for p in benign)


def test_attack_seeds_are_expected_to_block():
    attacks = generate(categories=["injection", "jailbreak", "command_exec"])
    assert attacks
    assert all(p.expected_block is True for p in attacks)


def test_rescan_control_vs_evasion_hypothesis():
    payloads = generate(categories=["injection"])
    b64 = next(p for p in payloads if p.transform_chain == ["base64"])
    assert "rescan control" in b64.bypass_hypothesis.lower()
    b32 = next(p for p in payloads if p.transform_chain == ["base32"])
    assert "evasion" in b32.bypass_hypothesis.lower()


def test_max_per_seed_caps_chains():
    capped = generate(categories=["injection"], max_per_seed=2)
    per_seed = {}
    for p in capped:
        per_seed.setdefault(p.seed, 0)
        per_seed[p.seed] += 1
    assert per_seed
    assert all(count == 2 for count in per_seed.values())


def test_custom_chain_overrides_default():
    payloads = generate(categories=["injection"], chains=[["morse"]])
    assert payloads
    assert all(p.transform_chain == ["morse"] for p in payloads)


def test_jsonl_round_trips():
    payloads = generate(categories=["jailbreak"])
    text = payloads_to_jsonl(payloads)
    rows = [json.loads(line) for line in text.splitlines()]
    assert len(rows) == len(payloads)
    assert rows[0]["pid"] == payloads[0].pid
    assert set(rows[0]) == {
        "pid", "category", "transform_chain", "seed", "text",
        "target_detector", "bypass_hypothesis", "expected_block",
    }


def test_write_batch_creates_file(tmp_path):
    payloads = generate(categories=["exfiltration"])
    out = write_batch(payloads, tmp_path / "nested" / "batch.jsonl")
    assert out.exists()
    lines = out.read_text(encoding="utf-8").strip().splitlines()
    assert len(lines) == len(payloads)


def test_all_seed_categories_generate():
    for cat in seed_categories():
        assert generate(categories=[cat]), f"category {cat} generated nothing"
