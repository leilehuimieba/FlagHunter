"""Atomic file tests (C-02 — §13.4 of the optimization guide).

C-02 acceptance: ``AtomicFilePort`` writes are crash-safe — a
process crash, signal, or disk-full event can never leave a
half-written file visible to subsequent readers. These tests
lock that contract plus the smaller invariants every implementation
must satisfy.

The tests cover both the in-memory and the filesystem
implementations because the in-memory one is what the rest of the
test suite uses (deterministic, fast, no real disk) while the
filesystem one is what production runs.
"""

from __future__ import annotations

import os
import threading
from pathlib import Path

import pytest

from flaghunter.domain import (
    AtomicWriteError,
    FilesystemAtomicFile,
    InMemoryAtomicFile,
    request_from_mapping,
)
from flaghunter.domain.atomic_file import (
    DEFAULT_ENCODING,
    ENCODING_KEY,
    FSYNC_KEY,
    OVERWRITE_KEY,
    PATH_KEY,
)
from flaghunter.ports import AtomicFilePort

# --- Helpers ----------------------------------------------------------------


def _path(payload: str | Path, **extra: object) -> dict[str, object]:
    out: dict[str, object] = {PATH_KEY: str(payload)}
    out.update(extra)
    return out


# --- request_from_mapping --------------------------------------------------


class TestRequestFromMapping:
    def test_accepts_minimal_payload(self) -> None:
        req = request_from_mapping(_path("/tmp/x.json"))
        assert req.path == Path("/tmp/x.json")
        assert req.encoding == DEFAULT_ENCODING
        assert req.overwrite is True
        assert req.fsync is True

    def test_accepts_all_optional_keys(self) -> None:
        req = request_from_mapping(
            _path("/tmp/x.json", encoding="utf-16", overwrite=False, fsync=False)
        )
        assert req.encoding == "utf-16"
        assert req.overwrite is False
        assert req.fsync is False

    def test_rejects_missing_path(self) -> None:
        with pytest.raises(ValueError, match="missing 'path'"):
            request_from_mapping({})

    def test_rejects_empty_path(self) -> None:
        with pytest.raises(ValueError, match="missing 'path'"):
            request_from_mapping({PATH_KEY: ""})

    def test_rejects_non_string_encoding(self) -> None:
        with pytest.raises(ValueError, match="must be a string"):
            request_from_mapping(_path("/tmp/x.json", encoding=123))

    def test_rejects_non_bool_overwrite(self) -> None:
        with pytest.raises(ValueError, match="must be a bool"):
            request_from_mapping(_path("/tmp/x.json", overwrite="yes"))

    def test_rejects_non_bool_fsync(self) -> None:
        with pytest.raises(ValueError, match="must be a bool"):
            request_from_mapping(_path("/tmp/x.json", fsync="no"))

    def test_round_trip_to_mapping_preserves_fields(self) -> None:
        original = _path("/tmp/x.json", encoding="utf-16", overwrite=False, fsync=False)
        req = request_from_mapping(original)
        out = req.to_mapping()
        import os

        assert out[PATH_KEY] == os.fspath(req.path)
        assert str(out[PATH_KEY]) == str(req.path)
        assert out[ENCODING_KEY] == "utf-16"
        assert out[OVERWRITE_KEY] is False
        assert out[FSYNC_KEY] is False


# --- InMemoryAtomicFile ----------------------------------------------------


class TestInMemoryAtomicFile:
    def test_write_then_read_round_trip(self) -> None:
        store = InMemoryAtomicFile()
        store.write_text(_path("/a.json"), "hello")
        assert store.read_text(_path("/a.json")) == "hello"

    def test_read_returns_none_for_missing(self) -> None:
        store = InMemoryAtomicFile()
        assert store.read_text(_path("/missing.json")) is None

    def test_write_replaces_existing_value(self) -> None:
        store = InMemoryAtomicFile()
        store.write_text(_path("/a.json"), "v1")
        store.write_text(_path("/a.json"), "v2")
        assert store.read_text(_path("/a.json")) == "v2"

    def test_overwrite_false_rejects_existing(self) -> None:
        store = InMemoryAtomicFile()
        store.write_text(_path("/a.json"), "v1")
        with pytest.raises(AtomicWriteError, match="refusing to overwrite"):
            store.write_text(_path("/a.json", overwrite=False), "v2")
        # Original content is preserved on rejection.
        assert store.read_text(_path("/a.json")) == "v1"

    def test_overwrite_false_allows_first_write(self) -> None:
        store = InMemoryAtomicFile()
        store.write_text(_path("/a.json", overwrite=False), "v1")
        assert store.read_text(_path("/a.json")) == "v1"

    def test_write_rejects_non_string_content(self) -> None:
        store = InMemoryAtomicFile()
        with pytest.raises(AtomicWriteError, match="content must be str"):
            store.write_text(_path("/a.json"), 12345)  # type: ignore[arg-type]

    def test_exists_true_after_write(self) -> None:
        store = InMemoryAtomicFile()
        store.write_text(_path("/a.json"), "x")
        assert store.exists(_path("/a.json")) is True

    def test_exists_false_before_write(self) -> None:
        store = InMemoryAtomicFile()
        assert store.exists(_path("/missing.json")) is False

    def test_remove_returns_true_when_existing(self) -> None:
        store = InMemoryAtomicFile()
        store.write_text(_path("/a.json"), "x")
        assert store.remove(_path("/a.json")) is True
        assert store.read_text(_path("/a.json")) is None

    def test_remove_returns_false_when_missing(self) -> None:
        store = InMemoryAtomicFile()
        assert store.remove(_path("/missing.json")) is False

    def test_satisfies_port_protocol(self) -> None:
        # Structural: ``isinstance`` check against the runtime-checkable
        # Protocol, not just attribute presence. Mirrors C-01.
        store = InMemoryAtomicFile()
        assert isinstance(store, AtomicFilePort)

    def test_reader_never_sees_partial_content(self) -> None:
        # The in-memory implementation must swap the value atomically;
        # a concurrent reader either sees the old value or the new
        # value, never something in between. We assert the structural
        # invariant (every observed value is a complete writer string)
        # rather than the timing-dependent "old is still visible"
        # check, which is racy under load.
        store = InMemoryAtomicFile()
        store.write_text(_path("/a.json"), "old")
        results: set[str] = set()

        def writer() -> None:
            for i in range(200):
                store.write_text(_path("/a.json"), f"new-{i}")

        def reader() -> None:
            for _ in range(200):
                value = store.read_text(_path("/a.json"))
                if value is not None and value != "old":
                    results.add(value)

        threads = [threading.Thread(target=writer) for _ in range(4)]
        threads += [threading.Thread(target=reader) for _ in range(4)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        # Every observed value must be a complete writer string;
        # no prefix-only fragments allowed.
        assert results, "reader thread saw no values at all"
        for v in results:
            assert v.startswith("new-"), v
            assert v[4:].isdigit(), v

    def test_len_and_iter(self) -> None:
        store = InMemoryAtomicFile()
        assert len(store) == 0
        store.write_text(_path("/a.json"), "x")
        store.write_text(_path("/b.json"), "y")
        assert len(store) == 2
        keys = list(iter(store))
        assert Path("/a.json") in keys
        assert Path("/b.json") in keys


# --- FilesystemAtomicFile --------------------------------------------------


@pytest.fixture
def tmp_dir(tmp_path: Path) -> Path:
    """A real on-disk temp directory the filesystem adapter can use."""
    target = tmp_path / "atomic"
    target.mkdir()
    return target


class TestFilesystemAtomicFile:
    def test_write_then_read_round_trip(self, tmp_dir: Path) -> None:
        fs = FilesystemAtomicFile()
        target = tmp_dir / "a.json"
        fs.write_text(_path(target), "hello")
        assert fs.read_text(_path(target)) == "hello"
        assert target.read_text(encoding="utf-8") == "hello"

    def test_write_creates_no_sidecar_on_success(self, tmp_dir: Path) -> None:
        fs = FilesystemAtomicFile()
        target = tmp_dir / "a.json"
        fs.write_text(_path(target), "x")
        # No .tmp file left behind in the same directory.
        siblings = list(tmp_dir.iterdir())
        assert siblings == [target]

    def test_write_creates_no_sidecar_on_overwrite(self, tmp_dir: Path) -> None:
        fs = FilesystemAtomicFile()
        target = tmp_dir / "a.json"
        target.write_text("v0", encoding="utf-8")
        for i in range(5):
            fs.write_text(_path(target), f"v{i}")
        siblings = list(tmp_dir.iterdir())
        assert siblings == [target]
        assert target.read_text(encoding="utf-8") == "v4"

    def test_overwrite_false_rejects_existing_file(self, tmp_dir: Path) -> None:
        fs = FilesystemAtomicFile()
        target = tmp_dir / "a.json"
        target.write_text("original", encoding="utf-8")
        with pytest.raises(AtomicWriteError, match="refusing to overwrite"):
            fs.write_text(_path(target, overwrite=False), "new")
        # Original is intact after rejection.
        assert target.read_text(encoding="utf-8") == "original"
        # No temp sidecar leaked.
        assert list(tmp_dir.iterdir()) == [target]

    def test_failing_write_does_not_leave_half_file(self, tmp_dir: Path) -> None:
        # Simulate a write failure by using a content type the
        # adapter refuses (non-str). Target is created only on
        # success; on failure nothing should be visible.
        fs = FilesystemAtomicFile()
        target = tmp_dir / "a.json"
        with pytest.raises(AtomicWriteError, match="content must be str"):
            fs.write_text(_path(target), 12345)  # type: ignore[arg-type]
        # Target does not exist.
        assert not target.exists()
        # No temp sidecar leaked.
        assert list(tmp_dir.iterdir()) == []

    def test_parent_dir_missing_fails_cleanly(self, tmp_dir: Path) -> None:
        fs = FilesystemAtomicFile()
        target = tmp_dir / "no-such-subdir" / "a.json"
        with pytest.raises(AtomicWriteError, match="parent directory does not exist"):
            fs.write_text(_path(target), "x")
        # Nothing was created.
        assert not target.exists()
        assert not target.parent.exists()

    def test_parent_path_is_a_file_fails_cleanly(self, tmp_dir: Path) -> None:
        fs = FilesystemAtomicFile()
        # Make ``parent`` a regular file, not a directory.
        blocker = tmp_dir / "blocker"
        blocker.write_text("i am a file, not a dir", encoding="utf-8")
        target = blocker / "a.json"
        with pytest.raises(AtomicWriteError, match="not a directory"):
            fs.write_text(_path(target), "x")
        assert not target.exists()

    def test_read_returns_none_for_missing(self, tmp_dir: Path) -> None:
        fs = FilesystemAtomicFile()
        assert fs.read_text(_path(tmp_dir / "missing.json")) is None

    def test_exists_true_after_write(self, tmp_dir: Path) -> None:
        fs = FilesystemAtomicFile()
        target = tmp_dir / "a.json"
        fs.write_text(_path(target), "x")
        assert fs.exists(_path(target)) is True

    def test_exists_false_before_write(self, tmp_dir: Path) -> None:
        fs = FilesystemAtomicFile()
        assert fs.exists(_path(tmp_dir / "missing.json")) is False

    def test_remove_returns_true_when_existing(self, tmp_dir: Path) -> None:
        fs = FilesystemAtomicFile()
        target = tmp_dir / "a.json"
        fs.write_text(_path(target), "x")
        assert fs.remove(_path(target)) is True
        assert not target.exists()

    def test_remove_returns_false_when_missing(self, tmp_dir: Path) -> None:
        fs = FilesystemAtomicFile()
        assert fs.remove(_path(tmp_dir / "missing.json")) is False

    def test_satisfies_port_protocol(self) -> None:
        fs = FilesystemAtomicFile()
        assert isinstance(fs, AtomicFilePort)

    def test_unicode_content_round_trip(self, tmp_dir: Path) -> None:
        fs = FilesystemAtomicFile()
        target = tmp_dir / "u.json"
        payload = "你好 · \U0001f44d · 漢字"
        fs.write_text(_path(target), payload)
        assert fs.read_text(_path(target)) == payload

    def test_fsync_actually_attempted(self, tmp_dir: Path, monkeypatch) -> None:
        # Spy on os.fsync to confirm the adapter calls it. The
        # atomic-replace contract is meaningless without the fsync
        # step (a power loss between ``write`` and ``os.replace``
        # could still leave the target empty).
        fs = FilesystemAtomicFile()
        target = tmp_dir / "a.json"
        seen: list[int] = []
        real_fsync = os.fsync

        def spy_fsync(fd: int) -> None:
            seen.append(fd)
            real_fsync(fd)

        monkeypatch.setattr("os.fsync", spy_fsync)
        fs.write_text(_path(target), "x")
        assert seen, "FilesystemAtomicFile did not call os.fsync"

    def test_fsync_opt_out_skips_fsync(self, tmp_dir: Path, monkeypatch) -> None:
        fs = FilesystemAtomicFile()
        target = tmp_dir / "a.json"

        def fail_fsync(fd: int) -> None:
            raise AssertionError("fsync should not be called when fsync=False")

        monkeypatch.setattr("os.fsync", fail_fsync)
        fs.write_text(_path(target, fsync=False), "x")
        assert target.read_text(encoding="utf-8") == "x"

    def test_concurrent_writes_to_different_files(self, tmp_dir: Path) -> None:
        fs = FilesystemAtomicFile()
        errors: list[Exception] = []

        def writer(idx: int) -> None:
            try:
                for i in range(20):
                    fs.write_text(_path(tmp_dir / f"f-{idx}.json"), f"v-{i}")
            except Exception as exc:  # pragma: no cover - surfaced in test
                errors.append(exc)

        threads = [threading.Thread(target=writer, args=(i,)) for i in range(8)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        assert not errors
        # All eight files are present; no half-content visible.
        for idx in range(8):
            content = (tmp_dir / f"f-{idx}.json").read_text(encoding="utf-8")
            assert content.startswith("v-")

    def test_concurrent_writes_to_same_file_serialise(self, tmp_dir: Path) -> None:
        # Two threads writing the SAME file must serialise on the
        # adapter-level per-path lock (Windows would otherwise reject
        # the second ``os.replace`` with ``WinError 5`` because the
        # destination is briefly open by the first writer). The
        # lock makes both writes complete cleanly; the final file
        # holds whichever writer ran last.
        fs = FilesystemAtomicFile()
        target = tmp_dir / "shared.json"
        target.write_text("initial", encoding="utf-8")
        errors: list[Exception] = []

        def writer(payload: str) -> None:
            try:
                for _ in range(20):
                    fs.write_text(_path(target), payload)
            except Exception as exc:  # pragma: no cover
                errors.append(exc)

        threads = [
            threading.Thread(target=writer, args=("alpha",)),
            threading.Thread(target=writer, args=("beta",)),
        ]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        assert not errors, f"writer failed: {errors[0]!r}"
        final = target.read_text(encoding="utf-8")
        assert final in ("alpha", "beta")


# --- Boundary shape (port-conformance sanity) ------------------------------


class TestBoundaryShape:
    def test_request_keys_are_documented_strings(self) -> None:
        # Per the port docstring, callers pass a plain dict with
        # string keys. We expose the constants so adapters and
        # callers do not silently drift.
        assert PATH_KEY == "path"
        assert ENCODING_KEY == "encoding"
        assert OVERWRITE_KEY == "overwrite"
        assert FSYNC_KEY == "fsync"

    def test_mapping_payload_is_plain_dict(self) -> None:
        # No framework-specific request object leaks across the
        # boundary. Plain dict, JSON-serialisable values only.
        store = InMemoryAtomicFile()
        store.write_text(_path("/a.json"), "x")
        # ``read_text`` accepts the same dict shape and returns a
        # plain string or None.
        out = store.read_text(_path("/a.json"))
        assert isinstance(out, str)
