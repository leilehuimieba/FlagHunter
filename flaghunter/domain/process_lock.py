"""Process lock domain types and in-memory / filesystem implementations.

Companion to ADR 0001 (single-writer for JSON snapshots,
O_APPEND for NDJSON). Provides:

* :class:`LockHandle` — concrete base handle; the in-memory and
  filesystem adapters use specialised subclasses.
* :class:`InMemoryProcessLock` — in-process implementation for
  tests and the in-process mode every store can use without
  paying for an OS syscall. Thread-safe.
* :class:`FilesystemProcessLock` — production adapter that uses
  ``fcntl.flock`` on POSIX and ``msvcrt.locking`` on Windows over
  a ``<target>.lock`` sidecar. Cross-process safety comes from
  the OS file lock; closing the fd releases the lock
  automatically.

The boundary shape is the same ``Mapping[str, object]`` port
convention used by C-01 and C-02. :func:`path_from_mapping` is
the canonical converter; the dataclass is the in-memory
implementation's internal type.
"""

from __future__ import annotations

import os
import sys
import threading
from collections.abc import Mapping
from pathlib import Path
from typing import IO, Optional

# --- Boundary helpers --------------------------------------------------------

PATH_KEY = "path"


def path_from_mapping(payload: Mapping[str, object]) -> Path:
    """Extract and validate the path from a mapping-shaped request."""
    raw = payload.get(PATH_KEY)
    if raw is None or raw == "":
        raise ValueError(f"process-lock request missing {PATH_KEY!r}")
    return Path(os.fspath(raw))


# --- Lock handle -------------------------------------------------------------


class LockHandle:
    """Concrete base :class:`LockHandle` (used by ``InMemoryProcessLock``).

    The filesystem adapter uses :class:`_FilesystemLockHandle` which
    holds an open file descriptor and an OS lock on it; this base
    class is the in-memory shape (a simple flag + a back-pointer to
    the owning registry).
    """

    def __init__(self, *, path: Path) -> None:
        self._path = path
        self._released = False

    @property
    def path(self) -> Path:
        return self._path

    @property
    def released(self) -> bool:
        return self._released

    def release(self) -> None:
        self._released = True

    def __enter__(self) -> "LockHandle":
        return self

    def __exit__(self, exc_type, exc, tb) -> None:
        self.release()


# --- In-memory implementation ------------------------------------------------


class InMemoryProcessLock:
    """In-process :class:`ProcessLockPort` for tests and dry-run.

    Thread-safe; the registry is a ``dict[Path, LockHandle]``
    protected by a ``threading.Lock``. The lock is **per-process**,
    so it does not give cross-process safety — that is the
    filesystem adapter's job. Use this when:
      * writing tests that need a ``with lock.acquire(path): ...``
        pattern but do not want to hit the real filesystem;
      * the store knows it is the only writer in this process and
        just wants a uniform code shape across adapters.
    """

    def __init__(self) -> None:
        self._held: dict[Path, LockHandle] = {}
        self._guard = threading.Lock()

    def acquire(
        self,
        path: Mapping[str, object],
        *,
        blocking: bool = True,
    ) -> Optional[LockHandle]:
        resolved = path_from_mapping(path)
        if blocking:
            # Spin until the lock is free. In-process the wait is
            # bounded by other threads in the same process and is
            # effectively instantaneous in tests.
            while True:
                with self._guard:
                    existing = self._held.get(resolved)
                    if existing is None or existing.released:
                        handle = LockHandle(path=resolved)
                        self._held[resolved] = handle
                        return handle
                # Yield the GIL so other threads can finish their
                # critical section. ``Event`` is the simplest way
                # without inventing a per-path condition variable.
                ev = threading.Event()
                ev.wait(timeout=0.001)
        # Non-blocking.
        with self._guard:
            existing = self._held.get(resolved)
            if existing is not None and not existing.released:
                return None
            handle = LockHandle(path=resolved)
            self._held[resolved] = handle
            return handle

    # Test-only introspection -------------------------------------------------

    def held_paths_snapshot(self) -> list[Path]:
        with self._guard:
            return [p for p, h in self._held.items() if not h.released]


# --- Filesystem implementation ----------------------------------------------


# POSIX + Windows lockfile backend. The fcntl / msvcrt modules are
# imported lazily so the rest of the module loads on any platform;
# the adapter raises a clear error on import failure rather than
# breaking unrelated imports.
def _import_fcntl():
    try:
        import fcntl  # type: ignore[import-not-found]
    except ImportError as exc:  # pragma: no cover - non-POSIX
        raise RuntimeError(
            "fcntl is not available on this platform; the POSIX "
            "process-lock backend cannot be used"
        ) from exc
    return fcntl


def _import_msvcrt():
    try:
        import msvcrt  # type: ignore[import-not-found]
    except ImportError as exc:  # pragma: no cover - non-Windows
        raise RuntimeError(
            "msvcrt is not available on this platform; the Windows "
            "process-lock backend cannot be used"
        ) from exc
    return msvcrt


def _default_lockfile_path(target: Path) -> Path:
    """Pick the sidecar lockfile path for ``target``.

    We use ``<target>.lock`` next to the target so the sidecar is
    on the same filesystem (relevant for NFS / SMB where
    cross-filesystem locks are unreliable).
    """
    return target.with_name(target.name + ".lock")


class _FilesystemLockHandle(LockHandle):
    """Filesystem lock handle. Holds an open fd for the lock lifetime.

    Closing the fd releases the OS-level lock (``fcntl.flock`` is
    fd-scoped on POSIX; ``msvcrt.locking`` releases when the fd is
    closed on Windows). This is the *whole point* of the design:
    process exit / fd close ⇒ lock auto-released, so a crashing
    process cannot deadlock the next writer.
    """

    def __init__(self, *, path: Path, fd: IO[bytes]) -> None:
        super().__init__(path=path)
        self._fd: IO[bytes] = fd

    def release(self) -> None:
        if self.released:
            return
        try:
            try:
                self._fd.close()
            except OSError:
                pass
        finally:
            super().release()


def _open_lockfile(lockfile: Path) -> IO[bytes]:
    """Open (or create) the sidecar lockfile in binary mode.

    The fd is opened with ``O_RDWR`` and a stable mode so the OS
    can take a lock on it. We do not write any data to the file;
    its sole purpose is to provide a kernel object for the lock
    primitive to attach to.
    """
    # Ensure the parent directory exists; the caller is otherwise
    # responsible for creating their working directory, but the
    # lockfile sidecar deserves a permissive fallback because it
    # is *implicit* state.
    parent = lockfile.parent
    if not parent.exists():
        raise FileNotFoundError(f"lockfile parent directory does not exist: {parent}")
    # ``os.open`` gives us precise control over the flags. We use
    # ``O_RDWR | O_CREAT`` so the file exists but we never write
    # to it; the lock is the only state.
    fd = os.open(
        str(lockfile),
        flags=os.O_RDWR | os.O_CREAT,
        mode=0o644,
    )
    return os.fdopen(fd, "rb")


class FilesystemProcessLock:
    """Filesystem :class:`ProcessLockPort` for production use.

    Backed by ``fcntl.flock`` on POSIX (``fcntl.LOCK_EX`` /
    ``fcntl.LOCK_NB``) and ``msvcrt.locking`` on Windows
    (``msvcrt.LK_NBLCK`` over a 1-byte range). The lock is held
    on a sidecar ``<target>.lock`` file that is opened once and
    held for the duration of the lock; closing the fd releases
    the OS-level lock.

    The lock is **advisory**: a writer that does not call
    ``acquire`` can still corrupt the protected file. This is
    documented in ADR 0001 and is the correct trade-off vs.
    mandatory locks (which are unreliable on NFS / SMB).
    """

    def __init__(self, *, lockfile_path=None) -> None:
        # Optional override: callers that want the lockfile in a
        # specific location (e.g. tests using ``tmp_path``) can
        # pass a callable ``target -> lockfile_path``. Default is
        # ``<target>.lock`` next to the target.
        self._lockfile_path = lockfile_path or _default_lockfile_path
        # ``sys.platform`` is checked once at construction; the
        # adapter is single-platform per instance because the OS
        # primitives are not interchangeable.
        self._posix = sys.platform != "win32"
        if self._posix:
            self._fcntl = _import_fcntl()
        else:
            self._msvcrt = _import_msvcrt()

    def _resolve_lockfile(self, target: Path) -> Path:
        return self._lockfile_path(target)

    def acquire(
        self,
        path: Mapping[str, object],
        *,
        blocking: bool = True,
    ) -> Optional[LockHandle]:
        target = path_from_mapping(path)
        lockfile = self._resolve_lockfile(target)
        fd = _open_lockfile(lockfile)
        try:
            if self._posix:
                op = (
                    self._fcntl.LOCK_EX
                    if blocking
                    else self._fcntl.LOCK_EX | self._fcntl.LOCK_NB
                )
                try:
                    self._fcntl.flock(fd.fileno(), op)
                except OSError as exc:
                    # ``LOCK_NB`` raises ``EWOULDBLOCK`` when the
                    # lock is held. Convert to the documented
                    # ``None`` return for non-blocking.
                    err = exc.errno if hasattr(exc, "errno") else None
                    if not blocking and err in (
                        getattr(self._fcntl, "EWOULDBLOCK", None),
                        getattr(self._fcntl, "EAGAIN", None),
                    ):
                        fd.close()
                        return None
                    fd.close()
                    raise
            else:
                if blocking:
                    # ``msvcrt.locking`` is always non-blocking
                    # (it raises ``OSError`` immediately if the
                    # region is locked). To emulate blocking we
                    # poll. Bounded only by the caller's patience.
                    import time

                    while True:
                        try:
                            self._msvcrt.locking(fd.fileno(), self._msvcrt.LK_NBLCK, 1)
                            break
                        except OSError as exc:
                            err = exc.errno if hasattr(exc, "errno") else None
                            if err not in (13, 33):  # ERROR_LOCK_VIOLATION
                                fd.close()
                                raise
                            time.sleep(0.001)
                else:
                    try:
                        self._msvcrt.locking(fd.fileno(), self._msvcrt.LK_NBLCK, 1)
                    except OSError as exc:
                        err = exc.errno if hasattr(exc, "errno") else None
                        if err in (13, 33):  # ERROR_LOCK_VIOLATION
                            fd.close()
                            return None
                        fd.close()
                        raise
        except BaseException:
            # Any failure to acquire leaves the fd closed; the
            # caller never sees a half-open handle.
            try:
                fd.close()
            except OSError:
                pass
            raise

        handle = _FilesystemLockHandle(path=target, fd=fd)
        return handle


# --- Re-exports for the public surface ---------------------------------------


__all__ = [
    "FilesystemProcessLock",
    "InMemoryProcessLock",
    "LockHandle",
    "path_from_mapping",
]
