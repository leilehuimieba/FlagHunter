"""Remote control-plane access policy (A-07 / A-08 · F-03 / F-04).

Pure-stdlib policy shared by the Web Console (``interface.web_server``) and the
MCP network transport (``mcp.server``). It has **no** aiohttp / framework
dependency, so it stays in the FOUNDATION layer (``flaghunter.config``) and each
ENTRY surface wraps it in its own middleware.

Model (总纲 §8.1 / §900–§901):

* The control plane binds **loopback by default**; a loopback bind is a trusted
  local-dev surface and does **not** require a token (one may still be set to
  opt in to enforcement even locally).
* **Any non-loopback bind** — a concrete LAN/public IP, or ``0.0.0.0`` / ``::``
  which expose every interface — is a *remote profile*: it **must** have a token
  configured, or the server refuses to start (fail-closed). This closes the
  F-03/F-04 exposure where a non-loopback bind served high-privilege routes with
  no authentication.
* A session ID correlates a session; it is **never** an identity (§901). Token
  verification is independent of any session handling.
"""

from __future__ import annotations

import hmac
import ipaddress
import os

# Per-surface token env vars, each with a shared fallback so an operator can set
# one token for the whole control plane or scope them independently.
WEB_AUTH_TOKEN_ENV = "FLAGHUNTER_WEB_AUTH_TOKEN"
MCP_AUTH_TOKEN_ENV = "FLAGHUNTER_MCP_AUTH_TOKEN"
SHARED_AUTH_TOKEN_ENV = "FLAGHUNTER_REMOTE_AUTH_TOKEN"

# Header names the ENTRY surfaces read for a bearer credential.
AUTHORIZATION_HEADER = "Authorization"
TOKEN_HEADER = "X-FlagHunter-Token"

_LOOPBACK_HOSTNAMES = {"localhost", "localhost.localdomain", "ip6-localhost"}


class RemoteAuthConfigError(RuntimeError):
    """A non-loopback bind was requested without a configured auth token."""


def _clean(value: str | None) -> str | None:
    if value is None:
        return None
    stripped = value.strip()
    return stripped or None


def is_loopback_host(host: str | None) -> bool:
    """Return True iff *host* is a loopback address/name safe to serve without auth.

    ``0.0.0.0`` / ``::`` (the unspecified / all-interfaces addresses) are
    explicitly **not** loopback — they expose external interfaces and therefore
    require authentication. An unresolvable hostname is treated as remote (we
    cannot prove it is loopback, so we fail safe).
    """
    host = _clean(host)
    if host is None:
        return False
    host = host.strip("[]")  # tolerate bracketed IPv6 like "[::1]"
    if host.lower() in _LOOPBACK_HOSTNAMES:
        return True
    try:
        ip = ipaddress.ip_address(host)
    except ValueError:
        return False
    if ip.is_unspecified:  # 0.0.0.0 or ::
        return False
    return ip.is_loopback


def resolve_web_auth_token() -> str | None:
    """The Web Console token: per-surface env var, else the shared fallback."""
    return _clean(os.environ.get(WEB_AUTH_TOKEN_ENV)) or _clean(
        os.environ.get(SHARED_AUTH_TOKEN_ENV)
    )


def resolve_mcp_auth_token() -> str | None:
    """The MCP network token: per-surface env var, else the shared fallback."""
    return _clean(os.environ.get(MCP_AUTH_TOKEN_ENV)) or _clean(
        os.environ.get(SHARED_AUTH_TOKEN_ENV)
    )


def require_token_for_bind(host: str | None, token: str | None, *, surface: str) -> None:
    """Fail-closed bootstrap guard: a non-loopback bind must carry a token.

    Raises :class:`RemoteAuthConfigError` when *host* is non-loopback and no
    token is configured. Loopback binds pass unconditionally.
    """
    if not is_loopback_host(host) and _clean(token) is None:
        raise RemoteAuthConfigError(
            f"{surface} refuses to bind non-loopback host {host!r} without an auth "
            f"token. Set {WEB_AUTH_TOKEN_ENV}/{MCP_AUTH_TOKEN_ENV} (or "
            f"{SHARED_AUTH_TOKEN_ENV}), or bind a loopback host (127.0.0.1) for "
            f"local-only use."
        )


def token_enforced(host: str | None, token: str | None) -> bool:
    """Whether requests must present a valid bearer token.

    Enforcement is on when a token is configured **or** the bind is non-loopback.
    After :func:`require_token_for_bind` has run at bootstrap, a non-loopback
    bind is guaranteed to have a token, so this reduces to "a token exists".
    """
    return _clean(token) is not None or not is_loopback_host(host)


def extract_bearer(header_value: str | None) -> str | None:
    """Parse ``Authorization: Bearer <token>`` → ``<token>`` (case-insensitive)."""
    value = _clean(header_value)
    if value is None:
        return None
    parts = value.split(None, 1)
    if len(parts) == 2 and parts[0].lower() == "bearer":
        return _clean(parts[1])
    return None


def token_matches(provided: str | None, expected: str | None) -> bool:
    """Constant-time compare of a provided credential against the expected token."""
    provided = _clean(provided)
    expected = _clean(expected)
    if not expected or not provided:
        return False
    return hmac.compare_digest(provided, expected)


def is_authorized(
    *,
    header_authorization: str | None = None,
    header_token: str | None = None,
    query_token: str | None = None,
    expected: str | None,
) -> bool:
    """Return True iff any presented credential matches *expected*.

    Accepts, in order, ``Authorization: Bearer <t>``, the ``X-FlagHunter-Token``
    header, or a ``token`` query parameter. The query parameter exists only so a
    browser ``EventSource`` (which cannot set request headers) can authenticate
    the SSE stream; header credentials are preferred everywhere else.
    """
    if token_matches(extract_bearer(header_authorization), expected):
        return True
    if token_matches(header_token, expected):
        return True
    return token_matches(query_token, expected)
