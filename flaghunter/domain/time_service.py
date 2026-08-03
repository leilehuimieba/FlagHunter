"""Time service implementations.

Two adapters:

* :class:`SystemTimeService` — production. ``datetime.now(timezone.utc)``
  for the wall clock, ``time.monotonic()`` for durations.
* :class:`FixedTimeService` — tests. Accepts injected
  ``utc_now`` and ``monotonic_now`` values; ``elapsed_since``
  works against the injected clock.

The boundary is ``TimeServicePort`` (C-05 / ADR 0002).
"""

from __future__ import annotations

import time
from datetime import datetime, timezone
from typing import Callable, Optional


def _to_iso_z(dt: datetime) -> str:
    """Render an aware UTC datetime as the canonical ``...Z`` wire form."""
    iso = dt.astimezone(timezone.utc).isoformat()
    if iso.endswith("+00:00"):
        iso = iso[:-6] + "Z"
    return iso


class SystemTimeService:
    """Production :class:`TimeServicePort`.

    Wraps:
    * ``datetime.now(timezone.utc)`` for wall clock (always aware
      UTC, never naive);
    * ``time.monotonic()`` for duration math.
    """

    def utc_now(self) -> datetime:
        return datetime.now(timezone.utc)

    def utc_now_iso(self) -> str:
        return _to_iso_z(self.utc_now())

    def monotonic_now(self) -> float:
        return time.monotonic()

    def elapsed_since(self, start_monotonic: float) -> float:
        return self.monotonic_now() - start_monotonic


class FixedTimeService:
    """Test :class:`TimeServicePort` with injected clocks.

    Two injection styles are supported:

    * Pass ``utc_at`` / ``mono_at`` as ``datetime`` / ``float``
      for a single, fixed value;
    * Pass ``utc_factory`` / ``mono_factory`` as callables for
      an advancing clock (e.g. ``lambda: self._now += timedelta(...)``).
    """

    def __init__(
        self,
        *,
        utc_at: Optional[datetime] = None,
        mono_at: Optional[float] = None,
        utc_factory: Optional[Callable[[], datetime]] = None,
        mono_factory: Optional[Callable[[], float]] = None,
    ) -> None:
        if utc_at is not None and not isinstance(utc_at, datetime):
            raise ValueError("utc_at must be a datetime")
        if utc_at is not None and utc_at.tzinfo is None:
            raise ValueError("utc_at must be timezone-aware")
        if mono_at is not None and not isinstance(mono_at, (int, float)):
            raise ValueError("mono_at must be a number")
        if utc_at is not None and utc_factory is not None:
            raise ValueError("pass utc_at or utc_factory, not both")
        if mono_at is not None and mono_factory is not None:
            raise ValueError("pass mono_at or mono_factory, not both")

        self._utc_fixed = utc_at
        self._mono_fixed = float(mono_at) if mono_at is not None else None
        self._utc_factory = utc_factory
        self._mono_factory = mono_factory
        if utc_at is None and utc_factory is None:
            # Sensible default: a fixed aware UTC instant.
            self._utc_fixed = datetime(2026, 8, 4, 12, 0, 0, tzinfo=timezone.utc)
        if mono_at is None and mono_factory is None:
            # Sensible default: monotonic 1000.0.
            self._mono_fixed = 1000.0

    def utc_now(self) -> datetime:
        if self._utc_factory is not None:
            value = self._utc_factory()
        else:
            assert self._utc_fixed is not None  # for type-checker
            value = self._utc_fixed
        if not isinstance(value, datetime):
            raise RuntimeError("utc_factory must return a datetime")
        if value.tzinfo is None:
            raise RuntimeError("utc_now must be timezone-aware")
        return value

    def utc_now_iso(self) -> str:
        return _to_iso_z(self.utc_now())

    def monotonic_now(self) -> float:
        if self._mono_factory is not None:
            value = self._mono_factory()
        else:
            assert self._mono_fixed is not None  # for type-checker
            value = self._mono_fixed
        if not isinstance(value, (int, float)):
            raise RuntimeError("mono_factory must return a number")
        return float(value)

    def elapsed_since(self, start_monotonic: float) -> float:
        return self.monotonic_now() - float(start_monotonic)
