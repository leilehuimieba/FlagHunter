"""不变量 I5 守护测试：每个注册策略至少一条静态分发路径可达。

背景见 ``docs/dev/基准_CTF能力与可达性_2026-06-18_V1.md``。
「能力写好却够不着」是本项目反复出现的失败模式（历史：随便注 SQLi 解题器写好却被
分类够不着，6m27s 未解；P4：graphql/nosql 新策略未接分发）。本测试把它从「某道 live
题几分钟后才暴露」变成「CI 即红」。

可达性闭包（与基准 §3 一致，**只认两条静态保证**，不依赖运行时假设生成）：
一个策略可达 ⇔
  - ``chain_name == "*"``（全链兜底），或
  - ``kind ∈ web_strategy_order``（web 链按 kind 执行的桥接清单），或
  - ``chain_name ∈ detect_type 输出集``（专链可经 detect_type 进入）。

下面三个常量是上述代码事实的**镜像**。按基准 §6 维护规则：改了 detect_type 返回值 /
chains.web 的 web_strategy_order，必须同步这里并重跑本测试。
"""

from __future__ import annotations

from flaghunter.agents.pa_agent.strategy_registry import StrategyRegistry

# --- 可达链/桥接来源（镜像代码事实，带 file:line 指引） --------------------

#: ctf_planner.detect_type() 的全部 return 字面量（ctf_planner.py:341–377）。
#: 注意：从不返回 cmdi / graphql / nosql / web-legacy。
DETECT_TYPE_CHAINS = {"misc", "upload", "lfi", "ssrf", "xss", "sqli", "jwt", "web"}

#: chains/web.py:44–61 的 web_strategy_order —— web 链按 **kind** 逐个执行的清单。
#: （它是该方法内的局部变量，无法 import，故在此镜像；改动须同步。）
WEB_STRATEGY_ORDER = {
    "hint_chain_followup",
    "file_read_endpoint",
    "path_traversal",
    "hash_guarded_file_read",
    "hash_reconstruction_attack",
    "ssti_probe",
    "ssti_identify",
    "ssti_exploit",
    "unicode_numeric_form_bypass",
    "contact_report_chain",
    "backup_source_leak",
    "php_unserialize_magic_method",
    "generic_param_sqli",
    "jwt_manipulation",
    "generic_param_cmdi",
    "generic_param_ssrf",
    "graphql_introspection",
    "nosql_injection",
}

CATCH_ALL = "*"

# --- 隔离区（quarantine）：只能缩小，永不扩大 ------------------------------

#: 当前已确认的可达性缺口。本测试容忍它们，但任何**新增**不可达策略会 FAIL。
#: 修法见基准 §4.1：把策略名追加进 chains/web.py 的 web_strategy_order 末尾
#: （precondition 已门控，flag 才短路 ⇒ 零回归），修好后从本集合移除。
#: 2026-06-18：graphql_introspection / nosql_injection 已实现真实探测并桥接进
#: web_strategy_order（commit 见 git），缺口闭合，故本集合清空。
KNOWN_UNREACHABLE_GAPS: set[str] = set()

#: 疑似已退役（chain_name="web-legacy"，被三阶段 ssti_probe/identify/exploit 取代）。
#: 待确认意图后 @deprecated 或删除（基准 §4.2），届时从本集合移除。
LEGACY_RETIRED = {
    "ssti_via_render_parameter",
    "tornado_ssti",
}

QUARANTINE = KNOWN_UNREACHABLE_GAPS | LEGACY_RETIRED


def _registered_strategies() -> dict[str, str]:
    """返回 {kind: chain_name}，覆盖 build_default 注册的全部策略。"""
    registry = StrategyRegistry.build_default()
    # _strategies 是 registry 的权威存储（dict[kind -> StrategyDefinition]）。
    return {kind: defn.chain_name for kind, defn in registry._strategies.items()}


def _is_statically_reachable(kind: str, chain_name: str) -> bool:
    return (
        chain_name == CATCH_ALL
        or kind in WEB_STRATEGY_ORDER
        or chain_name in DETECT_TYPE_CHAINS
    )


def test_i5_every_registered_strategy_is_reachable_or_quarantined():
    """I5：每个注册策略要么静态可达，要么在显式隔离区里。"""
    strategies = _registered_strategies()
    assert strategies, "build_default 未注册任何策略——注册链路本身已坏"

    offenders: list[str] = []
    for kind, chain_name in sorted(strategies.items()):
        if _is_statically_reachable(kind, chain_name):
            continue
        if kind in QUARANTINE:
            continue
        offenders.append(f"{kind} (chain_name={chain_name!r})")

    assert not offenders, (
        "以下注册策略不可达，且不在隔离区——能力写好却够不着：\n  "
        + "\n  ".join(offenders)
        + "\n修法：把它接进分发（detect_type / 假设生成 / chains/web.py 的 "
        "web_strategy_order 之一），或带理由加入 KNOWN_UNREACHABLE_GAPS。"
        "详见 docs/dev/基准_CTF能力与可达性_2026-06-18_V1.md §4–§5。"
    )


def test_quarantine_entries_still_exist_and_still_unreachable():
    """隔离区卫生：防止 allowlist 腐烂——只能缩小，不能藏回归。

    - 若某隔离项已被接通（变可达）→ FAIL，提示从隔离区移除。
    - 若某隔离项已不再注册（被删除）→ FAIL，提示从隔离区移除。
    """
    strategies = _registered_strategies()

    now_reachable: list[str] = []
    no_longer_registered: list[str] = []
    for kind in sorted(QUARANTINE):
        chain_name = strategies.get(kind)
        if chain_name is None:
            no_longer_registered.append(kind)
            continue
        if _is_statically_reachable(kind, chain_name):
            now_reachable.append(kind)

    assert not now_reachable, (
        "以下策略已变为可达，请从隔离区（KNOWN_UNREACHABLE_GAPS / LEGACY_RETIRED）移除："
        f" {now_reachable}"
    )
    assert not no_longer_registered, (
        "以下策略已不再注册，请从隔离区移除其条目："
        f" {no_longer_registered}"
    )


def test_web_bridge_and_detect_type_constants_have_no_typos_against_registry():
    """轻量自检：web 桥接里"看起来像注册策略"的条目，名字应能在注册表中找到。

    web_strategy_order 可含非注册项（如 path_traversal 是假设 kind / 内联处理），
    故只对**已知是注册策略**的桥接名做拼写校验，避免桥接清单里把策略名打错导致
    "以为接了其实没接"。
    """
    strategies = _registered_strategies()
    registered_kinds = set(strategies)
    # 这些桥接项是注册策略，必须在注册表里拼写一致；path_traversal 等非注册项不校验。
    bridged_registered = WEB_STRATEGY_ORDER & {
        "hint_chain_followup",
        "file_read_endpoint",
        "hash_guarded_file_read",
        "hash_reconstruction_attack",
        "ssti_probe",
        "ssti_identify",
        "ssti_exploit",
        "unicode_numeric_form_bypass",
        "contact_report_chain",
        "backup_source_leak",
        "php_unserialize_magic_method",
        "generic_param_sqli",
        "jwt_manipulation",
        "generic_param_cmdi",
        "generic_param_ssrf",
        "graphql_introspection",
        "nosql_injection",
    }
    missing = sorted(bridged_registered - registered_kinds)
    assert not missing, (
        "web_strategy_order 桥接了这些名字，但注册表里没有同名策略（可能拼错或已删）："
        f" {missing}"
    )
