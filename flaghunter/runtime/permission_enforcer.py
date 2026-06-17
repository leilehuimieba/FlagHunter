"""Permission enforcer for tool execution safety.

Classifies tools and commands by risk gradient:
  RECON_ONLY → VULN_SCAN → EXPLOIT → POST_EXPLOIT → ALLOW
"""

from __future__ import annotations

import os
import re
from dataclasses import dataclass
from enum import IntEnum
from typing import Any


class PermissionMode(IntEnum):
    RECON_ONLY = 1       # passive recon: nmap -sL, subfinder, whatweb, whois
    VULN_SCAN = 2        # active scanning: nuclei, nikto, nmap -sV --script vuln
    EXPLOIT = 3          # exploitation: sqlmap --os-shell, msf exploit, hydra
    POST_EXPLOIT = 4     # post-exploitation: mimikatz, psexec, reverse shell
    ALLOW = 99           # unrestricted (default)


# ── Tool → minimum required permission mode ────────────────────────────────
_TOOL_RISK_MAP: dict[str, PermissionMode] = {
    # Recon tools (read-only network discovery)
    "subfinder": PermissionMode.RECON_ONLY,
    "gau": PermissionMode.RECON_ONLY,
    "httpx_probe": PermissionMode.RECON_ONLY,
    "whatweb": PermissionMode.RECON_ONLY,
    "katana": PermissionMode.RECON_ONLY,
    "wayback": PermissionMode.RECON_ONLY,
    "web_search": PermissionMode.RECON_ONLY,
    "knowledge_search": PermissionMode.RECON_ONLY,
    "dirscan": PermissionMode.RECON_ONLY,
    "gf": PermissionMode.RECON_ONLY,
    "read": PermissionMode.RECON_ONLY,
    "notes": PermissionMode.RECON_ONLY,

    # Vuln scan tools (active probing but no exploitation)
    "nuclei": PermissionMode.VULN_SCAN,
    "afrog": PermissionMode.VULN_SCAN,
    "dalfox": PermissionMode.VULN_SCAN,
    "waf": PermissionMode.VULN_SCAN,
    "nikto": PermissionMode.VULN_SCAN,
    "nmap": PermissionMode.VULN_SCAN,
    "fscan": PermissionMode.VULN_SCAN,
    "recon_bundle": PermissionMode.VULN_SCAN,

    # Exploit tools (active exploitation)
    "sqlmap": PermissionMode.EXPLOIT,
    "hydra": PermissionMode.EXPLOIT,
    "http_request": PermissionMode.EXPLOIT,
    "login_flow": PermissionMode.EXPLOIT,
    "browser": PermissionMode.EXPLOIT,
    "opencli_browser": PermissionMode.EXPLOIT,

    # Post-exploit tools
    "msf": PermissionMode.POST_EXPLOIT,
    "pwn": PermissionMode.POST_EXPLOIT,
    "binary": PermissionMode.POST_EXPLOIT,
    "radare2": PermissionMode.POST_EXPLOIT,
    "angr_solve": PermissionMode.POST_EXPLOIT,
    "crypto_solve": PermissionMode.POST_EXPLOIT,
}

# ── Reverse shell / dangerous command patterns ──────────────────────────────
_REVERSE_SHELL_PATTERNS: list[re.Pattern] = [
    re.compile(rb, re.IGNORECASE) for rb in [
        # Reverse shells
        r"\bnc\s+.*-e\s+/bin/(?:ba|z|a)?sh",
        r"\bnc\s+.*-c\s+(?:ba|z|a)?sh",
        r"\bbash\s+-i\s+>&.*/dev/tcp/",
        r"\bpython3?\s+-c\s+.*(?:pty|spawn|socket)",
        r"\bperl\s+-e\s+.*socket",
        r"\bruby\s+-e\s+.*socket",
        r"\bphp\s+-r\s+.*(?:fsockopen|exec|system)",
        r"\bsocat\s+.*exec:",
        r"\bncat\s+.*-e\s+",
        r"\bmsf(?:venom|console)",
        # Dangerous system commands
        r"\brm\s+-rf\s+/",
        r"\bdd\s+if=.*of=/dev/",
        r"\bmkfs\.",
        r"\b(?:chmod|chown)\s+777\s+/",
        r"\biptables\s+-F",
        r"\bwget\s+.*\|\s*(?:ba|z|a)?sh",
        r"\bcurl\s+.*\|\s*(?:ba|z|a)?sh",
    ]
]

# ── Read-only / recon command prefix allowlist ──────────────────────────────
_RECON_COMMAND_PREFIXES: tuple[str, ...] = (
    # Network recon
    "nmap -sL", "nmap -sn", "nmap --top-ports", "nmap -p",
    "whois", "dig ", "nslookup ", "host ",
    # HTTP recon
    "curl ", "wget ", "curl.exe",
    # General read-only
    "cat ", "head ", "tail ", "less ", "more ",
    "ls ", "dir ", "find ", "grep ", "rg ", "locate ",
    "echo ", "printf ", "env ", "printenv ", "set ",
    "ps ", "top ", "htop ", "df ", "du ", "free ", "uname ",
    "ifconfig", "ip ", "netstat", "ss ", "route ",
    "ping ", "traceroute", "tracert",
    "python3 --version", "python --version", "pip list", "pip show",
    "git status", "git log", "git diff", "git branch",
    "docker ps", "docker images",
    # Read-only tool invocations
    "nikto -h", "whatweb ", "theHarvester",
)


@dataclass
class EnforcementResult:
    allowed: bool
    reason: str = ""
    required_mode: PermissionMode = PermissionMode.ALLOW


def _tokenize_command(command: str) -> list[str]:
    """Best-effort tokenize a shell command string into word tokens."""
    import shlex
    try:
        return shlex.split(command)
    except ValueError:
        return command.split()


def classify_bash_command(command: str) -> PermissionMode:
    """Classify a bash command by its risk level.

    Returns the *minimum* PermissionMode required to run this command.
    """
    cmd = command.strip()
    if not cmd:
        return PermissionMode.RECON_ONLY

    cmd_lower = cmd.lower()

    # 1. Check for reverse shell / dangerous patterns → POST_EXPLOIT
    for pattern in _REVERSE_SHELL_PATTERNS:
        if pattern.search(cmd):
            return PermissionMode.POST_EXPLOIT

    # 2. Check for exploitation frameworks → POST_EXPLOIT
    if any(marker in cmd_lower for marker in (
        "msfconsole", "msfvenom", "mimikatz", "psexec",
        "mettle", "meterpreter",
    )):
        return PermissionMode.POST_EXPLOIT

    # 3. Check for active exploitation commands → EXPLOIT
    if any(marker in cmd_lower for marker in (
        "sqlmap", "hydra", "hashcat", "john ",
        "exploit", "payload", "--os-shell", "--os-pwn",
    )):
        return PermissionMode.EXPLOIT

    # 4. Active scanning tools → VULN_SCAN
    if any(marker in cmd_lower for marker in (
        "nuclei", "nikto ", "zap-", "burp",
    )):
        return PermissionMode.VULN_SCAN

    # 5. Read-only commands → RECON_ONLY
    if cmd_lower.startswith(_RECON_COMMAND_PREFIXES):
        return PermissionMode.RECON_ONLY

    # 6. Default: safe-ish but uncertain → VULN_SCAN
    return PermissionMode.VULN_SCAN


class PermissionEnforcer:
    """Enforces tool execution permissions based on risk gradient."""

    def __init__(
        self,
        mode: PermissionMode = PermissionMode.ALLOW,
        workspace_root: str | None = None,
    ):
        self.mode = mode
        self.workspace_root = workspace_root or os.getcwd()

    @classmethod
    def from_env(cls) -> PermissionEnforcer:
        mode_val = int(os.getenv("PENTESTAGENT_PERMISSION_MODE", str(PermissionMode.ALLOW)))
        return cls(mode=PermissionMode(mode_val))

    def check(self, tool_name: str, arguments: dict[str, Any] | None = None) -> EnforcementResult:
        """Check if a tool execution is allowed under current permission mode.

        Returns EnforcementResult with allowed=False if permission is insufficient.
        """
        args = arguments or {}

        # Determine minimum required mode for this tool+args combination
        required = self._required_mode(tool_name, args)

        if self.mode >= required:
            return EnforcementResult(allowed=True, required_mode=required)

        return EnforcementResult(
            allowed=False,
            reason=(
                f"Tool '{tool_name}' requires at least {required.name} "
                f"(risk level {int(required)}), current mode is {self.mode.name} "
                f"(risk level {int(self.mode)})"
            ),
            required_mode=required,
        )

    def _required_mode(self, tool_name: str, arguments: dict[str, Any]) -> PermissionMode:
        """Determine the minimum required permission mode for a tool call."""
        name = tool_name.strip().lower()

        # For terminal/bash, classify based on the command content
        if name in ("terminal", "bash", "shell", "cmd", "powershell"):
            command = str(arguments.get("command", "") or arguments.get("cmd", ""))
            if command:
                return classify_bash_command(command)
            return PermissionMode.VULN_SCAN

        # Look up in tool risk map
        if name in _TOOL_RISK_MAP:
            return _TOOL_RISK_MAP[name]

        # Runtime tools that execute commands — check their arguments
        if name == "runtime" or name == "docker":
            command = str(arguments.get("command", "") or arguments.get("cmd", ""))
            if command:
                return classify_bash_command(command)
            return PermissionMode.VULN_SCAN

        # Unknown tools: default to VULN_SCAN (conservative but not blocking)
        return PermissionMode.VULN_SCAN

    def set_mode(self, mode: PermissionMode) -> None:
        self.mode = mode
