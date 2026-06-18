"""Hybrid runtime: a curl-only primary backend augmented with a local browser.

``SSHRuntime`` and ``DockerRuntime`` execute the full Kali toolchain and hold
the network position, but their ``browser_action`` is a lightweight ``curl``
fetch — no rendered DOM, no JS, no real cookies. ``LocalRuntime`` is the only
backend with Playwright.

``HybridBrowserRuntime`` wraps a curl-only *primary* and transparently delegates
everything except ``browser_action``. For browser work it routes per **target
host**: on first contact it probes — from the local host — whether the target is
reachable; if so the whole browse session for that host runs on a lazily-started
``LocalRuntime`` (rendered DOM + real cookies, fixing the Kali-backend
``get_cookies`` gap); if not (e.g. a target only reachable from the VM's network)
it falls back to the primary's ``curl`` path. Decisions are cached per host and
downgraded on mid-session failure, so the default behaviour is never worse than
the primary alone.
"""

from __future__ import annotations

import logging
from typing import Any, Callable, Optional
from urllib.parse import urlparse

from .runtime import CommandResult, Runtime

logger = logging.getLogger(__name__)

# Browser sub-actions that genuinely need a rendered DOM / real session and are
# therefore worth routing to a local Playwright engine when the target is
# reachable. Lightweight metadata actions ("diagnose") are handled separately.
_RENDER_WORTHY_ACTIONS = frozenset(
    {"navigate", "get_content", "get_links", "get_forms", "get_cookies", "screenshot"}
)

_UNREACHABLE_HINTS = (
    "connect",
    "timeout",
    "timed out",
    "refused",
    "unreachable",
    "name or service",
    "could not resolve",
    "net::err",
)


class HybridBrowserRuntime(Runtime):
    """Wrap a curl-only *primary* runtime and add a reachability-routed browser."""

    def __init__(
        self,
        primary: Runtime,
        browser_factory: Optional[Callable[[], Runtime]] = None,
        *,
        probe_timeout: float = 3.0,
        mcp_manager=None,
    ):
        super().__init__(mcp_manager)
        self.primary = primary
        self._probe_timeout = probe_timeout
        if browser_factory is None:
            from .runtime import LocalRuntime

            browser_factory = LocalRuntime
        self._browser_factory = browser_factory
        self._local: Optional[Runtime] = None
        self._local_started = False
        # host:port -> "local" | "primary"
        self._host_engine: dict[str, str] = {}
        self._last_host_key: Optional[str] = None

    # ------------------------------------------------------------------ #
    # Transparent delegation
    # ------------------------------------------------------------------ #
    def __getattr__(self, name: str) -> Any:
        # Only invoked when normal attribute lookup fails. Delegate unknown
        # attributes (host/port/user, copy_to_container, ...) to the primary so
        # callers and runtime_info keep working unchanged. Guard against the
        # pre-__init__ window where ``primary`` is not yet bound.
        primary = object.__getattribute__(self, "__dict__").get("primary")
        if primary is None:
            raise AttributeError(name)
        return getattr(primary, name)

    async def start(self):
        # Local browser is started lazily on first reachable target.
        await self.primary.start()

    async def stop(self):
        if self._local is not None and self._local_started:
            try:
                await self._local.stop()
            except Exception as exc:  # pragma: no cover - cleanup best-effort
                logger.exception("Failed to stop local browser runtime: %s", exc)
            finally:
                self._local_started = False
        await self.primary.stop()

    async def execute_command(self, command: str, timeout: int = 300) -> CommandResult:
        return await self.primary.execute_command(command, timeout=timeout)

    async def proxy_action(self, action: str, **kwargs) -> dict:
        return await self.primary.proxy_action(action, **kwargs)

    async def is_running(self) -> bool:
        return await self.primary.is_running()

    async def get_status(self) -> dict:
        status = await self.primary.get_status()
        if isinstance(status, dict):
            status = {**status, "hybrid_browser": True}
        return status

    # ------------------------------------------------------------------ #
    # Browser routing
    # ------------------------------------------------------------------ #
    async def browser_action(self, action: str, **kwargs) -> dict:
        if action == "diagnose":
            # Conservative: advertise the primary's contract (callers gate on
            # supported_actions, which the primary already lists). The rendered
            # path is opportunistic and reported per-host once a session starts.
            result = await self.primary.browser_action(action, **kwargs)
            if isinstance(result, dict):
                result = {**result, "hybrid_browser": True}
            return result

        url = kwargs.get("url") or ""
        host_key = self._resolve_host_key(url) if url else self._last_host_key
        if url and host_key:
            self._last_host_key = host_key

        engine = await self._engine_for(host_key, url, action)

        if engine == "local":
            try:
                local = await self._ensure_local()
                result = await local.browser_action(action, **kwargs)
            except Exception as exc:
                logger.warning(
                    "Local browser engine failed for %s (%s); falling back to primary.",
                    host_key,
                    exc,
                )
                if host_key:
                    self._host_engine[host_key] = "primary"
                return await self.primary.browser_action(action, **kwargs)

            if self._looks_unreachable(result):
                logger.info(
                    "Local browser engine could not reach %s; downgrading to primary.",
                    host_key,
                )
                if host_key:
                    self._host_engine[host_key] = "primary"
                return await self.primary.browser_action(action, **kwargs)
            return result

        return await self.primary.browser_action(action, **kwargs)

    async def _engine_for(
        self, host_key: Optional[str], url: str, action: str
    ) -> str:
        if not host_key:
            return "primary"
        cached = self._host_engine.get(host_key)
        if cached is not None:
            return cached
        # Only pay a probe for a render-worthy action that carries a URL.
        if not url or action not in _RENDER_WORTHY_ACTIONS:
            return "primary"
        reachable = await self._probe_local_reachable(url)
        engine = "local" if reachable else "primary"
        self._host_engine[host_key] = engine
        return engine

    async def _ensure_local(self) -> Runtime:
        if self._local is None:
            self._local = self._browser_factory()
        if not self._local_started:
            await self._local.start()
            self._local_started = True
        return self._local

    async def _probe_local_reachable(self, url: str) -> bool:
        """Return True if the target answers an HTTP request from the local host.

        Any HTTP response (including 4xx/5xx) counts as reachable — httpx only
        raises on connect/timeout/DNS failures, which is exactly the
        "local host can't reach it" signal we want.
        """
        try:
            import httpx
        except ImportError:
            return False
        for method in ("HEAD", "GET"):
            try:
                async with httpx.AsyncClient(
                    timeout=self._probe_timeout,
                    follow_redirects=False,
                    verify=False,
                ) as client:
                    await client.request(method, url)
                return True
            except Exception:
                continue
        return False

    @staticmethod
    def _resolve_host_key(url: str) -> Optional[str]:
        try:
            parsed = urlparse(url if "://" in url else f"http://{url}")
        except Exception:
            return None
        host = (parsed.hostname or "").lower()
        if not host:
            return None
        port = parsed.port or (443 if parsed.scheme == "https" else 80)
        return f"{host}:{port}"

    @staticmethod
    def _looks_unreachable(result: Any) -> bool:
        if not isinstance(result, dict):
            return False
        err = str(result.get("error") or "").lower()
        if not err:
            return False
        return any(hint in err for hint in _UNREACHABLE_HINTS)
