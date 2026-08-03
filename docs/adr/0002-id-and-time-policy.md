# ADR 0002: Identity and time policy

* **Status**: Accepted
* **Date**: 2026-08-04
* **Phase / Backlog item**: C-05 (per §13.4 of `docs/optimization-guide.md`)
* **Supersedes**: —
* **Superseded by**: —

## Context and problem statement

The codebase has at least **three** different ID-generation patterns
in production code today, plus **fifteen or more** `datetime.now()`
call sites that mix naive local time, aware UTC, and `time.time()`
wall clock:

* `flaghunter/domain/challenge/contracts/task_dag_plan.py` and
  `flaghunter/agents/pa_agent/ctf_state.py` both define
  `def _new_id(prefix: str) -> str: return f"{prefix}_{uuid.uuid4().hex[:16]}"` —
  the same pattern, duplicated, **truncating UUID4 to 16 hex chars**
  (a 64-bit prefix, collision-resistant for ~4 billion ids before
  the birthday bound).
* `flaghunter/agents/crew/worker_pool.py` uses a sequential
  counter: `f"agent-{self._next_id}"` — process-local, resets on
  restart, not safe for cross-process uniqueness.
* `datetime.now()` (naive local) is used in `agents/state.py`,
  `cpa_modules/m5_swarm_link/...`, `cpa_modules/m3_reporter/...`
  and a handful of other places. `datetime.now(timezone.utc)`
  appears in `harness/session_ledger.py`,
  `harness/checkpoint_store.py`, `harness/artifact_registry.py`,
  and `quality/acceptance.py` — i.e. some stores already
  converged on aware UTC, others have not.
* `time.time()` is used in `cpa_modules/m6_turbo/result_cache.py`
  and `cpa_modules/m6_turbo/memory_optimizer.py` for age / TTL —
  these should be monotonic for duration math, not wall clock.
* `time.monotonic()` is used in `observability.py`,
  `cpa_modules/m6_turbo/...`, and `agents/base_agent.py` for
  elapsed time — already correct.

The masterplan §12.5 and §12.6 already document the policy we
want:

* "全部持久化时间使用 UTC aware ISO 8601"
* "duration 使用 monotonic clock"
* "local time 只在 presentation 格式化"
* "task_id、run_id、session_id、trace_id、span_id、receipt_id、
  claim_id、proof_id 明确格式和生命周期"
* "不随意截断 UUID 作为持久唯一键"
* "`datetime.utcnow()` 和 naive `datetime.now()` 逐步迁移，但
  不做无关全仓改动"

C-05 acceptance is *"时序关联一致"*. The decision below
commits the codebase to a single policy and a single way for
production code to ask for an ID or a timestamp.

## Decision drivers

* **No new runtime dependencies.**
* **Testability.** Every test that needs a deterministic ID or
  clock must be able to inject one without monkey-patching
  `uuid` or `time` globals.
* **Policy, not policing.** The boundary is the port; the
  per-call-site migration is gradual (masterplan §12.5 says
  exactly this). C-05 commits the policy and the boundary, not
  a full rewire of the existing 315 call sites.
* **One source of truth for ID format.** A new ID creator must
  produce the same shape regardless of which module asked.
* **Backwards-compatible migration.** Existing persisted IDs in
  `loot/` are 16-hex truncated. The new service must keep
  producing values that consumers can still parse (so a future
  migration can read old data), but new IDs are full 32-hex.

## Considered options

### Option A — Port + adapters + ADR (chosen)

Introduce two ports:

* `IdentityServicePort` — `new_id(prefix=None) -> str` returns
  `f"{prefix}_{uuid4_hex}"` (or just `uuid4_hex` if no prefix);
  no truncation, no counter. An in-memory deterministic adapter
  for tests; a `UuidIdentityService` backed by `uuid.uuid4` for
  production.
* `TimeServicePort` — `utc_now() -> datetime` (always aware
  UTC), `utc_now_iso() -> str` (ISO 8601 with `Z` suffix),
  `monotonic_now() -> float`. A `SystemTimeService` for
  production that wraps `datetime.now(timezone.utc)` +
  `time.monotonic`; a `FixedTimeService` for tests that accepts
  injected values.

Three call-site groups get migrated in this slice:

* The two `def _new_id` helpers (one each in
  `task_dag_plan.py` and `ctf_state.py`) and the
  `_generate_id` counter in `worker_pool.py` — switched to call
  the port through a session-provided service.
* `agents/state.py` (uses `datetime.now()` for the
  `last_transition` timestamp) — switched to the time port.
* `harness/session_ledger.py`,
  `harness/checkpoint_store.py`, `harness/artifact_registry.py`
  — already use `datetime.now(timezone.utc)`. They get
  re-routed through the port so a single `FixedTimeService` in
  tests gives deterministic timestamps across all three stores.

The ~315 other call sites stay on `datetime.now()` /
`time.time()` until a per-area migration (e.g. the next
harness slice, the next agent-state slice) replaces them
deliberately. ADR says: **gradual is correct**.

*Pros*: zero new deps; testable; one source of truth; no
unrelated bulk changes; explicit policy in code.

*Cons*: requires every call site to inject a service (or
fall back to the session-default service). Two adapters per
port doubles the surface; small test cost.

### Option B — Monkey-patch `datetime` and `uuid` in tests

Add a fixture that monkey-patches `datetime.now` and
`uuid.uuid4` at the test root.

*Pros*: zero code change in production paths.

*Cons*: makes IDs `int` (not `str`) in some implementations
breaks the existing truncation pattern; cross-process
consistency is harder to reason about; monkey-patching is
brittle and lints flag it.

### Option C — Library (e.g. `pendulum`, `python-ulid`)

*Pros*: feature-rich.

*Cons*: new runtime dep; pendulum is large; ULID requires
choice rationale (sortable vs random); we have no business
need for sortable IDs at this point.

### Option D — Single global module-level helpers

`identity.new_id()` and `time.utc_now()` as module functions
in `flaghunter.domain.identity` /
`flaghunter.domain.clock`.

*Pros*: smaller diff.

*Cons*: globals are not injectable; tests would need
monkey-patching. Loses the port boundary, which is the
auditable decision surface this codebase has committed to
(C-01, C-02, C-03 all set this precedent).

## Decision

**Adopt Option A**.

### ID format

* New IDs are **full 32 hex characters** (`uuid.uuid4().hex`),
  no truncation.
* Optional human-readable prefix: `f"{prefix}_{uuid4_hex}"`,
  e.g. `task_5f3a8c1d0e9b4a7c2f1e8d6b5a4c3b2a`.
* The prefix is **display only**; uniqueness is the UUID4
  suffix. Parsers MUST treat the underscore as a separator and
  the hex string as the canonical id.
* The `_new_id` helpers in `task_dag_plan.py`,
  `ctf_state.py`, and the counter in `worker_pool.py` are
  migrated in this slice. New IDs in `loot/` going forward
  will be 32 hex; pre-existing 16-hex ids remain valid and
  will be migrated as those store areas get reworked (a
  follow-up slice reads the data and bumps the format).

### Time policy

* `utc_now()` returns `datetime.now(timezone.utc)`. **Always
  aware.** Code MUST NOT call `datetime.now()` without a tz
  argument for anything that touches persistence, ordering,
  or display.
* `utc_now_iso()` returns the canonical wire form:
  `datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")`
  — e.g. `"2026-08-04T12:34:56.789012+00:00"` becomes
  `"2026-08-04T12:34:56.789012Z"`. Use this for JSON
  serialisation; consumers parse with `datetime.fromisoformat`
  after replacing the `Z`.
* `monotonic_now()` returns `time.monotonic()`. Use for
  durations; never subtract from a wall clock.
* `time.time()` is reserved for *absolute* time only (i.e.
  when you need "what is the wall-clock value right now?",
  not "how long did this take?"). The existing
  `result_cache.py` TTL math is a real bug — it subtracts two
  wall-clock values to compute age, which is wrong across a
  daylight-saving change. The fix is the C-05 migration of
  that file: switch the TTL math to `monotonic_now` against
  an absolute anchor that is also monotonic.

### Boundary

* `flaghunter/ports/identity_service.py` —
  `IdentityServicePort` Protocol.
* `flaghunter/ports/time_service.py` — `TimeServicePort`
  Protocol.
* `flaghunter/domain/identity_service.py` —
  `UuidIdentityService` (production) and
  `InMemoryIdentityService` (test). New IDs land here so the
  session initializer can wire them in.
* `flaghunter/domain/time_service.py` — `SystemTimeService`
  (production) and `FixedTimeService` (test). The system
  service is the **default**; production code that does not
  inject a service should pull it from the session
  initializer. (The session initializer wire-up is **out of
  scope for C-05**; it lands when a future slice refactors
  the application services to consume the port.)

### Active schemas

* `port.identity_service@v1` and `port.time_service@v1` are
  added to `active_schemas.py` with the existing C-01
  catalogue discipline. `known_active_schema_count` becomes
  14 (3 + 11 port).

## Consequences

### Positive

* Every new ID produced in the system is unique with the
  same probability as `uuid.uuid4()` (122 bits of entropy,
  no truncation).
* Tests can inject deterministic IDs and clocks without
  monkey-patching `uuid` or `time` — strictly better
  composition.
* The ID format and time policy are auditable: one port,
  one ADR, one canonical place to look.
* The C-01 / C-02 / C-03 port-boundary pattern is preserved.

### Negative

* A new `id` and `time` service have to be threaded through
  every call site that wants to use them. The session
  initializer will land in a future slice; until then,
  call sites can fall back to the `UuidIdentityService` /
  `SystemTimeService` constructed ad-hoc. This is a
  **gradual** cost.
* The two `_new_id` helpers and the worker counter all have
  to be migrated; if one is missed, a new id shape can leak
  into `loot/`. The C-05 tests pin the port-shape contract;
  a future slice will pin the no-direct-uuid4-import rule at
  lint-imports level.
* `time.time()` is still used in `result_cache.py` and
  `memory_optimizer.py` after this slice. The masterplan
  §12.5 calls out duration-via-wall-clock as a bug; the fix
  is in this slice for `result_cache.py` (the worst offender
  — TTL math) and deferred to the next turbo slice for
  `memory_optimizer.py` (which is internal to a future C-10
  refactor anyway).

### Neutral

* Existing 16-hex ids in `loot/` continue to parse. The new
  service is 32-hex; the next migration of those stores can
  read both shapes.
* `time.time()` is not banned. It is reserved for absolute
  wall-clock and the few places that need it (e.g. log
  timestamps that are deliberately wall-clock so an operator
  can correlate with `date(1)`). The boundary just makes the
  intent explicit.

## Follow-up

* **Session initializer wire-up** — wire `UuidIdentityService`
  and `SystemTimeService` into the session initializer so
  application services can consume them by injection rather
  than construction.
* **Linter guard** — add an import-linter contract that
  forbids `flaghunter.domain.*` from importing `uuid` or
  `datetime.now` directly; they must go through the ports.
* **`result_cache.py` TTL fix** — the C-05 slice migrates the
  worst of the `time.time()` duration math; a turbo follow-up
  finishes `memory_optimizer.py`.
* **Store migration** — when C-04 (checksum/sequence) and
  C-10 (state store adapter) rewire the harness and
  conversation stores, they will consume both ports in one
  pass rather than incrementally.
* **Format upgrade** — when every consumer of the truncated
  16-hex ids is gone, bump the service to *only* emit 32-hex
  and drop the prefix support. That is a much later migration.
