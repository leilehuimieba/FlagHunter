# FlagHunter P5 Pre-Eval Plan v0.1

Date: 2026-07-04

Status: pre-eval planning and acceptance harness only. This document does not authorize
learning-loop implementation, policy mutation, persistent memory writeback, strategy
optimization, tool execution, or solver behavior changes.

## Evaluation Goals

P5 pre-eval exists to decide whether the current P1/P2/P3/P4 evidence and replay
surfaces are strong enough to justify a later P5 implementation card. The immediate goal
is to evaluate read-side contracts, not to improve solving behavior.

The pre-eval harness should answer these questions:

- Can compact evidence, trace, receipt, recovery, crew bridge, replay audit, readback,
  digest, and bundle artifacts be represented without treating them as proof?
- Can a reviewer reproduce the same replay/readback/bundle output from the same local
  compact fixtures?
- Do outputs remain bounded, redacted, deterministic, and operator-reviewable?
- Are all candidate, control, tool, model, state, handoff, budget, node, crew, replay,
  audit, eval, view, and bundle artifacts kept below proof authority?
- Is there enough documented evidence to ask for explicit user authorization before any
  P5 implementation begins?

## Evaluation Inputs

Allowed evaluation inputs are compact read-side artifacts only:

- P1 claim and evidence readback summaries.
- P2 trace and audit readback surfaces.
- P3 solve node, task brief, and solve receipt readback surfaces.
- P4 Task DAG dry receipt and local dry result surfaces.
- P4 recovery proposal, proposal readback, and review artifacts.
- P4 crew bridge request, receipt, preview, handoff, admission, and dry approval artifacts.
- P4-E replay audit index, readback package, operator view, and bundle outputs.

These inputs are evaluation material. They are not proof authority and must not be used
to upgrade claims, approve flags, write ledgers, mutate state, write queues, or change
strategy selection.

## Fixture Selection

Use one or two small local fixtures. They must be deterministic and authorized for
repository-local testing:

- Synthetic compact replay fixture: two in-memory artifacts, one review-like artifact and
  one dry crew bridge artifact, both using local identifiers and bounded metadata.
- Existing v1 evidence trial fixture: the current local replay fixture suite can remain
  in the verification command to confirm the older evidence-readback path still behaves.

Fixture selection rationale:

- Small fixtures reduce review noise and keep failures attributable.
- Synthetic fixtures can include sensitive-looking metadata so redaction is exercised
  without leaking real secrets.
- Existing evidence fixtures protect backward compatibility for P1/P2/P3 readback
  contracts.
- No fixture may require a real target, external network, real exploit run, tool call, or
  persistent write outside test-local temporary paths.

## Metric Definitions

- evidence completeness: the bundle or report exposes enough compact evidence references,
  counts, and summaries for a human reviewer to understand what was observed.
- trace reproducibility: the same local fixture inputs produce the same replay/readback
  ids, summaries, and digest items.
- receipt coverage: relevant P3/P4 receipt-like artifacts are present as compact rows or
  counted as missing with an explicit warning.
- proof-boundary compliance: no eval artifact is treated as proof authority, and no eval
  step can approve a flag or upgrade a claim.
- redaction compliance: secrets, cookies, tokens, passwords, authorization headers, raw
  command output, full request/response bodies, and candidate flags do not leak into the
  pre-eval surfaces.
- operator reviewability: overview, rows, severity, warnings, and bundle summaries are
  compact enough for manual review without requiring a UI implementation.
- replay consistency: replay audit index, readback package, operator view, and bundle
  stay deterministic under input reordering.

## Pass/Fail Gates

P5 pre-eval passes only if all gates below pass:

- proof boundary: eval outputs remain below proof authority and cannot approve or upgrade
  evidence.
- no secret leakage: sensitive fixture values and candidate flags are redacted or omitted.
- no action execution: tests do not call tools, workers, network clients, shell execution,
  browser automation, dispatch loops, recovery flows, queue writers, or state writers.
- deterministic replay/readback: same normalized fixture inputs produce the same bundle
  identifiers and compact output.
- bounded output: metadata, summaries, warnings, and digest items stay within documented
  limits.
- manual approval before P5 implementation: any learning loop, policy mutation,
  persistent memory writeback, or strategy optimization requires explicit user
  authorization in a later card.

Fail any gate if:

- output contains unredacted secrets, raw command/body data, or candidate flags;
- output implies proof authority;
- a fixture executes a solver, tool, network request, worker, queue write, or state write;
- replay ids are unstable across equivalent input ordering;
- a later implementation step is started without explicit user authorization.

## Manual Review Checklist

Before requesting P5 implementation authorization, a reviewer should confirm:

- The fixture list is local, deterministic, synthetic or already authorized.
- The evaluation input set is clearly separated from proof authority.
- Replay bundle output is compact and does not contain full raw artifacts.
- Warning and attention counts are understandable to an operator.
- Metric names map to concrete pass/fail gates.
- No strategy, model, tool, worker, dispatcher, or recovery behavior has changed.
- No persistent memory writeback or policy update path was introduced.

## Explicit Non-Goals

P5-A does not:

- implement a learning loop;
- tune strategy weights;
- write training data;
- update strategy memory;
- auto-select models or tools;
- change solver outcome;
- alter dispatcher, crew, recovery, or tool-execution behavior;
- run exploits or evaluate real targets;
- write files as part of the runtime path;
- emit ledger records;
- write state, proof, or queues.

## P5 Implementation Authorization Boundary

P5 implementation is not authorized by this plan.

Any future work involving learning loops, reward signals, policy mutation, strategy
optimization, persistent memory writeback, automated model/tool selection, or solver
behavior changes requires explicit user authorization in a separate card. The authorization
request must identify the intended mutation surface, the rollback plan, the evidence used
for acceptance, and the proof-boundary safeguards.

Until that authorization exists, P5 work is limited to local documentation and pure
read-side acceptance harnesses over compact fixtures.
