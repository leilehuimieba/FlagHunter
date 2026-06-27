"""Red-team payload-generation toolchain for evaluating LLM/agent guardrails.

This package is FlagHunter's **offensive payload factory** for *authorised*
red-blue exercises against AI-security middleware (prompt-injection /
jailbreak / exfiltration / obfuscation detectors). It turns a small set of
**synthetic, benign seed attacks** into large, labelled batches by applying
deterministic obfuscation/encoding transforms, so a defender's detector stack
can be measured for both miss-rate (evasion) and false-positive rate.

**Safety contract:** every seed and every generated payload uses *fake canary
data only* (``SAFE_CANARY_*`` tokens, ``*.invalid`` domains, constructed
non-real identifiers). Nothing here exfiltrates real data, targets a real host,
or executes anything — payloads are inert test strings handed to a detector.
This is enforced by ``tests/unit/redteam/test_safety_canaries.py``.

**Layering (I1):** CAPABILITY layer. Pure-stdlib data + functions; imports
nothing from ORCHESTRATION/SESSION/ENTRY. The agent-facing tool wrapper lives
in :mod:`flaghunter.tools.llm_payload_gen` and depends on this package, not the
other way round.
"""

from .transforms import (
    Transform,
    apply_chain,
    get_transform,
    list_transforms,
    transform_names,
)
from .seeds import AttackSeed, CANARIES, list_seeds, seed_categories
from .generator import Payload, generate, payloads_to_jsonl, write_batch
from .probe import (
    ProbeResult,
    classify,
    probe_endpoint,
    results_to_jsonl,
    results_to_tsv,
    summarize,
)

__all__ = [
    "Transform",
    "apply_chain",
    "get_transform",
    "list_transforms",
    "transform_names",
    "AttackSeed",
    "CANARIES",
    "list_seeds",
    "seed_categories",
    "Payload",
    "generate",
    "payloads_to_jsonl",
    "write_batch",
    "ProbeResult",
    "classify",
    "probe_endpoint",
    "results_to_jsonl",
    "results_to_tsv",
    "summarize",
]
