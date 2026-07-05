"""Boundary tests for the public ports package.

New public architecture contracts should use domain-neutral names, while legacy
CTF/security names are treated as adapter/legacy implementation details until
explicitly migrated.
"""

from __future__ import annotations

import ast
import importlib
import inspect
import warnings
from pathlib import Path
from typing import Any


REPO_ROOT = Path(__file__).resolve().parents[2]
PORTS_ROOT = REPO_ROOT / "flaghunter" / "ports"
PLAYBOOK_PATH = (
    REPO_ROOT
    / "docs"
    / "dev"
    / "FlagHunter_Clean_Architecture_Migration_Playbook_v0.1_2026-07-04.md"
)


EXPECTED_PORTS = {
    "flaghunter.ports.tool_runner": {
        "ToolRunnerPort": {"run_tool"},
    },
    "flaghunter.ports.runtime_action": {
        "RuntimeActionPort": {"run_command"},
    },
    "flaghunter.ports.proof_authority": {
        "VerifierPort": {"review_claim"},
        "ProofAuthorityPort": {
            "append_proof_record",
            "confirm_claim",
        },
    },
    "flaghunter.ports.state_store": {
        "StateStorePort": {"load_snapshot", "save_snapshot"},
        "ClaimStorePort": {
            "create_candidate_claim",
            "find_claims",
            "append_evidence_trace",
        },
    },
    "flaghunter.ports.audit_store": {
        "AuditStorePort": {"append_event", "query_events"},
        "ArtifactStorePort": {"register_artifact", "get_artifact"},
        "CheckpointStorePort": {"create_checkpoint", "load_checkpoint"},
        "ReadModelStorePort": {"get_read_model", "list_read_models"},
    },
    "flaghunter.ports.crew_bridge": {
        "CrewBridgePort": {"dispatch_task"},
        "TaskDAGRunnerPort": {"run_ready_task"},
    },
    "flaghunter.ports.task_ingress": {
        "TaskIngressPort": {"submit_task"},
    },
}


FORBIDDEN_IMPORT_PREFIXES = (
    "flaghunter.agents",
    "flaghunter.tools",
    "flaghunter.runtime",
    "flaghunter.interface",
    "flaghunter.mcp",
    "flaghunter.session",
)

FORBIDDEN_ACTION_TOKENS = {
    "subprocess",
    "asyncio.subprocess",
    "execute_tools",
    "_execute_tools",
    "WorkerPool",
    "CTFTaskDispatcher",
    "ToolExecutor",
    "LocalRuntime",
    "DockerRuntime",
    "SSHRuntime",
    "Playwright",
    "write_text",
    "open(",
    "requests",
    "httpx",
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

FORBIDDEN_PROOF_CALLS = {
    "add_flag",
    "create_claim",
    "build_verification_decision_event",
    "verification_decision",
}

FORBIDDEN_PUBLIC_DOMAIN_TERMS = {
    "ctf",
    "pentest",
    "exploit",
    "vulnerability",
    "hacking",
}


def _ports_sources() -> list[Path]:
    assert PORTS_ROOT.is_dir(), "flaghunter.ports package must exist"
    return sorted(PORTS_ROOT.rglob("*.py"))


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


def _is_protocol(cls: type[Any]) -> bool:
    return bool(getattr(cls, "_is_protocol", False))


def _is_runtime_protocol(cls: type[Any]) -> bool:
    return bool(getattr(cls, "_is_runtime_protocol", False))


def test_expected_ports_are_importable_and_reexported() -> None:
    """New public contracts use neutral names; legacy terms stay behind adapters."""
    package = importlib.import_module("flaghunter.ports")

    for module_name, expected_classes in EXPECTED_PORTS.items():
        module = importlib.import_module(module_name)
        for class_name in expected_classes:
            assert getattr(module, class_name).__name__ == class_name
            assert getattr(package, class_name).__name__ == class_name


def test_each_port_is_a_runtime_checkable_protocol_with_expected_methods() -> None:
    for module_name, expected_classes in EXPECTED_PORTS.items():
        module = importlib.import_module(module_name)
        for class_name, methods in expected_classes.items():
            cls = getattr(module, class_name)
            assert inspect.isclass(cls), f"{class_name} must be a class"
            assert _is_protocol(cls), f"{class_name} must be a Protocol"
            assert _is_runtime_protocol(cls), (
                f"{class_name} should be runtime-checkable for adapter boundary checks"
            )
            for method in methods:
                assert callable(getattr(cls, method, None)), (
                    f"{class_name}.{method} must be declared"
                )


def test_ports_package_does_not_import_concrete_layers() -> None:
    offenders: list[tuple[str, str]] = []
    for path in _ports_sources():
        for imported in _imported_module_names(_parse(path)):
            normalized = imported.lstrip(".")
            if normalized.startswith(FORBIDDEN_IMPORT_PREFIXES):
                offenders.append((_relative(path), imported))

    assert offenders == []


def test_ports_package_contains_no_action_or_concrete_implementation_surfaces() -> None:
    offenders: list[tuple[str, str]] = []
    for path in _ports_sources():
        text = path.read_text(encoding="utf-8")
        offenders.extend(
            (_relative(path), token)
            for token in FORBIDDEN_ACTION_TOKENS
            if token in text
        )

    assert offenders == []


def test_ports_package_contains_no_production_wiring_surfaces() -> None:
    playbook = PLAYBOOK_PATH.read_text(encoding="utf-8")
    assert "Ports production wiring source guard" in playbook
    for token in sorted(FORBIDDEN_PRODUCTION_WIRING_TOKENS):
        assert token in playbook

    offenders: list[tuple[str, str]] = []
    for path in _ports_sources():
        text = path.read_text(encoding="utf-8")
        offenders.extend(
            (_relative(path), token)
            for token in FORBIDDEN_PRODUCTION_WIRING_TOKENS
            if token in text
        )

    assert offenders == []


def test_port_methods_are_contract_only_ellipsis_stubs() -> None:
    offenders: list[tuple[str, str, int]] = []
    for path in _ports_sources():
        tree = _parse(path)
        for node in ast.walk(tree):
            if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                continue
            non_docstring_body = list(node.body)
            if (
                non_docstring_body
                and isinstance(non_docstring_body[0], ast.Expr)
                and isinstance(non_docstring_body[0].value, ast.Constant)
                and isinstance(non_docstring_body[0].value.value, str)
            ):
                non_docstring_body = non_docstring_body[1:]
            if len(non_docstring_body) != 1:
                offenders.append((_relative(path), node.name, node.lineno))
                continue
            body_node = non_docstring_body[0]
            if not (
                isinstance(body_node, ast.Expr)
                and isinstance(body_node.value, ast.Constant)
                and body_node.value.value is Ellipsis
            ):
                offenders.append((_relative(path), node.name, node.lineno))

    assert offenders == []


def test_proof_authority_port_does_not_emit_or_write_proof() -> None:
    offenders: list[tuple[str, str, int]] = []
    for path in _ports_sources():
        tree = _parse(path)
        for node in ast.walk(tree):
            if (
                isinstance(node, ast.Call)
                and isinstance(node.func, ast.Attribute)
                and node.func.attr in FORBIDDEN_PROOF_CALLS
            ):
                offenders.append((_relative(path), node.func.attr, node.lineno))
            if (
                isinstance(node, ast.Call)
                and isinstance(node.func, ast.Name)
                and node.func.id in FORBIDDEN_PROOF_CALLS
            ):
                offenders.append((_relative(path), node.func.id, node.lineno))
            if (
                isinstance(node, ast.Constant)
                and isinstance(node.value, str)
                and "verified" in node.value
            ):
                offenders.append((_relative(path), node.value, node.lineno))

    assert offenders == []


def test_new_ports_public_names_and_docstrings_are_domain_neutral() -> None:
    """New public architecture contracts use neutral names; legacy terms stay in adapters."""
    offenders: list[tuple[str, str, int]] = []
    for path in _ports_sources():
        tree = _parse(path)
        module_doc = ast.get_docstring(tree) or ""
        lowered_doc = module_doc.lower()
        offenders.extend(
            (_relative(path), f"module docstring contains {term}", 1)
            for term in FORBIDDEN_PUBLIC_DOMAIN_TERMS
            if term in lowered_doc
        )
        for node in ast.walk(tree):
            if isinstance(node, (ast.ClassDef, ast.FunctionDef, ast.AsyncFunctionDef)):
                lowered_name = node.name.lower()
                offenders.extend(
                    (_relative(path), f"{node.name} contains {term}", node.lineno)
                    for term in FORBIDDEN_PUBLIC_DOMAIN_TERMS
                    if term in lowered_name
                )
                docstring = (ast.get_docstring(node) or "").lower()
                offenders.extend(
                    (
                        _relative(path),
                        f"{node.name} docstring contains {term}",
                        node.lineno,
                    )
                    for term in FORBIDDEN_PUBLIC_DOMAIN_TERMS
                    if term in docstring
                )

    assert offenders == []
