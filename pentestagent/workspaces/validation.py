"""Workspace target validation utilities.

Provides helpers to extract candidate targets from arbitrary tool arguments
and to determine whether a candidate target is covered by the allowed
workspace targets (IP, CIDR, hostname).
"""

import ipaddress
import logging
from typing import Any, List
from urllib.parse import urlparse

from .manager import TargetManager


def gather_candidate_targets(obj: Any) -> List[str]:
    """
    Extract candidate target strings from arguments (shallow, non-recursive).

    This function inspects only the top-level of the provided object (str or dict)
    and collects values for common target keys (e.g., 'target', 'host', 'ip', etc.).
    It does NOT recurse into nested dictionaries or lists. If you need to extract
    targets from deeply nested structures, you must implement or call a recursive
    extractor separately.

    Rationale: Shallow extraction is fast and predictable for most tool argument
    schemas. For recursive extraction, see the project documentation or extend
    this function as needed.
    """
    candidates: List[str] = []
    if isinstance(obj, str):
        candidates.append(obj)
    elif isinstance(obj, dict):
        for k, v in obj.items():
            if k.lower() in (
                "target",
                "host",
                "hostname",
                "ip",
                "address",
                "url",
                "hosts",
                "targets",
            ):
                if isinstance(v, (list, tuple)):
                    for it in v:
                        if isinstance(it, str):
                            candidates.append(it)
                elif isinstance(v, str):
                    candidates.append(v)
    return candidates


def _parse_url_target(value: str) -> dict[str, Any] | None:
    try:
        parsed = urlparse(value.strip())
    except Exception:
        return None

    if not parsed.scheme or not parsed.hostname:
        return None

    try:
        return {
            "scheme": parsed.scheme.lower(),
            "host": TargetManager.normalize_host(parsed.hostname),
            "port": parsed.port,
            "path": parsed.path or "/",
        }
    except Exception:
        return None


def _parse_host_port(value: str) -> dict[str, Any] | None:
    raw = value.strip()
    if not raw:
        return None

    if raw.startswith("[") and "]:" in raw:
        host_part, port_part = raw[1:].split("]:", 1)
        if port_part.isdigit():
            try:
                return {
                    "host": TargetManager.normalize_host(host_part),
                    "port": int(port_part),
                }
            except Exception:
                return None

    if raw.count(":") == 1 and "://" not in raw:
        host_part, port_part = raw.rsplit(":", 1)
        if port_part.isdigit():
            try:
                return {
                    "host": TargetManager.normalize_host(host_part),
                    "port": int(port_part),
                }
            except Exception:
                return None

    return None


def _simple_allowed_values(allowed: List[str]) -> List[str]:
    flattened: List[str] = []
    for item in allowed:
        if not isinstance(item, str):
            continue
        if parsed := _parse_url_target(item):
            flattened.append(parsed["host"])
            continue
        if parsed_hp := _parse_host_port(item):
            flattened.append(parsed_hp["host"])
            continue
        flattened.append(item)
    return flattened


def _plain_allowed_values(allowed: List[str]) -> List[str]:
    """Return only non-URL, non-host:port scope entries.

    When a candidate is a full URL/host:port, explicit port-scoped allowed
    entries must not silently degrade into host-only matches.
    """
    flattened: List[str] = []
    for item in allowed:
        if not isinstance(item, str):
            continue
        if _parse_url_target(item) or _parse_host_port(item):
            continue
        flattened.append(item)
    return flattened


def _is_simple_target_in_scope(candidate: str, allowed: List[str]) -> bool:
    try:
        norm = TargetManager.normalize_target(candidate)
    except Exception:
        return False

    try:
        if "/" in norm:
            cand_net = ipaddress.ip_network(norm, strict=False)
            for a in allowed:
                try:
                    normalized_allowed = TargetManager.normalize_target(a)
                    if "/" in normalized_allowed:
                        an = ipaddress.ip_network(normalized_allowed, strict=False)
                        if cand_net.subnet_of(an) or cand_net == an:
                            return True
                    else:
                        try:
                            allowed_ip = ipaddress.ip_address(normalized_allowed)
                        except Exception:
                            continue
                        if (
                            cand_net.num_addresses == 1
                            and cand_net.network_address == allowed_ip
                        ):
                            return True
                except Exception:
                    continue
            return False

        try:
            cand_ip = ipaddress.ip_address(norm)
            for a in allowed:
                try:
                    normalized_allowed = TargetManager.normalize_target(a)
                    if "/" in normalized_allowed:
                        an = ipaddress.ip_network(normalized_allowed, strict=False)
                        if cand_ip in an:
                            return True
                    else:
                        if normalized_allowed == norm:
                            return True
                except Exception:
                    try:
                        if TargetManager.normalize_host(a) == norm:
                            return True
                    except Exception:
                        continue
            return False
        except Exception:
            for a in allowed:
                try:
                    if TargetManager.normalize_target(a) == norm:
                        return True
                except Exception:
                    try:
                        if TargetManager.normalize_host(a) == norm:
                            return True
                    except Exception:
                        continue
            return False
    except Exception as e:
        logging.getLogger(__name__).exception("Error checking target scope: %s", e)
        return False


def is_target_in_scope(candidate: str, allowed: List[str]) -> bool:
    """Check whether `candidate` is covered by any entry in `allowed`.

    Allowed entries may be IPs, CIDRs, or hostnames/labels. Candidate may
    also be an IP, CIDR, or hostname. The function normalizes inputs and
    performs robust comparisons for networks and addresses.
    """
    if not isinstance(candidate, str) or not candidate.strip() or not allowed:
        return False

    candidate = candidate.strip()

    if parsed_candidate_url := _parse_url_target(candidate):
        for entry in allowed:
            if not isinstance(entry, str):
                continue
            if allowed_url := _parse_url_target(entry):
                if parsed_candidate_url["host"] == allowed_url["host"]:
                    if (
                        allowed_url["port"] is None
                        or parsed_candidate_url["port"] == allowed_url["port"]
                    ):
                        return True
            elif allowed_host_port := _parse_host_port(entry):
                if (
                    parsed_candidate_url["host"] == allowed_host_port["host"]
                    and parsed_candidate_url["port"] == allowed_host_port["port"]
                ):
                    return True
        return _is_simple_target_in_scope(
            parsed_candidate_url["host"], _plain_allowed_values(allowed)
        )

    if parsed_candidate_host_port := _parse_host_port(candidate):
        for entry in allowed:
            if not isinstance(entry, str):
                continue
            if allowed_url := _parse_url_target(entry):
                if parsed_candidate_host_port["host"] == allowed_url["host"]:
                    if (
                        allowed_url["port"] is None
                        or parsed_candidate_host_port["port"] == allowed_url["port"]
                    ):
                        return True
            elif allowed_host_port := _parse_host_port(entry):
                if (
                    parsed_candidate_host_port["host"] == allowed_host_port["host"]
                    and parsed_candidate_host_port["port"] == allowed_host_port["port"]
                ):
                    return True
        return _is_simple_target_in_scope(
            parsed_candidate_host_port["host"], _plain_allowed_values(allowed)
        )

    return _is_simple_target_in_scope(candidate, _simple_allowed_values(allowed))
