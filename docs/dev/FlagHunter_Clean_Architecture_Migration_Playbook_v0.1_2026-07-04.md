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

### Legacy read-model shim side-effect sink coverage guard

Status: explicit side-effect sink coverage guard added for Phase 2B
compatibility shims.

`tests/unit/agents/test_phase2b_compatibility_shims.py` now requires legacy
read-model shim side-effect guards to explicitly cover process, filesystem,
network, socket, browser/runtime, and tool-execution sink names:

- `Playwright`
- `ToolExecutor`
- `asyncio.subprocess`
- `httpx`
- `open(`
- `requests`
- `socket`
- `subprocess`
- `write_text`

This guard keeps legacy read-model compatibility shims as re-export-only
compatibility surfaces. Shims may preserve old import paths for neutral domain
contracts, but they must not become filesystem readers/writers, process
launchers, network clients, socket users, browser/runtime surfaces, or tool
executors.

Boundary confirmation for this guard:

- no production behavior changes
- no concrete adapter construction
- no composition root changes
- no MCP production wiring
- no dispatcher loop changes
- no runtime construction
- no ToolExecutor changes
- no proof authority behavior changes

### Legacy read-model shim outer-layer import coverage guard

Status: explicit outer-layer import coverage guard added for Phase 2B
compatibility shims.

`tests/unit/agents/test_phase2b_compatibility_shims.py` now requires legacy
read-model shim import guards to explicitly cover legacy evaluation and
red-team helper packages:

- `flaghunter.eval`
- `flaghunter.redteam`

This guard keeps legacy read-model compatibility shims as narrow re-export
surfaces for neutral domain contracts. Shims may preserve old import paths, but
they must not reach into evaluation harnesses, red-team legacy helpers,
runtime, tools, MCP, presentation, session, or harness integration paths.

Boundary confirmation for this guard:

- no production behavior changes
- no concrete adapter construction
- no composition root changes
- no MCP production wiring
- no dispatcher loop changes
- no runtime construction
- no ToolExecutor changes
- no proof authority behavior changes

### Legacy read-model shim coverage completeness guard

Status: aggregate coverage completeness guard added for Phase 2B
compatibility shims.

`tests/unit/agents/test_phase2b_compatibility_shims.py` now requires the legacy
read-model shim guard record to keep all Phase 2B shim boundary guard groups
visible together:

- `Legacy read-model shim outer-layer import coverage guard`
- `Legacy read-model shim side-effect sink coverage guard`
- `Legacy read-model shim proof action coverage guard`

This aggregate guard prevents Phase 2B compatibility shim coverage from
drifting into partial protection. Legacy read-model shims must remain
re-export-only compatibility surfaces with outer-layer imports, side-effect
sinks, and proof authority write or upgrade surfaces guarded as one complete
shim boundary.

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
- `flaghunter.eval`
- `flaghunter.interface`
- `flaghunter.knowledge`
- `flaghunter.llm`
- `flaghunter.mcp`
- `flaghunter.playbooks`
- `flaghunter.ports`
- `flaghunter.redteam`
- `flaghunter.runtime`
- `flaghunter.session`
- `flaghunter.tools`
- `flaghunter.workspaces`

This guard keeps `flaghunter/domain/challenge/contracts` as the innermost
schema/read-model layer and prevents future contract slices from reaching
outward into adapters, application services, production configuration,
legacy feature modules, evaluation harnesses, red-team legacy helpers,
playbooks, model/runtime code, presentation, MCP, tools, sessions, or
workspace helpers.

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

### Domain contract public surface domain-neutral naming guard

Status: public naming guard recorded for inner domain contracts.

`tests/unit/test_domain_challenge_contracts.py` now requires the domain
contract public surface guard to keep module path parts, public class names,
public function names, docstrings, and core dataclass field names aligned with
the domain-neutral naming policy.

Forbidden public-domain terms for new domain contracts:

- `ctf`
- `pentest`
- `exploit`
- `vulnerability`
- `hacking`
- `attack`
- `redteam`

Forbidden core proof field names:

- `flag`
- `verified_flag`
- `verified_flags`

This guard keeps new `flaghunter/domain/challenge/contracts` surfaces in the
neutral challenge/task/claim/evidence/proof vocabulary. Legacy security terms
remain confined to legacy implementation, adapters, compatibility shims,
fixtures, or historical documentation until a focused migration explicitly
moves or removes them.

Boundary confirmation for this guard:

- no production behavior changes
- no concrete adapter construction
- no composition root changes
- no MCP production wiring
- no dispatcher loop changes
- no runtime construction
- no ToolExecutor changes
- no proof authority behavior changes

### Domain contract source guard coverage completeness guard

Status: aggregate coverage completeness guard added for inner domain contracts.

`tests/unit/test_domain_challenge_contracts.py` now requires the domain
contract source guard record to keep all domain boundary guard groups visible
together:

- `Domain contract production wiring source guard`
- `Domain contract outer-layer import coverage guard`
- `Domain contract side-effect sink coverage guard`
- `Domain contract proof action coverage guard`
- `Domain contract public surface domain-neutral naming guard`

This aggregate guard prevents the innermost domain-contract boundary coverage
from drifting into partial protection. Domain contracts must keep production
wiring surfaces, outer-layer imports, side-effect sinks, proof authority write
or upgrade surfaces, and public neutral naming guarded as one complete
pure-schema boundary.

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

### Candidate A neutral metadata projection baseline

Status: neutral metadata projection fixture added before any production path
switch.

`BuildChallengeBoardReadModel` now promotes neutral snapshot metadata fields
`decisions`, `candidates`, `actionResults`, and `recommendedTask` into the
first-class `ChallengeBoardReadModel` fields that
`build_task_board_projection` already projects into Candidate A-compatible
response keys. Promoted fields are removed from residual metadata, while
read-side context such as `hypotheses` remains under metadata for projection.

`tests/unit/test_application_board_read_model_service.py` records this baseline
with `test_build_promotes_neutral_board_metadata_to_read_model_fields`, giving a
future Candidate A implementation slice a fuller neutral board input without
touching `flaghunter/interface/blackboard_lite.py`.

Boundary confirmation for this baseline:

- no production path switch
- no dispatcher loop changes
- no `CTFState` ownership split
- no `CTFVerifier` proof behavior changes
- no ToolExecutor changes
- no WorkerPool/CrewOrchestrator changes
- no MCP production wiring
- no proof authority behavior changes

### Candidate A neutral metadata alias projection baseline

Status: neutral metadata alias fixture added before any production path switch.

`BuildChallengeBoardReadModel` now accepts legacy-compatible read-side metadata
aliases and still projects them into neutral `ChallengeBoardReadModel` fields:
`activeDecision` becomes the first decision row, `recommendedAction` becomes
`recommendedTask`, `action_results` becomes `actionResults`, and
`attack_surfaces` becomes `surfaceRefs`. The aliases are removed from residual
metadata after promotion.

`tests/unit/test_application_board_read_model_service.py` records this baseline
with `test_build_promotes_board_metadata_aliases_to_read_model_fields`, giving
future Candidate A equivalence work a neutral builder that can consume both
fresh neutral metadata and compatibility-shaped read-side inputs before any
production call site is switched.

Boundary confirmation for this baseline:

- no production path switch
- no dispatcher loop changes
- no `CTFState` ownership split
- no `CTFVerifier` proof behavior changes
- no ToolExecutor changes
- no WorkerPool/CrewOrchestrator changes
- no MCP production wiring
- no proof authority behavior changes

### Candidate A neutral candidate enrichment baseline

Status: candidate enrichment fixture added before any production path switch.

`build_task_board_projection` now enriches the selected candidate with active
decision display fields and enriches the recommended candidate with
recommended-action trigger and strongest-hypothesis fields. This mirrors the
current Candidate A blackboard display shape while keeping the work inside the
neutral application projection helper.

`tests/unit/test_application_board_read_model_service.py` records this baseline
with `test_task_board_projection_enriches_selected_and_recommended_candidates`,
so future Candidate A read-path equivalence work can compare selected candidate
and recommended candidate details before touching `blackboard_lite.py`.

Boundary confirmation for this baseline:

- no production path switch
- no dispatcher loop changes
- no `CTFState` ownership split
- no `CTFVerifier` proof behavior changes
- no ToolExecutor changes
- no WorkerPool/CrewOrchestrator changes
- no MCP production wiring
- no proof authority behavior changes

### Candidate A neutral candidate ordering baseline

Status: candidate ordering fixture added before any production path switch.

`build_task_board_projection` now orders neutral candidates by `priority` and
then action name when priority metadata is present, and projects `lastResult`
from the latest matching action result. This mirrors the Candidate A display
contract needed for a future Web blackboard equivalence check while keeping the
behavior inside the neutral application projection helper.

`tests/unit/test_application_board_read_model_service.py` records this baseline
with `test_task_board_projection_orders_candidates_and_projects_last_result`,
so future Candidate A read-path equivalence work can compare candidate ordering
and latest result display without touching `blackboard_lite.py`.

Boundary confirmation for this baseline:

- no production path switch
- no dispatcher loop changes
- no `CTFState` ownership split
- no `CTFVerifier` proof behavior changes
- no ToolExecutor changes
- no WorkerPool/CrewOrchestrator changes
- no MCP production wiring
- no proof authority behavior changes

### Candidate A neutral candidate marker baseline

Status: candidate marker fixture added before any production path switch.

`build_task_board_projection` now adds `recommended=False` to ordered neutral candidates
when they do not already carry a recommendation marker. This mirrors
the current Candidate A candidate display contract where candidates start as
not recommended before explicit or derived recommendation logic marks one as
recommended.

`tests/unit/test_application_board_read_model_service.py` records this baseline
with
`test_task_board_projection_adds_default_recommended_marker_for_ordered_candidates`,
so future Candidate A read-path equivalence work can compare ordered neutral
candidates without synthesizing marker state in `blackboard_lite.py`.

Boundary confirmation for this baseline:

- no production path switch
- no dispatcher loop changes
- no `CTFState` ownership split
- no `CTFVerifier` proof behavior changes
- no ToolExecutor changes
- no WorkerPool/CrewOrchestrator changes
- no MCP production wiring
- no proof authority behavior changes

### Candidate A neutral hypothesis summary alias baseline

Status: hypothesis summary alias fixture added before any production path switch.

`build_task_board_projection` now accepts read-side hypothesis summary aliases
such as `strongest_hypothesis_kind`, `strongest_hypothesis_status`, and
`strongest_hypothesis_confidence` from neutral action-result inputs and projects
them into the Candidate A-compatible `strongestHypothesisKind`,
`strongestHypothesisStatus`, and `strongestHypothesisConfidence` fields. This
matches the current read-side event payload shape without reading legacy state.

`tests/unit/test_application_board_read_model_service.py` records this baseline
with `test_task_board_projection_accepts_hypothesis_summary_aliases`, so future
Candidate A read-path equivalence work can compare hypothesis summary display
fields before touching `blackboard_lite.py`.

Boundary confirmation for this baseline:

- no production path switch
- no dispatcher loop changes
- no `CTFState` ownership split
- no `CTFVerifier` proof behavior changes
- no ToolExecutor changes
- no WorkerPool/CrewOrchestrator changes
- no MCP production wiring
- no proof authority behavior changes

### Candidate A neutral source type alias baseline

Status: source type alias fixture added before any production path switch.

`build_task_board_projection` now accepts neutral candidate `source_type`
metadata and projects it into the Candidate A-compatible `sourceType` field
when deriving a recommended action. The recommended candidate enrichment path
also receives `sourceType` from the derived recommendation, keeping source
classification display-compatible without reading legacy state.

`tests/unit/test_application_board_read_model_service.py` records this baseline
with `test_task_board_projection_accepts_candidate_source_type_alias`, so
future Candidate A read-path equivalence work can compare candidate source
classification before touching `blackboard_lite.py`.

Boundary confirmation for this baseline:

- no production path switch
- no dispatcher loop changes
- no `CTFState` ownership split
- no `CTFVerifier` proof behavior changes
- no ToolExecutor changes
- no WorkerPool/CrewOrchestrator changes
- no MCP production wiring
- no proof authority behavior changes

### Candidate A neutral trigger reason alias baseline

Status: trigger reason alias fixture added before any production path switch.

`build_task_board_projection` now accepts direct action-result trigger reason
metadata as `triggerReason` or `trigger_reason` when deriving a recommended
action. The existing `details.reason` payload remains the first source, while
the aliases keep neutral read-side event payloads display-compatible with
Candidate A's `triggerReason` field.

`tests/unit/test_application_board_read_model_service.py` records this baseline
with `test_task_board_projection_accepts_action_result_trigger_reason_alias`,
so future Candidate A read-path equivalence work can compare trigger reason
display fields before touching `blackboard_lite.py`.

Boundary confirmation for this baseline:

- no production path switch
- no dispatcher loop changes
- no `CTFState` ownership split
- no `CTFVerifier` proof behavior changes
- no ToolExecutor changes
- no WorkerPool/CrewOrchestrator changes
- no MCP production wiring
- no proof authority behavior changes

### Candidate A neutral trigger action driver alias baseline

Status: trigger action driver alias fixture added before any production path switch.

`build_task_board_projection` now accepts direct action-result trigger action
driver metadata as `triggerActionDriver` or `trigger_action_driver` when
deriving a recommended action. The existing action-result `driver` remains the
first source, while the aliases keep neutral read-side event payloads
display-compatible with Candidate A's `triggerActionDriver` field.

`tests/unit/test_application_board_read_model_service.py` records this baseline
with `test_task_board_projection_accepts_action_result_trigger_driver_alias`,
so future Candidate A read-path equivalence work can compare trigger action
driver display fields before touching `blackboard_lite.py`.

Boundary confirmation for this baseline:

- no production path switch
- no dispatcher loop changes
- no `CTFState` ownership split
- no `CTFVerifier` proof behavior changes
- no ToolExecutor changes
- no WorkerPool/CrewOrchestrator changes
- no MCP production wiring
- no proof authority behavior changes

### Candidate A neutral trigger time alias baseline

Status: trigger time alias fixture added before any production path switch.

`build_task_board_projection` now accepts direct action-result trigger time
metadata as `triggerAt` or `trigger_at` when deriving a recommended action. The
existing action-result `t` timestamp remains the first source, while the aliases
keep neutral read-side event payloads display-compatible with Candidate A's
`triggerAt` field.

`tests/unit/test_application_board_read_model_service.py` records this baseline
with `test_task_board_projection_accepts_action_result_trigger_time_alias`, so
future Candidate A read-path equivalence work can compare trigger timestamp
display fields before touching `blackboard_lite.py`.

Boundary confirmation for this baseline:

- no production path switch
- no dispatcher loop changes
- no `CTFState` ownership split
- no `CTFVerifier` proof behavior changes
- no ToolExecutor changes
- no WorkerPool/CrewOrchestrator changes
- no MCP production wiring
- no proof authority behavior changes

### Candidate A neutral trigger result alias baseline

Status: trigger result alias fixture added before any production path switch.

`build_task_board_projection` now accepts direct action-result status metadata
as `triggerResult` or `trigger_result` when deriving a recommended action. The
existing action-result `result` field remains the first source, while the
aliases keep neutral read-side event payloads display-compatible with Candidate
A's `triggerResult` field.

`tests/unit/test_application_board_read_model_service.py` records this baseline
with `test_task_board_projection_accepts_action_result_trigger_result_alias`,
so future Candidate A read-path equivalence work can compare trigger result
display fields before touching `blackboard_lite.py`.

Boundary confirmation for this baseline:

- no production path switch
- no dispatcher loop changes
- no `CTFState` ownership split
- no `CTFVerifier` proof behavior changes
- no ToolExecutor changes
- no WorkerPool/CrewOrchestrator changes
- no MCP production wiring
- no proof authority behavior changes

### Candidate A neutral expected action alias baseline

Status: action-result expected-action alias fixture added before any production path switch.

`build_task_board_projection` now accepts neutral action-result expected action
metadata as `expected_action` and normalizes it into the Candidate A-compatible
`expectedAction` field. Existing `expectedAction` remains the first source,
while the alias is removed from projected rows so neutral inputs do not change
the public response key shape.

`tests/unit/test_application_board_read_model_service.py` records this baseline
with `test_task_board_projection_accepts_action_result_expected_action_alias`,
so future Candidate A read-path equivalence work can compare action alignment
rows before touching `blackboard_lite.py`.

Boundary confirmation for this baseline:

- no production path switch
- no dispatcher loop changes
- no `CTFState` ownership split
- no `CTFVerifier` proof behavior changes
- no ToolExecutor changes
- no WorkerPool/CrewOrchestrator changes
- no MCP production wiring
- no proof authority behavior changes

### Candidate A neutral observed action alias baseline

Status: action-result observed-action alias fixture added before any production path switch.

`build_task_board_projection` now accepts neutral action-result observed action
metadata as `observed_action` and normalizes it into the Candidate A-compatible
`observedAction` field. Existing `observedAction` remains the first source,
while the alias is removed from projected rows so neutral inputs do not change
the public response key shape.

`tests/unit/test_application_board_read_model_service.py` records this baseline
with `test_task_board_projection_accepts_action_result_observed_action_alias`,
so future Candidate A read-path equivalence work can compare observed action
alignment rows before touching `blackboard_lite.py`.

Boundary confirmation for this baseline:

- no production path switch
- no dispatcher loop changes
- no `CTFState` ownership split
- no `CTFVerifier` proof behavior changes
- no ToolExecutor changes
- no WorkerPool/CrewOrchestrator changes
- no MCP production wiring
- no proof authority behavior changes

### Candidate A neutral task action alias baseline

Status: task action alias fixture added before any production path switch.

`build_task_board_projection` now accepts neutral candidate and action-result
action metadata as `taskAction` or `task_action` and normalizes it into the
Candidate A-compatible `action` field. Existing `action` remains the first
source, while aliases are removed from the projected rows so neutral inputs do
not change the public response key shape.

`tests/unit/test_application_board_read_model_service.py` records this baseline
with `test_task_board_projection_accepts_task_action_aliases`, so future
Candidate A read-path equivalence work can compare task action rows before
touching `blackboard_lite.py`.

Boundary confirmation for this baseline:

- no production path switch
- no dispatcher loop changes
- no `CTFState` ownership split
- no `CTFVerifier` proof behavior changes
- no ToolExecutor changes
- no WorkerPool/CrewOrchestrator changes
- no MCP production wiring
- no proof authority behavior changes

### Candidate A neutral next action alias baseline

Status: active decision next-action alias fixture added before any production path switch.

`build_task_board_projection` now accepts neutral active decision action
metadata as `next_action` and normalizes it into the Candidate A-compatible
`nextAction` field. Existing `nextAction` remains the first source, while the
alias is removed from projected decision rows so neutral inputs do not change
the public response key shape.

`tests/unit/test_application_board_read_model_service.py` records this baseline
with `test_task_board_projection_accepts_active_decision_next_action_alias`, so
future Candidate A read-path equivalence work can compare active decision rows
before touching `blackboard_lite.py`.

Boundary confirmation for this baseline:

- no production path switch
- no dispatcher loop changes
- no `CTFState` ownership split
- no `CTFVerifier` proof behavior changes
- no ToolExecutor changes
- no WorkerPool/CrewOrchestrator changes
- no MCP production wiring
- no proof authority behavior changes

### Candidate A neutral decision driver alias baseline

Status: active decision driver alias fixture added before any production path switch.

`build_task_board_projection` now accepts neutral active decision driver
metadata as `decision_driver` and normalizes it into the Candidate A-compatible
`driver` field. Existing `driver` remains the first source, while the alias is
removed from projected decision rows so neutral inputs do not change the public
response key shape.

`tests/unit/test_application_board_read_model_service.py` records this baseline
with `test_task_board_projection_accepts_active_decision_driver_alias`, so
future Candidate A read-path equivalence work can compare active decision
driver rows before touching `blackboard_lite.py`.

Boundary confirmation for this baseline:

- no production path switch
- no dispatcher loop changes
- no `CTFState` ownership split
- no `CTFVerifier` proof behavior changes
- no ToolExecutor changes
- no WorkerPool/CrewOrchestrator changes
- no MCP production wiring
- no proof authority behavior changes

### Candidate A neutral decision kind alias baseline

Status: active decision kind alias fixture added before any production path switch.

`build_task_board_projection` now accepts neutral active decision kind metadata
as `decision_kind` and normalizes it into the Candidate A-compatible
`decisionKind` field. Existing `decisionKind` remains the first source, while
the alias is removed from projected decision rows so neutral inputs do not
change the public response key shape.

`tests/unit/test_application_board_read_model_service.py` records this baseline
with `test_task_board_projection_accepts_active_decision_kind_alias`, so future
Candidate A read-path equivalence work can compare active decision kind rows
before touching `blackboard_lite.py`.

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
- `flaghunter.eval`
- `flaghunter.interface`
- `flaghunter.knowledge`
- `flaghunter.llm`
- `flaghunter.mcp`
- `flaghunter.playbooks`
- `flaghunter.redteam`
- `flaghunter.runtime`
- `flaghunter.session`
- `flaghunter.tools`
- `flaghunter.workspaces`

This guard keeps `flaghunter/ports` from reaching outward into adapters,
application services, production configuration, legacy feature modules,
evaluation harnesses, red-team legacy helpers, playbooks, model/runtime code,
presentation, MCP, tools, sessions, or workspace helpers before explicit
production-wiring approval.

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

### Ports source guard coverage completeness guard

Status: aggregate coverage completeness guard added for protocol-only ports.

`tests/unit/test_ports_contracts.py` now requires the ports source guard record
to keep all ports boundary guard groups visible together:

- `Ports production wiring source guard`
- `Ports outer-layer import coverage guard`
- `Ports action sink coverage guard`
- `Ports proof action coverage guard`
- `Public surface domain-neutral naming coverage guard`

This aggregate guard prevents ports boundary coverage from drifting into
partial protection. Ports must keep production wiring surfaces, outer-layer
imports, action sinks, proof authority calls, and public neutral naming guarded
as one complete protocol-only boundary.

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
- `flaghunter.eval`
- `flaghunter.interface`
- `flaghunter.knowledge`
- `flaghunter.llm`
- `flaghunter.mcp`
- `flaghunter.playbooks`
- `flaghunter.redteam`
- `flaghunter.runtime`
- `flaghunter.session`
- `flaghunter.tools`
- `flaghunter.workspaces`

This guard keeps `flaghunter/application/challenge` as a use-case layer that
depends only on neutral contracts and ports, and prevents future service slices
from reaching outward into adapters, legacy feature modules, evaluation
harnesses, red-team legacy helpers, playbooks, production configuration,
model/runtime code, presentation, MCP, tools, sessions, or workspace helpers
before explicit production-wiring approval.

Boundary confirmation for this guard:

- no production behavior changes
- no concrete adapter construction
- no composition root changes
- no MCP production wiring
- no dispatcher loop changes
- no runtime construction
- no ToolExecutor changes
- no proof authority behavior changes

#### Specific application service source guard import coverage consistency guard

Status: focused application-service source guard import coverage consistency
added for individual application service tests.

`tests/unit/test_application_service_source_guards.py` now requires every
`tests/unit/test_application_*_service.py` focused source guard to cover the
outer legacy evaluation and red-team helper packages:

- `flaghunter.eval`
- `flaghunter.redteam`

This guard keeps single-service focused tests consistent with the package-level
application service boundary guard, so running an individual application
service test still blocks accidental imports from evaluation harnesses or
red-team legacy helpers.

Boundary confirmation for this guard:

- no production behavior changes
- no concrete adapter construction
- no composition root changes
- no MCP production wiring
- no dispatcher loop changes
- no runtime construction
- no ToolExecutor changes
- no proof authority behavior changes

#### Application service source guard coverage completeness guard

Status: aggregate coverage completeness guard added for neutral application
services.

`tests/unit/test_application_service_source_guards.py` now requires the
application-service source guard record to keep all application boundary guard
groups visible together:

- `Application service side-effect sink coverage guard`
- `Application service proof action coverage guard`
- `Application service production wiring source guard`
- `Application service outer-layer import coverage guard`
- `Specific application service source guard import coverage consistency guard`
- `Public surface domain-neutral naming coverage guard`

This aggregate guard prevents application-service boundary coverage from
drifting into partial protection. Application services must keep side-effect
sinks, proof authority surfaces, production wiring names, outer-layer imports,
focused service-test import coverage, and public neutral naming guarded as one
complete use-case boundary.

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
- `flaghunter.eval`
- `flaghunter.interface`
- `flaghunter.knowledge`
- `flaghunter.llm`
- `flaghunter.mcp.server`
- `flaghunter.playbooks`
- `flaghunter.ports`
- `flaghunter.redteam`
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
- `flaghunter.eval`
- `flaghunter.interface`
- `flaghunter.knowledge`
- `flaghunter.llm`
- `flaghunter.mcp.server`
- `flaghunter.playbooks`
- `flaghunter.redteam`
- `flaghunter.runtime`
- `flaghunter.session`
- `flaghunter.tools`
- `flaghunter.workspaces`

The application-service contract forbids these outer layers:

- `flaghunter.adapters`
- `flaghunter.agents`
- `flaghunter.config`
- `flaghunter.cpa_modules`
- `flaghunter.eval`
- `flaghunter.interface`
- `flaghunter.knowledge`
- `flaghunter.llm`
- `flaghunter.mcp.server`
- `flaghunter.playbooks`
- `flaghunter.redteam`
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

### Core import-linter coverage completeness guard

Status: aggregate coverage completeness guard added for core import-linter
contracts.

`tests/unit/test_import_layers.py` now requires the import-linter coverage
record to stay linked to the source-guard completeness records for the neutral
core layers:

- `Domain contract source guard coverage completeness guard`
- `Ports source guard coverage completeness guard`
- `Application service source guard coverage completeness guard`

The import-linter contract names must remain visible in the same governance
record:

- `domain-contract-independence`
- `ports-contract-boundary`
- `application-service-boundary`

This aggregate guard prevents the `.importlinter` architecture gate from
drifting away from the AST/source guards that cover production wiring surfaces,
outer-layer imports, side-effect sinks, proof authority surfaces, and neutral
public naming for domain contracts, ports, and application services.

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

Status: retired by Task ingress production wiring A landing for MCP task submission only.

`tests/unit/mcp/test_mcp_ingress_mode_contract.py` now guards the production
MCP server package so only `flaghunter/mcp/server/mcp_tools.py` may import and
construct `SubmitTaskIngress` for MCP run_task/run_task_async task submission
ingress after explicit production wiring A approval.

Required gate for any further MCP task execution wiring: explicit production
wiring approval.

This guard keeps the task ingress adapter, port, and other MCP server files
unwired. Production wiring A is limited to calling the neutral application
service at task submission time; it does not change MCP routing, task
execution driving, agent construction, or dispatcher behavior.

Boundary confirmation for this baseline:

- MCP run_task/run_task_async task submission ingress only
- no MCP router changes
- no `_drive_task` changes
- no `_make_agent` changes
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

Status: retired by Task ingress production wiring A for the approved MCP task submission entrypoint only.

`tests/unit/test_task_ingress_production_wiring_guards.py` now guards
interface, MCP, agents, tools, runtime, session, workspaces, and config
production entrypoint packages against importing or constructing task ingress
adapter, service, or port wiring outside the approved
`flaghunter/mcp/server/mcp_tools.py` run_task/run_task_async task submission
ingress slice and the approved `flaghunter/interface/web_server.py` post_task
task creation ingress slice.

Required gate for any further production entrypoint wiring: explicit production
wiring approval.

This guard keeps task ingress production wiring A/B from expanding into CLI,
TUI, other Web handlers, other MCP server files, dispatcher, tool executor,
runtime, session, workspace, or configuration paths.

Boundary confirmation for this baseline:

- MCP run_task/run_task_async task submission ingress only
- Web post_task task creation ingress only
- no CLI/TUI production wiring
- no MCP router changes
- no `_drive_task` changes
- no `_make_agent` changes
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

#### Task ingress production entry file coverage guard

Status: explicit production entry file coverage guard added before task
ingress production wiring approval.

`tests/unit/test_task_ingress_production_wiring_guards.py` now requires the
production entrypoint pre-wiring guard to explicitly scan top-level production
entry files where task ingress wiring could otherwise bypass package-root
scans:

- `flaghunter/__main__.py`
- `flaghunter/hooks.py`
- `flaghunter/logging_config.py`
- `flaghunter/observability.py`
- `flaghunter/task_registry.py`

This guard keeps future task ingress adapter/service/port wiring checks from
missing package command entry, startup hook, logging, observability, or task
registry entry files.

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

#### Task ingress production pre-wiring coverage completeness guard

Status: aggregate coverage completeness guard added before task ingress
production wiring approval.

`tests/unit/test_task_ingress_production_wiring_guards.py` now requires the
task ingress production pre-wiring record to keep every pre-approval guard
surface visible together:

- `Task ingress MCP pre-wiring guard baseline`
- `Task ingress production entrypoint pre-wiring guard baseline`
- `Task ingress production entry root coverage guard`
- `Task ingress production entry file coverage guard`
- `Task ingress production wiring token coverage guard`

This aggregate guard prevents task ingress production wiring protection from
drifting into partial coverage. Task ingress adapter, port, and application
service skeletons must remain unwired from MCP, production entry roots,
top-level entry files, and concrete wiring tokens until explicit production
wiring approval lands.

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

#### Task ingress production wiring A implementation landing record

Status: implementation landed for MCP task submission ingress only.

Current approval fact:

- Task ingress production wiring A: implementation landed

Target:

- `flaghunter/mcp/server/mcp_tools.py::run_task`
- `flaghunter/mcp/server/mcp_tools.py::run_task_async`

Implementation summary:

- MCP `run_task` and `run_task_async` now submit task ingress through the
  neutral `SubmitTaskIngress` application service after the task entry, mode
  contract, local asset contract, resume contract, and CTF run artifacts are
  prepared.
- The ingress service call preserves raw task instructions as `instructions`
  and uses task metadata only for entrypoint, mode subtype, and goal style.
- The service result is not surfaced in MCP response text and is not used to
  drive execution, so external MCP response shape, task entry behavior,
  `ingressHandoff`, control decision, blocked behavior, and async scheduling
  stay compatible.

Equivalence evidence:

- `tests/unit/mcp/test_mcp_ingress_mode_contract.py::test_mcp_run_task_and_async_submit_neutral_ingress_without_response_drift`
  proves both MCP task submission entrypoints call `SubmitTaskIngress`, keep
  raw instructions, keep run ids, and do not add ingress text to external MCP
  responses.
- `tests/unit/mcp/test_mcp_ingress_mode_contract.py::test_mcp_task_submission_ingress_wiring_uses_application_service_after_approval`
  proves only the application service is wired and that `_drive_task` and
  `_make_agent` are not part of the ingress helper.
- `tests/unit/test_task_ingress_production_wiring_guards.py` allows only this
  MCP submission service wiring while keeping adapter/port wiring and every
  other production entrypoint guarded.

Rollback command:

- `git revert <Task ingress production wiring A implementation commit>`

Boundary confirmation for this landing:

- no MCP router changes
- no `_drive_task` changes
- no `_make_agent` changes
- no Web/CLI/TUI production wiring
- no ToolExecutor changes
- no `CTFVerifier` proof behavior changes
- no `CTFState` ownership split
- no `CTFTaskDispatcher` flow changes
- no composition root changes
- no proof authority behavior changes
- no P5 implementation
- no crew/recovery changes

#### Task ingress production wiring B implementation landing record

Status: implementation landed for Web post_task task creation ingress only.

Current approval fact:

- Task ingress production wiring B: implementation landed

Target:

- `flaghunter/interface/web_server.py::post_task`

Implementation summary:

- Web `POST /api/tasks` now submits task creation ingress through the neutral
  `SubmitTaskIngress` application service after the task dict, mode contract,
  local asset contract, effective goal, control decision, and `ingressHandoff`
  are prepared.
- The ingress service call preserves the task goal/title/target as raw
  `instructions` and uses task metadata only for entrypoint, mode subtype, and
  goal style.
- The service result is not surfaced in Web response JSON and is not used to
  drive execution, so Web external response shape, task dict behavior,
  `ingressHandoff`, control decision, blocked behavior, and background-thread
  scheduling stay compatible.

Equivalence evidence:

- `tests/unit/interface/test_web_server.py::test_post_task_submits_neutral_ingress_without_response_or_thread_drift`
  proves Web task creation calls `SubmitTaskIngress`, keeps raw instructions,
  keeps run ids, does not add ingress fields to the external response, and
  preserves background-thread scheduling for runnable tasks.
- `tests/unit/interface/test_web_server.py::test_post_task_blocked_path_submits_ingress_without_starting_thread`
  proves blocked task creation still records ingress while preserving blocked
  status and no background thread.
- `tests/unit/interface/test_web_server.py::test_web_task_submission_ingress_wiring_uses_application_service_after_approval`
  records the approved Web service wiring.
- `tests/unit/test_task_ingress_production_wiring_guards.py` allows only the
  approved MCP A and Web B service wiring while keeping adapter/port wiring and
  every other production entrypoint guarded.

Rollback command:

- `git revert <Task ingress production wiring B implementation commit>`

Boundary confirmation for this landing:

- no MCP follow-up changes
- no MCP router changes
- no `_drive_task` changes
- no `_make_agent` changes
- no CLI/TUI production wiring
- no other Web handler production wiring
- no ToolExecutor changes
- no `CTFVerifier` proof behavior changes
- no `CTFState` ownership split
- no `CTFTaskDispatcher` flow changes
- no composition root changes
- no proof authority behavior changes
- no P5 implementation
- no crew/recovery changes

#### Task ingress remaining entrypoint denial guard

Status: remaining entrypoint denial guard recorded, no new production wiring approved.

After Task ingress production wiring A and B, only the two approved task
submission helper scopes may construct `SubmitTaskIngress`:

- `flaghunter/mcp/server/mcp_tools.py::_submit_task_ingress`
- `flaghunter/interface/web_server.py::_submit_web_task_ingress`

`tests/unit/test_task_ingress_production_wiring_guards.py::test_task_ingress_remaining_entrypoints_stay_unwired_after_a_and_b`
now locks those call scopes and keeps all remaining entrypoints not approved.

Denied surfaces remain:

- `MCPRouter`
- `_drive_task`
- `_make_agent`
- CLI/TUI
- other Web handler
- composition root

This guard prevents the partial Task ingress production wiring approval from
drifting into MCP router wiring, MCP task execution wiring, CLI/TUI task
creation, broader Web handlers, or composition-root assembly by implication.

Boundary confirmation for this guard:

- no new production wiring
- no MCP router changes
- no `_drive_task` changes
- no `_make_agent` changes
- no CLI/TUI production wiring
- no other Web handler production wiring
- no ToolExecutor changes
- no `CTFVerifier` proof behavior changes
- no `CTFState` ownership split
- no `CTFTaskDispatcher` flow changes
- no composition root changes
- no proof authority behavior changes
- no P5 implementation
- no crew/recovery changes

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

Status: implementation approved and landed.

This plan covered the focused migration that lets
`SubmitTaskIngress` use the neutral task ingress domain contracts internally
while preserving its current external behavior and injected port payload
compatibility.

File list for the implementation slice:

- `flaghunter/application/challenge/task_ingress_service.py`
- `tests/unit/test_application_task_ingress_service.py`
- `tests/unit/test_application_service_source_guards.py`
- `tests/unit/test_task_ingress_adapter.py`
- `tests/unit/test_clean_architecture_migration_playbook.py`

risk: low-medium, because service output shape and ingress port payload compatibility could change if the service switches from the current raw mapping payload to neutral contract serialization without a compatibility check.

rollback point: revert the single service migration commit.

Required behavior for the implementation slice:

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

Required verification for the implementation slice:

```powershell
.\.venv\Scripts\python.exe -m pytest tests/unit/test_application_task_ingress_service.py -q
.\.venv\Scripts\python.exe -m pytest tests/unit/test_task_ingress_adapter.py -q
.\.venv\Scripts\python.exe -m pytest tests/unit/test_import_layers.py tests/unit/test_ports_contracts.py tests/unit/test_domain_challenge_contracts.py tests/unit/test_task_ingress_production_wiring_guards.py -q
git diff --check
```

### Task ingress service contract migration pre-approval guard

Status: retired by task ingress service contract migration landing.

`tests/unit/test_application_task_ingress_service.py` now guards
`flaghunter/application/challenge/task_ingress_service.py` to require the
neutral task ingress domain contract classes after the approved service
contract migration landed.

Required after landing:

- import `flaghunter.domain.challenge.contracts.task_ingress`
- construct or reference `TaskIngressRequest`
- construct or reference `TaskIngressReceipt`
- construct or reference `TaskIngressReadback`
- keep the current injected port request payload shape
- preserve raw `instructions` in the injected port request payload

This guard was updated in the same service migration commit that
preserves current external response shape, preserves injected port compatibility
or explicitly versions the payload, and runs the verification commands recorded
in the service contract migration plan.

Boundary confirmation for this landing guard:

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

Status: implementation landed after explicit approval.

Readiness evidence already recorded:

- Task ingress application service skeleton baseline
- Task ingress domain contract skeleton baseline
- Task ingress readback contract skeleton baseline
- Task ingress service contract migration plan
- Task ingress service contract migration pre-approval guard retired by landing

Representative behavior evidence preserved by the implementation:

- `test_submit_returns_pending_payload_without_ingress_port`
- `test_submit_delegates_to_task_ingress_port_only`
- `test_submit_accepts_minimal_empty_values`
- `test_task_ingress_service_contract_migration_landing_guard`

Implementation landing constraints satisfied:

- explicit approval was granted before editing `flaghunter/application/challenge/task_ingress_service.py`
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

### Post read-side core decoupling approval queue

Status: approval queue recorded, implementation not approved by this section.

Web read paths and Deferred MCP readback are landed. The next migration work
must move from read-side projection cleanup into service, wiring, and core
production decoupling only through explicit per-candidate approval. This section
does not approve implementation; it orders the next review gates and keeps the
high-risk core surfaces separated.

| Candidate | Risk tier | Current status | Implementation approved | Required approval | Required verification |
|-----------|-----------|----------------|-------------------------|-------------------|-----------------------|
| Task ingress service contract migration | low-medium | implementation landed | true | explicit service migration approval granted | application service focused, adapter focused, architecture/source guards, production pre-wiring guards, `git diff --check` |
| Task ingress production wiring | high | A and B landed; remaining entrypoints not approved | partial | explicit production wiring approval per entrypoint family | MCP/entrypoint wiring focused, task ingress guards, architecture/source guards, `git diff --check` |
| Verifier/proof authority boundary | high | not approved | false | explicit proof-authority approval | verifier fixture, proof authority invariants, P1 claim invariants, source guards, `git diff --check` |
| State ownership split | high | not approved | false | explicit state ownership split approval | state snapshot fixtures, replay/readback fixtures, import/source guards, `git diff --check` |
| ToolExecutor side-effect split | high | not approved | false | explicit ToolExecutor side-effect split approval | tool receipt fixtures, executor guard fixtures, finish control receipt, architecture/source guards, `git diff --check` |
| Dispatcher/composition root production wiring | maximum | not approved | false | explicit dispatcher and composition-root approval | dispatcher focused, entrypoint focused, MCP/web/CLI smoke guards, architecture/source guards, `git diff --check` |

Queue rules:

- one functional point per commit
- no bundled core edits
- no approval by implication
- no MCP task execution wiring without explicit production wiring approval
- no ToolExecutor changes without ToolExecutor-specific approval
- no Verifier/proof authority behavior changes without proof-authority approval
- no CTFState ownership split without state-specific approval
- no CTFTaskDispatcher flow changes without dispatcher-specific approval
- no composition root changes without composition-root approval
- no P5 implementation
- rollback point is always the single implementation commit for the approved
  candidate

#### Verifier/proof authority boundary approval plan

Status: approval plan recorded, implementation not approved.

Purpose:

- Prepare the first high-risk proof-authority review package after the
  read-side, MCP readback, and task-ingress slices landed.
- Keep proof-authority writes stay in verifier-owned code until explicitly migrated behind neutral contracts, ports, adapters, or application services.
- Make the next implementation review concrete without granting approval by
  implication.

Candidate scope for a future approved implementation:

- `flaghunter/agents/pa_agent/verifier.py`
- `flaghunter/agents/pa_agent/ctf_state.py`
- `tests/unit/agents/test_p1_claim_invariants.py`
- `tests/unit/test_verifier_adapter.py`
- playbook governance records for the single approved proof-authority slice

Current proof-authority surfaces that require explicit review:

- `upgrade_claim_to_verified`
- `append_verification_record`
- `record_verification_receipt`
- `verified_flags`
- `VerificationDecision.VERIFIED`

Required approval:

- explicit proof-authority approval required before implementation
- one proof-authority functional point per commit
- no status-only approval without matching implementation evidence
- rollback point: revert the single approved proof-authority implementation commit

Readiness evidence currently available:

- Proof authority characterization readiness aggregate
- Proof authority write surface characterization guard
- Verified decision reference characterization guard
- Proof authority port action unwired guard
- Proof authority adapter import unwired guard
- Verifier adapter import unwired guard

The readiness aggregate is approval package evidence, not implementation approval.

Required verification for a future approved implementation:

```powershell
.\.venv\Scripts\python.exe -m pytest tests/unit/agents/test_p1_claim_invariants.py tests/unit/test_verifier_adapter.py -q
.\.venv\Scripts\python.exe -m pytest tests/unit/test_import_layers.py tests/unit/agents/test_p1_source_guards.py tests/unit/test_ports_contracts.py tests/unit/test_domain_challenge_contracts.py tests/unit/test_adapter_boundary_skeleton.py tests/unit/test_proof_authority_adapter.py -q
git diff --check
```

Boundary confirmation for this approval plan:

- no implementation approval by this section
- no ToolExecutor changes
- no `CTFState` ownership split
- no `CTFTaskDispatcher` flow changes
- no MCP production wiring
- no Web/CLI/TUI task wiring changes
- no composition root changes
- no P5 implementation
- no crew/recovery changes

#### State ownership split approval plan

Status: approval plan recorded, implementation not approved.

Purpose:

- Prepare the first high-risk state ownership review package after read-side,
  task-ingress, and proof-authority approval planning.
- Keep state ownership stays in legacy CTFState until explicitly migrated
  behind neutral state, claim, evidence, proof, artifact, checkpoint, or read
  model contracts.
- Make state-store adapter substitution evidence concrete without granting
  production state split approval by implication.

Candidate scope for a future approved implementation:

- `flaghunter/agents/pa_agent/ctf_state.py`
- `flaghunter/adapters/state/state_store_adapter.py`
- `tests/unit/test_state_store_adapter.py`
- `tests/unit/agents/test_p1_claim_invariants.py`
- `tests/unit/agents/test_p4_task_dag_replay_audit_bundle.py`
- playbook governance records for the single approved state ownership slice

Current state ownership surfaces that require explicit review:

- `claims_by_id`
- `verification_records_by_id`
- `execution_traces_by_id`
- `to_snapshot`
- `from_snapshot`
- `add_flag`
- `create_claim`

Required approval:

- explicit state ownership split approval required before implementation
- one state ownership functional point per commit
- no status-only approval without matching implementation evidence
- rollback point: revert the single approved state ownership implementation commit

Required verification for a future approved implementation:

```powershell
.\.venv\Scripts\python.exe -m pytest tests/unit/test_state_store_adapter.py tests/unit/agents/test_p1_claim_invariants.py tests/unit/agents/test_p4_task_dag_replay_audit_bundle.py -q
.\.venv\Scripts\python.exe -m pytest tests/unit/test_import_layers.py tests/unit/agents/test_p1_source_guards.py tests/unit/test_ports_contracts.py tests/unit/test_domain_challenge_contracts.py tests/unit/test_adapter_boundary_skeleton.py -q
git diff --check
```

Boundary confirmation for this approval plan:

- no implementation approval by this section
- no proof-authority behavior changes
- no ToolExecutor changes
- no `CTFTaskDispatcher` flow changes
- no MCP production wiring
- no Web/CLI/TUI task wiring changes
- no composition root changes
- no P5 implementation
- no crew/recovery changes

#### CTFState legacy construction characterization guard

Status: characterization guard recorded, no state ownership changed.

`tests/unit/agents/test_p1_source_guards.py::test_p1_ctf_state_construction_stays_in_current_legacy_surfaces`
now locks the current legacy `CTFState` direct construction and snapshot
restoration surfaces before any state-store ownership split, dispatcher
rewiring, or composition-root migration.

Current allowed direct construction surfaces:

- `flaghunter/agents/pa_agent/coordinator.py` -> `CTFCoordinator._bootstrap_dispatcher`
- `flaghunter/agents/pa_agent/ctf_crew_runner.py` -> `run_ctf_crew_solve`
- `flaghunter/interface/tui_ctf_apply.py` -> `CtfApplyMixin._rebuild_override_stop_report`
- `flaghunter/interface/tui_ctf_apply.py` -> `CtfApplyMixin._rebuild_wrong_flag_stop_report`
- `flaghunter/interface/tui_ctf_runners.py` -> `CtfRunnerMixin._run_ctf_crew_dispatcher_mode`

Current allowed snapshot restoration surfaces:

- `flaghunter/agents/pa_agent/ctf_dispatcher.py` -> `CTFTaskDispatcher._restore_context` -> `CTFState.from_snapshot`
- `flaghunter/agents/pa_agent/session_context.py` -> `SessionContextView.build_run_context` -> `CTFState.from_snapshot`
- `flaghunter/agents/pa_agent/session_context.py` -> `SessionContextView.build_blackboard_view` -> `CTFState.from_snapshot`
- `flaghunter/interface/blackboard_lite.py` -> `_snapshot_from_state_payload` -> `CTFState.from_snapshot`

This confirms legacy state construction and snapshot restoration remain characterized.
It does not approve a state ownership split, state-store production wiring, or
composition-root migration.

Boundary confirmation for this guard:

- no state ownership split
- no proof-authority behavior changes
- no ToolExecutor changes
- no `CTFTaskDispatcher` flow changes
- no MCP production wiring
- no Web/CLI/TUI task wiring changes
- no composition root changes
- no P5 implementation
- no crew/recovery changes

#### State ownership first slice approval text template

Status: approval text template recorded, implementation not approved by this section.

Copyable approval text for the recommended state boundary first slice:

```text
批准 State ownership split 第一刀：
candidate: State ownership split
first slice: state snapshot or claim-store ownership characterization with no storage ownership migration
scope: state boundary characterization only
rollback: revert the single implementation commit
readiness evidence: CTFState legacy construction characterization guard reviewed
landing evidence: required
独立 TDD、独立 commit/push。
禁止 CTFState ownership migration。
禁止 CTFVerifier decision behavior change。
禁止 proof authority behavior change。
禁止 Dispatcher、ToolExecutor、MCP production wiring、Web/CLI/TUI task wiring、composition root、P5、crew/recovery。
```

Recommended first slice:

- one state snapshot or claim-store ownership characterization seam
- no mutation ownership transfer
- no proof upgrade authority movement
- no production construction or composition-root wiring

Approval text invariants:

- this template is not approval by itself
- approval must be sent as a user message
- state-store adapter evidence does not approve production state ownership migration
- state ownership work must not move proof upgrade authority
- state ownership work must remain downstream of the proof/verifier boundary guards

Required verification for a future approved state first slice:

```powershell
.\.venv\Scripts\python.exe -m pytest tests/unit/test_state_store_adapter.py tests/unit/agents/test_p1_claim_invariants.py tests/unit/agents/test_p4_task_dag_replay_audit_bundle.py -q
.\.venv\Scripts\python.exe -m pytest tests/unit/test_import_layers.py tests/unit/agents/test_p1_source_guards.py tests/unit/test_ports_contracts.py tests/unit/test_domain_challenge_contracts.py tests/unit/test_adapter_boundary_skeleton.py tests/unit/test_clean_architecture_migration_playbook.py -q
git diff --check
```

Boundary confirmation for this template:

- no implementation approval by this section
- no state ownership split
- no proof-authority behavior changes
- no verifier decision behavior changes
- no ToolExecutor changes
- no `CTFTaskDispatcher` flow changes
- no MCP production wiring
- no Web/CLI/TUI task wiring changes
- no composition root changes
- no P5 implementation
- no crew/recovery changes

#### ToolExecutor side-effect split approval plan

Status: approval plan recorded, implementation not approved.

Purpose:

- Prepare the first high-risk ToolExecutor side-effect review package after
  read-side, task-ingress, proof-authority, and state ownership approval
  planning.
- Keep tool execution side effects stay in legacy ToolExecutor until explicitly migrated behind neutral tool receipt, tool runner, runtime action, audit, artifact, or checkpoint contracts.
- Make tool-runner adapter and tool-receipt service evidence concrete without
  granting production executor split approval by implication.

Candidate scope for a future approved implementation:

- `flaghunter/tools/executor.py`
- `flaghunter/adapters/tools/tool_runner_adapter.py`
- `tests/unit/tools/test_executor.py`
- `tests/unit/tools/test_executor_cookie_inject.py`
- `tests/unit/tools/test_finish_control_receipt.py`
- `tests/unit/test_application_tool_receipt_service.py`
- `tests/unit/test_tool_runner_adapter.py`
- playbook governance records for the single approved ToolExecutor slice

Current ToolExecutor side-effect surfaces that require explicit review:

- `execute`
- `execute_batch`
- `runtime`
- `scope check`
- `cookie auto-inject`
- `stealth mode`
- `flag scanning`
- `missing-tool detection`

Required approval:

- explicit ToolExecutor side-effect split approval required before implementation
- one ToolExecutor functional point per commit
- no status-only approval without matching implementation evidence
- rollback point: revert the single approved ToolExecutor implementation commit

Required verification for a future approved implementation:

```powershell
.\.venv\Scripts\python.exe -m pytest tests/unit/tools/test_executor.py tests/unit/tools/test_executor_cookie_inject.py tests/unit/tools/test_finish_control_receipt.py tests/unit/test_application_tool_receipt_service.py tests/unit/test_tool_runner_adapter.py -q
.\.venv\Scripts\python.exe -m pytest tests/unit/test_import_layers.py tests/unit/agents/test_p1_source_guards.py tests/unit/test_ports_contracts.py tests/unit/test_domain_challenge_contracts.py tests/unit/test_adapter_boundary_skeleton.py -q
git diff --check
```

Boundary confirmation for this approval plan:

- no implementation approval by this section
- no proof-authority behavior changes
- no `CTFState` ownership split
- no `CTFTaskDispatcher` flow changes
- no MCP production wiring
- no Web/CLI/TUI task wiring changes
- no composition root changes
- no P5 implementation
- no crew/recovery changes

#### ToolExecutor legacy construction characterization guard

Status: characterization guard recorded, no ToolExecutor behavior changed.

`tests/unit/agents/test_p1_source_guards.py::test_p1_tool_executor_construction_stays_in_base_agent_only`
now locks the current legacy `ToolExecutor` definition, package re-export, and
production construction surface before any ToolExecutor side-effect split,
tool-runner adapter wiring, or composition-root migration.

Current allowed definition and re-export surfaces:

- `flaghunter/tools/executor.py`
- `flaghunter/tools/__init__.py`
- `ToolExecutor`

Current allowed production construction surface:

- `flaghunter/agents/base_agent.py`
- `BaseAgent.__init__`
- `ToolExecutor`

This confirms BaseAgent construction remains the only production construction surface.
It does not approve a ToolExecutor side-effect split, tool-runner production
wiring, or composition-root migration.

Boundary confirmation for this guard:

- no ToolExecutor side-effect split
- no proof-authority behavior changes
- no `CTFState` ownership split
- no `CTFTaskDispatcher` flow changes
- no MCP production wiring
- no Web/CLI/TUI task wiring changes
- no composition root changes
- no P5 implementation
- no crew/recovery changes

#### ToolExecutor first slice approval text template

Status: approval text template recorded, implementation not approved by this section.

Copyable approval text for the recommended ToolExecutor boundary first slice:

```text
批准 ToolExecutor side-effect split 第一刀：
candidate: ToolExecutor side-effect split
first slice: tool receipt or tool-runner side-effect characterization with no executor production wiring
scope: ToolExecutor boundary characterization only
rollback: revert the single implementation commit
readiness evidence: ToolExecutor legacy construction characterization guard reviewed
landing evidence: required
独立 TDD、独立 commit/push。
禁止 ToolExecutor side-effect migration。
禁止 tool-runner production wiring。
禁止 runtime construction changes。
禁止 CTFState ownership migration。
禁止 proof authority behavior change。
禁止 Dispatcher、MCP production wiring、Web/CLI/TUI task wiring、composition root、P5、crew/recovery。
```

Recommended first slice:

- one tool receipt or tool-runner side-effect characterization seam
- no executor ownership transfer
- no runtime construction movement
- no production task execution wiring
- no proof or state ownership movement

Approval text invariants:

- this template is not approval by itself
- approval must be sent as a user message
- tool-runner adapter evidence does not approve production ToolExecutor migration
- ToolExecutor work must not move proof upgrade or state ownership authority
- ToolExecutor work must remain downstream of proof/verifier and state boundary guards

Required verification for a future approved ToolExecutor first slice:

```powershell
.\.venv\Scripts\python.exe -m pytest tests/unit/tools/test_executor.py tests/unit/tools/test_executor_cookie_inject.py tests/unit/tools/test_finish_control_receipt.py tests/unit/test_application_tool_receipt_service.py tests/unit/test_tool_runner_adapter.py -q
.\.venv\Scripts\python.exe -m pytest tests/unit/test_import_layers.py tests/unit/agents/test_p1_source_guards.py tests/unit/test_ports_contracts.py tests/unit/test_domain_challenge_contracts.py tests/unit/test_adapter_boundary_skeleton.py tests/unit/test_clean_architecture_migration_playbook.py -q
git diff --check
```

Boundary confirmation for this template:

- no implementation approval by this section
- no ToolExecutor side-effect split
- no tool-runner production wiring
- no runtime construction changes
- no proof-authority behavior changes
- no `CTFState` ownership split
- no `CTFTaskDispatcher` flow changes
- no MCP production wiring
- no Web/CLI/TUI task wiring changes
- no composition root changes
- no P5 implementation
- no crew/recovery changes

#### Dispatcher/composition root production wiring approval plan

Status: approval plan recorded, implementation not approved.

Purpose:

- Prepare the maximum-risk dispatcher and composition-root review package after
  read-side, task-ingress, proof-authority, state ownership, and ToolExecutor
  approval planning.
- Keep dispatcher and composition root wiring stay in legacy entrypoints until explicitly migrated behind neutral application services, ports, adapters, and an approved composition root.
- Make the future wiring route concrete without granting dispatcher flow,
  entrypoint behavior, or production assembly approval by implication.

Candidate scope for a future approved implementation:

- `flaghunter/agents/pa_agent/ctf_dispatcher.py`
- `flaghunter/session/initializer.py`
- `flaghunter/session/agent_session.py`
- `flaghunter/interface/cli.py`
- `flaghunter/interface/web_server.py`
- `flaghunter/mcp/server/mcp_tools.py`
- `tests/unit/agents/test_ctf_dispatcher.py`
- `tests/unit/session/test_agent_session.py`
- `tests/unit/interface/test_web_server.py`
- `tests/unit/mcp/test_mcp_ingress_mode_contract.py`
- playbook governance records for the single approved dispatcher/composition-root slice

Current dispatcher and composition-root surfaces that require explicit review:

- `CTFTaskDispatcher`
- `build_agent_components`
- `AgentSession.create`
- `run_task`
- `run_task_async`
- `post_task`
- `MCPRouter`

Required approval:

- explicit dispatcher and composition-root approval required before implementation
- one dispatcher/composition-root functional point per commit
- no status-only approval without matching implementation evidence
- rollback point: revert the single approved dispatcher/composition-root implementation commit

Required verification for a future approved implementation:

```powershell
.\.venv\Scripts\python.exe -m pytest tests/unit/session/test_agent_session.py tests/unit/interface/test_web_server.py tests/unit/mcp/test_mcp_ingress_mode_contract.py -q
.\.venv\Scripts\python.exe -m pytest tests/unit/agents/test_ctf_dispatcher.py tests/unit/test_import_layers.py tests/unit/agents/test_p1_source_guards.py -q
git diff --check
```

Boundary confirmation for this approval plan:

- no implementation approval by this section
- no proof-authority behavior changes
- no `CTFState` ownership split
- no ToolExecutor changes
- no MCP router changes
- no unapproved Web/CLI/TUI behavior changes
- no persisted schema compatibility changes
- no P5 implementation
- no crew/recovery changes

#### CTFTaskDispatcher legacy construction characterization guard

Status: characterization guard recorded, no dispatcher flow changed.

`tests/unit/agents/test_p1_source_guards.py::test_p1_ctf_task_dispatcher_construction_stays_in_current_legacy_entrypoints`
now locks the current legacy `CTFTaskDispatcher` definition and direct
construction surfaces before any dispatcher flow migration, entrypoint rewiring,
MCP task execution wiring change, or composition-root migration.

Current allowed definition surface:

- `flaghunter/agents/pa_agent/ctf_dispatcher.py`
- `CTFTaskDispatcher`

Current allowed construction surfaces:

- `flaghunter/agents/pa_agent/ctf_crew_runner.py` -> `run_ctf_crew_solve`
- `flaghunter/agents/pa_agent/ctf_crew_runner.py` -> `run_ctf_crew_solve._worker_runner`
- `flaghunter/eval/replay.py` -> `run_replay`
- `flaghunter/interface/cli.py` -> `run_cli`
- `flaghunter/interface/tui_ctf_runners.py` -> `CtfRunnerMixin._run_ctf_dispatcher_mode`
- `flaghunter/interface/tui_ctf_runners.py` -> `CtfRunnerMixin._run_ctf_crew_dispatcher_mode`
- `flaghunter/interface/tui_ctf_runners.py` -> `CtfRunnerMixin._run_ctf_crew_dispatcher_mode._worker_runner`
- `flaghunter/interface/web_server.py` -> `_run_agent_task._build_and_run`
- `flaghunter/mcp/server/mcp_tools.py` -> `_drive_task`

This confirms legacy entrypoints remain the only dispatcher construction surfaces.
It does not approve dispatcher flow changes, entrypoint behavior changes, MCP
production wiring changes, or composition-root migration.

Boundary confirmation for this guard:

- no dispatcher flow changes
- no composition root changes
- no MCP router changes
- no ToolExecutor changes
- no `CTFState` ownership split
- no proof-authority behavior changes
- no Web/CLI/TUI behavior changes
- no P5 implementation
- no crew/recovery changes

#### Dispatcher composition root first slice approval text template

Status: approval text template recorded, implementation not approved by this section.

Copyable approval text for the maximum-risk dispatcher/composition-root first slice:

```text
批准 Dispatcher/composition root production wiring 第一刀：
candidate: Dispatcher/composition root production wiring
first slice: composition-root characterization or wiring plan with no production entrypoint switch
scope: dispatcher/composition-root boundary characterization only
rollback: revert the single implementation commit
readiness evidence: CTFTaskDispatcher legacy construction characterization guard reviewed
landing evidence: required
独立 TDD、独立 commit/push。
禁止 CTFTaskDispatcher flow change。
禁止 composition root production wiring。
禁止 MCP/Web/CLI/TUI task execution path switch。
禁止 ToolExecutor side-effect migration。
禁止 CTFState ownership migration。
禁止 proof authority behavior change。
禁止 P5、crew/recovery。
```

Recommended first slice:

- composition-root wiring only after proof, state, and executor seams land
- no production entrypoint switch
- no dispatcher flow movement
- no MCP router or task execution wiring
- no proof, state, or executor ownership movement

Approval text invariants:

- this template is not approval by itself
- approval must be sent as a user message
- dispatcher/composition-root work must stay last until proof, state, and executor seams land
- composition-root planning does not approve production entrypoint wiring
- any future wiring slice must name one entrypoint family and one rollback commit

Required verification for a future approved dispatcher/composition-root first slice:

```powershell
.\.venv\Scripts\python.exe -m pytest tests/unit/session/test_agent_session.py tests/unit/interface/test_web_server.py tests/unit/mcp/test_mcp_ingress_mode_contract.py -q
.\.venv\Scripts\python.exe -m pytest tests/unit/agents/test_ctf_dispatcher.py tests/unit/test_import_layers.py tests/unit/agents/test_p1_source_guards.py tests/unit/test_clean_architecture_migration_playbook.py -q
git diff --check
```

Boundary confirmation for this template:

- no implementation approval by this section
- no dispatcher flow changes
- no composition root production wiring
- no MCP router changes
- no MCP/Web/CLI/TUI task execution path switch
- no ToolExecutor side-effect split
- no `CTFState` ownership split
- no proof-authority behavior changes
- no P5 implementation
- no crew/recovery changes

#### Core production approval package aggregate guard

Status: aggregate guard recorded, implementation not approved by this section.

The four core production approval packages are now recorded, but approval packages do not grant implementation approval. This aggregate guard keeps their status aligned with the post read-side approval queue and prevents no approval by implication drift before explicit human approval lands.

| Core candidate | Approval package | Readiness evidence | Implementation approved | Current implementation state |
|----------------|------------------|--------------------|-------------------------|------------------------------|
| Verifier/proof authority boundary | `Verifier/proof authority boundary approval plan` | `Proof authority characterization readiness aggregate` | false | not approved |
| State ownership split | `State ownership split approval plan` | `CTFState legacy construction characterization guard` | false | not approved |
| ToolExecutor side-effect split | `ToolExecutor side-effect split approval plan` | `ToolExecutor legacy construction characterization guard` | false | not approved |
| Dispatcher/composition root production wiring | `Dispatcher/composition root production wiring approval plan` | `CTFTaskDispatcher legacy construction characterization guard` | false | not approved |

Required aggregate invariants:

- every core package must remain implementation approved = false until explicit human approval lands
- approval package status must not be used as implementation approval
- readiness evidence must not be used as implementation approval
- each future implementation must update exactly one package and add a landing record
- rollback point remains the single approved implementation commit

Required verification for this aggregate guard:

```powershell
.\.venv\Scripts\python.exe -m pytest tests/unit/test_clean_architecture_migration_playbook.py -q
git diff --check
```

Boundary confirmation for this aggregate guard:

- no implementation approval by this section
- no proof-authority behavior changes
- no `CTFState` ownership split
- no ToolExecutor changes
- no `CTFTaskDispatcher` flow changes
- no MCP production wiring
- no Web/CLI/TUI task wiring changes
- no composition root changes
- no P5 implementation
- no crew/recovery changes

#### Core approval queue aggregate consistency guard

Status: queue aggregate consistency guard recorded, implementation not approved by this section.

The post read-side core decoupling approval queue and the core production
approval package aggregate guard describe the same four high-risk candidates.
Their queue rows and aggregate rows must stay aligned before any core
implementation approval can land.

Required approval text copied from the queue:

- explicit proof-authority approval
- explicit state ownership split approval
- explicit ToolExecutor side-effect split approval
- explicit dispatcher and composition-root approval

Required verification families copied from the queue:

- verifier fixture, proof authority invariants, P1 claim invariants, source guards, `git diff --check`
- state snapshot fixtures, replay/readback fixtures, import/source guards, `git diff --check`
- tool receipt fixtures, executor guard fixtures, finish control receipt, architecture/source guards, `git diff --check`
- dispatcher focused, entrypoint focused, MCP/web/CLI smoke guards, architecture/source guards, `git diff --check`

Required aggregate invariants:

- queue rows and aggregate rows must stay aligned
- required approval text must remain visible before implementation
- required verification text must remain visible before implementation
- no core implementation approval may be inferred from either table alone

Boundary confirmation for this consistency guard:

- no implementation approval by this section
- no proof-authority behavior changes
- no `CTFState` ownership split
- no ToolExecutor changes
- no `CTFTaskDispatcher` flow changes
- no MCP production wiring
- no Web/CLI/TUI task wiring changes
- no composition root changes
- no P5 implementation
- no crew/recovery changes

#### Core implementation landing evidence template

Status: landing evidence template recorded, no core implementation approved by this section.

Any future approved core implementation must add a candidate-specific landing record in the same commit as the implementation. This template applies only after explicit approval for one core candidate is granted.

Eligible core candidates:

- Verifier/proof authority boundary
- State ownership split
- ToolExecutor side-effect split
- Dispatcher/composition root production wiring

Required landing record fields:

- core candidate
- implementation commit SHA
- approved scope
- readiness evidence reviewed
- files changed
- red test evidence
- focused regression result
- architecture/source-guard result
- git diff --check result
- post-push branch status
- rollback command
- boundary confirmation

Required verification for this template:

```powershell
.\.venv\Scripts\python.exe -m pytest tests/unit/test_clean_architecture_migration_playbook.py -q
git diff --check
```

Boundary confirmation for this landing template:

- no implementation approval by this template
- one core functional point per commit
- no bundled proof, state, executor, dispatcher, composition-root, MCP, and entrypoint changes
- readiness evidence must match the core aggregate row for the approved candidate
- rollback command must use the real implementation commit SHA

#### Core first implementation slice recommendation

Status: recommendation recorded, implementation not approved by this section.

Recommended first approval review: Verifier/proof authority boundary.

Dispatcher/composition root production wiring remains last because it can
transitively touch entrypoints, dispatcher flow, state ownership, proof
authority, executor side effects, and MCP/Web/CLI/TUI behavior at once.

| Order | Core candidate | First approved slice to request | Why this order | Implementation approved |
|-------|----------------|---------------------------------|----------------|-------------------------|
| 1 | Verifier/proof authority boundary | proof-authority boundary characterization or adapter wrapper with no decision behavior change | it owns the accepted-proof authority rule and has focused invariants already present | false |
| 2 | State ownership split | one state snapshot or claim-store ownership seam after proof authority review | state ownership should not move before proof upgrade authority is pinned | false |
| 3 | ToolExecutor side-effect split | one tool receipt or tool-runner side-effect seam after proof and state seams land | tool execution emits artifacts and receipts that should target stable proof/state boundaries | false |
| 4 | Dispatcher/composition root production wiring | composition-root wiring only after proof, state, and executor seams land | dispatcher and entrypoint wiring has the widest blast radius and should remain last | false |

Required recommendation invariants:

- recommendation does not approve implementation
- human approval must name exactly one core candidate and one first slice
- dispatcher/composition root work must stay last until narrower core seams land

#### Core first slice approval text template

Status: approval text template recorded, implementation not approved by this section.

Copyable approval text for the recommended first slice:

```text
批准 Verifier/proof authority boundary 第一刀：
candidate: Verifier/proof authority boundary
first slice: proof-authority boundary characterization or adapter wrapper with no decision behavior change
scope: verifier/proof-authority boundary only
rollback: revert the single implementation commit
readiness evidence: Proof authority characterization readiness aggregate reviewed
readiness guards: Proof authority adapter import unwired guard and Verifier adapter import unwired guard reviewed
landing evidence: required
独立 TDD、独立 commit/push。
禁止 State ownership split、ToolExecutor、Dispatcher、composition root、MCP production wiring、Web/CLI/TUI task wiring、proof behavior change、P5、crew/recovery。
禁止 proof authority production wiring。
禁止 verifier production wiring。
禁止 verifier decision behavior change。
```

Approval text invariants:

- this template is not approval by itself
- approval must be sent as a user message
- approval text must not authorize bundled core changes
- readiness evidence does not approve implementation by itself
- adapter wrapper does not mean production wiring approval
- verifier/proof-authority adapter import guards must remain green

#### Proof adapter wrapper delegate-only pre-approval guard

Status: delegate-only guard recorded, implementation not approved.

The proof boundary adapter wrappers exist as skeletons, but they must remain
delegate-only until a separate explicit production wiring approval lands.

Guarded adapter scopes:

- `VerifierAdapter.review_claim`
- `ProofAuthorityAdapter.append_proof_record`
- `ProofAuthorityAdapter.confirm_claim`

Required invariants:

- adapter wrappers remain delegate-only skeletons
- adapter wrapper approval is not production wiring approval
- no verifier decision behavior changes
- no proof-authority behavior changes
- no `CTFState` ownership split
- no ToolExecutor changes
- no `CTFTaskDispatcher` flow changes
- no composition root changes

Required verification for this guard:

```powershell
.\.venv\Scripts\python.exe -m pytest tests/unit/test_verifier_adapter.py tests/unit/test_proof_authority_adapter.py -q
.\.venv\Scripts\python.exe -m pytest tests/unit/agents/test_p1_source_guards.py tests/unit/test_clean_architecture_migration_playbook.py -q
git diff --check
```

Boundary confirmation for this guard:

- no production wiring approval by this section
- no proof-authority behavior changes
- no verifier decision behavior changes
- no `CTFState` ownership split
- no ToolExecutor changes
- no `CTFTaskDispatcher` flow changes
- no MCP production wiring
- no Web/CLI/TUI task wiring
- no composition root changes
- no P5 implementation
- no crew/recovery changes

#### Verifier proof authority boundary first slice landing record

Status: first slice landed after explicit approval.

Current approval fact:

- Verifier/proof authority boundary: first slice landed

Approved scope:

- proof-authority boundary characterization
- adapter wrappers remain delegate-only
- `VerifierAdapter.review_claim`
- `ProofAuthorityAdapter.append_proof_record`
- `ProofAuthorityAdapter.confirm_claim`

Readiness evidence reviewed:

- Proof authority characterization readiness aggregate reviewed
- Proof adapter wrapper delegate-only pre-approval guard reviewed

Implementation summary:

- The first slice records the approved verifier/proof-authority boundary
  characterization landing without changing production proof behavior.
- Existing proof adapter wrappers remain delegate-only skeletons over injected
  ports and do not construct `CTFVerifier`, call `CTFState`, or wire
  production proof authority.
- This landing confirms the next proof-boundary step still needs a separate
  approval before any production wiring, verifier decision behavior, or state
  ownership migration.

Red test evidence:

- `tests/unit/test_clean_architecture_migration_playbook.py::test_playbook_records_verifier_proof_authority_first_slice_landing`
  failed before this record existed with:
  `AssertionError: missing heading: Verifier proof authority boundary first slice landing record`

Required verification for this landing:

```powershell
.\.venv\Scripts\python.exe -m pytest tests/unit/test_verifier_adapter.py tests/unit/test_proof_authority_adapter.py -q
.\.venv\Scripts\python.exe -m pytest tests/unit/agents/test_p1_source_guards.py tests/unit/test_clean_architecture_migration_playbook.py -q
git diff --check
```

Rollback command: git revert <Verifier proof authority first slice commit>

Boundary confirmation for this landing:

- no proof authority production wiring
- no verifier production wiring
- no verifier decision behavior changes
- no proof-authority behavior changes
- no `CTFState` ownership split
- no ToolExecutor changes
- no `CTFTaskDispatcher` flow changes
- no composition root changes
- no MCP production wiring
- no Web/CLI/TUI task wiring changes
- no P5 implementation
- no crew/recovery changes

#### P1-B proof adapter delegate guard hardening landing record

Status: guard hardening landed after explicit approval.

Current approval fact:

- Candidate P1-B Verifier/proof authority boundary second slice: landed

Approved scope:

- legacy verifier/proof authority adapter wrapper characterization
- proof adapter guard hardening
- `flaghunter/adapters/proof`
- focused proof adapter tests
- source guards
- playbook governance record

Guarded adapter body invariants:

- VerifierAdapter.review_claim remains a single awaited delegate call
- ProofAuthorityAdapter.append_proof_record remains a single delegate call
- ProofAuthorityAdapter.confirm_claim remains a single delegate call
- no legacy `CTFVerifier` construction
- no legacy `CTFState` calls
- no proof authority production wiring
- no verifier production wiring
- no verifier decision behavior changes
- no proof-authority behavior changes

Implementation summary:

- `tests/unit/test_verifier_adapter.py` now characterizes
  `VerifierAdapter.review_claim` as a direct `self._verifier.review_claim`
  delegation with no branching, local assignment, exception handling, or proof
  upgrade behavior.
- `tests/unit/test_proof_authority_adapter.py` now characterizes
  `ProofAuthorityAdapter.append_proof_record` and
  `ProofAuthorityAdapter.confirm_claim` as direct `self._authority`
  delegations with no branching, local assignment, exception handling, legacy
  verifier construction, state calls, or production wiring.
- No production adapter code changed because the current adapter skeletons
  already match the approved delegate-only shape.

Red test evidence:

- `tests/unit/test_clean_architecture_migration_playbook.py::test_playbook_records_p1b_proof_adapter_delegate_guard_hardening_landing`
  failed before this record existed with:
  `AssertionError: missing heading: P1-B proof adapter delegate guard hardening landing record`

Required verification for this landing:

```powershell
.\.venv\Scripts\python.exe -m pytest tests/unit/test_verifier_adapter.py tests/unit/test_proof_authority_adapter.py -q
.\.venv\Scripts\python.exe -m pytest tests/unit/agents/test_p1_source_guards.py tests/unit/agents/test_p1_claim_invariants.py tests/unit/test_adapter_boundary_skeleton.py tests/unit/test_clean_architecture_migration_playbook.py -q
git diff --check
```

Rollback command: git revert <P1-B proof adapter delegate guard hardening commit>

Boundary confirmation for this landing:

- no production wiring
- no proof authority production wiring
- no verifier production wiring
- no verifier decision behavior changes
- no proof-authority behavior changes
- no `CTFState` ownership split
- no Dispatcher changes
- no ToolExecutor changes
- no MCP/Web/CLI/TUI changes
- no composition root changes
- no P5 implementation
- no crew/recovery changes

#### Task ingress service contract migration approval flag consistency guard

Status: approval consistency guard updated, implementation landed.

The task ingress service migration has three governance surfaces that moved
together after explicit approval:

- Task ingress service contract migration plan
- Task ingress service contract migration pre-approval guard
- Task ingress service contract migration readiness checklist

| Governance surface | Implementation approved | Service migration landed |
|--------------------|-------------------------|--------------------------|
| plan | true | true |
| pre-approval guard | true | true |
| readiness checklist | true | true |

Required consistency:

- the plan records implementation approved and landed
- the pre-approval guard is retired by the landing guard
- the readiness checklist records the explicit approval and landing
- no production wiring approval by implication
- no production wiring
- no status-only approval without matching implementation evidence

#### Task ingress service contract migration landing record template

Status: implementation landing record completed.

Task ingress service contract migration implementation landing record.

Current approval fact:

- Task ingress service contract migration: implementation landed

The approved task ingress service migration commit adds a completed landing
record before the service migration is treated as landed.

Required landing record fields:

- Implementation commit SHA: recorded in the completion report for this commit
- Target: `flaghunter/application/challenge/task_ingress_service.py`
- Behavior equivalence evidence: old/new output equivalence test name and
  result
- Port payload compatibility evidence: raw `instructions` in the injected port request payload preserved
- Neutral service contract evidence: service internally uses `TaskIngressRequest`, `TaskIngressReceipt`, and `TaskIngressReadback`
- Pre-approval guard update: landing guard test name and result from the same
  implementation commit
- Focused regression result: exact command and result
- Architecture/source-guard result: exact command and result
- git diff --check result: exact result
- Post-push branch status: exact `git status --short --branch`
- Rollback command: git revert <Task ingress service contract migration implementation commit>
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

This landing record covers only the approved service contract migration. It
does not authorize task ingress production wiring or any downstream core
production rewiring.

#### Task ingress service rollback placeholder consistency guard

Status: rollback placeholder guard updated, implementation landed.

This guard keeps rollback scoped to the single task ingress service migration
commit. The exact commit SHA is reported in the completion report after the
commit is created.

| Scope | Rollback command | Applies after | Current executable |
|-------|------------------|---------------|--------------------|
| task ingress service migration | `git revert <Task ingress service contract migration implementation commit>` | service migration commit lands | true |

Required consistency:

- rollback remains one service migration commit only
- the completion report records the exact executable commit SHA
- no production wiring rollback is bundled with this service migration rollback
- the landing record records `Rollback command: git revert <Task ingress
  service contract migration implementation commit>`

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

Status: approval transition evidence consistency guard updated, implementation landed.

Approval evidence is present for the approved task ingress service migration.
It does not approve task ingress production wiring.

| Evidence item | Required location | Current approval evidence present |
|---------------|-------------------|-----------------------------------|
| red test evidence | `Task ingress service contract migration readiness checklist` | true |
| green focused regression | `Task ingress service contract migration readiness checklist` | true |
| architecture/source regression | `Task ingress service contract migration readiness checklist` | true |
| approval flag update evidence | `Task ingress service contract migration approval flag consistency guard` | true |
| landing record placeholder | `Task ingress service contract migration landing record template` | true |
| rollback placeholder evidence | `Task ingress service rollback placeholder consistency guard` | true |
| post-push branch status | `Task ingress service contract migration readiness checklist` | true |

Rules:

- approval evidence must be present before implementation approval changes
- all approval evidence rows moved together with the implementation landing
  evidence
- no row may imply production wiring approval
- no task ingress production wiring is authorized by this evidence guard

#### Task ingress service landing status guard

Status: landing status guard updated, service migration landed.

The task ingress service migration has landed. The landing record, rollback
placeholder, and approval evidence guard agree on that state while downstream
production wiring remains unapproved.

| Landing surface | Required location | Current landed |
|-----------------|-------------------|----------------|
| landing record template | `Task ingress service contract migration landing record template` | true |
| rollback placeholder | `Task ingress service rollback placeholder consistency guard` | true |
| approval evidence | `Task ingress service approval transition evidence consistency guard` | true |

Rules:

- no landing surface may move to `Current landed` = `true` without explicit
  approval and implementation evidence
- rollback is the single service migration commit
- approval evidence rows must not imply production wiring approval
- no task ingress production wiring is authorized by this landing status guard

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
- `flaghunter.eval`
- `flaghunter.interface`
- `flaghunter.knowledge`
- `flaghunter.llm`
- `flaghunter.mcp`
- `flaghunter.playbooks`
- `flaghunter.redteam`
- `flaghunter.runtime`
- `flaghunter.session`
- `flaghunter.tools`
- `flaghunter.workspaces`

This guard keeps substitution fixtures focused on fake injected ports and
prevents them from silently becoming a domain-contract, application-service,
legacy feature-module, evaluation harness, red-team legacy helper, playbook,
runtime, MCP, tool, session, or workspace integration path.

Boundary confirmation for this guard:

- no production behavior changes
- no concrete adapter production wiring
- no composition root changes
- no MCP production wiring
- no dispatcher loop changes
- no runtime construction
- no ToolExecutor changes
- no proof authority behavior changes

#### Adapter substitution fixture side-effect sink coverage guard

Status: explicit side-effect sink coverage guard added for adapter substitution
fixtures.

`tests/unit/test_adapter_substitution_source_guards.py` now requires
`tests/unit/test_adapter_port_substitution.py` to remain free of common
filesystem, process, network, socket, browser/runtime, and tool-execution
sinks:

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

This guard keeps adapter substitution fixtures as pure replaceability tests
over injected fake ports. They may prove that adapter skeletons can be
substituted, but they must not become filesystem readers or writers, process
launchers, network clients, runtime bridges, or tool-execution paths.

Boundary confirmation for this guard:

- no production behavior changes
- no concrete adapter production wiring
- no composition root changes
- no MCP production wiring
- no dispatcher loop changes
- no runtime construction
- no ToolExecutor changes
- no proof authority behavior changes

#### Adapter substitution fixture proof authority coverage guard

Status: explicit proof authority write-surface coverage guard added for adapter
substitution fixtures.

`tests/unit/test_adapter_substitution_source_guards.py` now requires
`tests/unit/test_adapter_port_substitution.py` to remain free of proof
authority port construction, proof authority adapter construction, proof record
writes, verification record writes, claim confirmation, proof upgrade calls,
accepted-proof literals, and legacy verified buckets:

- `ProofAuthorityPort`
- `ProofAuthorityAdapter`
- `append_proof_record`
- `append_verification_record`
- `confirm_claim`
- `upgrade_claim_to_verified`
- `level="verified"`
- `level='verified'`
- `verified_flags`
- `verifiedFlags`

This guard keeps adapter substitution fixtures focused on replaceability over
fake injected ports. They may prove adapters can be swapped, but they must not
construct proof authority surfaces, write accepted proof, confirm claims, or
simulate proof upgrades.

Boundary confirmation for this guard:

- no production behavior changes
- no concrete adapter production wiring
- no composition root changes
- no MCP production wiring
- no dispatcher loop changes
- no runtime construction
- no ToolExecutor changes
- no proof authority behavior changes

#### Adapter substitution fixture production token coverage guard

Status: explicit production runtime token coverage guard added for adapter
substitution fixtures.

`tests/unit/test_adapter_substitution_source_guards.py` now requires
`tests/unit/test_adapter_port_substitution.py` to remain free of production
dispatcher, verifier, tool executor, crew orchestration, and runtime
construction surfaces:

- `CTFTaskDispatcher`
- `CTFVerifier`
- `ToolExecutor`
- `WorkerPool`
- `CrewOrchestrator`
- `LocalRuntime`
- `DockerRuntime`
- `SSHRuntime`

This guard keeps adapter substitution fixtures as test-only replaceability
checks over fake injected ports. They may verify that an adapter can be
substituted, but they must not instantiate or reference production dispatcher,
verifier, tool executor, crew, or runtime implementations.

Boundary confirmation for this guard:

- no production behavior changes
- no concrete adapter production wiring
- no composition root changes
- no MCP production wiring
- no dispatcher loop changes
- no runtime construction
- no ToolExecutor changes
- no proof authority behavior changes

#### Adapter substitution fixture coverage completeness guard

Status: aggregate coverage completeness guard added for adapter substitution
fixtures.

`tests/unit/test_adapter_substitution_source_guards.py` now requires the
adapter substitution fixture source guard record to keep all four guard groups
visible together:

- `Adapter substitution fixture import coverage guard`
- `Adapter substitution fixture side-effect sink coverage guard`
- `Adapter substitution fixture production token coverage guard`
- `Adapter substitution fixture proof authority coverage guard`

This aggregate guard prevents the adapter substitution fixture source guard
from drifting into partial coverage. The fixture must keep import boundaries,
side-effect sinks, production runtime tokens, and proof authority write
surfaces covered as one complete replaceability-test boundary.

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
- `flaghunter.eval`
- `flaghunter.interface`
- `flaghunter.knowledge`
- `flaghunter.llm`
- `flaghunter.mcp`
- `flaghunter.playbooks`
- `flaghunter.redteam`
- `flaghunter.runtime`
- `flaghunter.session`
- `flaghunter.tools`
- `flaghunter.workspaces`

This guard keeps current adapter skeletons from reaching into application
services, production configuration, legacy feature modules, evaluation
harnesses, red-team legacy helpers, playbooks, model/runtime code,
presentation, MCP, tools, sessions, or workspace helpers before a focused
adapter-wrapper or production-wiring slice is approved.

Boundary confirmation for this guard:

- no production behavior changes
- no concrete adapter production wiring
- no composition root changes
- no MCP production wiring
- no dispatcher loop changes
- no runtime construction
- no ToolExecutor changes
- no proof authority behavior changes

#### Specific adapter source guard import coverage consistency guard

Status: focused adapter source guard import coverage consistency added for
individual adapter tests.

`tests/unit/test_adapter_boundary_skeleton.py` now requires every
`tests/unit/test_*_adapter.py` focused source guard to cover the outer legacy
evaluation and red-team helper packages:

- `flaghunter.eval`
- `flaghunter.redteam`

This guard keeps single-adapter focused tests consistent with the package-level
adapter boundary guard, so running an individual adapter test still blocks
accidental imports from evaluation harnesses or red-team legacy helpers.

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

#### Adapter source guard coverage completeness guard

Status: aggregate coverage completeness guard added for adapter skeleton source
guards.

`tests/unit/test_adapter_boundary_skeleton.py` now requires the adapter
skeleton source guard record to keep all adapter boundary guard groups visible
together:

- `Adapter production wiring source guard`
- `Adapter action sink coverage guard`
- `Adapter proof action coverage guard`
- `Adapter outer-layer import coverage guard`
- `Adapter public surface domain-neutral naming guard`
- `Specific adapter source guard import coverage consistency guard`

This aggregate guard prevents adapter skeleton boundary coverage from drifting
into partial protection. Adapter skeletons must keep production wiring
surfaces, action sinks, proof authority surfaces, outer-layer imports, public
neutral naming, and focused adapter-test import coverage guarded as one
complete unwired-adapter boundary.

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
- neutral metadata projection baseline
- neutral metadata alias projection baseline
- neutral candidate enrichment baseline
- neutral candidate ordering baseline
- neutral candidate marker baseline
- neutral hypothesis summary alias baseline
- neutral source type alias baseline
- neutral trigger reason alias baseline
- neutral trigger action driver alias baseline
- neutral trigger time alias baseline
- neutral trigger result alias baseline
- neutral expected action alias baseline
- neutral observed action alias baseline
- neutral task action alias baseline
- neutral next action alias baseline
- neutral malformed board item projection baseline
- neutral recommended action projection baseline
- neutral explicit recommendation marker baseline
- neutral candidate/action-result degraded baseline
- neutral suppressed recommendation baseline
- Candidate A Web blackboard fixture evidence:
  `test_candidate_a_pre_approval_guard_blocks_neutral_builder_wiring`
  `test_build_promotes_neutral_board_metadata_to_read_model_fields`
  `test_build_promotes_board_metadata_aliases_to_read_model_fields`
  `test_task_board_projection_enriches_selected_and_recommended_candidates`
  `test_task_board_projection_orders_candidates_and_projects_last_result`
  `test_task_board_projection_adds_default_recommended_marker_for_ordered_candidates`
  `test_task_board_projection_accepts_hypothesis_summary_aliases`
  `test_task_board_projection_accepts_candidate_source_type_alias`
  `test_task_board_projection_accepts_action_result_trigger_reason_alias`
  `test_task_board_projection_accepts_action_result_trigger_driver_alias`
  `test_task_board_projection_accepts_action_result_trigger_time_alias`
  `test_task_board_projection_accepts_action_result_trigger_result_alias`
  `test_task_board_projection_accepts_action_result_expected_action_alias`
  `test_task_board_projection_accepts_action_result_observed_action_alias`
  `test_task_board_projection_accepts_task_action_aliases`
  `test_task_board_projection_accepts_active_decision_next_action_alias`
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

Status: implementation landed.

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

Implemented scope:

- target only
  `flaghunter/interface/web_trace_timeline.py::_build_control_observation_timeline_events`
- use `tests/unit/web_console/test_trace_timeline_read_model_switch.py` as the
  required old/new output equivalence fixture home
- preserve event IDs, timestamps, `kind`, `title`, `summary`, `driver`, and `input` fields
- preserve empty, malformed, unsupported, and no-mutation behavior
- no proof writes and no proof authority decisions

Implementation landing:

- one implementation commit only
- rollback point: revert the single Candidate B implementation commit
- no schema migration or production wiring in the implementation commit

Required verification for the implementation slice:

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

Status: implementation landed.

Candidate B executed the trace timeline read-path switch in this order:

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
- Candidate direction: serialize-task projection is the next review gate after
  Candidate B has landed.
- Risk: medium-to-high. This is a fan-out path for task list/detail, retry,
  continue, and control decision views.
- Required approval: separate short plan; one call-site family per commit.

#### Candidate C approval plan

Status: approval required before implementation.

Prerequisite: proceed only after explicit Candidate C serialize-task approval is
granted. Candidate C must not introduce a second projection shape or bypass the
Candidate A/B equivalence fixtures.

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

These constraints must hold until Candidate C serialize-task implementation is
approved.

#### Candidate C implementation readiness checklist

Status: ready for serialize-task approval review, not approved for implementation.

Candidate C serialize-task and control-decision have landed as separate commits.
Deferred MCP readback is the next review gate and remains unapproved.

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

Status: implementation landed for Deferred MCP readback.

Deferred MCP readback proceeded only after the approved Web read-model
projection path landed and explicit MCP production wiring approval was granted.

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

- Web read-model projection equivalence is proven
- explicit MCP production wiring approval was granted before editing the MCP
  readback helper
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

Status: implementation landed.

Web projection equivalence has landed and explicit MCP production wiring
approval was granted. The Deferred MCP readback switch was executed in this
order:

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

Status: sequence guard recorded, Web read paths and Deferred MCP readback landed; core production wiring remains guarded.

Candidates A, B, C serialize-task, C control-decision, and Deferred MCP
readback have landed as separate read-path switches.

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
- Candidate C serialize-task may not be implemented before Candidate B lands
- Candidate C control-decision may not be implemented before Candidate C serialize-task lands
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

Status: acceptance matrix recorded, Web read paths and Deferred MCP readback landed.

| Candidate | Status | Target path | Unblock condition |
|-----------|--------|-------------|-------------------|
| Candidate A | implementation landed | `blackboard_lite.py` | complete |
| Candidate B | implementation landed | `web_trace_timeline.py` | complete |
| Candidate C | implementation landed | `web_serialize_task.py and web_control_decision.py` | complete |
| Deferred MCP | implementation landed | `mcp_tools.py` | complete |

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

Status: approval drift guard recorded, Web read paths and Deferred MCP readback landed.

Current approval facts must not drift silently:

- Candidate A: implementation landed
- Candidate B: implementation landed
- Candidate C: implementation landed
- Deferred MCP: implementation landed

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

Status: consolidated approval package recorded, Web read paths and Deferred MCP readback landed.

| Candidate | Current status | Target | evidence present | remaining blocker |
|-----------|----------------|--------|------------------|-------------------|
| Candidate A | implementation landed | `flaghunter/interface/blackboard_lite.py::build_task_blackboard_snapshot` | neutral projection fixtures, Web blackboard fixtures, source guard, pre-approval guard retired by implementation landing record | complete |
| Candidate B | implementation landed | `flaghunter/interface/web_trace_timeline.py::_build_control_observation_timeline_events` | characterization fixture, read-only source guard, pre-approval guard retired by implementation landing record | complete |
| Candidate C | implementation landed | `flaghunter/interface/web_serialize_task.py::_serialize_task` and `flaghunter/interface/web_control_decision.py::_task_blackboard_snapshot_for_decision` | serialize-task fixture, control-decision merge fixture, source guard, pre-approval guard retired by implementation landing records | complete |
| Deferred MCP | implementation landed | `flaghunter/mcp/server/mcp_tools.py::_append_blackboard_snapshot_lines` | readback formatting fixture, empty/malformed fixture, source guard, pre-approval guard retired by implementation landing record | complete |

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

Status: machine-readable status ledger recorded, Web read paths and Deferred MCP readback landed.

This machine-readable approval ledger is the compact index for the current
read-path candidate state. It is intentionally repetitive with the narrative
sections so guard tests can detect drift before implementation starts.

| Candidate | canonicalStatus | approvedForImplementation | nextGate |
|-----------|-----------------|---------------------------|----------|
| Candidate A | implementation landed | true | complete |
| Candidate B | implementation landed | true | complete |
| Candidate C | implementation landed | true | complete |
| Deferred MCP | implementation landed | true | complete |

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

Status: explicit MCP approval guard recorded, Deferred MCP readback implementation landed.

Deferred MCP is the only current read-path candidate whose future implementation
counts as MCP production wiring. It remained blocked until Web projection
equivalence landed plus explicit MCP production wiring approval was recorded.
Web read-path equivalence alone must never authorize an MCP readback switch.

Canonical Deferred MCP blocker: Web projection equivalence lands plus explicit MCP production wiring approval.

Required parsed checks:

- Deferred MCP ledger `nextGate` is `complete`
- Deferred MCP readiness `Missing approval` is `complete`
- Deferred MCP approval package `remaining blocker` is `complete`
- Deferred MCP source-map row remains
  `flaghunter/mcp/server/mcp_tools.py` with `Implementation approved` = `true`
- Deferred MCP approved execution checklist must confirm explicit MCP production wiring approval
- Deferred MCP approved execution checklist keeps `confirm explicit MCP
  production wiring approval`
- Deferred MCP non-goals must keep no MCP production wiring without explicit approval
- Deferred MCP non-goals keep `no MCP production wiring without explicit
  approval`
- no task execution path switch is authorized by this explicit MCP approval guard

#### Read-path approved execution checklist index

Status: checklist index recorded, no implementation approved by this section.

This index keeps the candidate-specific execution checklists discoverable
without granting implementation approval. Every row must remain
`implementation not approved` until the matching approval state transition is
recorded.

| Candidate | Checklist section | Checklist status | Approval state |
|-----------|-------------------|------------------|----------------|
| Candidate A | `Candidate A approved execution checklist` | not approved; checklist only | implementation not approved |
| Candidate B | `Candidate B approved execution checklist` | implementation landed | implementation landed |
| Candidate C | `Candidate C approved execution checklist` | not approved; checklist only | implementation not approved |
| Deferred MCP | `Deferred MCP approved execution checklist` | implementation landed | implementation landed |

Rules:

- each indexed checklist section must exist in this playbook
- each indexed checklist must keep `Status: not approved; checklist only.`
- the index is a readiness map, not implementation approval
- no production path switch is authorized by this checklist index

#### Read-path implementation approval readiness report

Status: readiness report recorded, Web read paths and Deferred MCP readback landed.

This report separates readiness evidence from approval. It identifies which
candidates have enough recorded evidence to request implementation approval and
which candidates remain sequence-blocked by an earlier read-path switch.

| Candidate | Current status | Readiness state | Missing approval | Implementation approved |
|-----------|----------------|-----------------|------------------|-------------------------|
| Candidate A | implementation landed | landed; output equivalence preserved | complete | true |
| Candidate B | implementation landed | landed; output equivalence preserved | complete | true |
| Candidate C | implementation landed | landed; output equivalence preserved | complete | true |
| Deferred MCP | implementation landed | landed; output equivalence preserved | complete | true |

Rules:

- readiness evidence is not implementation approval
- Candidate A has landed as the first read-path implementation candidate
- Candidate B has landed as the second read-path implementation candidate
- Candidate C serialize-task and control-decision have landed
- Deferred MCP readback landed only after Web projection equivalence and
  explicit MCP production wiring approval
- no production path switch is authorized by this readiness report

#### Read-path pre-approval source-map guard

Status: Web read paths A, B, C1, C2, and Deferred MCP readback implementation landed.

This source map lists the production source files that must remain free of
neutral read-model projection wiring while the matching read-path candidate is
not approved for implementation. It complements the candidate-specific source
guards by keeping one parseable map in the playbook.

| Candidate | Source path | Forbidden neutral wiring | Implementation approved |
|-----------|-------------|--------------------------|-------------------------|
| Candidate A | `flaghunter/interface/blackboard_lite.py` | `flaghunter.application.challenge`, `flaghunter.domain.challenge.contracts`, `build_task_board_projection`, `BuildChallengeBoardReadModel`, `ChallengeBoardReadModel` | true |
| Candidate B | `flaghunter/interface/web_trace_timeline.py` | `flaghunter.application.challenge`, `flaghunter.domain.challenge.contracts`, `build_task_board_projection`, `BuildChallengeBoardReadModel`, `ChallengeBoardReadModel` | true |
| Candidate C serialize-task | `flaghunter/interface/web_serialize_task.py` | `flaghunter.application.challenge`, `flaghunter.domain.challenge.contracts`, `build_task_board_projection`, `BuildChallengeBoardReadModel`, `ChallengeBoardReadModel` | true |
| Candidate C control-decision | `flaghunter/interface/web_control_decision.py` | `flaghunter.application.challenge`, `flaghunter.domain.challenge.contracts`, `build_task_board_projection`, `BuildChallengeBoardReadModel`, `ChallengeBoardReadModel` | true |
| Deferred MCP | `flaghunter/mcp/server/mcp_tools.py` | `flaghunter.application.challenge`, `flaghunter.domain.challenge.contracts`, `build_task_board_projection`, `BuildChallengeBoardReadModel`, `ChallengeBoardReadModel` | true |

Rules:

- every source path in this map must exist
- forbidden neutral wiring must remain absent until explicit implementation
  approval lands for that candidate
- source-map rows must remain `Implementation approved` = `false` until the
  matching implementation commit updates the pre-approval guard; Web read paths
  A, B, C serialize-task, C control-decision, and Deferred MCP are the landed
  exceptions in this table
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

#### Read-path approval package evidence completeness guard

Status: evidence completeness guard recorded, no implementation approved by this section.

The approval package records readiness evidence for each read-path candidate,
but approval package readiness evidence is not implementation approval evidence.
This guard separates currently complete readiness indexes from approval
transition and landing evidence that must remain absent until explicit
implementation approval and a future implementation commit exist.

| Evidence group | Required section | Current complete |
|----------------|------------------|------------------|
| candidate status ledger | `Read-path candidate status ledger` | true |
| readiness report | `Read-path implementation approval readiness report` | true |
| source-map coverage | `Read-path approval package source-map consistency guard` | true |
| approval transition evidence | `Read-path approval transition evidence consistency guard` | false |
| landing evidence | `Read-path implementation landed evidence guard` | false |

Rules:

- every approval package row must keep source guard and pre-approval guard
  evidence visible before an approval request can be reviewed
- every approval package row must keep a remaining blocker while
  implementation approval remains false
- approval transition evidence remains incomplete until explicit approval
  evidence lands in the same governance commit as the approval transition
- landing evidence remains incomplete until a real implementation commit SHA
  and rollback command are recorded
- no production path switch is authorized by this evidence completeness guard

#### Read-path implementation landed evidence guard

Status: landed evidence guard recorded, Web read paths and Deferred MCP readback landed.

This guard prevents a candidate from being marked `implementation landed`
without the landing record required by the template below. Current rows have no
landing evidence because no read-path implementation has been approved or
landed.

| Candidate | Implementation landed | Landing evidence | Required before landed |
|-----------|-----------------------|------------------|------------------------|
| Candidate A | true | Candidate A implementation landing record | landing record, implementation commit, regression results |
| Candidate B | true | Candidate B implementation landing record | landing record, implementation commit, regression results |
| Candidate C | true | Candidate C1 and Candidate C2 implementation landing records | landing records, implementation commits, regression results |
| Deferred MCP | true | Deferred MCP implementation landing record | landing record, implementation commit, regression results |

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

Status: aggregate approval flag guard recorded, Web read paths and Deferred MCP readback landed.

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
  `approvedForImplementation` remains `false`; landed read paths have both
  values `true`
- landed evidence `Implementation landed` remains `false` until a landing
  record exists
- Candidate C source-map sub-rows must collapse back to the canonical
  Candidate C ledger row
- no production path switch is authorized by this aggregate approval flag guard

#### Read-path rollback command index

Status: rollback command index recorded, Web read paths and Deferred MCP readback landed.

This index records placeholder only rollback commands for future read-path
implementation commits. Each command becomes valid only after the matching
candidate implementation commit lands and its landing record captures the real
commit SHA. A placeholder is not a currently executable rollback command and
does not imply that any read-path implementation has landed.

| Candidate | Rollback command | Applies after | Current executable |
|-----------|------------------|---------------|--------------------|
| Candidate A | `git revert <Candidate A implementation commit>` | Candidate A implementation commit lands | false |
| Candidate B | `git revert <Candidate B implementation commit>` | Candidate B implementation commit lands | false |
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

#### Read-path implementation landing status guard

Status: landing status guard recorded, Web read paths and Deferred MCP readback landed.

Web read paths and Deferred MCP readback have landed. The landed evidence rows,
rollback index, and landing record template must continue to agree that
rollback commands remain placeholder-only until the real implementation commit
SHA is substituted in a release/rollback workflow.

| Landing surface | Required location | Current landed |
|-----------------|-------------------|----------------|
| landed evidence rows | `Read-path implementation landed evidence guard` | true |
| rollback index | `Read-path rollback command index` | false |
| landing record template | `Read-path implementation landing record template` | true |

Rules:

- no landing surface may move to `Current landed` = `true` without a real
  candidate implementation commit SHA
- landed evidence rows may move to `Implementation landed` = `true` only with
  a candidate-specific landing record
- rollback commands remain placeholder-only and non-executable while
  `Current landed` remains `false`
- no production path switch is authorized by this landing status guard

#### Read-path readiness-to-landing transition guard

Status: readiness-to-landing guard recorded, Web read paths and Deferred MCP readback landed.

Readiness complete alone must not unlock landing. A future read-path
implementation can move from readiness review to landed only when explicit
approval evidence, implementation approval flags, landing evidence, executable
rollback commands, and landing status all move together in the required
governance or implementation commit.

| Transition checkpoint | Required section | Current satisfied |
|-----------------------|------------------|-------------------|
| readiness indexes complete | `Read-path approval package evidence completeness guard` | true |
| approval transition evidence complete | `Read-path approval package evidence completeness guard` | false |
| implementation approval flags raised | `Read-path approval flag aggregate guard` | true |
| landing evidence recorded | `Read-path implementation landed evidence guard` | true |
| rollback commands executable | `Read-path rollback command index` | false |
| landing status raised | `Read-path implementation landing status guard` | true |

Rules:

- readiness indexes may be complete while implementation approval remains false
- approval transition evidence must be complete before any implementation
  approval flag can move to true
- implementation approval flags must be raised before any landing evidence can
  move to true
- landing evidence and executable rollback commands require the same real
  implementation commit SHA
- landing status remains false until landing evidence and rollback commands are
  current for the candidate
- no production path switch is authorized by this readiness-to-landing guard

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

Status: approval consistency guard recorded, Web read paths and Deferred MCP readback landed.

The read-path approval state has a single source of approval truth across the
acceptance matrix, drift guard, approval package summary, and each
candidate-specific implementation readiness checklist.

| Candidate | Canonical status | Must match |
|-----------|------------------|------------|
| Candidate A | implementation landed | acceptance matrix, drift guard, approval package summary, Candidate A readiness checklist |
| Candidate B | implementation landed | acceptance matrix, drift guard, approval package summary, Candidate B readiness checklist |
| Candidate C | implementation landed | acceptance matrix, drift guard, approval package summary, Candidate C readiness checklist |
| Deferred MCP | implementation landed | acceptance matrix, drift guard, approval package summary, Deferred MCP readiness checklist |

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
| Candidate A | acceptance, drift, package, ledger, readiness, source-map, checklist, landing evidence | true |
| Candidate B | acceptance, drift, package, ledger, readiness, source-map, checklist, landing evidence | true |
| Candidate C | acceptance, drift, package, ledger, readiness, source-map, checklist, landing evidence | true |
| Deferred MCP | acceptance, drift, package, ledger, readiness, source-map, checklist, landing evidence | true |

Rules:

- every approval table must keep the same canonical candidate set
- split Candidate C source-map rows must not create a second approval state
- no production path switch is authorized by this candidate coverage guard

#### Read-path approval transition evidence consistency guard

Status: approval transition evidence consistency guard recorded, no implementation approved.

Approval evidence must be present before any read-path implementation approval
changes. The current state intentionally records no approval evidence because no
read-path implementation has been approved.

| Evidence item | Required location | Current approval evidence present |
|---------------|-------------------|-----------------------------------|
| acceptance matrix update | `Read-path switch acceptance matrix` | false |
| approval drift update | `Read-path approval drift guard` | false |
| candidate status ledger update | `Read-path candidate status ledger` | false |
| readiness evidence update | `Read-path implementation approval readiness report` | false |
| source-map approval update | `Read-path pre-approval source-map guard` | false |
| approved execution checklist update | `Read-path approved execution checklist index` | false |
| landing record placeholder | `Read-path implementation landing record template` | false |

Rules:

- approval evidence must be present before implementation approval changes
- all approval evidence rows must move together in the approval-transition
  governance commit
- no row may claim current approval evidence while implementation remains
  unapproved
- no production path switch is authorized by this evidence guard

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

#### Candidate A implementation landing record

Status: implementation landed for Candidate A.

Current approval fact:

- Candidate A: implementation landed

Target:

- `flaghunter/interface/blackboard_lite.py::build_task_blackboard_snapshot`

Implementation summary:

- Candidate A now routes the Web blackboard read projection through the neutral
  `ChallengeBoardReadModel` and `build_task_board_projection` helper.
- The existing legacy read-side collection remains read-only and is converted
  into a neutral board read model before returning the public Candidate
  A-compatible projection shape.
- The implementation commit modifies only Candidate A production helper code,
  Candidate A tests, and this playbook governance record.

Equivalence evidence:

- `tests/unit/interface/test_blackboard_lite.py` representative, degraded,
  decision/ingress/action-result, recommendation, alignment, hypothesis, and
  suppression fixtures preserve the existing public output shape.
- `tests/unit/test_application_board_read_model_service.py` keeps the neutral
  projection contract covered.
- `tests/unit/test_clean_architecture_migration_playbook.py` records this
  landing state and keeps unapproved downstream read paths guarded.

Rollback command:

- `git revert <Candidate A implementation commit>`

Boundary confirmation for this landing:

- no bundled Web and MCP implementation
- no dispatcher loop changes
- no `CTFState` ownership split
- no `CTFVerifier` proof behavior changes
- no ToolExecutor changes
- no WorkerPool/CrewOrchestrator changes
- no MCP production wiring
- no composition root changes
- no proof authority behavior changes
- no P5 implementation

#### Candidate A pre-approval production switch guard

Status: retired by Candidate A implementation landing.

`tests/unit/interface/test_blackboard_lite.py` now guards
`flaghunter/interface/blackboard_lite.py::build_task_blackboard_snapshot`
to require the neutral application board projection builder after Candidate A
implementation approval landed.

Current approval fact:

- Candidate A: implementation landed

This guard changed in the same implementation commit that proves old/new output
equivalence for the first read-path switch.

Required after landing:

- import `flaghunter.application.challenge.board_read_model_service`
- call `build_task_board_projection`
- construct or reference `ChallengeBoardReadModel`
- keep MCP readback, task serialization, and control-decision merge helpers out
  of this implementation commit

Boundary confirmation for this landing guard:

- no dispatcher loop changes
- no `CTFState` ownership split
- no `CTFVerifier` proof behavior changes
- no ToolExecutor changes
- no WorkerPool/CrewOrchestrator changes
- no MCP production wiring
- no proof authority behavior changes

#### Candidate B pre-approval production switch guard

#### Candidate B implementation landing record

Status: implementation landed for Candidate B.

Current approval fact:

- Candidate B: implementation landed

Target:

- `flaghunter/interface/web_trace_timeline.py::_build_control_observation_timeline_events`

Implementation summary:

- Candidate B now routes the Web trace observation read projection through
  neutral `ChallengeBoardReadModel` facts and `build_task_board_projection`.
- The existing legacy `ctfStateSnapshot.observations` collection remains
  read-only and is converted into neutral board facts before returning the
  public trace timeline event shape.
- The implementation commit modifies only Candidate B production helper code,
  Candidate B tests, and this playbook governance record.

Equivalence evidence:

- `tests/unit/web_console/test_trace_timeline_read_model_switch.py` preserves
  supported observation events, empty/malformed input behavior, default resume
  bootstrap fields, and no task mutation.
- `tests/unit/test_clean_architecture_migration_playbook.py` records this
  landing state and keeps Candidate C, Deferred MCP, and core production wiring
  guarded.

Rollback command:

- `git revert <Candidate B implementation commit>`

Boundary confirmation for this landing:

- no bundled Web and MCP implementation
- no dispatcher loop changes
- no `CTFState` ownership split
- no `CTFVerifier` proof behavior changes
- no ToolExecutor changes
- no WorkerPool/CrewOrchestrator changes
- no MCP production wiring
- no composition root changes
- no proof authority behavior changes
- no P5 implementation

#### Candidate B pre-approval production switch guard

Status: retired by Candidate B implementation landing.

`tests/unit/web_console/test_trace_timeline_read_model_switch.py` now guards
`flaghunter/interface/web_trace_timeline.py::_build_control_observation_timeline_events`
against importing or calling neutral challenge board/read-model projection
helpers before Candidate B implementation approval landed.

Current approval fact:

- Candidate B: implementation landed

This guard changed in the same implementation commit that proves old/new output
equivalence for the trace timeline read path.

Required after landing:

- import `flaghunter.application.challenge.board_read_model_service`
- call `build_task_board_projection`
- construct `ChallengeBoardReadModel`
- keep Candidate C and Deferred MCP production helpers out of this
  implementation commit

Boundary confirmation for this pre-approval guard:

- no production path switch
- no dispatcher loop changes
- no `CTFState` ownership split
- no `CTFVerifier` proof behavior changes
- no ToolExecutor changes
- no WorkerPool/CrewOrchestrator changes
- no MCP production wiring
- no proof authority behavior changes

#### Candidate C1 implementation landing record

Status: implementation landed for Candidate C serialize-task.

Current approval fact:

- Candidate C serialize-task: implementation landed

Target:

- `flaghunter/interface/web_serialize_task.py::_serialize_task`

Implementation summary:

- Candidate C1 now routes the Web task serialization read projection through
  neutral `ChallengeBoardReadModel` and `build_task_board_projection` before
  building task detail summaries.
- The existing returned `blackboardSnapshot` payload remains compatible with
  the pre-switch task serialization shape.
- The implementation commit modifies only Candidate C1 production helper code,
  Candidate C tests, and this playbook governance record.

Equivalence evidence:

- `tests/unit/interface/test_web_server.py::test_candidate_c_serialize_task_fixture_preserves_snapshot_and_summaries_before_switch`
  preserves task detail blackboard payload, next-action explanation,
  active-decision summary, and capability flags.
- `tests/unit/interface/test_web_server.py::test_candidate_c1_implementation_uses_neutral_projection_and_keeps_c2_guarded`
  records the C1 landing and keeps C2 guarded.
- `tests/unit/test_clean_architecture_migration_playbook.py` records this
  landing state and keeps Deferred MCP and core production wiring guarded.

Rollback command:

- `git revert <Candidate C1 implementation commit>`

Boundary confirmation for this landing:

- no bundled Web and MCP implementation
- no Candidate C2 implementation in this commit
- no dispatcher loop changes
- no `CTFState` ownership split
- no `CTFVerifier` proof behavior changes
- no ToolExecutor changes
- no WorkerPool/CrewOrchestrator changes
- no MCP production wiring
- no composition root changes
- no proof authority behavior changes
- no P5 implementation

#### Candidate C2 implementation landing record

Status: implementation landed for Candidate C control-decision.

Current approval fact:

- Candidate C control-decision: implementation landed

Target:

- `flaghunter/interface/web_control_decision.py::_task_blackboard_snapshot_for_decision`

Implementation summary:

- Candidate C2 now routes the Web control-decision blackboard snapshot rebuild
  through neutral `ChallengeBoardReadModel` and `build_task_board_projection`
  before merging task and explicit snapshots.
- The existing control-decision snapshot merge semantics remain compatible with
  the pre-switch output shape.
- The implementation commit modifies only Candidate C2 production helper code,
  Candidate C tests, and this playbook governance record.

Equivalence evidence:

- `tests/unit/interface/test_web_server.py::test_candidate_c_control_decision_snapshot_merge_fixture_before_switch`
  preserves rebuilt snapshot priority, fallback list fills, active-decision
  merge behavior, and recommended-action merge behavior.
- `tests/unit/interface/test_web_server.py::test_candidate_c_read_paths_use_neutral_projection_after_c2_lands`
  records both C1 and C2 landing state.
- `tests/unit/test_clean_architecture_migration_playbook.py` records this
  landing state and keeps Deferred MCP and core production wiring guarded.

Rollback command:

- `git revert <Candidate C2 implementation commit>`

Boundary confirmation for this landing:

- no bundled Web and MCP implementation
- no dispatcher loop changes
- no `CTFState` ownership split
- no `CTFVerifier` proof behavior changes
- no ToolExecutor changes
- no WorkerPool/CrewOrchestrator changes
- no MCP production wiring
- no composition root changes
- no proof authority behavior changes
- no P5 implementation

#### Deferred MCP implementation landing record

Status: implementation landed for Deferred MCP readback.

Current approval fact:

- Deferred MCP readback: implementation landed

Target:

- `flaghunter/mcp/server/mcp_tools.py::_append_blackboard_snapshot_lines`

Implementation summary:

- Deferred MCP now routes blackboard readback through neutral
  `ChallengeBoardReadModel` and `build_task_board_projection` before formatting
  the existing MCP readback lines.
- The existing MCP readback line text, ordering, and omission behavior remain
  compatible with the pre-switch output shape.
- The implementation commit modifies only the Deferred MCP readback helper,
  MCP readback tests, and this playbook governance record.

Equivalence evidence:

- `tests/unit/mcp/test_mcp_ingress_mode_contract.py::test_mcp_blackboard_readback_formatting_matches_candidate_a_projection`
  preserves representative facts, pending verification, active-decision,
  recommended-action, action-result, and surface-summary readback lines.
- `tests/unit/mcp/test_mcp_ingress_mode_contract.py::test_mcp_blackboard_readback_empty_and_malformed_inputs_are_quiet`
  preserves quiet omission behavior for empty, missing, or malformed inputs.
- `tests/unit/mcp/test_mcp_ingress_mode_contract.py::test_deferred_mcp_readback_uses_neutral_projection_after_approval`
  records the landing and requires the approved neutral projection wiring.

Rollback command:

- `git revert <Deferred MCP implementation commit>`

Boundary confirmation for this landing:

- no MCP task execution wiring changes
- no MCP router changes
- no dispatcher loop changes
- no `CTFState` ownership split
- no `CTFVerifier` proof behavior changes
- no ToolExecutor changes
- no WorkerPool/CrewOrchestrator changes
- no composition root changes
- no proof authority behavior changes
- no P5 implementation
- no crew/recovery changes

#### Candidate C pre-approval production switch guard

Status: retired by Candidate C1 and C2 implementation landings.

`tests/unit/interface/test_web_server.py` now guards
`flaghunter/interface/web_serialize_task.py::_serialize_task` and
`flaghunter/interface/web_control_decision.py::_task_blackboard_snapshot_for_decision`
against importing or calling neutral challenge board/read-model projection
helpers before Candidate C implementation approval landed.

Current approval fact:

- Candidate C serialize-task: implementation landed
- Candidate C control-decision: implementation landed

This guard changed across the C1 and C2 implementation commits that prove
old/new output equivalence for each affected call-site family.

Required after landing:

- import `flaghunter.application.challenge.board_read_model_service`
- call `build_task_board_projection`
- construct `ChallengeBoardReadModel`
- keep Deferred MCP production helpers out of these implementation commits

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

This fixture is not Deferred MCP approval. Candidate C serialize-task has
landed.

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

This fixture is not Deferred MCP approval. Candidate C control-decision has
landed.

Boundary confirmation for this fixture baseline:

- no production path switch
- no dispatcher loop changes
- no `CTFState` ownership split
- no `CTFVerifier` proof behavior changes
- no ToolExecutor changes
- no WorkerPool/CrewOrchestrator changes
- no MCP production wiring
- no proof authority behavior changes

#### Proof authority write surface characterization guard

Status: characterization guard recorded, no proof behavior changed.

`tests/unit/agents/test_p1_source_guards.py::test_p1_proof_authority_write_calls_stay_in_verifier_and_state_only`
now locks the current proof-authority write surface before any verifier,
state, dispatcher, or composition-root implementation split.

Current allowed proof-authority calls:

- `CTFVerifier._sync_flag_claim` -> `CTFState.upgrade_claim_to_verified`
- `CTFVerifier._append_flag_verification_record` -> `CTFState.append_verification_record`
- `CTFVerifier._ensure_result_trace` -> `CTFState.record_verification_receipt`

Current allowed proof-authority definitions:

- `flaghunter/agents/pa_agent/ctf_state.py` defines `upgrade_claim_to_verified`
- `flaghunter/agents/pa_agent/ctf_state.py` defines `append_verification_record`
- `flaghunter/agents/pa_agent/ctf_state.py` defines `record_verification_receipt`

The characterization intentionally keeps the current implementation locations
visible:

- `flaghunter/agents/pa_agent/verifier.py`
- `flaghunter/agents/pa_agent/ctf_state.py`

This is a source guard only. It does not approve moving proof ownership,
changing verifier decisions, or splitting state storage.

Boundary confirmation for this guard:

- no proof-authority behavior changes
- no `CTFState` ownership split
- no ToolExecutor changes
- no `CTFTaskDispatcher` flow changes
- no MCP production wiring
- no Web/CLI/TUI task wiring changes
- no composition root changes
- no P5 implementation
- no crew/recovery changes

#### Verified decision reference characterization guard

Status: characterization guard recorded, no proof behavior changed.

`tests/unit/agents/test_p1_source_guards.py::test_p1_verified_decision_references_stay_in_verifier_and_state_only`
now locks the current `VerificationDecision.VERIFIED` production reference
surface before any proof-authority implementation split.

Current allowed `VerificationDecision.VERIFIED` references:

- `CTFVerifier._append_flag_verification_record`
- `CTFVerifier._record_decision_for_result`
- `CTFState._has_sufficient_verified_record`

The characterization intentionally keeps the current implementation files
visible:

- `flaghunter/agents/pa_agent/verifier.py`
- `flaghunter/agents/pa_agent/ctf_state.py`

This guard allows verifier/state code to map and consume already-authoritative
verified decisions, but blocks presentation, dispatcher, task ingress, MCP,
tool execution, replay, and readback paths from introducing new direct
`VerificationDecision.VERIFIED` references.

Boundary confirmation for this guard:

- no proof-authority behavior changes
- no `CTFState` ownership split
- no ToolExecutor changes
- no `CTFTaskDispatcher` flow changes
- no MCP production wiring
- no Web/CLI/TUI task wiring changes
- no composition root changes
- no P5 implementation
- no crew/recovery changes

#### Proof authority port action unwired guard

Status: source guard recorded, no production wiring approved.

`tests/unit/agents/test_p1_source_guards.py::test_p1_proof_authority_port_actions_remain_unwired_outside_port_and_adapter`
now locks the proof authority port action methods as skeleton-only surfaces.

Current allowed proof authority port action definitions:

- `ProofAuthorityPort.append_proof_record`
- `ProofAuthorityPort.confirm_claim`
- `ProofAuthorityAdapter.append_proof_record`
- `ProofAuthorityAdapter.confirm_claim`

Current allowed files:

- `flaghunter/ports/proof_authority.py`
- `flaghunter/adapters/proof/proof_authority_adapter.py`

The guarded action names are:

- `append_proof_record`
- `confirm_claim`

This keeps the proof authority port and adapter skeleton available for a
future approved proof-authority boundary migration, while preventing accidental
production wiring or direct proof-authority action calls elsewhere.

Boundary confirmation for this guard:

- no proof-authority behavior changes
- no proof authority production wiring
- no `CTFState` ownership split
- no ToolExecutor changes
- no `CTFTaskDispatcher` flow changes
- no MCP production wiring
- no Web/CLI/TUI task wiring changes
- no composition root changes
- no P5 implementation
- no crew/recovery changes

#### Proof authority adapter import unwired guard

Status: source guard recorded, no production wiring approved.

`tests/unit/agents/test_p1_source_guards.py::test_p1_proof_authority_adapter_stays_unwired_from_production_imports`
now locks the proof authority adapter and authority port names as unwired
production surfaces.

Current allowed adapter skeleton files:

- `flaghunter/adapters/proof/__init__.py`
- `flaghunter/adapters/proof/proof_authority_adapter.py`

Guarded names:

- `ProofAuthorityAdapter`
- `ProofAuthorityPort`

This keeps the proof authority adapter skeleton importable for its adapter
tests and package re-export, while preventing presentation, application
services, entrypoints, MCP, dispatcher, state, verifier, runtime, or
composition-root-adjacent modules from importing or wiring it before explicit
proof-authority production approval.

Boundary confirmation for this guard:

- no proof-authority behavior changes
- no proof authority production wiring
- no `CTFState` ownership split
- no ToolExecutor changes
- no `CTFTaskDispatcher` flow changes
- no MCP production wiring
- no Web/CLI/TUI task wiring changes
- no composition root changes
- no P5 implementation
- no crew/recovery changes

#### Verifier adapter import unwired guard

Status: source guard recorded, no production wiring approved.

`tests/unit/agents/test_p1_source_guards.py::test_p1_verifier_adapter_stays_unwired_from_production_imports`
now locks the verifier adapter as an unwired production surface.

Current allowed verifier adapter skeleton files:

- `flaghunter/adapters/proof/__init__.py`
- `flaghunter/adapters/proof/verifier_adapter.py`

Guarded adapter name:

- `VerifierAdapter`

`VerifierPort` remains allowed through approved application-service ports; this
guard blocks only `VerifierAdapter` production imports or wiring before an
explicit Verifier/proof authority boundary implementation approval.

Boundary confirmation for this guard:

- no verifier production wiring
- no proof-authority behavior changes
- no proof authority production wiring
- no `CTFState` ownership split
- no ToolExecutor changes
- no `CTFTaskDispatcher` flow changes
- no MCP production wiring
- no Web/CLI/TUI task wiring changes
- no composition root changes
- no P5 implementation
- no crew/recovery changes

#### CTFVerifier legacy construction characterization guard

Status: characterization guard recorded, no verifier behavior changed.

`tests/unit/agents/test_p1_source_guards.py::test_p1_ctf_verifier_construction_stays_legacy_dispatcher_only`
now locks the current `CTFVerifier` production construction surface before any
verifier adapter, proof-authority boundary, dispatcher, or composition-root
wiring.

Current allowed production construction surface:

- `flaghunter/agents/pa_agent/ctf_dispatcher.py`
- `CTFTaskDispatcher.__init__`
- `CTFVerifier`

This confirms legacy dispatcher construction remains the only production construction surface.
It does not approve verifier production wiring, composition-root migration, or
proof-authority behavior changes.

Boundary confirmation for this guard:

- no verifier production wiring
- no proof-authority behavior changes
- no proof authority production wiring
- no `CTFState` ownership split
- no ToolExecutor changes
- no `CTFTaskDispatcher` flow changes
- no MCP production wiring
- no Web/CLI/TUI task wiring changes
- no composition root changes
- no P5 implementation
- no crew/recovery changes

#### Proof authority characterization readiness aggregate

Status: aggregate guard recorded, implementation not approved.

This aggregate keeps the proof-authority boundary characterization runway
visible as approval package evidence, not implementation approval.

Required characterization guards:

- Proof authority write surface characterization guard
- Verified decision reference characterization guard
- Proof authority port action unwired guard
- Proof authority adapter import unwired guard
- Verifier adapter import unwired guard
- CTFVerifier legacy construction characterization guard

Focused guard tests:

- `test_p1_proof_authority_write_calls_stay_in_verifier_and_state_only`
- `test_p1_verified_decision_references_stay_in_verifier_and_state_only`
- `test_p1_proof_authority_port_actions_remain_unwired_outside_port_and_adapter`
- `test_p1_proof_authority_adapter_stays_unwired_from_production_imports`
- `test_p1_verifier_adapter_stays_unwired_from_production_imports`
- `test_p1_ctf_verifier_construction_stays_legacy_dispatcher_only`

Verifier/proof authority boundary implementation remains unapproved. These
guards only prove the current write surface, verified-decision reference
surface, port action skeleton, adapter import skeleton, and legacy verifier
construction surface are characterized before a future explicit approval.

Boundary confirmation for this aggregate:

- no proof-authority behavior changes
- no proof authority production wiring
- no `CTFState` ownership split
- no ToolExecutor changes
- no `CTFTaskDispatcher` flow changes
- no MCP production wiring
- no Web/CLI/TUI task wiring changes
- no composition root changes
- no P5 implementation
- no crew/recovery changes

#### Web provenance/trace payload test debt characterization landing record

Status: characterization debt fixed for Web provenance and trace payload read paths.

Current approval fact:

- Web provenance/trace payload test debt characterization: implementation landed

Target:

- `flaghunter/interface/blackboard_lite.py`
- `tests/unit/interface/test_web_server.py`

Implementation summary:

- Web blackboard projection now preserves Web-only fact payload fields
  `artifactUrl` and `exploitType` after the neutral board projection step.
- This keeps source-leak and local-source exploit provenance visible in task
  detail payloads, trace payload summaries, and trace outcome event JSON.
- The fix is read-only payload projection work. It does not continue task
  ingress wiring and does not change execution, dispatcher, verifier, state,
  tool executor, MCP, or composition-root behavior.

Red test evidence:

- `tests/unit/interface/test_web_server.py` initially reported 10 existing
  failures in provenance/trace payload fixtures, including missing
  `artifactUrl`, missing local-source `exploitKind`, and trace summaries
  missing local-source exploit provenance.

Focused evidence:

- `tests/unit/interface/test_web_server.py::test_task_detail_surfaces_exploit_provenance_from_source_leak_observation`
- `tests/unit/interface/test_web_server.py::test_task_detail_surfaces_exploit_provenance_from_local_source_hint`
- `tests/unit/interface/test_web_server.py::test_build_trace_payload_projects_artifacts_checkpoint_and_outcomes_from_session_context`
- `tests/unit/interface/test_web_server.py::test_build_trace_payload_projects_dispatcher_started_outcome_event`
- `tests/unit/interface/test_web_server.py::test_build_trace_payload_projects_dispatcher_started_summary_with_local_source_exploit_truth`
- `tests/unit/interface/test_web_server.py::test_build_trace_payload_projects_control_action_outcome_events`
- `tests/unit/interface/test_web_server.py::test_build_trace_payload_surfaces_exploit_provenance_summary`
- `tests/unit/interface/test_web_server.py::test_build_trace_payload_keeps_local_source_hint_exploit_provenance_in_outcome_events`
- `tests/unit/interface/test_web_server.py::test_build_trace_payload_projects_verification_and_finish_summaries_with_local_source_exploit_truth`
- `tests/unit/interface/test_web_server.py::test_build_trace_payload_projects_recovery_decision_summary_with_local_source_exploit_truth`

Rollback command:

- `git revert <Web provenance/trace payload characterization implementation commit>`

Boundary confirmation for this landing:

- no Task ingress wiring expansion
- no MCP changes
- no ToolExecutor changes
- no `CTFVerifier` proof behavior changes
- no `CTFState` ownership split
- no `CTFTaskDispatcher` flow changes
- no composition root changes
- no proof authority behavior changes
- no P5 implementation
- no crew/recovery changes

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
