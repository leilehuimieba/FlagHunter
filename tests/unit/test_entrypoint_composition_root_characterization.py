"""Characterization tests for entrypoint composition-root usage."""

from __future__ import annotations

import ast
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[2]


def _source(relative_path: str) -> str:
    return (REPO_ROOT / relative_path).read_text(encoding="utf-8-sig")


def _function_source(relative_path: str, function_name: str) -> str:
    path = REPO_ROOT / relative_path
    text = path.read_text(encoding="utf-8-sig")
    tree = ast.parse(text, filename=str(path))
    for node in tree.body:
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and node.name == function_name:
            return ast.get_source_segment(text, node) or ""
    raise AssertionError(f"{function_name} was not found in {relative_path}")


def test_presentation_entrypoints_currently_use_agent_session_create() -> None:
    entrypoints = {
        "CLI": _function_source("flaghunter/interface/cli.py", "run_cli"),
        "TUI": _source("flaghunter/interface/tui.py"),
        "Web": _function_source("flaghunter/interface/web_server.py", "_run_agent_task"),
        "MCP server bootstrap": _function_source("flaghunter/interface/main.py", "_initialize"),
    }

    common_forbidden_direct_assembly = (
        "FlagHunterAgent(",
        "build_runtime(",
        "LLM(model=",
    )

    for name, source in entrypoints.items():
        assert "AgentSession.create" in source, name
        for token in common_forbidden_direct_assembly:
            assert token not in source, f"{name} still contains {token}"
    for name in ("CLI", "Web", "MCP server bootstrap"):
        assert "get_all_tools(" not in entrypoints[name], name


def test_web_entrypoint_still_uses_compatibility_initializer_seam() -> None:
    source = _function_source("flaghunter/interface/web_server.py", "_run_agent_task")

    assert 'importlib.import_module("flaghunter.interface.initializer")' in source
    assert "builder=initializer_module.build_agent_components" in source
    assert "AgentSession.create" in source


def test_mcp_task_execution_routes_construction_through_agent_session_after_approval() -> None:
    mcp_source = _source("flaghunter/mcp/server/mcp_tools.py")
    make_agent_source = _function_source("flaghunter/mcp/server/mcp_tools.py", "_make_agent")
    builder_source = _function_source(
        "flaghunter/mcp/server/mcp_tools.py",
        "_build_mcp_task_components",
    )
    drive_task_source = _function_source("flaghunter/mcp/server/mcp_tools.py", "_drive_task")

    assert "AgentSession.create" in make_agent_source
    assert "builder=_build_mcp_task_components" in make_agent_source
    assert "FlagHunterAgent(" not in make_agent_source
    assert "runtime = _RuntimeClass(**_runtime_kwargs)" not in make_agent_source
    assert "FlagHunterAgent(" in builder_source
    assert "runtime = _RuntimeClass(**_runtime_kwargs)" in builder_source
    assert "CTFTaskDispatcher(" in drive_task_source


def test_mcp_task_execution_session_wiring_stays_inside_mcp_tools() -> None:
    server_root = REPO_ROOT / "flaghunter" / "mcp" / "server"
    offenders: list[tuple[str, str]] = []
    forbidden_outside_mcp_tools = (
        "AgentSession",
        "_build_mcp_task_components",
        "FlagHunterAgent(",
        "CTFTaskDispatcher(",
        "_RuntimeClass(",
    )

    for path in sorted(server_root.glob("*.py")):
        relative = path.relative_to(REPO_ROOT).as_posix()
        source = path.read_text(encoding="utf-8-sig")
        if path.name == "mcp_tools.py":
            continue
        offenders.extend(
            (relative, token)
            for token in forbidden_outside_mcp_tools
            if token in source
        )

    assert offenders == []
