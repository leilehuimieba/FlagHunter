from __future__ import annotations

from collections.abc import Mapping
from typing import Any

_CTF_SUBTYPES = {"web", "crypto", "pwn", "reverse", "misc"}
_PENTEST_SUBTYPES = {"web", "network", "host", "api"}
_KNOWN_MODES = {"ctf", "pentest"}


def _clean_str(value: Any) -> str:
    return str(value or "").strip().lower()


def _normalize_subtype(value: Any, *, mode: str) -> str:
    subtype = _clean_str(value)
    if mode == "ctf":
        return subtype if subtype in _CTF_SUBTYPES else "unknown"
    if mode == "pentest":
        return subtype if subtype in _PENTEST_SUBTYPES else "unknown"
    return "unknown"


def resolve_mode_contract(
    payload: Mapping[str, Any] | None,
    *,
    source_task: Mapping[str, Any] | None = None,
) -> dict[str, str]:
    payload = payload or {}
    source_task = source_task or {}

    payload_mode = _clean_str(payload.get("mode"))
    source_mode = _clean_str(source_task.get("mode"))

    if payload_mode in _KNOWN_MODES:
        mode = payload_mode
    elif source_mode in _KNOWN_MODES:
        mode = source_mode
    else:
        payload_ctf_type = _clean_str(payload.get("ctfType"))
        mode = "ctf" if payload_ctf_type else "pentest"

    if mode == "ctf":
        mode_subtype = _normalize_subtype(
            source_task.get("modeSubtype")
            or source_task.get("ctfType")
            or payload.get("ctfType"),
            mode=mode,
        )
        goal_style = "flag"
    else:
        mode_subtype = _normalize_subtype(
            source_task.get("modeSubtype")
            or payload.get("modeSubtype")
            or payload.get("ctfType"),
            mode=mode,
        )
        goal_style = "evidence"

    return {
        "mode": mode,
        "modeSubtype": mode_subtype,
        "goalStyle": goal_style,
    }
