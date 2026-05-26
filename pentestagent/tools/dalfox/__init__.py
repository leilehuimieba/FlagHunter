"""Dalfox — modern XSS vulnerability scanner and payload validator."""

import json
import os
import tempfile

from ...runtime.runtime import Runtime
from ...tools._tool_env import find_tool
from ...tools.registry import ToolSchema, register_tool


@register_tool(
    name="dalfox",
    description="Scan a target URL for XSS vulnerabilities using Dalfox. Supports reflected, stored, and DOM-based XSS detection with automatic payload generation and WAF bypass attempts.",
    schema=ToolSchema(
        type="object",
        properties={
            "url": {"type": "string", "description": "Target URL to scan"},
            "method": {"type": "string", "description": "HTTP method: GET or POST (default: GET)", "default": "GET"},
            "data": {"type": "string", "description": "POST data or query string for parameter injection"},
            "cookie": {"type": "string", "description": "Cookie string to include in requests"},
            "headers": {"type": "string", "description": "Custom headers (format: Key:Value,Key2:Value2)"},
            "blind": {"type": "string", "description": "Blind XSS callback URL (e.g., http://your-server/xss)"},
            "only_custom_payload": {"type": "boolean", "description": "Use only custom payloads (default: false)", "default": False},
            "waf_evasion": {"type": "boolean", "description": "Enable WAF evasion techniques (default: true)", "default": True},
            "timeout": {"type": "integer", "description": "Timeout in seconds (default: 60)", "default": 60},
        },
        required=["url"],
    ),
    category="scanner",
)
async def dalfox(arguments: dict, runtime: Runtime) -> str:
    url = arguments.get("url", "")
    method = arguments.get("method", "GET").upper()
    data = arguments.get("data", "")
    cookie = arguments.get("cookie", "")
    headers = arguments.get("headers", "")
    blind = arguments.get("blind", "")
    only_custom = arguments.get("only_custom_payload", False)
    waf_evasion = arguments.get("waf_evasion", True)
    timeout = arguments.get("timeout", 60)

    if not url:
        return "Error: url is required"

    dalfox_path = find_tool("dalfox")
    if not dalfox_path:
        return "Error: dalfox is not installed. Install: go install github.com/hahwul/dalfox/v2@latest"

    output_file = os.path.join(tempfile.gettempdir(), f"dalfox_{os.getpid()}.json")

    cmd_parts = [
        dalfox_path,
        "url", url,
        "--format", "json",
        "--output", output_file,
        "--silence",
    ]

    if method == "POST":
        cmd_parts.append("--method")
        cmd_parts.append("POST")
    if data:
        cmd_parts.extend(["--data", data])
    if cookie:
        cmd_parts.extend(["--cookie", cookie])
    if headers:
        for header in headers.split(","):
            header = header.strip()
            if header:
                cmd_parts.extend(["--header", header])
    if blind:
        cmd_parts.extend(["--blind", blind])
    if only_custom:
        cmd_parts.append("--only-custom-payload")
    if waf_evasion:
        cmd_parts.append("--waf-evasion")

    cmd = " ".join(cmd_parts)
    result = await runtime.execute_command(cmd, timeout=timeout)

    if result.exit_code != 0 and not os.path.exists(output_file):
        return f"Dalfox execution failed:\n{result.stderr or result.stdout}"

    findings = []
    try:
        if os.path.exists(output_file):
            with open(output_file, "r", encoding="utf-8", errors="ignore") as f:
                content = f.read().strip()
                if content:
                    try:
                        data_parsed = json.loads(content)
                        if isinstance(data_parsed, list):
                            findings = data_parsed
                        elif isinstance(data_parsed, dict):
                            findings = data_parsed.get("findings", [data_parsed])
                    except json.JSONDecodeError:
                        # Dalfox may output JSONL
                        for line in content.splitlines():
                            line = line.strip()
                            if line:
                                try:
                                    findings.append(json.loads(line))
                                except json.JSONDecodeError:
                                    pass
            try:
                os.remove(output_file)
            except OSError:
                pass
    except Exception as e:
        return f"Error parsing dalfox output: {e}\nRaw stdout:\n{result.stdout[:2000]}"

    if not findings:
        return f"Dalfox scan complete for {url}.\nNo XSS vulnerabilities detected.\n\nRaw output:\n{result.stdout[:1500]}"

    summary = [
        f"Dalfox XSS Scan Results for {url}",
        f"Method: {method} | WAF Evasion: {waf_evasion}",
        f"Findings: {len(findings)}",
        "",
    ]

    for i, finding in enumerate(findings[:20], 1):
        f_type = finding.get("type", "unknown")
        param = finding.get("param", finding.get("parameter", "unknown"))
        payload = finding.get("payload", "")
        severity = finding.get("severity", "medium")
        summary.append(f"[{i}] Type: {f_type} | Severity: {severity}")
        summary.append(f"    Parameter: {param}")
        if payload:
            summary.append(f"    Payload: {payload[:200]}")
        info = finding.get("info", "")
        if info:
            summary.append(f"    Info: {info[:200]}")
        summary.append("")

    if len(findings) > 20:
        summary.append(f"... and {len(findings) - 20} more findings")

    return "\n".join(summary)
