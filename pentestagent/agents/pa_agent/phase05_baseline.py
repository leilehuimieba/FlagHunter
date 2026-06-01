"""Phase 0.5 live-solve baseline registry.

This file backfills the "live solve proof" phase as executable repository state
instead of prose-only memory.  It records:

- which real challenge scenarios were used as baseline evidence
- what the earliest blocker was during live solving
- which planned phase owns that blocker
- whether the blocker has already been fixed or remains open
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Literal


BaselineStatus = Literal["fixed", "pending", "partial"]


@dataclass(frozen=True, slots=True)
class Phase05Blocker:
    slug: str
    summary: str
    root_cause: str
    mapped_phase: str
    status: BaselineStatus


@dataclass(frozen=True, slots=True)
class Phase05Evidence:
    acceptance_test: str
    expected_chain: list[str]
    expected_outcome: str
    proof_kind: Literal["real_flag", "earliest_blocker"]


@dataclass(frozen=True, slots=True)
class Phase05Scenario:
    slug: str
    challenge_name: str
    category: str
    source: str
    evidence: Phase05Evidence
    earliest_blocker: Phase05Blocker
    supporting_blockers: tuple[Phase05Blocker, ...] = field(default_factory=tuple)
    notes: tuple[str, ...] = field(default_factory=tuple)


PHASE05_SCENARIOS: tuple[Phase05Scenario, ...] = (
    Phase05Scenario(
        slug="buu_easy_sql_auth_form",
        challenge_name="[极客大挑战 2019]EasySQL",
        category="web/sqli",
        source="buuoj-live",
        evidence=Phase05Evidence(
            acceptance_test=(
                "tests/integration/test_ctf_dispatcher_acceptance.py::"
                "test_ctf_dispatcher_acceptance_solves_auth_form_sqli_via_http_fallback"
            ),
            expected_chain=["sqli"],
            expected_outcome="flag{acceptance_dispatcher_sqli_ok}",
            proof_kind="real_flag",
        ),
        earliest_blocker=Phase05Blocker(
            slug="auth_form_shortest_path_missing",
            summary="agent 能识别登录页，但没有稳定的 auth-form SQLi 最短执行链",
            root_cause=(
                "策略层缺少登录表单识别、GET/POST 自适应提交，以及 browserless HTTP fallback；"
                "导致遇到真实登录表单时无法形成闭环利用。"
            ),
            mapped_phase="Phase 5",
            status="fixed",
        ),
        supporting_blockers=(
            Phase05Blocker(
                slug="optional_tool_gate_blocked_shortest_path",
                summary="可选工具缺失会阻塞本可直接成功的最短链",
                root_cause="tool gating 以整条链静态 require，而不是 step-level require。",
                mapped_phase="Phase 5",
                status="fixed",
            ),
            Phase05Blocker(
                slug="state_was_implicit",
                summary="flag / artifact / wrong-flag 反馈分散在 notes 与局部变量中",
                root_cause="主循环缺少独立状态容器，恢复与回溯都依赖隐式上下文。",
                mapped_phase="Phase 1",
                status="fixed",
            ),
        ),
        notes=(
            "该题证明：不能只会分析页面，必须形成输入→提交→回显→flag 提取的最短执行闭环。",
            "该题同时证明：browser 缺失不能直接让 web 题解题能力瘫痪。",
        ),
    ),
    Phase05Scenario(
        slug="buu_php_source_leak_unserialize",
        challenge_name="[极客大挑战 2019]PHP",
        category="web/source-leak/php-object-injection",
        source="buuoj-live",
        evidence=Phase05Evidence(
            acceptance_test=(
                "tests/integration/test_ctf_dispatcher_php_object_injection_acceptance.py::"
                "test_ctf_dispatcher_acceptance_escalates_past_source_flag_to_runtime_flag"
            ),
            expected_chain=["web"],
            expected_outcome="flag{php_object_injection_runtime_ok}",
            proof_kind="real_flag",
        ),
        earliest_blocker=Phase05Blocker(
            slug="source_only_flag_false_stop",
            summary="源码泄露中的 decoy flag 会把 agent 提前误导到错误成功",
            root_cause=(
                "系统没有把 source-only / runtime / verified flag 分层，"
                "也没有独立 Verifier 对证据来源做升级判定。"
            ),
            mapped_phase="Phase 2",
            status="pending",
        ),
        supporting_blockers=(
            Phase05Blocker(
                slug="wrong_flag_feedback_not_structural",
                summary="用户反馈 flag 错误后，系统缺少统一拒绝与重新搜索机制",
                root_cause="wrong flag 反馈没有统一进入验证/恢复主干，只是局部补丁逻辑。",
                mapped_phase="Phase 3",
                status="partial",
            ),
            Phase05Blocker(
                slug="strategy_escalation_not_explicit",
                summary="从 backup/source leak 升级到 PHP unserialize runtime exploit 缺少显式策略层归属",
                root_cause="当前升级链主要堆在 dispatcher 中，还未进入 StrategyRegistry / HypothesisEngine。",
                mapped_phase="Phase 4",
                status="pending",
            ),
        ),
        notes=(
            "该题证明：候选 flag 不能直接等于成功，必须继续利用到 runtime 证据。",
            "该题也证明：wrong-flag 回退和恢复控制不是锦上添花，而是主干能力。",
        ),
    ),
    Phase05Scenario(
        slug="buu_unicorn_shop_unicode_numeric_form",
        challenge_name="[ASIS 2019]Unicorn shop",
        category="web/business-logic/unicode-numeric-bypass",
        source="buuoj-live",
        evidence=Phase05Evidence(
            acceptance_test=(
                "tests/integration/test_ctf_phase05_unicorn_shop_baseline.py::"
                "test_phase05_unicorn_shop_live_artifact_records_real_flag_proof"
            ),
            expected_chain=["web"],
            expected_outcome="flag{fab255a8-9c2c-4a51-b0b6-00ec1facd250}",
            proof_kind="real_flag",
        ),
        earliest_blocker=Phase05Blocker(
            slug="unicode_numeric_form_hypothesis_missing",
            summary="agent 曾经已看到 /charge 表单，但没有长出单字符 Unicode 数值绕过假设",
            root_cause=(
                "HypothesisEngine / StrategyRegistry 更偏向 backup/source-leak 等传统 web 路径；"
                "面对带 price 约束的业务表单时，没有生成 numeric constraint / unicode numeric bypass "
                "这一类最短执行假设，导致主路径被错误吸到 backup_source_leak。"
            ),
            mapped_phase="Phase 3",
            status="fixed",
        ),
        supporting_blockers=(
            Phase05Blocker(
                slug="recon_form_shape_not_preserved",
                summary="recon 阶段只保留 forms 数量，不保留表单细节，导致业务约束类假设无法稳定长出",
                root_cause=(
                    "live run 里 HypothesisEngine 需要看到 form action=/charge 与 id/price 字段组合，"
                    "但 phase_recon observation 之前只记录 forms=1；修复后保留 forms_detail / raw_links / content_preview。"
                ),
                mapped_phase="Phase 3",
                status="fixed",
            ),
            Phase05Blocker(
                slug="web_strategy_order_missed_business_form_path",
                summary="web 链缺少显式的 Unicode numeric 表单绕过策略入口，backup/source 路径会先吞掉执行机会",
                root_cause=(
                    "即使识别到购买表单，dispatcher 之前也没有最小 POST 探测链；"
                    "修复后新增 unicode_numeric_form_bypass strategy，并放到 backup_source_leak 前执行。"
                ),
                mapped_phase="Phase 4",
                status="fixed",
            ),
        ),
        notes=(
            "2026-05-25 复跑 live proof 已命中真实 flag，证明该能力缺口已经补上。",
            "该题证明：不是所有 web 题都应先走源码/备份路径，业务表单约束本身就可能是主漏洞面。",
            "当前 live 证据已固化在 reports/benchmarks/ctf_phase05_unicorn_shop_live.clean.json，可回放表单识别、baseline 请求与 Unicode payload 命中过程。",
        ),
    ),
)


def build_phase05_baseline() -> dict:
    scenarios = [asdict(item) for item in PHASE05_SCENARIOS]
    phase_status = {
        "Phase 0.5": "backfilled",
        "Phase 1": "completed",
        "Phase 2": "pending",
        "Phase 3": "pending",
        "Phase 4": "pending",
        "Phase 5": "partial",
        "Phase 6": "pending",
    }
    return {
        "schema_version": "1.0",
        "phase": "0.5",
        "summary": {
            "scenario_count": len(scenarios),
            "real_flag_proofs": sum(
                1 for scenario in PHASE05_SCENARIOS if scenario.evidence.proof_kind == "real_flag"
            ),
            "pending_blockers": sum(
                1
                for scenario in PHASE05_SCENARIOS
                if scenario.earliest_blocker.status != "fixed"
            ),
        },
        "phase_status": phase_status,
        "scenarios": scenarios,
    }


__all__ = [
    "PHASE05_SCENARIOS",
    "Phase05Blocker",
    "Phase05Evidence",
    "Phase05Scenario",
    "build_phase05_baseline",
]
