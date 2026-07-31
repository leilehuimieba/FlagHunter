"""B-01 / B-02 — CI carries blocking quality gates, phased for a legacy tree.

The optimization masterplan (§13.4, B-01/B-02) requires the CI pipeline to
enforce lint/format and the import-linter architecture contracts as *blocking*
gates, not advisory ``continue-on-error`` steps that let regressions through.

Because the existing tree is not yet lint/format-zeroed, the blocking lint gate
is scoped to *changed files* (``修改范围 0 错误``): new and modified
``flaghunter/*.py`` must be clean, while a separate full-tree job stays advisory
until the backlog is cleared. This test locks that shape in:

  * a ``lint-changed`` job whose ruff + black steps are blocking (no
    ``continue-on-error``),
  * an ``import-linter`` job whose ``lint-imports`` step is blocking,
  * the full-tree ``lint`` job may remain advisory (so a big-bang flip that
    could red-line CI on unverified legacy violations is not silently
    introduced).
"""

from __future__ import annotations

from pathlib import Path

import pytest

yaml = pytest.importorskip("yaml")

_REPO_ROOT = Path(__file__).resolve().parents[2]
_WORKFLOW = _REPO_ROOT / ".github" / "workflows" / "tests.yml"


def _load_jobs() -> dict:
    data = yaml.safe_load(_WORKFLOW.read_text("utf-8"))
    assert isinstance(data, dict), "workflow did not parse to a mapping"
    jobs = data.get("jobs")
    assert isinstance(jobs, dict) and jobs, "workflow has no jobs"
    return jobs


def _steps(job: dict) -> list[dict]:
    return [s for s in job.get("steps", []) if isinstance(s, dict)]


def _steps_running(job: dict, needle: str) -> list[dict]:
    return [s for s in _steps(job) if needle in str(s.get("run", ""))]


def _is_blocking(step: dict) -> bool:
    # A step blocks the job unless it explicitly opts out with continue-on-error.
    return step.get("continue-on-error", False) is not True


def test_changed_files_lint_gate_exists_and_blocks() -> None:
    jobs = _load_jobs()
    assert "lint-changed" in jobs, "missing blocking changed-files lint gate"
    gate = jobs["lint-changed"]

    ruff_steps = _steps_running(gate, "ruff check")
    black_steps = _steps_running(gate, "black --check")
    assert ruff_steps, "lint-changed must run ruff check"
    assert black_steps, "lint-changed must run black --check"

    for step in (*ruff_steps, *black_steps):
        assert _is_blocking(step), (
            f"changed-files lint step must be blocking, "
            f"got continue-on-error on: {step.get('name')!r}"
        )


def test_import_linter_gate_exists_and_blocks() -> None:
    jobs = _load_jobs()
    assert "import-linter" in jobs, "missing blocking import-linter architecture gate"
    gate = jobs["import-linter"]

    lint_steps = _steps_running(gate, "lint-imports")
    assert lint_steps, "import-linter job must run lint-imports"
    for step in lint_steps:
        assert _is_blocking(step), "lint-imports step must be blocking"


def test_full_tree_lint_stays_advisory_no_bigbang_flip() -> None:
    # The full-tree lint job is a *visibility* backlog surface; flipping it to
    # blocking without first zeroing the tree would red-line CI on pre-existing
    # violations. Guard that it keeps continue-on-error until that cleanup lands.
    jobs = _load_jobs()
    assert "lint" in jobs, "expected the advisory full-tree lint job"
    full = jobs["lint"]
    tree_steps = [
        s
        for s in _steps(full)
        if "flaghunter/" in str(s.get("run", ""))
        and ("ruff" in str(s.get("run", "")) or "black" in str(s.get("run", "")))
    ]
    assert tree_steps, "advisory lint job should still run ruff/black on the tree"
    assert all(
        s.get("continue-on-error", False) is True for s in tree_steps
    ), "full-tree ruff/black must stay advisory until the tree is zeroed (B-01)"
