"""Safety contract: the payload factory only ever emits fake canary data.

These guards back the safety promise in the red-blue PROTOCOL — synthetic /
benign payloads, fake data only, no real hosts or secrets. If a future edit
sneaks a real-looking secret or live domain into a seed, CI fails here.
"""

from __future__ import annotations

import re

from flaghunter.redteam import generate
from flaghunter.redteam.extraction import list_framings
from flaghunter.redteam.seeds import CANARIES, list_seeds


def _all_inert_strings():
    """Every attacker-controlled test string the package can emit."""
    return [s.text for s in list_seeds()] + [f.text for f in list_framings()]

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
    """No seed/framing may point at a resolvable host — only *.invalid sinks."""
    for text in _all_inert_strings():
        for url in re.findall(r"https?://[^\s'\")]+", text):
            assert ".invalid" in url, f"references non-.invalid URL: {url}"


def test_no_seed_contains_real_key_material():
    for text in _all_inert_strings():
        for marker in _FORBIDDEN_SUBSTRINGS:
            assert marker not in text, f"forbidden marker {marker!r} in test string"


def test_pii_values_are_exactly_the_canaries():
    """Any digit-run that looks like an ID/card/phone must be a declared canary."""
    canary_numbers = {
        CANARIES["pii_id"], CANARIES["pii_card"], CANARIES["pii_phone"]
    }
    for text in _all_inert_strings():
        for run in re.findall(r"\d{11,}", text):
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
