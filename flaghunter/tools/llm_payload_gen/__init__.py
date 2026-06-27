"""Tool: generate synthetic red-team payloads to evaluate an LLM/agent guardrail.

Thin agent-facing wrapper over :mod:`flaghunter.redteam`. Lets the agent build
labelled, obfuscated test-payload batches (prompt injection / jailbreak /
exfiltration / etc.) for an *authorised* red-blue detector evaluation, and
optionally drop them as JSONL for a defender to score.

All payloads are inert, synthetic, and use fake canary data only — see the
safety contract in :mod:`flaghunter.redteam`.
"""

from ...redteam import (
    generate,
    payloads_to_jsonl,
    seed_categories,
    transform_names,
    write_batch,
)
from ...runtime.runtime import Runtime
from ..registry import ToolSchema, register_tool


@register_tool(
    name="llm_payload_gen",
    description=(
        "Generate synthetic, benign red-team test payloads for evaluating an "
        "LLM/agent guardrail's detectors (prompt injection, jailbreak, "
        "exfiltration, sensitive-file, command-exec, data-poisoning, "
        "markup-exfil, pii-leak). Applies deterministic obfuscation/encoding "
        "transforms (base32/85, homoglyph, zero-width, morse, nesting, ...) to "
        "seed attacks so a defender can be measured for evasion (miss-rate) and "
        "false positives. All payloads use fake canary data and are for "
        "authorised detector evaluation only."
    ),
    schema=ToolSchema(
        type="object",
        properties={
            "categories": {
                "type": "array",
                "items": {"type": "string"},
                "description": (
                    "Seed categories to include: injection, jailbreak, "
                    "exfiltration, sensitive_file, command_exec, data_poisoning, "
                    "markup_exfil, pii_leak, benign. Empty = all."
                ),
            },
            "transforms": {
                "type": "array",
                "items": {"type": "string"},
                "description": (
                    "Transform names to apply as a single chain to each seed "
                    "(e.g. ['base32'] or ['base64','base64'] for nesting). "
                    "Empty = a curated evasive default set of chains."
                ),
            },
            "max_per_seed": {
                "type": "integer",
                "description": "Cap on transform chains per seed (default: all).",
            },
            "output_path": {
                "type": "string",
                "description": "Optional path to write the batch as JSONL.",
            },
        },
        required=[],
    ),
    category="redteam",
)
async def llm_payload_gen(arguments: dict, runtime: Runtime) -> str:
    categories = arguments.get("categories") or None
    transforms = arguments.get("transforms")
    max_per_seed = arguments.get("max_per_seed")
    output_path = arguments.get("output_path")

    # A non-empty `transforms` list is treated as one chain applied to each seed.
    chains = [list(transforms)] if transforms else None

    try:
        payloads = generate(
            categories=categories,
            chains=chains,
            max_per_seed=max_per_seed,
        )
    except KeyError as e:
        return (
            f"Error: {e}\nAvailable transforms: {', '.join(transform_names())}\n"
            f"Available categories: {', '.join(seed_categories())}"
        )

    if not payloads:
        return (
            "No payloads generated (unknown category?).\n"
            f"Available categories: {', '.join(seed_categories())}"
        )

    lines = [
        f"Generated {len(payloads)} payload(s) "
        f"across {len({p.category for p in payloads})} categor(ies).",
    ]

    if output_path:
        written = write_batch(payloads, output_path)
        lines.append(f"Wrote JSONL batch -> {written}")

    lines.append("")
    lines.append("Sample (first 5):")
    for p in payloads[:5]:
        chain = "+".join(p.transform_chain) if p.transform_chain else "raw"
        lines.append(f"  [{p.pid}] target={p.target_detector}")
        lines.append(f"    chain={chain}  expected_block={p.expected_block}")
        lines.append(f"    text={p.text[:120]}")
        lines.append(f"    why={p.bypass_hypothesis}")

    if not output_path:
        lines.append("")
        lines.append("Full JSONL (pass output_path to write to a file instead):")
        lines.append(payloads_to_jsonl(payloads))

    return "\n".join(lines)
