"""Neutral, transport-agnostic event bus (architecture joint A).

This is the single event source that all entrypoints (TUI / CLI / web / MCP)
subscribe to, replacing the three previously divergent mechanisms:

- TUI's ``interface/notifier.py`` callback registry
- web_server's queue/SSE ``EventBus``
- MCP's global ``_emit`` + ``_ui_hook``

Design choices:

- **Callback-based push.** Subscribers register a callable ``(Event) -> None``.
  A queue/SSE consumer (web) simply subscribes a callback that does
  ``queue.put_nowait(event)``; a TUI subscribes its render callback; MCP
  subscribes its outgoing emitter. One bus, many adapters.
- **Publisher never breaks.** A subscriber that raises is isolated — its
  exception is swallowed so one bad consumer cannot take down the agent loop
  (architecture invariant I3: events have a single source).
- **Thread-safe.** ``emit`` may be called from worker threads (tools run in
  executors), so subscriber bookkeeping is guarded by a lock.
"""

from __future__ import annotations

import threading
from dataclasses import dataclass, field
from typing import Any, Callable, List


@dataclass(slots=True)
class Event:
    """A structured event flowing through the bus."""

    type: str
    data: dict = field(default_factory=dict)
    source: str = ""


Subscriber = Callable[[Event], None]


class EventBus:
    """Single neutral event source. Push to callbacks; adapters bridge transports."""

    def __init__(self) -> None:
        self._subscribers: List[Subscriber] = []
        self._lock = threading.Lock()

    def subscribe(self, callback: Subscriber) -> Callable[[], None]:
        """Register *callback*; returns an unsubscribe function (idempotent)."""
        with self._lock:
            self._subscribers.append(callback)

        def _unsubscribe() -> None:
            with self._lock:
                try:
                    self._subscribers.remove(callback)
                except ValueError:
                    pass

        return _unsubscribe

    def emit(self, type: str, data: dict[str, Any] | None = None, source: str = "") -> Event:
        """Broadcast an event to every subscriber. Subscriber errors are isolated."""
        event = Event(type=type, data=dict(data or {}), source=source)
        with self._lock:
            targets = list(self._subscribers)
        for callback in targets:
            try:
                callback(event)
            except Exception:
                # I3: one faulty consumer must never break the publisher.
                continue
        return event

    def emit_event(self, event: Event) -> Event:
        """Broadcast a pre-built :class:`Event` (used when re-emitting)."""
        return self.emit(event.type, event.data, event.source)

    @property
    def subscriber_count(self) -> int:
        with self._lock:
            return len(self._subscribers)
