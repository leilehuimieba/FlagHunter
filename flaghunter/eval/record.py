"""Automatic fixture recording for the deterministic replay harness."""

from __future__ import annotations

import copy
import json
from collections import Counter
from types import SimpleNamespace
from typing import Any


class RecordingRuntime:
    """Runtime wrapper that records calls while delegating to a real runtime."""

    def __init__(self, runtime: Any):
        self.runtime = runtime
        self.calls: list[dict[str, Any]] = []
        self.environment = getattr(
            runtime,
            "environment",
            SimpleNamespace(available_tools=[]),
        )

    async def browser_action(self, action: str, **kwargs) -> dict[str, Any]:
        response = await self.runtime.browser_action(action, **kwargs)
        self._record("browser", action, kwargs, response)
        return response

    async def proxy_action(self, action: str, **kwargs) -> dict[str, Any]:
        response = await self.runtime.proxy_action(action, **kwargs)
        self._record("proxy", action, kwargs, response)
        return response

    async def execute_command(self, command: str, timeout: int = 180):
        response = await self.runtime.execute_command(command, timeout=timeout)
        self._record("command", command, {"timeout": timeout}, response)
        return response

    def dump_fixture(
        self,
        name: str,
        target: str,
        expected_flag: str,
        *,
        goal: str = "拿到flag",
        type: str = "web",
        hint: str = "",
        default_proxy: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """Return a ReplayFixture-compatible JSON dictionary."""
        return {
            "name": name,
            "target": target,
            "goal": goal,
            "type": type,
            "hint": hint,
            "expected_flag": expected_flag,
            "browser": self._browser_fixture(),
            "proxy_rules": self._proxy_rules(),
            "default_proxy": default_proxy
            or self._infer_default_proxy()
            or {"status_code": 404, "body": "not found"},
        }

    def _record(
        self,
        channel: str,
        action: str,
        kwargs: dict[str, Any],
        response: Any,
    ) -> None:
        self.calls.append(
            {
                "channel": channel,
                "action": action,
                "kwargs": _json_safe(kwargs),
                "response": _json_safe(response),
            }
        )

    def _browser_fixture(self) -> dict[str, Any]:
        browser: dict[str, Any] = {}
        for call in self.calls:
            if call["channel"] != "browser":
                continue
            browser[call["action"]] = copy.deepcopy(call["response"])
        return browser

    def _proxy_rules(self) -> list[dict[str, Any]]:
        rules = []
        for call in self.calls:
            if call["channel"] != "proxy":
                continue

            when = self._proxy_when(call["kwargs"])
            response = copy.deepcopy(call["response"])
            if response == self._infer_default_proxy():
                continue
            rules.append({"when": when, "response": response})
        return _dedupe_rules(rules)

    def _proxy_when(self, kwargs: dict[str, Any]) -> dict[str, Any]:
        when: dict[str, Any] = {}
        url = str(kwargs.get("url") or "")
        if url:
            when["url_contains"] = url

        body_contains = _body_contains(kwargs)
        if body_contains:
            when["body_contains"] = body_contains

        if _requires_operator_injection(kwargs):
            when["requires_operator_injection"] = True

        return when

    def _infer_default_proxy(self) -> dict[str, Any] | None:
        proxy_responses = [
            json.dumps(call["response"], sort_keys=True, ensure_ascii=False)
            for call in self.calls
            if call["channel"] == "proxy"
        ]
        if not proxy_responses:
            return None

        serialized, count = Counter(proxy_responses).most_common(1)[0]
        response = json.loads(serialized)
        if count > 1 and _looks_default_proxy_response(response):
            return response
        return None


def _json_safe(value: Any) -> Any:
    try:
        json.dumps(value)
        return copy.deepcopy(value)
    except TypeError:
        pass

    if isinstance(value, SimpleNamespace):
        return {key: _json_safe(val) for key, val in vars(value).items()}
    if isinstance(value, dict):
        return {str(key): _json_safe(val) for key, val in value.items()}
    if isinstance(value, (list, tuple)):
        return [_json_safe(item) for item in value]
    if hasattr(value, "__dict__"):
        return {key: _json_safe(val) for key, val in vars(value).items()}
    return str(value)


def _body_contains(kwargs: dict[str, Any]) -> str | None:
    json_body = kwargs.get("json")
    data = kwargs.get("data")

    if json_body is not None:
        return json.dumps(json_body, sort_keys=True, ensure_ascii=False)
    if isinstance(data, dict) and data:
        key, value = next(iter(data.items()))
        return json.dumps({key: value}, sort_keys=True, ensure_ascii=False)
    if data:
        return str(data)
    return None


def _requires_operator_injection(kwargs: dict[str, Any]) -> bool:
    json_body = kwargs.get("json")
    data = kwargs.get("data")

    operator_injection = False
    if isinstance(json_body, dict):
        operator_injection = any(
            isinstance(value, dict) for value in json_body.values()
        )
    if isinstance(data, dict):
        operator_injection = operator_injection or any("[$" in str(key) for key in data)
    return operator_injection


def _looks_default_proxy_response(response: dict[str, Any]) -> bool:
    status_code = int(response.get("status_code") or 0)
    body = str(response.get("body") or "").lower()
    return status_code in {400, 401, 403, 404, 405} or body in {
        "",
        "not found",
        "forbidden",
        "invalid credentials",
    }


def _dedupe_rules(rules: list[dict[str, Any]]) -> list[dict[str, Any]]:
    seen = set()
    deduped = []
    for rule in rules:
        marker = json.dumps(rule, sort_keys=True, ensure_ascii=False)
        if marker in seen:
            continue
        seen.add(marker)
        deduped.append(rule)
    return deduped
