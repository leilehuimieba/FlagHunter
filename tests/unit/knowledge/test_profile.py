"""Project-type profiles (P5 — 统一骨架 + profile 覆盖层)."""

from __future__ import annotations

from flaghunter.knowledge.kill_chain import Phase
from flaghunter.knowledge.profile import (
    CODE_AUDIT,
    CTF,
    DEFAULT_PROFILE,
    PROFILES,
    Profile,
    get_profile,
)


def test_ctf_profile_is_the_aggressive_url_default():
    assert CTF.name == "ctf"
    assert CTF.exploitation_mode == "aggressive"
    assert CTF.entry_kind == "url"
    # Empty budget override → falls back to the P4 module default (byte-identical).
    assert CTF.phase_round_budgets == {}


def test_code_audit_profile_is_a_conservative_source_scaffold():
    assert CODE_AUDIT.name == "code_audit"
    assert CODE_AUDIT.exploitation_mode == "conservative"
    assert CODE_AUDIT.entry_kind == "source"
    # Tighter EXPLOIT budget — audit converges earlier, leaves a trail.
    assert CODE_AUDIT.phase_round_budgets == {Phase.EXPLOIT: 12}


def test_default_profile_is_ctf():
    assert DEFAULT_PROFILE == "ctf"
    assert get_profile(None) is CTF
    assert get_profile("") is CTF


def test_get_profile_resolves_known_names_case_insensitively():
    assert get_profile("ctf") is CTF
    assert get_profile("code_audit") is CODE_AUDIT
    assert get_profile("  CODE_AUDIT  ") is CODE_AUDIT


def test_unknown_profile_falls_back_to_default_not_error():
    # A typo degrades to the byte-identical default rather than raising.
    assert get_profile("nonsense") is CTF


def test_registry_keys_match_profile_names_and_are_well_formed():
    valid_modes = {"aggressive", "conservative"}
    valid_entries = {"url", "source", "blackbox"}
    for key, profile in PROFILES.items():
        assert isinstance(profile, Profile)
        assert key == profile.name
        assert profile.exploitation_mode in valid_modes
        assert profile.entry_kind in valid_entries
