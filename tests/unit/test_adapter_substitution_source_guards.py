"""Source guards for adapter substitution fixtures."""

from __future__ import annotations

import ast
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[2]
SUBSTITUTION_TEST_PATH = REPO_ROOT / "tests" / "unit" / "test_adapter_port_substitution.py"

ALLOWED_FLAGHUNTER_IMPORT_PREFIXES = (
    "flaghunter.adapters",
    "flaghunter.ports",
)

FORBIDDEN_IMPORT_PREFIXES = (
    "flaghunter.agents",
    "flaghunter.config",
    "flaghunter.interface",
    "flaghunter.knowledge",
    "flaghunter.llm",
    "flaghunter.mcp",
    "flaghunter.runtime",
    "flaghunter.session",
    "flaghunter.tools",
)

FORBIDDEN_SIDE_EFFECT_CALLS = {
    "open",
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

FORBIDDEN_PRODUCTION_TOKENS = {
    "CTFTaskDispatcher",
    "CTFVerifier",
    "ToolExecutor",
    "WorkerPool",
    "CrewOrchestrator",
    "LocalRuntime",
    "DockerRuntime",
    "SSHRuntime",
}

FORBIDDEN_PROOF_AUTHORITY_TOKENS = {
    "ProofAuthorityPort",
    "ProofAuthorityAdapter",
    "append_proof_record",
    "append_verification_record",
    "confirm_claim",
    "upgrade_claim_to_verified",
    'level="verified"',
    "level='verified'",
    "verified_flags",
    "verifiedFlags",
}


def _parse_substitution_test() -> ast.Module:
    assert SUBSTITUTION_TEST_PATH.is_file(), "adapter substitution fixture must exist"
    return ast.parse(
        SUBSTITUTION_TEST_PATH.read_text(encoding="utf-8"),
        filename=str(SUBSTITUTION_TEST_PATH),
    )


def _imported_module_names(tree: ast.Module) -> list[str]:
    modules: list[str] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            modules.extend(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom):
            modules.append("." * node.level + (node.module or ""))
    return modules


def _call_name(node: ast.AST) -> str:
    if isinstance(node, ast.Name):
        return node.id
    if isinstance(node, ast.Attribute):
        parent = _call_name(node.value)
        return f"{parent}.{node.attr}" if parent else node.attr
    return ""


def test_adapter_substitution_fixtures_do_not_import_concrete_layers() -> None:
    offenders: list[str] = []

    for imported in _imported_module_names(_parse_substitution_test()):
        normalized = imported.lstrip(".")
        if not normalized.startswith("flaghunter."):
            continue
        if normalized.startswith(ALLOWED_FLAGHUNTER_IMPORT_PREFIXES):
            continue
        if normalized.startswith(FORBIDDEN_IMPORT_PREFIXES):
            offenders.append(imported)
            continue
        offenders.append(imported)

    assert offenders == []


def test_adapter_substitution_fixtures_have_no_side_effect_sinks() -> None:
    offenders: list[tuple[str, int]] = []

    for node in ast.walk(_parse_substitution_test()):
        if not isinstance(node, ast.Call):
            continue
        call_name = _call_name(node.func)
        if call_name in FORBIDDEN_SIDE_EFFECT_CALLS:
            offenders.append((call_name, node.lineno))

    assert offenders == []


def test_adapter_substitution_fixtures_have_no_proof_authority_write_surfaces() -> None:
    text = SUBSTITUTION_TEST_PATH.read_text(encoding="utf-8")

    offenders = sorted(
        token
        for token in FORBIDDEN_PRODUCTION_TOKENS | FORBIDDEN_PROOF_AUTHORITY_TOKENS
        if token in text
    )

    assert offenders == []
