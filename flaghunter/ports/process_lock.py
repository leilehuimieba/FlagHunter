"""Process lock port contract.

Cross-process exclusive lock on a path. Closes the C-03 gap that
``AtomicFilePort`` (C-02) does not cover: per-process atomic writes
are safe, but two processes writing the same JSON snapshot at the
same time still race. The lock gives the caller an OS-level
advisory exclusive lock for the duration of a critical section so
``read-modify-replace`` cycles are serialised across processes.

The lock is **advisory**, not mandatory: a writer that ignores the
lock can still corrupt the file. This is documented in ADR 0001
and is the correct trade-off because mandatory locks are not
reliable on NFS / SMB and not portable to Windows in the same
shape. The caller contract is the ``with lock.acquire(path): ...``
pattern; code review is the second line of defence.

Boundary shape is ``Mapping[str, object]`` (per C-01 / C-02
precedent): the in-memory dataclass lives in the domain layer; a
future remote-lock adapter (etcd, consul, redis) can hydrate the
same wire shape without inheriting the OS-flavour implementation.
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import Protocol, runtime_checkable

# --- Boundary constants ------------------------------------------------------

PATH_KEY = "path"


@runtime_checkable
class ProcessLockPort(Protocol):
    """Cross-process advisory exclusive lock on a path.

    The lock is held for the lifetime of the returned
    :class:`LockHandle`; closing the handle (explicit ``release()``,
    ``with`` block exit, or process exit) releases it. Concurrent
    ``acquire`` calls on the same path block until the holder
    releases, unless ``blocking=False`` is passed — in which case
    the call returns ``None`` immediately if the lock is already
    held.
    """

    def acquire(
        self,
        path: Mapping[str, object],
        *,
        blocking: bool = True,
    ) -> "LockHandle | None":
        """Acquire an exclusive lock on ``path``.

        ``path`` MUST be a mapping with a ``"path"`` key carrying
        the lock target (str or os.PathLike). Returns a
        :class:`LockHandle` on success, or ``None`` when
        ``blocking=False`` and the lock is already held.

        Raises on I/O error (e.g. the sidecar lockfile cannot be
        created on the target filesystem).
        """
        ...


class LockHandle:
    """Handle returned by :meth:`ProcessLockPort.acquire`.

    Adapters may subclass this; the protocol only mandates the
    three methods below. The ``with`` block is the idiomatic way
    to bound a critical section:

    .. code-block:: python

        with lock.acquire(path) as handle:
            atomic_file.write_text(path, snapshot)
        # handle released here, even on exception

    Calling :meth:`release` after the handle is already released
    is a no-op (idempotent).
    """

    def release(self) -> None:
        """Release the lock. Idempotent."""
        ...

    def __enter__(self) -> "LockHandle": ...

    def __exit__(self, exc_type, exc, tb) -> None: ...
