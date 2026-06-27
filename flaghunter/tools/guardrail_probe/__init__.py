"""Tool: probe a live LLM-guardrail HTTP endpoint with generated payloads.

Generates a synthetic red-team payload batch (via :mod:`flaghunter.redteam`)
and sends each at an *authorised* guardrail gateway, classifying every response
into blocked / flagged / bypassed / false-positive. Returns the blue-team TSV
plus a bypass summary. For authorised red-blue detector evaluation only.
"""

import asyncio

from ...redteam import (
    generate,
    probe_endpoint,
    results_to_tsv,
    summarize,
    transform_names,
)
from ...runtime.runtime import Runtime
from ..registry import ToolSchema, register_tool


@register_tool(
    name="guardrail_probe",
    description=(
        "Send synthetic red-team payloads at a live LLM/agent-guardrail HTTP "
        "endpoint and report which were blocked, flagged, or BYPASSED. "
        "Generates an obfuscation/jailbreak/exfil corpus, POSTs each as "
        "{session_id, message}, and classifies the guardrail's decision. "
        "Authorised detector evaluation only; payloads use fake canary data."
    ),
    schema=ToolSchema(
        type="object",
        properties={
            "url": {"type": "string", "description": "Guardrail gateway URL (POST endpoint)."},
            "categories": {
                "type": "array", "items": {"type": "string"},
                "description": "Seed categories (injection, jailbreak, ...). Empty = all.",
            },
            "transforms": {
                "type": "array", "items": {"type": "string"},
                "description": "Transform chain applied to each seed. Empty = curated default chains.",
            },
            "max_per_seed": {"type": "integer", "description": "Cap on chains per seed."},
            "timeout": {"type": "number", "description": "Per-request timeout seconds (default 15)."},
        },
        required=["url"],
    ),
    category="redteam",
)
async def guardrail_probe(arguments: dict, runtime: Runtime) -> str:
    url = arguments.get("url", "")
    if not url:
        return "Error: url is required (the guardrail gateway POST endpoint)."

    categories = arguments.get("categories") or None
    transforms = arguments.get("transforms")
    max_per_seed = arguments.get("max_per_seed")
    timeout = float(arguments.get("timeout", 15) or 15)
    chains = [list(transforms)] if transforms else None

    try:
        payloads = generate(categories=categories, chains=chains, max_per_seed=max_per_seed)
    except KeyError as e:
        return f"Error: {e}\nAvailable transforms: {', '.join(transform_names())}"
    if not payloads:
        return "No payloads generated (unknown category?)."

    # urllib is blocking; keep the event loop free.
    results = await asyncio.to_thread(probe_endpoint, url, payloads, None, timeout)
    s = summarize(results)

    lines = [
        f"Probed {url} with {s['total']} payload(s).",
        f"  blocked/flagged vs BYPASSED: bypasses={s['bypass_count']} "
        f"(rate={s['bypass_rate']}), false_positives={s['false_positive_count']}",
        f"  outcomes={s['by_outcome']}",
    ]
    if s["bypassed_pids"]:
        lines.append(f"  BYPASSED payloads: {', '.join(s['bypassed_pids'])}")
    lines.append("")
    lines.append(results_to_tsv(results))
    return "\n".join(lines)
