"""Atomic file port contract.

Atomic file writes are the low-level primitive every higher-level
state store (C-04 checksum/sequence, C-10 state store adapter,
conversation store, checkpoint store, harness ledger) needs to
avoid producing half-written files on crash, signal, or power loss.

The contract intentionally stays at the **path + text** level rather
than run-id-keyed or domain-keyed: callers below the application
layer (e.g. the future state store adapter, the
``ConversationStore``, the ``CheckpointStore``) need a generic
primitive they can call against any path. Higher-level state stores
build their own keying on top of this port.

Boundary shape is ``Mapping[str, object]`` (see C-01 precedent): the
in-memory dataclass lives in the domain layer; future JSON-file or
remote-storage adapters can hydrate the same wire shape without
inheriting any implementation.
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import Protocol, runtime_checkable


@runtime_checkable
class AtomicFilePort(Protocol):
    """Atomic text-file read/write primitive.

    All implementations MUST guarantee that ``read_text`` never
    observes a half-written file: either the previous content is
    still visible, or the new content is fully visible. Half-written
    content must never leak to readers, even across process crash,
    signal, or power loss (modulo the OS / filesystem guarantees
    documented at the adapter level).
    """

    def write_text(
        self,
        path: Mapping[str, object],
        content: str,
    ) -> None:
        """Write ``content`` to ``path`` atomically.

        ``path`` MUST be a mapping with a ``"path"`` key carrying the
        destination path (string or os.PathLike). The call MUST
        either succeed (the file is fully written and visible to
        subsequent readers) or raise without leaving any observable
        half-file at the destination. Any temporary sidecar files
        MUST be cleaned up on failure.

        Optional mapping keys:

        * ``"encoding"`` (str, default ``"utf-8"``): text encoding.
        * ``"overwrite"`` (bool, default ``True``): if ``False``,
          raise when the destination already exists instead of
          replacing it.
        * ``"fsync"`` (bool, default ``True``): request the
          implementation to flush + fsync before the atomic
          rename. Adapters that cannot fsync MUST document the
          weaker durability they offer.
        """
        ...

    def read_text(
        self,
        path: Mapping[str, object],
    ) -> str | None:
        """Read the file at ``path`` and return its text content.

        Return ``None`` when the file does not exist. Raise on any
        I/O or decoding error — callers are responsible for
        deciding whether a missing file is fatal.
        """
        ...

    def exists(self, path: Mapping[str, object]) -> bool:
        """Return ``True`` iff a file exists at ``path``."""
        ...

    def remove(self, path: Mapping[str, object]) -> bool:
        """Remove the file at ``path``.

        Return ``True`` if a file was removed, ``False`` if no file
        existed. Raise on any other I/O error (e.g. permission
        denied). MUST never partially remove.
        """
        ...
