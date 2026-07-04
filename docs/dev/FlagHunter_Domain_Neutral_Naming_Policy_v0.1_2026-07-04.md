# FlagHunter Domain-Neutral Naming Policy v0.1

Date: 2026-07-04
Status: active guidance for new public architecture work
Scope: public contracts, ports, domain packages, adapters, docs, tests, future migration tasks

## 1. Direction

FlagHunter should evolve into a general challenge, competition, and task agent framework.

Security and CTF workflows remain important supported use cases, but they should become adapter packs, strategy packs, fixtures, and compatibility surfaces rather than the vocabulary of the core architecture.

The core platform vocabulary should describe work in terms of:

- challenge
- competition
- task
- run
- agent
- worker
- tool
- claim
- evidence
- proof
- artifact
- receipt
- trace
- review
- read model
- checkpoint
- policy
- strategy

This makes the project easier to reuse for different competitions, evaluation harnesses, tool-augmented agents, local task runners, and future plugin systems.

## 2. Public Naming Rule

New public architecture contracts should use domain-neutral names.

Avoid introducing new public package, module, class, function, method, schema, fixture, and doc names containing security-specific terms such as:

- `ctf`
- `pentest`
- `exploit`
- `vulnerability`
- `hacking`
- `attack`
- `redteam`

Allowed exceptions:

- Existing legacy paths and classes that already contain these terms.
- Compatibility shims that preserve old import paths.
- Adapter or plugin modules whose explicit purpose is a security/CTF integration.
- Historical docs, writeups, fixtures, and benchmark records that describe actual CTF/security work.

When in doubt, name the core contract neutrally and put domain-specific wording in the adapter.

Examples:

| Prefer | Avoid for new core contracts |
| --- | --- |
| `flaghunter/domain/challenge/contracts/claims.py` | `flaghunter/domain/ctf/contracts/claims.py` |
| `flaghunter/application/challenge/solve_challenge.py` | `flaghunter/application/ctf/solve_challenge.py` |
| `review_claim(...)` | `verify_flag_claim(...)` |
| `TaskDAGRunnerPort` | `CTFAttackRunnerPort` |
| `ChallengeAdapter` | `PentestAdapter` for core code |
| `ArtifactStorePort` | `ExploitStorePort` for core code |

## 3. Legacy Naming Rule

Do not mass-rename existing legacy modules as part of unrelated work.

Current paths such as `flaghunter/agents/pa_agent/ctf_state.py`, `flaghunter/agents/pa_agent/ctf_dispatcher.py`, and historical CTF docs remain valid until a planned migration slice creates neutral contracts and compatibility shims.

Legacy CTF/security names are treated as adapter or legacy implementation details until explicitly migrated.

The safe migration pattern is:

1. Add neutral contract or port first.
2. Add tests proving the neutral surface has no concrete dependency.
3. Add an adapter that wraps the existing legacy implementation.
4. Move one call site at a time to the neutral contract.
5. Keep the old import path as a shim while downstream code migrates.
6. Remove or deprecate the old name only after compatibility users are accounted for.

## 4. Contract And Port Naming

The first clean-architecture extraction should use neutral public ports:

- `ToolRunnerPort`
- `RuntimeActionPort`
- `VerifierPort`
- `ProofAuthorityPort`
- `StateStorePort`
- `ClaimStorePort`
- `AuditStorePort`
- `ArtifactStorePort`
- `CheckpointStorePort`
- `CrewBridgePort`
- `TaskDAGRunnerPort`
- `ReadModelStorePort`

Method names should also stay neutral:

- `run_tool`
- `run_action`
- `review_claim`
- `append_proof_record`
- `confirm_claim`
- `load_snapshot`
- `save_snapshot`
- `append_event`
- `register_artifact`
- `dispatch_task`
- `run_task`
- `get_read_model`

Core proof contracts should talk about claims, evidence, records, and proof. They should not talk about flags except in a legacy adapter or security-specific plugin.

## 5. Documentation Rule

New architecture docs should separate:

- Core framework vocabulary: neutral challenge/task/claim/evidence/proof terms.
- Current implementation facts: may name existing legacy classes exactly when reviewing the current code.
- Security/CTF domain packs: domain-specific adapters, strategies, tests, and historical records.

For reviews, use both names when needed:

```text
Legacy implementation: CTFTaskDispatcher
Target boundary: Challenge application service behind neutral ports
```

This keeps the docs honest without letting historical implementation names define the future architecture.

## 6. Future Migration Tasks

The future architecture backlog should include these explicit tasks:

1. Ports skeleton uses neutral names only.
2. New domain contracts live under a neutral package such as `flaghunter/domain/challenge/contracts/`.
3. Security/CTF-specific behavior moves behind adapters, strategy packs, or compatibility facades.
4. Existing `ctf_*` modules are migrated only through compatibility shims and focused tests.
5. Import/source guards enforce neutral naming for new core public contract packages.
6. Presentation layers consume read models and use cases with neutral DTO names.
7. Tool packs expose capabilities through generic tool metadata, not core security vocabulary.
8. Docs and AGENTS instructions continue to state that proof authority is domain-neutral: claims become proof only through proof authority, regardless of challenge type.

## 7. Review Checklist

Before accepting a new architecture or boundary PR, check:

- New core public names are domain-neutral.
- No new core package path contains `ctf`, `pentest`, `exploit`, `vulnerability`, `hacking`, `attack`, or `redteam`.
- Any domain-specific term is isolated to an adapter, plugin, fixture, benchmark, compatibility shim, or historical doc.
- Legacy imports are not expanded to new callers when a neutral port or contract exists.
- The PR does not mix naming migration with behavior changes.
- Source guards cover the new boundary.
- Proof authority remains claim/evidence/proof based, not challenge-type specific.
