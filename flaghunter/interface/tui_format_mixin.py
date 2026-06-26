"""Scan-tool result formatters mixed into FlagHunterTUI (debt ledger 第五波·TUI 刀7, mixin 试点).

Extracted from tui.py. The first **mixin** cut of the FlagHunterTUI god-class:
four pure scan-tool result formatters (nmap / dirscan / nuclei / sqlmap) that
take a structured result dict and return a display string. They use **zero**
``self`` state (verified by AST) — pure functions parked as methods — so they
are the safest possible pilot to validate the mixin mechanism (MRO method
resolution + that stay-behind ``self._format_*_result(...)`` callers in the
``_parse_*_command`` methods keep resolving). FlagHunterTUI inherits this mixin
via ``class FlagHunterTUI(ToolResultFormatMixin, App)``.
"""

from __future__ import annotations

from typing import Any


class ToolResultFormatMixin:
    """Scan-tool result → display-string formatters for FlagHunterTUI."""

    def _format_nmap_result(self, result: dict[str, Any], target: str, ports: str) -> str:
        """Format structured nmap output for TUI display."""
        lines = [f"[nmap] Target: {result.get('target') or target}"]

        status = result.get("status")
        if status:
            lines.append(f"Status: {status}")

        port_items = result.get("ports")
        if isinstance(port_items, list) and port_items:
            lines.append("Ports:")
            for item in port_items:
                if not isinstance(item, dict):
                    continue
                port_value = item.get("port", "?")
                state = item.get("state", "unknown")
                service = item.get("service") or "unknown"
                protocol = item.get("protocol") or ""
                version = item.get("version") or ""
                line = f"- {port_value}"
                if protocol:
                    line += f"/{protocol}"
                line += f" {state} {service}"
                if version:
                    line += f" ({version})"
                lines.append(line)
        else:
            lines.append(f"Ports: no results for range {ports}")

        os_guess = result.get("os_guess")
        if os_guess:
            lines.append(f"OS Guess: {os_guess}")

        error = result.get("error")
        if error:
            lines.append(f"Error: {error}")
        elif result.get("raw") and not (isinstance(port_items, list) and port_items):
            lines.append("Note: scan completed but no structured port rows were parsed.")

        return "\n".join(lines)

    def _format_dirscan_result(
        self, result: dict[str, Any], url: str, wordlist: str
    ) -> str:
        """Format structured dirscan output for TUI display."""
        lines = [f"[dirscan] URL: {result.get('url') or url}"]
        tool_used = result.get("tool_used")
        if tool_used:
            lines.append(f"Tool: {tool_used}")
        lines.append(f"Wordlist: {wordlist}")

        found_items = result.get("found")
        if isinstance(found_items, list) and found_items:
            lines.append("Found paths:")
            for item in found_items:
                if not isinstance(item, dict):
                    continue
                status = item.get("status", "?")
                path = item.get("path") or "/"
                size = item.get("size")
                line = f"- {status} {path}"
                if size not in (None, "", 0):
                    line += f" [size={size}]"
                lines.append(line)
        else:
            lines.append("Found paths: none")

        error = result.get("error")
        if error:
            lines.append(f"Error: {error}")

        return "\n".join(lines)

    def _format_nuclei_result(
        self, result: dict[str, Any], target: str, severity: list[str]
    ) -> str:
        """Format structured nuclei output for TUI display."""
        lines = [f"[nuclei] Target: {result.get('target') or target}"]
        lines.append(f"Severity filter: {','.join(severity)}")

        findings = result.get("findings")
        if isinstance(findings, list) and findings:
            lines.append(f"Findings ({len(findings)}):")
            for item in findings:
                if not isinstance(item, dict):
                    continue
                template_id = item.get("template_id") or "unknown-template"
                sev = item.get("severity") or "unknown"
                name = item.get("name") or ""
                line = f"- {template_id} {sev}"
                if name:
                    line += f" - {name}"
                lines.append(line)
        else:
            lines.append("Findings: none")

        error = result.get("error")
        if error:
            lines.append(f"Error: {error}")

        return "\n".join(lines)

    def _format_sqlmap_result(self, result: dict[str, Any], url: str) -> str:
        """Format structured sqlmap output for TUI display."""
        vulnerable = bool(result.get("vulnerable"))
        lines = [f"[sqlmap] URL: {url}", f"Vulnerable: {'yes' if vulnerable else 'no'}"]

        injection_points = result.get("injection_points")
        if isinstance(injection_points, list) and injection_points:
            lines.append("Injection points:")
            for item in injection_points:
                if not isinstance(item, dict):
                    continue
                parameter = item.get("parameter") or "unknown"
                injection_type = item.get("type") or "unknown"
                dbms = item.get("dbms") or ""
                payload = item.get("payload") or ""
                line = f"- {parameter}: {injection_type}"
                if dbms:
                    line += f" [{dbms}]"
                if payload:
                    line += f" | payload={payload}"
                lines.append(line)
        else:
            lines.append("Injection points: none")

        databases = result.get("databases")
        if isinstance(databases, list) and databases:
            lines.append("Databases: " + ", ".join(str(db) for db in databases))

        error = result.get("error")
        if error:
            lines.append(f"Error: {error}")

        return "\n".join(lines)
