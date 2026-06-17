"""Legacy ``PENTESTAGENT_*`` env vars must alias onto the canonical ``FLAGHUNTER_*``."""

import os

from flaghunter.config.env import apply_legacy_env_aliases


def test_legacy_var_aliased_to_canonical(monkeypatch):
    monkeypatch.delenv("FLAGHUNTER_MODEL", raising=False)
    monkeypatch.setenv("PENTESTAGENT_MODEL", "gpt-5")

    apply_legacy_env_aliases()

    assert os.environ["FLAGHUNTER_MODEL"] == "gpt-5"


def test_canonical_takes_precedence_over_legacy(monkeypatch):
    monkeypatch.setenv("PENTESTAGENT_MODEL", "legacy-value")
    monkeypatch.setenv("FLAGHUNTER_MODEL", "canonical-value")

    apply_legacy_env_aliases()

    assert os.environ["FLAGHUNTER_MODEL"] == "canonical-value"


def test_arbitrary_suffix_is_aliased(monkeypatch):
    monkeypatch.delenv("FLAGHUNTER_STEALTH", raising=False)
    monkeypatch.setenv("PENTESTAGENT_STEALTH", "1")

    apply_legacy_env_aliases()

    assert os.environ["FLAGHUNTER_STEALTH"] == "1"


def test_unrelated_var_not_created(monkeypatch):
    monkeypatch.delenv("FLAGHUNTER_NOT_SET_XYZ", raising=False)
    monkeypatch.delenv("PENTESTAGENT_NOT_SET_XYZ", raising=False)

    apply_legacy_env_aliases()

    assert "FLAGHUNTER_NOT_SET_XYZ" not in os.environ
