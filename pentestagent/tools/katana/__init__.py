"""Katana — fast modern web crawler with JavaScript rendering support."""

import json
import os
import tempfile

from ...runtime.runtime import Runtime
from ...tools._tool_env import find_tool
from ...tools.registry import ToolSchema, register_tool


@register_tool(
    name="katana",
    description="Crawl a target URL using Katana to discover endpoints, JS files, forms, and parameters. Supports JavaScript rendering and automatic form detection.",
    schema=ToolSchema(
        type="object",
        properties={
            "url": {"type": "string", "description": "Target URL to crawl"},
            "depth": {"type": "integer", "description": "Maximum crawl depth (default: 3)", "default": 3},
            "timeout": {"type": "integer", "description": "Timeout in seconds per request (default: 10)", "default": 10},
            "js_render": {"type": "boolean", "description": "Enable JavaScript rendering (default: true)", "default": True},
            "headless": {"type": "boolean", "description": "Use headless browser for JS rendering (default: true)", "default": True},
            "scope": {"type": "string", "description": "Crawl scope: domain/subdomain/www/root (default: domain)", "default": "domain"},
            "output_fields": {"type": "string", "description": "Comma-separated output fields: url,path,host,param,fqdn (default: url,path,param)", "default": "url,path,param"},
        },
        required=["url"],
    ),
    category="recon",
)
async def katana(arguments: dict, runtime: Runtime) -> str:
    url = arguments.get("url", "")
    depth = arguments.get("depth", 3)
    timeout = arguments.get("timeout", 10)
    js_render = arguments.get("js_render", True)
    headless = arguments.get("headless", True)
    scope = arguments.get("scope", "domain")
    output_fields = arguments.get("output_fields", "url,path,param")

    if not url:
        return "Error: url is required"

    katana_path = find_tool("katana")
    if not katana_path:
        return "Error: katana is not installed. Install: go install github.com/projectdiscovery/katana/cmd/katana@latest"

    output_file = os.path.join(tempfile.gettempdir(), f"katana_{os.getpid()}.json")

    cmd_parts = [
        katana_path,
        "-u", url,
        "-d", str(depth),
        "-timeout", str(timeout),
        "-scope", scope,
        "-j",  # JSONL output
        "-silent",
        "-o", output_file,
    ]

    if js_render:
        cmd_parts.append("-jc")
    if headless:
        cmd_parts.append("-headless")
    if output_fields:
        cmd_parts.extend(["-f", output_fields])

    cmd = " ".join(cmd_parts)
    result = await runtime.execute_command(cmd, timeout=max(timeout * depth * 2, 60))

    if result.exit_code != 0 and not os.path.exists(output_file):
        return f"Katana execution failed:\n{result.stderr or result.stdout}"

    endpoints = []
    forms = []
    js_files = []
    parameters = set()

    try:
        if os.path.exists(output_file):
            with open(output_file, "r", encoding="utf-8", errors="ignore") as f:
                for line in f:
                    line = line.strip()
                    if not line:
                        continue
                    try:
                        item = json.loads(line)
                    except json.JSONDecodeError:
                        continue

                    endpoint_url = item.get("url", "")
                    if endpoint_url:
                        endpoints.append(endpoint_url)

                    path = item.get("path", "")
                    if path.endswith(".js"):
                        js_files.append(endpoint_url or path)

                    # Katana JSONL may include input/type fields
                    item_type = item.get("type", "")
                    if item_type == "form" or "form" in str(item).lower():
                        forms.append(item)

                    for k in item.get("params", []):
                        if isinstance(k, str):
                            parameters.add(k)

            try:
                os.remove(output_file)
            except OSError:
                pass
    except Exception as e:
        return f"Error parsing katana output: {e}\nRaw stdout:\n{result.stdout[:2000]}"

    # Deduplicate
    endpoints = sorted(set(endpoints))
    js_files = sorted(set(js_files))

    summary = [
        f"Katana Crawl Results for {url}",
        f"Depth: {depth} | JS Render: {js_render} | Scope: {scope}",
        f"Total Endpoints: {len(endpoints)}",
        f"JS Files: {len(js_files)}",
        f"Forms Detected: {len(forms)}",
        f"Unique Parameters: {len(parameters)}",
        "",
        "Endpoints (top 50):",
    ]
    for ep in endpoints[:50]:
        summary.append(f"  - {ep}")
    if len(endpoints) > 50:
        summary.append(f"  ... and {len(endpoints) - 50} more")

    if js_files:
        summary.extend(["", "JavaScript Files:",])
        for js in js_files[:30]:
            summary.append(f"  - {js}")

    if parameters:
        summary.extend(["", "Discovered Parameters:",])
        for p in sorted(parameters)[:30]:
            summary.append(f"  - {p}")

    if forms:
        summary.extend(["", "Forms Detected:",])
        for form in forms[:10]:
            summary.append(f"  - {json.dumps(form, ensure_ascii=False)[:200]}")

    return "\n".join(summary)
