"""Atomic file domain types and in-memory / filesystem implementations.

Atomic file writes are the low-level primitive every higher-level
state store needs to avoid producing half-written files on crash,
signal, or power loss. This module provides:

* :class:`AtomicWriteError` — the single failure shape the port
  raises, wrapping any underlying I/O error so callers do not have
  to catch the full ``OSError`` zoo.
* :class:`InMemoryAtomicFile` — an in-process implementation used by
  tests and CLI code that wants the contract without the disk.
* :class:`FilesystemAtomicFile` — the production implementation:
  write to a uniquely-named temp file in the same directory as
  the target, ``flush`` + ``os.fsync`` the temp, then ``os.replace``
  the temp onto the target. ``os.replace`` is atomic on POSIX and
  on Windows since Python 3.3; the ``fsync`` is what makes the
  write durable across a power loss.

The boundary shape for the port is ``Mapping[str, object]``; the
internal implementation dataclass :class:`_WriteRequest` is *not*
exposed at the port boundary. ``request_from_mapping`` /
``to_mapping`` are the canonical converters (mirroring C-01
:mod:`flaghunter.domain.schema_catalog`).
"""

from __future__ import annotations

import os
import tempfile
import threading
from collections.abc import Iterator, Mapping
from dataclasses import dataclass
from pathlib import Path

# --- Boundary types ----------------------------------------------------------


# Keys recognised in the mapping-shaped request / response boundary.
# Mirrors C-01: the port contract uses plain dicts; the dataclass is
# the in-memory implementation's internal type.
PATH_KEY = "path"
ENCODING_KEY = "encoding"
OVERWRITE_KEY = "overwrite"
FSYNC_KEY = "fsync"
DEFAULT_ENCODING = "utf-8"


def request_from_mapping(payload: Mapping[str, object]) -> "_WriteRequest":
    """Validate and convert a mapping-shaped request into a request.

    Required: ``"path"`` (str or os.PathLike). Optional: ``"encoding"``
    (str, default utf-8), ``"overwrite"`` (bool, default True),
    ``"fsync"`` (bool, default True).
    """
    raw_path = payload.get(PATH_KEY)
    if raw_path is None or raw_path == "":
        raise ValueError(f"atomic-file request missing {PATH_KEY!r}")
    path = Path(os.fspath(raw_path))
    encoding_raw = payload.get(ENCODING_KEY, DEFAULT_ENCODING)
    if not isinstance(encoding_raw, str):
        raise ValueError(
            f"atomic-file request {ENCODING_KEY!r} must be a string, "
            f"got {type(encoding_raw).__name__}"
        )
    overwrite_raw = payload.get(OVERWRITE_KEY, True)
    if not isinstance(overwrite_raw, bool):
        raise ValueError(
            f"atomic-file request {OVERWRITE_KEY!r} must be a bool, "
            f"got {type(overwrite_raw).__name__}"
        )
    fsync_raw = payload.get(FSYNC_KEY, True)
    if not isinstance(fsync_raw, bool):
        raise ValueError(
            f"atomic-file request {FSYNC_KEY!r} must be a bool, "
            f"got {type(fsync_raw).__name__}"
        )
    return _WriteRequest(
        path=path,
        encoding=encoding_raw,
        overwrite=overwrite_raw,
        fsync=fsync_raw,
    )


@dataclass(frozen=True)
class _WriteRequest:
    """Internal representation of an atomic write request.

    Not part of the port boundary; see ``request_from_mapping``.
    """

    path: Path
    encoding: str = DEFAULT_ENCODING
    overwrite: bool = True
    fsync: bool = True

    def to_mapping(self) -> dict[str, object]:
        return {
            PATH_KEY: str(self.path),
            ENCODING_KEY: self.encoding,
            OVERWRITE_KEY: self.overwrite,
            FSYNC_KEY: self.fsync,
        }


# --- Errors ------------------------------------------------------------------


class AtomicWriteError(OSError):
    """Raised when an atomic write cannot complete cleanly.

    Wraps the underlying ``OSError`` (or ``ValueError`` for invalid
    request shapes) so callers only need to catch this single type
    rather than the full error zoo. The original cause is available
    via ``__cause__``.
    """

    def __init__(self, message: str, *, path: Path | None = None) -> None:
        super().__init__(message)
        self.path = path


# --- In-memory implementation (tests / dry-run) ------------------------------


class InMemoryAtomicFile:
    """In-memory ``AtomicFilePort`` for tests and dry-run code.

    Thread-safe; the in-process store is a ``dict[Path, str]``
    protected by a ``threading.Lock``. ``os.replace`` semantics are
    emulated by atomic pointer swap; no half-file is ever visible
    to ``read_text`` because the store only ever assigns the full
    new content.
    """

    def __init__(self) -> None:
        self._store: dict[Path, str] = {}
        self._lock = threading.Lock()
        # Sidecar files left behind when a write is interrupted
        # mid-way. Useful for tests that want to assert cleanup.
        self.abandoned_sidecars: list[Path] = []

    def write_text(
        self,
        path: Mapping[str, object],
        content: str,
    ) -> None:
        req = request_from_mapping(path)
        if not isinstance(content, str):
            raise AtomicWriteError(
                f"content must be str, got {type(content).__name__}",
                path=req.path,
            )
        with self._lock:
            if not req.overwrite and req.path in self._store:
                raise AtomicWriteError(
                    f"refusing to overwrite existing file: {req.path}",
                    path=req.path,
                )
            # Atomic swap under the lock: no reader ever sees a
            # half-string because the dict assignment is a single
            # Python statement and the lock prevents concurrent
            # readers from interleaving.
            self._store[req.path] = content

    def read_text(self, path: Mapping[str, object]) -> str | None:
        raw = path.get(PATH_KEY)
        if raw is None or raw == "":
            raise ValueError(f"atomic-file read missing {PATH_KEY!r}")
        resolved = Path(os.fspath(raw))
        with self._lock:
            return self._store.get(resolved)

    def exists(self, path: Mapping[str, object]) -> bool:
        raw = path.get(PATH_KEY)
        if raw is None or raw == "":
            raise ValueError(f"atomic-file exists missing {PATH_KEY!r}")
        resolved = Path(os.fspath(raw))
        with self._lock:
            return resolved in self._store

    def remove(self, path: Mapping[str, object]) -> bool:
        raw = path.get(PATH_KEY)
        if raw is None or raw == "":
            raise ValueError(f"atomic-file remove missing {PATH_KEY!r}")
        resolved = Path(os.fspath(raw))
        with self._lock:
            return self._store.pop(resolved, None) is not None

    # Test-only introspection -------------------------------------------------

    def keys_snapshot(self) -> list[Path]:
        with self._lock:
            return list(self._store.keys())

    def __iter__(self) -> Iterator[Path]:
        with self._lock:
            snapshot = list(self._store.keys())
        return iter(snapshot)

    def __len__(self) -> int:
        with self._lock:
            return len(self._store)


# --- Filesystem implementation (production) ----------------------------------


class FilesystemAtomicFile:
    """Filesystem-backed ``AtomicFilePort`` for production use.

    Algorithm (the well-known atomic-replace recipe):

    1. Open a uniquely-named temp file in the **same directory** as
       the target (same filesystem => ``os.replace`` is atomic).
    2. Write the content.
    3. ``flush()`` then ``os.fsync(fd)`` to push bytes to the
       physical disk.
    4. Close the fd.
    5. ``os.replace(tmp, target)`` — atomic on POSIX and on
       Windows since Python 3.3.
    6. On any failure before step 5, attempt to unlink the temp
       file; the original target (if any) is left untouched.

    ``fsync`` defaults to ``True`` because the whole point of the
    adapter is durability across crash / power loss; callers that
    genuinely want the weaker ``flush``-only guarantee can opt out
    via the ``fsync=False`` request key.

    **Concurrency**: ``Windows`` opens files with shared-delete =
    False by default, so two concurrent ``os.replace`` calls on the
    same target fail with ``WinError 5 Access Denied`` because the
    destination is briefly open. We mitigate this in-process by
    holding a per-path lock around the whole write, so two threads
    writing the *same* file serialize; different files still run in
    parallel. Cross-process concurrency is **not** addressed here
    and is the responsibility of C-03 (single-writer decision).
    """

    def __init__(self) -> None:
        # Per-path lock: different paths run in parallel, same path
        # serializes. A guard lock protects the lock dict itself.
        self._path_locks: dict[Path, threading.Lock] = {}
        self._locks_guard = threading.Lock()

    def _lock_for(self, path: Path) -> threading.Lock:
        with self._locks_guard:
            lock = self._path_locks.get(path)
            if lock is None:
                lock = threading.Lock()
                self._path_locks[path] = lock
            return lock

    def write_text(
        self,
        path: Mapping[str, object],
        content: str,
    ) -> None:
        req = request_from_mapping(path)
        if not isinstance(content, str):
            raise AtomicWriteError(
                f"content must be str, got {type(content).__name__}",
                path=req.path,
            )
        if not req.overwrite and req.path.exists():
            raise AtomicWriteError(
                f"refusing to overwrite existing file: {req.path}",
                path=req.path,
            )
        with self._lock_for(req.path):
            self._atomic_write_text(req, content)

    @staticmethod
    def _atomic_write_text(req: _WriteRequest, content: str) -> None:
        target = req.path
        parent = target.parent
        # We must have a real parent directory to put the temp file
        # in (same-fs rule for atomic replace). If the parent
        # doesn't exist, fail fast: callers are responsible for
        # creating their own working directory.
        try:
            if not parent.exists():
                raise AtomicWriteError(
                    f"parent directory does not exist: {parent}",
                    path=target,
                )
            if not parent.is_dir():
                raise AtomicWriteError(
                    f"parent path is not a directory: {parent}",
                    path=target,
                )
        except OSError as exc:
            raise AtomicWriteError(
                f"cannot stat parent directory {parent}: {exc}",
                path=target,
            ) from exc

        # NamedTemporaryFile gives us a unique name in the same
        # directory; delete=False so we control the unlink and can
        # also ``os.replace`` it.
        tmp_path: Path | None = None
        try:
            tmp_fd, tmp_str = tempfile.mkstemp(
                prefix=f".{target.name}.",
                suffix=".tmp",
                dir=str(parent),
            )
            tmp_path = Path(tmp_str)
            try:
                with os.fdopen(tmp_fd, "w", encoding=req.encoding) as fh:
                    fh.write(content)
                    fh.flush()
                    if req.fsync:
                        os.fsync(fh.fileno())
            except Exception:
                # Close + unlink if we never replaced.
                try:
                    os.unlink(tmp_path)
                except OSError:
                    pass
                raise
            os.replace(tmp_path, target)
            tmp_path = None
        except AtomicWriteError:
            raise
        except OSError as exc:
            if tmp_path is not None:
                try:
                    os.unlink(tmp_path)
                except OSError:
                    pass
            raise AtomicWriteError(
                f"atomic write failed for {target}: {exc}",
                path=target,
            ) from exc

    def read_text(self, path: Mapping[str, object]) -> str | None:
        raw = path.get(PATH_KEY)
        if raw is None or raw == "":
            raise ValueError(f"atomic-file read missing {PATH_KEY!r}")
        resolved = Path(os.fspath(raw))
        if not resolved.exists():
            return None
        if not resolved.is_file():
            raise AtomicWriteError(
                f"path is not a regular file: {resolved}",
                path=resolved,
            )
        try:
            return resolved.read_text(encoding="utf-8")
        except OSError as exc:
            raise AtomicWriteError(
                f"read failed for {resolved}: {exc}", path=resolved
            ) from exc

    def exists(self, path: Mapping[str, object]) -> bool:
        raw = path.get(PATH_KEY)
        if raw is None or raw == "":
            raise ValueError(f"atomic-file exists missing {PATH_KEY!r}")
        resolved = Path(os.fspath(raw))
        return resolved.is_file()

    def remove(self, path: Mapping[str, object]) -> bool:
        raw = path.get(PATH_KEY)
        if raw is None or raw == "":
            raise ValueError(f"atomic-file remove missing {PATH_KEY!r}")
        resolved = Path(os.fspath(raw))
        try:
            resolved.unlink()
            return True
        except FileNotFoundError:
            return False
        except OSError as exc:
            raise AtomicWriteError(
                f"remove failed for {resolved}: {exc}", path=resolved
            ) from exc
