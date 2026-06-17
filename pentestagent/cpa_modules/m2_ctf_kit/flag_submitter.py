#!/usr/bin/env python3
"""
PentestAgent M2 - CTF Kit / Flag 自动提交模块
===============================================
支持多平台（CTFd、HackTheBox、TryHackMe、Root-Me、Manual）的 Flag 异步提交封装。
使用 Python 3.10+ 标准库 urllib，无需额外依赖。

典型用法：
    result = await submit_flag(
        flag="flag{example}",
        platform_type="ctfd",
        challenge_id="42",
        base_url="https://ctf.example.com",
        auth_token="your_token"
    )
    print(format_flag_result(result))
"""

from __future__ import annotations

import asyncio
import json
import os
import ssl
import urllib.request
import urllib.error
from dataclasses import dataclass, field
from typing import Any, Coroutine, Dict, List, Optional


# ---------------------------------------------------------------------------
# 结果对象
# ---------------------------------------------------------------------------
@dataclass
class SubmitResult:
    """Flag 提交结果统一封装。

    所有平台提交后均返回此对象，调用方无需捕获异常。

    Attributes:
        success: HTTP 请求是否成功送达（网络层面）。
        message: 平台返回的原始消息文本。
        platform: 平台标识名称，如 ``"CTFd"``、``"HTB"``。
        correct: Flag 是否被判定为正确。
        points: 本题得分（仅 correct=True 时有效）。
        rank: 当前队伍排名（部分平台支持）。
        total_teams: 参赛队伍总数（部分平台支持）。
        error: 当 success=False 时的错误描述。
        challenge_id: 对应题目 ID。
    """

    success: bool = False
    message: str = ""
    platform: str = ""
    correct: bool = False
    points: int = 0
    rank: int = 0
    total_teams: int = 0
    error: str = ""
    challenge_id: str = ""


# ---------------------------------------------------------------------------
# 平台配置基类
# ---------------------------------------------------------------------------
class CtfPlatform:
    """CTF 平台抽象基类。

    所有具体平台应继承此类并实现 ``submit_flag``、``get_challenges``、``get_scoreboard``。
    """

    def __init__(
        self,
        base_url: str,
        api_key: str | None = None,
        auth_token: str | None = None,
    ) -> None:
        self.base_url = base_url.rstrip("/")
        self.api_key = api_key
        self.auth_token = auth_token
        self.supports_submit = True

    async def submit_flag(self, flag: str, challenge_id: str | None = None) -> SubmitResult:
        """提交 Flag 到平台。子类必须重写。"""
        raise NotImplementedError

    async def get_challenges(self) -> List[dict]:
        """获取题目列表。子类必须重写。"""
        raise NotImplementedError

    async def get_scoreboard(self) -> dict:
        """获取积分榜。子类必须重写。"""
        raise NotImplementedError

    def _headers(self) -> dict[str, str]:
        """构造通用 HTTP 请求头，含认证信息。"""
        h = {"Content-Type": "application/json", "Accept": "application/json"}
        if self.auth_token:
            h["Authorization"] = f"Token {self.auth_token}"
        if self.api_key:
            h["X-API-Key"] = self.api_key
        return h

    def _request(
        self, method: str, path: str, data: dict | None = None
    ) -> dict[str, Any]:
        """使用标准库 ``urllib`` 发送同步 HTTP 请求并返回 JSON 字典。

        内部封装了 SSL 证书验证关闭（用于自签名 CTF 环境）和 30 秒超时。

        Args:
            method: HTTP 方法，如 ``"GET"``、``"POST"``。
            path: API 路径，如 ``"/api/v1/challenges"``。
            data: 请求体字典，自动序列化为 JSON。

        Returns:
            解析后的 JSON 字典；出错时返回 ``{"error": "描述"}``。
        """
        url = f"{self.base_url}{path}"
        ctx = ssl.create_default_context()
        ctx.check_hostname = False
        ctx.verify_mode = ssl.CERT_NONE
        req = urllib.request.Request(url, method=method, headers=self._headers())
        if data:
            req.data = json.dumps(data).encode("utf-8")
        try:
            with urllib.request.urlopen(req, context=ctx, timeout=30) as resp:
                raw = resp.read().decode("utf-8")
                return json.loads(raw) if raw else {}
        except urllib.error.HTTPError as e:
            body = e.read().decode("utf-8", errors="ignore")
            return {"error": f"HTTP {e.code}: {e.reason}", "body": body}
        except Exception as exc:
            return {"error": str(exc)}

    async def _arequest(
        self, method: str, path: str, data: dict | None = None
    ) -> dict[str, Any]:
        """异步包装器：在默认线程池中执行 ``_request``，避免阻塞事件循环。"""
        loop = asyncio.get_running_loop()
        return await loop.run_in_executor(None, self._request, method, path, data)


# ---------------------------------------------------------------------------
# 1. CTFd 平台
# ---------------------------------------------------------------------------
class CTFdPlatform(CtfPlatform):
    """CTFd <https://ctfd.io>`_ 平台提交器。

    CTFd 是国内外观赛最常见的开源 CTF 平台，API 风格统一。
    """

    async def submit_flag(self, flag: str, challenge_id: str | None = None) -> SubmitResult:
        """向 CTFd 提交 Flag。

        Args:
            flag: 待提交的 Flag 字符串。
            challenge_id: CTFd 内部题目 ID（数字字符串）。
        """
        if not challenge_id:
            return SubmitResult(
                success=False, error="CTFd 需要 challenge_id", platform="CTFd"
            )
        payload = {"challenge_id": challenge_id, "submission": flag}
        resp = await self._arequest("POST", "/api/v1/challenges/attempt", payload)

        if "error" in resp:
            return SubmitResult(success=False, error=resp["error"], platform="CTFd")

        data = resp.get("data", {})
        status = data.get("status", "")
        msg = data.get("message", "")

        correct = status == "correct"
        points = 0
        if correct:
            points = data.get("challenge", {}).get("value", 0)

        return SubmitResult(
            success=True,
            message=msg,
            platform="CTFd",
            correct=correct,
            points=points,
            challenge_id=challenge_id,
        )

    async def get_challenges(self) -> List[dict]:
        resp = await self._arequest("GET", "/api/v1/challenges")
        return resp.get("data", {}).get("challenges", []) if "data" in resp else []

    async def get_scoreboard(self) -> dict:
        return await self._arequest("GET", "/api/v1/scoreboard")


# ---------------------------------------------------------------------------
# 2. HackTheBox 平台
# ---------------------------------------------------------------------------
class HTBPlatform(CtfPlatform):
    """HackTheBox <https://hackthebox.com>`_ 平台提交器（CTF 赛事模式）。"""

    async def submit_flag(self, flag: str, challenge_id: str | None = None) -> SubmitResult:
        """向 HackTheBox CTF 提交 Flag。

        HTB API v4 要求 ``challenge_id`` 作为 URL 路径参数。
        """
        if not challenge_id:
            return SubmitResult(
                success=False, error="HTB 需要 challenge_id", platform="HTB"
            )
        payload = {"flag": flag, "challenge_id": challenge_id}
        resp = await self._arequest("POST", "/api/v4/challenge/attempt", payload)

        if "error" in resp:
            return SubmitResult(success=False, error=resp["error"], platform="HTB")

        msg = resp.get("message", "")
        correct = resp.get("status", False) is True or "correct" in msg.lower()

        return SubmitResult(
            success=True,
            message=msg,
            platform="HTB",
            correct=correct,
            challenge_id=challenge_id,
        )

    async def get_challenges(self) -> List[dict]:
        resp = await self._arequest("GET", "/api/v4/challenge/list")
        return resp.get("data", []) if isinstance(resp.get("data"), list) else []

    async def get_scoreboard(self) -> dict:
        return await self._arequest("GET", "/api/v4/scoreboard")


# ---------------------------------------------------------------------------
# 3. TryHackMe 平台
# ---------------------------------------------------------------------------
class TryHackMePlatform(CtfPlatform):
    """TryHackMe <https://tryhackme.com>`_ 平台提交器。"""

    async def submit_flag(self, flag: str, challenge_id: str | None = None) -> SubmitResult:
        """向 TryHackMe 提交 Flag。

        API v1 将 ``challenge_id`` 作为 ``room_code`` 或 ``task_id`` 透传。
        """
        payload: dict[str, Any] = {"flag": flag}
        if challenge_id:
            payload["challenge_id"] = challenge_id
        resp = await self._arequest("POST", "/api/v1/flag/submit", payload)

        if "error" in resp:
            return SubmitResult(success=False, error=resp["error"], platform="TryHackMe")

        msg = resp.get("message", "")
        correct = resp.get("correct", False) or "correct" in msg.lower()
        points = resp.get("points", 0)

        return SubmitResult(
            success=True,
            message=msg,
            platform="TryHackMe",
            correct=correct,
            points=points,
            challenge_id=challenge_id or "",
        )

    async def get_challenges(self) -> List[dict]:
        resp = await self._arequest("GET", "/api/v1/challenges")
        return resp if isinstance(resp, list) else resp.get("data", [])

    async def get_scoreboard(self) -> dict:
        return await self._arequest("GET", "/api/v1/scoreboard")


# ---------------------------------------------------------------------------
# 4. Root-Me 平台（手动提交提示）
# ---------------------------------------------------------------------------
class RootMePlatform(CtfPlatform):
    """Root-Me <https://root-me.org>`_ 平台提交器。

    .. note::
        Root-Me 需要浏览器登录及 CSRF 验证，本类仅返回手动提交提示。
    """

    async def submit_flag(self, flag: str, challenge_id: str | None = None) -> SubmitResult:
        """返回手动提交提示，不执行实际网络请求。"""
        return SubmitResult(
            success=True,
            message="Flag 提交需要手动完成，请访问网站提交",
            platform="Root-Me",
            correct=False,
            challenge_id=challenge_id or "",
        )

    async def get_challenges(self) -> List[dict]:
        return []

    async def get_scoreboard(self) -> dict:
        return {}


# ---------------------------------------------------------------------------
# 5. 手动提交平台
# ---------------------------------------------------------------------------
class ManualPlatform(CtfPlatform):
    """手动提交平台 —— 不自动发送网络请求，仅在 TUI 中显示 Flag 与目标地址。"""

    def __init__(
        self,
        base_url: str,
        api_key: str | None = None,
        auth_token: str | None = None,
    ) -> None:
        super().__init__(base_url=base_url, api_key=api_key, auth_token=auth_token)
        self.supports_submit = False

    async def submit_flag(self, flag: str, challenge_id: str | None = None) -> SubmitResult:
        """将 Flag 和提交地址组织为消息返回，供 TUI 展示。"""
        msg = f"Flag: {flag}，请手动提交到: {self.base_url}"
        if challenge_id:
            msg += f"（题目 ID: {challenge_id}）"
        return SubmitResult(
            success=True,
            message=msg,
            platform="Manual",
            correct=False,
            challenge_id=challenge_id or "",
        )

    async def get_challenges(self) -> List[dict]:
        return []

    async def get_scoreboard(self) -> dict:
        return {}


class ReadOnlyPlatform(ManualPlatform):
    """只读平台画像 —— 保留平台类型，但暂不执行自动提交。"""

    platform_name: str = "ReadOnly"

    async def submit_flag(self, flag: str, challenge_id: str | None = None) -> SubmitResult:
        msg = f"{self.platform_name} 当前仅支持平台画像与上下文对齐，请手动提交 Flag"
        if self.base_url:
            msg += f"：{self.base_url}"
        if challenge_id:
            msg += f"（题目 ID: {challenge_id}）"
        return SubmitResult(
            success=True,
            message=msg,
            platform=self.platform_name,
            correct=False,
            challenge_id=challenge_id or "",
        )


class BuuOJPlatform(ReadOnlyPlatform):
    """BUUOJ 平台画像适配器（只读）。"""

    platform_name = "BUUOJ"


class CTFShowPlatform(ReadOnlyPlatform):
    """CTFShow 平台画像适配器（只读）。"""

    platform_name = "CTFShow"


# ---------------------------------------------------------------------------
# 通用函数
# ---------------------------------------------------------------------------
_PLATFORM_MAP: dict[str, type[CtfPlatform]] = {
    "ctfd": CTFdPlatform,
    "htb": HTBPlatform,
    "hackthebox": HTBPlatform,
    "tryhackme": TryHackMePlatform,
    "thm": TryHackMePlatform,
    "rootme": RootMePlatform,
    "root-me": RootMePlatform,
    "buuoj": BuuOJPlatform,
    "ctfshow": CTFShowPlatform,
    "manual": ManualPlatform,
}


async def submit_flag(
    flag: str,
    platform_type: str = "manual",
    challenge_id: str | None = None,
    **kwargs: Any,
) -> SubmitResult:
    """通用 Flag 提交入口。

    根据 ``platform_type`` 自动实例化对应平台类并执行提交。

    Args:
        flag: 要提交的 Flag 字符串。
        platform_type: 平台类型标识，支持 ``"ctfd"``、``"htb"``、
            ``"tryhackme"``、``"rootme"``、``"manual"`` 及其别名。
        challenge_id: 目标题目 ID（CTFd/HTB 等平台需要）。
        **kwargs: 传递给平台构造器的参数，如 ``base_url``、``api_key``、
            ``auth_token``。

    Returns:
        SubmitResult: 统一结果对象，不会抛出异常。

    Example::

        result = await submit_flag(
            flag="flag{test}",
            platform_type="ctfd",
            challenge_id="12",
            base_url="https://ctf.example.com",
            auth_token="YOUR_TOKEN",
        )
    """
    key = platform_type.lower()
    cls = _PLATFORM_MAP.get(key)
    if cls is None:
        return SubmitResult(
            success=False,
            error=f"不支持的平台类型: {platform_type}",
            platform=platform_type,
        )

    try:
        instance = cls(
            base_url=kwargs.get("base_url", "https://ctf.example.com"),
            api_key=kwargs.get("api_key"),
            auth_token=kwargs.get("auth_token"),
        )
        return await instance.submit_flag(flag, challenge_id)
    except Exception as exc:
        return SubmitResult(success=False, error=str(exc), platform=platform_type)


def build_platform_client(
    platform_type: str = "manual",
    **kwargs: Any,
) -> CtfPlatform | None:
    """构造平台客户端实例，供平台感知层复用。"""
    key = str(platform_type or "manual").lower()
    cls = _PLATFORM_MAP.get(key)
    if cls is None:
        return None
    return cls(
        base_url=kwargs.get("base_url", "https://ctf.example.com"),
        api_key=kwargs.get("api_key"),
        auth_token=kwargs.get("auth_token"),
    )


async def get_platform_snapshot(
    platform_type: str = "manual",
    **kwargs: Any,
) -> dict[str, Any]:
    """抓取平台最小快照：题目数 / 计分板关键字段 / 是否可提交。"""
    client = build_platform_client(platform_type, **kwargs)
    if client is None:
        return {
            "success": False,
            "platform_type": platform_type,
            "error": f"不支持的平台类型: {platform_type}",
        }

    snapshot: dict[str, Any] = {
        "success": True,
        "platform_type": platform_type,
        "base_url": kwargs.get("base_url", ""),
        "supports_submit": bool(getattr(client, "supports_submit", str(platform_type).lower() != "manual")),
        "challenge_count": None,
        "scoreboard_keys": [],
        "challenge_briefs": [],
    }
    try:
        challenges = await client.get_challenges()
        if isinstance(challenges, list):
            snapshot["challenge_count"] = len(challenges)
            snapshot["challenge_briefs"] = [
                _normalize_challenge_brief(item) for item in challenges[:20]
            ]
    except Exception as exc:
        snapshot["challenge_error"] = str(exc)

    try:
        scoreboard = await client.get_scoreboard()
        if isinstance(scoreboard, dict):
            snapshot["scoreboard_keys"] = list(scoreboard.keys())[:8]
    except Exception as exc:
        snapshot["scoreboard_error"] = str(exc)

    return snapshot


def _normalize_challenge_brief(item: Any) -> dict[str, Any]:
    if not isinstance(item, dict):
        return {
            "id": "",
            "name": str(item),
            "category": "",
            "status": "",
            "solved": False,
            "raw": item,
        }

    challenge_id = (
        item.get("id")
        or item.get("challenge_id")
        or item.get("task_id")
        or item.get("room_code")
        or ""
    )
    name = (
        item.get("name")
        or item.get("title")
        or item.get("challenge")
        or item.get("slug")
        or ""
    )
    status = str(
        item.get("status")
        or item.get("state")
        or item.get("result")
        or ""
    )
    solved = bool(
        item.get("solved")
        or item.get("completed")
        or item.get("owned")
        or str(status).strip().lower() in {"solved", "completed", "owned", "correct"}
    )
    return {
        "id": str(challenge_id or ""),
        "name": str(name or ""),
        "category": str(item.get("category") or item.get("type") or ""),
        "status": status,
        "solved": solved,
        "url": str(item.get("url") or item.get("link") or ""),
        "raw": item,
    }


def detect_platform_from_url(url: str) -> str:
    """从 URL 自动检测平台类型。

    基于域名关键词进行启发式匹配，未识别时返回 ``"manual"``。

    Args:
        url: CTF 平台地址，如 ``"https://ctf.example.com"``。

    Returns:
        平台类型标识字符串。

    Example::

        >>> detect_platform_from_url("https://myctf.ctfd.io")
        'ctfd'
        >>> detect_platform_from_url("https://app.hackthebox.com")
        'htb'
    """
    url_lower = url.lower()
    if "ctfd" in url_lower:
        return "ctfd"
    if "buuoj" in url_lower:
        return "buuoj"
    if "ctf.show" in url_lower or "ctfshow" in url_lower:
        return "ctfshow"
    if "hackthebox" in url_lower or "htb" in url_lower:
        return "htb"
    if "tryhackme" in url_lower or "tryhackm" in url_lower:
        return "tryhackme"
    if "root-me" in url_lower or "rootme" in url_lower:
        return "rootme"
    return "manual"


def format_flag_result(result: SubmitResult) -> str:
    """将 ``SubmitResult`` 格式化为 TUI 可显示的单行字符串。

    Args:
        result: 提交结果对象。

    Returns:
        格式化后的中文字符串。

    Example::

        >>> r = SubmitResult(success=True, platform="CTFd", correct=True, points=100, rank=5, total_teams=50)
        >>> format_flag_result(r)
        '[CTFd] Flag正确! +100pts | 排名: 5/50'
    """
    if not result.success:
        return f"[{result.platform}] 提交失败: {result.error}"
    if result.correct:
        rank_str = f" | 排名: {result.rank}/{result.total_teams}" if result.rank else ""
        return f"[{result.platform}] Flag正确! +{result.points}pts{rank_str}"
    if result.platform in ("Root-Me", "Manual", "BUUOJ", "CTFShow"):
        return f"[{result.platform}] {result.message}"
    return f"[{result.platform}] Flag错误: {result.message}"


def load_platform_from_env() -> dict[str, str]:
    """从环境变量读取平台配置。

    支持的环境变量：

    - ``CPA_CTF_PLATFORM_TYPE`` — 平台类型（默认 ``"manual"``）
    - ``CPA_CTF_PLATFORM_URL``  — 平台地址（默认 ``""``）
    - ``CPA_CTF_API_KEY``       — API 密钥（可选）
    - ``CPA_CTF_AUTH_TOKEN``    — 认证令牌（可选）
    - ``CPA_CTF_AUTO_SUBMIT``   — 是否自动提交（默认 ``"false"``）

    Returns:
        包含上述键的配置字典。
    """
    return {
        "platform_type": os.environ.get("CPA_CTF_PLATFORM_TYPE", "manual"),
        "base_url": os.environ.get("CPA_CTF_PLATFORM_URL", ""),
        "api_key": os.environ.get("CPA_CTF_API_KEY", ""),
        "auth_token": os.environ.get("CPA_CTF_AUTH_TOKEN", ""),
        "auto_submit": os.environ.get("CPA_CTF_AUTO_SUBMIT", "false").lower(),
    }


# ---------------------------------------------------------------------------
# 便捷批量提交
# ---------------------------------------------------------------------------
async def submit_flags_batch(
    items: List[Dict[str, Any]], concurrency: int = 3
) -> List[SubmitResult]:
    """批量提交 Flag，限制并发数防止触发平台限流。

    Args:
        items: 每个元素为字典，键包括 ``flag``、``platform_type``、
            ``challenge_id`` 以及平台连接参数。
        concurrency: 最大并发提交数量。

    Returns:
        与 ``items`` 一一对应的 ``SubmitResult`` 列表。
    """
    semaphore = asyncio.Semaphore(concurrency)

    async def _submit(item: dict) -> SubmitResult:
        async with semaphore:
            return await submit_flag(
                flag=item["flag"],
                platform_type=item.get("platform_type", "manual"),
                challenge_id=item.get("challenge_id"),
                base_url=item.get("base_url", ""),
                api_key=item.get("api_key"),
                auth_token=item.get("auth_token"),
            )

    tasks = [_submit(item) for item in items]
    return await asyncio.gather(*tasks, return_exceptions=False)


if __name__ == "__main__":
    # 简单自测
    async def _self_test() -> None:
        r1 = await submit_flag("flag{test}", "manual", base_url="https://ctf.example.com")
        print(format_flag_result(r1))

        r2 = await submit_flag("flag{x}", "rootme", challenge_id="123")
        print(format_flag_result(r2))

        print("detect:", detect_platform_from_url("https://abc.ctfd.io"))

    asyncio.run(_self_test())
