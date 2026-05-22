"""Tests for host-isolated WAF note handling."""

import asyncio

import pentestagent.tools.executor as executor_module
import pentestagent.tools.notes as notes_module
import pentestagent.tools.waf as waf_module
from pentestagent.tools.waf import run_waf


def test_waf_note_key_contains_host(monkeypatch):
    async def _fake_probe(runtime, url):
        return {
            "normal": {
                "status": 200,
                "headers": {"Server": "cloudflare", "cf-ray": "123abc"},
                "body": "ok",
                "error": "",
            },
            "attack": {
                "status": 403,
                "headers": {"cf-ray": "123abc"},
                "body": "blocked",
                "error": "",
            },
        }

    monkeypatch.setattr(waf_module, "_probe_http", _fake_probe)
    monkeypatch.setattr(notes_module, "_save_notes_unlocked", lambda: None)
    notes_module._notes.clear()

    asyncio.run(run_waf(action="detect", url="http://target-a.com/login"))

    matching_keys = [key for key in notes_module._notes if "target-a.com" in key]
    assert matching_keys
    note = notes_module._notes[matching_keys[0]]
    assert matching_keys[0] == "waf_detected_target-a.com"
    assert note["metadata"]["host"] == "target-a.com"
    assert note["metadata"]["url"] == "http://target-a.com/login"


def test_stealth_active_matching_host(monkeypatch):
    monkeypatch.delenv("PENTESTAGENT_STEALTH", raising=False)
    monkeypatch.setattr(
        notes_module,
        "get_all_notes_sync",
        lambda: {
            "waf_detected_target-a.com": {
                "category": "waf_detected",
                "metadata": {
                    "host": "target-a.com",
                    "delay_range": [1.2, 2.8],
                },
            }
        },
    )

    active, delay_range = executor_module._is_stealth_active(
        "http://target-a.com/scan"
    )

    assert active is True
    assert delay_range == (1.2, 2.8)


def test_stealth_inactive_different_host(monkeypatch):
    monkeypatch.delenv("PENTESTAGENT_STEALTH", raising=False)
    monkeypatch.setattr(
        notes_module,
        "get_all_notes_sync",
        lambda: {
            "waf_detected_target-a.com": {
                "category": "waf_detected",
                "metadata": {
                    "host": "target-a.com",
                    "delay_range": [1.2, 2.8],
                },
            }
        },
    )

    active, delay_range = executor_module._is_stealth_active(
        "http://target-b.com/scan"
    )

    assert active is False
    assert delay_range == (0.5, 2.0)


def test_legacy_key_still_matches(monkeypatch):
    monkeypatch.delenv("PENTESTAGENT_STEALTH", raising=False)
    monkeypatch.setattr(
        notes_module,
        "get_all_notes_sync",
        lambda: {
            "waf_detected": {
                "category": "waf_detected",
                "metadata": {"delay_range": [1.2, 2.8]},
            }
        },
    )

    active, delay_range = executor_module._is_stealth_active(
        "http://target-b.com/scan"
    )

    assert active is True
    assert delay_range == (1.2, 2.8)
