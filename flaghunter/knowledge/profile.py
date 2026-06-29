"""Project-type profiles (P5 — 统一骨架 + profile 覆盖层).

不分三条线:CTF / 授权代码审计 / 攻防演练共用**同一条装配线**(coordinator 的
工序流水线 + solve 循环),差别仅"进场信息形态 + 工序取舍 + 停止准则 + 激进度"
这几个覆盖旋钮,收敛为一个声明式 ``Profile``。骨架不变,profile 只覆盖配置。

现状:``CTFTaskDispatcher.exploitation_mode`` 是这条 profile 轴的**雏形**,但生产
里 8 个构造点无一选择它(永远落默认 aggressive)。P5 把它升级为一等公民
``Profile`` + 选择机制,exploitation_mode 退化为 Profile 的一个字段(激进度)。

**诚实边界**:``code_audit`` profile 现为**声明式骨架** —— 它声明"进场=源码、
保守激进度、更紧停止预算",但框架当前**无白盒/源码审计能力**(全仓零 SAST/
source-review)。真白盒能力是能力波的活,不在 P5。P5 坐实的是**抽象 + 覆盖机制
+ 停止准则覆盖示范**,不假装能做代码审计。

分层(对标 ``kill_chain.py`` / ``blackboard_schema.py``):stdlib only,住在
CAPABILITY 层(``knowledge/``),故 ORCHESTRATION(agents)与 ENTRY(interface)
都可 import;**绝不 import ``agents/``**,守 I1。
"""

from __future__ import annotations

from dataclasses import dataclass, field

from .kill_chain import Phase


@dataclass(frozen=True)
class Profile:
    """A project-type overlay over the shared kill-chain skeleton.

    Frozen value object — profiles are constants selected at run start, not
    mutated. Every field is a *covering knob*; the skeleton (phases, contracts,
    chains) is identical across profiles.
    """

    name: str
    # 激进度: "aggressive" (CTF — 走最短链直接放 exploit payload) vs
    # "conservative" (审计/演练 — 先探针确认 vuln-class 再放具体 payload)。
    # 这是 dispatcher/executor 现已消费的具体 gate(ssti/hash exploitation)。
    exploitation_mode: str
    # 进场信息形态: "url" (CTF) / "source" (代码审计) / "blackbox" (攻防演练)。
    # 声明式 —— 告知 setup 阶段期望何种进场资产;消费由各阶段后续接线。
    entry_kind: str
    # 停止准则覆盖(P4): per-phase 轮次预算覆盖。空 dict → 回落 kill_chain 模块默认。
    phase_round_budgets: dict[str, int] = field(default_factory=dict)
    description: str = ""


# ── 注册表(先做 CTF + 代码审计两类坐实抽象;攻防演练随后)──────────────────

CTF = Profile(
    name="ctf",
    exploitation_mode="aggressive",
    entry_kind="url",
    phase_round_budgets={},  # 用 P4 模块默认预算(EXPLOIT=24);字节级一致于现状
    description="CTF 靶场:给 URL(有时源码),知道大致走向,激进走最短链直奔 flag。",
)

CODE_AUDIT = Profile(
    name="code_audit",
    exploitation_mode="conservative",
    entry_kind="source",
    # 审计取舍:更早收敛、留痕优先 → 比 CTF 更紧的 EXPLOIT 预算。
    phase_round_budgets={Phase.EXPLOIT: 12},
    description=(
        "授权代码审计(声明式骨架,框架暂无白盒能力):给源码,白盒优先、保守先确认,"
        "可疑点回灌线上验证。"
    ),
)

PROFILES: dict[str, Profile] = {p.name: p for p in (CTF, CODE_AUDIT)}

DEFAULT_PROFILE: str = CTF.name


def get_profile(name: str | None) -> Profile:
    """Resolve a profile by name. Unknown / blank → the default (CTF).

    Forgiving by design: an unrecognised ``--profile`` falls back to CTF rather
    than erroring, so a typo degrades to the byte-identical default behaviour.
    """
    key = str(name or "").strip().lower()
    return PROFILES.get(key, PROFILES[DEFAULT_PROFILE])


__all__ = [
    "Profile",
    "CTF",
    "CODE_AUDIT",
    "PROFILES",
    "DEFAULT_PROFILE",
    "get_profile",
]
