from __future__ import annotations

import json
from pathlib import Path
import subprocess
import sys

from flaghunter.agents.pa_agent.phase05_baseline import (
    PHASE05_SCENARIOS,
    build_phase05_baseline,
)


def test_phase05_baseline_registry_covers_real_live_solve_scenarios():
    baseline = build_phase05_baseline()

    assert baseline["schema_version"] == "1.0"
    assert baseline["phase"] == "0.5"
    assert baseline["summary"]["scenario_count"] >= 3
    assert baseline["summary"]["real_flag_proofs"] >= 3

    slugs = {scenario.slug for scenario in PHASE05_SCENARIOS}
    assert "buu_easy_sql_auth_form" in slugs
    assert "buu_php_source_leak_unserialize" in slugs
    assert "buu_unicorn_shop_unicode_numeric_form" in slugs

    phase_map = baseline["phase_status"]
    assert phase_map["Phase 1"] == "completed"
    assert phase_map["Phase 2"] == "pending"


def test_phase05_baseline_blockers_are_phase_mapped_and_test_backed():
    repo_root = Path(__file__).resolve().parents[2]

    for scenario in PHASE05_SCENARIOS:
        assert scenario.evidence.acceptance_test.startswith("tests/integration/")
        test_file = scenario.evidence.acceptance_test.split("::", 1)[0]
        assert (repo_root / test_file).exists()

        assert scenario.earliest_blocker.mapped_phase in {
            "Phase 1",
            "Phase 2",
            "Phase 3",
            "Phase 4",
            "Phase 5",
            "Phase 6",
        }
        assert scenario.earliest_blocker.summary
        assert scenario.earliest_blocker.root_cause


def test_phase05_export_script_writes_json_report(tmp_path: Path):
    repo_root = Path(__file__).resolve().parents[2]
    script_path = repo_root / "scripts" / "export_phase05_baseline.py"

    completed = subprocess.run(
        [sys.executable, str(script_path)],
        cwd=repo_root,
        capture_output=True,
        text=True,
        check=True,
    )

    output_path = Path(completed.stdout.strip().splitlines()[-1])
    assert output_path.exists()

    data = json.loads(output_path.read_text(encoding="utf-8"))
    assert data["phase"] == "0.5"
    assert data["summary"]["scenario_count"] >= 3
