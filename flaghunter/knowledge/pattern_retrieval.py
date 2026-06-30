"""Deterministic attack-pattern retrieval — 曲库初筛 (②③).

Given a challenge *fingerprint* (response headers / error strings / framework
fingerprint / cookie + parameter names), recall the top-k candidate attack-pattern
``kind``s so the dispatcher only runs *those* ``_has_*`` probes for final gating
(design §2②). Both layers are deterministic, so a hit-challenge's final hypothesis
set is byte-for-byte identical regardless of how big 曲库 grows.

The pipeline is a 1:1 port of the reference KB's **zero-random** retrieval
(D:\\newwork\\AI-Agents\\aiagentstudy\\knowledge\\raw\\{query-kb,build-kb-fts}.py):

    item-level BM25  ┐
                     ├─ RRF fusion (K=60) ─► rule rerank ─► (-score, kind) sort
    alias-level BM25 ┘

- **item doc** = title + aliases + signals + technique_ids + topic + kind tokens.
- **alias docs** = one mini-doc per alias (the reference's chunk index) — lets a
  single sharp fingerprint term (``tornado.web``) rank its kind highly even when
  the rest of the item doc dilutes it.
- **RRF** fuses the two rankings without tuning weights (rank-only, scale-free).
- **rule rerank** adds deterministic bonuses for exact alias / title / kind hits.

No embeddings, no sqlite, no ``rank_bm25`` dependency (BM25 is implemented inline)
— pure stdlib so it runs in the base install and never introduces randomness.
``aliases.json`` (optional) injects cross-cutting fingerprint synonyms at build
time (design §2③), so a new fingerprint only edits the table, never the probes.
"""

from __future__ import annotations

import json
import math
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Iterable

_DEFAULT_PATTERNS_DIR = Path(__file__).resolve().parent / "attack_patterns"

# BM25 constants — the textbook defaults (Robertson/Spärck-Jones). Fixed, never
# tuned at runtime, so retrieval is reproducible.
_BM25_K1 = 1.5
_BM25_B = 0.75
# Reciprocal-rank-fusion constant (reference query-kb.py uses 60).
_RRF_K = 60

_TOKEN_RE = re.compile(r"[a-z0-9]+")


def _tokenize(text: str) -> list[str]:
    """Deterministic lowercase alphanumeric tokenizer (stable, no randomness)."""
    return _TOKEN_RE.findall(str(text or "").lower())


@dataclass(frozen=True)
class RetrievalResult:
    kind: str
    score: float
    matched_terms: tuple[str, ...] = field(default_factory=tuple)
    chain: str = "web"


class _BM25:
    """Minimal in-memory BM25 over a fixed document set. Deterministic."""

    def __init__(self, docs: list[list[str]]) -> None:
        self._docs = docs
        self._doc_len = [len(d) for d in docs]
        self._avg_len = (sum(self._doc_len) / len(docs)) if docs else 0.0
        # document frequency per term
        df: dict[str, int] = {}
        for doc in docs:
            for term in set(doc):
                df[term] = df.get(term, 0) + 1
        n = len(docs)
        self._idf = {
            term: math.log(1.0 + (n - freq + 0.5) / (freq + 0.5))
            for term, freq in df.items()
        }
        self._tf: list[dict[str, int]] = []
        for doc in docs:
            counts: dict[str, int] = {}
            for term in doc:
                counts[term] = counts.get(term, 0) + 1
            self._tf.append(counts)

    def scores(self, query_terms: Iterable[str]) -> list[float]:
        q = list(query_terms)
        out = [0.0] * len(self._docs)
        for i, counts in enumerate(self._tf):
            dl = self._doc_len[i]
            denom_norm = _BM25_K1 * (1 - _BM25_B + _BM25_B * (dl / self._avg_len if self._avg_len else 0.0))
            score = 0.0
            for term in q:
                tf = counts.get(term, 0)
                if not tf:
                    continue
                idf = self._idf.get(term, 0.0)
                score += idf * (tf * (_BM25_K1 + 1)) / (tf + denom_norm)
            out[i] = score
        return out


def _load_aliases(root: Path) -> list[list[str]]:
    """Optional cross-cutting synonym groups from ``aliases.json``.

    Format: ``{"groups": [["tornado", "tornado.web", "{{ }}"], ...]}``. Each group
    is a set of mutually-implying fingerprint terms; at query time, hitting any
    member injects the group's other (tokenized) terms for recall.
    """
    path = root / "aliases.json"
    if not path.exists():
        return []
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return []
    groups: list[list[str]] = []
    for group in data.get("groups", []) or []:
        toks: list[str] = []
        seen: set[str] = set()
        for member in group:
            for tok in _tokenize(member):
                if tok not in seen:
                    seen.add(tok)
                    toks.append(tok)
        if len(toks) >= 2:
            groups.append(toks)
    return groups


def load_patterns(root: str | Path | None = None) -> list[dict[str, Any]]:
    """Load every ``attack_patterns/<kind>/pattern.json`` (sorted by kind)."""
    base = Path(root) if root is not None else _DEFAULT_PATTERNS_DIR
    patterns: list[dict[str, Any]] = []
    if not base.exists():
        return patterns
    for pattern_file in sorted(base.glob("*/pattern.json")):
        try:
            obj = json.loads(pattern_file.read_text(encoding="utf-8"))
        except Exception:
            continue
        if isinstance(obj, dict) and obj.get("kind"):
            patterns.append(obj)
    return patterns


class PatternIndex:
    """Deterministic BM25×RRF retrieval over the attack-pattern 曲库."""

    def __init__(self, patterns: list[dict[str, Any]], alias_groups: list[list[str]] | None = None) -> None:
        # Stable order: sort by kind so ranking ties break deterministically.
        self._patterns = sorted(patterns, key=lambda p: str(p.get("kind") or ""))
        self._kinds = [str(p.get("kind") or "") for p in self._patterns]
        self._chains = {str(p.get("kind") or ""): str(p.get("exploit_chain_ref") or "web") for p in self._patterns}
        self._alias_groups = alias_groups or []

        # item-level docs: title + aliases + signals + technique_ids + topic + kind
        item_docs: list[list[str]] = []
        # alias-level docs: one per alias term, mapped back to its kind index
        alias_docs: list[list[str]] = []
        self._alias_owner: list[int] = []
        # exact alias set per kind for the rule-rerank bonus
        self._alias_sets: list[set[str]] = []
        for idx, p in enumerate(self._patterns):
            aliases = [str(a) for a in (p.get("aliases") or [])]
            signals = [str(s) for s in (p.get("signals") or [])]
            techniques = [str(t) for t in (p.get("technique_ids") or [])]
            blob = " ".join(
                [str(p.get("title") or ""), str(p.get("kind") or ""), str(p.get("topic") or "")]
                + aliases + signals + techniques
            )
            item_docs.append(_tokenize(blob))
            self._alias_sets.append({a.lower().strip() for a in aliases if a.strip()})
            for alias in aliases:
                alias_docs.append(_tokenize(alias + " " + str(p.get("kind") or "")))
                self._alias_owner.append(idx)

        self._item_bm25 = _BM25(item_docs)
        self._alias_bm25 = _BM25(alias_docs) if alias_docs else None

    @classmethod
    def from_dir(cls, root: str | Path | None = None) -> "PatternIndex":
        base = Path(root) if root is not None else _DEFAULT_PATTERNS_DIR
        return cls(load_patterns(base), _load_aliases(base))

    def _expand_query(self, tokens: list[str]) -> list[str]:
        """Inject alias-group synonyms for any token present (recall, deterministic)."""
        present = set(tokens)
        expanded = list(tokens)
        for group in self._alias_groups:
            if present & set(group):
                for tok in group:
                    if tok not in present:
                        present.add(tok)
                        expanded.append(tok)
        return expanded

    def retrieve(self, fingerprint: str, top_k: int = 8) -> list[RetrievalResult]:
        """Recall the top-k candidate kinds for a challenge fingerprint.

        Deterministic: same fingerprint → same ranked kinds, byte-stable.
        """
        if not self._patterns:
            return []
        q_tokens = self._expand_query(_tokenize(fingerprint))
        if not q_tokens:
            return []
        q_set = set(q_tokens)

        # --- item-level ranking ---
        item_scores = self._item_bm25.scores(q_tokens)
        item_rank = self._rank_indices(item_scores)

        # --- alias-level ranking, projected back onto kinds (best alias wins) ---
        kind_alias_score = [0.0] * len(self._patterns)
        if self._alias_bm25 is not None:
            alias_scores = self._alias_bm25.scores(q_tokens)
            for alias_idx, score in enumerate(alias_scores):
                owner = self._alias_owner[alias_idx]
                if score > kind_alias_score[owner]:
                    kind_alias_score[owner] = score
        alias_rank = self._rank_indices(kind_alias_score)

        # --- RRF fusion (rank-only, scale-free) ---
        fused: dict[int, float] = {}
        for rank_list in (item_rank, alias_rank):
            for position, idx in enumerate(rank_list):
                fused[idx] = fused.get(idx, 0.0) + 1.0 / (_RRF_K + position + 1)

        # --- deterministic rule rerank: exact alias / kind-token bonuses ---
        results: list[RetrievalResult] = []
        for idx, base_score in fused.items():
            if base_score <= 0.0 and item_scores[idx] <= 0.0 and kind_alias_score[idx] <= 0.0:
                continue
            matched = sorted(t for t in q_set if t in self._alias_sets[idx] or t == self._kinds[idx])
            bonus = 0.02 * len(matched)
            if self._kinds[idx] in q_set:
                bonus += 0.05
            results.append(
                RetrievalResult(
                    kind=self._kinds[idx],
                    score=round(base_score + bonus, 8),
                    matched_terms=tuple(matched),
                    chain=self._chains.get(self._kinds[idx], "web"),
                )
            )

        # stable: highest score first, kind as deterministic tiebreak
        results.sort(key=lambda r: (-r.score, r.kind))
        return results[: max(0, int(top_k))]

    @staticmethod
    def _rank_indices(scores: list[float]) -> list[int]:
        """Indices sorted by score desc; ties broken by index (deterministic)."""
        return [i for i, _ in sorted(enumerate(scores), key=lambda kv: (-kv[1], kv[0]))]


__all__ = ["PatternIndex", "RetrievalResult", "load_patterns"]
