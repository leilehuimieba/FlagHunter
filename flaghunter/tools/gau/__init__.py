"""GAU (GetAllUrls) — fetch known URLs from AlienVault's Open Threat Exchange, the Wayback Machine, and Common Crawl."""

import os
import tempfile

from ...runtime.runtime import Runtime
from ...tools._tool_env import find_tool
from ...tools.registry import ToolSchema, register_tool


@register_tool(
    name="gau",
    description="Discover historical URLs for a target domain using GAU. Retrieves URLs from Wayback Machine, Common Crawl, and OTX. Useful for finding old endpoints, parameters, and hidden paths.",
    schema=ToolSchema(
        type="object",
        properties={
            "domain": {"type": "string", "description": "Target domain (e.g., example.com)"},
            "subs": {"type": "boolean", "description": "Include subdomains (default: true)", "default": True},
            "providers": {"type": "string", "description": "Providers: wayback,otx,commoncrawl (default: all)", "default": "wayback,otx,commoncrawl"},
            "blacklist": {"type": "string", "description": "Extensions to skip: png,jpg,gif,css (default: png,jpg,gif,css,woff,ttf,svg)"},
            "timeout": {"type": "integer", "description": "Timeout in seconds (default: 60)", "default": 60},
            "max_urls": {"type": "integer", "description": "Maximum URLs to return (default: 500)", "default": 500},
        },
        required=["domain"],
    ),
    category="recon",
)
async def gau(arguments: dict, runtime: Runtime) -> str:
    domain = arguments.get("domain", "")
    subs = arguments.get("subs", True)
    providers = arguments.get("providers", "wayback,otx,commoncrawl")
    blacklist = arguments.get("blacklist", "")
    timeout = arguments.get("timeout", 60)
    max_urls = arguments.get("max_urls", 500)

    if not domain:
        return "Error: domain is required"

    gau_path = find_tool("gau")
    if not gau_path:
        return "Error: gau is not installed. Install: go install github.com/lc/gau/v2/cmd/gau@latest"

    output_file = os.path.join(tempfile.gettempdir(), f"gau_{os.getpid()}.txt")

    cmd_parts = [
        gau_path,
        domain,
        "--silent",
        "-o", output_file,
    ]

    if subs:
        cmd_parts.append("--subs")
    if providers:
        cmd_parts.extend(["--providers", providers])
    if blacklist:
        cmd_parts.extend(["--blacklist", blacklist])
    else:
        cmd_parts.extend(["--blacklist", "png,jpg,gif,css,woff,ttf,svg,ico,pdf,zip"])

    cmd = " ".join(cmd_parts)
    result = await runtime.execute_command(cmd, timeout=timeout)

    if result.exit_code != 0 and not os.path.exists(output_file):
        return f"GAU execution failed:\n{result.stderr or result.stdout}"

    urls = []
    try:
        if os.path.exists(output_file):
            with open(output_file, "r", encoding="utf-8", errors="ignore") as f:
                urls = [line.strip() for line in f if line.strip()]
            try:
                os.remove(output_file)
            except OSError:
                pass
    except Exception as e:
        return f"Error reading GAU output: {e}\nRaw stdout:\n{result.stdout[:2000]}"

    if not urls:
        return f"GAU scan complete for {domain}.\nNo historical URLs found.\n\nRaw output:\n{result.stdout[:1500]}"

    # Categorize URLs
    endpoints = []
    params = set()
    js_files = []
    api_endpoints = []
    interesting = []

    for url in urls:
        if ".js" in url:
            js_files.append(url)
        if "/api/" in url or "/graphql" in url or "/rest/" in url:
            api_endpoints.append(url)
        if "?" in url:
            endpoint_base = url.split("?")[0]
            endpoints.append(endpoint_base)
            for param in url.split("?")[1].split("&"):
                if "=" in param:
                    params.add(param.split("=")[0])
        else:
            endpoints.append(url)

        # Interesting patterns
        lower = url.lower()
        if any(k in lower for k in ["admin", "login", "config", "backup", "flag", "shell", "upload", "test", "debug", "phpinfo", ".env", ".git"]):
            interesting.append(url)

    endpoints = sorted(set(endpoints))
    js_files = sorted(set(js_files))
    api_endpoints = sorted(set(api_endpoints))
    interesting = sorted(set(interesting))

    summary = [
        f"GAU Historical URL Results for {domain}",
        f"Providers: {providers} | Subdomains: {subs}",
        f"Total URLs: {len(urls)}",
        f"Unique Endpoints: {len(endpoints)}",
        f"API Endpoints: {len(api_endpoints)}",
        f"JS Files: {len(js_files)}",
        f"Interesting Paths: {len(interesting)}",
        f"Unique Parameters: {len(params)}",
        "",
    ]

    if interesting:
        summary.extend(["Interesting Paths:",])
        for url in interesting[:30]:
            summary.append(f"  - {url}")
        summary.append("")

    if api_endpoints:
        summary.extend(["API Endpoints:",])
        for url in api_endpoints[:30]:
            summary.append(f"  - {url}")
        summary.append("")

    if js_files:
        summary.extend(["JavaScript Files:",])
        for url in js_files[:30]:
            summary.append(f"  - {url}")
        summary.append("")

    if params:
        summary.extend(["Discovered Parameters:",])
        for p in sorted(params)[:30]:
            summary.append(f"  - {p}")
        summary.append("")

    summary.extend(["Sample Endpoints:",])
    for url in endpoints[:50]:
        summary.append(f"  - {url}")
    if len(endpoints) > 50:
        summary.append(f"  ... and {len(endpoints) - 50} more")

    return "\n".join(summary)
