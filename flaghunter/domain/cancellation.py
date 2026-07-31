"""Propagatable cancellation scopes + registry (A-02 · §1.2 ① · F-01/F-02).

Today "stop" (Web) and "cancel" (MCP) mostly flip a status field and persist it:
the background daemon thread and the CTF dispatcher's long ``await`` keep running,
so an operator who sees ``stopped``/``cancelled`` can still watch tools fire. The
missing piece is a *handle* the running work can observe. This module provides it:

  * :class:`CancellationToken` — a thread-safe, poll-based abort flag that works
    identically from a sync daemon thread (Web) and an async dispatcher loop (MCP);
  * :class:`CancellationScope` — a token plus parent/child links so cancelling a
    parent propagates to every descendant ("可传播的 cancellation scope");
  * :class:`CancellationRegistry` — a task-id → scope map so any control surface
    can cancel a task by id.

It is a pure DOMAIN primitive (stdlib only, no FlagHunter imports) and changes no
behaviour on its own. A-03/A-04 register a scope when a task starts and have the
worker call :meth:`CancellationToken.raise_if_cancelled` at each action boundary,
so after cancellation the number of further actions is zero.
"""

from __future__ import annotations

import threading
from typing import Iterator


SCHEMA_VERSION = "task.cancellation.v1"

_DEFAULT_REASON = "cancelled"


class TaskCancelled(Exception):
    """Raised by cooperative workers when their token has been cancelled."""

    def __init__(self, reason: str = _DEFAULT_REASON) -> None:
        super().__init__(reason)
        self.reason = reason


class CancellationToken:
    """A thread-safe abort flag pollable from sync and async code alike.

    Cancellation is one-way and idempotent: the first :meth:`cancel` records the
    reason and latches the flag; later calls are no-ops. Cooperative workers poll
    :attr:`cancelled` or call :meth:`raise_if_cancelled` between actions, and may
    :meth:`wait` on the underlying event for a cancellable sleep.
    """

    __slots__ = ("_event", "_reason", "_lock")

    def __init__(self) -> None:
        self._event = threading.Event()
        self._reason = _DEFAULT_REASON
        self._lock = threading.Lock()

    def cancel(self, reason: str = _DEFAULT_REASON) -> bool:
        """Latch cancellation. Returns True if this call was the one that set it."""
        with self._lock:
            if self._event.is_set():
                return False
            self._reason = reason or _DEFAULT_REASON
            self._event.set()
            return True

    @property
    def cancelled(self) -> bool:
        return self._event.is_set()

    @property
    def reason(self) -> str:
        return self._reason

    def raise_if_cancelled(self) -> None:
        """Raise :class:`TaskCancelled` if cancellation has been requested."""
        if self._event.is_set():
            raise TaskCancelled(self._reason)

    def wait(self, timeout: float | None = None) -> bool:
        """Block until cancelled or ``timeout`` elapses (a cancellable sleep).

        Returns True if cancellation fired, False on timeout. Use in place of
        ``time.sleep`` inside a worker so a pending cancel wakes it immediately.
        """
        return self._event.wait(timeout)


class CancellationScope:
    """A cancellation token with parent/child links for propagation.

    Cancelling a scope cancels its whole subtree. A scope also reports itself as
    cancelled if any ancestor was cancelled, so a freshly created child of an
    already-cancelled parent starts cancelled.
    """

    __slots__ = ("task_id", "token", "_parent", "_children", "_lock")

    def __init__(
        self, task_id: str = "", parent: "CancellationScope | None" = None
    ) -> None:
        self.task_id = task_id
        self.token = CancellationToken()
        self._parent = parent
        self._children: list[CancellationScope] = []
        self._lock = threading.Lock()
        if parent is not None:
            parent._add_child(self)
            # Inherit an already-latched parent cancellation immediately.
            if parent.cancelled:
                self.cancel(parent.token.reason)

    def _add_child(self, child: "CancellationScope") -> None:
        with self._lock:
            self._children.append(child)

    def child(self, task_id: str = "") -> "CancellationScope":
        """Create a linked child scope; cancelling self cancels it too."""
        return CancellationScope(task_id=task_id, parent=self)

    @property
    def cancelled(self) -> bool:
        if self.token.cancelled:
            return True
        parent = self._parent
        return parent is not None and parent.cancelled

    def cancel(self, reason: str = _DEFAULT_REASON) -> bool:
        """Cancel this scope and propagate to the entire subtree."""
        newly = self.token.cancel(reason)
        with self._lock:
            children = list(self._children)
        for child in children:
            child.cancel(reason)
        return newly

    def raise_if_cancelled(self) -> None:
        if self.cancelled:
            raise TaskCancelled(self.token.reason)


class CancellationRegistry:
    """Thread-safe map of task-id → :class:`CancellationScope`.

    A control surface opens a scope when a task starts, the worker observes the
    scope's token, and :meth:`cancel` aborts a task by id from anywhere.
    """

    def __init__(self) -> None:
        self._scopes: dict[str, CancellationScope] = {}
        self._lock = threading.Lock()

    def open(self, task_id: str) -> CancellationScope:
        """Register (or return the existing) scope for ``task_id``."""
        with self._lock:
            scope = self._scopes.get(task_id)
            if scope is None:
                scope = CancellationScope(task_id=task_id)
                self._scopes[task_id] = scope
            return scope

    def get(self, task_id: str) -> CancellationScope | None:
        with self._lock:
            return self._scopes.get(task_id)

    def cancel(self, task_id: str, reason: str = _DEFAULT_REASON) -> bool:
        """Cancel a task's scope by id. Returns False if the id is unknown."""
        scope = self.get(task_id)
        if scope is None:
            return False
        scope.cancel(reason)
        return True

    def close(self, task_id: str) -> None:
        """Drop a task's scope once it has reached a terminal state."""
        with self._lock:
            self._scopes.pop(task_id, None)

    def active_ids(self) -> list[str]:
        """Ids of registered scopes that have not been cancelled."""
        with self._lock:
            return [tid for tid, s in self._scopes.items() if not s.cancelled]

    def __len__(self) -> int:
        with self._lock:
            return len(self._scopes)

    def __iter__(self) -> Iterator[str]:
        with self._lock:
            return iter(list(self._scopes))


# --- process-wide default registry ------------------------------------------
_REGISTRY = CancellationRegistry()


def get_cancellation_registry() -> CancellationRegistry:
    """Return the process-wide default cancellation registry."""
    return _REGISTRY
