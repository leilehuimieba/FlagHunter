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
- `SubmitTaskIngress`

The completed skeletons do not connect production call sites and do not change
the dispatcher loop, `CTFState`, `CTFVerifier`, `ToolExecutor`, crew runtime,
MCP production wiring, or composition root behavior.

### Phase 4 verification baseline

Focused Phase 4 regression should include:

```powershell
.\.venv\Scripts\python.exe -m pytest tests/unit/test_import_layers.py tests/unit/agents/test_p1_source_guards.py tests/unit/agents/test_p1_claim_invariants.py tests/unit/tools/test_finish_control_receipt.py tests/unit/agents/test_p2_audit_export.py tests/unit/agents/test_p2_evidence_snapshot.py tests/unit/agents/test_p2_ledger_event_readback.py tests/unit/agents/test_p4_task_dag_plan_schema.py tests/unit/agents/test_p4_task_dag_ready_selector.py tests/unit/agents/test_p4_task_dag_replay_audit_bundle.py tests/unit/test_ports_contracts.py tests/unit/test_domain_challenge_contracts.py tests/unit/agents/test_phase2b_compatibility_shims.py tests/unit/test_adapter_boundary_skeleton.py tests/unit/test_tool_runner_adapter.py tests/unit/test_runtime_action_adapter.py tests/unit/test_read_model_store_adapter.py tests/unit/test_state_store_adapter.py tests/unit/test_audit_store_adapter.py tests/unit/test_artifact_store_adapter.py tests/unit/test_checkpoint_store_adapter.py tests/unit/test_claim_store_adapter.py tests/unit/test_verifier_adapter.py tests/unit/test_proof_authority_adapter.py tests/unit/test_crew_bridge_adapter.py tests/unit/test_task_dag_runner_adapter.py tests/unit/test_task_ingress_adapter.py tests/unit/test_application_challenge_snapshot_service.py tests/unit/test_application_task_receipt_service.py tests/unit/test_application_evidence_snapshot_service.py tests/unit/test_application_claim_review_service.py tests/unit/test_application_tool_receipt_service.py tests/unit/test_application_worker_task_service.py tests/unit/test_application_task_ingress_service.py tests/unit/test_application_board_read_model_service.py -q
```

### Legacy read-model shim proof action coverage guard

Status: explicit proof action coverage guard added for Phase 2B compatibility
shims.

`tests/unit/agents/test_phase2b_compatibility_shims.py` now requires legacy
read-model shim proof guards to explicitly cover proof authority write, upgrade,
and accepted-proof sink names:

- `append_proof_record`
- `append_verification_record`
- `confirm_claim`
- `level="verified"`
- `level='verified'`
- `upgrade_claim_to_verified`
- `verification_decision`
- `verified_flags`

This guard keeps legacy read-model compatibility shims as re-export-only
compatibility surfaces. Shims may preserve old import paths for neutral domain
contracts, but they must not reintroduce proof authority actions, accepted-proof
writes, claim confirmation, or proof upgrade decisions.

Boundary confirmation for this guard:

- no production behavior changes
- no concrete adapter construction
- no composition root changes
- no MCP production wiring
- no dispatcher loop changes
- no runtime construction
- no ToolExecutor changes
- no proof authority behavior changes

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

### Domain contract production wiring source guard

Status: production wiring source guard added for inner domain contracts.

`tests/unit/test_domain_challenge_contracts.py` now guards
`flaghunter/domain/challenge/contracts` against production assembly surfaces.
Domain contracts must remain pure schema/read-model contracts and may not
reference these production wiring names:

- `FlagHunterAgent`
- `AgentSession`
- `MCPRouter`
- `MCPServer`
- `CompositionRoot`
- `create_agent`
- `run_task_async`

This guard keeps domain contracts from becoming an accidental composition root,
MCP task runner, or agent/session factory while clean architecture wiring
remains explicitly out of scope.

Boundary confirmation for this guard:

- no concrete adapter construction
- no composition root changes
- no MCP production wiring
- no dispatcher loop changes
- no runtime construction
- no ToolExecutor changes
- no proof authority behavior changes

### Domain contract outer-layer import coverage guard

Status: outer-layer import coverage guard added for inner domain contracts.

`tests/unit/test_domain_challenge_contracts.py` now requires the domain
contract import guard to cover every outer FlagHunter layer:

- `flaghunter.adapters`
- `flaghunter.agents`
- `flaghunter.application`
- `flaghunter.config`
- `flaghunter.cpa_modules`
- `flaghunter.interface`
- `flaghunter.knowledge`
- `flaghunter.llm`
- `flaghunter.mcp`
- `flaghunter.playbooks`
- `flaghunter.ports`
- `flaghunter.runtime`
- `flaghunter.session`
- `flaghunter.tools`
- `flaghunter.workspaces`

This guard keeps `flaghunter/domain/challenge/contracts` as the innermost
schema/read-model layer and prevents future contract slices from reaching
outward into adapters, application services, production configuration,
legacy feature modules, playbooks, model/runtime code, presentation, MCP,
tools, sessions, or workspace helpers.

Boundary confirmation for this guard:

- no production behavior changes
- no concrete adapter construction
- no composition root changes
- no MCP production wiring
- no dispatcher loop changes
- no runtime construction
- no ToolExecutor changes
- no proof authority behavior changes

### Domain contract side-effect sink coverage guard

Status: explicit side-effect sink coverage guard added for inner domain
contracts.

`tests/unit/test_domain_challenge_contracts.py` now requires the domain
contract source guard to explicitly cover common filesystem, process, network,
socket, browser/runtime, and tool-execution sinks:

- `open(`
- `Path.open`
- `Path.read_text`
- `Path.write_text`
- `Path.read_bytes`
- `Path.write_bytes`
- `subprocess.run`
- `subprocess.Popen`
- `subprocess.call`
- `asyncio.create_subprocess_exec`
- `asyncio.create_subprocess_shell`
- `requests.get`
- `requests.post`
- `requests.request`
- `httpx.get`
- `httpx.post`
- `httpx.request`
- `socket.socket`

This guard keeps domain contracts as pure schema/read-model code and prevents
future contract slices from becoming accidental filesystem readers/writers,
process launchers, network clients, socket users, browser/runtime surfaces, or
tool executors.

Boundary confirmation for this guard:

- no production behavior changes
- no concrete adapter construction
- no composition root changes
- no MCP production wiring
- no dispatcher loop changes
- no runtime construction
- no ToolExecutor changes
- no proof authority behavior changes

### Domain contract proof action coverage guard

Status: explicit proof action coverage guard added for inner domain contracts.

`tests/unit/test_domain_challenge_contracts.py` now requires the domain contract
proof guard to explicitly cover proof authority write, upgrade, and accepted
proof sink names:

- `append_proof_record`
- `append_verification_record`
- `confirm_claim`
- `level="verified"`
- `level='verified'`
- `upgrade_claim_to_verified`
- `verification_decision`
- `verified_flags`

This guard keeps `flaghunter/domain/challenge/contracts` as pure
schema/read-model contracts. Domain contracts may describe proof records as
data, but they must not become proof authorities, accepted-proof writers, claim
confirmers, or proof upgrade decision makers.

Boundary confirmation for this guard:

- no production behavior changes
- no concrete adapter construction
- no composition root changes
- no MCP production wiring
- no dispatcher loop changes
- no runtime construction
- no ToolExecutor changes
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

### Ports production wiring source guard

Status: production wiring source guard added for protocol-only ports.

`tests/unit/test_ports_contracts.py` now guards the ports package against
production assembly surfaces. Ports must remain protocol-only boundary contracts
and may not reference these production wiring names:

- `FlagHunterAgent`
- `AgentSession`
- `MCPRouter`
- `MCPServer`
- `CompositionRoot`
- `create_agent`
- `run_task_async`

This guard keeps `flaghunter/ports` from becoming an accidental composition
root, MCP task runner, or agent/session factory while concrete production
wiring remains explicitly out of scope.

Boundary confirmation for this guard:

- no concrete adapter construction
- no composition root changes
- no MCP production wiring
- no dispatcher loop changes
- no runtime construction
- no ToolExecutor changes
- no proof authority behavior changes

### Ports outer-layer import coverage guard

Status: outer-layer import coverage guard added for protocol-only ports.

`tests/unit/test_ports_contracts.py` now requires the ports import guard to
cover every outer FlagHunter layer while ports remain protocol-only contracts:

- `flaghunter.adapters`
- `flaghunter.agents`
- `flaghunter.application`
- `flaghunter.config`
- `flaghunter.cpa_modules`
- `flaghunter.interface`
- `flaghunter.knowledge`
- `flaghunter.llm`
- `flaghunter.mcp`
- `flaghunter.playbooks`
- `flaghunter.runtime`
- `flaghunter.session`
- `flaghunter.tools`
- `flaghunter.workspaces`

This guard keeps `flaghunter/ports` from reaching outward into adapters,
application services, production configuration, legacy feature modules,
playbooks, model/runtime code, presentation, MCP, tools, sessions, or workspace
helpers before explicit production-wiring approval.

Boundary confirmation for this guard:

- no production behavior changes
- no concrete adapter construction
- no composition root changes
- no MCP production wiring
- no dispatcher loop changes
- no runtime construction
- no ToolExecutor changes
- no proof authority behavior changes

### Ports action sink coverage guard

Status: explicit action sink coverage guard added for protocol-only ports.

`tests/unit/test_ports_contracts.py` now requires the ports action guard to
explicitly cover common filesystem, process, network, and socket sinks:

- `open(`
- `Path.open`
- `Path.read_text`
- `Path.write_text`
- `Path.read_bytes`
- `Path.write_bytes`
- `subprocess.run`
- `subprocess.Popen`
- `subprocess.call`
- `asyncio.create_subprocess_exec`
- `asyncio.create_subprocess_shell`
- `requests.get`
- `requests.post`
- `requests.request`
- `httpx.get`
- `httpx.post`
- `httpx.request`
- `socket.socket`

This guard keeps ports as protocol-only contracts and prevents future port
slices from becoming accidental filesystem readers/writers, process launchers,
network clients, socket users, runtime surfaces, or tool executors.

Boundary confirmation for this guard:

- no production behavior changes
- no concrete adapter construction
- no composition root changes
- no MCP production wiring
- no dispatcher loop changes
- no runtime construction
- no ToolExecutor changes
- no proof authority behavior changes

### Ports proof action coverage guard

Status: explicit proof action coverage guard added for protocol-only ports.

`tests/unit/test_ports_contracts.py` now requires the ports proof guard to
explicitly cover proof authority write, upgrade, accepted-proof, and legacy
accepted-proof call names:

- `add_flag`
- `append_proof_record`
- `append_verification_record`
- `build_verification_decision_event`
- `confirm_claim`
- `create_claim`
- `upgrade_claim_to_verified`
- `verification_decision`

This guard keeps ports as Protocol-only contracts. Ports may declare neutral
method shapes such as `append_proof_record` and `confirm_claim`, but ports must
not call proof authority implementations, write accepted proof, create claims,
or emit proof upgrade decisions.

Boundary confirmation for this guard:

- no production behavior changes
- no concrete adapter construction
- no composition root changes
- no MCP production wiring
- no dispatcher loop changes
- no runtime construction
- no ToolExecutor changes
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

#### Application service side-effect sink coverage guard

Status: explicit side-effect sink coverage guard recorded for neutral
application services.

`tests/unit/test_application_service_source_guards.py` now requires the
application service source guard to explicitly cover common filesystem,
process, network, and socket sinks:

- `open`
- `Path.open`
- `Path.read_text`
- `Path.write_text`
- `Path.read_bytes`
- `Path.write_bytes`
- `subprocess.run`
- `subprocess.Popen`
- `subprocess.call`
- `asyncio.create_subprocess_exec`
- `asyncio.create_subprocess_shell`
- `requests.get`
- `requests.post`
- `requests.request`
- `httpx.get`
- `httpx.post`
- `httpx.request`
- `socket.socket`

This guard keeps application services as pure use-case orchestration over
neutral contracts and ports, and prevents future service slices from becoming
filesystem readers/writers, process launchers, network clients, socket users,
runtime surfaces, or tool executors.

Boundary confirmation for this guard:

- no production behavior changes
- no concrete adapter construction
- no composition root changes
- no MCP production wiring
- no dispatcher loop changes
- no runtime construction
- no ToolExecutor changes
- no proof authority behavior changes

#### Application service proof action coverage guard

Status: explicit proof action coverage guard recorded for neutral application
services.

`tests/unit/test_application_service_source_guards.py` now requires the
application service proof guard to explicitly cover proof authority write,
upgrade, accepted-proof, and legacy accepted-proof sink names:

- `append_proof_record`
- `append_verification_record`
- `confirm_claim`
- `level="verified"`
- `level='verified'`
- `upgrade_claim_to_verified`
- `verification_decision`
- `verifiedFlags`
- `verified_flags`

This guard keeps application services as use-case orchestration over neutral
contracts and ports. Application services may review or project claims through
ports, but they must not become proof authorities, accepted-proof writers,
claim confirmers, or proof upgrade decision makers before an approved
proof-authority wiring slice.

Boundary confirmation for this guard:

- no production behavior changes
- no concrete adapter construction
- no composition root changes
- no MCP production wiring
- no dispatcher loop changes
- no runtime construction
- no ToolExecutor changes
- no proof authority behavior changes

#### Application service production wiring source guard

Status: production wiring source guard added before composition-root approval.

`tests/unit/test_application_service_source_guards.py` now also guards
application services against production assembly surfaces. Application services
must stay use-case level and may not construct or reference these production
wiring names before composition-root approval:

- `FlagHunterAgent`
- `AgentSession`
- `MCPRouter`
- `MCPServer`
- `CompositionRoot`
- `create_agent`
- `run_task_async`

This guard keeps application services from becoming an accidental composition
root, MCP server task runner, or agent/session factory while production wiring
remains explicitly out of scope.

Boundary confirmation for this guard:

- no composition root changes
- no MCP production wiring
- no dispatcher loop changes
- no runtime construction
- no ToolExecutor changes
- no proof authority behavior changes

#### Application service outer-layer import coverage guard

Status: outer-layer import coverage guard added for neutral application services.

`tests/unit/test_application_service_source_guards.py` now requires the
application-service import guard to cover every outer FlagHunter layer while
still allowing only `flaghunter.domain` and `flaghunter.ports` imports:

- `flaghunter.adapters`
- `flaghunter.agents`
- `flaghunter.config`
- `flaghunter.cpa_modules`
- `flaghunter.interface`
- `flaghunter.knowledge`
- `flaghunter.llm`
- `flaghunter.mcp`
- `flaghunter.playbooks`
- `flaghunter.runtime`
- `flaghunter.session`
- `flaghunter.tools`
- `flaghunter.workspaces`

This guard keeps `flaghunter/application/challenge` as a use-case layer that
depends only on neutral contracts and ports, and prevents future service slices
from reaching outward into adapters, legacy feature modules, playbooks,
production configuration, model/runtime code, presentation, MCP, tools,
sessions, or workspace helpers before explicit production-wiring approval.

Boundary confirmation for this guard:

- no production behavior changes
- no concrete adapter construction
- no composition root changes
- no MCP production wiring
- no dispatcher loop changes
- no runtime construction
- no ToolExecutor changes
- no proof authority behavior changes

### Core import-linter outer-layer coverage guard

Status: import-linter outer-layer coverage guard added for neutral core layers.

`tests/unit/test_import_layers.py` now requires `.importlinter` to keep these
core clean-architecture contracts in sync with the source guards:

- `domain-contract-independence`
- `ports-contract-boundary`
- `application-service-boundary`

The domain contract forbids these outer layers:

- `flaghunter.adapters`
- `flaghunter.application`
- `flaghunter.config`
- `flaghunter.cpa_modules`
- `flaghunter.interface`
- `flaghunter.knowledge`
- `flaghunter.llm`
- `flaghunter.mcp.server`
- `flaghunter.playbooks`
- `flaghunter.ports`
- `flaghunter.runtime`
- `flaghunter.session`
- `flaghunter.tools`
- `flaghunter.workspaces`

The ports contract forbids these outer layers:

- `flaghunter.adapters`
- `flaghunter.agents`
- `flaghunter.application`
- `flaghunter.config`
- `flaghunter.cpa_modules`
- `flaghunter.interface`
- `flaghunter.knowledge`
- `flaghunter.llm`
- `flaghunter.mcp.server`
- `flaghunter.playbooks`
- `flaghunter.runtime`
- `flaghunter.session`
- `flaghunter.tools`
- `flaghunter.workspaces`

The application-service contract forbids these outer layers:

- `flaghunter.adapters`
- `flaghunter.agents`
- `flaghunter.config`
- `flaghunter.cpa_modules`
- `flaghunter.interface`
- `flaghunter.knowledge`
- `flaghunter.llm`
- `flaghunter.mcp.server`
- `flaghunter.playbooks`
- `flaghunter.runtime`
- `flaghunter.session`
- `flaghunter.tools`
- `flaghunter.workspaces`

This guard adds no production wiring. It only makes import-linter enforce the
same neutral domain/ports/application dependency boundaries that the source
guards already check.

Boundary confirmation for this guard:

- no production behavior changes
- no concrete adapter construction
- no composition root changes
- no MCP production wiring
- no dispatcher loop changes
- no runtime construction
- no ToolExecutor changes
- no proof authority behavior changes

### Public surface domain-neutral naming coverage guard

Status: public naming coverage guard added for neutral ports and application
services.

`tests/unit/test_ports_contracts.py` and
`tests/unit/test_application_service_source_guards.py` now require new public
ports and application service surfaces to keep the full domain-neutral naming
policy forbidden-term set:

- `ctf`
- `pentest`
- `exploit`
- `vulnerability`
- `hacking`
- `attack`
- `redteam`

The guard checks public module paths, module docstrings, class names, function
names, and class/function docstrings for the neutral architecture layers. It
does not scan legacy payload compatibility keys or historical documentation,
because those remain compatibility details until an approved migration slice
changes them.

Boundary confirmation for this guard:

- no production behavior changes
- no concrete adapter construction
- no composition root changes
- no MCP production wiring
- no dispatcher loop changes
- no runtime construction
- no ToolExecutor changes
- no proof authority behavior changes

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

### Task ingress adapter skeleton baseline

Status: task ingress adapter skeleton added before MCP production wiring.

`TaskIngressPort` now exists as a neutral protocol-only boundary under
`flaghunter/ports/`. `TaskIngressAdapter` now exists under
`flaghunter/adapters/mcp/` and delegates to injected task ingress ports without
constructing or importing the production MCP server.

`tests/unit/test_task_ingress_adapter.py` verifies the adapter delegates to an
injected task ingress port, exports through `flaghunter.adapters.mcp`, and has
no concrete/action/proof imports. `tests/unit/test_adapter_port_substitution.py`
also covers substitutable injected task ingress ports.

Boundary confirmation for this baseline:

- no MCP production wiring
- no `flaghunter/mcp/server` imports
- no dispatcher loop changes
- no `CTFState` ownership split
- no `CTFVerifier` proof behavior changes
- no ToolExecutor changes
- no WorkerPool/CrewOrchestrator changes
- no composition root changes
- no proof authority behavior changes
- no P5 implementation

### Task ingress domain contract skeleton baseline

Status: task ingress domain contract skeleton added before service migration or
production wiring.

`TaskIngressRequest` and `TaskIngressReceipt` now exist under
`flaghunter/domain/challenge/contracts/task_ingress.py` as schema-versioned and
JSON-friendly neutral contracts. The contracts serialize only sanitized
instructions and receipt summaries, artifact references, and metadata so raw
task text is not promoted into a public domain payload.

`tests/unit/test_domain_challenge_contracts.py` verifies import/re-export,
schema versions, round-trip serialization, sanitized instructions and receipt
summaries, empty-input behavior, domain-neutral names, and contract source
guards.

Verification focus: sanitized instructions and receipt summaries.

Boundary confirmation for this baseline:

- no service migration
- no MCP production wiring
- no concrete adapter construction
- no dispatcher loop changes
- no `CTFState` ownership split
- no `CTFVerifier` proof behavior changes
- no ToolExecutor changes
- no WorkerPool/CrewOrchestrator changes
- no composition root changes
- no proof authority behavior changes
- no P5 implementation

### Task ingress readback contract skeleton baseline

Status: task ingress readback contract skeleton added before service migration
or production wiring.

`TaskIngressReadback` now exists under
`flaghunter/domain/challenge/contracts/task_ingress.py` as a schema-versioned
and JSON-friendly neutral read model. It aggregates already-neutral ingress
requests and receipts, emits request and receipt summary counts, and records
task type and status counts without reading runtime state or invoking
production ingress paths.

`tests/unit/test_domain_challenge_contracts.py` verifies import/re-export,
round-trip serialization, empty-input behavior, request and receipt summary
counts, task type and status counts, sanitization, domain-neutral names, and
contract source guards.

Boundary confirmation for this baseline:

- no service migration
- no MCP production wiring
- no concrete adapter construction
- no dispatcher loop changes
- no `CTFState` ownership split
- no `CTFVerifier` proof behavior changes
- no ToolExecutor changes
- no WorkerPool/CrewOrchestrator changes
- no composition root changes
- no proof authority behavior changes
- no P5 implementation

### Task ingress MCP pre-wiring guard baseline

Status: MCP pre-wiring guard added before production wiring.

`tests/unit/mcp/test_mcp_ingress_mode_contract.py` now guards the production
MCP server package against importing or constructing `TaskIngressAdapter`,
`SubmitTaskIngress`, `TaskIngressPort`, task ingress adapters, task ingress
application services, or task ingress port modules before explicit production
wiring approval is recorded.

Required gate: explicit production wiring approval.

This guard keeps the task ingress adapter, port, application service, and
domain contracts available as clean architecture runway without silently
rewiring MCP task execution.

Boundary confirmation for this baseline:

- no MCP production wiring
- no concrete adapter construction
- no dispatcher loop changes
- no `CTFState` ownership split
- no `CTFVerifier` proof behavior changes
- no ToolExecutor changes
- no WorkerPool/CrewOrchestrator changes
- no composition root changes
- no proof authority behavior changes
- no P5 implementation

### Task ingress production entrypoint pre-wiring guard baseline

Status: production entrypoint pre-wiring guard added before production wiring.

`tests/unit/test_task_ingress_production_wiring_guards.py` now guards
interface, MCP, agents, tools, runtime, session, workspaces, and config
production entrypoint packages against importing or constructing
`TaskIngressAdapter`, `SubmitTaskIngress`, `TaskIngressPort`, task ingress
adapters, task ingress application services, or task ingress port modules
before explicit production wiring approval is recorded. The scan includes
`flaghunter/mcp/server` so MCP server entrypoints cannot silently adopt the
task ingress runway before approval.

Required gate: explicit production wiring approval.

This guard keeps task ingress skeleton work from becoming accidental production
entrypoint wiring through CLI, TUI, MCP server, dispatcher, tool executor,
runtime, session, workspace, or configuration paths.

Boundary confirmation for this baseline:

- no production entrypoint wiring
- no MCP production wiring
- no concrete adapter construction
- no dispatcher loop changes
- no `CTFState` ownership split
- no `CTFVerifier` proof behavior changes
- no ToolExecutor changes
- no WorkerPool/CrewOrchestrator changes
- no composition root changes
- no proof authority behavior changes
- no P5 implementation

#### Task ingress production entry root coverage guard

Status: explicit production entry root coverage guard added before task
ingress production wiring approval.

`tests/unit/test_task_ingress_production_wiring_guards.py` now requires the
production entrypoint pre-wiring guard to explicitly cover every production
entry root where task ingress wiring would be high-risk before approval:

- `flaghunter/agents`
- `flaghunter/config`
- `flaghunter/interface`
- `flaghunter/mcp`
- `flaghunter/runtime`
- `flaghunter/session`
- `flaghunter/tools`
- `flaghunter/workspaces`

This guard keeps future task ingress adapter/service/port wiring checks from
silently narrowing the scan away from presentation, MCP, agent, tool,
runtime, session, workspace, or configuration entrypoints.

Boundary confirmation for this guard:

- no production entrypoint wiring
- no MCP production wiring
- no concrete adapter construction
- no dispatcher loop changes
- no `CTFState` ownership split
- no `CTFVerifier` proof behavior changes
- no ToolExecutor changes
- no WorkerPool/CrewOrchestrator changes
- no composition root changes
- no proof authority behavior changes
- no P5 implementation

#### Task ingress production wiring token coverage guard

Status: explicit production wiring token coverage guard added before task
ingress production wiring approval.

`tests/unit/test_task_ingress_production_wiring_guards.py` now requires the
production entrypoint pre-wiring guard to explicitly cover every task ingress
adapter, service, port, and module import token that would indicate production
wiring:

- `TaskIngressAdapter`
- `TaskIngressPort`
- `SubmitTaskIngress`
- `flaghunter.adapters.mcp`
- `flaghunter.application.challenge.task_ingress_service`
- `flaghunter.ports.task_ingress`
- `task_ingress_adapter`
- `task_ingress_service`

This guard keeps task ingress adapter/service/port skeletons from being wired
into interface, MCP, agents, tools, runtime, session, workspace, or config
entrypoints before explicit production wiring approval.

Boundary confirmation for this guard:

- no production entrypoint wiring
- no MCP production wiring
- no concrete adapter construction
- no dispatcher loop changes
- no `CTFState` ownership split
- no `CTFVerifier` proof behavior changes
- no ToolExecutor changes
- no WorkerPool/CrewOrchestrator changes
- no composition root changes
- no proof authority behavior changes
- no P5 implementation

### Task ingress application service skeleton baseline

Status: task ingress application service skeleton added before production wiring.

`SubmitTaskIngress` now exists under `flaghunter/application/challenge/` as a
neutral application service. It builds schema-versioned task ingress requests
and delegates through an injected `TaskIngressPort` when one is provided. It
depends only on neutral contracts and ports.

`tests/unit/test_application_task_ingress_service.py` verifies import/re-export,
empty-input behavior, request serialization, injected-port delegation, public
method shape, domain-neutral names, and application-layer source guards.

Boundary confirmation for this baseline:

- no MCP production wiring
- no concrete adapter construction
- no dispatcher loop changes
- no `CTFState` ownership split
- no `CTFVerifier` proof behavior changes
- no ToolExecutor changes
- no WorkerPool/CrewOrchestrator changes
- no composition root changes
- no proof authority behavior changes
- no P5 implementation

### Task ingress service contract migration plan

Status: plan recorded, implementation not approved.

This plan covers a future focused migration that may let
`SubmitTaskIngress` use the neutral task ingress domain contracts internally
while preserving its current external behavior and injected port payload
compatibility.

File list for the future implementation slice:

- `flaghunter/application/challenge/task_ingress_service.py`
- `tests/unit/test_application_task_ingress_service.py`
- `tests/unit/test_application_service_source_guards.py`
- `tests/unit/test_task_ingress_adapter.py`
- `tests/unit/test_clean_architecture_migration_playbook.py`

risk: low-medium, because service output shape and ingress port payload compatibility could change if the service switches from the current raw mapping payload to neutral contract serialization without a compatibility check.

rollback point: revert the single service migration commit.

Required behavior for the future implementation slice:

- preserve current external response shape unless explicitly versioned
- preserve raw `instructions` in the port request if downstream compatibility still expects it
- optional neutral contract payloads may only be used internally or under a
  compatible additive key
- keep all serialized cross-module payloads schema-versioned and JSON-friendly

Non-goals:

- no production wiring
- no MCP server changes
- no dispatcher loop changes
- no `CTFState` ownership split
- no `CTFVerifier` proof behavior changes
- no ToolExecutor changes
- no WorkerPool/CrewOrchestrator changes
- no composition root changes
- no proof authority behavior changes
- no P5 implementation

Required verification for the future implementation slice:

```powershell
.\.venv\Scripts\python.exe -m pytest tests/unit/test_application_task_ingress_service.py -q
.\.venv\Scripts\python.exe -m pytest tests/unit/test_task_ingress_adapter.py -q
.\.venv\Scripts\python.exe -m pytest tests/unit/test_import_layers.py tests/unit/test_ports_contracts.py tests/unit/test_domain_challenge_contracts.py tests/unit/test_task_ingress_production_wiring_guards.py -q
git diff --check
```

### Task ingress service contract migration pre-approval guard

Status: pre-approval guard active, implementation not approved.

`tests/unit/test_application_task_ingress_service.py` now guards
`flaghunter/application/challenge/task_ingress_service.py` against importing or
constructing the neutral task ingress domain contract classes before the
service contract migration is approved and implemented in a focused service
migration commit.

Forbidden before approval:

- import `flaghunter.domain.challenge.contracts.task_ingress`
- construct or reference `TaskIngressRequest`
- construct or reference `TaskIngressReceipt`
- construct or reference `TaskIngressReadback`
- change the current injected port request payload shape
- remove raw `instructions` from the injected port request payload

Updating this guard is allowed only in the same service migration commit that
preserves current external response shape, preserves injected port compatibility
or explicitly versions the payload, and runs the verification commands recorded
in the service contract migration plan.

Boundary confirmation for this pre-approval guard:

- no service migration
- no production wiring
- no MCP server changes
- no dispatcher loop changes
- no `CTFState` ownership split
- no `CTFVerifier` proof behavior changes
- no ToolExecutor changes
- no WorkerPool/CrewOrchestrator changes
- no composition root changes
- no proof authority behavior changes
- no P5 implementation

### Task ingress service contract migration readiness checklist

Status: ready for approval review, not approved for implementation.

Readiness evidence already recorded:

- Task ingress application service skeleton baseline
- Task ingress domain contract skeleton baseline
- Task ingress readback contract skeleton baseline
- Task ingress service contract migration plan
- Task ingress service contract migration pre-approval guard

Representative behavior evidence to preserve in the future implementation:

- `test_submit_returns_pending_payload_without_ingress_port`
- `test_submit_delegates_to_task_ingress_port_only`
- `test_submit_accepts_minimal_empty_values`
- `test_task_ingress_service_contract_migration_pre_approval_guard`

Implementation approval constraints:

- approval is still required before editing `flaghunter/application/challenge/task_ingress_service.py`
- one service migration commit only
- update the pre-approval guard in the same implementation commit
- preserve current external response shape unless explicitly versioned
- preserve raw `instructions` in the injected port request payload
- old/new output equivalence must be proven in `tests/unit/test_application_task_ingress_service.py`
- rollback point: revert the single service migration commit

Non-goals:

- no production wiring
- no MCP server changes
- no dispatcher loop changes
- no `CTFState` ownership split
- no `CTFVerifier` proof behavior changes
- no ToolExecutor changes
- no WorkerPool/CrewOrchestrator changes
- no composition root changes
- no proof authority behavior changes
- no P5 implementation

Required verification for the future implementation commit:

```powershell
.\.venv\Scripts\python.exe -m pytest tests/unit/test_application_task_ingress_service.py -q
.\.venv\Scripts\python.exe -m pytest tests/unit/test_task_ingress_adapter.py -q
.\.venv\Scripts\python.exe -m pytest tests/unit/test_clean_architecture_migration_playbook.py tests/unit/test_import_layers.py tests/unit/agents/test_p1_source_guards.py tests/unit/test_ports_contracts.py tests/unit/test_domain_challenge_contracts.py tests/unit/test_application_service_source_guards.py tests/unit/test_task_ingress_production_wiring_guards.py -q
git diff --check
```

#### Task ingress service contract migration approval flag consistency guard

Status: approval consistency guard recorded, implementation not approved by this section.

The task ingress service migration has three governance surfaces that must stay
aligned before any implementation work starts:

- Task ingress service contract migration plan
- Task ingress service contract migration pre-approval guard
- Task ingress service contract migration readiness checklist

| Governance surface | Implementation approved | Service migration landed |
|--------------------|-------------------------|--------------------------|
| plan | false | false |
| pre-approval guard | false | false |
| readiness checklist | false | false |

Required consistency:

- the plan remains `implementation not approved`
- the pre-approval guard remains active
- the readiness checklist remains `not approved for implementation`
- no implementation approval by implication
- no service migration
- no production wiring
- no status-only approval without an explicit approval section and matching
  implementation commit

#### Task ingress service contract migration landing record template

Status: landing evidence template recorded, implementation not approved.

Any future approved task ingress service migration commit must add a completed
landing record before the service migration can be treated as landed.

Required landing record fields:

- Implementation commit SHA: `<sha>`
- Target: `flaghunter/application/challenge/task_ingress_service.py`
- Behavior equivalence evidence: old/new output equivalence test name and
  result
- Port payload compatibility evidence: proof that the injected port request
  still preserves raw `instructions` in the injected port request payload unless
  an explicitly versioned payload is approved
- Pre-approval guard update: guard test name and result from the same
  implementation commit
- Focused regression result: exact command and result
- Architecture/source-guard result: exact command and result
- git diff --check result: exact result
- Post-push branch status: exact `git status --short --branch`
- Rollback command: git revert <sha>
- Boundary confirmation: unchanged high-risk areas

Required boundary confirmation:

- no production wiring
- no MCP server changes
- no dispatcher loop changes
- no `CTFState` ownership split
- no `CTFVerifier` proof behavior changes
- no ToolExecutor changes
- no WorkerPool/CrewOrchestrator changes
- no composition root changes
- no proof authority behavior changes
- no P5 implementation

This is a template only. It records the required evidence shape for a future
approved implementation commit; no service migration is authorized by this template.

#### Task ingress service rollback placeholder consistency guard

Status: rollback placeholder guard recorded, implementation not approved.

This guard keeps the rollback command for the future task ingress service
migration as a placeholder only until the implementation commit lands. The
placeholder is not a currently executable rollback command and must not contain
a real commit SHA before the landing record is completed.

| Scope | Rollback command | Applies after | Current executable |
|-------|------------------|---------------|--------------------|
| task ingress service migration | `git revert <single task ingress service migration commit>` | service migration commit lands | false |

Required consistency:

- placeholder only
- not a currently executable rollback command
- no real commit SHA before the service migration landing record exists
- the landing record template remains the place that records `Rollback command:
  git revert <sha>`
- no service migration is authorized by this rollback guard

#### Task ingress service approval transition atomicity guard

Status: approval transition atomicity guard recorded, implementation not approved.

Any future transition from `not approved` to approved implementation for the
task ingress service migration must update every mirrored governance surface in
the same governance commit before implementation starts.

| Atomic update | Required section |
|---------------|------------------|
| plan approval status | `Task ingress service contract migration plan` |
| pre-approval guard status | `Task ingress service contract migration pre-approval guard` |
| readiness approval status | `Task ingress service contract migration readiness checklist` |
| approval flag table | `Task ingress service contract migration approval flag consistency guard` |
| landing evidence template | `Task ingress service contract migration landing record template` |
| rollback placeholder | `Task ingress service rollback placeholder consistency guard` |
| verification evidence | `Task ingress service contract migration readiness checklist` |

Rules:

- approval transition evidence must land before implementation
- partial approval updates must fail review
- the implementation commit must remain separate from the approval-transition
  governance commit
- no service migration is authorized by this atomicity guard

#### Task ingress service approval transition coverage guard

Status: approval transition coverage guard recorded, implementation not approved.

Every future task ingress service approval transition must keep the same
canonical governance surface set across approval transition tables before any
implementation commit starts.

| Governance surface | Required before approval transition | Current implementation approved |
|--------------------|-------------------------------------|---------------------------------|
| plan approval status | true | false |
| pre-approval guard status | true | false |
| readiness approval status | true | false |
| approval flag table | true | false |
| landing evidence template | true | false |
| rollback placeholder | true | false |
| verification evidence | true | false |

Rules:

- every approval transition table must keep the same canonical governance surface set
- missing governance surfaces must fail review before implementation starts
- no surface listed here grants implementation approval by itself
- no service migration is authorized by this coverage guard

#### Task ingress service approval transition evidence consistency guard

Status: approval transition evidence consistency guard recorded, implementation not approved.

Approval evidence must be present before implementation approval changes for
the task ingress service migration. The current state intentionally records no
approval evidence because no service migration has been approved.

| Evidence item | Required location | Current approval evidence present |
|---------------|-------------------|-----------------------------------|
| red test evidence | `Task ingress service contract migration readiness checklist` | false |
| green focused regression | `Task ingress service contract migration readiness checklist` | false |
| architecture/source regression | `Task ingress service contract migration readiness checklist` | false |
| approval flag update evidence | `Task ingress service contract migration approval flag consistency guard` | false |
| landing record placeholder | `Task ingress service contract migration landing record template` | false |
| rollback placeholder evidence | `Task ingress service rollback placeholder consistency guard` | false |
| post-push branch status | `Task ingress service contract migration readiness checklist` | false |

Rules:

- approval evidence must be present before implementation approval changes
- all approval evidence rows must move together in the approval-transition
  governance commit
- no row may claim current approval evidence while implementation remains
  unapproved
- no service migration is authorized by this evidence guard

### Adapter substitution source guard baseline

Status: source guard added for substitution fixtures.

`tests/unit/test_adapter_substitution_source_guards.py` now guards
`tests/unit/test_adapter_port_substitution.py` so substitution fixtures do not import concrete layers while proving adapter replaceability. The guard confirms:

- no side-effect sinks
- no proof authority write surfaces
- no production wiring

This baseline keeps the adapter substitution fixtures focused on fake injected
ports and prevents them from becoming an accidental production-wiring path.

#### Adapter substitution fixture import coverage guard

Status: import coverage guard added for adapter substitution fixtures.

`tests/unit/test_adapter_substitution_source_guards.py` now requires
`tests/unit/test_adapter_port_substitution.py` to import only adapter skeletons
and ports while explicitly forbidding every other FlagHunter layer:

- `flaghunter.agents`
- `flaghunter.application`
- `flaghunter.config`
- `flaghunter.cpa_modules`
- `flaghunter.domain`
- `flaghunter.interface`
- `flaghunter.knowledge`
- `flaghunter.llm`
- `flaghunter.mcp`
- `flaghunter.playbooks`
- `flaghunter.runtime`
- `flaghunter.session`
- `flaghunter.tools`
- `flaghunter.workspaces`

This guard keeps substitution fixtures focused on fake injected ports and
prevents them from silently becoming a domain-contract, application-service,
legacy feature-module, playbook, runtime, MCP, tool, session, or workspace
integration path.

Boundary confirmation for this guard:

- no production behavior changes
- no concrete adapter production wiring
- no composition root changes
- no MCP production wiring
- no dispatcher loop changes
- no runtime construction
- no ToolExecutor changes
- no proof authority behavior changes

#### Adapter production wiring source guard

Status: production wiring source guard added for adapter skeletons.

`tests/unit/test_adapter_boundary_skeleton.py` now guards adapter sources
against production assembly surfaces. Adapter skeletons may wrap injected ports
or fake test ports, but they may not reference these production wiring names
before an approved composition-root slice:

- `FlagHunterAgent`
- `AgentSession`
- `MCPRouter`
- `MCPServer`
- `CompositionRoot`
- `create_agent`
- `run_task_async`

This guard keeps `flaghunter/adapters` from becoming an accidental composition
root, MCP task runner, or agent/session factory while adapter skeletons remain
unwired.

Boundary confirmation for this guard:

- no concrete adapter production wiring
- no composition root changes
- no MCP production wiring
- no dispatcher loop changes
- no runtime construction
- no ToolExecutor changes
- no proof authority behavior changes

#### Adapter action sink coverage guard

Status: explicit action sink coverage guard added for adapter skeletons before
production wiring.

`tests/unit/test_adapter_boundary_skeleton.py` now requires the adapter action
guard to explicitly cover common filesystem, process, network, and socket
sinks:

- `open(`
- `Path.open`
- `Path.read_text`
- `Path.write_text`
- `Path.read_bytes`
- `Path.write_bytes`
- `subprocess.run`
- `subprocess.Popen`
- `subprocess.call`
- `asyncio.create_subprocess_exec`
- `asyncio.create_subprocess_shell`
- `requests.get`
- `requests.post`
- `requests.request`
- `httpx.get`
- `httpx.post`
- `httpx.request`
- `socket.socket`

This guard keeps adapter skeletons unwired and prevents future adapter slices
from becoming accidental filesystem readers/writers, process launchers, network
clients, socket users, runtime surfaces, or tool executors before an approved
adapter-wrapper or production-wiring slice.

Boundary confirmation for this guard:

- no production behavior changes
- no concrete adapter production wiring
- no composition root changes
- no MCP production wiring
- no dispatcher loop changes
- no runtime construction
- no ToolExecutor changes
- no proof authority behavior changes

#### Adapter proof action coverage guard

Status: explicit proof action coverage guard added for adapter skeletons before
production wiring.

`tests/unit/test_adapter_boundary_skeleton.py` now requires the adapter proof
guard to explicitly cover proof authority write, upgrade, and accepted-proof
sink names:

- `append_proof_record`
- `append_verification_record`
- `confirm_claim`
- `level="verified"`
- `level='verified'`
- `upgrade_claim_to_verified`
- `verification_decision`
- `verified_flags`

This guard keeps adapter skeletons from becoming proof authorities or accepted
proof writers before an approved proof-authority adapter-wrapper or production
wiring slice. The only current exception is the dedicated proof authority adapter
skeleton, which may expose neutral port-delegation methods for
`append_proof_record` and `confirm_claim` without constructing concrete
verifier/proof-authority implementations or changing proof authority behavior.

Boundary confirmation for this guard:

- no production behavior changes
- no concrete adapter production wiring
- no composition root changes
- no MCP production wiring
- no dispatcher loop changes
- no runtime construction
- no ToolExecutor changes
- no proof authority behavior changes

#### Adapter outer-layer import coverage guard

Status: outer-layer import coverage guard added for adapter skeletons.

`tests/unit/test_adapter_boundary_skeleton.py` now requires the adapter source
guard to cover every outer production layer while adapter skeletons remain
unwired:

- `flaghunter.agents`
- `flaghunter.application`
- `flaghunter.config`
- `flaghunter.cpa_modules`
- `flaghunter.interface`
- `flaghunter.knowledge`
- `flaghunter.llm`
- `flaghunter.mcp`
- `flaghunter.playbooks`
- `flaghunter.runtime`
- `flaghunter.session`
- `flaghunter.tools`
- `flaghunter.workspaces`

This guard keeps current adapter skeletons from reaching into application
services, production configuration, legacy feature modules, playbooks,
model/runtime code, presentation, MCP, tools, sessions, or workspace helpers
before a focused adapter-wrapper or production-wiring slice is approved.

Boundary confirmation for this guard:

- no production behavior changes
- no concrete adapter production wiring
- no composition root changes
- no MCP production wiring
- no dispatcher loop changes
- no runtime construction
- no ToolExecutor changes
- no proof authority behavior changes

#### Adapter public surface domain-neutral naming guard

Status: public naming guard added for adapter skeletons before production
wiring.

`tests/unit/test_adapter_boundary_skeleton.py` now guards adapter package
paths, module docstrings, class names, function names, and class/function
docstrings against introducing the public domain-specific terms reserved for
legacy implementation details:

- `ctf`
- `pentest`
- `exploit`
- `vulnerability`
- `hacking`
- `attack`
- `redteam`

This keeps new adapter skeleton public surfaces aligned with the neutral
architecture vocabulary while legacy/security terminology remains confined to
existing implementation modules, compatibility details, fixtures, or historical
docs until a focused migration explicitly changes them.

Boundary confirmation for this guard:

- no production behavior changes
- no concrete adapter production wiring
- no composition root changes
- no MCP production wiring
- no dispatcher loop changes
- no runtime construction
- no ToolExecutor changes
- no proof authority behavior changes

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

#### Candidate A approval request crispness guard

Status: crispness guard recorded, implementation not approved by this section.

This guard makes the Candidate A implementation approval request easy to
review before explicit human approval. It records the required approval-package
fields in one parseable table and does not grant implementation approval by
implication.

| Approval package field | Required detail | Present in request |
|------------------------|-----------------|--------------------|
| file list | `flaghunter/interface/blackboard_lite.py`, `tests/unit/interface/test_blackboard_lite.py`, `flaghunter/application/challenge/board_read_model_service.py` only if required | true |
| risk | medium; read-only Web task detail projection | true |
| rollback point | revert the single Candidate A implementation commit | true |
| equivalence tests | `tests/unit/interface/test_blackboard_lite.py` representative and degraded fixtures | true |
| non-goals | dispatcher, state ownership, verifier, ToolExecutor, crew, MCP wiring, composition root, adapters, proof authority, P5 | true |
| focused commands | blackboard focused, application projection focused, architecture/source guards, `git diff --check` | true |

Rules:

- Candidate A still requires explicit human approval before implementation.
- no implementation approval by implication is created by this checklist
- the requested implementation remains one read-only Web blackboard projection
  call-site family
- no dispatcher, state, verifier, ToolExecutor, crew, MCP production wiring,
  composition root, adapter, proof authority, or P5 work is authorized here

#### Candidate A approved execution checklist

Status: not approved; checklist only.

If explicit Candidate A implementation approval is granted, execute the first
read-path switch in this order:

- confirm explicit Candidate A approval is recorded in the playbook before
  editing production code
- update the pre-approval guard in the same implementation commit that changes
  the read path
- edit only `flaghunter/interface/blackboard_lite.py` for the production
  helper switch
- preserve current public projection keys:
  `facts`, `hypotheses`, `pending_verifications`, `decisions`, `candidates`,
  `active_decision`, `action_results`, `recommended_action`, and
  `attack_surfaces`
- prove old/new output equivalence in `tests/unit/interface/test_blackboard_lite.py`
- record implementation landing evidence using the read-path implementation
  landing record template
- rollback point: revert the single Candidate A implementation commit

Forbidden companion edits for the approved Candidate A implementation:

- do not modify `flaghunter/mcp/server/mcp_tools.py`
- do not modify `flaghunter/interface/web_trace_timeline.py`
- do not modify `flaghunter/interface/web_serialize_task.py`
- do not modify `flaghunter/interface/web_control_decision.py`

Boundary constraints for the approved Candidate A implementation:

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

Required verification for the approved Candidate A implementation:

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

#### Candidate B approved execution checklist

Status: not approved; checklist only.

If Candidate A output equivalence has landed and explicit Candidate B
implementation approval is granted, execute the trace timeline read-path switch
in this order:

- confirm Candidate A output equivalence has landed before editing Candidate B
  production code
- confirm explicit Candidate B implementation approval is recorded in the
  playbook
- update the pre-approval guard in the same implementation commit that changes
  the trace timeline read path
- edit only `flaghunter/interface/web_trace_timeline.py` for the production
  helper switch
- preserve event IDs, timestamps, `kind`, `title`, `summary`, `driver`, and `input` fields
- preserve empty, malformed, unsupported, and no-mutation behavior
- prove old/new output equivalence in
  `tests/unit/web_console/test_trace_timeline_read_model_switch.py`
- record implementation landing evidence using the read-path implementation
  landing record template
- rollback point: revert the single Candidate B implementation commit

Forbidden companion edits for the approved Candidate B implementation:

- do not modify `flaghunter/interface/blackboard_lite.py`
- do not modify `flaghunter/mcp/server/mcp_tools.py`
- do not modify `flaghunter/interface/web_serialize_task.py`
- do not modify `flaghunter/interface/web_control_decision.py`

Boundary constraints for the approved Candidate B implementation:

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

Required verification for the approved Candidate B implementation:

```powershell
.\.venv\Scripts\python.exe -m pytest tests/unit/web_console/test_trace_timeline_read_model_switch.py -q
.\.venv\Scripts\python.exe -m pytest tests/unit/test_clean_architecture_migration_playbook.py tests/unit/test_import_layers.py tests/unit/agents/test_p1_source_guards.py tests/unit/test_ports_contracts.py tests/unit/test_domain_challenge_contracts.py -q
git diff --check
```

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

#### Candidate C approved execution checklist

Status: not approved; checklist only.

If Candidate A output equivalence has landed and explicit Candidate C
implementation approval is granted, execute Candidate C as two separate
read-path switch commits:

- confirm Candidate A output equivalence has landed before editing Candidate C
  production code
- confirm explicit Candidate C implementation approval is recorded in the
  playbook
- one call-site family per commit
- serialize-task projection first
- control-decision snapshot merge second
- update the pre-approval guard in the same implementation commit that changes
  the affected Candidate C read path
- prove old/new output equivalence in `tests/unit/interface/test_web_server.py`
- record implementation landing evidence using the read-path implementation
  landing record template
- rollback point: revert the single Candidate C implementation commit for the
  affected call-site family

Allowed production edit targets for approved Candidate C implementation:

- edit only `flaghunter/interface/web_serialize_task.py` for the serialize-task commit
- edit only `flaghunter/interface/web_control_decision.py` for the control-decision commit

Forbidden companion edits for approved Candidate C implementation:

- do not modify `flaghunter/interface/blackboard_lite.py`
- do not modify `flaghunter/interface/web_trace_timeline.py`
- do not modify `flaghunter/mcp/server/mcp_tools.py`
- no bundled serialize-task and control-decision implementation

Boundary constraints for approved Candidate C implementation:

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

Required verification for approved Candidate C implementation:

```powershell
.\.venv\Scripts\python.exe -m pytest tests/unit/interface/test_blackboard_lite.py tests/unit/test_clean_architecture_migration_playbook.py -q
.\.venv\Scripts\python.exe -m pytest tests/unit/interface/test_web_server.py tests/unit/test_clean_architecture_migration_playbook.py -q
.\.venv\Scripts\python.exe -m pytest tests/unit/test_import_layers.py tests/unit/agents/test_p1_source_guards.py tests/unit/test_ports_contracts.py tests/unit/test_domain_challenge_contracts.py -q
git diff --check
```

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

#### Deferred MCP approved execution checklist

Status: not approved; checklist only.

If Web projection equivalence has landed and explicit MCP production wiring
approval is granted, execute the Deferred MCP readback switch in this order:

- confirm Web projection equivalence has landed before editing MCP readback code
- confirm explicit MCP production wiring approval is recorded in the playbook
- update the pre-approval guard in the same implementation commit that changes
  MCP readback
- edit only `flaghunter/mcp/server/mcp_tools.py::_append_blackboard_snapshot_lines`
- consume the same approved read-model projection used by the Web read path
- must not become an independent projection shape
- preserve readback line text, ordering, and omission behavior
- prove old/new output equivalence in
  `tests/unit/mcp/test_mcp_ingress_mode_contract.py`
- record implementation landing evidence using the read-path implementation
  landing record template
- rollback point: revert the single Deferred MCP implementation commit

Forbidden companion edits for the approved Deferred MCP implementation:

- do not modify Candidate A, Candidate B, or Candidate C production helpers
- do not modify task execution, task creation, async task handling, or router
  dispatch logic

Boundary constraints for the approved Deferred MCP implementation:

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

Required verification for the approved Deferred MCP implementation:

```powershell
.\.venv\Scripts\python.exe -m pytest tests/unit/mcp/test_mcp_ingress_mode_contract.py tests/unit/test_clean_architecture_migration_playbook.py -q
.\.venv\Scripts\python.exe -m pytest tests/unit/test_import_layers.py tests/unit/agents/test_p1_source_guards.py tests/unit/test_ports_contracts.py tests/unit/test_domain_challenge_contracts.py -q
git diff --check
```

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
| Candidate A | approval requested, not approved | `blackboard_lite.py` | explicit Candidate A implementation approval |
| Candidate B | ready for approval review, not approved | `web_trace_timeline.py` | Candidate A equivalence lands and Candidate B implementation approval |
| Candidate C | blocked on Candidate A approval, not approved | `web_serialize_task.py and web_control_decision.py` | Candidate A equivalence lands and Candidate C implementation approval |
| Deferred MCP | blocked on Web projection equivalence and explicit MCP approval, not approved | `mcp_tools.py` | Web projection equivalence lands plus explicit MCP production wiring approval |

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

#### Read-path approval package summary

Status: consolidated approval package recorded, no implementation approved by
this section.

| Candidate | Current status | Target | evidence present | remaining blocker |
|-----------|----------------|--------|------------------|-------------------|
| Candidate A | approval requested, not approved | `flaghunter/interface/blackboard_lite.py::build_task_blackboard_snapshot` | neutral projection fixtures, Web blackboard fixtures, source guard, pre-approval guard | explicit Candidate A implementation approval |
| Candidate B | ready for approval review, not approved | `flaghunter/interface/web_trace_timeline.py::_build_control_observation_timeline_events` | characterization fixture, read-only source guard, pre-approval guard | Candidate A equivalence lands and Candidate B implementation approval |
| Candidate C | blocked on Candidate A approval, not approved | `flaghunter/interface/web_serialize_task.py::_serialize_task` and `flaghunter/interface/web_control_decision.py::_task_blackboard_snapshot_for_decision` | serialize-task fixture, control-decision merge fixture, source guard, pre-approval guard | Candidate A equivalence lands and Candidate C implementation approval |
| Deferred MCP | blocked on Web projection equivalence and explicit MCP approval, not approved | `flaghunter/mcp/server/mcp_tools.py::_append_blackboard_snapshot_lines` | readback formatting fixture, empty/malformed fixture, source guard, pre-approval guard | Web projection equivalence lands plus explicit MCP production wiring approval |

This package records implementation not approved. Any production implementation
still requires the candidate-specific approval state transition and a single
implementation commit.

Forbidden scope for this package:

- no production path switch
- no dispatcher loop changes
- no `CTFState` ownership split
- no `CTFVerifier` proof behavior changes
- no ToolExecutor changes
- no WorkerPool/CrewOrchestrator changes
- no MCP production wiring
- no composition root changes
- no proof authority behavior changes
- no P5 implementation

#### Read-path candidate status ledger

Status: machine-readable status ledger recorded, no implementation approved by this section.

This machine-readable approval ledger is the compact index for the current
read-path candidate state. It is intentionally repetitive with the narrative
sections so guard tests can detect drift before implementation starts.

| Candidate | canonicalStatus | approvedForImplementation | nextGate |
|-----------|-----------------|---------------------------|----------|
| Candidate A | approval requested, not approved | false | explicit Candidate A implementation approval |
| Candidate B | ready for approval review, not approved | false | Candidate A equivalence lands and Candidate B implementation approval |
| Candidate C | blocked on Candidate A approval, not approved | false | Candidate A equivalence lands and Candidate C implementation approval |
| Deferred MCP | blocked on Web projection equivalence and explicit MCP approval, not approved | false | Web projection equivalence lands plus explicit MCP production wiring approval |

Rules:

- `approvedForImplementation` must remain `false` until explicit approval is
  recorded for that candidate
- any row status change must be updated in the same governance commit as the
  acceptance matrix, drift guard, approval package summary, and candidate
  readiness checklist
- no implementation approval by implication
- no production path switch is authorized by this ledger

#### Read-path parsed status consistency guard

Status: parsed consistency guard recorded, no implementation approved by this section.

The playbook test suite must parse `Read-path candidate status ledger`,
compare it with `Read-path switch acceptance matrix`, and
compare it with `Read-path approval package summary`. The parsed candidate
names and canonical statuses must remain identical across all three sections
before any implementation approval can land.

Required parsed checks:

- candidate sets match across the ledger, acceptance matrix, and approval package
- ledger `canonicalStatus` matches the acceptance matrix `Status`
- ledger `canonicalStatus` matches the approval package `Current status`
- ledger `approvedForImplementation` remains `false` for every current row
- no production path switch is authorized by this parsed consistency guard

#### Read-path nextGate consistency guard

Status: nextGate consistency guard recorded, no implementation approved by this section.

The playbook test suite must parse the same three read-path approval tables and
prove that each candidate has one canonical blocker before implementation:

- ledger `nextGate` matches the acceptance matrix `Unblock condition`
- ledger `nextGate` matches the approval package `remaining blocker`
- every current `nextGate` still requires explicit candidate-specific approval
- Deferred MCP still requires explicit MCP production wiring approval
- no production path switch is authorized by this nextGate consistency guard

#### Deferred MCP explicit wiring approval guard

Status: explicit MCP approval guard recorded, no implementation approved by this section.

Deferred MCP is the only current read-path candidate whose future implementation
would count as MCP production wiring. It remains blocked until Web projection
equivalence lands plus explicit MCP production wiring approval is recorded.
Web read-path equivalence alone must never authorize an MCP readback switch.

Canonical Deferred MCP blocker: Web projection equivalence lands plus explicit MCP production wiring approval.

Required parsed checks:

- Deferred MCP ledger `nextGate` remains `Web projection equivalence lands plus
  explicit MCP production wiring approval`
- Deferred MCP readiness `Missing approval` remains `Web projection equivalence
  lands plus explicit MCP production wiring approval`
- Deferred MCP approval package `remaining blocker` remains `Web projection
  equivalence lands plus explicit MCP production wiring approval`
- Deferred MCP source-map row remains
  `flaghunter/mcp/server/mcp_tools.py` with `Implementation approved` = `false`
- Deferred MCP approved execution checklist must confirm explicit MCP production wiring approval
- Deferred MCP approved execution checklist keeps `confirm explicit MCP
  production wiring approval`
- Deferred MCP non-goals must keep no MCP production wiring without explicit approval
- Deferred MCP non-goals keep `no MCP production wiring without explicit
  approval`
- no production path switch is authorized by this explicit MCP approval guard

#### Read-path approved execution checklist index

Status: checklist index recorded, no implementation approved by this section.

This index keeps the candidate-specific execution checklists discoverable
without granting implementation approval. Every row must remain
`implementation not approved` until the matching approval state transition is
recorded.

| Candidate | Checklist section | Checklist status | Approval state |
|-----------|-------------------|------------------|----------------|
| Candidate A | `Candidate A approved execution checklist` | not approved; checklist only | implementation not approved |
| Candidate B | `Candidate B approved execution checklist` | not approved; checklist only | implementation not approved |
| Candidate C | `Candidate C approved execution checklist` | not approved; checklist only | implementation not approved |
| Deferred MCP | `Deferred MCP approved execution checklist` | not approved; checklist only | implementation not approved |

Rules:

- each indexed checklist section must exist in this playbook
- each indexed checklist must keep `Status: not approved; checklist only.`
- the index is a readiness map, not implementation approval
- no production path switch is authorized by this checklist index

#### Read-path implementation approval readiness report

Status: readiness report recorded, no implementation approved by this section.

This report separates readiness evidence from approval. It identifies which
candidates have enough recorded evidence to request implementation approval and
which candidates remain sequence-blocked by an earlier read-path switch.

| Candidate | Current status | Readiness state | Missing approval | Implementation approved |
|-----------|----------------|-----------------|------------------|-------------------------|
| Candidate A | approval requested, not approved | approval package ready; explicit implementation approval missing | explicit Candidate A implementation approval | false |
| Candidate B | ready for approval review, not approved | sequence blocked; Candidate A equivalence missing | Candidate A equivalence lands and Candidate B implementation approval | false |
| Candidate C | blocked on Candidate A approval, not approved | sequence blocked; Candidate A equivalence missing | Candidate A equivalence lands and Candidate C implementation approval | false |
| Deferred MCP | blocked on Web projection equivalence and explicit MCP approval, not approved | sequence blocked; Web projection equivalence and MCP approval missing | Web projection equivalence lands plus explicit MCP production wiring approval | false |

Rules:

- readiness evidence is not implementation approval
- Candidate A remains the only first read-path implementation candidate ready
  to ask for explicit approval
- Candidate B and Candidate C remain blocked until Candidate A equivalence lands
- Deferred MCP remains blocked until Web projection equivalence lands and MCP
  production wiring approval is explicit
- no production path switch is authorized by this readiness report

#### Read-path pre-approval source-map guard

Status: source-map guard recorded, no implementation approved by this section.

This source map lists the production source files that must remain free of
neutral read-model projection wiring while the matching read-path candidate is
not approved for implementation. It complements the candidate-specific source
guards by keeping one parseable map in the playbook.

| Candidate | Source path | Forbidden neutral wiring | Implementation approved |
|-----------|-------------|--------------------------|-------------------------|
| Candidate A | `flaghunter/interface/blackboard_lite.py` | `flaghunter.application.challenge`, `flaghunter.domain.challenge.contracts`, `build_task_board_projection`, `BuildChallengeBoardReadModel`, `ChallengeBoardReadModel` | false |
| Candidate B | `flaghunter/interface/web_trace_timeline.py` | `flaghunter.application.challenge`, `flaghunter.domain.challenge.contracts`, `build_task_board_projection`, `BuildChallengeBoardReadModel`, `ChallengeBoardReadModel` | false |
| Candidate C serialize-task | `flaghunter/interface/web_serialize_task.py` | `flaghunter.application.challenge`, `flaghunter.domain.challenge.contracts`, `build_task_board_projection`, `BuildChallengeBoardReadModel`, `ChallengeBoardReadModel` | false |
| Candidate C control-decision | `flaghunter/interface/web_control_decision.py` | `flaghunter.application.challenge`, `flaghunter.domain.challenge.contracts`, `build_task_board_projection`, `BuildChallengeBoardReadModel`, `ChallengeBoardReadModel` | false |
| Deferred MCP | `flaghunter/mcp/server/mcp_tools.py` | `flaghunter.application.challenge`, `flaghunter.domain.challenge.contracts`, `build_task_board_projection`, `BuildChallengeBoardReadModel`, `ChallengeBoardReadModel` | false |

Rules:

- every source path in this map must exist
- forbidden neutral wiring must remain absent until explicit implementation
  approval lands for that candidate
- source-map rows must remain `Implementation approved` = `false` until the
  matching implementation commit updates the pre-approval guard
- no production path switch is authorized by this source-map guard

#### Read-path source-map forbidden-token single-source guard

Status: forbidden-token parser guard recorded, no implementation approved by this section.

The `Forbidden neutral wiring` column in `Read-path pre-approval source-map
guard` is the single source of truth for neutral read-model wiring tokens that
must stay absent from each unapproved production source path. The playbook test
suite must parse that table column directly, with no hardcoded duplicate token
tuple in the test body.

Rules:

- no hardcoded duplicate token tuple may replace the playbook table as the
  guard source
- every forbidden token checked by the source-map guard must come from the
  `Forbidden neutral wiring` table cell for that source row
- updating the source-map token set requires changing the playbook table, not a
  parallel hardcoded list
- all listed tokens remain forbidden while the row's `Implementation approved`
  value is `false`
- no production path switch is authorized by this parser guard

#### Read-path approval package source-map consistency guard

Status: approval package source-map consistency guard recorded, no implementation approved by this section.

The read-path approval package and pre-approval source map must stay aligned
before any implementation approval is granted. Every approval package row that
claims `evidence present` must include both `source guard` and `pre-approval
guard`, and every target source path listed in the approval package must have
matching source-map coverage.

Required parsed checks:

- approval package candidates match the canonical source-map candidates after
  Candidate C source-map sub-rows collapse back to Candidate C
- every approval package `evidence present` cell includes `source guard`
- every approval package `evidence present` cell includes `pre-approval guard`
- each approval package target source path matches the source paths listed for
  that candidate in `Read-path pre-approval source-map guard`
- no production path switch is authorized by this source-map coverage guard

#### Read-path implementation landed evidence guard

Status: landed evidence guard recorded, no implementation approved by this section.

This guard prevents a candidate from being marked `implementation landed`
without the landing record required by the template below. Current rows have no
landing evidence because no read-path implementation has been approved or
landed.

| Candidate | Implementation landed | Landing evidence | Required before landed |
|-----------|-----------------------|------------------|------------------------|
| Candidate A | false | none | landing record, commit SHA, regression results |
| Candidate B | false | none | landing record, commit SHA, regression results |
| Candidate C | false | none | landing record, commit SHA, regression results |
| Deferred MCP | false | none | landing record, commit SHA, regression results |

Rules:

- no row may move to `Implementation landed` = `true` without a
  candidate-specific landing record
- the landing record must include the implementation commit SHA, old/new
  equivalence evidence, pre-approval guard update, focused regression,
  architecture/source-guard result, `git diff --check`, post-push status, and
  rollback command
- a status change to `implementation landed` must be in the same commit as the
  landing evidence update
- no production path switch is authorized by this landed evidence guard

#### Read-path approval flag aggregate guard

Status: aggregate approval flag guard recorded, no implementation approved by this section.

This aggregate guard ties together the boolean approval and landing fields that
are intentionally repeated across the read-path governance tables, including
ledger `approvedForImplementation`, readiness report `Implementation approved`,
source-map `Implementation approved`, and landed evidence `Implementation
landed`. A future
approval or landing change must update all related rows in the same governance
or implementation commit.

Required aggregate checks:

- ledger `approvedForImplementation` matches the readiness report
  `Implementation approved`
- source-map `Implementation approved` remains `false` while the ledger
  `approvedForImplementation` remains `false`
- landed evidence `Implementation landed` remains `false` until a landing
  record exists
- Candidate C source-map sub-rows must collapse back to the canonical
  Candidate C ledger row
- no production path switch is authorized by this aggregate approval flag guard

#### Read-path rollback command index

Status: rollback command index recorded, no implementation approved by this section.

This index records placeholder only rollback commands for future read-path
implementation commits. Each command becomes valid only after the matching
candidate implementation commit lands and its landing record captures the real
commit SHA. A placeholder is not a currently executable rollback command and
does not imply that any read-path implementation has landed.

| Candidate | Rollback command | Applies after | Current executable |
|-----------|------------------|---------------|--------------------|
| Candidate A | `git revert <single Candidate A implementation commit>` | candidate implementation commit lands | false |
| Candidate B | `git revert <single Candidate B implementation commit>` | candidate implementation commit lands | false |
| Candidate C serialize-task | `git revert <single Candidate C serialize-task implementation commit>` | candidate implementation commit lands | false |
| Candidate C control-decision | `git revert <single Candidate C control-decision implementation commit>` | candidate implementation commit lands | false |
| Deferred MCP | `git revert <single Deferred MCP implementation commit>` | candidate implementation commit lands | false |

Rules:

- Candidate C remains split into separate rollback rows because its two
  approved future call-site families must land as separate implementation
  commits.
- every rollback command remains a placeholder until the matching landing
  record contains a real implementation commit SHA
- `Current executable` remains `false` while the corresponding implementation
  has not landed
- no production path switch is authorized by this rollback command index

#### Read-path landing rollback consistency guard

Status: landing rollback consistency guard recorded, no implementation approved by this section.

The rollback index and landing record template serve different stages. The
rollback index keeps placeholder rollback commands non-executable before
implementation. A future landing record must replace the placeholder with the
real implementation commit SHA by recording `Rollback command: git revert
<sha>`.

Required parsed checks:

- placeholder rollback commands remain non-executable while
  `Current executable` is `false`
- placeholder rollback commands must not contain a real commit SHA before a
  landing record exists
- the landing record template keeps `Rollback command: git revert <sha>`
- every current landed evidence row remains `Implementation landed` = `false`
  with `Landing evidence` = `none`
- every future landed row must include a real implementation commit SHA before
  its rollback command can become executable
- no production path switch is authorized by this landing rollback guard

#### Candidate C split commit consistency guard

Status: split commit consistency guard recorded, no implementation approved by this section.

Candidate C has two future read-path call-site families and must remain split
across the approval checklist, source map, and rollback index. If explicit
Candidate C implementation approval is later granted, it still requires two
separate read-path switch commits: serialize-task projection first and
control-decision snapshot merge second.

The required execution shape is two separate read-path switch commits with no
bundled serialize-task and control-decision implementation.

Required parsed checks:

- `Read-path pre-approval source-map guard` keeps separate Candidate C rows for
  `flaghunter/interface/web_serialize_task.py` and
  `flaghunter/interface/web_control_decision.py`
- `Read-path rollback command index` keeps separate Candidate C rollback
  placeholders for serialize-task and control-decision
- `Candidate C approved execution checklist` keeps `one call-site family per
  commit`
- `Candidate C approved execution checklist` keeps `serialize-task projection
  first`
- `Candidate C approved execution checklist` keeps `control-decision snapshot
  merge second`
- no bundled serialize-task and control-decision implementation is allowed
- no production path switch is authorized by this split commit guard

#### Read-path approval status consistency guard

Status: approval consistency guard recorded, no implementation approved by this
section.

The read-path approval state has a single source of approval truth across the
acceptance matrix, drift guard, approval package summary, and each
candidate-specific implementation readiness checklist.

| Candidate | Canonical status | Must match |
|-----------|------------------|------------|
| Candidate A | approval requested, not approved | acceptance matrix, drift guard, approval package summary, Candidate A readiness checklist |
| Candidate B | ready for approval review, not approved | acceptance matrix, drift guard, approval package summary, Candidate B readiness checklist |
| Candidate C | blocked on Candidate A approval, not approved | acceptance matrix, drift guard, approval package summary, Candidate C readiness checklist |
| Deferred MCP | blocked on Web projection equivalence and explicit MCP approval, not approved | acceptance matrix, drift guard, approval package summary, Deferred MCP readiness checklist |

Any approval status change must land in the same governance commit before
implementation starts. The update must include:

- acceptance matrix row
- drift guard fact
- approval package summary row
- candidate-specific implementation readiness checklist
- verification evidence for the status change

There is no status-only implementation approval. The rule is: approval drift must fail review
until all mirrored status locations and the relevant guard tests agree.

#### Read-path approval transition atomicity guard

Status: approval transition atomicity guard recorded, no implementation approved by this section.

Any future read-path approval transition must update every mirrored governance
location in the same governance commit before implementation starts. This guard
records atomicity requirements only; it does not approve implementation and does
not authorize a production path switch.

Required same-commit updates:

- acceptance matrix row
- approval drift fact
- candidate status ledger
- readiness report
- source-map approval flag
- approved execution checklist
- verification evidence

| Atomic update | Required section |
|---------------|------------------|
| acceptance matrix row | `Read-path switch acceptance matrix` |
| approval drift fact | `Read-path approval drift guard` |
| candidate status ledger | `Read-path candidate status ledger` |
| readiness report | `Read-path implementation approval readiness report` |
| source-map approval flag | `Read-path pre-approval source-map guard` |
| approved execution checklist | `Read-path approved execution checklist index` |
| verification evidence | `Read-path implementation landing record template` |

Rules:

- approval transition evidence must land before any implementation commit
- partial approval updates must fail review until all mirrored locations agree
- no production path switch is authorized by this atomicity guard

#### Read-path approval transition candidate coverage guard

Status: candidate coverage guard recorded, no implementation approved by this section.

Every read-path approval transition must cover the same canonical candidate set
across the approval tables and landing evidence rows. Candidate C split source-map rows collapse to the canonical Candidate C approval state for
approval status checks, while its future implementation commits remain split by
call-site family.

| Candidate | Required coverage | Current implementation approval |
|-----------|-------------------|---------------------------------|
| Candidate A | acceptance, drift, package, ledger, readiness, source-map, checklist, landing evidence | false |
| Candidate B | acceptance, drift, package, ledger, readiness, source-map, checklist, landing evidence | false |
| Candidate C | acceptance, drift, package, ledger, readiness, source-map, checklist, landing evidence | false |
| Deferred MCP | acceptance, drift, package, ledger, readiness, source-map, checklist, landing evidence | false |

Rules:

- every approval table must keep the same canonical candidate set
- split Candidate C source-map rows must not create a second approval state
- no production path switch is authorized by this candidate coverage guard

#### Read-path implementation landing record template

Status: landing evidence template recorded, no implementation approved by this
section.

Any future read-path implementation commit must add a candidate-specific landing
record with these fields before the candidate can move to `implementation
landed`:

- candidate
- implementation commit SHA
- target helper or call-site family
- old/new output equivalence evidence and fixture name
- pre-approval guard update made in the same implementation commit
- focused regression result
- architecture/source-guard result
- `git diff --check` result
- post-push branch status
- rollback command

The landing record must keep these boundaries explicit:

- one production call-site family per commit
- no bundled Web and MCP implementation
- no dispatcher loop changes
- no `CTFState` ownership split
- no `CTFVerifier` proof behavior changes
- no ToolExecutor changes
- no WorkerPool/CrewOrchestrator changes
- no MCP production wiring unless the candidate is Deferred MCP and explicit
  MCP approval is recorded
- no composition root changes
- no proof authority behavior changes
- no P5 implementation

Example landing record shape for a future approved implementation:

```text
Candidate: <Candidate A | Candidate B | Candidate C | Deferred MCP>
Implementation commit SHA: <sha>
Target: <helper or call-site family>
Equivalence evidence: <test name and result>
Pre-approval guard update: <guard test name and result>
Focused regression result: <command and exact result>
Architecture/source-guard result: <command and exact result>
git diff --check result: <exact result>
Post-push branch status: <git status --short --branch>
Rollback command: git revert <sha>
Boundary confirmation: <unchanged high-risk areas>
```

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
