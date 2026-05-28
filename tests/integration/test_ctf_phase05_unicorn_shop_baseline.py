from __future__ import annotations

import json
import subprocess
from pathlib import Path

from pentestagent.agents.pa_agent.phase05_baseline import PHASE05_SCENARIOS


def _shared_repo_root(repo_root: Path) -> Path:
    try:
        common_dir = subprocess.check_output(
            ["git", "rev-parse", "--git-common-dir"],
            cwd=repo_root,
            text=True,
        ).strip()
    except Exception:
        return repo_root

    common_path = Path(common_dir)
    if not common_path.is_absolute():
        common_path = (repo_root / common_path).resolve()
    return common_path.parent


def test_phase05_unicorn_shop_live_artifact_records_real_flag_proof():
    repo_root = Path(__file__).resolve().parents[2]
    artifact_path = _shared_repo_root(repo_root) / "reports" / "ctf_phase05_unicorn_shop_live.clean.json"

    assert artifact_path.exists()

    data = json.loads(artifact_path.read_text(encoding="utf-8"))
    state = data.get("state") or {}

    assert data["success"] is True
    assert data["flag"] == "flag{fab255a8-9c2c-4a51-b0b6-00ec1facd250}"
    assert data["chain_used"] == ["web"]
    assert data["reason"] == "unicode numeric form bypass via price=万"
    assert state.get("detected_type") == "web"
    assert state.get("llm_exploration_steps") == 0
    assert state.get("verified_flags")
    assert state["verified_flags"][0]["value"] == "flag{fab255a8-9c2c-4a51-b0b6-00ec1facd250}"
    assert state["hypotheses"][0]["kind"] == "unicode_numeric_form_bypass"
    assert state["hypotheses"][0]["status"] == "supported"
    assert any(obs.get("kind") == "unicode_numeric_baseline" for obs in state.get("observations") or [])
    assert any(
        obs.get("kind") == "unicode_numeric_probe"
        and (obs.get("metadata") or {}).get("payload") == "万"
        for obs in state.get("observations") or []
    )

    slugs = {scenario.slug for scenario in PHASE05_SCENARIOS}
    assert "buu_unicorn_shop_unicode_numeric_form" in slugs
