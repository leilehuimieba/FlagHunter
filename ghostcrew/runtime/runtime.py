"""Runtime abstraction for GhostCrew."""

import platform
from abc import ABC, abstractmethod
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING, Optional

if TYPE_CHECKING:
    from ..mcp import MCPManager


@dataclass
class EnvironmentInfo:
    """System environment information."""

    os: str  # "Windows", "Linux", "Darwin"
    os_version: str
    shell: str  # "powershell", "bash", "zsh", etc.
    architecture: str  # "x86_64", "arm64", etc.

    def __str__(self) -> str:
        """Concise string representation for prompts."""
        return f"{self.os} ({self.architecture}), shell: {self.shell}"


def detect_environment() -> EnvironmentInfo:
    """Detect the current system environment."""
    os_name = platform.system()
    os_version = platform.release()
    arch = platform.machine()

    # Detect shell
    if os_name == "Windows":
        # Check for PowerShell vs CMD
        shell = "powershell"
    else:
        # Unix-like: check common shells
        import os

        shell_path = os.environ.get("SHELL", "/bin/sh")
        shell = shell_path.split("/")[-1]  # Extract shell name

    return EnvironmentInfo(
        os=os_name, os_version=os_version, shell=shell, architecture=arch
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

    async def start(self):
        """Start the local runtime."""
        self._running = True
        # Create organized loot directory structure
        Path("loot").mkdir(exist_ok=True)
        Path("loot/reports").mkdir(exist_ok=True)
        Path("loot/artifacts").mkdir(exist_ok=True)
        Path("loot/artifacts/screenshots").mkdir(exist_ok=True)

    async def stop(self):
        """Stop the local runtime gracefully."""
        # Clean up any active subprocesses
        for proc in self._active_processes:
            try:
                if proc.returncode is None:
                    proc.terminate()
                    await proc.wait()
            except Exception:
                pass
        self._active_processes.clear()

        # Clean up browser
        await self._cleanup_browser()
        self._running = False

    async def _cleanup_browser(self):
        """Clean up browser resources properly."""
        # Close in reverse order of creation
        if self._page:
            try:
                await self._page.close()
            except Exception:
                pass
            self._page = None

        if self._browser_context:
            try:
                await self._browser_context.close()
            except Exception:
                pass
            self._browser_context = None

        if self._browser:
            try:
                await self._browser.close()
            except Exception:
                pass
            self._browser = None

        if self._playwright:
            try:
                await self._playwright.stop()
            except Exception:
                pass
            self._playwright = None

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
        self._browser = await self._playwright.chromium.launch(headless=True)
        self._browser_context = await self._browser.new_context(
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
        )
        self._page = await self._browser_context.new_page()

    async def execute_command(self, command: str, timeout: int = 300) -> CommandResult:
        """Execute a command locally."""
        import asyncio
        import subprocess

        try:
            process = await asyncio.create_subprocess_shell(
                command,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
                stdin=subprocess.DEVNULL,  # Prevent interactive prompts
            )

            stdout, stderr = await asyncio.wait_for(
                process.communicate(), timeout=timeout
            )

            return CommandResult(
                exit_code=process.returncode or 0,
                stdout=stdout.decode(errors="replace"),
                stderr=stderr.decode(errors="replace"),
            )

        except asyncio.TimeoutError:
            return CommandResult(
                exit_code=-1,
                stdout="",
                stderr=f"Command timed out after {timeout} seconds",
            )
        except asyncio.CancelledError:
            # Handle Ctrl+C gracefully
            return CommandResult(exit_code=-1, stdout="", stderr="Command cancelled")
        except Exception as e:
            return CommandResult(exit_code=-1, stdout="", stderr=str(e))

    async def browser_action(self, action: str, **kwargs) -> dict:
        """Perform browser automation actions using Playwright."""
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

                await self._page.goto(
                    url, timeout=timeout, wait_until="domcontentloaded"
                )

                if kwargs.get("wait_for"):
                    await self._page.wait_for_selector(
                        kwargs["wait_for"], timeout=timeout
                    )

                return {"url": self._page.url, "title": await self._page.title()}

            elif action == "screenshot":
                import time
                import uuid
                from pathlib import Path

                # Navigate first if URL provided
                if kwargs.get("url"):
                    await self._page.goto(
                        kwargs["url"], timeout=timeout, wait_until="domcontentloaded"
                    )

                # Save screenshot to loot/artifacts/screenshots/
                output_dir = Path("loot/artifacts/screenshots")
                output_dir.mkdir(parents=True, exist_ok=True)

                timestamp = int(time.time())
                unique_id = uuid.uuid4().hex[:8]
                filename = f"screenshot_{timestamp}_{unique_id}.png"
                filepath = output_dir / filename

                await self._page.screenshot(path=str(filepath), full_page=True)

                return {"path": str(filepath)}

            elif action == "get_content":
                if kwargs.get("url"):
                    await self._page.goto(
                        kwargs["url"], timeout=timeout, wait_until="domcontentloaded"
                    )

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
                    await self._page.goto(
                        kwargs["url"], timeout=timeout, wait_until="domcontentloaded"
                    )

                links = await self._page.evaluate(
                    """() => {
                    return Array.from(document.querySelectorAll('a[href]')).map(a => ({
                        href: a.href,
                        text: a.innerText.trim()
                    }));
                }"""
                )

                return {"links": links}

            elif action == "get_forms":
                if kwargs.get("url"):
                    await self._page.goto(
                        kwargs["url"], timeout=timeout, wait_until="domcontentloaded"
                    )

                forms = await self._page.evaluate(
                    """() => {
                    return Array.from(document.querySelectorAll('form')).map(form => ({
                        action: form.action,
                        method: form.method || 'GET',
                        inputs: Array.from(form.querySelectorAll('input, textarea, select')).map(input => ({
                            name: input.name,
                            type: input.type || 'text',
                            value: input.value
                        }))
                    }));
                }"""
                )

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

        try:
            async with httpx.AsyncClient(
                timeout=timeout, follow_redirects=True
            ) as client:
                if action == "request":
                    method = kwargs.get("method", "GET").upper()
                    url = kwargs.get("url")
                    headers = kwargs.get("headers", {})
                    data = kwargs.get("data")

                    if not url:
                        return {"error": "URL is required"}

                    response = await client.request(
                        method, url, headers=headers, data=data
                    )

                    return {
                        "status_code": response.status_code,
                        "headers": dict(response.headers),
                        "body": (
                            response.text[:10000]
                            if len(response.text) > 10000
                            else response.text
                        ),
                    }

                elif action == "get":
                    url = kwargs.get("url")
                    if not url:
                        return {"error": "URL is required"}

                    response = await client.get(url, headers=kwargs.get("headers", {}))
                    return {
                        "status_code": response.status_code,
                        "headers": dict(response.headers),
                        "body": response.text[:10000],
                    }

                elif action == "post":
                    url = kwargs.get("url")
                    if not url:
                        return {"error": "URL is required"}

                    response = await client.post(
                        url,
                        headers=kwargs.get("headers", {}),
                        data=kwargs.get("data"),
                        json=kwargs.get("json"),
                    )
                    return {
                        "status_code": response.status_code,
                        "headers": dict(response.headers),
                        "body": response.text[:10000],
                    }

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
