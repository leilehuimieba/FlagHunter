"""Identity service port contract.

Closes the C-05 gap: at least three different ID-generation
patterns are in production today (truncated UUID, full UUID,
sequential counter). The boundary makes the format explicit and
injectable so tests can produce deterministic ids without
monkey-patching ``uuid`` globals.

See ADR 0002 for the policy: new ids are **full 32 hex chars**
(no truncation) with an optional display prefix; the prefix is
display only, the canonical id is the hex suffix.
"""

from __future__ import annotations

from typing import Protocol, runtime_checkable


@runtime_checkable
class IdentityServicePort(Protocol):
    """Single source of identity for the rest of the system.

    All new ids are produced by calling this port; production
    code MUST NOT call ``uuid.uuid4`` directly. The optional
    ``prefix`` is display only: ``f"{prefix}_{uuid4_hex}"`` or
    just ``uuid4_hex`` when ``prefix`` is ``None``.
    """

    def new_id(self, prefix: str | None = None) -> str:
        """Return a fresh, globally-unique id.

        The returned string is either:
          * ``uuid4_hex`` (32 hex chars, lower-case) when
            ``prefix`` is ``None``;
          * ``f"{prefix}_{uuid4_hex}"`` when ``prefix`` is given.
        """
        ...

    def new_id_with_kind(self, kind: str) -> str:
        """Semantic alias: ``self.new_id(prefix=kind)``.

        Provided as a convenience for call sites that always pass
        a non-empty ``kind`` (e.g. ``"task"``, ``"run"``,
        ``"session"``, ``"trace"``). The kind is the prefix.
        """
        ...
