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
PLAYBOOK_PATH = os.path.join(
    REPO_ROOT,
    "docs",
    "dev",
    "FlagHunter_Clean_Architecture_Migration_Playbook_v0.1_2026-07-04.md",
)


def _import_linter_config_text() -> str:
    with open(CONFIG_PATH, encoding="utf-8") as handle:
        return handle.read()


def _contract_section(config_text: str, contract_name: str) -> str:
    marker = f"[importlinter:contract:{contract_name}]"
    start = config_text.index(marker)
    next_contract = config_text.find("\n[importlinter:contract:", start + len(marker))
    if next_contract == -1:
        return config_text[start:]
    return config_text[start:next_contract]


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
    config_text = _import_linter_config_text()

    assert "[importlinter:contract:domain-contract-independence]" in config_text
    assert "flaghunter.domain" in config_text


def test_application_layer_has_import_linter_boundary() -> None:
    """Application services may use ports/contracts but not concrete layers."""
    config_text = _import_linter_config_text()

    assert "[importlinter:contract:application-service-boundary]" in config_text
    assert "flaghunter.application" in config_text


def test_core_clean_architecture_import_linter_boundaries_cover_outer_layers() -> None:
    """Domain, ports, and application boundaries must include every outer layer."""
    config_text = _import_linter_config_text()
    with open(PLAYBOOK_PATH, encoding="utf-8") as handle:
        playbook_text = handle.read()

    assert "Core import-linter outer-layer coverage guard" in playbook_text

    required_by_contract = {
        "domain-contract-independence": {
            "flaghunter.adapters",
            "flaghunter.application",
            "flaghunter.config",
            "flaghunter.cpa_modules",
            "flaghunter.eval",
            "flaghunter.interface",
            "flaghunter.knowledge",
            "flaghunter.llm",
            "flaghunter.mcp.server",
            "flaghunter.playbooks",
            "flaghunter.ports",
            "flaghunter.redteam",
            "flaghunter.runtime",
            "flaghunter.session",
            "flaghunter.tools",
            "flaghunter.workspaces",
        },
        "ports-contract-boundary": {
            "flaghunter.adapters",
            "flaghunter.agents",
            "flaghunter.application",
            "flaghunter.config",
            "flaghunter.cpa_modules",
            "flaghunter.eval",
            "flaghunter.interface",
            "flaghunter.knowledge",
            "flaghunter.llm",
            "flaghunter.mcp.server",
            "flaghunter.playbooks",
            "flaghunter.redteam",
            "flaghunter.runtime",
            "flaghunter.session",
            "flaghunter.tools",
            "flaghunter.workspaces",
        },
        "application-service-boundary": {
            "flaghunter.adapters",
            "flaghunter.agents",
            "flaghunter.config",
            "flaghunter.cpa_modules",
            "flaghunter.eval",
            "flaghunter.interface",
            "flaghunter.knowledge",
            "flaghunter.llm",
            "flaghunter.mcp.server",
            "flaghunter.playbooks",
            "flaghunter.redteam",
            "flaghunter.runtime",
            "flaghunter.session",
            "flaghunter.tools",
            "flaghunter.workspaces",
        },
    }

    for contract_name, required_modules in required_by_contract.items():
        section = _contract_section(config_text, contract_name)
        assert contract_name in playbook_text
        for module_name in sorted(required_modules):
            assert module_name in section
            assert module_name in playbook_text


def test_core_import_linter_coverage_completeness_links_source_guards() -> None:
    """Import-linter core contracts must stay tied to source-guard completeness."""
    with open(PLAYBOOK_PATH, encoding="utf-8") as handle:
        playbook_text = handle.read()

    assert "Core import-linter coverage completeness guard" in playbook_text
    for guard_name in (
        "Domain contract source guard coverage completeness guard",
        "Ports source guard coverage completeness guard",
        "Application service source guard coverage completeness guard",
    ):
        assert guard_name in playbook_text
    for contract_name in (
        "domain-contract-independence",
        "ports-contract-boundary",
        "application-service-boundary",
    ):
        assert contract_name in playbook_text
