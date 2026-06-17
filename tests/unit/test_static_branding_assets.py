"""Static branding guards for root-level launch/setup assets."""

from __future__ import annotations

from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
BRANDED_ASSETS = [
    ROOT / "Dockerfile",
    ROOT / "Dockerfile.kali",
    ROOT / "docker-entrypoint.sh",
    ROOT / "scripts" / "setup.sh",
    ROOT / "scripts" / "setup.ps1",
]


def test_root_launch_assets_use_flaghunter_branding():
    for path in BRANDED_ASSETS:
        text = path.read_text(encoding="utf-8")
        assert "FlagHunter" in text or "FLAGHUNTER" in text
        assert "PentestAgent" not in text
        assert "PENTESTAGENT" not in text


def test_readme_primary_usage_uses_flaghunter_command_and_package():
    readme = (ROOT / "README.md").read_text(encoding="utf-8")

    assert "Python 包目录 `flaghunter/`" in readme
    assert "运行入口命令 `flaghunter`" in readme
    assert "```bash\nflaghunter" in readme
    assert "Python 包目录 `pentestagent/`" not in readme
    assert "运行入口命令 `pentestagent`" not in readme
