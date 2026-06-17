"""Structured nmap wrapper for PentestAgent."""

from __future__ import annotations

import json
import platform
from typing import TYPE_CHECKING
from xml.etree import ElementTree as ET

from .._tool_env import patch_tool_path, find_tool
from ..registry import ToolSchema, register_tool

if TYPE_CHECKING:
    from ...runtime import Runtime

patch_tool_path()


def _decode(raw: bytes) -> str:
    if isinstance(raw, str):
        return raw
    for enc in ("utf-8", "gbk", "cp936", "latin-1"):
        try:
            return raw.decode(enc)
        except (UnicodeDecodeError, AttributeError):
            continue
    return raw.decode("utf-8", errors="replace")


def _normalize_text(raw: bytes | str | None) -> str:
    if raw is None:
        return ""
    return _decode(raw).encode("utf-8", "replace").decode("utf-8")


def _default_result(target: str, raw: str = "") -> dict:
    """Create a default structured result."""
    return {
        "target": target,
        "status": "unknown",
        "ports": [],
        "os_guess": "",
        "raw": raw,
    }


def _shell_quote(value: str) -> str:
    """Quote a shell argument conservatively for current runtimes."""
    return '"' + str(value).replace('"', '\\"') + '"'


def _build_nmap_command(
    target: str, ports: str, scan_type: str, scripts: list[str]
) -> str:
    """Build an nmap command that emits XML to stdout."""
    normalized_scan_type = (scan_type or "SYN").lower()
    if normalized_scan_type == "udp":
        base_flags = ["-sU", "-sV", "-Pn", "--open"]
    elif platform.system() == "Windows":
        # Windows 默认走 TCP connect 扫描，避免依赖 npcap
        base_flags = ["-sT", "-sV", "-Pn", "--open"]
    else:
        # Linux / 其他平台保持 SYN 扫描
        base_flags = ["-sS", "-sV", "-Pn", "--open"]

    parts = ["nmap", "-oX", "-", *base_flags, "-p", _shell_quote(ports)]

    script_names = [s.strip() for s in (scripts or []) if str(s).strip()]
    if script_names:
        parts.extend(["--script", _shell_quote(",".join(script_names))])

    parts.append(_shell_quote(target))
    return " ".join(parts)


async def _execute_command(runtime: "Runtime", command: str, timeout: int = 300):
    """Execute a command using the available runtime API."""
    if hasattr(runtime, "execute_command"):
        return await runtime.execute_command(command, timeout=timeout)

    if hasattr(runtime, "execute"):
        return await runtime.execute(command)

    raise AttributeError("Runtime does not expose execute_command() or execute()")


def _extract_service_version(service_elem: ET.Element | None) -> tuple[str, str]:
    """Extract service name and version string from a port/service element."""
    if service_elem is None:
        return "", ""

    service_name = service_elem.attrib.get("name", "")
    version_parts = [
        service_elem.attrib.get("product", "").strip(),
        service_elem.attrib.get("version", "").strip(),
        service_elem.attrib.get("extrainfo", "").strip(),
    ]
    version = " ".join(part for part in version_parts if part).strip()
    return service_name, version


def _parse_nmap_xml(target: str, xml_text: str, raw: str) -> dict:
    """Parse nmap XML output into a structured dictionary."""
    result = _default_result(target=target, raw=raw)

    root = ET.fromstring(xml_text)
    host = root.find("host")
    if host is None:
        return result

    status_elem = host.find("status")
    if status_elem is not None:
        result["status"] = status_elem.attrib.get("state", "unknown")

    os_match = host.find("./os/osmatch")
    if os_match is not None:
        result["os_guess"] = os_match.attrib.get("name", "")

    ports: list[dict] = []
    for port_elem in host.findall("./ports/port"):
        state_elem = port_elem.find("state")
        service_elem = port_elem.find("service")
        service_name, version = _extract_service_version(service_elem)

        script_results = {}
        for script_elem in port_elem.findall("script"):
            script_id = script_elem.attrib.get("id", "")
            if script_id:
                script_results[script_id] = script_elem.attrib.get("output", "")

        port_info = {
            "port": int(port_elem.attrib.get("portid", "0")),
            "protocol": port_elem.attrib.get("protocol", ""),
            "state": state_elem.attrib.get("state", "unknown")
            if state_elem is not None
            else "unknown",
            "service": service_name,
            "version": version,
            "scripts": script_results,
        }
        ports.append(port_info)

    result["ports"] = ports
    return result


def _looks_like_nmap_missing(command_result) -> bool:
    """Best-effort detection for missing nmap binary."""
    stdout = _normalize_text(getattr(command_result, "stdout", "") or "")
    stderr = _normalize_text(getattr(command_result, "stderr", "") or "")
    text = f"{stdout}\n{stderr}".lower()
    indicators = (
        "not found",
        "is not recognized",
        "no such file",
        "could not find executable",
        "cannot find the file",
    )
    return getattr(command_result, "exit_code", 0) != 0 and any(
        indicator in text for indicator in indicators
    )


async def _run_python_nmap_fallback(
    target: str, ports: str, scan_type: str, scripts: list[str]
) -> dict:
    """Fallback to python-nmap when direct XML execution is unavailable."""
    result = _default_result(target=target)

    try:
        import nmap  # type: ignore
    except Exception as exc:
        result["raw"] = f"nmap command unavailable and python-nmap import failed: {exc}"
        return result

    try:
        scanner = nmap.PortScanner()
        normalized_scan_type = (scan_type or "SYN").lower()
        if normalized_scan_type == "udp":
            args = ["-sU", "-sV", "-Pn", "--open", "-p", ports]
        elif platform.system() == "Windows":
            args = ["-sT", "-sV", "-Pn", "--open", "-p", ports]
        else:
            args = ["-sS", "-sV", "-Pn", "--open", "-p", ports]

        script_names = [s.strip() for s in (scripts or []) if str(s).strip()]
        if script_names:
            args.extend(["--script", ",".join(script_names)])

        scanner.scan(hosts=target, arguments=" ".join(args))

        if target not in scanner.all_hosts():
            result["raw"] = json.dumps(scanner._scan_result, ensure_ascii=False)  # noqa: SLF001
            return result

        host_data = scanner[target]
        result["status"] = host_data.state() if hasattr(host_data, "state") else "unknown"

        tcp_data = host_data.get("tcp", {})
        udp_data = host_data.get("udp", {})
        ports: list[dict] = []
        for protocol, proto_data in (("tcp", tcp_data), ("udp", udp_data)):
            for port_number, port_data in sorted(proto_data.items()):
                scripts_map = {}
                if isinstance(port_data, dict):
                    for key, value in port_data.items():
                        if key.startswith("script_"):
                            scripts_map[key.removeprefix("script_")] = value

                version_parts = [
                    str(port_data.get("product", "")).strip(),
                    str(port_data.get("version", "")).strip(),
                    str(port_data.get("extrainfo", "")).strip(),
                ]
                version = " ".join(part for part in version_parts if part).strip()

                ports.append(
                    {
                        "port": int(port_number),
                        "protocol": protocol,
                        "state": port_data.get("state", "unknown"),
                        "service": port_data.get("name", ""),
                        "version": version,
                        "scripts": scripts_map,
                    }
                )

        result["ports"] = ports

        matches = host_data.get("osmatch", [])
        if matches:
            result["os_guess"] = matches[0].get("name", "")

        result["raw"] = json.dumps(scanner._scan_result, ensure_ascii=False)  # noqa: SLF001
        return result
    except Exception as exc:
        result["raw"] = f"python-nmap fallback failed: {exc}"
        return result


async def run_nmap(
    target: str,
    ports: str = "1-1000",
    scan_type: str = "SYN",
    scripts: list[str] = [],
    runtime=None,
) -> dict:
    """
    Run nmap and return a structured dictionary.

    The registered tool wrapper serializes this dictionary to JSON for the
    current tool execution interface.
    """
    if runtime is None and not find_tool("nmap"):
        fallback_result = await _run_python_nmap_fallback(
            target=target,
            ports=ports or "1-1000",
            scan_type=scan_type or "SYN",
            scripts=scripts or [],
        )
        if not fallback_result.get("raw"):
            fallback_result["raw"] = "nmap not installed"
        return fallback_result

    if runtime is None:
        from ...runtime import LocalRuntime

        runtime = LocalRuntime()

    command = _build_nmap_command(
        target=target,
        ports=ports or "1-1000",
        scan_type=scan_type or "SYN",
        scripts=scripts or [],
    )

    try:
        command_result = await _execute_command(runtime, command, timeout=300)
    except Exception as exc:
        return _default_result(target=target, raw=f"runtime execution failed: {exc}")

    raw_output = _normalize_text(getattr(command_result, "stdout", "") or "")
    stderr_output = _normalize_text(getattr(command_result, "stderr", "") or "")
    combined_raw = raw_output if not stderr_output else f"{raw_output}\n{stderr_output}".strip()

    if raw_output.strip().startswith("<?xml") or "<nmaprun" in raw_output:
        try:
            return _parse_nmap_xml(target=target, xml_text=raw_output, raw=combined_raw)
        except ET.ParseError as exc:
            return _default_result(
                target=target,
                raw=f"{combined_raw}\nXML parse error: {exc}".strip(),
            )

    if _looks_like_nmap_missing(command_result):
        fallback_result = await _run_python_nmap_fallback(
            target=target,
            ports=ports or "1-1000",
            scan_type=scan_type or "SYN",
            scripts=scripts or [],
        )
        if not fallback_result.get("raw"):
            fallback_result["raw"] = combined_raw
        return fallback_result

    return _default_result(target=target, raw=combined_raw)


@register_tool(
    name="nmap",
    description="Run an nmap scan and return structured JSON results.",
    schema=ToolSchema(
        properties={
            "target": {
                "type": "string",
                "description": "Target host, IP, or CIDR to scan",
            },
            "ports": {
                "type": "string",
                "description": "Port selection, e.g. '1-1000' or '22,80,443'",
                "default": "1-1000",
            },
            "scan_type": {
                "type": "string",
                "description": "Scan type: SYN, UDP, or version",
                "default": "SYN",
            },
            "scripts": {
                "type": "array",
                "description": "Optional nmap NSE scripts to run",
                "items": {"type": "string"},
            },
        },
        required=["target"],
    ),
    category="network",
)
async def nmap_tool(arguments: dict, runtime: "Runtime") -> str:
    """Registered PentestAgent tool wrapper for structured nmap output."""
    result = await run_nmap(
        target=arguments["target"],
        ports=arguments.get("ports", "1-1000"),
        scan_type=arguments.get("scan_type", "SYN"),
        scripts=arguments.get("scripts", []) or [],
        runtime=runtime,
    )
    return json.dumps(result, ensure_ascii=False)
