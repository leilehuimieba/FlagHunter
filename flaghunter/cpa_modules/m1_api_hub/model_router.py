"""
M1 模型路由器

根据任务提示（task_hint）和当前可用的 provider / model 描述，
选择一个更合适的目标模型字符串，供上层调度器做二次匹配。
"""

from __future__ import annotations

from typing import Iterable

ROUTING_RULES = {
    "planning": "heavy",
    "analysis": "heavy",
    "exploitation": "heavy",
    "formatting": "light",
    "summary": "light",
    "tool_parse": "light",
    "default": "medium",
}

MODEL_TIERS = {
    "light": ["claude-haiku-4-20250514", "gpt-4o-mini"],
    "medium": ["claude-sonnet-4-20250514", "gpt-4o"],
    "heavy": ["claude-opus-4-5", "claude-sonnet-4-20250514"],
}

_FAMILY_DEFAULTS = {
    "anthropic": {
        "light": "claude-haiku-4-20250514",
        "medium": "claude-sonnet-4-20250514",
        "heavy": "claude-opus-4-5",
    },
    "openai": {
        "light": "gpt-4o-mini",
        "medium": "gpt-4o",
        "heavy": "gpt-4o",
    },
}


def _normalize_text(value: str) -> str:
    return (value or "").strip().lower()


def _resolve_tier(task_hint: str) -> str:
    normalized = _normalize_text(task_hint)
    if normalized in MODEL_TIERS:
        return normalized

    if normalized in ROUTING_RULES:
        return ROUTING_RULES[normalized]

    for keyword, tier in ROUTING_RULES.items():
        if keyword != "default" and keyword in normalized:
            return tier

    return ROUTING_RULES["default"]


def _candidate_supported(candidate_model: str, available_items: Iterable[str]) -> bool:
    candidate_lower = _normalize_text(candidate_model)
    available = [_normalize_text(item) for item in available_items]

    if not available:
        return True

    if "claude" in candidate_lower:
        family_tokens = ("claude", "anthropic", "haiku", "sonnet", "opus")
        return any(any(token in item for token in family_tokens) for item in available)

    if "gpt" in candidate_lower:
        family_tokens = ("gpt", "openai", "4o", "mini")
        return any(any(token in item for token in family_tokens) for item in available)

    return any(candidate_lower in item or item in candidate_lower for item in available)


def _detect_available_families(available_items: Iterable[str]) -> list[str]:
    families: list[str] = []
    for item in available_items:
        normalized = _normalize_text(item)
        if any(token in normalized for token in ("claude", "anthropic", "haiku", "sonnet", "opus")):
            if "anthropic" not in families:
                families.append("anthropic")
        if any(token in normalized for token in ("gpt", "openai", "4o", "mini")):
            if "openai" not in families:
                families.append("openai")
    return families


def _score_available_model(model: str, tier: str) -> int:
    normalized = _normalize_text(model)
    if normalized in {"anthropic", "openai"}:
        return 0
    score = 0

    if tier == "light":
        if "haiku" in normalized:
            score += 100
        if "mini" in normalized:
            score += 90
        if "sonnet" in normalized or "gpt-4o" in normalized:
            score += 40
    elif tier == "medium":
        if "sonnet" in normalized:
            score += 100
        if "gpt-4o" in normalized and "mini" not in normalized:
            score += 90
        if "opus" in normalized:
            score += 60
    elif tier == "heavy":
        if "opus" in normalized:
            score += 100
        if "sonnet" in normalized:
            score += 90
        if "gpt-4o" in normalized and "mini" not in normalized:
            score += 70

    if "claude" in normalized or "anthropic" in normalized:
        score += 10
    if "gpt" in normalized or "openai" in normalized:
        score += 10

    return score


def _select_best_available_model(available_items: Iterable[str], tier: str) -> str | None:
    items = [
        item for item in available_items
        if _normalize_text(item) and _normalize_text(item) not in {"anthropic", "openai"}
    ]
    if not items:
        return None

    scored = sorted(
        ((item, _score_available_model(item, tier)) for item in items),
        key=lambda pair: pair[1],
        reverse=True,
    )
    best_item, best_score = scored[0]
    return best_item if best_score > 0 else None


def route(task_hint: str, available_providers: list[str]) -> str:
    """
    根据任务提示与当前可用 provider / model 描述，返回推荐模型字符串。

    Args:
        task_hint: 调用方传入的场景标签，如 ``planning`` / ``tool_parse``。
        available_providers: 可用 provider、provider id、provider name 或 model 描述列表。

    Returns:
        推荐模型字符串。
    """
    tier = _resolve_tier(task_hint)
    candidates = MODEL_TIERS.get(tier, MODEL_TIERS["medium"])

    for candidate in candidates:
        if _candidate_supported(candidate, available_providers):
            best_available = _select_best_available_model(available_providers, tier)
            if best_available:
                return best_available
            return candidate

    families = _detect_available_families(available_providers)
    for family in families:
        preferred = _FAMILY_DEFAULTS.get(family, {}).get(tier)
        if preferred:
            return preferred

    default_candidates = MODEL_TIERS[ROUTING_RULES["default"]]
    for candidate in default_candidates:
        if _candidate_supported(candidate, available_providers):
            return candidate

    return candidates[0]
