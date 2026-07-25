"""Verdict + cost extraction from a completed ``flaghunter run``.

This is the deliberately-decoupled seam: rather than importing dispatcher
internals (which churn heavily), the judge reads the run's *external surfaces* —
captured stdout, the ``--report`` markdown, and ``loot/notes.json`` — and derives
a verdict and best-effort cost metrics with plain regex. The load-bearing signal
is the flag match; everything else degrades gracefully to ``None`` when a surface
can't be parsed, so a stdout format change never crashes a baseline run (it just
blanks a column).
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from enum import Enum

from .corpus import Challenge

# Flag bodies that are placeholders / format hints, not a real capture. Guards
# against matching the echoed task ("flag 格式 flag{...}") or a template line.
_PLACEHOLDER_BODIES = {"", "...", "xxx", "xxxx", "...}", "your_flag", "flag_here"}

# Textual cues that a run got to exploitation but never confirmed a flag.
_NEAR_CUES = (
    "near-solve",
    "near solve",
    "candidate flag",
    "unverified flag",
    "近解",
    "候选 flag",
    "候选flag",
)

# Cues for the three chronic diseases, so the scorecard can attribute failures.
_DISEASE_CUES = {
    "fixation": ("fixation", "同一工具", "repeated payload"),
    "spinning": ("spinning", "空转", "stalled", "no_progress", "dead-end", "dead end"),
    "reachability": ("repertoire_miss", "repertoire miss", "unreachable", "够不着"),
}


class Verdict(str, Enum):
    SOLVED = "solved"
    NEAR = "near"
    FAIL = "fail"
    ERROR = "error"
    SKIPPED = "skipped"


@dataclass
class JudgeResult:
    verdict: Verdict
    flag_found: str | None = None
    matched_expectation: bool = False
    steps: int | None = None
    max_loops: int | None = None
    tokens: int | None = None
    tools_used: list[str] = field(default_factory=list)
    diseases: list[str] = field(default_factory=list)
    detail: str = ""


def extract_flag(text: str, pattern: str, known_flag: str | None = None) -> str | None:
    """Return the first real flag in ``text`` matching ``pattern``.

    If ``known_flag`` is given, require an exact substring match (offline judging
    of a challenge whose flag is already known). Otherwise match the regex and
    reject placeholder bodies so an echoed format hint isn't scored as a capture.
    """
    if not text:
        return None
    if known_flag:
        return known_flag if known_flag in text else None
    for m in re.finditer(pattern, text, flags=re.IGNORECASE):
        candidate = m.group(0)
        body = candidate[candidate.find("{") + 1 : candidate.rfind("}")].strip().lower()
        if body in _PLACEHOLDER_BODIES:
            continue
        return candidate
    return None


def _parse_steps(stdout: str) -> tuple[int | None, int | None]:
    """Extract (last_step, max_loops) from a run's stdout.

    The authoritative step count is the dispatcher's terminal line
    ``done: stopped=<reason> steps=<N> solved=<bool>``. The ``Loops: X/Y``
    Finished panel is the *deterministic-substrate* loop counter and reads
    ``0`` when the live blackboard loop solved the challenge, so it is NOT a
    reliable step signal — the old ``\\d+/\\d+`` heuristic latched onto
    ``Loops: 0/12`` and reported ``steps=0`` for fast live solves. We prefer,
    in order: the ``steps=<N>`` terminal line, then the highest ``step <N>:``
    trace line. If neither is present we return ``None`` (an honest blank)
    rather than a wrong ``0`` scraped from the loop panel.
    """
    steps: int | None = None
    term = re.findall(r"stopped=\w+\s+steps=(\d+)", stdout)
    if term:
        steps = max(int(x) for x in term)
    else:
        trace = re.findall(r"\bstep\s+(\d+)\s*:", stdout, re.IGNORECASE)
        if trace:
            steps = max(int(x) for x in trace)
    max_loops: int | None = None
    panel = re.search(r"[Ll]oops:\s*\d+\s*/\s*(\d+)", stdout)
    if panel:
        max_loops = int(panel.group(1))
    return steps, max_loops


def _parse_tokens(stdout: str) -> int | None:
    m = re.search(r"(?:total[_ ]?tokens|tokens?)\D{0,12}?([\d,]{2,})", stdout, re.IGNORECASE)
    if not m:
        return None
    try:
        return int(m.group(1).replace(",", ""))
    except ValueError:
        return None


def _parse_tools(stdout: str) -> list[str]:
    """Tools actually invoked, in order, from the dispatcher trace.

    The authoritative surface is the ``step N: call_tool <name>`` line the CTF
    dispatcher prints per step. The old loose ``tool[:\\s]+<word>`` scan latched
    onto free-text prose ("the tool will…", "running for…") and polluted the
    list with junk tokens like ``not`` / ``will`` — so we only fall back to it
    when no structured ``call_tool`` lines exist at all.
    """
    tools: list[str] = []
    for m in re.finditer(r"call_tool\s+([a-z][a-z0-9_\-]{1,30})", stdout, re.IGNORECASE):
        name = m.group(1).lower()
        if name not in tools:
            tools.append(name)
    if tools:
        return tools[:40]
    for m in re.finditer(r"(?:tool|执行|running)[:\s]+([a-z][a-z0-9_\-]{2,30})", stdout, re.IGNORECASE):
        name = m.group(1).lower()
        if name not in tools:
            tools.append(name)
    return tools[:40]


def _detect_diseases(text: str) -> list[str]:
    low = text.lower()
    return [name for name, cues in _DISEASE_CUES.items() if any(c in low for c in cues)]


def judge_run(
    challenge: Challenge,
    *,
    stdout: str = "",
    report_text: str = "",
    notes_text: str = "",
    returncode: int = 0,
    timed_out: bool = False,
) -> JudgeResult:
    """Derive a verdict + cost metrics from a completed run's external surfaces."""
    if timed_out or (returncode not in (0, None) and not stdout):
        return JudgeResult(
            verdict=Verdict.ERROR,
            detail=("timeout" if timed_out else f"exit={returncode}, no output"),
        )

    # Prefer structured surfaces (report/notes) over noisy stdout for the flag.
    combined = "\n".join(filter(None, [report_text, notes_text, stdout]))
    flag = extract_flag(combined, challenge.flag_pattern, challenge.known_flag)

    steps, max_loops = _parse_steps(stdout)
    tokens = _parse_tokens(stdout)
    tools = _parse_tools(stdout)
    diseases = _detect_diseases(combined)

    if flag:
        verdict = Verdict.SOLVED
    elif timed_out:
        verdict = Verdict.ERROR
    elif any(cue in combined.lower() for cue in _NEAR_CUES):
        verdict = Verdict.NEAR
    else:
        verdict = Verdict.FAIL

    matched = verdict.value == challenge.expected_verdict

    return JudgeResult(
        verdict=verdict,
        flag_found=flag,
        matched_expectation=matched,
        steps=steps,
        max_loops=max_loops or challenge.max_loops,
        tokens=tokens,
        tools_used=tools,
        diseases=diseases,
        detail="" if flag else f"no flag; rc={returncode}",
    )
