"""Local tool availability checks for CTF execution chains."""

from __future__ import annotations

import importlib.util
import os
import shutil
import subprocess
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

from ._tool_env import check_disk_space, find_tool, suggest_missing_tool


BUILTIN_TOOLS = {"browser", "terminal", "web_search", "knowledge_search", "http_request", "notes", "finish"}

INSTALL_COMMANDS: dict[str, str] = {
    "browser": "pip install playwright && playwright install chromium",
    "curl": "apt install curl",
    "http_request": "pip install httpx",
    "httpx": "pip install httpx",
    "sqlmap": "pip install sqlmap",
    "ffuf": "go install github.com/ffuf/ffuf/v2@latest",
    "nuclei": "go install github.com/projectdiscovery/nuclei/v3/cmd/nuclei@latest",
    "nikto": "apt install nikto",
    "wfuzz": "pip install wfuzz",
    "xsser": "pip install xsser",
    "commix": "pip install commix",
    "burpsuite": "apt install burpsuite",
    "chromium": "apt install chromium",
    "firefox": "apt install firefox",
    "playwright": "pip install playwright && playwright install chromium",
    "python3": "apt install python3",
    "node": "apt install nodejs npm",
    "go": "apt install golang",
    "nc": "apt install netcat-openbsd",
    "socat": "apt install socat",
    "web_search": "pip install httpx",
}

_VERSION_FLAGS: dict[str, list[list[str]]] = {
    "python3": [["--version"]],
    "node": [["--version"]],
    "go": [["version"]],
    "ffuf": [["-V"], ["--help"]],
    "nuclei": [["-version"], ["-h"]],
    "sqlmap": [["--version"], ["-h"]],
    "nikto": [["-Version"], ["-H"]],
    "wfuzz": [["--version"], ["-h"]],
    "curl": [["--version"]],
    "firefox": [["--version"]],
    "chromium": [["--version"]],
    "nc": [["-h"]],
    "socat": [["-V"], ["-h"]],
    "burpsuite": [["--help"]],
    "commix": [["--version"], ["-h"]],
    "xsser": [["--version"], ["-h"]],
}


@dataclass
class ToolStatus:
    available: bool
    path: str | None = None
    version: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


class ToolMissingError(RuntimeError):
    def __init__(self, missing: dict[str, ToolStatus]):
        self.missing = missing
        names = ", ".join(sorted(missing))
        super().__init__(f"Missing required tools: {names}")


class ToolGuard:
    """Check external tooling before executing a CTF chain."""

    def __init__(self, runtime=None):
        self.runtime = runtime

    def check(self, tool_name: str) -> ToolStatus:
        normalized = str(tool_name or "").strip().lower()
        if not normalized:
            return ToolStatus(available=False)

        if normalized in BUILTIN_TOOLS:
            if normalized == "browser":
                has_runtime = self.runtime is not None and hasattr(
                    self.runtime, "browser_action"
                )
                has_dep = _module_available("playwright")
                return ToolStatus(
                    available=bool(has_runtime and has_dep),
                    path="runtime.browser_action" if has_runtime else None,
                    version="playwright" if has_dep else None,
                )
            if normalized == "http_request":
                has_runtime = self.runtime is not None and hasattr(
                    self.runtime, "proxy_action"
                )
                has_dep = _module_available("httpx")
                return ToolStatus(
                    available=bool(has_runtime and has_dep),
                    path="runtime.proxy_action" if has_runtime else None,
                    version="httpx" if has_dep else None,
                )
            if normalized == "web_search":
                has_dep = _module_available("httpx")
                has_provider = bool(
                    os.getenv("TAVILY_API_KEY")
                    or os.getenv("BRAVE_SEARCH_API_KEY")
                    or find_tool("opencli")
                    or shutil.which("opencli.cmd")
                    or shutil.which("opencli.exe")
                )
                return ToolStatus(
                    available=bool(has_dep and has_provider),
                    path="builtin:web_search" if has_dep else None,
                    version="httpx" if has_dep else None,
                )
            if normalized == "knowledge_search":
                return ToolStatus(
                    available=True,
                    path="builtin:knowledge_search",
                    version="local-rag",
                )
            if normalized == "terminal" and self.runtime is not None:
                return ToolStatus(
                    available=hasattr(self.runtime, "execute_command"),
                    path=(
                        "runtime.execute_command"
                        if hasattr(self.runtime, "execute_command")
                        else None
                    ),
                    version=None,
                )
            return ToolStatus(available=True, path=f"builtin:{normalized}", version=None)

        resolved = find_tool(normalized)
        if not resolved and normalized == "python3":
            resolved = shutil.which("python")
        if not resolved and normalized == "nc":
            resolved = find_tool("netcat") or shutil.which("ncat")
        if not resolved and normalized == "chromium":
            resolved = find_tool("chrome") or shutil.which("chromium-browser")

        if not resolved:
            return ToolStatus(available=False, path=None, version=None)

        version = self._detect_version(normalized, resolved)
        return ToolStatus(available=True, path=resolved, version=version)

    def check_batch(self, tools: list[str]) -> dict[str, ToolStatus]:
        return {tool: self.check(tool) for tool in tools}

    def suggest_install(self, tool_name: str) -> str:
        normalized = str(tool_name or "").strip().lower()
        if normalized in INSTALL_COMMANDS:
            return INSTALL_COMMANDS[normalized]
        hint = suggest_missing_tool(normalized)
        if "Install:" in hint:
            return hint.split("Install:", 1)[1].strip()
        return hint

    async def install_and_verify(self, tool_name: str) -> bool:
        if self.runtime is None or not hasattr(self.runtime, "execute_command"):
            return False

        disk = check_disk_space(str(Path.cwd().anchor or Path.cwd()))
        if float(disk.get("free_gb", 0.0)) < 0.5:
            raise RuntimeError("Insufficient disk space for auto-install (<500MB free)")

        command = self.suggest_install(tool_name)
        result = await self.runtime.execute_command(command, timeout=900)
        if getattr(result, "exit_code", 1) != 0:
            return False
        return self.check(tool_name).available

    def require(self, tools: list[str]) -> dict[str, ToolStatus]:
        statuses = self.check_batch(tools)
        missing = {name: status for name, status in statuses.items() if not status.available}
        if missing:
            raise ToolMissingError(missing)
        return statuses

    def _detect_version(self, tool_name: str, resolved_path: str) -> str | None:
        attempts = _VERSION_FLAGS.get(tool_name, [["--version"], ["-V"], ["version"]])
        binary = resolved_path
        for args in attempts:
            try:
                proc = subprocess.run(
                    [binary, *args],
                    capture_output=True,
                    text=True,
                    timeout=8,
                    shell=False,
                )
            except Exception:
                continue
            output = (proc.stdout or proc.stderr or "").strip()
            if output:
                return output.splitlines()[0][:160]
        return None


def _module_available(module_name: str) -> bool:
    return importlib.util.find_spec(module_name) is not None


__all__ = ["ToolGuard", "ToolStatus", "ToolMissingError"]
