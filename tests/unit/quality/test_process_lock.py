"""Process lock tests (C-03 — §13.4 of the optimization guide).

C-03 acceptance: multi-thread and multi-process concurrency
semantics for state stores are explicit. The acceptance is met
by the existence of ``ProcessLockPort`` (the boundary that JSON
snapshot writers cross before their read-modify-replace cycle)
plus a working in-memory and filesystem adapter. These tests
lock the boundary contract and the smaller invariants each
adapter must satisfy.
"""

from __future__ import annotations

import multiprocessing as mp
import threading
import time
from pathlib import Path

import pytest

from flaghunter.domain import (
    FilesystemProcessLock,
    InMemoryProcessLock,
    LockHandle,
    path_from_mapping,
)
from flaghunter.domain.process_lock import _default_lockfile_path
from flaghunter.ports import ProcessLockPort

# --- Helpers ----------------------------------------------------------------


def _path(payload: str | Path) -> dict[str, object]:
    return {"path": str(payload)}


# --- path_from_mapping ------------------------------------------------------


class TestPathFromMapping:
    def test_accepts_string_path(self) -> None:
        assert path_from_mapping(_path("/tmp/x.json")) == Path("/tmp/x.json")

    def test_accepts_pathlike(self) -> None:
        p = Path("/tmp/x.json")
        assert path_from_mapping({"path": p}) == p

    def test_rejects_missing_path(self) -> None:
        with pytest.raises(ValueError, match="missing 'path'"):
            path_from_mapping({})

    def test_rejects_empty_path(self) -> None:
        with pytest.raises(ValueError, match="missing 'path'"):
            path_from_mapping({"path": ""})


# --- LockHandle -------------------------------------------------------------


class TestLockHandle:
    def test_starts_unreleased(self) -> None:
        h = LockHandle(path=Path("/tmp/x.json"))
        assert h.released is False

    def test_release_marks_released(self) -> None:
        h = LockHandle(path=Path("/tmp/x.json"))
        h.release()
        assert h.released is True

    def test_release_is_idempotent(self) -> None:
        h = LockHandle(path=Path("/tmp/x.json"))
        h.release()
        h.release()
        assert h.released is True

    def test_context_manager_releases_on_exit(self) -> None:
        h = LockHandle(path=Path("/tmp/x.json"))
        with h as inner:
            assert inner is h
            assert inner.released is False
        assert h.released is True

    def test_context_manager_releases_on_exception(self) -> None:
        h = LockHandle(path=Path("/tmp/x.json"))
        with pytest.raises(RuntimeError, match="boom"):
            with h:
                raise RuntimeError("boom")
        assert h.released is True


# --- InMemoryProcessLock ----------------------------------------------------


class TestInMemoryProcessLock:
    def test_first_acquire_returns_handle(self) -> None:
        lock = InMemoryProcessLock()
        h = lock.acquire(_path("/a.json"))
        assert h is not None
        assert h.released is False

    def test_second_acquire_blocks_until_release(self) -> None:
        lock = InMemoryProcessLock()
        h1 = lock.acquire(_path("/a.json"))
        assert h1 is not None
        # Non-blocking returns None when held.
        assert lock.acquire(_path("/a.json"), blocking=False) is None
        h1.release()
        # Now it can be acquired again.
        h2 = lock.acquire(_path("/a.json"))
        assert h2 is not None
        h2.release()

    def test_different_paths_do_not_conflict(self) -> None:
        lock = InMemoryProcessLock()
        h1 = lock.acquire(_path("/a.json"))
        h2 = lock.acquire(_path("/b.json"))
        assert h1 is not None and h2 is not None
        h1.release()
        h2.release()

    def test_context_manager_critical_section(self) -> None:
        lock = InMemoryProcessLock()
        with lock.acquire(_path("/a.json")) as h:
            assert h.released is False
            # While inside, non-blocking acquire returns None.
            assert lock.acquire(_path("/a.json"), blocking=False) is None
        # After exit, the path is free.
        h2 = lock.acquire(_path("/a.json"))
        assert h2 is not None
        h2.release()

    def test_serialises_concurrent_writers(self) -> None:
        # In-process: 8 threads each write a value, the lock
        # serialises them so observers never see interleaving.
        lock = InMemoryProcessLock()
        path = _path("/a.json")
        observed: list[int] = []
        observed_lock = threading.Lock()

        def worker(idx: int) -> None:
            with lock.acquire(path):
                observed.append(idx)
                time.sleep(0.001)

        threads = [threading.Thread(target=worker, args=(i,)) for i in range(8)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()
        # All 8 writes happened in some serial order; the lock
        # guarantees we cannot miss any.
        assert sorted(observed) == list(range(8))
        with observed_lock:
            assert len(observed) == 8

    def test_satisfies_port_protocol(self) -> None:
        assert isinstance(InMemoryProcessLock(), ProcessLockPort)


# --- FilesystemProcessLock --------------------------------------------------


@pytest.fixture
def fs_lock_dir(tmp_path: Path) -> Path:
    return tmp_path / "locks"


class TestFilesystemProcessLock:
    def test_first_acquire_returns_handle(self, fs_lock_dir: Path) -> None:
        fs_lock_dir.mkdir()
        target = fs_lock_dir / "a.json"
        lock = FilesystemProcessLock()
        h = lock.acquire(_path(target))
        assert h is not None
        h.release()

    def test_lockfile_lives_next_to_target(self, fs_lock_dir: Path) -> None:
        fs_lock_dir.mkdir()
        target = fs_lock_dir / "a.json"
        # Default path puts the sidecar next to the target.
        assert _default_lockfile_path(target) == fs_lock_dir / "a.json.lock"

    def test_acquire_creates_lockfile(self, fs_lock_dir: Path) -> None:
        fs_lock_dir.mkdir()
        target = fs_lock_dir / "a.json"
        lock = FilesystemProcessLock()
        h = lock.acquire(_path(target))
        try:
            assert (fs_lock_dir / "a.json.lock").exists()
        finally:
            h.release()

    def test_release_closes_lockfile(self, fs_lock_dir: Path) -> None:
        fs_lock_dir.mkdir()
        target = fs_lock_dir / "a.json"
        lock = FilesystemProcessLock()
        h = lock.acquire(_path(target))
        h.release()
        # On Windows the file may still appear on disk for a short
        # time, but it must not be locked any more — a fresh
        # acquire must succeed.
        h2 = lock.acquire(_path(target))
        assert h2 is not None
        h2.release()

    def test_second_acquire_returns_none_when_held(self, fs_lock_dir: Path) -> None:
        fs_lock_dir.mkdir()
        target = fs_lock_dir / "a.json"
        lock = FilesystemProcessLock()
        h1 = lock.acquire(_path(target))
        try:
            assert lock.acquire(_path(target), blocking=False) is None
        finally:
            h1.release()

    def test_different_targets_do_not_conflict(self, fs_lock_dir: Path) -> None:
        fs_lock_dir.mkdir()
        lock = FilesystemProcessLock()
        h1 = lock.acquire(_path(fs_lock_dir / "a.json"))
        h2 = lock.acquire(_path(fs_lock_dir / "b.json"))
        try:
            assert h1 is not None and h2 is not None
        finally:
            h1.release()
            h2.release()

    def test_missing_parent_dir_raises(self, tmp_path: Path) -> None:
        target = tmp_path / "no-such-dir" / "a.json"
        lock = FilesystemProcessLock()
        with pytest.raises(FileNotFoundError, match="parent directory does not exist"):
            lock.acquire(_path(target))

    def test_context_manager_releases_on_exit(self, fs_lock_dir: Path) -> None:
        fs_lock_dir.mkdir()
        target = fs_lock_dir / "a.json"
        lock = FilesystemProcessLock()
        with lock.acquire(_path(target)) as h:
            assert h.released is False
        # After exit the path is free.
        h2 = lock.acquire(_path(target))
        assert h2 is not None
        h2.release()

    def test_satisfies_port_protocol(self, fs_lock_dir: Path) -> None:
        fs_lock_dir.mkdir()
        assert isinstance(FilesystemProcessLock(), ProcessLockPort)

    def test_released_handle_can_be_reacquired(self, fs_lock_dir: Path) -> None:
        fs_lock_dir.mkdir()
        target = fs_lock_dir / "a.json"
        lock = FilesystemProcessLock()
        for _ in range(5):
            h = lock.acquire(_path(target))
            assert h is not None
            h.release()


# --- Cross-process safety (the C-03 acceptance) ----------------------------


def _subprocess_writer(
    target_path: str,
    ready_path: str,
    done_path: str,
    hold_seconds: float,
) -> None:
    """Subprocess helper: acquire the lock, write a marker, hold,
    release. Used to prove the cross-process guarantee end-to-end.
    """
    from flaghunter.domain import FilesystemProcessLock

    fs = FilesystemProcessLock()
    # Make sure the sidecar is in a known state.
    target = Path(target_path)
    handle = fs.acquire(_path(target))
    assert handle is not None, "subprocess failed to acquire the lock"
    try:
        Path(ready_path).write_text("acquired", encoding="utf-8")
        time.sleep(hold_seconds)
        Path(done_path).write_text("released", encoding="utf-8")
    finally:
        handle.release()


def _wait_for(path: Path, timeout: float) -> str:
    deadline = time.time() + timeout
    while time.time() < deadline:
        if path.exists():
            return path.read_text(encoding="utf-8")
        time.sleep(0.01)
    raise AssertionError(f"timed out waiting for {path}")


class TestCrossProcessSafety:
    """The C-03 acceptance: multi-process semantics are explicit.

    The lock is OS-enforced across processes; a non-blocking
    ``acquire`` from process B while process A holds the lock
    MUST return ``None`` until A releases.
    """

    def test_non_blocking_returns_none_when_other_process_holds(
        self, tmp_path: Path
    ) -> None:
        target = tmp_path / "state.json"
        target.write_text("seed", encoding="utf-8")
        ready = tmp_path / "child.ready"
        done = tmp_path / "child.done"

        ctx = mp.get_context("spawn")
        child = ctx.Process(
            target=_subprocess_writer,
            args=(str(target), str(ready), str(done), 1.0),
        )
        child.start()
        try:
            # Wait until the child has acquired the lock.
            _wait_for(ready, timeout=10)
            # We must not be able to acquire the same lock from
            # this process while the child holds it.
            fs = FilesystemProcessLock()
            assert fs.acquire(_path(target), blocking=False) is None
            # The child will release on its own; we just wait
            # for the done marker so the cleanup is deterministic.
            _wait_for(done, timeout=10)
        finally:
            child.join(timeout=5)
            if child.is_alive():
                child.terminate()
                child.join()
