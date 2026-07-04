"""Architecture-enforcement guard: invariant I1 (dependencies point DOWNWARD).

This test runs the import-linter contracts declared in the repo-root
``.importlinter`` file and asserts every contract is KEPT. It locks in the
layered/forbidden contracts that already hold so any NEW upward import
(violating the 6-layer top-down skeleton) fails the gate.

The contracts intentionally carry a small set of ``ignore_imports`` baseline
entries (each tagged ``# DEBT:`` in ``.importlinter``) for pre-existing
structural debt, so the gate enforces "no new violations" rather than a clean
sheet that does not yet exist.

If import-linter is not installed (e.g. a minimal env without the dev extra),
the test skips gracefully. When it IS installed it asserts green for real.
"""

from __future__ import annotations

import os

import pytest

# Repo root = two levels up from this file (tests/unit/ -> repo root).
REPO_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
CONFIG_PATH = os.path.join(REPO_ROOT, ".importlinter")


def test_import_linter_contracts_all_kept() -> None:
    """All import-linter contracts in .importlinter must be KEPT."""
    try:
        from importlinter import configuration
        from importlinter.application.use_cases import lint_imports
    except ImportError:  # pragma: no cover - env without dev extra
        pytest.skip("import-linter not installed; skipping architecture gate")

    # Register import-linter's built-in option readers/contract types. The CLI
    # does this at import time; the library API requires it explicitly.
    configuration.configure()

    assert os.path.isfile(CONFIG_PATH), f"missing import-linter config: {CONFIG_PATH}"

    # lint_imports() resolves the config relative to CWD; run from repo root so
    # it picks up the root-level .importlinter and the installed flaghunter pkg.
    prev_cwd = os.getcwd()
    os.chdir(REPO_ROOT)
    try:
        all_kept = lint_imports(config_filename=CONFIG_PATH)
    finally:
        os.chdir(prev_cwd)

    assert all_kept is True, (
        "import-linter reported a BROKEN contract (invariant I1 violation). "
        "Run `lint-imports` from the repo root to see which upward import was "
        "introduced, then either remove it or, if it is accepted debt, add a "
        "`# DEBT:`-tagged ignore_imports entry in .importlinter."
    )


def test_domain_layer_has_import_linter_boundary() -> None:
    """The neutral domain layer must stay below ports and concrete layers."""
    config_text = open(CONFIG_PATH, encoding="utf-8").read()

    assert "[importlinter:contract:domain-contract-independence]" in config_text
    assert "flaghunter.domain" in config_text


def test_application_layer_has_import_linter_boundary() -> None:
    """Application services may use ports/contracts but not concrete layers."""
    config_text = open(CONFIG_PATH, encoding="utf-8").read()

    assert "[importlinter:contract:application-service-boundary]" in config_text
    assert "flaghunter.application" in config_text
