# FlagHunter Module Boundary Review v0.1

Date: 2026-07-04
Scope reviewed:

- `flaghunter/agents/pa_agent/ctf_dispatcher.py`
- `flaghunter/agents/pa_agent/ctf_state.py`
- `flaghunter/tools/executor.py`
- `flaghunter/agents/crew/`
- `flaghunter/mcp/server/`
- `flaghunter/interface/`
- `flaghunter/agents/pa_agent/task_dag_*.py`
- `flaghunter/agents/pa_agent/*readback*.py`
- `tests/unit/agents/test_p1_source_guards.py`

This review is docs-only. It does not propose changing dispatcher, crew, recovery, tool executor, or P1-P5 behavior in the current slice.

## 1. Findings First

### Added files

- `docs/dev/FlagHunter_Clean_Architecture_Development_Guidelines_v0.1_2026-07-04.md`
- `docs/dev/FlagHunter_Module_Boundary_Review_v0.1_2026-07-04.md`

No production code was changed.

### Current modularity score

Overall score: 5.5 / 10.

Reasoning:

- Contract/readback maturity: 7 / 10. P1-P5 surfaces use dataclasses, schema versions, projections, redaction, and source guards. This is the strongest part of the current architecture.
- Proof-authority boundary: 7 / 10. The source guards strongly protect verifier-only verified proof upgrades. The remaining weakness is that proof-related storage methods still live on `CTFState`, so the boundary is convention-plus-tests rather than a dedicated port.
- Dispatcher/Application separation: 4 / 10. `CTFTaskDispatcher` is a facade, coordinator host, state owner, verifier owner, capability owner, runtime/tool guard owner, audit/checkpoint/ledger owner, and chain mixin aggregate.
- State/Domain purity: 4 / 10. `CTFState` contains good contract-like dataclasses and validation, but also imports config/kill-chain policy, owns async locks, stores mutable run state, maintains task DAG stores, creates claims, appends verification records, upgrades claims, and serializes snapshots.
- Tool execution boundary: 4 / 10. `ToolExecutor` mixes execution, cache, M4 scope enforcement, cookie injection, stealth, flag scanning, missing-tool notes, provenance, and claim creation.
- Presentation separation: 5 / 10. Some web modules have been split into leaf read-model helpers, and `interface.initializer` is a shim over `session.initializer`; however CLI/Web/MCP still directly instantiate concrete dispatcher/runtime/agent flows.
- Composition root: 6 / 10. `flaghunter/session/initializer.py` is a useful shared composition root, but concrete assembly still appears in CLI, Web, MCP, and crew worker code.

### Key positive signals

- `CTFState.create_claim` rejects direct verified claims, and `upgrade_claim_to_verified` requires a passed, sufficient verification record.
- `CTFVerifier` is the apparent proof-authority path that appends verification records and upgrades claims.
- `tests/unit/agents/test_p1_source_guards.py` contains broad source guards for verified proof writes, control/ingress paths, executor/context surfacing, claim views, evidence snapshots, ledger readbacks, solve nodes, task DAG, crew paths, and replay audit readbacks.
- P3/P4/P5 read-side surfaces generally include explicit schema versions, dataclasses, redaction helpers, and proof-like field filtering.
- `flaghunter/session/initializer.py` centralizes a meaningful portion of component assembly and runtime selection.

## 2. Reviewed Boundary Facts

### Dispatcher

`flaghunter/agents/pa_agent/ctf_dispatcher.py` imports concrete notes/tool guard, harness ledger/checkpoint/artifact stores, profile, many chain mixins, coordinator, control receipts, audit infra, capability registry, recovery, reasoning, verifier, strategy registry, strategy memory, and planner modules. The class starts at `CTFTaskDispatcher` and inherits more than twenty mixins.

Important observed lines:

- Imports from tools/harness/knowledge/config/pa-agent internals: lines 30-110.
- `CTFTaskDispatcher` mixin aggregate: around lines 281-307.
- Constructor creates concrete `ToolGuard`, `RuntimeAuditedActions`, `AuditStore`, executors, `RecoveryController`, `StrategyRegistry`, `CapabilityRegistry`, `StrategyMemoryStore`, `ReasoningLayer`, `PlatformTaskOrchestrator`, `CTFCoordinator`, and `CTFVerifier`: around lines 315-397.
- Public `run` delegates to coordinator but still keeps the concrete dispatcher object as the service locator passed into the coordinator.

Assessment: the dispatcher is a pragmatic facade, not yet an application service. It is the highest-value place to introduce ports because it currently knows every important implementation.

### State

`flaghunter/agents/pa_agent/ctf_state.py` contains both contract-like dataclasses and mutable aggregate behavior.

Important observed lines:

- Claim/proof enums and dataclasses: around lines 53-303.
- `CTFState` mutable fields, including observations, artifacts, hypotheses, experiments, candidate/runtime/verified/rejected buckets, claims, verification records, execution traces, solve graph, task briefs, receipts, task DAG plan, phase budgets, and exploration logs: around lines 330-388.
- Config and policy imports: `config.constants`, `knowledge.kill_chain`, solve-node/task-DAG modules.
- `create_claim` forbids direct verified creation: around lines 695-760.
- `append_verification_record`: around lines 761-824.
- `upgrade_claim_to_verified`: around lines 826-859.
- Legacy `add_flag` still owns candidate/runtime/verified/rejected buckets: around line 1161.

Assessment: `CTFState` is the current domain aggregate, state store, claim store, proof record store, readback backing store, and snapshot serializer. This is workable for rapid iteration, but it makes clean boundary enforcement depend on source guards and conventions.

### Tool executor

`flaghunter/tools/executor.py` is an execution adapter plus policy coordinator plus state writer.

Important observed lines:

- Scope check, stealth, missing-tool, notes, provenance, flag scanning, and result cache are in the same module.
- `ToolExecutor.__init__` stores runtime and creates cache/semaphore/run id: around lines 591-609.
- `_ctf_state` reaches into `runtime.ctf_state` or `runtime.state`: around lines 638-642.
- `_record_tool_receipt` writes tool receipts into state by duck typing: around lines 644-680.
- `_link_discovered_flags_to_candidate_claims` creates non-verified claims from tool flag scans: around lines 682-733.
- `execute` performs validation, cache, M4 scope check, cookie injection from notes, stealth delays, actual tool execution, flag scanning, missing-tool handling, notes writes, retrospective writes, and finalization: around lines 761-1020.

Assessment: it should become an adapter behind `ToolRunnerPort`. Scope, cookie injection, stealth, provenance, notes, and claim side effects should be separate decorators/use cases around the port.

### Crew

`flaghunter/agents/crew/` has clean-ish local models, but orchestration still imports concrete implementations.

Important observed lines:

- `CrewOrchestrator` imports `ShadowGraph`, prompts, swarm bridge, crew tools, and `WorkerPool`.
- `WorkerPool` imports `FlagHunterAgent` and creates a concrete `LocalRuntime` internally.
- Crew tools close over a concrete `WorkerPool`.
- `swarm_bridge` imports M5 swarm link dynamically and reads preferred flag summaries from PA-agent claim views.

Assessment: crew is a natural adapter boundary. A `CrewBridgePort` can hide `WorkerPool`, `CrewOrchestrator`, swarm bridge, and worker runtime creation from application services.

### MCP server

`flaghunter/mcp/server/mcp_tools.py` currently combines transport-facing tool handlers, task registry, task execution, dispatcher construction, readback formatting, configuration mutation, event emission, and metrics/log retrieval.

Important observed lines:

- Imports presentation helpers from `interface.blackboard_lite`, `interface.control_contract`, and `interface.mode_router`.
- `_make_agent` constructs concrete runtime and `FlagHunterAgent`: around lines 211-229.
- `_drive_task` imports and constructs `CTFTaskDispatcher` for CTF mode: around lines 771-829.
- MCP handler functions directly manage config, task lifecycle, conversation history, memory, logs, and metrics.

Assessment: MCP should be a presentation adapter. It should depend on application services and read models, not dispatcher constructors or state internals.

### UI / Presentation

`flaghunter/interface/` is partly decomposed but still crosses into application and infrastructure.

Important observed lines:

- `interface.initializer` is a compatibility shim over `session.initializer`, which is a good composition-root direction.
- `cli.py` imports/constructs `CTFTaskDispatcher` and `CrewOrchestrator` in command execution paths.
- `web_server.py` imports many leaf helper modules, directly imports `build_workspace_run_context`, constructs `CTFTaskDispatcher`, loads settings, creates tasks, reads files, aggregates session context, and exposes handlers.
- `blackboard_lite.py` imports `CTFState` directly and derives presentation snapshots from raw state/session structures.

Assessment: Web/CLI/TUI/MCP are not yet read-model-only. Some helper extraction has reduced cycles, but presentation still understands too much of business implementation.

### P1-P5 read-side contract surfaces

Observed surfaces include:

- P1 claim views and proof guards: `claim_views.py`, `control_receipts.py`, source guards.
- P2 evidence/audit/ledger readbacks: `audit_views.py`, `evidence_snapshot.py`, `ledger_event_views.py`.
- P3 solve node and solve readback: `solve_node.py`, `p3_solve_readback.py`.
- P4 task DAG contracts/readbacks/crew/local/recovery/replay audit modules.
- P5 pre-eval/eval artifacts in tests/docs.

Strengths:

- Versioned schema constants are common.
- Dataclasses are common.
- Builders normalize dict/dataclass inputs.
- Many readback modules sanitize/redact raw payloads.
- Source guards forbid proof writes and execution imports in read-side modules.

Risks:

- Many contract/readback modules live under `agents/pa_agent`, so consumers import through an implementation package rather than a domain/contracts package.
- Some read models import `CTFState` directly, tying read contracts to the mutable state aggregate.
- Guarding uses a lot of literal-token checks. This is useful but brittle and may miss aliased calls or false-positive on comments unless AST scopes continue expanding.
- Several modules intentionally split sensitive tokens such as `"verified" + "_flags"` to avoid source-guard strings. This is acceptable for guard compatibility but shows that proof-like filtering wants a shared contract helper rather than per-file repetition.

## 3. High Coupling Points And Risks

1. Dispatcher as service locator.
   Risk: any small change to verification, recovery, crew, audit, checkpoint, task DAG, runtime, or tool execution can require dispatcher edits and broad regression testing.

2. `CTFState` as all-in-one domain/state/proof/snapshot object.
   Risk: read-only surfaces and proof-writing surfaces share the same class. This increases the chance of accidental proof escalation or unintended mutation from presentation/readback paths.

3. Tool executor writes receipts and claims by reaching through runtime.
   Risk: execution adapter controls domain side effects implicitly. It is hard to test tool execution independently from state mutation, notes, provenance, and proof guard behavior.

4. Presentation constructs concrete engines.
   Risk: CLI/Web/MCP can diverge in behavior because each path wires dispatcher, handoff, challenge context, and runtime details slightly differently.

5. Crew worker runtime creation is internal to worker pool.
   Risk: crew cannot be tested or migrated as a pure application boundary; runtime choice and worker execution are coupled.

6. MCP server is a multi-role module.
   Risk: handler changes can accidentally alter task execution semantics, config mutation, readback shape, and lifecycle behavior together.

7. Contract/readback modules are in implementation package.
   Risk: stable read-side schema is harder for other modules to consume without depending on PA-agent internals.

8. Repeated redaction/proof-like filtering.
   Risk: inconsistent redaction and filtering across task DAG, replay audit, crew bridge, evidence snapshots, and UI readbacks.

9. Source guards are strong but local.
   Risk: a new module can bypass existing tests unless every new contract/use case/adapter gets its own guard entry and ownership checklist.

## 4. Recommended Target Directory And Naming

Incremental target, not a single refactor:

```text
flaghunter/
  domain/
    ctf/
      contracts/
        claims.py
        proof.py
        state_snapshot.py
        solve_node.py
        task_dag.py
        crew.py
        audit.py
        evidence.py
        control.py
      validation/
        redaction.py
        proof_like_fields.py
  application/
    ctf/
      solve_challenge.py
      verify_candidate.py
      record_tool_receipt.py
      build_evidence_snapshot.py
      run_task_dag.py
      dispatch_crew_task.py
      recover_from_dag_result.py
  ports/
    tool_runner.py
    runtime_actions.py
    verifier.py
    proof_authority.py
    state_store.py
    claim_store.py
    audit_store.py
    artifact_store.py
    checkpoint_store.py
    crew_bridge.py
    task_dag_runner.py
    read_model_store.py
  adapters/
    runtime/
      local_runtime_adapter.py
      docker_runtime_adapter.py
      ssh_runtime_adapter.py
    tools/
      tool_executor_adapter.py
    crew/
      worker_pool_adapter.py
    mcp/
      mcp_adapter.py
    storage/
      file_ledger_adapter.py
      file_checkpoint_adapter.py
      file_artifact_registry_adapter.py
  presentation/
    cli/
    tui/
    web/
    mcp/
    reports/
  composition/
    root.py
```

During migration, keep compatibility re-export modules in old paths so existing tests and entrypoints remain stable.

## 5. First Safe Ports To Extract

These can be added as Protocol-only skeletons without changing behavior:

1. `ToolRunnerPort`
   - Method: `run_tool(name, arguments) -> ToolRunReceipt`.
   - Adapter later wraps `ToolExecutor.execute`.
   - Initial value: lets application code stop importing `ToolExecutor`.

2. `StateStorePort`
   - Methods: `load_snapshot(run_id)`, `save_snapshot(run_id, snapshot)`.
   - Adapter later wraps checkpoint/session state persistence.
   - Initial value: separates state serialization from state mutation.

3. `ClaimStorePort`
   - Methods: `create_candidate_claim`, `find_claims_by_kind`, `append_evidence_trace`.
   - Must not include `upgrade_claim_to_verified`.
   - Initial value: lets tool/model/control paths create only non-verified claims.

4. `ProofAuthorityPort`
   - Method: `upgrade_to_verified(claim_id, verification_record_id)`.
   - Adapter backed only by verifier/proof-authority code.
   - Initial value: makes proof writes reviewable and source-guardable.

5. `VerifierPort`
   - Method: `verify_flag_candidate(candidate, evidence) -> VerificationReceipt`.
   - Adapter wraps `CTFVerifier`.
   - Initial value: separates verification orchestration from state storage.

6. `AuditStorePort`
   - Methods: `append_event`, `query_events`.
   - Adapter wraps session ledger/audit stores.
   - Initial value: readbacks stop depending on concrete ledger/event files.

7. `ArtifactStorePort`
   - Methods: `register_artifact`, `get_artifact`.
   - Adapter wraps artifact registry.
   - Initial value: dispatcher does not directly own artifact registry.

8. `CheckpointStorePort`
   - Methods: `create_checkpoint`, `load_checkpoint`.
   - Adapter wraps `CheckpointStore`.
   - Initial value: resume/handoff no longer needs presentation-specific checkpoint reads.

9. `CrewBridgePort`
   - Method: `dispatch_task(request) -> CrewTaskReceipt`.
   - Adapter wraps `CrewOrchestrator`, `WorkerPool`, and swarm bridge.
   - Initial value: application services can ask for crew execution without importing crew internals.

10. `TaskDAGRunnerPort`
    - Method: `run_ready_task(plan, state_snapshot) -> TaskDAGReceipt`.
    - Adapter initially delegates to existing local shim/crew bridge.
    - Initial value: task DAG contracts become runnable without knowing dispatcher internals.

The first implementation patch should add only Protocols, contract dataclasses, and source guards. Existing production code can keep using current classes until adapter wrappers are added.

## 6. Development Guideline Summary

The companion guidelines document defines the desired rule:

- Domain/Contracts are dataclass/schema/enum/Protocol plus pure validation only.
- Use Cases/Application Services orchestrate business actions through ports.
- Ports define interfaces only.
- Adapters contain concrete runtime, Docker, MCP, worker pool, and file/storage implementations.
- Presentation consumes read models and command DTOs, not business internals.
- Composition Root is the only place where real implementations are assembled.
- Proof authority belongs only to verifier/proof-authority code.
- Every new module boundary needs a contract, builder/use case, boundary tests, and source guard.
- Multi-developer work crosses modules only through stable schema/Protocol.

## 7. Phased Route

### Phase 0: Docs-only

- Land these two docs.
- Add no production behavior.
- Socialize proof-authority and contract/source-guard rules.

### Phase 1: Ports skeleton

- Add `flaghunter/ports/` Protocol modules.
- Add contract-only tests proving no implementation imports.
- Add source guards for ports and future domain/contracts package.
- Do not wire them into dispatcher yet.

### Phase 2: Contract relocation with compatibility re-exports

- Copy or move stable P1-P5 contracts/readbacks into `flaghunter/domain/ctf/contracts/`.
- Keep old `agents/pa_agent/*` import paths as re-export shims.
- Start with pure readback modules: solve-node/task-DAG/audit/evidence surfaces.
- Do not move `CTFState` as a whole.

### Phase 3: Adapter wrappers

- Wrap current `ToolExecutor` as `ToolRunnerPort`.
- Wrap `CTFVerifier` as `VerifierPort` and `ProofAuthorityPort`.
- Wrap `WorkerPool`/`CrewOrchestrator` as `CrewBridgePort`.
- Wrap ledger/checkpoint/artifact stores as storage/audit/artifact ports.
- Preserve current call sites; add tests for wrappers.

### Phase 4: Application services

- Extract small use cases:
  - record tool receipt
  - build evidence snapshot
  - verify candidate flag
  - dispatch crew task
  - run one task DAG node
- Move only one call site at a time.
- Keep dispatcher public behavior identical.

### Phase 5: Composition root

- Extend `session.initializer` or introduce `composition/root.py`.
- Ensure CLI/Web/MCP/TUI receive a component bundle.
- Remove concrete dispatcher/runtime/worker construction from presentation modules one route at a time.

### Phase 6: Source guards

- Expand `test_p1_source_guards.py` into boundary-specific files:
  - `test_contract_source_guards.py`
  - `test_ports_source_guards.py`
  - `test_presentation_source_guards.py`
  - `test_proof_authority_source_guards.py`
  - `test_adapter_boundary_guards.py`
- Keep proof guards strict: only verifier/proof-authority can upgrade verified proof.

## 8. AGENTS.md Patch Recommendation

Do not edit root `AGENTS.md` in this worktree while commit-split threads are active. Suggested future addition:

```markdown
## Clean Architecture Boundary Rule

New FlagHunter modules must follow the Domain/Contracts -> Application Services -> Ports -> Adapters -> Presentation dependency rule. Contracts are dataclass/schema/Protocol-only and may not import runtime/tool executor/UI/storage. Presentation consumes read models. Concrete implementations are wired only in the composition root. Verified proof can only be upgraded by verifier/proof-authority code; candidates, controls, tools, model outputs, state, handoff, crew, replay, audit, and eval artifacts are not proof authorities. Every module boundary requires a contract, builder/use case, boundary tests, and source guard.
```

## 9. Verification Plan

Because this slice is docs-only, the relevant checks are:

- Confirm only the two docs were added by this thread.
- Run P1 source guards to ensure existing proof-boundary tests still pass in this worktree.
- Run `git diff --cached --stat` and confirm nothing is staged.

Commands:

```bash
pytest tests/unit/agents/test_p1_source_guards.py
git diff --cached --stat
git status --short --branch
```

Results should be recorded in the final handoff.
