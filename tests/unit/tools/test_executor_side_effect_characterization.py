"""Characterization tests for legacy ToolExecutor side-effect ownership."""

from __future__ import annotations

import ast
import importlib
import warnings
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[3]
EXECUTOR_PATH = REPO_ROOT / "flaghunter" / "tools" / "executor.py"
TOOLS_INIT_PATH = REPO_ROOT / "flaghunter" / "tools" / "__init__.py"


def _parse_executor() -> ast.Module:
    with warnings.catch_warnings():
        warnings.simplefilter("ignore", SyntaxWarning)
        return ast.parse(
            EXECUTOR_PATH.read_text(encoding="utf-8-sig"),
            filename=str(EXECUTOR_PATH),
        )


def _parse_tools_init() -> ast.Module:
    with warnings.catch_warnings():
        warnings.simplefilter("ignore", SyntaxWarning)
        return ast.parse(
            TOOLS_INIT_PATH.read_text(encoding="utf-8-sig"),
            filename=str(TOOLS_INIT_PATH),
        )


def _imported_module_names(tree: ast.Module) -> list[str]:
    modules: list[str] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            modules.extend(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom):
            modules.append("." * node.level + (node.module or ""))
    return modules


def _class_method(
    tree: ast.Module,
    class_name: str,
    method_name: str,
) -> ast.FunctionDef | ast.AsyncFunctionDef:
    for node in ast.walk(tree):
        if not isinstance(node, ast.ClassDef) or node.name != class_name:
            continue
        for item in node.body:
            if (
                isinstance(item, (ast.FunctionDef, ast.AsyncFunctionDef))
                and item.name == method_name
            ):
                return item
    raise AssertionError(f"{class_name}.{method_name} was not found")


def _source_for(node: ast.AST) -> str:
    source = EXECUTOR_PATH.read_text(encoding="utf-8")
    return ast.get_source_segment(source, node) or ""


def test_tool_executor_execute_retains_legacy_side_effect_surface_markers() -> None:
    method = _class_method(_parse_executor(), "ToolExecutor", "execute")
    source = _source_for(method)

    required_markers = {
        "scope check": "_m4_scope_check",
        "cookie auto-inject": "_COOKIE_AUTO_INJECT_TOOLS",
        "credential note read": "get_all_notes_sync",
        "stealth tool set": "_STEALTH_TOOLS",
        "stealth mode": "_is_stealth_active",
        "stealth delay": "_stealth_delay",
        "tool execution": "tool.execute",
        "tool timeout": "asyncio.wait_for",
        "flag scanning": "_FLAG_PATTERN",
        "flag handling": "_handle_flag_discovery",
        "missing-tool detection": "_looks_like_missing_tool_error",
        "install advisory": "_build_tool_install_confirmation_message",
        "tool install notification": "tool_install_required",
        "missing-tool note lock": "_notes_lock",
    }
    missing = [
        (surface, marker)
        for surface, marker in sorted(required_markers.items())
        if marker not in source
    ]

    assert missing == []


def test_tool_executor_batch_still_delegates_through_legacy_execute() -> None:
    method = _class_method(_parse_executor(), "ToolExecutor", "execute_batch")
    source = _source_for(method)

    assert "self.execute(tool, args)" in source
    assert "asyncio.gather" in source
    assert "_batch_semaphore" in source
    assert "ToolRunnerAdapter" not in source
    assert "flaghunter.adapters.tools" not in source


def test_tool_executor_module_does_not_import_tool_runner_adapter() -> None:
    tree = _parse_executor()
    offenders: list[tuple[str, int]] = []

    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                if alias.name.startswith("flaghunter.adapters.tools"):
                    offenders.append((alias.name, node.lineno))
        if isinstance(node, ast.ImportFrom):
            module = node.module or ""
            if module.startswith("flaghunter.adapters.tools"):
                offenders.append((module, node.lineno))
            for alias in node.names:
                if alias.name == "ToolRunnerAdapter":
                    offenders.append((alias.name, node.lineno))

    assert offenders == []


def test_tools_namespace_keeps_tool_executor_legacy_reexport_only() -> None:
    package = importlib.import_module("flaghunter.tools")
    executor_module = importlib.import_module("flaghunter.tools.executor")
    source = TOOLS_INIT_PATH.read_text(encoding="utf-8")

    assert package.ToolExecutor is executor_module.ToolExecutor
    assert "ToolExecutor" in package.__all__
    assert "ExecutionResult" not in package.__all__

    imported_modules = set(_imported_module_names(_parse_tools_init()))
    assert ".executor" in imported_modules
    assert ".loader" in imported_modules
    assert ".registry" in imported_modules

    forbidden_tokens = {
        "ToolRunnerAdapter",
        "ToolRunnerPort",
        "flaghunter.adapters.tools",
        "flaghunter.ports.tool_runner",
        "ExecutionResult",
    }
    offenders = sorted(token for token in forbidden_tokens if token in source)

    assert offenders == []
