"""Export the Phase 0.5 baseline registry to a JSON artifact."""

from __future__ import annotations

import json
from pathlib import Path
import sys


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from pentestagent.agents.pa_agent.phase05_baseline import build_phase05_baseline


def main() -> None:
    out_path = ROOT / "reports" / "benchmarks" / "ctf_phase05_baseline.json"
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(
        json.dumps(build_phase05_baseline(), indent=2, ensure_ascii=False),
        encoding="utf-8",
    )
    print(out_path)


if __name__ == "__main__":
    main()
