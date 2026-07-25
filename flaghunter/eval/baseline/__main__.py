"""CLI entry: ``python -m flaghunter.eval.baseline``.

Examples
--------
Offline plumbing smoke (no network / LLM / tools) — every tier's shape is exercised::

    python -m flaghunter.eval.baseline --dry-run --out loot/baseline/dry

Real T0 anchor sweep, cold memory, tool execution on the Kali VM::

    python -m flaghunter.eval.baseline \
        --tiers T0 --targets targets.json --memory cold --ssh \
        --out loot/baseline/$(date +%Y%m%d)

``targets.json`` maps challenge id → live instance URL::

    {"dasctf_easysql": "http://node.ctf2.dasctf.com:1234/"}
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from .corpus import load_corpus
from .report import format_markdown, summarize
from .runner import run_baseline


def _parse_targets(values: list[str], targets_file: str | None) -> dict[str, str]:
    targets: dict[str, str] = {}
    if targets_file:
        targets.update(json.loads(Path(targets_file).read_text(encoding="utf-8")))
    for v in values or []:
        if "=" not in v:
            raise SystemExit(f"--target expects id=url, got: {v!r}")
        cid, url = v.split("=", 1)
        targets[cid.strip()] = url.strip()
    return targets


def main(argv: list[str] | None = None) -> int:
    # The report/progress carry ✓ and CJK; a Windows GBK console would crash on
    # print. Force UTF-8 on the streams (files are already written UTF-8).
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(encoding="utf-8", errors="replace")  # type: ignore[attr-defined]
        except (AttributeError, ValueError):
            pass

    p = argparse.ArgumentParser(prog="flaghunter.eval.baseline", description=__doc__)
    p.add_argument("--tiers", default="", help="Comma list, e.g. T0,T1 (default: all)")
    p.add_argument("--types", default="", help="Comma list, e.g. web,crypto (default: all)")
    p.add_argument("--targets-file", help="JSON file mapping challenge id → URL")
    p.add_argument("--target", action="append", default=[], help="id=url (repeatable)")
    p.add_argument("--memory", choices=["cold", "warm"], default="cold")
    p.add_argument("--ssh", action="store_true", help="Run tools on the Kali VM via SSH")
    p.add_argument("--docker", action="store_true", help="Run tools in Docker")
    p.add_argument("--dry-run", action="store_true", help="Synthetic outcomes; no subprocess")
    p.add_argument("--out", default="loot/baseline/latest", help="Output dir for scorecard + report")
    args = p.parse_args(argv)

    tiers = [t for t in args.tiers.split(",") if t] or None
    types = [t for t in args.types.split(",") if t] or None
    challenges = load_corpus(tiers=tiers, types=types)
    if not challenges:
        print("no challenges matched the tier/type filter", file=sys.stderr)
        return 2

    targets = _parse_targets(args.target, args.targets_file)
    out_dir = Path(args.out)
    out_dir.mkdir(parents=True, exist_ok=True)
    runs_dir = out_dir / "runs"

    def _progress(row):
        mark = "✓" if row.flag_found else row.verdict
        print(f"[{row.tier}] {row.challenge_id}: {mark}", file=sys.stderr)

    rows = run_baseline(
        challenges,
        targets,
        memory_mode=args.memory,
        ssh=args.ssh,
        docker=args.docker,
        dry_run=args.dry_run,
        runs_dir=runs_dir,
        on_row=_progress,
    )

    scorecard = {"summary": summarize(rows), "rows": [r.to_dict() for r in rows]}
    (out_dir / "scorecard.json").write_text(
        json.dumps(scorecard, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    report_md = format_markdown(rows)
    (out_dir / "report.md").write_text(report_md, encoding="utf-8")

    print(report_md)
    print(f"\n→ scorecard: {out_dir / 'scorecard.json'}", file=sys.stderr)
    print(f"→ report:    {out_dir / 'report.md'}", file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
