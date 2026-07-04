# FlagHunter Clean Architecture Development Guidelines v0.1

Date: 2026-07-04
Status: draft for incremental adoption
Scope: module boundaries, contracts, ports/adapters, presentation read models, proof authority, source guards, domain-neutral public naming

## 1. North Star

FlagHunter should converge toward a clean, testable architecture where the core platform is a general challenge, competition, and task agent framework. Security and CTF workflows remain supported use cases, but they should live behind adapters, strategy packs, fixtures, and compatibility shims rather than defining the vocabulary of the core architecture.

The dependency rule is:

```text
Presentation -> Application Services -> Domain/Contracts
             -> Ports
Adapters     -> Ports + external systems
Composition Root wires concrete implementations
```

Inner layers must not import outer layers. If a lower-level module needs an effect, it receives a Protocol/port rather than importing a concrete runtime, tool executor, UI notifier, storage class, MCP server, or worker pool.

## 1.1 Domain-Neutral Public Naming

New public architecture contracts should use domain-neutral names. Prefer `challenge`, `competition`, `task`, `run`, `agent`, `worker`, `tool`, `claim`, `evidence`, `proof`, `artifact`, `receipt`, `trace`, `review`, `read model`, `checkpoint`, `policy`, and `strategy`.

Avoid new public core package/module/class/function/schema names containing security-specific terms such as `ctf`, `pentest`, `exploit`, `vulnerability`, `hacking`, `attack`, or `redteam`.

Existing legacy names remain implementation facts. Do not mass-rename historical modules such as `ctf_dispatcher.py` or `ctf_state.py` in unrelated slices. Treat them as legacy implementation or adapter details until an explicit migration introduces neutral contracts plus compatibility shims.

Detailed naming rules live in `docs/dev/FlagHunter_Domain_Neutral_Naming_Policy_v0.1_2026-07-04.md`.

## 2. Target Layers

### Domain / Contracts

Domain/Contracts define the stable vocabulary and invariants of FlagHunter.

Allowed:

- `dataclass` value objects and read models.
- `Enum` values for bounded vocabulary.
- `Protocol` interfaces when a caller needs an abstract capability.
- `SCHEMA_VERSION` constants and explicit `schemaVersion` fields in serialized payloads.
- Pure validation, normalization, projection, redaction, and deterministic builders.
- Serialization helpers such as `to_dict`, `from_dict`, and `build_*_readback`.

Forbidden:

- Importing runtime implementations.
- Importing `ToolExecutor`, tool registry implementations, tool modules, or shell/browser adapters.
- Importing TUI/CLI/Web/MCP presentation modules.
- Importing storage implementations such as filesystem ledgers, checkpoint stores, artifact registries, or notes stores.
- Reading environment variables directly.
- Network, subprocess, filesystem writes, Playwright/browser calls, Docker, SSH, MCP transport, or UI notification side effects.
- Minting verified proof unless the contract is explicitly the verifier/proof-authority contract.

Contract modules should be boring by design. A good contract file can be imported by every other layer without starting services, reading local files, loading models, or changing state outside the passed object.

Recommended names:

```text
flaghunter/domain/challenge/contracts/claims.py
flaghunter/domain/challenge/contracts/proof.py
flaghunter/domain/challenge/contracts/solve_node.py
flaghunter/domain/challenge/contracts/task_dag.py
flaghunter/domain/challenge/contracts/audit.py
flaghunter/domain/challenge/contracts/control.py
flaghunter/domain/challenge/contracts/read_models.py
```

### Use Cases / Application Services

Use cases orchestrate business actions. They can coordinate domain contracts and ports, but they should not own concrete infrastructure.

Allowed:

- Pure or side-effect-light orchestration.
- Calling injected ports such as `ToolRunnerPort`, `VerifierPort`, `StateStorePort`, `CrewBridgePort`, and `AuditStorePort`.
- Returning explicit result dataclasses/read models.
- Owning transaction shape, retry policy at the business level, and workflow decisions.

Forbidden:

- Importing `LocalRuntime`, `DockerRuntime`, `SSHRuntime`, `ToolExecutor`, `WorkerPool`, `MCPRouter`, TUI widgets, or concrete file stores.
- Reaching into `runtime.ctf_state` by duck typing.
- Writing proof state directly except through a verifier/proof-authority port.

Recommended names:

```text
flaghunter/application/challenge/solve_challenge.py
flaghunter/application/challenge/record_tool_receipt.py
flaghunter/application/challenge/build_evidence_snapshot.py
flaghunter/application/challenge/run_task_dag.py
flaghunter/application/challenge/dispatch_worker_task.py
```

### Ports

Ports define required capabilities. They contain no implementation.

Example direction:

```python
from typing import Any, Protocol


class ToolRunnerPort(Protocol):
    async def run_tool(self, name: str, arguments: dict[str, Any]) -> "ToolRunReceipt":
        ...


class VerifierPort(Protocol):
    async def review_claim(self, claim_id: str, evidence: "EvidenceBundle") -> "VerificationReceipt":
        ...


class StateStorePort(Protocol):
    def get_state(self, run_id: str) -> "RunStateSnapshot":
        ...

    def save_state(self, run_id: str, snapshot: "RunStateSnapshot") -> None:
        ...
```

First-class ports FlagHunter should introduce before moving concrete code:

- `ToolRunnerPort`: execute a named tool and return a receipt/read model.
- `RuntimeActionPort`: HTTP/browser/shell operations at the runtime-action level.
- `VerifierPort`: ask proof authority to review a claim against evidence.
- `ProofAuthorityPort`: the only writer allowed to upgrade to verified proof.
- `StateStorePort`: load/save state snapshots.
- `ClaimStorePort`: create non-verified claims, append verifier records, read claim views.
- `AuditStorePort`: append/query audit events.
- `ArtifactStorePort`: register/query artifacts.
- `CheckpointStorePort`: create/load checkpoints.
- `CrewBridgePort`: hand a task to crew/worker execution and return a receipt.
- `TaskDAGRunnerPort`: run or simulate a DAG node without knowing worker/runtime details.
- `ReadModelStorePort`: expose presentation-ready read models.

### Adapters

Adapters implement ports with concrete infrastructure.

Examples:

```text
flaghunter/adapters/runtime/local_runtime_adapter.py
flaghunter/adapters/runtime/docker_runtime_adapter.py
flaghunter/adapters/runtime/ssh_runtime_adapter.py
flaghunter/adapters/tools/tool_executor_adapter.py
flaghunter/adapters/mcp/mcp_adapter.py
flaghunter/adapters/crew/worker_pool_adapter.py
flaghunter/adapters/storage/file_ledger_adapter.py
flaghunter/adapters/storage/file_checkpoint_adapter.py
flaghunter/adapters/audit/session_ledger_adapter.py
flaghunter/adapters/artifacts/artifact_registry_adapter.py
```

Adapters may import external libraries, local runtimes, filesystem stores, MCP transports, worker pools, notifier bridges, and settings. They must return contract/read-model types rather than leaking concrete objects upward.

### Presentation

Presentation includes CLI, TUI, Web UI, MCP server handlers, and reports.

Rules:

- Presentation consumes read models, command DTOs, and application service results.
- Presentation may format, filter, paginate, and render.
- Presentation must not own proof-upgrade decisions.
- Presentation must not directly mutate domain state.
- Presentation must not instantiate business engines except through the composition root.
- Presentation may pass user intent to application services, but should not know implementation details such as dispatcher chain mixins, tool-guard internals, or state mutation methods.

MCP is presentation plus transport. Its tools should be thin handlers over use cases and read models.

### Composition Root

There should be one primary place where real implementations are wired together.

Current good direction: `flaghunter/session/initializer.py` is already the shared assembly area for agent components and runtimes, with `flaghunter/interface/initializer.py` acting as a compatibility shim.

Target:

```text
flaghunter/composition/root.py
flaghunter/session/initializer.py  # compatibility/import facade during migration
```

Responsibilities:

- Build settings.
- Select runtime adapter.
- Build LLM/provider adapter.
- Build tool runner adapter.
- Build verifier/proof authority.
- Build storage adapters.
- Build crew bridge adapter.
- Build application services.
- Return a typed component bundle.

Forbidden outside composition root:

- New concrete `LocalRuntime`, `DockerRuntime`, `SSHRuntime`.
- New concrete legacy dispatcher implementations such as `CTFTaskDispatcher`.
- New concrete `WorkerPool`.
- New concrete file ledger/checkpoint/artifact stores.
- Direct global settings mutation except in explicit configuration use cases.

## 3. Proof Authority Rule

Proof authority is a hard boundary.

Only verifier/proof-authority code may upgrade a claim or flag into verified proof.

The following are never proof authorities:

- Candidate flag scanners.
- Control decisions.
- Tool outputs.
- Model/LLM messages.
- State reconstruction.
- Handoff envelopes.
- Budget/stopping decisions.
- Solve nodes.
- Crew worker receipts.
- Replay audit artifacts.
- Audit readbacks.
- Eval artifacts.
- Presentation selectors such as `verifiedFlag`.

Allowed proof flow:

```text
candidate/control/tool/model signal
  -> non-verified claim or receipt
  -> verifier/proof authority validates evidence
  -> verification record with sufficient_for_upgrade
  -> verified claim/proof upgrade
  -> read models consume verified proof as selector/read-only data
```

Implementation guardrails:

- `create_claim(level="verified")` must remain forbidden.
- Direct legacy `add_flag(level="verified")` writes must stay verifier-only until legacy buckets are retired.
- Read-side modules may display verified proof already produced by proof authority, but must not create, upgrade, or infer it.
- Any new module that mentions verification must have source guards proving it cannot emit `verification_decision`, call `append_verification_record`, call `upgrade_claim_to_verified`, or write verified legacy buckets unless it is the verifier/proof-authority module.

## 4. Module Development Contract

Every new module or extracted boundary should ship with four things:

1. Contract: dataclasses/enums/schema versions/Protocol definitions.
2. Builder or use case: deterministic `build_*`, `normalize_*`, `record_*`, or `run_*` entrypoint.
3. Boundary tests: behavior tests for the public contract/use case.
4. Source guard: AST/text guard for forbidden imports, forbidden proof writes, and forbidden side effects.

Minimum source guard categories:

- Contract guard: no runtime/tool executor/UI/storage imports.
- Proof guard: no verified proof writes outside proof authority.
- Side-effect guard: no subprocess/browser/network/filesystem writes in contracts/read models.
- Presentation guard: UI/MCP/report modules consume read models or application service ports.
- Adapter guard: adapters implement ports and do not leak concrete return types across stable boundaries.

## 5. Stable Schema Rules

All cross-module data surfaces must be explicit, stable, and versioned.

Rules:

- Use `schemaVersion` in every serialized payload.
- Keep schema constants close to the dataclass/read-model builder.
- Prefer additive changes.
- Never rename or remove fields without a migration shim.
- Keep redaction logic in the contract/read-model builder when the field can contain raw HTTP bodies, secrets, cookies, tokens, flags, paths, or tool output.
- When a payload crosses presentation, MCP, crew, replay, audit, or eval boundaries, it must be serializable by `dict/list/str/int/float/bool/None`.

## 6. Multi-Developer Ownership

Module ownership should follow stable contracts, not implementation internals.

Rules:

- Each module owner maintains their own contract, use case, adapter, boundary tests, and source guards.
- Cross-module calls use stable schema/Protocol only.
- Direct imports across sibling implementation modules are temporary debt and should be documented with a migration note.
- A module owner may extend their contract additively, but cannot make another owner import their adapter.
- Breaking schema changes need version bump and migration tests.
- Proof authority changes require review from the verifier/proof owner.
- Presentation changes cannot introduce new business authority.

Recommended ownership map:

| Area | Owner Surface | Stable Boundary |
| --- | --- | --- |
| Claim/proof | verifier/proof owner | `ProofAuthorityPort`, claim/proof contracts |
| Tool execution | tools/runtime owner | `ToolRunnerPort`, tool receipts |
| State snapshots | state owner | `StateStorePort`, state snapshot/read models |
| Crew | crew owner | `CrewBridgePort`, crew receipts |
| MCP | integration owner | MCP handler DTOs + application services |
| UI/report | presentation owner | read models only |
| Task DAG | task orchestration owner | DAG contracts + `TaskDAGRunnerPort` |
| Audit/replay | audit owner | audit event/readback contracts |

## 7. Migration Discipline

Do not start with a large production refactor. Use this order:

1. Docs-only: document current ownership, target layering, and forbidden dependencies.
2. Ports skeleton: add Protocol files and source guards without changing runtime behavior.
3. Neutral domain contracts: introduce `domain/challenge` contracts before relocating legacy security/CTF contracts.
4. Adapter wrappers: wrap existing implementations behind ports while preserving call sites.
5. Application services: move orchestration behind use cases one entrypoint at a time.
6. Composition root: move concrete object creation into one assembly function.
7. Presentation migration: CLI/TUI/MCP/Web call use cases/read models, not concrete engines.
8. Source guard expansion: enforce each boundary as it becomes real.

Stop after every slice with tests. Do not combine proof changes, dispatcher-loop changes, crew migration, and presentation migration in the same patch.

## 8. Patch Suggestion For Root AGENTS.md

Do not apply this automatically while other commit-split threads are active. If/when the root development standard is updated, add a short section like:

```markdown
## Clean Architecture Boundary Rule

New FlagHunter modules must follow the Domain/Contracts -> Application Services -> Ports -> Adapters -> Presentation dependency rule. New public contracts and ports use domain-neutral challenge/task/claim/evidence/proof naming; legacy CTF/security names are adapter or compatibility details until explicitly migrated. Contracts are dataclass/schema/Protocol-only and may not import runtime/tool executor/UI/storage. Presentation consumes read models. Concrete implementations are wired only in the composition root. Verified proof can only be upgraded by verifier/proof-authority code; candidates, controls, tools, model outputs, state, handoff, crew, replay, audit, and eval artifacts are not proof authorities. Every module boundary requires a contract, builder/use case, boundary tests, and source guard.
```

## 9. PR Checklist

Before opening a PR for boundary work:

- The changed module declares its layer.
- New public core names follow the domain-neutral naming policy.
- Public payloads have `schemaVersion`.
- New cross-module calls use Protocol/schema, not concrete implementation imports.
- Contracts do not import runtime/tool executor/UI/storage.
- Presentation uses read models or use cases.
- Verified proof writes are verifier/proof-authority only.
- Source guards cover forbidden imports and proof writes.
- Tests include at least one behavior test for the contract/use case.
- No unrelated dispatcher/crew/recovery/tool-executor loop changes are mixed in.
- Migration notes identify what remains temporary.
