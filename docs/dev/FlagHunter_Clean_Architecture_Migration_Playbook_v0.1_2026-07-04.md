# FlagHunter Clean Architecture Migration Playbook v0.1

Date: 2026-07-04
Status: active execution playbook
Scope: incremental migration from legacy implementation packages toward neutral clean architecture

## 1. Final Target

FlagHunter should converge toward a pure, modular architecture where the core platform is a general challenge/task framework.

The target dependency direction is:

```text
Presentation -> Application Services -> Domain / Contracts
             -> Ports
Adapters     -> Ports + external systems
Composition Root wires concrete implementations
```

The final state should have these properties:

- Core public contracts use neutral names: challenge, task, claim, evidence, proof, artifact, receipt, read model, checkpoint, policy, strategy.
- Legacy security-specific implementation names remain behind adapters, compatibility shims, fixtures, or historical modules until a focused cleanup removes them.
- Presentation layers consume read models or application services, not mutable legacy state or concrete engines.
- Concrete runtime, tool executor, verifier, worker pool, MCP wiring, and file stores are assembled only in the composition root.
- Proof authority remains a hard boundary: only verifier/proof-authority code may upgrade a claim into accepted proof.
- Every cross-module payload has `schemaVersion` and JSON-friendly fields.
- Every migration slice has boundary tests and source guards.

## 2. Non-Negotiable Rules

### One Functional Point Per Commit

Each functional point must be committed separately.

Allowed single-commit examples:

- Add one contract/read-model package.
- Move one pure read-side contract to a neutral package with compatibility re-export.
- Add one adapter skeleton without production wiring.
- Switch one low-risk read path to a neutral read model.
- Add or tighten one source guard group.

Do not mix contract relocation, production wiring, proof-authority changes, dispatcher changes, and cleanup in the same commit.

### Stop And Revert When A Slice Breaks

If a migration slice breaks tests or behavior in a way that is not immediately understood:

1. Stop editing.
2. Record the failing command and failure summary.
3. Revert only the current functional slice.
4. Re-plan a smaller slice.
5. Re-run the pre-slice verification before retrying.

Never revert unrelated user or parallel-agent work.

### Domain-Neutral Public Naming

New public core package, module, class, function, schema, fixture, and doc names must not introduce these terms:

- `ctf`
- `pentest`
- `exploit`
- `vulnerability`
- `hacking`
- `attack`
- `redteam`

Allowed locations for legacy/security vocabulary:

- Existing legacy modules.
- Adapters wrapping legacy implementation.
- Compatibility shims preserving old imports.
- Security-specific strategy packs or fixtures.
- Historical docs and writeups.

### Proof Authority Rule

Only verifier/proof-authority code may perform proof upgrade actions.

Forbidden outside proof authority:

- direct accepted-proof writes
- legacy verified bucket writes
- `upgrade_claim_to_verified`
- `append_verification_record`
- proof-upgrade decisions emitted by control, tools, model output, replay, audit, readback, or presentation selectors

Read-side modules may display proof already produced by proof authority, but must not create, infer, or upgrade it.

## 3. Approval Gates

### Automatically Executable Low-Risk Work

These can proceed without additional approval once this playbook is approved:

- Pure domain contracts.
- Read models.
- Protocol-only ports.
- Source guards and import guards.
- Adapter skeletons with no production wiring.
- Compatibility re-exports preserving behavior.
- Tests that lock existing behavior or new boundaries.

### Requires A Short Plan Before Execution

These require a plan with file list, risk, rollback point, and verification command before changes:

- Moving a legacy read-side module to neutral contracts.
- Adding an application service that legacy code may later call.
- Adding an adapter wrapper around a concrete implementation.
- Switching a presentation/query path to a neutral read model.
- Updating import-linter layering.

### Requires Explicit Approval

These are high-risk and must be approved as separate slices:

- Changing `CTFTaskDispatcher` production flow or chain dispatch.
- Splitting `CTFState` storage ownership.
- Moving `create_claim`, proof-record append, or proof upgrade ownership.
- Changing `CTFVerifier` production proof behavior.
- Splitting `ToolExecutor.execute` side effects.
- Wiring `WorkerPool` or `CrewOrchestrator` through a production `CrewBridgePort`.
- Rewiring MCP server, CLI, TUI, or web server production task execution.
- Introducing or changing the composition root for production runtime assembly.
- Removing or renaming legacy security-specific modules.
- Changing persisted schema compatibility.

## 4. Migration Route

### Phase 2A: Neutral Read-Side Contract Relocation

Goal: move or copy stable, pure read-side contracts into `flaghunter/domain/challenge/contracts/`.

Initial candidates:

- control receipts
- evidence snapshots
- claim views
- audit views
- ledger event views
- solve node read models
- task graph contracts and replay readbacks

Rules:

- Old import paths remain available.
- Old behavior remains unchanged.
- New neutral package owns stable contract shape.
- Legacy modules may become compatibility shims only after tests prove equivalence.

Acceptance:

- New neutral module imports without concrete dependencies.
- Old path still imports.
- Serialized payloads remain equivalent unless explicitly versioned.
- Source guards forbid concrete imports, side effects, and proof upgrade actions.

### Phase 2B: Compatibility Shims

Goal: old modules re-export neutral contracts while preserving downstream imports.

Rules:

- Do not remove old files yet.
- Do not rename public legacy paths yet.
- Add tests proving old and new imports resolve to the same public contract objects where possible.

Acceptance:

- Existing test suite does not require call-site changes.
- Legacy import path has no new business logic.
- New source guard prevents reintroducing concrete behavior into shim files.

### Phase 3A: Adapter Skeletons

Goal: add adapters that wrap legacy implementations without connecting production call sites.

Initial adapters:

- tool executor adapter
- verifier adapter
- proof authority adapter
- state store adapter
- claim store adapter
- audit store adapter
- artifact store adapter
- checkpoint store adapter
- crew bridge adapter

Rules:

- Adapter names may mention legacy only in private implementation detail if unavoidable.
- Public adapter-facing contracts remain neutral.
- No dispatcher or presentation call site switches in the skeleton commit.

Acceptance:

- Adapter imports the concrete implementation only in adapter package.
- Adapter returns neutral contracts or mappings.
- Source guards prove domain/contracts and ports do not import adapters.

### Phase 3B: First Low-Risk Production Read Path Switch

Goal: switch one presentation/query/readback path to consume a neutral read model.

Rules:

- Choose read-only path first.
- No proof writes.
- No dispatcher loop changes.
- One call site per commit.

Acceptance:

- Old and new output are equivalent for representative fixtures.
- Existing behavior tests pass.
- New boundary test proves presentation does not import legacy state for that path.

### Phase 4: Application Services

Goal: introduce small use cases that orchestrate domain contracts and ports.

Initial use cases:

- build challenge run snapshot
- record task receipt
- build evidence snapshot
- review claim
- record tool receipt
- dispatch worker task

Rules:

- Application services depend on contracts and ports, not concrete runtime/tool/UI/MCP/worker implementations.
- Dispatcher may delegate to one service at a time only after approval.

Acceptance:

- Use case has behavior tests.
- Use case has source guards.
- Concrete dependencies are injected through ports only.

### Phase 5: Production Wiring And Composition Root

Goal: wire real implementations through the composition root.

Rules:

- This phase requires explicit approval per route.
- Runtime, tool executor, verifier, state stores, crew, and MCP wiring are migrated separately.
- Dispatcher main flow is migrated last.

Acceptance:

- CLI/TUI/MCP/web paths construct business components through the composition root.
- No presentation route directly constructs concrete dispatcher/runtime/worker implementations except compatibility facades still under migration.
- Integration and acceptance tests cover each migrated entry point.

### Phase 6: Legacy Cleanup

Goal: remove obsolete compatibility shims and legacy naming only after all call sites have moved.

Rules:

- Cleanup is last, not first.
- Removal requires import scans and downstream compatibility check.
- Historical docs and fixtures may keep legacy names.

Acceptance:

- No production imports depend on removed legacy path.
- Migration notes identify replacements.
- Full relevant regression passes.

## 5. Verification Standard

Every slice must record:

- Branch name.
- Commit SHA.
- Files changed.
- Red test evidence when production behavior or contract behavior is added.
- Focused test command and result.
- Architecture/source-guard command and result.
- `git diff --check` result before commit.
- `git status --short --branch` after commit.

Minimum commands for contract/read-model slices:

```powershell
.\.venv\Scripts\python.exe -m pytest tests/unit/test_import_layers.py tests/unit/agents/test_p1_source_guards.py tests/unit/test_ports_contracts.py tests/unit/test_domain_challenge_contracts.py -q
git diff --check
```

Minimum commands for proof-adjacent slices:

```powershell
.\.venv\Scripts\python.exe -m pytest tests/unit/agents/test_p1_source_guards.py tests/unit/agents/test_p1_claim_invariants.py -q
```

Minimum commands for task graph or replay slices:

```powershell
.\.venv\Scripts\python.exe -m pytest tests/unit/agents/test_p4_task_dag_replay_audit_bundle.py -q
```

Full suite is desirable when speed permits:

```powershell
.\.venv\Scripts\python.exe -m pytest -q
```

If full suite is too slow or blocked by environment, record the limitation honestly and rely on the focused regression set for that slice.

## 6. Completion Checklist

The migration is complete when:

- Core domain contracts live under neutral `flaghunter/domain/challenge/contracts`.
- Stable ports cover tool running, runtime actions, verification, proof authority, state, claims, audit, artifacts, checkpoints, crew, task graph, and read models.
- Legacy implementation is accessed through adapters or compatibility facades.
- Application services own business use cases.
- Presentation consumes read models or application services.
- Composition root wires concrete implementations.
- Proof authority writes are isolated and source-guarded.
- Legacy security-specific public core names no longer expand into new core architecture surfaces.
- Existing behavior and supported entry points pass their regression/acceptance tests.

## 7. Current Execution Status

This ledger records the currently integrated low-risk skeleton work on branch
`codex/flaghunter-domain-challenge-contracts`. It is a planning aid, not a
production-wiring approval.

### Phase 4 application service skeletons completed

These use cases now exist as neutral application services under
`flaghunter/application/challenge/`. They depend only on domain contracts and
ports, have behavior tests, and are covered by the `.importlinter`
`application-service-boundary` contract.

- `BuildChallengeRunSnapshot`
- `RecordTaskReceipt`
- `BuildEvidenceSnapshot`
- `ReviewClaim`
- `RecordToolReceipt`
- `DispatchWorkerTask`
- `BuildChallengeBoardReadModel`

The completed skeletons do not connect production call sites and do not change
the dispatcher loop, `CTFState`, `CTFVerifier`, `ToolExecutor`, crew runtime,
MCP production wiring, or composition root behavior.

### Phase 4 verification baseline

Focused Phase 4 regression should include:

```powershell
.\.venv\Scripts\python.exe -m pytest tests/unit/test_import_layers.py tests/unit/agents/test_p1_source_guards.py tests/unit/agents/test_p1_claim_invariants.py tests/unit/tools/test_finish_control_receipt.py tests/unit/agents/test_p2_audit_export.py tests/unit/agents/test_p2_evidence_snapshot.py tests/unit/agents/test_p2_ledger_event_readback.py tests/unit/agents/test_p4_task_dag_plan_schema.py tests/unit/agents/test_p4_task_dag_ready_selector.py tests/unit/agents/test_p4_task_dag_replay_audit_bundle.py tests/unit/test_ports_contracts.py tests/unit/test_domain_challenge_contracts.py tests/unit/agents/test_phase2b_compatibility_shims.py tests/unit/test_adapter_boundary_skeleton.py tests/unit/test_tool_runner_adapter.py tests/unit/test_runtime_action_adapter.py tests/unit/test_read_model_store_adapter.py tests/unit/test_state_store_adapter.py tests/unit/test_audit_store_adapter.py tests/unit/test_artifact_store_adapter.py tests/unit/test_checkpoint_store_adapter.py tests/unit/test_claim_store_adapter.py tests/unit/test_verifier_adapter.py tests/unit/test_proof_authority_adapter.py tests/unit/test_crew_bridge_adapter.py tests/unit/test_task_dag_runner_adapter.py tests/unit/test_application_challenge_snapshot_service.py tests/unit/test_application_task_receipt_service.py tests/unit/test_application_evidence_snapshot_service.py tests/unit/test_application_claim_review_service.py tests/unit/test_application_tool_receipt_service.py tests/unit/test_application_worker_task_service.py tests/unit/test_application_board_read_model_service.py -q
```

### Challenge board read-model skeleton baseline

Status: neutral read-model builder added before any production path switch.

`BuildChallengeBoardReadModel` now exists under
`flaghunter/application/challenge/` and builds a neutral
`ChallengeBoardReadModel` from an already-neutral `ChallengeRunSnapshot`.
The supporting `BoardItem` and `ChallengeBoardReadModel` contracts live under
`flaghunter/domain/challenge/contracts/` and keep serialized payloads
schema-versioned and JSON-friendly.

This baseline gives Candidate A a guarded neutral read-model landing point, but
it does not connect `flaghunter/interface/blackboard_lite.py`, MCP readback, or
any production route to the new builder.

Boundary confirmation for this baseline:

- no production path switch
- no dispatcher loop changes
- no `CTFState` ownership split
- no `CTFVerifier` proof behavior changes
- no ToolExecutor changes
- no WorkerPool/CrewOrchestrator changes
- no MCP production wiring
- no proof authority behavior changes

### Challenge board read-model sanitization baseline

Status: neutral read-model sanitization guard added before any production path
switch.

`BoardItem` and `ChallengeBoardReadModel` now reuse shared sanitization helpers
for serialized value, source, metadata, decision, candidate, action-result,
recommended-task, and surface-ref payloads. The behavior redacts raw body
content and sensitive token/password/session-style values before the neutral
board read model can become a presentation input.

`tests/unit/test_application_board_read_model_service.py` records this baseline
with a red/green fixture that verifies no raw body or sensitive token leaks from
the new schema-versioned read model payload.

Boundary confirmation for this baseline:

- no production path switch
- no dispatcher loop changes
- no `CTFState` ownership split
- no `CTFVerifier` proof behavior changes
- no ToolExecutor changes
- no WorkerPool/CrewOrchestrator changes
- no MCP production wiring
- no proof authority behavior changes

### Candidate A neutral board projection fixture baseline

Status: neutral projection fixture added before any production path switch.

`build_task_board_projection` now exists as a pure helper under
`flaghunter/application/challenge/board_read_model_service.py`. It projects an
already-neutral `ChallengeBoardReadModel` into the Candidate A-compatible response key shape
used by the current Web blackboard projection:
`facts`, `hypotheses`, `pending_verifications`, `decisions`, `candidates`,
`active_decision`, `action_results`, `recommended_action`, and
`attack_surfaces`.

`tests/unit/test_application_board_read_model_service.py` locks this
equivalence fixture so a future Candidate A implementation slice has a
neutral, source-guarded projection target before any presentation call site is
switched.

Boundary confirmation for this baseline:

- no production path switch
- no dispatcher loop changes
- no `CTFState` ownership split
- no `CTFVerifier` proof behavior changes
- no ToolExecutor changes
- no WorkerPool/CrewOrchestrator changes
- no MCP production wiring
- no proof authority behavior changes

### Candidate A neutral evidence projection baseline

Status: neutral evidence projection fixture added before any production path
switch.

`build_task_board_projection` now preserves non-pending evidence by projecting
it into the Candidate A-compatible `facts` list, while evidence explicitly
marked for pending verification remains under `pending_verifications`. This
keeps neutral evidence read models aligned with the current Web blackboard
display semantics without connecting the new helper to `blackboard_lite.py`.

`tests/unit/test_application_board_read_model_service.py` locks this behavior
with a red/green fixture so future Candidate A implementation work can prove
neutral evidence is not dropped during the projection step.

Boundary confirmation for this baseline:

- no production path switch
- no dispatcher loop changes
- no `CTFState` ownership split
- no `CTFVerifier` proof behavior changes
- no ToolExecutor changes
- no WorkerPool/CrewOrchestrator changes
- no MCP production wiring
- no proof authority behavior changes

### Candidate A neutral degraded projection baseline

Status: degraded-input fixture added before any production path switch.

`build_task_board_projection` now returns a quiet empty projection for missing
read models and tolerates empty or malformed neutral board inputs by omitting
bad rows instead of raising or synthesizing proof/action state. This mirrors the
existing Candidate A degraded-input discipline before any Web blackboard
presentation path is switched to the neutral helper.

`tests/unit/test_application_board_read_model_service.py` records this baseline
so future Candidate A implementation work can preserve empty/malformed behavior
while proving old/new output equivalence.

Boundary confirmation for this baseline:

- no production path switch
- no dispatcher loop changes
- no `CTFState` ownership split
- no `CTFVerifier` proof behavior changes
- no ToolExecutor changes
- no WorkerPool/CrewOrchestrator changes
- no MCP production wiring
- no proof authority behavior changes

### Candidate A neutral malformed board item projection baseline

Status: malformed board item fixture added before any production path switch.

`build_task_board_projection` now omits malformed neutral board item mappings
that do not carry a usable `itemType`. This prevents empty mappings or blank
neutral item kinds from being projected into Candidate A-compatible `facts` or
`pending_verifications` as synthetic empty rows.

`tests/unit/test_application_board_read_model_service.py` records this baseline
with a red/green fixture for malformed facts and pending-verification evidence.
The behavior remains a pure application helper constraint and is not connected
to Web blackboard, MCP readback, dispatcher, or runtime wiring.

Boundary confirmation for this baseline:

- no production path switch
- no dispatcher loop changes
- no `CTFState` ownership split
- no `CTFVerifier` proof behavior changes
- no ToolExecutor changes
- no WorkerPool/CrewOrchestrator changes
- no MCP production wiring
- no proof authority behavior changes

### Candidate A neutral recommended action projection baseline

Status: recommended-action fallback fixture added before any production path
switch.

`build_task_board_projection` now derives a Candidate A-compatible
`recommended_action` from already-neutral candidates, the active decision, and
action results when no explicit `recommendedTask` is present. The fixture locks
the selected-action failed/skipped fallback shape, trigger provenance fields,
and the recommended candidate marker without reading legacy state.

`tests/unit/test_application_board_read_model_service.py` records this baseline
so a future Web blackboard read-path switch can prove selected/recommended
candidate semantics against a neutral projection target before touching
presentation wiring.

Boundary confirmation for this baseline:

- no production path switch
- no dispatcher loop changes
- no `CTFState` ownership split
- no `CTFVerifier` proof behavior changes
- no ToolExecutor changes
- no WorkerPool/CrewOrchestrator changes
- no MCP production wiring
- no proof authority behavior changes

### Candidate A neutral explicit recommendation marker baseline

Status: explicit recommended-task candidate marker fixture added before any
production path switch.

`build_task_board_projection` now preserves an explicit neutral
`recommendedTask` as the authoritative `recommended_action` and marks the
matching neutral candidate as recommended. This keeps explicit planner/read
model guidance from being overwritten by fallback derivation while preserving
the Candidate A selected/recommended candidate marker shape.

`tests/unit/test_application_board_read_model_service.py` records this baseline
with a red/green fixture that proves explicit recommendation data takes
priority over derived trigger details and remains pure read-model projection
logic.

Boundary confirmation for this baseline:

- no production path switch
- no dispatcher loop changes
- no `CTFState` ownership split
- no `CTFVerifier` proof behavior changes
- no ToolExecutor changes
- no WorkerPool/CrewOrchestrator changes
- no MCP production wiring
- no proof authority behavior changes

### Candidate A neutral candidate/action-result degraded baseline

Status: malformed candidate/action-result fixture added before any production
path switch.

`build_task_board_projection` now omits malformed neutral candidate rows
without a usable `action` and action-result rows without both `action` and
`result`. This prevents empty candidate/action records from becoming part of
the Candidate A-compatible projection before any presentation path consumes the
neutral helper.

`tests/unit/test_application_board_read_model_service.py` records this baseline
with a red/green fixture so future Web blackboard read-path work can preserve
degraded-input behavior while still proving old/new output equivalence.

Boundary confirmation for this baseline:

- no production path switch
- no dispatcher loop changes
- no `CTFState` ownership split
- no `CTFVerifier` proof behavior changes
- no ToolExecutor changes
- no WorkerPool/CrewOrchestrator changes
- no MCP production wiring
- no proof authority behavior changes

### Candidate A neutral suppressed recommendation baseline

Status: suppressed-recommendation fixture added before any production path
switch.

`build_task_board_projection` now preserves a neutral active decision's
`suppressedRecommendation` read model while avoiding a newly derived
`recommended_action` from failed selected-action results. This keeps
suppression as display/read-model state rather than converting it into a fresh
action recommendation.

`tests/unit/test_application_board_read_model_service.py` records this baseline
with a red/green fixture so future Web blackboard read-path work can preserve
suppressed recommendation semantics before any presentation wiring changes.

Boundary confirmation for this baseline:

- no production path switch
- no dispatcher loop changes
- no `CTFState` ownership split
- no `CTFVerifier` proof behavior changes
- no ToolExecutor changes
- no WorkerPool/CrewOrchestrator changes
- no MCP production wiring
- no proof authority behavior changes

### Application service source guard baseline

Status: source guard added before production wiring.

`tests/unit/test_application_service_source_guards.py` now guards the neutral
application service package so application services import only neutral contracts and ports. The guard confirms:

- no concrete execution imports
- no side-effect sinks
- no proof upgrade surfaces
- no production wiring

This baseline is not a dispatcher, MCP, crew, runtime, verifier, or composition
root change. It exists so later application-service slices cannot accidentally
reach into concrete legacy implementations while clean architecture wiring is
still pending approval.

### Adapter port substitution fixture baseline

Status: substitution fixture added before production wiring.

`tests/unit/test_adapter_port_substitution.py` now proves injected ports can be substituted without production wiring for the tool runner and runtime action adapters.
The fixture uses fake injected ports and confirms the adapters
delegate to those injected objects rather than constructing concrete runtime or
tool executor implementations.

Boundary confirmation for this baseline:

- no concrete runtime or tool executor construction
- no dispatcher, MCP, crew, or proof authority wiring
- no production wiring
- no behavior changes in existing runtime paths

### Storage adapter substitution fixture baseline

Status: substitution fixture added before production wiring.

`tests/unit/test_adapter_port_substitution.py` now proves fake injected stores can be substituted without production wiring for the state, read model, claim, and checkpoint store adapters.
The fixture confirms storage adapters delegate to injected stores rather than
constructing file-backed stores or reaching into runtime task state.

Boundary confirmation for this baseline:

- no file-backed store construction
- no dispatcher, MCP, crew, or proof authority wiring
- no production wiring
- no behavior changes in existing storage paths

### Audit/artifact adapter substitution fixture baseline

Status: substitution fixture added before production wiring.

`tests/unit/test_adapter_port_substitution.py` now proves fake injected stores can be substituted without production wiring for the audit and artifact store adapters.
The fixture confirms audit and artifact adapters delegate to injected stores
rather than constructing audit logs, artifact files, runtime stores, or
production persistence paths.

Boundary confirmation for this baseline:

- no audit log or artifact file construction
- no dispatcher, MCP, crew, or proof authority wiring
- no production wiring
- no behavior changes in existing audit or artifact paths

### Crew/task graph adapter substitution fixture baseline

Status: substitution fixture added before production wiring.

`tests/unit/test_adapter_port_substitution.py` now proves fake injected runners can be substituted without production wiring for the crew bridge and task graph runner adapters.
The fixture confirms crew-facing adapters delegate to injected runners rather
than constructing `WorkerPool`, `CrewOrchestrator`, task execution loops,
runtime implementations, or proof authority components.

Boundary confirmation for this baseline:

- no WorkerPool or CrewOrchestrator construction
- no dispatcher, MCP, runtime, or proof authority wiring
- no production wiring
- no behavior changes in existing crew or task graph paths

### Verifier adapter substitution fixture baseline

Status: substitution fixture added before production wiring.

`tests/unit/test_adapter_port_substitution.py` now proves fake injected reviewers can be substituted without production wiring for the verifier adapter.
The fixture confirms verifier adapters delegate to injected reviewers rather
than constructing `CTFVerifier`, invoking proof authority writes, or reaching
into dispatcher, runtime, MCP, or crew wiring.

Boundary confirmation for this baseline:

- no proof authority writes
- no CTFVerifier construction
- no dispatcher, MCP, runtime, or crew wiring
- no production wiring
- no proof authority behavior changes

### Adapter substitution source guard baseline

Status: source guard added for substitution fixtures.

`tests/unit/test_adapter_substitution_source_guards.py` now guards
`tests/unit/test_adapter_port_substitution.py` so substitution fixtures do not import concrete layers while proving adapter replaceability. The guard confirms:

- no side-effect sinks
- no proof authority write surfaces
- no production wiring

This baseline keeps the adapter substitution fixtures focused on fake injected
ports and prevents them from becoming an accidental production-wiring path.

### Adapter substitution runway completed

Status: low-risk adapter substitution fixture runway completed.

The adapter substitution fixture baseline now covers:

- tool runner and runtime action adapters
- state, read model, claim, and checkpoint store adapters
- audit and artifact store adapters
- crew bridge and task graph runner adapters
- verifier adapter
- substitution source guard

These fixtures prove adapter skeletons can delegate to injected fake ports
without constructing concrete legacy implementations. They do not approve or
perform production wiring.

The next adapter work requires a short plan or explicit approval, depending on the target route:

- adapter wrappers around concrete implementations require a short plan with
  file list, risk, rollback point, and verification command
- production wiring, composition root changes, dispatcher flow changes,
  ToolExecutor changes, WorkerPool/CrewOrchestrator changes, MCP wiring, and
  proof authority behavior changes require explicit approval

Boundary confirmation for this runway:

- no production wiring has been approved by these fixtures
- no dispatcher loop changes
- no MCP production wiring
- no ToolExecutor changes
- no WorkerPool/CrewOrchestrator construction
- no proof authority behavior changes

### Next approval gate

The next material step is no longer another neutral skeleton by default; it is
choosing a first production read path or wiring route. Any slice that touches
production wiring, composition root, `CTFTaskDispatcher`, `CTFState`,
`CTFVerifier`, `ToolExecutor`, `WorkerPool`, `CrewOrchestrator`, MCP production
wiring, persisted schema compatibility, or proof authority behavior requires a
separate approval plan before implementation.

Recommended next low-risk alternatives before wiring:

- Add or tighten source guards for application service behavior.
- Add adapter fixtures that prove injected ports can be substituted without
  production wiring.
- Identify one read-only presentation/query path candidate and prepare an
  approval plan with file list, risk, rollback point, and verification command.

### Read-only presentation/query path candidate audit

This audit names candidate call sites for a future first read-path switch. It
does not approve implementation. The switch itself must be a separate slice.

Candidate A: Web blackboard snapshot projection.

- Current path:
  `flaghunter/interface/blackboard_lite.py::build_task_blackboard_snapshot`
- Current coupling fact: the module imports legacy `CTFState` and reconstructs
  state from `ctfStateSnapshot` for display-only blackboard facts, hypotheses,
  pending verification items, candidates, action results, and attack surfaces.
- Candidate direction: replace the display projection input with a neutral
  `ChallengeRunSnapshot` or application-service-built read model while
  preserving the existing serialized blackboard response shape.
- Risk: medium. This path feeds Web task detail and MCP readback formatting.
- Required approval: short plan before implementation; no dispatcher loop
  changes, no proof writes, no production wiring changes.

#### Candidate A approval plan

Status: approval required before implementation.

Scope: prepare a future read-only switch for the Web blackboard snapshot
projection. The current helper reads `ctfStateSnapshot`, reconstructs legacy
`CTFState`, and projects display-only facts, hypotheses, pending verification
items, candidates, action results, active decision state, recommended action,
and attack surfaces. The future implementation should introduce a neutral
blackboard projection builder or application-service-built read model while
preserving the existing public snapshot shape.

File list for the future implementation slice:

- `flaghunter/interface/blackboard_lite.py::build_task_blackboard_snapshot`
- `tests/unit/interface/test_blackboard_lite.py`
- optional neutral projection builder under `flaghunter/application/challenge/`
  or `flaghunter/domain/challenge/contracts/` only if it remains a pure,
  read-only neutral blackboard projection builder

Required fixture evidence:

- old/new output equivalence for representative existing
  `ctfStateSnapshot` inputs
- old/new output equivalence for missing or malformed state snapshots
- old/new output equivalence for decision records, ingress handoff, session
  context action results, candidates, and attack surfaces
- no proof writes and no proof authority decisions

Risk: medium. The path is read-only, but it feeds Web task detail, task API
serialization, control-decision inputs, and MCP readback formatting. The first
implementation slice must preserve field names, list ordering where currently
tested, selected/recommended candidate semantics, and formatting helper output.

Rollback point: revert the single Candidate A implementation commit. No schema
migration, production wiring, MCP handler rewiring, or composition-root change
should be introduced in that commit.

Verification commands for the future implementation slice:

```powershell
.\.venv\Scripts\python.exe -m pytest tests/unit/interface/test_blackboard_lite.py -q
.\.venv\Scripts\python.exe -m pytest tests/unit/test_clean_architecture_migration_playbook.py tests/unit/test_import_layers.py tests/unit/agents/test_p1_source_guards.py tests/unit/test_ports_contracts.py tests/unit/test_domain_challenge_contracts.py -q
git diff --check
```

Explicit non-goals for Candidate A:

- no dispatcher loop changes
- no `CTFState` ownership split
- no `CTFVerifier` proof behavior changes
- no ToolExecutor changes
- no WorkerPool/CrewOrchestrator changes
- no MCP production wiring
- no composition root changes
- no concrete adapter implementation
- no proof authority behavior changes
- no P5 implementation

#### Candidate A implementation readiness checklist

Status: ready for approval review, not approved for implementation.

The neutral projection runway for Candidate A now has these pre-switch
baselines recorded:

- neutral board projection fixture baseline
- neutral evidence projection baseline
- neutral degraded projection baseline
- neutral malformed board item projection baseline
- neutral recommended action projection baseline
- neutral explicit recommendation marker baseline
- neutral candidate/action-result degraded baseline
- neutral suppressed recommendation baseline
- Candidate A Web blackboard fixture evidence:
  `test_candidate_a_pre_approval_guard_blocks_neutral_builder_wiring`
  `test_candidate_a_representative_fixture_locks_public_projection_shape`
  `test_candidate_a_missing_or_malformed_state_snapshot_baseline`
  `test_candidate_a_decision_ingress_action_result_baseline`

Implementation gate:

- approval is still required before editing `flaghunter/interface/blackboard_lite.py`
- one implementation commit only
- old/new output equivalence must be proven in `tests/unit/interface/test_blackboard_lite.py`
- do not modify `flaghunter/mcp/server/mcp_tools.py`
- do not modify `flaghunter/interface/web_serialize_task.py`
- do not modify `flaghunter/interface/web_control_decision.py`
- do not change dispatcher, verifier, tool executor, crew, MCP production
  wiring, composition root, or proof authority behavior

Required verification for the future implementation slice:

```powershell
.\.venv\Scripts\python.exe -m pytest tests/unit/interface/test_blackboard_lite.py -q
.\.venv\Scripts\python.exe -m pytest tests/unit/test_application_board_read_model_service.py tests/unit/test_clean_architecture_migration_playbook.py -q
.\.venv\Scripts\python.exe -m pytest tests/unit/test_import_layers.py tests/unit/agents/test_p1_source_guards.py tests/unit/test_ports_contracts.py tests/unit/test_domain_challenge_contracts.py -q
git diff --check
```

#### Candidate A implementation approval request

Status: approval requested, not approved.

This request asks for approval to run the first Candidate A implementation
slice after the neutral projection runway and Web blackboard characterization
fixtures are in place. The future change would switch only the read-only Web
blackboard projection builder toward the neutral board projection helper while
preserving the public response shape.

File list for the future implementation slice:

- `flaghunter/interface/blackboard_lite.py`
- `tests/unit/interface/test_blackboard_lite.py`
- `flaghunter/application/challenge/board_read_model_service.py` only if the
  future implementation needs a small pure projection helper adjustment; no
  production wiring should be added there.

risk: medium. The target helper is a read-only Web task detail projection
input, but it feeds API serialization/control-decision inputs and
MCP readback formatting indirectly through existing callers. The implementation
must prove old/new output equivalence before replacing any read-side projection
path.

rollback point: revert the single Candidate A implementation commit.

Required fixture evidence:

- old/new output equivalence for representative existing `ctfStateSnapshot`
  task detail input
- old/new output equivalence for missing or malformed state snapshots
- old/new output equivalence for decision records, ingress handoff, session
  context action results, candidates, and surface summaries
- preserved selected/recommended candidate semantics
- no proof writes and no proof authority decisions

Forbidden companion edits:

- do not modify `flaghunter/mcp/server/mcp_tools.py`
- do not modify `flaghunter/interface/web_serialize_task.py`
- do not modify `flaghunter/interface/web_control_decision.py`

Explicit non-goals for the requested Candidate A implementation slice:

- no dispatcher loop changes
- no `CTFState` ownership split
- no `CTFVerifier` proof behavior changes
- no ToolExecutor changes
- no WorkerPool/CrewOrchestrator changes
- no MCP production wiring
- no composition root changes
- no concrete adapter implementation
- no proof authority behavior changes
- no P5 implementation

Required verification for the requested implementation slice:

```powershell
.\.venv\Scripts\python.exe -m pytest tests/unit/interface/test_blackboard_lite.py -q
.\.venv\Scripts\python.exe -m pytest tests/unit/test_application_board_read_model_service.py tests/unit/test_clean_architecture_migration_playbook.py -q
.\.venv\Scripts\python.exe -m pytest tests/unit/test_import_layers.py tests/unit/agents/test_p1_source_guards.py tests/unit/test_ports_contracts.py tests/unit/test_domain_challenge_contracts.py -q
git diff --check
```

#### Candidate A source guard baseline

Status: source guard added before any production path switch.

`tests/unit/interface/test_blackboard_lite.py` now guards
`flaghunter/interface/blackboard_lite.py::build_task_blackboard_snapshot` as a
read-only presentation projection. The guard allows the existing legacy
`CTFState` read dependency while confirming:

- no execution/runtime imports beyond existing read-side projection dependencies
- no proof upgrade surfaces
- no production path switch

This baseline keeps Candidate A stable until an approved neutral blackboard
projection builder can prove output equivalence.

#### Candidate A representative fixture baseline

Status: representative fixture added before any production path switch.

`tests/unit/interface/test_blackboard_lite.py` now includes
`test_candidate_a_representative_fixture_locks_public_projection_shape` as the
first broad Candidate A equivalence fixture. It locks the current public Web
blackboard projection shape for representative existing `ctfStateSnapshot` inputs,
including decision records, ingress handoff, session context action results,
candidates and attack surfaces.

This fixture is not a neutral read-model switch. It exists so a future neutral
blackboard projection builder can prove old/new output equivalence before any
Candidate A implementation changes are approved.

Boundary confirmation for this baseline:

- no production path switch
- no dispatcher loop changes
- no `CTFState` ownership split
- no `CTFVerifier` proof behavior changes
- no ToolExecutor changes
- no WorkerPool/CrewOrchestrator changes
- no MCP production wiring
- no proof authority behavior changes

#### Candidate A missing/malformed fixture baseline

Status: missing/malformed fixture added before any production path switch.

`tests/unit/interface/test_blackboard_lite.py` now includes
`test_candidate_a_missing_or_malformed_state_snapshot_baseline`. It locks the
current public Web blackboard projection behavior for missing or malformed state
snapshots, including resume facts and selected ingress candidate output.

This fixture is not a neutral read-model switch. It exists so a future neutral
blackboard projection builder can prove old/new output equivalence for degraded
state inputs before any Candidate A implementation changes are approved.

Boundary confirmation for this baseline:

- no production path switch
- no dispatcher loop changes
- no `CTFState` ownership split
- no `CTFVerifier` proof behavior changes
- no ToolExecutor changes
- no WorkerPool/CrewOrchestrator changes
- no MCP production wiring
- no proof authority behavior changes

#### Candidate A decision/ingress/action-result fixture baseline

Status: decision/ingress/action-result fixture added before any production path
switch.

`tests/unit/interface/test_blackboard_lite.py` now includes
`test_candidate_a_decision_ingress_action_result_baseline`. It locks the
current public Web blackboard projection behavior for decision records, ingress handoff, and session context action results,
including selected candidate and recommended action ordering.

This fixture is not a neutral read-model switch. It exists so a future neutral
blackboard projection builder can prove old/new output equivalence for
decision/readback merge semantics before any Candidate A implementation changes
are approved.

Boundary confirmation for this baseline:

- no production path switch
- no dispatcher loop changes
- no `CTFState` ownership split
- no `CTFVerifier` proof behavior changes
- no ToolExecutor changes
- no WorkerPool/CrewOrchestrator changes
- no MCP production wiring
- no proof authority behavior changes

Candidate B: Web control-observation trace timeline.

- Current path:
  `flaghunter/interface/web_trace_timeline.py::_build_control_observation_timeline_events`
- Current coupling fact: this pure presentation helper reads
  `task["ctfStateSnapshot"]["observations"]` as dictionaries and projects a
  limited display timeline for bootstrap/resume observations.
- Candidate direction: consume neutral evidence/read-model references from a
  task detail DTO, leaving event shape unchanged.
- Risk: low-to-medium. It is read-only and localized, but timeline fixtures must
  prove output equivalence.
- Required approval: short plan before implementation with representative
  fixture coverage and rollback point.

#### Candidate B approval plan

Status: approval required before implementation.

Scope: prepare a future read-only switch for the Web control-observation trace
timeline. The helper currently reads
`task["ctfStateSnapshot"]["observations"]`, supports
`initial_fact_collection_requested` and `resume_bootstrap_hint`, and projects
display-only timeline events. The future implementation should accept neutral
evidence/read-model references from the task detail DTO while preserving the
existing timeline event shape.

File list for the future implementation slice:

- `flaghunter/interface/web_trace_timeline.py::_build_control_observation_timeline_events`
- `tests/unit/web_console/test_trace_timeline_read_model_switch.py`
- a representative fixture that contains the two supported observation kinds
  plus ignored malformed or unsupported rows

Required fixture evidence:

- old/new output equivalence for the existing
  `ctfStateSnapshot.observations` input shape
- old/new output equivalence for the neutral read-model input shape once added
- empty and malformed input behavior remains unchanged
- no proof writes and no proof authority decisions

Risk: low-to-medium. The code path is localized and read-only, but it feeds a
user-facing timeline, so the event IDs, timestamps, `kind`, `title`, `summary`,
`driver`, and `input` fields must remain stable for representative fixture
coverage.

Rollback point: revert the single Candidate B implementation commit. No schema
migration or production wiring should be introduced in that commit.

Verification commands for the future implementation slice:

```powershell
.\.venv\Scripts\python.exe -m pytest tests/unit/web_console/test_trace_timeline_read_model_switch.py -q
.\.venv\Scripts\python.exe -m pytest tests/unit/test_clean_architecture_migration_playbook.py tests/unit/test_import_layers.py tests/unit/agents/test_p1_source_guards.py tests/unit/test_ports_contracts.py tests/unit/test_domain_challenge_contracts.py -q
git diff --check
```

Explicit non-goals for Candidate B:

- no dispatcher loop changes
- no `CTFState` ownership split
- no `CTFVerifier` proof behavior changes
- no ToolExecutor changes
- no WorkerPool/CrewOrchestrator changes
- no MCP production wiring
- no composition root changes
- no concrete adapter implementation
- no proof authority behavior changes
- no P5 implementation

#### Candidate B characterization baseline

Status: test baseline added before any production path switch.

The fixture test
`tests/unit/web_console/test_trace_timeline_read_model_switch.py` locks the
existing control-observation timeline output for the two supported observation
kinds, ignored malformed rows, empty input handling, default resume-bootstrap
fields, and no task mutation. This baseline exists so a future neutral
read-model switch can prove output equivalence before changing the presentation
helper.

Boundary confirmation for this baseline:

- no production path switch
- no dispatcher loop changes
- no `CTFState` ownership split
- no `CTFVerifier` proof behavior changes
- no ToolExecutor changes
- no WorkerPool/CrewOrchestrator changes
- no MCP production wiring
- no proof authority behavior changes

#### Candidate B source guard baseline

Status: source guard added before any production path switch.

`tests/unit/web_console/test_trace_timeline_read_model_switch.py` now guards
`_build_control_observation_timeline_events` so the localized presentation
helper remains read-only while Candidate B is prepared. The guard confirms:

- no concrete execution imports
- no side-effect sinks
- no proof upgrade surfaces

These constraints must hold before the neutral read-model switch is approved.

#### Candidate B implementation readiness checklist

Status: ready for approval review, not approved for implementation.

The control-observation trace timeline runway now has these pre-switch
baselines recorded:

- Candidate B approval plan
- Candidate B characterization baseline
- Candidate B source guard baseline
- Candidate B trace timeline fixture evidence:
  `test_control_observation_timeline_projects_supported_rows`
  `test_control_observation_timeline_handles_empty_or_malformed_input`
  `test_trace_timeline_includes_observations_without_mutating_task`
  `test_control_observation_timeline_source_stays_read_only`

Readiness scope for the future implementation slice:

- target only
  `flaghunter/interface/web_trace_timeline.py::_build_control_observation_timeline_events`
- use `tests/unit/web_console/test_trace_timeline_read_model_switch.py` as the
  required old/new output equivalence fixture home
- preserve event IDs, timestamps, `kind`, `title`, `summary`, `driver`, and `input` fields
- preserve empty, malformed, unsupported, and no-mutation behavior
- no proof writes and no proof authority decisions

Implementation gate:

- approval is still required before editing `flaghunter/interface/web_trace_timeline.py`
- one implementation commit only
- rollback point: revert the single Candidate B implementation commit
- no schema migration or production wiring in the implementation commit

Required verification for the future implementation slice:

```powershell
.\.venv\Scripts\python.exe -m pytest tests/unit/web_console/test_trace_timeline_read_model_switch.py -q
.\.venv\Scripts\python.exe -m pytest tests/unit/test_clean_architecture_migration_playbook.py tests/unit/test_import_layers.py tests/unit/agents/test_p1_source_guards.py tests/unit/test_ports_contracts.py tests/unit/test_domain_challenge_contracts.py -q
git diff --check
```

Explicit non-goals for the requested Candidate B implementation slice:

- no dispatcher loop changes
- no `CTFState` ownership split
- no `CTFVerifier` proof behavior changes
- no ToolExecutor changes
- no WorkerPool/CrewOrchestrator changes
- no MCP production wiring
- no composition root changes
- no concrete adapter implementation
- no proof authority behavior changes
- no P5 implementation

Candidate C: Web task serialization and control-decision snapshot merge.

- Current paths:
  `flaghunter/interface/web_serialize_task.py::_serialize_task`
  and
  `flaghunter/interface/web_control_decision.py::_task_blackboard_snapshot_for_decision`
- Current coupling fact: these helpers call `build_task_blackboard_snapshot` and
  merge the result into task API projection/control-decision inputs.
- Candidate direction: switch only after Candidate A has an equivalent neutral
  blackboard projection builder.
- Risk: medium-to-high. This is a fan-out path for task list/detail, retry,
  continue, and control decision views.
- Required approval: separate short plan; one call-site family per commit.

#### Candidate C approval plan

Status: approval required before implementation.

Prerequisite: proceed only after Candidate A output equivalence is proven for a
neutral blackboard projection builder. Candidate C must not introduce a second
projection shape or bypass the Candidate A equivalence fixtures.

Scope: prepare future read-only switches for the Web task serialization and
control-decision snapshot merge paths. The current helpers call
`build_task_blackboard_snapshot`, merge existing `blackboardSnapshot` payloads,
and feed task detail serialization, retry/continue/control-decision flows, and
active decision summaries.

File list for the future implementation slices:

- `flaghunter/interface/web_serialize_task.py::_serialize_task`
- `flaghunter/interface/web_control_decision.py::_task_blackboard_snapshot_for_decision`
- existing Candidate A fixtures in `tests/unit/interface/test_blackboard_lite.py`
- focused Web serialization/control-decision fixture tests added only as needed

Required fixture evidence:

- old/new output equivalence for `_serialize_task` task detail output
- old/new output equivalence for `_task_blackboard_snapshot_for_decision`
- preserved fallback merge behavior between rebuilt and existing
  `blackboardSnapshot`
- preserved active decision summary and next-action explanation fields
- no proof writes and no proof authority decisions

Risk: medium-to-high. This is a fan-out path for task list/detail, retry,
continue, and control-decision views. Implementation must use one call-site
family per commit: serialize-task projection first, control-decision snapshot
merge second, and no MCP readback change in either commit.

Rollback point: revert the single Candidate C implementation commit for the
affected call-site family. No schema migration, MCP handler rewiring,
composition-root change, or production execution wiring should be introduced in
that commit.

Verification commands for the future implementation slices:

```powershell
.\.venv\Scripts\python.exe -m pytest tests/unit/interface/test_blackboard_lite.py tests/unit/test_clean_architecture_migration_playbook.py -q
.\.venv\Scripts\python.exe -m pytest tests/unit/test_import_layers.py tests/unit/agents/test_p1_source_guards.py tests/unit/test_ports_contracts.py tests/unit/test_domain_challenge_contracts.py -q
git diff --check
```

Explicit non-goals for Candidate C:

- no dispatcher loop changes
- no `CTFState` ownership split
- no `CTFVerifier` proof behavior changes
- no ToolExecutor changes
- no WorkerPool/CrewOrchestrator changes
- no MCP production wiring
- no composition root changes
- no concrete adapter implementation
- no proof authority behavior changes
- no P5 implementation

#### Candidate C source guard baseline

Status: source guard added before any production path switch.

`tests/unit/interface/test_web_server.py` now guards
`flaghunter/interface/web_serialize_task.py::_serialize_task` and
`flaghunter/interface/web_control_decision.py::_task_blackboard_snapshot_for_decision`
as read-only projection/merge helpers. The guard confirms:

- no execution/runtime imports
- no side-effect sinks
- no proof upgrade surfaces

These constraints must hold until Candidate A output equivalence is proven and
Candidate C implementation is approved.

#### Candidate C implementation readiness checklist

Status: blocked on Candidate A approval, not approved for implementation.

Candidate C remains downstream of Candidate A. It may proceed only after
Candidate A output equivalence is proven and the neutral blackboard projection
builder is approved for the first production read-path switch.

Current pre-switch baselines recorded:

- Candidate C approval plan
- Candidate C source guard baseline
- Candidate C serialize-task projection fixture baseline:
  `test_candidate_c_serialize_task_fixture_preserves_snapshot_and_summaries_before_switch`
- Candidate C control-decision snapshot merge fixture baseline:
  `test_candidate_c_control_decision_snapshot_merge_fixture_before_switch`
- existing Candidate A fixtures in `tests/unit/interface/test_blackboard_lite.py`
- Web projection/merge guards in `tests/unit/interface/test_web_server.py`

Readiness scope for future implementation slices:

- `flaghunter/interface/web_serialize_task.py::_serialize_task`
- `flaghunter/interface/web_control_decision.py::_task_blackboard_snapshot_for_decision`
- one call-site family per commit
- serialize-task projection first
- control-decision snapshot merge second
- no MCP readback change in either Candidate C commit

Required fixture evidence:

- old/new output equivalence for serialized task detail output
- old/new output equivalence for control-decision snapshot merge output
- preserved fallback merge behavior between rebuilt and existing
  `blackboardSnapshot`
- preserved active decision summary and next-action explanation fields
- no proof writes and no proof authority decisions

Implementation gate:

- Candidate A must be approved and implemented first
- approval is still required before editing either Candidate C production helper
- rollback point: revert the single Candidate C implementation commit for the
  affected call-site family
- no schema migration, MCP handler rewiring, composition-root change, or
  production execution wiring in either Candidate C commit

Required verification for future Candidate C implementation slices:

```powershell
.\.venv\Scripts\python.exe -m pytest tests/unit/interface/test_blackboard_lite.py tests/unit/test_clean_architecture_migration_playbook.py -q
.\.venv\Scripts\python.exe -m pytest tests/unit/interface/test_web_server.py tests/unit/test_clean_architecture_migration_playbook.py -q
.\.venv\Scripts\python.exe -m pytest tests/unit/test_import_layers.py tests/unit/agents/test_p1_source_guards.py tests/unit/test_ports_contracts.py tests/unit/test_domain_challenge_contracts.py -q
git diff --check
```

Explicit non-goals for the requested Candidate C implementation slices:

- no dispatcher loop changes
- no `CTFState` ownership split
- no `CTFVerifier` proof behavior changes
- no ToolExecutor changes
- no WorkerPool/CrewOrchestrator changes
- no MCP production wiring
- no composition root changes
- no concrete adapter implementation
- no proof authority behavior changes
- no P5 implementation

Deferred MCP readback candidate:

- Current path:
  `flaghunter/mcp/server/mcp_tools.py::_append_blackboard_snapshot_lines`
- Current coupling fact: MCP imports presentation blackboard builders and uses
  task state snapshots for readback text.
- Candidate direction: defer until Web read-model projection equivalence is
  proven. MCP production wiring remains out of scope for this candidate audit.
- Required approval: explicit MCP production wiring approval before any handler
  route is rewired.

#### Deferred MCP readback approval plan

Status: approval required before implementation.

Prerequisite: proceed only after Web read-model projection equivalence is proven
for the neutral blackboard/read-model path. MCP readback must consume the same
approved read-model projection and must not become an independent projection
shape.

Scope: prepare a future read-only switch for MCP blackboard readback text. The
current helper imports presentation blackboard builders and formats task state
snapshots into user-facing lines. The future implementation should preserve the
existing line text, ordering, and omission behavior while using the approved
neutral read-model projection as input.

File list for the future implementation slice:

- `flaghunter/mcp/server/mcp_tools.py::_append_blackboard_snapshot_lines`
- focused MCP readback fixture tests for representative blackboard snapshot
  lines
- the already-approved Web read-model projection fixtures that prove the input
  projection shape is equivalent

Required fixture evidence:

- old/new output equivalence for representative MCP readback text
- old/new output equivalence for empty, missing, or malformed blackboard
  snapshot inputs
- preserved ordering for facts, hypotheses, pending verification items,
  candidates, action results, and attack surfaces already emitted by the helper
- no proof writes and no proof authority decisions

Risk: high. The helper is read-only, but it lives inside MCP server task
readback code, so implementation counts as MCP production wiring unless
explicitly approved. It must be isolated as one MCP readback commit and must not
change task execution, task creation, async task tracking, or handler routing.

Rollback point: revert the single Deferred MCP implementation commit. No schema
migration, dispatcher loop change, ToolExecutor change, WorkerPool/CrewOrchestrator
change, composition-root change, or proof authority behavior change should be
introduced in that commit.

Verification commands for the future implementation slice:

```powershell
.\.venv\Scripts\python.exe -m pytest tests/unit/test_clean_architecture_migration_playbook.py -q
.\.venv\Scripts\python.exe -m pytest tests/unit/test_import_layers.py tests/unit/agents/test_p1_source_guards.py tests/unit/test_ports_contracts.py tests/unit/test_domain_challenge_contracts.py -q
git diff --check
```

Explicit non-goals for Deferred MCP:

- no MCP production wiring without explicit approval
- no dispatcher loop changes
- no `CTFState` ownership split
- no `CTFVerifier` proof behavior changes
- no ToolExecutor changes
- no WorkerPool/CrewOrchestrator changes
- no composition root changes
- no concrete adapter implementation
- no proof authority behavior changes
- no P5 implementation

#### Deferred MCP source guard baseline

Status: source guard added before any MCP readback implementation.

`tests/unit/mcp/test_mcp_ingress_mode_contract.py` now guards
`flaghunter/mcp/server/mcp_tools.py::_append_blackboard_snapshot_lines` as a
read-only MCP readback projection helper. The guard leaves current behavior
unchanged while confirming:

- no task execution or handler routing changes
- no side-effect sinks
- no proof upgrade surfaces
- no MCP production wiring

This baseline must stay in place until Web read-model projection equivalence is
proven and a separate MCP production wiring approval is granted.

#### Deferred MCP pre-approval production wiring guard

Status: source guard added before any Deferred MCP implementation approval.

`tests/unit/mcp/test_mcp_ingress_mode_contract.py` now guards
`flaghunter/mcp/server/mcp_tools.py::_append_blackboard_snapshot_lines`
against importing or calling neutral challenge board/read-model projection
helpers while Deferred MCP remains blocked on Web projection equivalence and
explicit MCP approval, not approved.

Current approval fact:

- Deferred MCP: blocked on Web projection equivalence and explicit MCP approval, not approved

This guard must remain active until Web projection equivalence lands and
explicit MCP production wiring approval is granted. Updating the guard is
allowed only in the same Deferred MCP implementation commit that proves old/new
MCP readback output equivalence.

Forbidden before approval:

- import `flaghunter.application.challenge`
- import `flaghunter.domain.challenge.contracts`
- call `build_task_board_projection`
- construct `BuildChallengeBoardReadModel`
- construct `ChallengeBoardReadModel`
- mark Deferred MCP as `implementation landed`
- modify Candidate A, Candidate B, or Candidate C production helpers

Boundary confirmation for this pre-approval guard:

- no MCP production wiring
- no task execution or handler routing changes
- no dispatcher loop changes
- no `CTFState` ownership split
- no `CTFVerifier` proof behavior changes
- no ToolExecutor changes
- no WorkerPool/CrewOrchestrator changes
- no composition root changes
- no proof authority behavior changes

#### Deferred MCP readback formatting fixture baseline

Status: representative fixture added before any MCP readback implementation.

`tests/unit/mcp/test_mcp_ingress_mode_contract.py` now includes
`test_mcp_blackboard_readback_formatting_matches_candidate_a_projection` as a
representative MCP readback text fixture. It locks the current
`_append_blackboard_snapshot_lines` output for Candidate A-style blackboard
projection data, including facts, pending verification readback, active
decision fields, recommended action fallback, action results, and surface
summaries.

This fixture is not an MCP production wiring change. It exists so a future MCP
readback switch can prove old/new output equivalence against the same public
line ordering and text before any MCP implementation change is approved.

Boundary confirmation for this baseline:

- no MCP production wiring
- no task execution or handler routing changes
- no dispatcher loop changes
- no `CTFState` ownership split
- no `CTFVerifier` proof behavior changes
- no ToolExecutor changes
- no WorkerPool/CrewOrchestrator changes
- no proof authority behavior changes

#### Deferred MCP empty/malformed readback fixture baseline

Status: degraded-input fixture added before any MCP readback implementation.

`tests/unit/mcp/test_mcp_ingress_mode_contract.py` now includes
`test_mcp_blackboard_readback_empty_and_malformed_inputs_are_quiet`. It locks
the current `_append_blackboard_snapshot_lines` behavior for empty, missing, or malformed blackboard snapshot inputs:
the helper emits no readback lines instead of synthesizing facts, actions, proof
state, or fallback text.

This fixture is not an MCP production wiring change. It exists so a future MCP
readback switch can prove old/new output equivalence for degraded inputs before
any MCP implementation change is approved.

Boundary confirmation for this baseline:

- no MCP production wiring
- no task execution or handler routing changes
- no dispatcher loop changes
- no `CTFState` ownership split
- no `CTFVerifier` proof behavior changes
- no ToolExecutor changes
- no WorkerPool/CrewOrchestrator changes
- no proof authority behavior changes

#### Deferred MCP implementation readiness checklist

Status: blocked on Web projection equivalence and explicit MCP approval, not approved for implementation.

Deferred MCP readback remains downstream of the approved Web read-model
projection path. It may proceed only after Web read-model projection equivalence
is proven and explicit MCP production wiring approval is granted.

Current pre-switch baselines recorded:

- Deferred MCP readback approval plan
- Deferred MCP source guard baseline
- Deferred MCP pre-approval production wiring guard:
  `test_deferred_mcp_pre_approval_guard_blocks_neutral_projection_wiring`
- Deferred MCP readback formatting fixture baseline
- Deferred MCP empty/malformed readback fixture baseline

Readiness scope for the future implementation slice:

- target only `flaghunter/mcp/server/mcp_tools.py::_append_blackboard_snapshot_lines`
- use `tests/unit/mcp/test_mcp_ingress_mode_contract.py` as the focused MCP
  readback fixture home
- must consume the same approved read-model projection
- must not become an independent projection shape
- preserve readback line text, ordering, and omission behavior
- no task execution or handler routing changes
- no proof writes and no proof authority decisions

Required fixture evidence:

- old/new output equivalence for representative MCP readback text
- old/new output equivalence for empty, missing, or malformed blackboard
  snapshot inputs
- preserved ordering for facts, hypotheses, pending verification items, candidates, action results, and attack surfaces
- no synthesized facts, actions, proof state, or fallback text for degraded
  inputs

Implementation gate:

- after Web read-model projection equivalence is proven
- explicit MCP production wiring approval is still required before editing the
  MCP readback helper
- one Deferred MCP implementation commit only
- rollback point: revert the single Deferred MCP implementation commit
- no schema migration, dispatcher loop change, ToolExecutor change,
  WorkerPool/CrewOrchestrator change, composition-root change, or proof
  authority behavior change in that commit

Required verification for the future Deferred MCP implementation slice:

```powershell
.\.venv\Scripts\python.exe -m pytest tests/unit/mcp/test_mcp_ingress_mode_contract.py tests/unit/test_clean_architecture_migration_playbook.py -q
.\.venv\Scripts\python.exe -m pytest tests/unit/test_import_layers.py tests/unit/agents/test_p1_source_guards.py tests/unit/test_ports_contracts.py tests/unit/test_domain_challenge_contracts.py -q
git diff --check
```

Explicit non-goals for the requested Deferred MCP implementation slice:

- no MCP production wiring without explicit approval
- no task execution or handler routing changes
- no dispatcher loop changes
- no `CTFState` ownership split
- no `CTFVerifier` proof behavior changes
- no ToolExecutor changes
- no WorkerPool/CrewOrchestrator changes
- no composition root changes
- no concrete adapter implementation
- no proof authority behavior changes
- no P5 implementation

#### First read-path switch sequence gate

Status: sequence guard recorded, no implementation approved by this section.

Candidate A is the only eligible first production read-path switch. The
Candidate A approval request must be accepted before implementation, and its
old/new output equivalence must land before any downstream Web or MCP readback
switch starts.

Required implementation order:

1. Candidate A: `flaghunter/interface/blackboard_lite.py`
2. Candidate B: `flaghunter/interface/web_trace_timeline.py`
3. Candidate C serialize-task family:
   `flaghunter/interface/web_serialize_task.py`
4. Candidate C control-decision family:
   `flaghunter/interface/web_control_decision.py`
5. Deferred MCP readback:
   `flaghunter/mcp/server/mcp_tools.py`

Sequence constraints:

- Candidate B may not be implemented before Candidate A lands
- Candidate C may not be implemented before Candidate A lands
- Deferred MCP may not be implemented before Web projection equivalence lands
- one production call-site family per commit
- no bundled Web and MCP implementation commits
- no parallel projection shapes
- rollback point: revert the single implementation commit for the affected read path

Explicit non-goals for this sequence gate:

- no dispatcher loop changes
- no `CTFState` ownership split
- no `CTFVerifier` proof behavior changes
- no ToolExecutor changes
- no WorkerPool/CrewOrchestrator changes
- no composition root changes
- no proof authority behavior changes
- no P5 implementation

#### Read-path switch acceptance matrix

Status: acceptance matrix recorded, no implementation approved by this section.

| Candidate | Status | Target path | Unblock condition |
|-----------|--------|-------------|-------------------|
| Candidate A | approval requested, not approved | `blackboard_lite.py` | explicit Candidate A approval |
| Candidate B | ready for approval review, not approved | `web_trace_timeline.py` | Candidate A equivalence lands |
| Candidate C | blocked on Candidate A approval, not approved | `web_serialize_task.py and web_control_decision.py` | Candidate A equivalence lands |
| Deferred MCP | blocked on Web projection equivalence and explicit MCP approval, not approved | `mcp_tools.py` | Web projection equivalence lands plus explicit MCP approval |

Required evidence before any row can move to implementation:

- old/new output equivalence
- source guard remains green
- focused regression remains green
- git diff --check remains green
- rollback point is the single implementation commit for that row

Forbidden scope for every row:

- dispatcher loop
- CTFState ownership
- CTFVerifier proof behavior
- ToolExecutor
- WorkerPool/CrewOrchestrator
- composition root
- proof authority behavior
- P5

#### Read-path source guard ledger

Status: source guard ownership recorded, no implementation approved by this
section.

| Candidate | Guard test | Guarded helper |
|-----------|------------|----------------|
| Candidate A | `tests/unit/interface/test_blackboard_lite.py` | `flaghunter/interface/blackboard_lite.py::build_task_blackboard_snapshot` |
| Candidate B | `tests/unit/web_console/test_trace_timeline_read_model_switch.py` | `flaghunter/interface/web_trace_timeline.py::_build_control_observation_timeline_events` |
| Candidate C | `tests/unit/interface/test_web_server.py` | `flaghunter/interface/web_serialize_task.py::_serialize_task` and `flaghunter/interface/web_control_decision.py::_task_blackboard_snapshot_for_decision` |
| Deferred MCP | `tests/unit/mcp/test_mcp_ingress_mode_contract.py` | `flaghunter/mcp/server/mcp_tools.py::_append_blackboard_snapshot_lines` |

Each guard must keep proving:

- no execution/runtime imports
- no side-effect sinks
- no proof upgrade surfaces
- no production wiring

#### Read-path approval state transitions

Status: transition rules recorded, no implementation approved by this section.

Allowed states for read-path candidates:

- not approved
- ready for approval review
- approval requested
- approved for implementation
- implementation landed
- blocked

Allowed transitions:

- not approved -> approval requested
- ready for approval review -> approval requested
- approval requested -> approved for implementation
- approved for implementation -> implementation landed
- blocked -> approval requested

Forbidden transitions:

- not approved -> implementation landed
- approval requested -> implementation landed
- blocked -> implementation landed
- ready for approval review -> implementation landed

Rules:

- moving into `approved for implementation` requires explicit human approval
- moving into `implementation landed` requires the single implementation commit
  for that candidate or call-site family
- old/new output equivalence must be recorded before implementation lands
- source guard remains green before and after the implementation commit

#### Read-path approval drift guard

Status: approval drift guard recorded, no implementation approved by this
section.

Current approval facts must not drift silently:

- Candidate A: approval requested, not approved
- Candidate B: ready for approval review, not approved
- Candidate C: blocked on Candidate A approval, not approved
- Deferred MCP: blocked on Web projection equivalence and explicit MCP approval, not approved

Any future approval status change must update all of these in the same
governance commit before implementation starts:

- the acceptance matrix row
- the approval state transition section
- the relevant implementation readiness checklist
- the verification evidence for that candidate

A status change alone is not implementation approval.

No candidate may be marked `implementation landed` without a commit SHA, the
focused regression result, the architecture/source-guard result, and the
post-push branch status.

#### Candidate A pre-approval production switch guard

Status: source guard added before Candidate A implementation approval.

`tests/unit/interface/test_blackboard_lite.py` now guards
`flaghunter/interface/blackboard_lite.py::build_task_blackboard_snapshot`
against importing or calling the neutral application board projection builder
while Candidate A remains approval requested, not approved.

Current approval fact:

- Candidate A: approval requested, not approved

This guard must remain active until explicit Candidate A implementation
approval lands. Updating the guard is allowed only in the same implementation
commit that proves old/new output equivalence for the first read-path switch.

Forbidden before approval:

- import `flaghunter.application.challenge.board_read_model_service`
- call `build_task_board_projection`
- construct `BuildChallengeBoardReadModel`
- mark Candidate A as `implementation landed`
- modify MCP readback, task serialization, or control-decision merge helpers

Boundary confirmation for this pre-approval guard:

- no production path switch
- no dispatcher loop changes
- no `CTFState` ownership split
- no `CTFVerifier` proof behavior changes
- no ToolExecutor changes
- no WorkerPool/CrewOrchestrator changes
- no MCP production wiring
- no proof authority behavior changes

#### Candidate B pre-approval production switch guard

Status: source guard added before Candidate B implementation approval.

`tests/unit/web_console/test_trace_timeline_read_model_switch.py` now guards
`flaghunter/interface/web_trace_timeline.py::_build_control_observation_timeline_events`
against importing or calling neutral challenge board/read-model projection
helpers while Candidate B remains ready for approval review, not approved.

Current approval fact:

- Candidate B: ready for approval review, not approved

This guard must remain active until Candidate A equivalence lands and Candidate
B implementation approval is explicitly granted. Updating the guard is allowed
only in the same Candidate B implementation commit that proves old/new output
equivalence for the trace timeline read path.

Forbidden before approval:

- import `flaghunter.application.challenge`
- import `flaghunter.domain.challenge.contracts`
- call `build_task_board_projection`
- construct `BuildChallengeBoardReadModel`
- construct `ChallengeBoardReadModel`
- mark Candidate B as `implementation landed`
- modify Candidate A, Candidate C, or Deferred MCP production helpers

Boundary confirmation for this pre-approval guard:

- no production path switch
- no dispatcher loop changes
- no `CTFState` ownership split
- no `CTFVerifier` proof behavior changes
- no ToolExecutor changes
- no WorkerPool/CrewOrchestrator changes
- no MCP production wiring
- no proof authority behavior changes

#### Candidate C pre-approval production switch guard

Status: source guard added before Candidate C implementation approval.

`tests/unit/interface/test_web_server.py` now guards
`flaghunter/interface/web_serialize_task.py::_serialize_task` and
`flaghunter/interface/web_control_decision.py::_task_blackboard_snapshot_for_decision`
against importing or calling neutral challenge board/read-model projection
helpers while Candidate C remains blocked on Candidate A approval, not approved.

Current approval fact:

- Candidate C: blocked on Candidate A approval, not approved

This guard must remain active until Candidate A equivalence lands and Candidate
C implementation approval is explicitly granted. Updating the guard is allowed
only in the same Candidate C implementation commit for the affected call-site
family that proves old/new output equivalence.

Forbidden before approval:

- import `flaghunter.application.challenge`
- import `flaghunter.domain.challenge.contracts`
- call `build_task_board_projection`
- construct `BuildChallengeBoardReadModel`
- construct `ChallengeBoardReadModel`
- mark Candidate C as `implementation landed`
- modify Candidate A, Candidate B, or Deferred MCP production helpers

Boundary confirmation for this pre-approval guard:

- no production path switch
- no dispatcher loop changes
- no `CTFState` ownership split
- no `CTFVerifier` proof behavior changes
- no ToolExecutor changes
- no WorkerPool/CrewOrchestrator changes
- no MCP production wiring
- no proof authority behavior changes

#### Candidate C serialize-task projection fixture baseline

Status: serialize-task fixture added before any Candidate C implementation.

`tests/unit/interface/test_web_server.py` now includes
`test_candidate_c_serialize_task_fixture_preserves_snapshot_and_summaries_before_switch`
as a representative fixture for
`flaghunter/interface/web_serialize_task.py::_serialize_task`.

The fixture locks the current task-detail serialization behavior that a future
Candidate C serialize-task switch must prove equivalent:

- preserve the existing `blackboardSnapshot` field in the returned task payload
- compute `nextActionExplanation` from the current control decision
- compute `activeDecisionSummary` from the merged read-side view
- preserve task capability flags for a running task
- do not write proof, infer proof authority decisions, or switch read paths

This fixture is not a production implementation approval. Candidate C remains
blocked on Candidate A approval, not approved.

Boundary confirmation for this fixture baseline:

- no production path switch
- no dispatcher loop changes
- no `CTFState` ownership split
- no `CTFVerifier` proof behavior changes
- no ToolExecutor changes
- no WorkerPool/CrewOrchestrator changes
- no MCP production wiring
- no proof authority behavior changes

#### Candidate C control-decision snapshot merge fixture baseline

Status: control-decision snapshot merge fixture added before any Candidate C
implementation.

`tests/unit/interface/test_web_server.py` now includes
`test_candidate_c_control_decision_snapshot_merge_fixture_before_switch` as a
representative fixture for
`flaghunter/interface/web_control_decision.py::_task_blackboard_snapshot_for_decision`.

The fixture locks the current control-decision snapshot merge behavior that a
future Candidate C control-decision switch must prove equivalent:

- rebuilt snapshot facts and active decision fields remain the primary source
- existing task `blackboardSnapshot` fills empty list sections such as pending
  verification items and action results
- explicit snapshot input fills still-empty list sections such as hypotheses
- existing and explicit active-decision fields only fill missing keys
- recommended-action fields merge without overriding existing selected action
- do not write proof, infer proof authority decisions, or switch read paths

This fixture is not a production implementation approval. Candidate C remains
blocked on Candidate A approval, not approved.

Boundary confirmation for this fixture baseline:

- no production path switch
- no dispatcher loop changes
- no `CTFState` ownership split
- no `CTFVerifier` proof behavior changes
- no ToolExecutor changes
- no WorkerPool/CrewOrchestrator changes
- no MCP production wiring
- no proof authority behavior changes

First read-path switch approval plan must include:

- file list
- risk
- rollback point
- representative fixture proving old/new output equivalence
- exact focused and architecture regression commands
- no proof writes
- no dispatcher loop changes
- no tool executor changes
- no crew runtime changes
- MCP production wiring remains out of scope unless explicitly approved
