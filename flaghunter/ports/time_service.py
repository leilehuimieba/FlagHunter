"""Time service port contract.

Closes the C-05 gap: at least fifteen naive ``datetime.now()``
call sites mix with four aware ``datetime.now(timezone.utc)``
sites, and ``time.time()`` is used for both wall-clock and
duration math (the latter is wrong across DST). The boundary
makes the policy explicit:

* ``utc_now()`` — always aware UTC. Use for persistence and
  ordering.
* ``utc_now_iso()`` — canonical wire form
  (``...Z`` suffix). Use for JSON serialisation.
* ``monotonic_now()`` — for durations. Never subtract from a
  wall clock.
* ``elapsed_since(start)`` — convenience for the common
  duration-since-X pattern.

See ADR 0002 for the rationale.
"""

from __future__ import annotations

from datetime import datetime
from typing import Protocol, runtime_checkable


@runtime_checkable
class TimeServicePort(Protocol):
    """Single source of timestamps and duration math."""

    def utc_now(self) -> datetime:
        """Return the current wall-clock as a timezone-aware UTC
        ``datetime``. NEVER naive. Callers MAY serialise via
        ``utc_now_iso()`` for the canonical wire form.
        """
        ...

    def utc_now_iso(self) -> str:
        """Return ``self.utc_now().isoformat()`` with the trailing
        ``+00:00`` rewritten to ``Z`` — the canonical wire form
        for serialising to JSON / NDJSON. Example:
        ``"2026-08-04T12:34:56.789012Z"``.
        """
        ...

    def monotonic_now(self) -> float:
        """Return a monotonically non-decreasing float suitable
        for measuring elapsed time. NEVER use ``time.time()``
        for durations; only the system clock for absolute
        instants.
        """
        ...

    def elapsed_since(self, start_monotonic: float) -> float:
        """Convenience: ``self.monotonic_now() - start_monotonic``.

        Use this for any "how long has X been running" math.
        """
        ...
