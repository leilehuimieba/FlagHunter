"""LLM utility functions for FlagHunter."""

from typing import Optional


def parse_llm_json(text: str) -> Optional[dict]:
    """
    Attempt to parse JSON from LLM output.

    Args:
        text: Text that may contain JSON

    Returns:
        Parsed dict or None
    """
    import json
    import re

    # Try direct parse first
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        pass

    # Try to find JSON in code blocks
    pattern = r"```(?:json)?\n?(.*?)```"
    matches = re.findall(pattern, text, re.DOTALL)

    for match in matches:
        try:
            return json.loads(match.strip())
        except json.JSONDecodeError:
            continue

    # Try to find JSON object in text
    pattern = r"\{[^{}]*\}"
    matches = re.findall(pattern, text)

    for match in matches:
        try:
            return json.loads(match)
        except json.JSONDecodeError:
            continue

    return None
