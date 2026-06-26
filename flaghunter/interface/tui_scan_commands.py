"""Scan-tool slash-command parsers mixed into FlagHunterTUI (debt ledger 第五波·TUI 刀8, god-class).

Extracted from tui.py. The /nmap, /dirscan, /nuclei, /sqlmap command parsers —
each shlex-parses the command, runs the corresponding tool via ``self._runtime``
(lazy-imported inside the body), and renders via ``self._format_*_result`` /
``self._add_system``. All cross refs resolve at runtime through the FlagHunterTUI
instance MRO (stay-behind ``_handle_command`` dispatcher + the ToolResultFormatMixin
formatters from 刀7), so this is a clean cohesive feature mixin. Tool imports are
lazy inside each method, so they travel with the code.
"""

from __future__ import annotations


class ScanCommandMixin:
    """/nmap /dirscan /nuclei /sqlmap command parsers for FlagHunterTUI."""

    # === TOOL CMD BEGIN: /nmap ===
    async def _parse_nmap_command(self, cmd: str) -> None:
        """Parse and execute /nmap command."""
        import shlex

        try:
            parts = shlex.split(cmd)
        except ValueError as exc:
            self._add_system(f"[nmap] Parse error: {exc}")
            return

        if len(parts) < 2:
            self._add_system(
                "Usage: /nmap <target> [ports]\n"
                "Example: /nmap 127.0.0.1\n"
                "         /nmap 127.0.0.1 22,80,443"
            )
            return

        target = parts[1].strip()
        ports = parts[2].strip() if len(parts) > 2 else "1-1000"

        if not target:
            self._add_system("Usage: /nmap <target> [ports]")
            return

        try:
            from ..tools.nmap import run_nmap
        except Exception as exc:
            self._add_system(f"[nmap] Tool unavailable: {exc}")
            return

        try:
            result = await run_nmap(target, ports, runtime=self._runtime)
        except Exception as exc:
            self._add_system(f"[nmap] Scan failed: {exc}")
            return

        if not isinstance(result, dict):
            self._add_system("[nmap] Unexpected tool result format.")
            return

        self._add_system(self._format_nmap_result(result, target, ports))

    # === TOOL CMD END: /nmap ===

    # === TOOL CMD BEGIN: /dirscan ===
    async def _parse_dirscan_command(self, cmd: str) -> None:
        """Parse and execute /dirscan command."""
        import shlex

        try:
            parts = shlex.split(cmd)
        except ValueError as exc:
            self._add_system(f"[dirscan] Parse error: {exc}")
            return

        if len(parts) < 2:
            self._add_system(
                "Usage: /dirscan <url> [wordlist]\n"
                "Example: /dirscan http://127.0.0.1\n"
                "         /dirscan http://127.0.0.1 /usr/share/wordlists/dirb/common.txt"
            )
            return

        url = parts[1].strip()
        wordlist = (
            parts[2].strip()
            if len(parts) > 2
            else "/usr/share/wordlists/dirb/common.txt"
        )

        if not url:
            self._add_system("Usage: /dirscan <url> [wordlist]")
            return

        try:
            from ..tools.dirscan import run_dirscan
        except Exception as exc:
            self._add_system(f"[dirscan] Tool unavailable: {exc}")
            return

        try:
            result = await run_dirscan(url, wordlist, runtime=self._runtime)
        except Exception as exc:
            self._add_system(f"[dirscan] Scan failed: {exc}")
            return

        if not isinstance(result, dict):
            self._add_system("[dirscan] Unexpected tool result format.")
            return

        self._add_system(self._format_dirscan_result(result, url, wordlist))

    # === TOOL CMD END: /dirscan ===

    # === TOOL CMD BEGIN: /nuclei ===
    async def _parse_nuclei_command(self, cmd: str) -> None:
        """Parse and execute /nuclei command."""
        import shlex

        try:
            parts = shlex.split(cmd)
        except ValueError as exc:
            self._add_system(f"[nuclei] Parse error: {exc}")
            return

        if len(parts) < 2:
            self._add_system(
                "Usage: /nuclei <target> [severity]\n"
                "Example: /nuclei http://127.0.0.1\n"
                "         /nuclei http://127.0.0.1 critical,high,medium"
            )
            return

        target = parts[1].strip()
        severity_arg = parts[2].strip() if len(parts) > 2 else "critical,high,medium"
        severity = [item.strip() for item in severity_arg.split(",") if item.strip()]
        if not severity:
            severity = ["critical", "high", "medium"]

        if not target:
            self._add_system("Usage: /nuclei <target> [severity]")
            return

        try:
            from ..tools.nuclei import run_nuclei
        except Exception as exc:
            self._add_system(f"[nuclei] Tool unavailable: {exc}")
            return

        try:
            result = await run_nuclei(target, severity=severity, runtime=self._runtime)
        except Exception as exc:
            self._add_system(f"[nuclei] Scan failed: {exc}")
            return

        if not isinstance(result, dict):
            self._add_system("[nuclei] Unexpected tool result format.")
            return

        self._add_system(self._format_nuclei_result(result, target, severity))

    # === TOOL CMD END: /nuclei ===

    # === TOOL CMD BEGIN: /sqlmap ===
    async def _parse_sqlmap_command(self, cmd: str) -> None:
        """Parse and execute /sqlmap command."""
        import shlex

        try:
            parts = shlex.split(cmd)
        except ValueError as exc:
            self._add_system(f"[sqlmap] Parse error: {exc}")
            return

        if len(parts) < 2:
            self._add_system(
                "Usage: /sqlmap <url> [--data <post_data>]\n"
                "Example: /sqlmap http://127.0.0.1/item.php?id=1\n"
                "         /sqlmap http://127.0.0.1/login --data \"user=admin&pass=test\""
            )
            return

        url = parts[1].strip()
        data = ""
        idx = 2
        while idx < len(parts):
            token = parts[idx]
            if token == "--data":
                if idx + 1 >= len(parts):
                    self._add_system("Usage: /sqlmap <url> [--data <post_data>]")
                    return
                data = parts[idx + 1]
                idx += 2
                continue

            self._add_system(f"[sqlmap] Unknown option: {token}")
            return

        if not url:
            self._add_system("Usage: /sqlmap <url> [--data <post_data>]")
            return

        try:
            from ..tools.sqlmap import run_sqlmap
        except Exception as exc:
            self._add_system(f"[sqlmap] Tool unavailable: {exc}")
            return

        try:
            result = await run_sqlmap(url, data=data, runtime=self._runtime)
        except Exception as exc:
            self._add_system(f"[sqlmap] Scan failed: {exc}")
            return

        if not isinstance(result, dict):
            self._add_system("[sqlmap] Unexpected tool result format.")
            return

        self._add_system(self._format_sqlmap_result(result, url))

    # === TOOL CMD END: /sqlmap ===
