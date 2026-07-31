"""A-07 / A-08 — remote control-plane access policy (F-03 / F-04).

The pure-stdlib policy in ``flaghunter.config.remote_access`` decides when the
Web Console and MCP network transport must authenticate. It encodes:

  * loopback bind = trusted local, token optional;
  * any non-loopback bind (incl. 0.0.0.0 / ::) = remote profile, token required
    or the server refuses to start (fail-closed);
  * a session ID is never an identity — only a matching bearer token authorizes.
"""

from __future__ import annotations

import pytest

from flaghunter.config import remote_access as ra


@pytest.mark.parametrize(
    "host,expected",
    [
        ("127.0.0.1", True),
        ("127.0.0.5", True),
        ("::1", True),
        ("[::1]", True),
        ("localhost", True),
        ("0.0.0.0", False),  # all-interfaces — NOT loopback
        ("::", False),
        ("192.168.1.10", False),
        ("10.0.0.4", False),
        ("example.com", False),  # unresolvable-as-loopback → remote (fail safe)
        ("", False),
        (None, False),
    ],
)
def test_is_loopback_host(host, expected):
    assert ra.is_loopback_host(host) is expected


def test_non_loopback_without_token_is_fail_closed():
    with pytest.raises(ra.RemoteAuthConfigError):
        ra.require_token_for_bind("0.0.0.0", None, surface="Web Console")
    with pytest.raises(ra.RemoteAuthConfigError):
        ra.require_token_for_bind("192.168.1.5", "   ", surface="MCP SSE")


def test_non_loopback_with_token_is_allowed():
    # Does not raise.
    ra.require_token_for_bind("0.0.0.0", "s3cret", surface="Web Console")


def test_loopback_without_token_is_allowed():
    # Local dev needs no token.
    ra.require_token_for_bind("127.0.0.1", None, surface="Web Console")


def test_token_enforced_matrix():
    # Loopback + no token → open.
    assert ra.token_enforced("127.0.0.1", None) is False
    # Loopback + token → enforced (opt-in even locally).
    assert ra.token_enforced("127.0.0.1", "t") is True
    # Non-loopback always enforced.
    assert ra.token_enforced("0.0.0.0", None) is True
    assert ra.token_enforced("10.0.0.1", "t") is True


def test_extract_bearer():
    assert ra.extract_bearer("Bearer abc123") == "abc123"
    assert ra.extract_bearer("bearer abc123") == "abc123"
    assert ra.extract_bearer("BEARER   spaced ") == "spaced"
    assert ra.extract_bearer("Basic abc123") is None
    assert ra.extract_bearer("abc123") is None
    assert ra.extract_bearer(None) is None


def test_token_matches_is_constant_time_and_strict():
    assert ra.token_matches("abc", "abc") is True
    assert ra.token_matches("abc", "abcd") is False
    assert ra.token_matches("", "abc") is False
    assert ra.token_matches("abc", "") is False
    assert ra.token_matches(None, "abc") is False
    assert ra.token_matches("abc", None) is False


def test_is_authorized_accepts_each_credential_channel():
    expected = "correct-horse"
    assert ra.is_authorized(header_authorization="Bearer correct-horse", expected=expected)
    assert ra.is_authorized(header_token="correct-horse", expected=expected)
    assert ra.is_authorized(query_token="correct-horse", expected=expected)
    # Wrong / missing credentials.
    assert not ra.is_authorized(header_authorization="Bearer nope", expected=expected)
    assert not ra.is_authorized(header_token="nope", expected=expected)
    assert not ra.is_authorized(expected=expected)
    # A session-id-like value is not a token.
    assert not ra.is_authorized(header_token="some-session-uuid", expected=expected)


def test_env_token_resolution_prefers_specific_then_shared(monkeypatch):
    monkeypatch.delenv(ra.WEB_AUTH_TOKEN_ENV, raising=False)
    monkeypatch.delenv(ra.MCP_AUTH_TOKEN_ENV, raising=False)
    monkeypatch.delenv(ra.SHARED_AUTH_TOKEN_ENV, raising=False)
    assert ra.resolve_web_auth_token() is None
    assert ra.resolve_mcp_auth_token() is None

    monkeypatch.setenv(ra.SHARED_AUTH_TOKEN_ENV, "shared")
    assert ra.resolve_web_auth_token() == "shared"
    assert ra.resolve_mcp_auth_token() == "shared"

    monkeypatch.setenv(ra.WEB_AUTH_TOKEN_ENV, "web-only")
    monkeypatch.setenv(ra.MCP_AUTH_TOKEN_ENV, "mcp-only")
    assert ra.resolve_web_auth_token() == "web-only"
    assert ra.resolve_mcp_auth_token() == "mcp-only"
