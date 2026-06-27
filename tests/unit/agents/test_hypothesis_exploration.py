"""N9 守护：主动探索（O1=C 之 C5）落在 hypothesis_engine 排序里。

钉死的契约（V3 §3.1-C5 / §10.6）：
  - 档1 常开：未试假设浮过**同等证据**的已试败者（修 _base_score 的 novelty
    平方衰减——历史里 ``novelty_bonus * 0.1`` 把加成压成 +0.01 纯噪声）。
  - 档2 卡死升级：随 state.no_progress_count 升级，卡死越久越偏好未试链，上限封顶。
  - **证据仍主导**（C5 从属于证据）：baseline 下高置信已试 > 低置信未试。
  - **证据地板仍生效**（不砸既有护栏）：无观察支持的未试假设即便被探索权重抬高，
    仍被 capped_ids 封到有观察者之后。
  - **C1 覆盖底线**：探索只重排，choose_chain_order 的链**集合**不随探索变（够得着
    的链终被外层循环遍历），只变顺序。
  - **纯确定性**：同 state 排两次结果一致（守护可复现，无 random）。
"""

from __future__ import annotations

from flaghunter.agents.pa_agent.ctf_state import CTFState, Experiment, Hypothesis
from flaghunter.agents.pa_agent.hypothesis_engine import (
    _EXPLORATION_BASE_WEIGHT,
    _EXPLORATION_STUCK_THRESHOLD,
    _EXPLORATION_WEIGHT_CAP,
    HypothesisEngine,
)


def _hyp(hid: str, kind: str, confidence: float, *, obs: list[str] | None = None) -> Hypothesis:
    return Hypothesis(
        id=hid,
        kind=kind,
        description=f"{kind} hypothesis",
        confidence=confidence,
        supporting_observations=list(obs or []),
    )


def _mark_tried(state: CTFState, hypothesis_id: str) -> None:
    state.experiments.append(
        Experiment(
            id=f"exp_{hypothesis_id}",
            hypothesis_id=hypothesis_id,
            action_type="probe",
            expected_signal="flag",
            status="completed",
        )
    )


def test_tier1_untried_floats_above_tried_at_equal_evidence():
    """档1：同等置信/证据下，未试假设排在已试败者之前（novelty 不再是噪声）。"""
    state = CTFState(target="http://t", goal="flag")
    tried = _hyp("h_tried", "lfi", 0.5)
    untried = _hyp("h_untried", "cmdi", 0.5)
    state.hypotheses = [tried, untried]
    _mark_tried(state, "h_tried")

    ranked = HypothesisEngine().rank(state)

    assert [h.id for h in ranked] == ["h_untried", "h_tried"]


def test_tier1_novelty_is_meaningful_not_hundredth_noise():
    """回归锁：未试加成等于 _EXPLORATION_BASE_WEIGHT（0.1），不是历史的 +0.01。"""
    state = CTFState(target="http://t", goal="flag")
    untried = _hyp("u", "cmdi", 0.5)
    tried = _hyp("t", "lfi", 0.5)
    state.hypotheses = [untried, tried]
    _mark_tried(state, "t")
    engine = HypothesisEngine()

    untried_score = engine._base_score(
        untried, max_obs=1, seen_experiments={"t"}, exploration_weight=_EXPLORATION_BASE_WEIGHT
    )
    tried_score = engine._base_score(
        tried, max_obs=1, seen_experiments={"t"}, exploration_weight=_EXPLORATION_BASE_WEIGHT
    )
    # 差值 = 整个 base weight（0.1），而非被 ×0.1 压成的 0.01
    assert round(untried_score - tried_score, 6) == _EXPLORATION_BASE_WEIGHT


def test_evidence_dominates_novelty_at_baseline():
    """C5 从属于证据：不卡死时高置信已试 > 低置信未试，探索不盖死证据。"""
    state = CTFState(target="http://t", goal="flag")
    strong_tried = _hyp("strong", "lfi", 1.0)
    weak_untried = _hyp("weak", "cmdi", 0.0)
    state.hypotheses = [weak_untried, strong_tried]
    _mark_tried(state, "strong")
    assert state.no_progress_count == 0

    ranked = HypothesisEngine().rank(state)

    assert ranked[0].id == "strong"


def test_tier2_exploration_weight_escalates_with_no_progress_then_caps():
    """档2：_exploration_weight 在阈值内常开、越阈线性递增、到上限封顶。确定性。"""
    engine = HypothesisEngine()
    state = CTFState(target="http://t", goal="flag")

    def weight_at(n: int) -> float:
        state.no_progress_count = n
        return engine._exploration_weight(state)

    # 阈值内 = 常开 base
    assert weight_at(0) == _EXPLORATION_BASE_WEIGHT
    assert weight_at(_EXPLORATION_STUCK_THRESHOLD - 1) == _EXPLORATION_BASE_WEIGHT
    # 越阈递增
    assert weight_at(_EXPLORATION_STUCK_THRESHOLD) > _EXPLORATION_BASE_WEIGHT
    assert weight_at(_EXPLORATION_STUCK_THRESHOLD + 1) > weight_at(_EXPLORATION_STUCK_THRESHOLD)
    # 单调不减
    assert weight_at(5) >= weight_at(4)
    # 上限封顶
    assert weight_at(100) == _EXPLORATION_WEIGHT_CAP
    # 确定性：同输入同输出
    assert weight_at(4) == weight_at(4)


def test_tier2_deep_stuck_flips_untried_over_tried_that_tier1_would_not():
    """档2 有牙齿：浅水（no_progress=0）证据主导，深卡死翻转到未试链。"""
    tried = _hyp("tried_strong", "lfi", 1.0)        # base 0.6
    untried = _hyp("untried_mid", "cmdi", 0.4)      # base 0.24 + novelty

    def rank_ids(no_progress: int) -> list[str]:
        state = CTFState(target="http://t", goal="flag")
        state.hypotheses = [
            _hyp("tried_strong", "lfi", 1.0),
            _hyp("untried_mid", "cmdi", 0.4),
        ]
        _mark_tried(state, "tried_strong")
        state.no_progress_count = no_progress
        return [h.id for h in HypothesisEngine().rank(state)]

    # 不卡死：证据主导，已试强假设在前
    assert rank_ids(0)[0] == "tried_strong"
    # 深度卡死：探索升级翻转到未试链
    assert rank_ids(10)[0] == "untried_mid"


def test_evidence_floor_still_caps_novelty_inflated_no_obs_hypothesis():
    """既有护栏不被砸：无观察支持的未试假设即便深卡死被抬高，仍被证据地板封到有观察者之后。"""
    state = CTFState(target="http://t", goal="flag")
    # 有观察支持者（地板设定者）
    grounded = _hyp("grounded", "lfi", 0.3, obs=["obs1"])
    # 无观察、高置信、未试——深卡死下探索权重最大
    floaty = _hyp("floaty", "cmdi", 0.9)
    state.hypotheses = [grounded, floaty]
    state.no_progress_count = 100  # 探索权重拉满

    ranked = HypothesisEngine().rank(state)

    # floaty 的 raw 分高，但无观察支持 → capped_ids 把它压到有观察的 grounded 之后
    assert [h.id for h in ranked] == ["grounded", "floaty"]


def test_c1_coverage_chain_set_invariant_under_exploration():
    """C1 覆盖底线：探索只改顺序，choose_chain_order 的链集合不随 no_progress 变。"""
    def chain_set(no_progress: int) -> set[str]:
        state = CTFState(target="http://t", goal="flag", detected_type="web")
        state.hypotheses = [
            _hyp("a", "lfi", 0.6),
            _hyp("b", "cmdi", 0.5),
            _hyp("c", "ssrf", 0.4),
        ]
        _mark_tried(state, "a")
        state.no_progress_count = no_progress
        return set(HypothesisEngine().choose_chain_order(state))

    calm = chain_set(0)
    stuck = chain_set(50)
    # 够得着的链集合恒定（只重排不删/增）——外层 while chain_order 仍遍历全集
    assert calm == stuck
    assert {"lfi", "cmdi", "ssrf", "web"} <= calm


def test_ranking_is_deterministic():
    """守护可复现：同一 state 连排两次结果字节级一致（无 random）。"""
    state = CTFState(target="http://t", goal="flag")
    state.hypotheses = [
        _hyp("a", "lfi", 0.7),
        _hyp("b", "cmdi", 0.5),
        _hyp("c", "ssrf", 0.5),
    ]
    _mark_tried(state, "a")
    state.no_progress_count = 4

    first = [h.id for h in HypothesisEngine().rank(state)]
    second = [h.id for h in HypothesisEngine().rank(state)]
    assert first == second
