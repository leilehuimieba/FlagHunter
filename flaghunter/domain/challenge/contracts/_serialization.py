from __future__ import annotations

from dataclasses import asdict, is_dataclass
from typing import Any, Mapping


JsonValue = dict[str, "JsonValue"] | list["JsonValue"] | str | int | float | bool | None


def coerce_json_value(value: Any) -> JsonValue:
    if value is None or isinstance(value, (str, int, float, bool)):
        return value
    if is_dataclass(value):
        return coerce_json_value(asdict(value))
    if isinstance(value, Mapping):
        return {str(key): coerce_json_value(item) for key, item in value.items()}
    if isinstance(value, tuple):
        return [coerce_json_value(item) for item in value]
    if isinstance(value, list):
        return [coerce_json_value(item) for item in value]
    return str(value)


def coerce_json_dict(value: Mapping[str, Any] | None) -> dict[str, JsonValue]:
    if value is None:
        return {}
    coerced = coerce_json_value(value)
    if isinstance(coerced, dict):
        return coerced
    return {}


def coerce_json_list(value: list[Any] | tuple[Any, ...] | None) -> list[JsonValue]:
    if value is None:
        return []
    coerced = coerce_json_value(list(value))
    if isinstance(coerced, list):
        return coerced
    return []
