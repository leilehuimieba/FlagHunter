from __future__ import annotations

import json
from pathlib import Path

import pytest

from flaghunter.quality.acceptance import (
    AcceptanceStatus,
    CheckStatus,
    CommandOutcome,
    ManifestError,
    QualityRunner,
    load_evidence,
    load_manifest,
    parse_optimization_backlog,
    validate_manifest_against_backlog,
    write_reports,
)

REPO_ROOT = Path(__file__).resolve().parents[3]


def _write_json(path: Path, value: object) -> Path:
    path.write_text(json.dumps(value), encoding="utf-8")
    return path


def _manifest_dict() -> dict[str, object]:
    return {
        "schemaVersion": 1,
        "profiles": {"quick": ["builtin-pass", "command-pass"]},
        "gates": [
            {
                "id": "builtin-pass",
                "title": "Built-in pass",
                "category": "governance",
                "kind": "builtin",
                "handler": "pass-handler",
                "blocking": True,
                "timeoutSeconds": 10,
                "covers": ["A-01", "A-02"],
            },
            {
                "id": "command-pass",
                "title": "Command pass",
                "category": "tests",
                "kind": "command",
                "command": ["tool", "check"],
                "blocking": True,
                "timeoutSeconds": 10,
                "covers": ["A-03"],
            },
        ],
        "acceptance": {
            "A-01": {
                "mode": "automated",
                "gates": ["builtin-pass"],
                "owner": "core",
                "evidenceRequirements": [],
            },
            "A-02": {
                "mode": "hybrid",
                "gates": ["builtin-pass"],
                "owner": "runtime",
                "evidenceRequirements": ["runtime cancellation trace"],
            },
            "A-03": {
                "mode": "external",
                "gates": [],
                "owner": "operations",
                "evidenceRequirements": ["operator drill receipt"],
            },
        },
    }


def _guide(path: Path) -> Path:
    path.write_text(
        """# Guide

### 13.2 Phase A

| ID | 优先级 | 工作项 | 预期产物 | 验收目标 |
|---|---|---|---|---|
| A-01 | P0 | lifecycle | contract | all entries agree |
| A-02 | P0 | cancellation | scope | zero post-cancel actions |
| A-03 | P0 | shutdown | receipt | no leaked resources |
""",
        encoding="utf-8",
    )
    return path


def test_parse_optimization_backlog_reads_acceptance_columns(tmp_path: Path) -> None:
    items = parse_optimization_backlog(_guide(tmp_path / "guide.md"))

    assert list(items) == ["A-01", "A-02", "A-03"]
    assert items["A-01"].phase == "A"
    assert items["A-01"].priority == "P0"
    assert items["A-01"].deliverable == "contract"
    assert items["A-01"].acceptance_target == "all entries agree"


def test_manifest_rejects_profile_referencing_unknown_gate(tmp_path: Path) -> None:
    raw = _manifest_dict()
    raw["profiles"] = {"quick": ["missing-gate"]}

    with pytest.raises(ManifestError, match="missing-gate"):
        load_manifest(_write_json(tmp_path / "quality.json", raw))


def test_manifest_rejects_duplicate_gate_ids(tmp_path: Path) -> None:
    raw = _manifest_dict()
    gates = list(raw["gates"])
    gates.append(dict(gates[0]))
    raw["gates"] = gates

    with pytest.raises(ManifestError, match="duplicate gate"):
        load_manifest(_write_json(tmp_path / "quality.json", raw))


def test_manifest_coverage_must_exactly_match_guide(tmp_path: Path) -> None:
    manifest = load_manifest(_write_json(tmp_path / "quality.json", _manifest_dict()))
    backlog = parse_optimization_backlog(_guide(tmp_path / "guide.md"))
    validate_manifest_against_backlog(manifest, backlog)

    del backlog["A-03"]
    with pytest.raises(ManifestError, match="unexpected.*A-03"):
        validate_manifest_against_backlog(manifest, backlog)


def test_runner_blocking_failure_controls_exit_code(tmp_path: Path) -> None:
    raw = _manifest_dict()
    raw["profiles"] = {"quick": ["builtin-pass", "command-fail", "advisory-fail"]}
    raw["gates"] = [
        raw["gates"][0],
        {
            "id": "command-fail",
            "title": "Blocking failure",
            "category": "tests",
            "kind": "command",
            "command": ["tool", "fail"],
            "blocking": True,
            "timeoutSeconds": 10,
            "covers": [],
        },
        {
            "id": "advisory-fail",
            "title": "Advisory failure",
            "category": "hygiene",
            "kind": "command",
            "command": ["tool", "advisory"],
            "blocking": False,
            "timeoutSeconds": 10,
            "covers": [],
        },
    ]
    manifest = load_manifest(_write_json(tmp_path / "quality.json", raw))

    def execute(command: tuple[str, ...], **_: object) -> CommandOutcome:
        return CommandOutcome(
            exit_code=0 if command[-1] == "check" else 7,
            stdout="output",
            stderr="failure" if command[-1] != "check" else "",
            duration_seconds=0.1,
        )

    runner = QualityRunner(
        manifest,
        repo_root=tmp_path,
        command_executor=execute,
        builtin_handlers={
            "pass-handler": lambda _context: CommandOutcome(0, "ok", "", 0.01)
        },
    )
    report = runner.run("quick", commit="abc123")

    assert [result.status for result in report.gates] == [
        CheckStatus.PASSED,
        CheckStatus.FAILED,
        CheckStatus.FAILED,
    ]
    assert report.exit_code == 1
    assert report.overall_status == "failed"


def test_missing_requirement_is_unavailable_and_blocks(tmp_path: Path) -> None:
    raw = _manifest_dict()
    raw["profiles"] = {"quick": ["missing-tool"]}
    raw["gates"] = [
        {
            "id": "missing-tool",
            "title": "Missing tool",
            "category": "security",
            "kind": "command",
            "command": ["missing", "scan"],
            "requiresModules": ["not_installed"],
            "blocking": True,
            "timeoutSeconds": 10,
            "covers": [],
        }
    ]
    manifest = load_manifest(_write_json(tmp_path / "quality.json", raw))
    runner = QualityRunner(
        manifest,
        repo_root=tmp_path,
        module_available=lambda _name: False,
    )

    report = runner.run("quick", commit="abc123")

    assert report.gates[0].status is CheckStatus.UNAVAILABLE
    assert report.exit_code == 1
    assert "not_installed" in report.gates[0].detail


def test_changed_file_gate_skips_when_no_python_files_changed(tmp_path: Path) -> None:
    raw = _manifest_dict()
    raw["profiles"] = {"quick": ["changed"]}
    raw["gates"] = [
        {
            "id": "changed",
            "title": "Changed Python",
            "category": "lint",
            "kind": "command",
            "command": ["tool", "{changed_python}"],
            "blocking": True,
            "timeoutSeconds": 10,
            "covers": [],
        }
    ]
    manifest = load_manifest(_write_json(tmp_path / "quality.json", raw))
    runner = QualityRunner(manifest, repo_root=tmp_path)

    report = runner.run("quick", commit="abc123", changed_python=())

    assert report.gates[0].status is CheckStatus.SKIPPED
    assert report.exit_code == 0


def test_acceptance_never_passes_hybrid_or_external_without_evidence(
    tmp_path: Path,
) -> None:
    manifest = load_manifest(_write_json(tmp_path / "quality.json", _manifest_dict()))
    runner = QualityRunner(
        manifest,
        repo_root=tmp_path,
        command_executor=lambda *_args, **_kwargs: CommandOutcome(0, "ok", "", 0.1),
        builtin_handlers={
            "pass-handler": lambda _context: CommandOutcome(0, "ok", "", 0.01)
        },
    )

    report = runner.run("quick", commit="abc123")

    assert report.acceptance["A-01"].status is AcceptanceStatus.PASSED
    assert report.acceptance["A-02"].status is AcceptanceStatus.PENDING
    assert report.acceptance["A-03"].status is AcceptanceStatus.PENDING


def test_matching_external_evidence_can_complete_hybrid_and_external_items(
    tmp_path: Path,
) -> None:
    evidence = load_evidence(
        _write_json(
            tmp_path / "evidence.json",
            {
                "schemaVersion": 1,
                "commit": "abc123",
                "items": {
                    "A-02": {
                        "status": "passed",
                        "recordedAt": "2026-07-31T10:00:00Z",
                        "reviewer": "operator",
                        "artifacts": ["artifacts/cancellation-trace.json"],
                        "notes": "clean cancellation",
                    },
                    "A-03": {
                        "status": "passed",
                        "recordedAt": "2026-07-31T10:01:00Z",
                        "reviewer": "operator",
                        "artifacts": ["artifacts/shutdown-receipt.json"],
                        "notes": "no leaked resources",
                    },
                },
            },
        )
    )
    manifest = load_manifest(_write_json(tmp_path / "quality.json", _manifest_dict()))
    runner = QualityRunner(
        manifest,
        repo_root=tmp_path,
        command_executor=lambda *_args, **_kwargs: CommandOutcome(0, "ok", "", 0.1),
        builtin_handlers={
            "pass-handler": lambda _context: CommandOutcome(0, "ok", "", 0.01)
        },
    )

    report = runner.run("quick", commit="abc123", evidence=evidence)

    assert report.acceptance["A-02"].status is AcceptanceStatus.PASSED
    assert report.acceptance["A-03"].status is AcceptanceStatus.PASSED


def test_stale_evidence_is_not_accepted(tmp_path: Path) -> None:
    evidence = load_evidence(
        _write_json(
            tmp_path / "evidence.json",
            {"schemaVersion": 1, "commit": "old", "items": {}},
        )
    )
    manifest = load_manifest(_write_json(tmp_path / "quality.json", _manifest_dict()))
    runner = QualityRunner(
        manifest,
        repo_root=tmp_path,
        command_executor=lambda *_args, **_kwargs: CommandOutcome(0, "ok", "", 0.1),
        builtin_handlers={
            "pass-handler": lambda _context: CommandOutcome(0, "ok", "", 0.01)
        },
    )

    report = runner.run("quick", commit="new", evidence=evidence)

    assert report.evidence_status == "stale"
    assert report.acceptance["A-02"].status is AcceptanceStatus.PENDING


def test_reports_are_written_as_json_and_markdown(tmp_path: Path) -> None:
    manifest = load_manifest(_write_json(tmp_path / "quality.json", _manifest_dict()))
    runner = QualityRunner(
        manifest,
        repo_root=tmp_path,
        command_executor=lambda *_args, **_kwargs: CommandOutcome(0, "ok", "", 0.1),
        builtin_handlers={
            "pass-handler": lambda _context: CommandOutcome(0, "ok", "", 0.01)
        },
    )
    report = runner.run("quick", commit="abc123")

    json_path, markdown_path = write_reports(report, tmp_path / "reports")

    payload = json.loads(json_path.read_text(encoding="utf-8"))
    markdown = markdown_path.read_text(encoding="utf-8")
    assert payload["schemaVersion"] == 1
    assert payload["profile"] == "quick"
    assert payload["commit"] == "abc123"
    assert "## Gate Results" in markdown
    assert "## Acceptance Results" in markdown


def test_repository_manifest_covers_every_optimization_backlog_item() -> None:
    manifest = load_manifest(REPO_ROOT / "quality-gates.json")
    backlog = parse_optimization_backlog(REPO_ROOT / "docs" / "optimization-guide.md")

    validate_manifest_against_backlog(manifest, backlog)

    assert len(backlog) == 67
    assert all(rule.owner for rule in manifest.acceptance.values())
    assert all(
        rule.gates or rule.evidence_requirements
        for rule in manifest.acceptance.values()
    )
