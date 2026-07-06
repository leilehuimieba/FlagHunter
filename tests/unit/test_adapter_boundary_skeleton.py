"""Boundary tests for the adapter package skeleton."""

from __future__ import annotations

import ast
import importlib
import warnings
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[2]
ADAPTERS_ROOT = REPO_ROOT / "flaghunter" / "adapters"
DOMAIN_ROOT = REPO_ROOT / "flaghunter" / "domain"
PORTS_ROOT = REPO_ROOT / "flaghunter" / "ports"
UNIT_TEST_ROOT = REPO_ROOT / "tests" / "unit"
PLAYBOOK_PATH = (
    REPO_ROOT
    / "docs"
    / "dev"
    / "FlagHunter_Clean_Architecture_Migration_Playbook_v0.1_2026-07-04.md"
)

EXPECTED_ADAPTER_PACKAGES = (
    "flaghunter.adapters",
    "flaghunter.adapters.artifacts",
    "flaghunter.adapters.audit",
    "flaghunter.adapters.crew",
    "flaghunter.adapters.mcp",
    "flaghunter.adapters.proof",
    "flaghunter.adapters.runtime",
    "flaghunter.adapters.storage",
    "flaghunter.adapters.tools",
)

EXPECTED_ADAPTER_NAMESPACE_EXPORTS = (
    "artifacts",
    "audit",
    "crew",
    "mcp",
    "proof",
    "runtime",
    "storage",
    "tools",
)

FORBIDDEN_INIT_IMPORT_PREFIXES = (
    "flaghunter.agents",
    "flaghunter.application",
    "flaghunter.config",
    "flaghunter.cpa_modules",
    "flaghunter.eval",
    "flaghunter.interface",
    "flaghunter.knowledge",
    "flaghunter.llm",
    "flaghunter.mcp",
    "flaghunter.playbooks",
    "flaghunter.redteam",
    "flaghunter.runtime",
    "flaghunter.session",
    "flaghunter.tools",
    "flaghunter.workspaces",
)

FORBIDDEN_ACTION_TOKENS = {
    "open(",
    "Path.open",
    "Path.read_text",
    "Path.write_text",
    "Path.read_bytes",
    "Path.write_bytes",
    "CTFTaskDispatcher",
    "CTFState",
    "CTFVerifier",
    "ToolExecutor",
    "WorkerPool",
    "CrewOrchestrator",
    "LocalRuntime",
    "DockerRuntime",
    "SSHRuntime",
    "subprocess",
    "subprocess.run",
    "subprocess.Popen",
    "subprocess.call",
    "asyncio.subprocess",
    "asyncio.create_subprocess_exec",
    "asyncio.create_subprocess_shell",
    "Playwright",
    "requests",
    "requests.get",
    "requests.post",
    "requests.request",
    "httpx",
    "httpx.get",
    "httpx.post",
    "httpx.request",
    "socket",
    "socket.socket",
    "write_text",
}

REQUIRED_ACTION_SINK_TOKENS = {
    "open(",
    "Path.open",
    "Path.read_text",
    "Path.write_text",
    "Path.read_bytes",
    "Path.write_bytes",
    "subprocess.run",
    "subprocess.Popen",
    "subprocess.call",
    "asyncio.create_subprocess_exec",
    "asyncio.create_subprocess_shell",
    "requests.get",
    "requests.post",
    "requests.request",
    "httpx.get",
    "httpx.post",
    "httpx.request",
    "socket.socket",
}

FORBIDDEN_PROOF_ACTION_TOKENS = {
    "verification_decision",
    "upgrade_claim_to_verified",
    "append_verification_record",
    "append_proof_record",
    "confirm_claim",
    'level="verified"',
    "level='verified'",
    "verified_flags",
}

REQUIRED_PROOF_ACTION_TOKENS = {
    "verification_decision",
    "upgrade_claim_to_verified",
    "append_verification_record",
    "append_proof_record",
    "confirm_claim",
    'level="verified"',
    "level='verified'",
    "verified_flags",
}

ALLOWED_PROOF_ACTION_TOKENS_BY_PATH = {
    "flaghunter/adapters/proof/proof_authority_adapter.py": {
        "append_proof_record",
        "confirm_claim",
    },
}

FORBIDDEN_PRODUCTION_WIRING_TOKENS = {
    "FlagHunterAgent",
    "AgentSession",
    "MCPRouter",
    "MCPServer",
    "CompositionRoot",
    "create_agent",
    "run_task_async",
}

FORBIDDEN_PUBLIC_DOMAIN_TERMS = {
    "ctf",
    "pentest",
    "exploit",
    "vulnerability",
    "hacking",
    "attack",
    "redteam",
}

REQUIRED_ADAPTER_COVERAGE_GUARD_SECTIONS = {
    "Adapter production wiring source guard",
    "Adapter action sink coverage guard",
    "Adapter proof action coverage guard",
    "Adapter outer-layer import coverage guard",
    "Adapter public surface domain-neutral naming guard",
    "Specific adapter source guard import coverage consistency guard",
}


def _parse(path: Path) -> ast.Module:
    with warnings.catch_warnings():
        warnings.simplefilter("ignore", SyntaxWarning)
        return ast.parse(path.read_text(encoding="utf-8-sig"), filename=str(path))


def _relative(path: Path) -> str:
    return path.relative_to(REPO_ROOT).as_posix()


def _imported_module_names(tree: ast.Module) -> list[str]:
    modules: list[str] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            modules.extend(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom):
            modules.append("." * node.level + (node.module or ""))
    return modules


def _python_sources(root: Path) -> list[Path]:
    assert root.is_dir(), f"missing package root: {_relative(root)}"
    return sorted(root.rglob("*.py"))


def _forbidden_proof_action_tokens_for(path: Path) -> set[str]:
    return FORBIDDEN_PROOF_ACTION_TOKENS - ALLOWED_PROOF_ACTION_TOKENS_BY_PATH.get(
        _relative(path),
        set(),
    )


def test_adapter_namespace_packages_are_importable() -> None:
    for module_name in EXPECTED_ADAPTER_PACKAGES:
        module = importlib.import_module(module_name)
        assert module.__name__ == module_name


def test_mcp_adapter_namespace_exports_task_ingress_skeleton() -> None:
    package = importlib.import_module("flaghunter.adapters.mcp")
    module = importlib.import_module("flaghunter.adapters.mcp.task_ingress_adapter")

    assert package.TaskIngressAdapter is module.TaskIngressAdapter
    assert package.__all__ == ["TaskIngressAdapter"]


def test_proof_adapter_namespace_is_reexport_only() -> None:
    package = importlib.import_module("flaghunter.adapters.proof")
    proof_authority_module = importlib.import_module(
        "flaghunter.adapters.proof.proof_authority_adapter"
    )
    verifier_module = importlib.import_module("flaghunter.adapters.proof.verifier_adapter")
    init_path = ADAPTERS_ROOT / "proof" / "__init__.py"
    tree = _parse(init_path)

    assert package.ProofAuthorityAdapter is proof_authority_module.ProofAuthorityAdapter
    assert package.VerifierAdapter is verifier_module.VerifierAdapter
    assert package.__all__ == ["ProofAuthorityAdapter", "VerifierAdapter"]

    imported_modules = _imported_module_names(tree)
    assert sorted(imported_modules) == [
        ".proof_authority_adapter",
        ".verifier_adapter",
    ]
    assert "ProofAuthorityPort" not in init_path.read_text(encoding="utf-8")
    assert "VerifierPort" not in init_path.read_text(encoding="utf-8")


def test_root_adapter_namespace_declares_managed_packages() -> None:
    module = importlib.import_module("flaghunter.adapters")

    assert module.__all__ == EXPECTED_ADAPTER_NAMESPACE_EXPORTS


def test_expected_adapter_package_list_covers_all_package_directories() -> None:
    actual = {
        "flaghunter.adapters"
        + (
            "."
            + path.parent.relative_to(ADAPTERS_ROOT).as_posix().replace("/", ".")
            if path.parent != ADAPTERS_ROOT
            else ""
        )
        for path in sorted(ADAPTERS_ROOT.rglob("__init__.py"))
    }

    assert set(EXPECTED_ADAPTER_PACKAGES) == actual


def test_adapter_package_initializers_do_not_wire_concrete_implementations() -> None:
    offenders: list[tuple[str, str]] = []

    for path in sorted(ADAPTERS_ROOT.rglob("__init__.py")):
        tree = _parse(path)
        for imported in _imported_module_names(tree):
            normalized = imported.lstrip(".")
            if normalized.startswith(FORBIDDEN_INIT_IMPORT_PREFIXES):
                offenders.append((_relative(path), imported))
        text = path.read_text(encoding="utf-8")
        offenders.extend(
            (_relative(path), token)
            for token in FORBIDDEN_ACTION_TOKENS
            if token in text
        )
        offenders.extend(
            (_relative(path), token)
            for token in _forbidden_proof_action_tokens_for(path)
            if token in text
        )

    assert offenders == []


def test_adapter_forbidden_import_prefixes_cover_outer_production_layers() -> None:
    required_prefixes = {
        "flaghunter.agents",
        "flaghunter.application",
        "flaghunter.config",
        "flaghunter.cpa_modules",
        "flaghunter.eval",
        "flaghunter.interface",
        "flaghunter.knowledge",
        "flaghunter.llm",
        "flaghunter.mcp",
        "flaghunter.playbooks",
        "flaghunter.redteam",
        "flaghunter.runtime",
        "flaghunter.session",
        "flaghunter.tools",
        "flaghunter.workspaces",
    }

    assert required_prefixes <= set(FORBIDDEN_INIT_IMPORT_PREFIXES)

    playbook = PLAYBOOK_PATH.read_text(encoding="utf-8")
    assert "Adapter outer-layer import coverage guard" in playbook
    for prefix in sorted(required_prefixes):
        assert prefix in playbook


def test_specific_adapter_source_guards_cover_outer_legacy_layers() -> None:
    required_prefixes = {
        "flaghunter.eval",
        "flaghunter.redteam",
    }
    adapter_test_paths = sorted(
        path
        for path in UNIT_TEST_ROOT.glob("test_*_adapter.py")
        if path.name != "test_adapter_boundary_skeleton.py"
    )
    assert adapter_test_paths

    missing: list[tuple[str, str]] = []
    for path in adapter_test_paths:
        text = path.read_text(encoding="utf-8")
        missing.extend(
            (_relative(path), prefix)
            for prefix in sorted(required_prefixes)
            if prefix not in text
        )

    assert missing == []

    playbook = PLAYBOOK_PATH.read_text(encoding="utf-8")
    assert "Specific adapter source guard import coverage consistency guard" in playbook
    for prefix in sorted(required_prefixes):
        assert prefix in playbook


def test_adapter_implementation_sources_do_not_wire_concrete_implementations() -> None:
    offenders: list[tuple[str, str]] = []

    for path in _python_sources(ADAPTERS_ROOT):
        if path.name == "__init__.py":
            continue

        tree = _parse(path)
        for imported in _imported_module_names(tree):
            normalized = imported.lstrip(".")
            if normalized.startswith(FORBIDDEN_INIT_IMPORT_PREFIXES):
                offenders.append((_relative(path), imported))

        text = path.read_text(encoding="utf-8")
        offenders.extend(
            (_relative(path), token)
            for token in FORBIDDEN_ACTION_TOKENS
            if token in text
        )
        offenders.extend(
            (_relative(path), token)
            for token in _forbidden_proof_action_tokens_for(path)
            if token in text
        )

    assert offenders == []


def test_adapter_action_guard_covers_explicit_sinks() -> None:
    assert REQUIRED_ACTION_SINK_TOKENS <= FORBIDDEN_ACTION_TOKENS

    playbook = PLAYBOOK_PATH.read_text(encoding="utf-8")
    assert "Adapter action sink coverage guard" in playbook
    for token in sorted(REQUIRED_ACTION_SINK_TOKENS):
        assert token in playbook


def test_adapter_proof_action_guard_covers_authority_sinks() -> None:
    assert REQUIRED_PROOF_ACTION_TOKENS <= FORBIDDEN_PROOF_ACTION_TOKENS

    playbook = PLAYBOOK_PATH.read_text(encoding="utf-8")
    assert "Adapter proof action coverage guard" in playbook
    assert "dedicated proof authority adapter" in playbook
    for token in sorted(REQUIRED_PROOF_ACTION_TOKENS):
        assert token in playbook


def test_adapter_sources_do_not_reference_production_wiring_surfaces() -> None:
    playbook = PLAYBOOK_PATH.read_text(encoding="utf-8")
    assert "Adapter production wiring source guard" in playbook
    for token in sorted(FORBIDDEN_PRODUCTION_WIRING_TOKENS):
        assert token in playbook

    offenders: list[tuple[str, str]] = []

    for path in _python_sources(ADAPTERS_ROOT):
        text = path.read_text(encoding="utf-8")
        offenders.extend(
            (_relative(path), token)
            for token in FORBIDDEN_PRODUCTION_WIRING_TOKENS
            if token in text
        )

    assert offenders == []


def test_inner_layers_do_not_import_adapter_package() -> None:
    offenders: list[tuple[str, str]] = []

    for root in (DOMAIN_ROOT, PORTS_ROOT):
        for path in _python_sources(root):
            for imported in _imported_module_names(_parse(path)):
                normalized = imported.lstrip(".")
                if normalized.startswith("flaghunter.adapters"):
                    offenders.append((_relative(path), imported))

    assert offenders == []


def test_adapter_public_names_docstrings_and_paths_are_domain_neutral() -> None:
    playbook = PLAYBOOK_PATH.read_text(encoding="utf-8")
    assert "Adapter public surface domain-neutral naming guard" in playbook
    for term in sorted(FORBIDDEN_PUBLIC_DOMAIN_TERMS):
        assert term in playbook

    offenders: list[tuple[str, str, int]] = []
    for path in _python_sources(ADAPTERS_ROOT):
        tree = _parse(path)
        path_parts = [part.lower() for part in path.relative_to(REPO_ROOT).parts[1:]]
        for part in path_parts:
            offenders.extend(
                (_relative(path), f"path part {part} contains {term}", 1)
                for term in FORBIDDEN_PUBLIC_DOMAIN_TERMS
                if term in part
            )

        module_doc = (ast.get_docstring(tree) or "").lower()
        offenders.extend(
            (_relative(path), f"module docstring contains {term}", 1)
            for term in FORBIDDEN_PUBLIC_DOMAIN_TERMS
            if term in module_doc
        )

        for node in ast.walk(tree):
            if isinstance(node, (ast.ClassDef, ast.FunctionDef, ast.AsyncFunctionDef)):
                lowered_name = node.name.lower()
                offenders.extend(
                    (_relative(path), f"{node.name} contains {term}", node.lineno)
                    for term in FORBIDDEN_PUBLIC_DOMAIN_TERMS
                    if term in lowered_name
                )
                lowered_doc = (ast.get_docstring(node) or "").lower()
                offenders.extend(
                    (
                        _relative(path),
                        f"{node.name} docstring contains {term}",
                        node.lineno,
                    )
                    for term in FORBIDDEN_PUBLIC_DOMAIN_TERMS
                    if term in lowered_doc
                )

    assert offenders == []


def test_adapter_source_guard_coverage_completeness_records_all_guard_groups() -> None:
    playbook = PLAYBOOK_PATH.read_text(encoding="utf-8")
    assert "Adapter source guard coverage completeness guard" in playbook
    for section_name in sorted(REQUIRED_ADAPTER_COVERAGE_GUARD_SECTIONS):
        assert section_name in playbook
