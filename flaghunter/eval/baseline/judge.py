"""Verdict + cost extraction from a completed ``flaghunter run``.

This is the deliberately-decoupled seam: rather than importing dispatcher
internals (which churn heavily), the judge reads the run's *external surfaces* —
captured stdout and the ``--report`` markdown — and derives a verdict and
best-effort cost metrics with plain regex. The load-bearing *success* signal is
the dispatcher's proof-backed terminal outcome (``solved=True``, which A-05
gates on a verified flag claim), NOT a raw flag-shaped string in stdout: a flag
the run never verified is scored a candidate (NEAR), never SOLVED, so the
scorecard's false-success rate stays 0 (D-02, §6.18: "judge 只消费
proof/receipt/trace，不从任意 stdout 猜测成功"). Cost metrics degrade gracefully
to ``None`` when a surface can't be parsed, so a stdout format change never
crashes a baseline run (it just blanks a column).
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


def _parse_terminal_outcome(stdout: str) -> tuple[str | None, bool | None]:
    """Extract ``(stopped_reason, solved)`` from the dispatcher's terminal line
    ``done: stopped=<reason> steps=<N> solved=<bool>`` (both the no-LLM and
    blackboard loops print this shape).

    ``solved`` is the proof-backed success signal: A-05 only lets the dispatcher
    print ``solved=True`` when a canonical flag claim was *verified* into a Fact,
    never for a flag-shaped string it merely observed. That makes this line — not
    a raw stdout flag regex — the authoritative success signal for the judge.
    Returns ``(None, None)`` when no terminal line is present (foreign/old
    output), so the caller falls back conservatively (a bare flag → candidate).
    """
    m = re.search(r"stopped=(\w+)\s+steps=\d+\s+solved=(True|False)", stdout)
    if not m:
        return None, None
    return m.group(1), m.group(2) == "True"


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

    # Proof-backed success signal (A-05 proof-gated), consumed instead of a raw
    # stdout flag regex. A ``known_flag`` exact match is offline ground truth (an
    # oracle the operator supplied to adjudicate), so it counts as proof too; a
    # live run without a known flag must carry the verified terminal outcome. A
    # flag-*shaped* string with neither is only a candidate — scoring it SOLVED
    # is the false-success channel D-02 closes.
    _stopped, proven = _parse_terminal_outcome(stdout)
    proof_backed = bool(challenge.known_flag and flag) or proven is True
    near_cue = any(cue in combined.lower() for cue in _NEAR_CUES)

    if proof_backed:
        verdict = Verdict.SOLVED
        detail = ""
    elif flag or near_cue:
        verdict = Verdict.NEAR
        detail = (
            "flag-shaped output not proof-backed (no verified terminal outcome)"
            if flag
            else "near cue without a captured flag"
        )
    else:
        verdict = Verdict.FAIL
        detail = f"no flag; rc={returncode}"

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
        detail=detail,
    )
