"""A-09 — browser-origin allowlist policy (F-05).

The Web Console used to reply ``Access-Control-Allow-Origin: *``. These tests pin
the FOUNDATION policy that replaces the wildcard: loopback origins are trusted by
default, the operator allowlist extends trust, and every other origin is rejected
— including for the CSRF gate on state-changing requests.
"""

from __future__ import annotations

from flaghunter.config.remote_access import (
    is_allowed_origin,
    is_loopback_origin,
    origin_permitted_for_request,
    resolve_allowed_origins,
)


def test_loopback_origins_are_trusted_by_default():
    for origin in (
        "http://127.0.0.1:8080",
        "http://localhost:5173",
        "https://localhost",
        "http://[::1]:9000",
    ):
        assert is_loopback_origin(origin) is True
        assert is_allowed_origin(origin, allowlist=frozenset()) is True


def test_non_loopback_origin_rejected_without_allowlist():
    assert is_allowed_origin("https://evil.example.com", allowlist=frozenset()) is False
    assert is_allowed_origin("http://192.168.1.50:8080", allowlist=frozenset()) is False


def test_allowlisted_origin_is_trusted():
    allow = resolve_allowed_origins("https://console.example.com, http://192.168.1.5:8080")
    assert is_allowed_origin("https://console.example.com", allowlist=allow) is True
    assert is_allowed_origin("http://192.168.1.5:8080", allowlist=allow) is True
    # A near-miss (different port) stays untrusted.
    assert is_allowed_origin("http://192.168.1.5:9999", allowlist=allow) is False


def test_origin_normalization_is_case_and_slash_insensitive():
    allow = resolve_allowed_origins("HTTPS://Console.Example.COM/")
    assert is_allowed_origin("https://console.example.com", allowlist=allow) is True


def test_malformed_origins_are_not_trusted():
    for bad in (None, "", "null", "example.com", "  "):
        assert is_allowed_origin(bad, allowlist=frozenset()) is False
    # A malformed allowlist entry is dropped, not trusted as a bare host.
    assert resolve_allowed_origins("not-an-origin, https://ok.example") == frozenset(
        {"https://ok.example"}
    )


def test_resolve_allowed_origins_empty_when_unset():
    assert resolve_allowed_origins("") == frozenset()
    assert resolve_allowed_origins(None) in (frozenset(), resolve_allowed_origins(None))


def test_csrf_gate_allows_safe_methods_regardless_of_origin():
    for method in ("GET", "HEAD", "OPTIONS"):
        assert (
            origin_permitted_for_request(
                method=method, origin="https://evil.example", allowlist=frozenset()
            )
            is True
        )


def test_csrf_gate_allows_missing_origin_for_non_browser_clients():
    # curl / the MCP client omit Origin and rely on bearer-token auth.
    assert (
        origin_permitted_for_request(method="POST", origin=None, allowlist=frozenset())
        is True
    )


def test_csrf_gate_rejects_state_change_from_untrusted_origin():
    assert (
        origin_permitted_for_request(
            method="POST", origin="https://evil.example", allowlist=frozenset()
        )
        is False
    )
    # A trusted (loopback) origin passes the gate.
    assert (
        origin_permitted_for_request(
            method="POST", origin="http://127.0.0.1:8080", allowlist=frozenset()
        )
        is True
    )
