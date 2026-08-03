# ADR 0001: Single-writer process-lock for JSON snapshots; O_APPEND for NDJSON

* **Status**: Accepted
* **Date**: 2026-08-04
* **Phase / Backlog item**: C-03 (per §13.4 of `docs/optimization-guide.md`)
* **Supersedes**: —
* **Superseded by**: —

## Context and problem statement

C-02 (`AtomicFilePort`) gives every state store a single-process
crash-safe writer: temp file → `flush` + `fsync` → `os.replace`.
What it does **not** give us is a guarantee about concurrent writers
from **different processes** (e.g. one web console process and one
MCP server process both touching the same `loot/conversations/index.json`,
or two background workers both writing to the same checkpoint
stream). On Windows two concurrent `os.replace` calls on the same
target fail with `WinError 5` because the destination is briefly
open; on POSIX they can race, depending on the filesystem.

The existing state stores in the codebase follow two patterns:

* **Replace-style JSON snapshots** — `ConversationStore`
  (`loot/conversations/{id}.json` and `conversations/index.json`)
  reads the file, mutates the in-memory model, then `write_text`
  the whole thing back.
* **Append-only NDJSON streams** — `SessionLedger`
  (`loot/ledger.jsonl`), `CheckpointStore`
  (`loot/checkpoints.jsonl`), `ArtifactRegistry`
  (`loot/artifacts.jsonl`) each `json.dumps(record) + "\n"` and
  write to the end of the file.

We need to commit to a multi-process concurrency model **before** the
C-04 / C-10 backlog items can rewire those stores on top of C-02.

## Decision drivers

* **No new runtime dependencies.** Adding SQLite, LMDB, or any
  embedded DB is a heavy cost for a small win and pulls in
  platform-specific binaries.
* **Honest semantics.** The C-03 acceptance is *"多线程/多进程语义
  明确"* — semantics must be clear, not necessarily universal.
* **Match existing patterns.** Most writes are already NDJSON
  append-only. Forcing a transaction model on them would be a
  rewrite, not an upgrade.
* **Windows + POSIX parity.** The codebase supports both. The
  chosen primitive must work on both without forking behaviour.
* **Crash safety first.** Whatever the model, partial-write
  visibility from C-02 must remain impossible.

## Considered options

### Option A — Single-writer + OS-level advisory lock (chosen)

A new `ProcessLockPort` gives callers an exclusive advisory lock
on a path. The filesystem adapter uses `fcntl.flock(LOCK_EX)` on
POSIX and `msvcrt.locking(LK_NBLCK, 1)` on Windows over a
sibling `.lock` file. Locks are auto-released when the process
exits or the lock handle is closed.

* `JSON snapshot` writers wrap their read-modify-replace cycle in
  `with lock.acquire(target): ...` so only one process is in the
  critical section at a time.
* `NDJSON append` writers do **not** need the lock: POSIX
  `O_APPEND` guarantees writes smaller than `PIPE_BUF` (4 KiB on
  Linux) are atomic at the file level, and the `AtomicFilePort`
  filesystem adapter already writes a single `fh.write(content)`
  + `os.fsync` per call which is the same single-write shape.

*Pros*: zero new deps; works on Windows + POSIX; clear semantics
("snapshot writers serialise, NDJSON writers append"); small
adapter (~80 lines).

*Cons*: advisory lock, not mandatory — a misbehaving writer that
ignores the lock can still corrupt the file. The C-03 boundary
documents this honestly: the lock is a **protocol**, not a
mandate; misuse is a defect, not a race.

### Option B — Embedded transaction storage (SQLite / LMDB)

Move all state stores into SQLite (or LMDB) with proper ACID
transactions.

*Pros*: real transactions, real concurrency, real recovery.

*Cons*: adds a C-extension runtime dep, complicates packaging
(wheels per platform), changes the on-disk format (breaks every
existing `loot/` consumer), and overshoots the actual need — the
NDJSON streams don't need transactions because their unit of
write is already a single line.

### Option C — Append-only log + periodic compaction

Every writer always appends. A background process compacts the log
into a snapshot. Readers consult the snapshot plus the tail of the
log.

*Pros*: lock-free writes, history is preserved, recovery is
trivial.

*Cons*: substantial rewrite of every store; the `ConversationStore`
read-modify-replace cycle is awkward under append-only; the
"compaction" step needs its own concurrency story which re-introduces
the original problem.

### Option D — Snapshot + WAL per file

Each writer writes a side file, then `os.replace`s onto the
target. This is what C-02 already does for the single-process
case; extending it to multi-process needs the same lock primitive
as Option A, so it would be Option A in disguise.

## Decision

**Adopt Option A**: introduce a `ProcessLockPort` (advisory
exclusive lock on a path) backed by `fcntl.flock` / `msvcrt.locking`,
and adopt the following per-store concurrency model:

| Store kind        | Pattern                       | Cross-process safety                                              |
| ----------------- | ----------------------------- | ----------------------------------------------------------------- |
| JSON snapshot     | single-writer + lock acquire  | guaranteed — only one process in the critical section at a time   |
| NDJSON append     | single `O_APPEND` write       | guaranteed per-line on POSIX; Windows `O_APPEND` is also atomic   |
| Binary blob       | single-writer + lock acquire  | same as JSON snapshot                                             |
| In-process dict   | n/a                           | guarded by `threading.Lock` / domain object, no on-disk story    |

**Implementation boundary**:

* `flaghunter/ports/process_lock.py` — `ProcessLockPort` Protocol
  with `acquire(path, *, blocking=True) -> LockHandle` and a
  `LockHandle` that supports `with` and explicit `release()`.
* `flaghunter/domain/process_lock.py`:
  * `InMemoryProcessLock` — for tests and the in-process mode
    that `ConversationStore` (etc.) can use today without paying
    for a real `fcntl` syscall.
  * `FilesystemProcessLock` — production adapter, uses
    `fcntl.flock` on POSIX and `msvcrt.locking` on Windows over
    a `<target>.lock` sidecar. The sidecar is created on demand
    with `O_CREAT`, mode `0o644`, and lives next to the target so
    it is on the same filesystem (relevant for NFS).
* `flaghunter/domain/active_schemas.py` — registers
  `port.process_lock@v1` so the boundary is discoverable from the
  C-01 catalog.

**Caller contract** (documented in the port docstring):

```python
with lock.acquire(target_path):
    atomic_file.write_text(target_path, snapshot)
# lock auto-released on exit; fd closed on release
```

A writer that ignores the lock violates the C-03 contract; the
advisory nature is explicit in the ADR so a code reviewer can
flag a missing `with` block.

## Consequences

### Positive

* Every state store has an unambiguous concurrency story.
* The C-04 (checksum/sequence) and C-10 (state store adapter)
  items can build on top of C-02 + this lock without re-asking
  the question.
* The Windows + POSIX parity is explicit (`fcntl.flock` vs
  `msvcrt.locking`).
* Zero new dependencies.

### Negative

* Advisory lock: a process that forgets `with lock.acquire(...)`
  can still corrupt a JSON snapshot. We accept this because the
  alternative (mandatory lock) is unreliable across NFS and SMB
  and is not portable to Windows in the same shape.
* Holding a lock across an `os.fsync` makes the critical section
  longer than strictly necessary. We accept this — `os.fsync` is
  the dominant cost already, the lock is a small additional wait
  on contention.
* Per-process lockfile (`.lock` sidecar) adds one file per
  protected target. Trivial cost on local disks; relevant on
  network mounts where lockfile creation can fail — the adapter
  surfaces that as `AtomicWriteError` so callers see it.

### Neutral

* Readers of JSON snapshots still need to be tolerant of the file
  being absent (mid-replace) or stale. The existing
  `ConversationStore` already handles this by returning `[]` on
  parse failure; no change.
* The lock is **per-process**, not per-thread. The in-memory
  adapter serialises same-process threads by path, but the
  filesystem adapter relies on the OS file lock (which is also
  per-process: each `open()` call gets its own fd, and a process
  holding a lock can open another fd without contention). For
  FlagHunter's actual use this is fine: there is no in-process
  reason for two threads to write the same snapshot at the same
  time (the C-02 per-path lock already prevents that), and a
  second process trying to write is exactly the case the lock
  catches.

## Follow-up

* **C-04** (checksum + sequence) and **C-10** (state store
  adapter) should consume `ProcessLockPort` for their
  snapshot-style writes. C-03 is the foundation; the migration
  of `ConversationStore`, `SessionLedger`, `CheckpointStore`,
  and `ArtifactRegistry` to the new pattern is the next batch of
  work, scoped per store.
* A future slice could add a `try_acquire` + timeout option to
  the lock to support bounded-wait writers, but the current
  `blocking=True / False` pair is enough for the existing
  callers.
* The advisory nature of the lock should be re-asserted in code
  review checklists so a missing `with` block is caught at PR
  time, not at incident time.
