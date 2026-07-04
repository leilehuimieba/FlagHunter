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

The completed skeletons do not connect production call sites and do not change
the dispatcher loop, `CTFState`, `CTFVerifier`, `ToolExecutor`, crew runtime,
MCP production wiring, or composition root behavior.

### Phase 4 verification baseline

Focused Phase 4 regression should include:

```powershell
.\.venv\Scripts\python.exe -m pytest tests/unit/test_import_layers.py tests/unit/agents/test_p1_source_guards.py tests/unit/agents/test_p1_claim_invariants.py tests/unit/tools/test_finish_control_receipt.py tests/unit/agents/test_p2_audit_export.py tests/unit/agents/test_p2_evidence_snapshot.py tests/unit/agents/test_p2_ledger_event_readback.py tests/unit/agents/test_p4_task_dag_plan_schema.py tests/unit/agents/test_p4_task_dag_ready_selector.py tests/unit/agents/test_p4_task_dag_replay_audit_bundle.py tests/unit/test_ports_contracts.py tests/unit/test_domain_challenge_contracts.py tests/unit/agents/test_phase2b_compatibility_shims.py tests/unit/test_adapter_boundary_skeleton.py tests/unit/test_tool_runner_adapter.py tests/unit/test_runtime_action_adapter.py tests/unit/test_read_model_store_adapter.py tests/unit/test_state_store_adapter.py tests/unit/test_audit_store_adapter.py tests/unit/test_artifact_store_adapter.py tests/unit/test_checkpoint_store_adapter.py tests/unit/test_claim_store_adapter.py tests/unit/test_verifier_adapter.py tests/unit/test_proof_authority_adapter.py tests/unit/test_crew_bridge_adapter.py tests/unit/test_task_dag_runner_adapter.py tests/unit/test_application_challenge_snapshot_service.py tests/unit/test_application_task_receipt_service.py tests/unit/test_application_evidence_snapshot_service.py tests/unit/test_application_claim_review_service.py tests/unit/test_application_tool_receipt_service.py tests/unit/test_application_worker_task_service.py -q
```

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
