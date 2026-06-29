"""source_audit: white-box source vulnerability triage (pure pattern scan)."""

from __future__ import annotations

import json

import pytest

from flaghunter.tools.registry import get_tool
from flaghunter.tools.source_audit import scan_source, source_audit


def test_tool_is_registered_and_exempt():
    tool = get_tool("source_audit")
    assert tool is not None
    assert tool.category == "audit"
    # white-box audit is outside the black-box ATT&CK/WSTG catalog → no techniques
    assert not tool.technique_ids
    from flaghunter.knowledge.attack_taxonomy import TOOL_EXEMPT

    assert "source_audit" in TOOL_EXEMPT


def test_scan_detects_php_unserialize_and_tainted_input(tmp_path):
    (tmp_path / "app.php").write_text(
        "<?php\n$x = unserialize($_GET['data']);\necho $x;\n",
        encoding="utf-8",
    )
    report = scan_source(tmp_path)
    rules = {f["rule"] for f in report["findings"]}
    assert "php_unserialize" in rules
    assert "php_tainted_input" in rules
    # unserialize is high severity
    unser = next(f for f in report["findings"] if f["rule"] == "php_unserialize")
    assert unser["severity"] == "high"
    assert unser["cwe"] == "CWE-502"
    assert unser["line"] == 2


def test_scan_detects_python_pickle_and_subprocess(tmp_path):
    (tmp_path / "svc.py").write_text(
        "import pickle, subprocess\n"
        "obj = pickle.loads(data)\n"
        "subprocess.run(cmd, shell=True)\n",
        encoding="utf-8",
    )
    report = scan_source(tmp_path)
    rules = {f["rule"] for f in report["findings"]}
    assert "py_pickle_load" in rules
    assert "py_subprocess_shell" in rules


def test_scan_detects_hardcoded_secret_any_language(tmp_path):
    (tmp_path / "config.py").write_text(
        'API_KEY = "s3cr3t_value_here"\n', encoding="utf-8"
    )
    report = scan_source(tmp_path)
    assert any(f["rule"] == "hardcoded_secret" for f in report["findings"])


def test_scan_skips_noise_dirs_and_unknown_extensions(tmp_path):
    (tmp_path / "node_modules").mkdir()
    (tmp_path / "node_modules" / "dep.js").write_text("eval(x)\n", encoding="utf-8")
    (tmp_path / "readme.txt").write_text("unserialize($_GET[x])\n", encoding="utf-8")
    report = scan_source(tmp_path)
    # nothing in node_modules; .txt not in the allow-list
    assert report["findings"] == []
    assert report["files_scanned"] == 0


def test_scan_clean_tree_has_no_findings(tmp_path):
    (tmp_path / "ok.py").write_text("x = 1 + 1\nprint(x)\n", encoding="utf-8")
    report = scan_source(tmp_path)
    assert report["total_findings"] == 0
    assert report["files_scanned"] == 1


def test_scan_missing_path_reports_error():
    report = scan_source("/no/such/dir/xyz")
    assert report["findings"] == []
    assert "error" in report


def test_max_findings_truncates(tmp_path):
    lines = "\n".join("$x = unserialize($_GET[%d]);" % i for i in range(50))
    (tmp_path / "many.php").write_text("<?php\n" + lines + "\n", encoding="utf-8")
    report = scan_source(tmp_path, max_findings=5)
    assert report["truncated"] is True
    assert report["total_findings"] == 5


def test_findings_sorted_high_severity_first(tmp_path):
    (tmp_path / "mix.php").write_text(
        "<?php\n$a = $_GET['x'];\nsystem($a);\n", encoding="utf-8"
    )
    report = scan_source(tmp_path)
    # high-severity (php_cmd_exec) must precede info (php_tainted_input)
    severities = [f["severity"] for f in report["findings"]]
    assert severities == sorted(severities, key=lambda s: {"high": 0, "info": 3}.get(s, 1))


@pytest.mark.asyncio
async def test_tool_wrapper_returns_json(tmp_path):
    (tmp_path / "a.php").write_text("<?php eval($_POST['c']);\n", encoding="utf-8")
    out = await source_audit({"path": str(tmp_path)}, runtime=None)
    parsed = json.loads(out)
    assert parsed["total_findings"] >= 1


@pytest.mark.asyncio
async def test_tool_wrapper_requires_path():
    out = await source_audit({}, runtime=None)
    assert "path is required" in out
