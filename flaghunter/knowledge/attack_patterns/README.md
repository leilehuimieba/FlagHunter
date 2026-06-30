# Attack-pattern 曲库 (schema-ised + searchable)

Design source of truth: `docs/dev/曲库与探索循环_活曲库化与战略探索_设计_2026-06-30_V1.md` §2.

Each attack-pattern `kind` is externalised here as searchable metadata so the
dispatcher can **recall** candidate kinds from a challenge fingerprint
(deterministic BM25×RRF, `pattern_retrieval.py`) before running the `_has_*`
probes for **final gating**. Both layers are deterministic → a hit-challenge's
final hypothesis set is byte-for-byte identical no matter how big 曲库 grows.

> The exploit chain itself stays **hardcoded in code** (`hypothesis_engine` +
> the chain registry). `pattern.json` is *only* the retrievable metadata that
> points at that chain — a retrieval hit runs the same byte-identical chain.

## Layout

```
attack_patterns/
  <kind>/
    pattern.json     # machine contract the retriever reads
    recipe.md        # (optional) human-readable distilled write-up
  aliases.json       # cross-cutting fingerprint synonym groups (recall only)
  eval/
    pattern-queries.jsonl   # golden {fingerprint → expected_kind} regression set
```

## `pattern.json` schema

| field | meaning |
|-------|---------|
| `id` | stable `ap-<kind>` identifier |
| `kind` | the hypothesis/strategy kind (matches `_CHAIN_BY_KIND`) |
| `title` | one-line human label |
| `status` | `active` / `deprecated` |
| `topic` | 漏洞族, derived from the WSTG category (`injection`, `authorization`, …) |
| `technique_ids` | WSTG / ATT&CK ids (mirror of `attack_taxonomy.STRATEGY_TECHNIQUES`) |
| `trigger` | how the kind fires: `detected_type:*`, `structural: *`, or `web-strategy` |
| `gate_probe` | the `_has_*` method (or condition) that does final gating |
| `exploit_chain_ref` | the chain name (mirror of `_CHAIN_BY_KIND`) a hit runs |
| `aliases` | fingerprint synonyms used to **recall** the kind (response headers / error strings / framework / cookie + param names) |
| `signals` | the gate's supporting-evidence terms (mirror of the code's `supports`) |
| `evidence_paths` | links to WP docs / distilled write-ups |

## Governance

- Every `kind` in `hypothesis_engine._CHAIN_BY_KIND` (minus the `llm_driven_exploration`
  / `generic_web_recon` meta-kinds) **must** have a `pattern.json` here. Enforced by
  `tests/unit/knowledge/test_pattern_retrieval.py`.
- After adding a pattern or editing `aliases.json`, run the golden eval
  (`pattern_eval.run_eval()`) and confirm hit-rate / MRR did not regress.
- New fingerprint synonyms go in `aliases.json` — never hard-code them into the
  `_has_*` probes.
