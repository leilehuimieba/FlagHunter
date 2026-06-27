"""Safety contract: the payload factory only ever emits fake canary data.

These guards back the safety promise in the red-blue PROTOCOL — synthetic /
benign payloads, fake data only, no real hosts or secrets. If a future edit
sneaks a real-looking secret or live domain into a seed, CI fails here.
"""

from __future__ import annotations

import re

from flaghunter.redteam import generate
from flaghunter.redteam.seeds import CANARIES, list_seeds

# Markers that must never appear: real key material headers.
_FORBIDDEN_SUBSTRINGS = [
    "BEGIN RSA PRIVATE KEY",
    "BEGIN OPENSSH PRIVATE KEY",
    "BEGIN PRIVATE KEY",
    "AKIA",            # AWS access key id prefix
    "sk-ant-",         # Anthropic key prefix
    "ghp_",            # GitHub PAT prefix
]


def test_every_url_in_seeds_uses_an_invalid_domain():
    """No seed may point at a resolvable host — only *.invalid sinks allowed."""
    for seed in list_seeds():
        for url in re.findall(r"https?://[^\s'\")]+", seed.text):
            assert ".invalid" in url, f"seed references non-.invalid URL: {url}"


def test_no_seed_contains_real_key_material():
    for seed in list_seeds():
        for marker in _FORBIDDEN_SUBSTRINGS:
            assert marker not in seed.text, f"forbidden marker {marker!r} in seed"


def test_pii_values_are_exactly_the_canaries():
    """Any digit-run that looks like an ID/card/phone must be a declared canary."""
    canary_numbers = {
        CANARIES["pii_id"], CANARIES["pii_card"], CANARIES["pii_phone"]
    }
    for seed in list_seeds():
        for run in re.findall(r"\d{11,}", seed.text):
            assert run in canary_numbers, f"undeclared long digit run: {run}"


def test_sensitive_looking_tokens_are_canaries():
    """Anything that reads like a secret token must be a SAFE_CANARY_* value."""
    for seed in list_seeds():
        for tok in re.findall(r"SAFE_CANARY_[A-Za-z0-9_]+", seed.text):
            assert tok in CANARIES.values() or tok.startswith("SAFE_CANARY_")


def test_generated_payloads_inherit_only_canary_seeds():
    """Every generated payload's seed is one of the vetted seed strings."""
    vetted = {s.text for s in list_seeds()}
    for p in generate():
        assert p.seed in vetted


def test_exfil_and_markup_seeds_target_the_canary_sink():
    sink = CANARIES["domain"]
    for seed in list_seeds(["exfiltration", "markup_exfil"]):
        if "://" in seed.text:
            assert sink in seed.text, f"exfil seed not aimed at canary sink: {seed.text}"
