"""Identity service implementations.

Two adapters:

* :class:`UuidIdentityService` — production. ``uuid.uuid4().hex``,
  no truncation, optional display prefix.
* :class:`InMemoryIdentityService` — tests. Deterministic counter
  + configurable prefix; emits the same shape the production
  service would, so tests can assert format without surprises.

The boundary is ``IdentityServicePort`` (C-05 / ADR 0002).
"""

from __future__ import annotations

import threading
import uuid
from typing import Optional

_HEX_LEN = 32  # uuid4().hex length


def _validate_prefix(prefix: str) -> str:
    """Strip and validate a prefix. Returns the cleaned prefix.

    Empty / whitespace-only prefixes are normalised to ``None``
    so the production service emits an unprefixed hex string
    instead of ``"_abcd..."``.
    """
    cleaned = prefix.strip()
    if not cleaned:
        raise ValueError("prefix must be a non-empty, non-whitespace string")
    return cleaned


class UuidIdentityService:
    """Production :class:`IdentityServicePort` backed by ``uuid.uuid4``.

    Every call returns a fresh ``uuid.uuid4().hex`` (32 lower-case
    hex characters, 128 bits of entropy). With an optional
    display prefix the format is ``f"{prefix}_{hex}"``.
    """

    def new_id(self, prefix: Optional[str] = None) -> str:
        hex_id = uuid.uuid4().hex
        if prefix is None:
            return hex_id
        return f"{_validate_prefix(prefix)}_{hex_id}"

    def new_id_with_kind(self, kind: str) -> str:
        return self.new_id(prefix=kind)


class InMemoryIdentityService:
    """Deterministic :class:`IdentityServicePort` for tests.

    Produces ids of the same shape as :class:`UuidIdentityService`
    so tests can assert format without surprises, but the
    underlying "random" bytes are a counter — tests can predict
    the *number* of distinct ids and the *order*.

    Thread-safe; the counter is guarded by a lock. The
    ``seed`` parameter is accepted so a test that wants
    fully-reproducible ids across runs can pass a fixed hex
    string; otherwise the counter starts at zero and the test
    just sees ``counter_000...0``, ``counter_000...1``, etc.
    """

    def __init__(self, *, seed: str = "0123456789abcdef0123456789abcdef") -> None:
        if len(seed) != _HEX_LEN or any(c not in "0123456789abcdef" for c in seed):
            raise ValueError(
                f"seed must be {_HEX_LEN} lower-case hex chars, got {seed!r}"
            )
        self._counter = 0
        self._lock = threading.Lock()
        self._seed = seed

    def new_id(self, prefix: Optional[str] = None) -> str:
        with self._lock:
            # Take the trailing segment of the counter, zero-padded
            # to ``_HEX_LEN``. The seed's leading bytes carry
            # visual identity; the trailing bytes carry the
            # counter. This keeps every emitted id the correct
            # length while staying deterministic.
            counter = self._counter
            self._counter += 1
        tail = format(counter, "x").rjust(_HEX_LEN, "0")
        head = self._seed[: _HEX_LEN - len(tail)] if len(tail) < _HEX_LEN else ""
        hex_id = (head + tail)[-_HEX_LEN:] if head else tail
        # Pad back up to _HEX_LEN if the counter is very small.
        if len(hex_id) < _HEX_LEN:
            hex_id = hex_id.rjust(_HEX_LEN, "0")
        if prefix is None:
            return hex_id
        return f"{_validate_prefix(prefix)}_{hex_id}"

    def new_id_with_kind(self, kind: str) -> str:
        return self.new_id(prefix=kind)

    def reset(self) -> None:
        with self._lock:
            self._counter = 0
