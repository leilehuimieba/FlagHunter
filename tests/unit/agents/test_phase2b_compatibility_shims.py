"""Phase 2B guards for legacy read-model compatibility shims."""

from __future__ import annotations

import ast
import importlib
import warnings
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[3]

SHIM_MODULES = {
    "flaghunter.agents.pa_agent.ledger_event_views": {
        "domain_module": "flaghunter.domain.challenge.contracts.ledger_events",
        "same_objects": {
            "LEDGER_EVENT_TYPES": "LEDGER_EVENT_TYPES",
            "P2_LEDGER_EVENT_TYPES": "LEDGER_EVENT_TYPES",
            "build_ledger_event_readback": "build_ledger_event_readback",
            "build_p2_ledger_event_readback": "build_ledger_event_readback",
        },
    },
    "flaghunter.agents.pa_agent.task_dag_plan": {
        "domain_module": "flaghunter.domain.challenge.contracts.task_dag_plan",
        "same_objects": {
            "TASK_DAG_PLAN_SCHEMA_VERSION": "TASK_DAG_PLAN_SCHEMA_VERSION",
            "TaskDAGPlan": "TaskDAGPlan",
            "TaskDAGNode": "TaskDAGNode",
            "TaskDAGEdge": "TaskDAGEdge",
            "select_next_ready_task": "select_next_ready_task",
            "build_task_dag_plan_readback": "build_task_dag_plan_readback",
        },
    },
}

FORBIDDEN_IMPORT_PREFIXES = (
    "flaghunter.tools",
    "flaghunter.runtime",
    "flaghunter.interface",
    "flaghunter.mcp",
    "flaghunter.session",
    "flaghunter.harness",
)

FORBIDDEN_SIDE_EFFECT_TOKENS = {
    "subprocess",
    "asyncio.subprocess",
    "open(",
    "write_text",
    "requests",
    "httpx",
    "socket",
    "Playwright",
    "ToolExecutor",
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


def _module_path(module_name: str) -> Path:
    return REPO_ROOT / (module_name.replace(".", "/") + ".py")


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


def test_legacy_read_model_shims_reexport_neutral_contract_objects() -> None:
    for shim_name, spec in SHIM_MODULES.items():
        shim = importlib.import_module(shim_name)
        domain = importlib.import_module(str(spec["domain_module"]))

        for shim_attr, domain_attr in spec["same_objects"].items():
            assert getattr(shim, shim_attr) is getattr(domain, domain_attr)


def test_legacy_read_model_shims_only_import_neutral_contracts() -> None:
    offenders: list[tuple[str, str]] = []

    for shim_name, spec in SHIM_MODULES.items():
        path = _module_path(shim_name)
        domain_module = str(spec["domain_module"])
        allowed_imports = {
            "__future__",
            domain_module,
            domain_module.removeprefix("flaghunter.agents.pa_agent"),
        }
        for imported in _imported_module_names(_parse(path)):
            normalized = imported.lstrip(".")
            if normalized in allowed_imports:
                continue
            if normalized.startswith(FORBIDDEN_IMPORT_PREFIXES):
                offenders.append((_relative(path), imported))

    assert offenders == []


def test_legacy_read_model_shims_have_no_side_effect_or_proof_actions() -> None:
    offenders: list[tuple[str, str]] = []

    for shim_name in SHIM_MODULES:
        path = _module_path(shim_name)
        text = path.read_text(encoding="utf-8")
        offenders.extend(
            (_relative(path), token)
            for token in FORBIDDEN_SIDE_EFFECT_TOKENS
            if token in text
        )
        offenders.extend(
            (_relative(path), token)
            for token in FORBIDDEN_PROOF_ACTION_TOKENS
            if token in text
        )

    assert offenders == []
