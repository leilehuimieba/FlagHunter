"""Runtime abstraction for FlagHunter."""

import asyncio
import base64
import logging
import platform
import shutil
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from pathlib import Path
from typing import TYPE_CHECKING, List, Optional
from urllib.parse import urlparse, urlunsplit

if TYPE_CHECKING:
    from ..mcp import MCPManager


# Categorized list of tools to check for
INTERESTING_TOOLS = {
    "network_scan": [
        "nmap",
        "masscan",
        "rustscan",
        "naabu",
        "unicornscan",
        "zmap",
        "arp-scan",
    ],
    "web_scan": [
        "nikto",
        "gobuster",
        "dirb",
        "dirbuster",
        "ffuf",
        "feroxbuster",
        "wpscan",
        "nuclei",
        "whatweb",
        "wfuzz",
        "arjun",
        "burpsuite",
        "zaproxy",
        "zap-cli",
    ],
    "enumeration": [
        "enum4linux",
        "enum4linux-ng",
        "smbclient",
        "smbmap",
        "rpcclient",
        "ldapsearch",
        "snmpwalk",
        "snmp-check",
        "onesixtyone",
        "nbtscan",
        "responder",
        "impacket-smbclient",
        "impacket-GetNPUsers",
        "impacket-GetUserSPNs",
        "impacket-psexec",
        "impacket-wmiexec",
        "impacket-dcomexec",
        "crackmapexec",
        "netexec",
        "evil-winrm",
        "kerbrute",
        "xfreerdp",
        "rdesktop",
    ],
    "exploitation": [
        "msfconsole",
        "msfvenom",
        "searchsploit",
        "sqlmap",
        "commix",
        "xsser",
        "ysoserial",
    ],
    "password_attacks": [
        "hydra",
        "medusa",
        "john",
        "hashcat",
        "crackmapexec",
        "netexec",
        "thc-hydra",
        "patator",
    ],
    "network_analysis": [
        "tcpdump",
        "tshark",
        "wireshark",
        "ngrep",
        "ettercap",
        "bettercap",
    ],
    "post_exploitation": [
        "mimikatz",
        "pypykatz",
        "impacket-secretsdump",
        "bloodhound",
        "sharphound",
        "powerview",
        "linpeas",
        "winpeas",
        "pspy",
    ],
    "tunneling": [
        "proxychains",
        "proxychains4",
        "socat",
        "chisel",
        "ligolo",
        "sshuttle",
        "ngrok",
    ],
    "osint": [
        "theHarvester",
        "recon-ng",
        "amass",
        "subfinder",
        "assetfinder",
        "sublist3r",
        "dnsenum",
        "dnsrecon",
        "fierce",
    ],
    "wireless": [
        "aircrack-ng",
        "airodump-ng",
        "aireplay-ng",
        "airmon-ng",
        "wifite",
        "kismet",
        "reaver",
        "bully",
        "hostapd",
        "wpa_supplicant",
    ],
    "reverse_engineering": [
        "ghidra",
        "radare2",
        "r2",
        "gdb",
        "pwndbg",
        "gef",
        "binwalk",
        "foremost",
        "exiftool",
        "objdump",
        "readelf",
        "strace",
        "ltrace",
    ],
    "cloud": [
        "aws",
        "az",
        "gcloud",
        "s3scanner",
        "cloud_enum",
        "ScoutSuite",
        "prowler",
        "pacu",
        "cloudfox",
    ],
    "forensics": [
        "steghide",
        "stegseek",
        "volatility",
        "volatility3",
        "autopsy",
        "sleuthkit",
        "binwalk",
        "foremost",
        "scalpel",
        "bulk_extractor",
    ],
    "fuzzing": [
        "boofuzz",
        "radamsa",
        "afl-fuzz",
        "zzuf",
        "honggfuzz",
    ],
    "mobile": [
        "adb",
        "apktool",
        "jadx",
        "frida",
        "objection",
        "mobsf",
        "drozer",
    ],
    "utilities": [
        "curl",
        "wget",
        "nc",
        "netcat",
        "ncat",
        "ssh",
        "telnet",
        "git",
        "docker",
        "kubectl",
        "kubeletctl",
        "kube-hunter",
        "trivy",
        "jq",
        "python3",
        "python",
        "perl",
        "ruby",
        "gcc",
        "g++",
        "make",
        "base64",
        "openssl",
        "xxd",
        "strings",
        "dig",
        "whois",
        "host",
        "traceroute",
        "mtr",
        "ping",
        "awk",
        "sed",
        "grep",
        "find",
    ],
}


@dataclass
class ToolInfo:
    """Information about an available tool."""

    name: str
    path: str
    category: str


@dataclass
class EnvironmentInfo:
    """System environment information."""

    os: str  # "Windows", "Linux", "Darwin"
    os_version: str
    shell: str  # "powershell", "bash", "zsh", etc.
    architecture: str  # "x86_64", "arm64", etc.
    available_tools: List[ToolInfo] = field(default_factory=list)

    def __str__(self) -> str:
        """Concise string representation for prompts."""
        # Group tools by category for cleaner output
        grouped = {}
        for tool in self.available_tools:
            if tool.category not in grouped:
                grouped[tool.category] = []
            grouped[tool.category].append(tool.name)

        tools_str = ""
        if grouped:
            lines = []
            for cat, tools in grouped.items():
                lines.append(f"  - {cat}: {', '.join(tools)}")
            tools_str = "\n" + "\n".join(lines)
        else:
            tools_str = " None"

        return (
            f"{self.os} ({self.architecture}), shell: {self.shell}\n"
            f"Available CLI Tools:{tools_str}"
        )


def detect_environment() -> EnvironmentInfo:
    """Detect the current system environment."""
    import os

    os_name = platform.system()
    os_version = platform.release()
    arch = platform.machine()
    shell = "unknown"

    # Detect shell and OS nuances
    if os_name == "Windows":
        # Better Windows shell detection
        comspec = os.environ.get("COMSPEC", "").lower()
        if "powershell" in comspec:
            shell = "powershell"
        elif "cmd.exe" in comspec:
            shell = "cmd"
        else:
            # Fallback: check if we are in a PS session via env vars
            if "PSModulePath" in os.environ:
                shell = "powershell"
            else:
                shell = "cmd"  # Default to cmd on Windows if unsure
    else:
        # Unix-like
        shell_path = os.environ.get("SHELL", "/bin/sh")
        shell = shell_path.split("/")[-1]

        # WSL Detection
        if os_name == "Linux":
            try:
                with open("/proc/version", "r") as f:
                    if "microsoft" in f.read().lower():
                        os_name = "Linux (WSL)"
            except Exception as e:
                logging.getLogger(__name__).debug("WSL detection probe failed: %s", e)

    # Detect available tools with categories
    available_tools = []
    for category, tools in INTERESTING_TOOLS.items():
        for tool_name in tools:
            tool_path = shutil.which(tool_name)
            if tool_path:
                available_tools.append(
                    ToolInfo(name=tool_name, path=tool_path, category=category)
                )

    return EnvironmentInfo(
        os=os_name,
        os_version=os_version,
        shell=shell,
        architecture=arch,
        available_tools=available_tools,
    )


@dataclass
class CommandResult:
    """Result of a command execution."""

    exit_code: int
    stdout: str
    stderr: str

    @property
    def success(self) -> bool:
        """Check if the command succeeded."""
        return self.exit_code == 0

    @property
    def output(self) -> str:
        """Get combined output."""
        parts = []
        if self.stdout:
            parts.append(self.stdout)
        if self.stderr:
            parts.append(self.stderr)
        return "\n".join(parts)


class Runtime(ABC):
    """Abstract base class for runtime environments."""

    _environment: Optional[EnvironmentInfo] = None

    def __init__(self, mcp_manager: Optional["MCPManager"] = None):
        """
        Initialize the runtime.

        Args:
            mcp_manager: Optional MCP manager for tool calls
        """
        self.mcp_manager = mcp_manager
        self.plan = None  # Set by agent for finish tool access

    @property
    def environment(self) -> EnvironmentInfo:
        """Get environment info (cached)."""
        if Runtime._environment is None:
            Runtime._environment = detect_environment()
        return Runtime._environment

    @abstractmethod
    async def start(self):
        """Start the runtime environment."""
        pass

    @abstractmethod
    async def stop(self):
        """Stop the runtime environment."""
        pass

    @abstractmethod
    async def execute_command(self, command: str, timeout: int = 300) -> CommandResult:
        """
        Execute a shell command.

        Args:
            command: The command to execute
            timeout: Timeout in seconds

        Returns:
            CommandResult with output
        """
        pass

    @abstractmethod
    async def browser_action(self, action: str, **kwargs) -> dict:
        """
        Perform a browser automation action.

        Args:
            action: The action to perform
            **kwargs: Action-specific arguments

        Returns:
            Action result
        """
        pass

    @abstractmethod
    async def proxy_action(self, action: str, **kwargs) -> dict:
        """
        Perform an HTTP proxy action.

        Args:
            action: The action to perform
            **kwargs: Action-specific arguments

        Returns:
            Action result
        """
        pass

    @abstractmethod
    async def is_running(self) -> bool:
        """Check if the runtime is running."""
        pass

    @abstractmethod
    async def get_status(self) -> dict:
        """
        Get runtime status information.

        Returns:
            Status dictionary
        """
        pass


def _build_loopback_url_candidates(url: str) -> list[str]:
    """Return equivalent local URL candidates in preferred attempt order."""
    try:
        parsed = urlparse(url.strip())
    except Exception:
        return [url]

    if not parsed.scheme or not parsed.hostname:
        return [url]

    hostname = parsed.hostname.lower()
    aliases: list[str]
    if hostname == "localhost":
        aliases = ["localhost", "127.0.0.1"]
    elif hostname in {"127.0.0.1", "127.1", "::1"}:
        aliases = ["127.0.0.1", "localhost"]
    else:
        return [url]

    candidates: list[str] = []
    for host in aliases:
        netloc = host
        if parsed.port is not None:
            netloc += f":{parsed.port}"
        rebuilt = urlunsplit(
            (
                parsed.scheme,
                netloc,
                parsed.path or "",
                parsed.query or "",
                parsed.fragment or "",
            )
        )
        if rebuilt not in candidates:
            candidates.append(rebuilt)
    return candidates or [url]


def _normalize_httpx_files(files: object) -> dict[str, object] | None:
    """Normalize loose multipart specs into a httpx-compatible mapping."""
    if not isinstance(files, dict) or not files:
        return None

    normalized: dict[str, object] = {}
    for field_name, spec in files.items():
        field = str(field_name or "").strip()
        if not field:
            continue

        if isinstance(spec, dict):
            file_path = str(spec.get("path") or "").strip()
            if file_path:
                path_obj = Path(file_path)
                if path_obj.exists() and path_obj.is_file():
                    content = path_obj.read_bytes()
                    filename = str(spec.get("filename") or path_obj.name)
                    content_type = str(spec.get("content_type") or "").strip()
                    normalized[field] = (
                        (filename, content, content_type)
                        if content_type
                        else (filename, content)
                    )
                    continue

            filename = str(spec.get("filename") or f"{field}.bin")
            content_type = str(spec.get("content_type") or "").strip()

            if "base64" in spec and spec.get("base64") is not None:
                try:
                    content = base64.b64decode(str(spec.get("base64") or ""))
                except Exception:
                    content = str(spec.get("base64") or "").encode("utf-8")
            elif "bytes" in spec and spec.get("bytes") is not None:
                raw = spec.get("bytes")
                if isinstance(raw, bytes):
                    content = raw
                else:
                    content = str(raw).encode("utf-8")
            else:
                content = str(spec.get("content") or "").encode("utf-8")

            normalized[field] = (
                (filename, content, content_type)
                if content_type
                else (filename, content)
            )
            continue

        if isinstance(spec, (str, Path)):
            candidate = Path(spec)
            if candidate.exists() and candidate.is_file():
                content = candidate.read_bytes()
                normalized[field] = (candidate.name, content)
            else:
                normalized[field] = (f"{field}.txt", str(spec).encode("utf-8"))
            continue

        if isinstance(spec, bytes):
            normalized[field] = (f"{field}.bin", spec)
            continue

        normalized[field] = (f"{field}.txt", str(spec).encode("utf-8"))

    return normalized or None


def _snapshot_httpx_cookies(cookies: object) -> dict[str, str]:
    """Best-effort cookie snapshot without assuming cookie names are unique.

    Some targets legitimately yield multiple cookies with the same name but
    different domain/path metadata. ``dict(httpx_cookies)`` can raise in that
    case. We only persist a minimal name->value mapping for follow-up requests,
    so keep the latest value seen for each cookie name instead of failing the
    entire request flow.
    """
    if cookies is None:
        return {}

    jar = getattr(cookies, "jar", None)
    if jar is not None:
        snapshot: dict[str, str] = {}
        for cookie in jar:
            name = str(getattr(cookie, "name", "") or "").strip()
            if not name:
                continue
            snapshot[name] = str(getattr(cookie, "value", "") or "")
        if snapshot:
            return snapshot

    try:
        items = cookies.items()
    except Exception:
        items = None
    if items is not None:
        try:
            return {
                str(key or "").strip(): str(value or "")
                for key, value in items
                if str(key or "").strip()
            }
        except Exception:
            pass

    try:
        return {
            str(key or "").strip(): str(value or "")
            for key, value in dict(cookies).items()
            if str(key or "").strip()
        }
    except Exception:
        return {}


class LocalRuntime(Runtime):
    """Local runtime that executes commands directly on the host."""

    def __init__(self, mcp_manager: Optional["MCPManager"] = None):
        super().__init__(mcp_manager)
        self._running = False
        self._browser = None
        self._browser_context = None
        self._page = None
        self._playwright = None
        self._active_processes: list = []
        self._browser_launch_source = "uninitialized"
        self._http_session_cookies: dict[str, str] = {}

    async def start(self):
        """Start the local runtime."""
        self._running = True
        # Create organized loot directory structure (workspace-aware)
        from ..workspaces.utils import get_loot_base

        base = get_loot_base()
        (base).mkdir(parents=True, exist_ok=True)
        (base / "reports").mkdir(parents=True, exist_ok=True)
        (base / "artifacts").mkdir(parents=True, exist_ok=True)
        (base / "artifacts" / "screenshots").mkdir(parents=True, exist_ok=True)

    async def stop(self):
        """Stop the local runtime gracefully."""
        # Clean up any active subprocesses
        for proc in self._active_processes:
            try:
                if proc.returncode is None:
                    proc.terminate()
                    await proc.wait()
                # Close pipes to prevent warnings
                if proc.stdin:
                    proc.stdin.close()
                if proc.stdout:
                    proc.stdout.close()
                if proc.stderr:
                    proc.stderr.close()
            except Exception as e:
                logging.getLogger(__name__).exception(
                    "Error cleaning up active process: %s", e
                )
                try:
                    from ..interface.notifier import notify

                    notify("warning", f"Runtime: error cleaning up process: {e}")
                except Exception as ne:
                    logging.getLogger(__name__).exception(
                        "Failed to notify operator about process cleanup error: %s", ne
                    )
        self._active_processes.clear()

        # Clean up browser
        await self._cleanup_browser()
        self._http_session_cookies.clear()
        self._running = False

    async def _cleanup_browser(self):
        """Clean up browser resources properly."""
        # Close in reverse order of creation
        if self._page:
            try:
                await self._page.close()
            except Exception as e:
                logging.getLogger(__name__).exception(
                    "Failed to close browser page: %s", e
                )
                try:
                    from ..interface.notifier import notify

                    notify("warning", f"Runtime: failed to close browser page: {e}")
                except Exception as ne:
                    logging.getLogger(__name__).exception(
                        "Failed to notify operator about browser page close error: %s",
                        ne,
                    )
            self._page = None

        if self._browser_context:
            try:
                await self._browser_context.close()
            except Exception as e:
                logging.getLogger(__name__).exception(
                    "Failed to close browser context: %s", e
                )
                try:
                    from ..interface.notifier import notify

                    notify("warning", f"Runtime: failed to close browser context: {e}")
                except Exception as ne:
                    logging.getLogger(__name__).exception(
                        "Failed to notify operator about browser context close error: %s",
                        ne,
                    )
            self._browser_context = None

        if self._browser:
            try:
                await self._browser.close()
            except Exception as e:
                logging.getLogger(__name__).exception("Failed to close browser: %s", e)
                try:
                    from ..interface.notifier import notify

                    notify("warning", f"Runtime: failed to close browser: {e}")
                except Exception as ne:
                    logging.getLogger(__name__).exception(
                        "Failed to notify operator about browser close error: %s", ne
                    )
            self._browser = None

        if self._playwright:
            try:
                await self._playwright.stop()
            except Exception as e:
                logging.getLogger(__name__).exception(
                    "Failed to stop playwright: %s", e
                )
                try:
                    from ..interface.notifier import notify

                    notify("warning", f"Runtime: failed to stop playwright: {e}")
                except Exception as ne:
                    logging.getLogger(__name__).exception(
                        "Failed to notify operator about playwright stop error: %s", ne
                    )
            self._playwright = None
        self._browser_launch_source = "uninitialized"

    async def _cleanup_subprocess(self, process, communicate_task=None) -> None:
        """Best-effort cleanup for asyncio subprocesses on all exit paths.

        This is especially important on Windows ProactorEventLoop where timed-out
        subprocess stdout/stderr pipe transports can otherwise survive until GC
        and trigger PytestUnraisableExceptionWarning during test teardown.
        """
        if process is None:
            return

        try:
            if process.returncode is None:
                try:
                    process.terminate()
                except ProcessLookupError:
                    pass
                except Exception:
                    try:
                        process.kill()
                    except Exception:
                        pass

                try:
                    if communicate_task is not None:
                        await asyncio.wait_for(asyncio.shield(communicate_task), timeout=1)
                    else:
                        await asyncio.wait_for(process.communicate(), timeout=1)
                except asyncio.TimeoutError:
                    try:
                        process.kill()
                    except ProcessLookupError:
                        pass
                    except Exception:
                        pass
                    try:
                        if communicate_task is not None:
                            await asyncio.wait_for(asyncio.shield(communicate_task), timeout=1)
                        else:
                            await asyncio.wait_for(process.communicate(), timeout=1)
                    except Exception:
                        pass
                except Exception:
                    try:
                        await asyncio.wait_for(process.wait(), timeout=1)
                    except Exception:
                        pass
            else:
                try:
                    await asyncio.wait_for(process.wait(), timeout=1)
                except Exception:
                    pass

            if communicate_task is not None and not communicate_task.done():
                communicate_task.cancel()
                try:
                    await communicate_task
                except asyncio.CancelledError:
                    pass
                except Exception:
                    pass

            for stream in (getattr(process, "stdin", None), getattr(process, "stdout", None), getattr(process, "stderr", None)):
                transport = getattr(stream, "_transport", None)
                if transport is None:
                    continue
                try:
                    is_closing = transport.is_closing()
                except Exception:
                    is_closing = False
                if not is_closing:
                    try:
                        transport.close()
                    except Exception:
                        pass

            proc_transport = getattr(process, "_transport", None)
            if proc_transport is not None:
                try:
                    proc_transport.close()
                except Exception:
                    pass

            # Let connection_lost / transport finalizers flush while the loop
            # is still alive, which prevents Windows Proactor pipe warnings at
            # interpreter / pytest teardown time.
            try:
                await asyncio.sleep(0.05)
            except Exception:
                pass
        finally:
            if process in self._active_processes:
                self._active_processes.remove(process)

    @staticmethod
    def _candidate_browser_executables() -> list[str]:
        candidates: list[str] = []
        system = platform.system().lower()
        names: list[str]
        known_paths: list[str]
        if system == "windows":
            names = ["chrome", "msedge", "chromium", "chromium-browser"]
            known_paths = [
                r"C:\Program Files\Google\Chrome\Application\chrome.exe",
                r"C:\Program Files (x86)\Google\Chrome\Application\chrome.exe",
                r"C:\Program Files\Microsoft\Edge\Application\msedge.exe",
                r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe",
            ]
        elif system == "darwin":
            names = ["Google Chrome", "Microsoft Edge", "Chromium"]
            known_paths = [
                "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome",
                "/Applications/Microsoft Edge.app/Contents/MacOS/Microsoft Edge",
                "/Applications/Chromium.app/Contents/MacOS/Chromium",
            ]
        else:
            names = ["google-chrome", "microsoft-edge", "chromium", "chromium-browser"]
            known_paths = []

        for name in names:
            resolved = shutil.which(name)
            if resolved and resolved not in candidates:
                candidates.append(resolved)
        for raw in known_paths:
            if Path(raw).exists() and raw not in candidates:
                candidates.append(raw)
        return candidates

    async def _launch_browser_with_fallbacks(self):
        last_error: Exception | None = None
        try:
            browser = await self._playwright.chromium.launch(headless=True)
            self._browser_launch_source = "playwright:bundled-chromium"
            return browser
        except Exception as exc:
            last_error = exc

        for executable in self._candidate_browser_executables():
            try:
                browser = await self._playwright.chromium.launch(
                    headless=True,
                    executable_path=executable,
                )
                self._browser_launch_source = f"system:{executable}"
                return browser
            except Exception as exc:
                last_error = exc
                continue

        if last_error is not None:
            raise last_error
        raise RuntimeError("Unable to launch browser")

    async def _ensure_browser(self):
        """Ensure browser is initialized."""
        if self._page is not None:
            return

        try:
            from playwright.async_api import async_playwright
        except ImportError as e:
            raise RuntimeError(
                "Playwright not installed. Install with:\n"
                "  pip install playwright\n"
                "  playwright install chromium"
            ) from e

        self._playwright = await async_playwright().start()
        self._browser = await self._launch_browser_with_fallbacks()
        self._browser_context = await self._browser.new_context(
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
            ignore_https_errors=True,
        )
        self._page = await self._browser_context.new_page()

    def _normalize_browser_bootstrap_error(self, exc: Exception) -> str:
        message = str(exc)
        install_hint = "playwright install chromium"
        lowered = message.lower()
        if "executable doesn't exist" in lowered and install_hint not in lowered:
            return (
                f"{message}\nInstall browser binaries with:\n"
                "  playwright install chromium"
            )
        return message

    async def _diagnose_browser(self) -> dict:
        if self._page is not None:
            return {
                "available": True,
                "engine": "playwright",
                "mode": "rendered_browser",
                "rendered_dom": True,
                "js_execution": True,
                "cookies": True,
                "supports_actions": [
                    "navigate",
                    "get_content",
                    "get_links",
                    "get_forms",
                    "click",
                    "type",
                    "execute_js",
                    "get_cookies",
                    "submit_form",
                    "screenshot",
                ],
                "path": "runtime.browser_action",
                "launch_source": self._browser_launch_source,
            }

        try:
            await self._ensure_browser()
        except RuntimeError as exc:
            return {
                "available": False,
                "engine": "playwright",
                "mode": "rendered_browser",
                "rendered_dom": False,
                "js_execution": False,
                "cookies": False,
                "error": str(exc),
                "path": "runtime.browser_action",
                "launch_source": self._browser_launch_source,
            }
        except Exception as exc:
            return {
                "available": False,
                "engine": "playwright",
                "mode": "rendered_browser",
                "rendered_dom": False,
                "js_execution": False,
                "cookies": False,
                "error": self._normalize_browser_bootstrap_error(exc),
                "path": "runtime.browser_action",
                "launch_source": self._browser_launch_source,
            }

        return {
            "available": True,
            "engine": "playwright",
            "mode": "rendered_browser",
            "rendered_dom": True,
            "js_execution": True,
            "cookies": True,
            "supports_actions": [
                "navigate",
                "get_content",
                "get_links",
                "get_forms",
                "click",
                "type",
                "execute_js",
                "get_cookies",
                "submit_form",
                "screenshot",
            ],
            "path": "runtime.browser_action",
            "launch_source": self._browser_launch_source,
        }

    async def _goto_with_loopback_fallback(self, url: str, timeout: int):
        """Navigate with one automatic retry across localhost loopback aliases."""
        last_error: Exception | None = None
        for candidate in _build_loopback_url_candidates(url):
            try:
                await self._page.goto(
                    candidate, timeout=timeout, wait_until="domcontentloaded"
                )
                return candidate
            except Exception as exc:
                last_error = exc
                continue
        if last_error is not None:
            raise last_error
        raise RuntimeError(f"Failed to navigate to {url}")

    async def execute_command(self, command: str, timeout: int = 300) -> CommandResult:
        """Execute a command locally."""
        import asyncio
        import os
        import re
        import subprocess

        # Regex to strip ANSI escape codes
        ansi_escape = re.compile(r"\x1B(?:[@-Z\\-_]|\[[0-?]*[ -/]*[@-~])")

        # Set environment variables to discourage ANSI output
        env = os.environ.copy()
        env["TERM"] = "dumb"
        env["NO_COLOR"] = "1"
        process = None
        communicate_task = None

        try:
            process = await asyncio.create_subprocess_shell(
                command,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
                stdin=subprocess.DEVNULL,  # Prevent interactive prompts
                env=env,
            )

            # Track process for cleanup
            self._active_processes.append(process)

            communicate_task = asyncio.create_task(process.communicate())
            stdout, stderr = await asyncio.wait_for(
                asyncio.shield(communicate_task), timeout=timeout
            )

            # Remove from tracking after completion
            if process in self._active_processes:
                self._active_processes.remove(process)

            # Decode and strip ANSI codes
            stdout_str = stdout.decode(errors="replace")
            stderr_str = stderr.decode(errors="replace")

            stdout_clean = ansi_escape.sub("", stdout_str)
            stderr_clean = ansi_escape.sub("", stderr_str)

            return CommandResult(
                exit_code=process.returncode or 0,
                stdout=stdout_clean,
                stderr=stderr_clean,
            )

        except asyncio.TimeoutError:
            await self._cleanup_subprocess(process, communicate_task)
            return CommandResult(
                exit_code=-1,
                stdout="",
                stderr=f"Command timed out after {timeout} seconds",
            )
        except asyncio.CancelledError:
            await self._cleanup_subprocess(process, communicate_task)
            # Handle Ctrl+C gracefully
            return CommandResult(exit_code=-1, stdout="", stderr="Command cancelled")
        except Exception as e:
            await self._cleanup_subprocess(process, communicate_task)
            return CommandResult(exit_code=-1, stdout="", stderr=str(e))

    async def browser_action(self, action: str, **kwargs) -> dict:
        """Perform browser automation actions using Playwright."""
        import asyncio

        # Enforce a hard timeout on the entire operation to prevent hanging
        # Add 5 seconds buffer to the requested timeout for browser startup overhead
        op_timeout = kwargs.get("timeout", 30) + 10

        try:
            return await asyncio.wait_for(
                self._execute_browser_action(action, **kwargs), timeout=op_timeout
            )
        except asyncio.TimeoutError:
            return {"error": f"Browser action '{action}' timed out after {op_timeout}s"}
        except Exception as e:
            return {"error": str(e)}

    async def _execute_browser_action(self, action: str, **kwargs) -> dict:
        """Internal execution of browser action."""
        if action == "diagnose":
            return await self._diagnose_browser()

        try:
            await self._ensure_browser()
        except RuntimeError as e:
            return {"error": str(e)}

        timeout = kwargs.get("timeout", 30) * 1000  # Convert to ms

        try:
            if action == "navigate":
                url = kwargs.get("url")
                if not url:
                    return {"error": "URL is required for navigate action"}

                used_url = await self._goto_with_loopback_fallback(url, timeout)

                if kwargs.get("wait_for"):
                    await self._page.wait_for_selector(
                        kwargs["wait_for"], timeout=timeout
                    )

                return {
                    "url": self._page.url or used_url,
                    "requested_url": url,
                    "title": await self._page.title(),
                }

            elif action == "screenshot":
                import time
                import uuid

                # Navigate first if URL provided
                if kwargs.get("url"):
                    await self._goto_with_loopback_fallback(kwargs["url"], timeout)

                # Save screenshot to workspace-aware loot/artifacts/screenshots/
                from ..workspaces.utils import get_loot_file

                output_dir = get_loot_file("artifacts/screenshots").parent

                timestamp = int(time.time())
                unique_id = uuid.uuid4().hex[:8]
                filename = f"screenshot_{timestamp}_{unique_id}.png"
                filepath = output_dir / filename

                await self._page.screenshot(path=str(filepath), full_page=True)

                return {"path": str(filepath)}

            elif action == "get_content":
                if kwargs.get("url"):
                    await self._goto_with_loopback_fallback(kwargs["url"], timeout)

                content = await self._page.content()

                # Also get text content for easier reading
                text_content = await self._page.evaluate(
                    "() => document.body.innerText"
                )

                return {
                    "content": text_content,
                    "html": content[:10000] if len(content) > 10000 else content,
                }

            elif action == "get_links":
                if kwargs.get("url"):
                    await self._goto_with_loopback_fallback(kwargs["url"], timeout)

                links = await self._page.evaluate("""() => {
                    return Array.from(document.querySelectorAll('a[href]')).map(a => ({
                        href: a.href,
                        text: a.innerText.trim()
                    }));
                }""")

                return {"links": links}

            elif action == "get_forms":
                if kwargs.get("url"):
                    await self._goto_with_loopback_fallback(kwargs["url"], timeout)

                forms = await self._page.evaluate("""() => {
                    return Array.from(document.querySelectorAll('form')).map(form => ({
                        action: form.action,
                        method: form.method || 'GET',
                        inputs: Array.from(form.querySelectorAll('input, textarea, select')).map(input => ({
                            name: input.name,
                            type: input.type || 'text',
                            value: input.value
                        }))
                    }));
                }""")

                return {"forms": forms}

            elif action == "click":
                selector = kwargs.get("selector")
                if not selector:
                    return {"error": "Selector is required for click action"}

                await self._page.click(selector, timeout=timeout)
                return {"selector": selector, "clicked": True}

            elif action == "type":
                selector = kwargs.get("selector")
                text = kwargs.get("text", "")
                if not selector:
                    return {"error": "Selector is required for type action"}

                await self._page.fill(selector, text, timeout=timeout)
                return {"selector": selector, "typed": True}

            elif action == "execute_js":
                javascript = kwargs.get("javascript")
                if not javascript:
                    return {"error": "JavaScript code is required"}

                result = await self._page.evaluate(javascript)
                return {"result": str(result) if result else ""}

            elif action == "get_cookies":
                cookies = await self._page.context.cookies()
                cookie_names = [
                    cookie["name"]
                    for cookie in cookies
                    if cookie.get("name")
                ]
                cookie_str = "; ".join(
                    f"{cookie['name']}={cookie['value']}"
                    for cookie in cookies
                    if cookie.get("name")
                )
                return {
                    "cookies": cookies,
                    "cookie_string": cookie_str,
                    "cookie_count": len(cookies),
                    "cookie_names": cookie_names,
                }

            elif action == "submit_form":
                fields = kwargs.get("fields", {})
                submit = kwargs.get("submit", "")
                field_selectors = list(fields.keys()) if isinstance(fields, dict) else []
                for selector, value in fields.items():
                    await self._page.fill(selector, str(value), timeout=timeout)
                if submit:
                    await self._page.click(submit, timeout=timeout)
                    await self._page.wait_for_load_state(
                        "domcontentloaded", timeout=timeout
                    )
                elif fields:
                    first_sel = next(iter(fields.keys()))
                    await self._page.press(first_sel, "Enter")
                    await self._page.wait_for_load_state(
                        "domcontentloaded", timeout=timeout
                    )
                return {
                    "submitted": True,
                    "url": self._page.url,
                    "submit_selector": submit,
                    "field_selectors": field_selectors,
                }

            else:
                return {"error": f"Unknown browser action: {action}"}

        except Exception as e:
            return {"error": f"Browser action failed: {str(e)}"}

    async def proxy_action(self, action: str, **kwargs) -> dict:
        """HTTP proxy actions using httpx."""
        try:
            import httpx
        except ImportError:
            return {"error": "httpx not installed. Install with: pip install httpx"}

        timeout = kwargs.get("timeout", 30)

        async def _send_request(
            client: "httpx.AsyncClient",
            method: str,
            url: str,
            headers: dict | None = None,
            data=None,
            files=None,
            json_body=None,
            *,
            binary: bool = False,
        ) -> dict:
            if not url:
                return {"error": "URL is required"}

            last_error: Exception | None = None
            for candidate in _build_loopback_url_candidates(url):
                try:
                    normalized_headers = dict(headers or {})
                    if not any(str(key).lower() == "cookie" for key in normalized_headers):
                        client.cookies.clear()
                        client.cookies.update(dict(self._http_session_cookies))
                    response = await client.request(
                        method,
                        candidate,
                        headers=normalized_headers,
                        data=data,
                        files=files,
                        json=json_body,
                    )
                    self._http_session_cookies.update(_snapshot_httpx_cookies(client.cookies))
                    result = {
                        "status_code": response.status_code,
                        "headers": dict(response.headers),
                        "final_url": str(response.url),
                        "redirect_history": [
                            {
                                "status_code": item.status_code,
                                "url": str(item.url),
                                "location": str(item.headers.get("location") or ""),
                            }
                            for item in list(response.history)
                        ],
                    }
                    if binary:
                        result["body_base64"] = base64.b64encode(response.content).decode("ascii")
                        result["content_type"] = str(response.headers.get("content-type") or "")
                    else:
                        result["body"] = (
                            response.text[:10000]
                            if len(response.text) > 10000
                            else response.text
                        )
                    return result
                except httpx.ConnectError as exc:
                    last_error = exc
                    continue

            if last_error is not None:
                raise last_error
            return {"error": "URL is required"}

        try:
            async with httpx.AsyncClient(
                timeout=timeout,
                follow_redirects=True,
                trust_env=False,
            ) as client:
                if action == "request":
                    method = kwargs.get("method", "GET").upper()
                    url = kwargs.get("url")
                    return await _send_request(
                        client,
                        method=method,
                        url=url,
                        headers=kwargs.get("headers", {}),
                        data=kwargs.get("data"),
                        files=_normalize_httpx_files(kwargs.get("files")),
                        json_body=kwargs.get("json"),
                        binary=bool(kwargs.get("binary")),
                    )

                elif action == "get":
                    url = kwargs.get("url")
                    return await _send_request(
                        client,
                        method="GET",
                        url=url,
                        headers=kwargs.get("headers", {}),
                        binary=bool(kwargs.get("binary")),
                    )

                elif action == "post":
                    url = kwargs.get("url")
                    return await _send_request(
                        client,
                        method="POST",
                        url=url,
                        headers=kwargs.get("headers", {}),
                        data=kwargs.get("data"),
                        files=_normalize_httpx_files(kwargs.get("files")),
                        json_body=kwargs.get("json"),
                        binary=bool(kwargs.get("binary")),
                    )

                else:
                    return {"error": f"Unknown proxy action: {action}"}

        except Exception as e:
            return {"error": f"Proxy action failed: {str(e)}"}

    async def is_running(self) -> bool:
        return self._running

    async def get_status(self) -> dict:
        return {
            "type": "local",
            "running": self._running,
            "browser_active": self._page is not None,
        }
