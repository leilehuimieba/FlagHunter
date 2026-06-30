"""Rule-first hypothesis engine for CTF execution."""

from __future__ import annotations

from typing import Iterable
from urllib.parse import parse_qs, urlparse

from .ctf_state import CTFState, Experiment, FlagProof, Hypothesis


# N9 主动探索（O1=C 之 C5，V3 §3.1 / §10.6）：novelty 加成的常开权重 + 卡死升级。
# 历史 bug（§10.6 点名）：_base_score 里 ``novelty_bonus * 0.1`` 把"未试假设"加成
# 压成最多 +0.01，在 ``confidence × 0.6`` 面前纯噪声 → 等于没有主动探索。
# N9 改为**有意义但从属于证据**的加成：常开 base 让未试假设浮过同等证据的已试败者；
# 随 ``state.no_progress_count`` 升级，卡死越久越偏好未试链（§10.6 "N 轮无进展强制
# novelty 链"）。**纯确定性**（无 random，守护可复现，项目禁不确定性）。**只重排不删**：
# 本权重不改 choose_chain_order 的链**集合**（C1 覆盖底线由外层 ``while chain_order``
# 循环保证够得着的链终被遍历），只改**顺序**；证据地板 capped_ids（rank:107）仍封顶
# 无观察支持的假设——探索在护栏允许的范围内重排，不砸经验/证据护栏。
_EXPLORATION_BASE_WEIGHT = 0.1       # 档1 常开（同等证据下未试 > 已试败）
_EXPLORATION_STUCK_THRESHOLD = 3     # 档2 触发阈值（对齐 recovery._agenda_trigger_threshold 默认）
_EXPLORATION_STUCK_STEP = 0.1        # 每多卡 1 轮的递增
_EXPLORATION_WEIGHT_CAP = 0.5        # 上限（有界，配合证据地板不致盖死高置信证据）


# Single source of truth for hypothesis-kind → chain routing. Consumed both
# here (generation-time chain ordering, choose_chain_order) and in
# ctf_dispatcher as _CHAIN_NAME_FOR_HYPOTHESIS (solve-time reverse lookup,
# _select_hypothesis_for_chain). Do NOT fork a second copy — the two used to
# drift (dispatcher map lacked jwt_manipulation, so the jwt chain could never
# select its own hypothesis).
_CHAIN_BY_KIND = {
    "llm_driven_exploration": "web",
    "artifact_forensics": "misc",
    "auth_form_sqli": "sqli",
    "generic_param_sqli": "sqli",
    "backup_source_leak": "web",
    "contact_report_chain": "web",
    "unicode_numeric_form_bypass": "web",
    "php_unserialize_magic_method": "web",
    "insecure_deserialization": "web",
    "xss_admin_bot_sid": "xss",
    "lfi": "lfi",
    "cmdi": "cmdi",
    "ssrf": "ssrf",
    "upload": "upload",
    "generic_web_recon": "web",
    # 结构感知假设 → web 链（Phase 0.5 易_tornado 补全）
    "hint_chain_followup": "web",
    "file_read_endpoint": "web",
    "path_traversal": "web",
    "hash_guarded_file_read": "web",
    "hash_reconstruction_attack": "web",
    "ssti_via_render_parameter": "web",
    "tornado_ssti": "web",
    # Phase 7 §5: 三阶段 SSTI 管道
    "ssti_probe": "web",
    "ssti_identify": "web",
    "ssti_exploit": "web",
    # P4: New strategies
    "jwt_manipulation": "jwt",
    # graphql/nosql run as web-chain strategies (see chains/web.py
    # web_strategy_order + 基准_CTF能力与可达性 §3.3/§4), not standalone chains.
    # These two kinds are currently never generated (基准 §3.2), so the bare
    # "graphql"/"nosql" chain names this map used to emit were a latent dead
    # mapping — the exact "_CHAIN_BY_KIND has a kind ≠ it's reachable" landmine
    # 基准 §1 flags as the top false-positive trap: if either kind ever gets a
    # generation point, emitting "graphql"/"nosql" would miss _chain_handler_map
    # and fall through to the robots.txt default handler. Map onto "web" so the
    # mapping matches where the strategy actually runs.
    "graphql_introspection": "web",
    "nosql_injection": "web",
    # XXE runs as a web-chain strategy (chains/web.py WEB_STRATEGY_ORDER), like
    # graphql/nosql/insecure_deserialization — not a standalone chain.
    "xxe_injection": "web",
    # Reflected XSS runs as a web-chain strategy too (client-side injection
    # primitive), not a standalone chain — see chains/web.py WEB_STRATEGY_ORDER.
    "reflected_xss": "web",
    # IDOR / open redirect run as web-chain strategies as well (authorization /
    # client-side redirect primitives) — see chains/web.py WEB_STRATEGY_ORDER.
    "idor_sequential": "web",
    "open_redirect": "web",
}


class HypothesisEngine:
    def generate(self, state: CTFState) -> list[Hypothesis]:
        hypotheses = self._rule_based_hypotheses(state)
        self._upsert_hypothesis(
            hypotheses,
            self._llm_driven_exploration_hypothesis(hypotheses),
        )
        if len(hypotheses) < 2:
            hypotheses.extend(self._llm_placeholder_hypotheses(state, hypotheses))

        ranked = self.rank(state, hypotheses)
        state.hypotheses = ranked
        return ranked

    def rank(self, state: CTFState, hypotheses: Iterable[Hypothesis] | None = None) -> list[Hypothesis]:
        items = list(hypotheses if hypotheses is not None else state.hypotheses)
        if not items:
            return []

        max_obs = max(1, len(state.observations) + len(state.artifacts))
        seen_experiments = {exp.hypothesis_id for exp in state.experiments}
        exploration_weight = self._exploration_weight(state)
        base_scores = {
            hypothesis.id: self._base_score(
                hypothesis,
                max_obs=max_obs,
                seen_experiments=seen_experiments,
                exploration_weight=exploration_weight,
            )
            for hypothesis in items
        }
        obs_supported_scores = [
            base_scores[hypothesis.id]
            for hypothesis in items
            if hypothesis.supporting_observations
        ]
        max_obs_score = max(obs_supported_scores) if obs_supported_scores else None

        final_scores: dict[str, float] = {}
        capped_ids: set[str] = set()
        for hypothesis in items:
            effective_memory = self._effective_memory_adjustment(
                state,
                hypothesis=hypothesis,
                base_score=base_scores[hypothesis.id],
                max_obs_score=max_obs_score,
            )
            final_scores[hypothesis.id] = base_scores[hypothesis.id] + effective_memory

        if obs_supported_scores:
            floor_score = max(
                final_scores[hypothesis.id]
                for hypothesis in items
                if hypothesis.supporting_observations
            )
            for hypothesis in items:
                if hypothesis.supporting_observations:
                    continue
                if final_scores[hypothesis.id] > floor_score:
                    capped_ids.add(hypothesis.id)

        return sorted(
            items,
            key=lambda hypothesis: (
                hypothesis.kind == "llm_driven_exploration",
                hypothesis.id in capped_ids,
                -final_scores[hypothesis.id],
                hypothesis.kind,
            ),
        )

    def choose_chain_order(self, state: CTFState) -> list[str]:
        ranked = self.generate(state) if not state.hypotheses else self.rank(state)
        chain_order: list[str] = []
        detected = str(state.detected_type or "").strip().lower()
        normalized_detected = "cmdi" if detected == "cmd" else detected
        if normalized_detected and normalized_detected not in {"", "auto", "web"}:
            chain_order.append(normalized_detected)

        for hypothesis in ranked:
            chain = _CHAIN_BY_KIND.get(hypothesis.kind)
            if chain and chain not in chain_order:
                chain_order.append(chain)

        if normalized_detected and normalized_detected not in chain_order and normalized_detected != "auto":
            chain_order.append(normalized_detected)

        if "web" not in chain_order:
            chain_order.append("web")
        return chain_order

    def record_experiment_feedback(
        self,
        state: CTFState,
        *,
        hypothesis_id: str,
        progress_delta: str,
        observed_signal: str | None = None,
        experiment_id: str | None = None,
        inputs: dict | None = None,
        expected_signal: str | None = None,
    ) -> None:
        hypothesis = self._find_hypothesis(state, hypothesis_id)
        if hypothesis is None:
            return

        experiment = self._find_experiment(state, experiment_id) if experiment_id else None
        if experiment is None:
            experiment = Experiment(
                id=experiment_id or f"exp_{len(state.experiments) + 1}",
                hypothesis_id=hypothesis_id,
                action_type=hypothesis.kind,
                inputs=dict(inputs or {}),
                expected_signal=expected_signal or "flag or progress",
                observed_signal=observed_signal,
                progress_delta=progress_delta,  # type: ignore[arg-type]
                status="completed",
            )
            state.experiments.append(experiment)
        else:
            if inputs:
                experiment.inputs.update(dict(inputs))
            if expected_signal:
                experiment.expected_signal = expected_signal
            experiment.observed_signal = observed_signal
            experiment.progress_delta = progress_delta  # type: ignore[assignment]
            experiment.status = "completed"

        if progress_delta == "terminal":
            hypothesis.confidence = 1.0
            hypothesis.status = "supported"
            return

        if progress_delta == "strong":
            hypothesis.confidence = min(1.0, hypothesis.confidence + 0.2)
            hypothesis.status = "active"
            return

        if progress_delta == "weak":
            hypothesis.confidence = min(1.0, hypothesis.confidence + 0.05)
            hypothesis.status = "active"
            return

        if progress_delta == "none":
            hypothesis.confidence = max(0.0, hypothesis.confidence - 0.15)
            counter_signal = "none"
            observed_lower = str(observed_signal or "").lower()
            if any(
                marker in observed_lower
                for marker in (
                    "uniform blocked responses",
                    "blocked surface",
                    "uniform failure",
                    "orz",
                )
            ):
                counter_signal = "uniform_failure_surface"
                hypothesis.confidence = max(0.0, hypothesis.confidence - 0.1)
            hypothesis.counter_evidence.append(counter_signal)
            if (
                hypothesis.counter_evidence.count("none") >= 3
                and not hypothesis.next_experiments
                and hypothesis.confidence < 0.15
            ):
                hypothesis.status = "exhausted"
            return

        if progress_delta == "rejected":
            observed_lower = str(observed_signal or "").lower()
            if any(
                marker in observed_lower
                for marker in (
                    "uniform blocked responses",
                    "blocked surface",
                    "uniform failure",
                    "orz",
                )
            ):
                hypothesis.counter_evidence.append("uniform_failure_surface")
                hypothesis.confidence = min(hypothesis.confidence, 0.08)
                # Don't exhaust on the *first* blocking signal alone — require
                # at least two separate "uniform_failure_surface" entries so
                # that a hypothesis is not killed by a single sibling strategy
                # hitting a WAF/filter while the chain's other strategies still
                # have unexplored paths.
                if hypothesis.counter_evidence.count("uniform_failure_surface") >= 2:
                    hypothesis.status = "exhausted"
                return
            hypothesis.confidence = 0.0
            hypothesis.status = "rejected"

    def apply_wrong_flag_feedback(
        self,
        state: CTFState,
        *,
        flag: str,
        rationale: str = "",
        proof: FlagProof | None = None,
    ) -> None:
        target_keys = [
            str(getattr(proof, "hypothesis_id", "") or "").strip(),
            str(getattr(proof, "strategy_kind", "") or "").strip(),
        ]
        target_keys = [item for item in target_keys if item]
        if not target_keys:
            return

        for hypothesis in state.hypotheses:
            if hypothesis.id not in target_keys and hypothesis.kind not in target_keys:
                continue
            hypothesis.confidence = max(0.0, float(hypothesis.confidence) - 0.35)
            marker = f"wrong_flag:{str(flag or '').strip()}"
            if marker not in hypothesis.counter_evidence:
                hypothesis.counter_evidence.append(marker)
            if rationale:
                rationale_marker = f"wrong_flag_rationale:{str(rationale).strip()}"
                if rationale_marker not in hypothesis.counter_evidence:
                    hypothesis.counter_evidence.append(rationale_marker)

        for key in target_keys:
            current = float(state.hypothesis_memory_adjustments.get(key, 0.0))
            state.hypothesis_memory_adjustments[key] = min(current, -0.2)

        state.meta_reasonings.append(
            {
                "type": "hypothesis_wrong_flag_feedback",
                "flag": str(flag or "").strip(),
                "rationale": str(rationale or "").strip(),
                "proof_strategy_kind": getattr(proof, "strategy_kind", None),
                "proof_hypothesis_id": getattr(proof, "hypothesis_id", None),
                "proof_evidence_source": getattr(proof, "evidence_source", None),
                "adjusted_keys": target_keys,
            }
        )

    def update_after_chain(
        self,
        state: CTFState,
        *,
        observed_signal: str | None,
    ) -> list[Hypothesis]:
        """Phase 7 §1: 链路结束后检查每个活跃假设的 abort_condition。

        若 observed_signal 满足 abort_condition（Devil's Advocate 提前剪枝），
        直接将该假设标记为 exhausted，跳过第二次等待。

        返回被提前终止的假设列表（用于日志和测试验证）。
        """
        aborted: list[Hypothesis] = []
        for hyp in state.hypotheses:
            if hyp.status not in ("active",):
                continue
            if not hyp.abort_condition:
                continue
            if self._abort_condition_matches(hyp, state, observed_signal):
                hyp.status = "exhausted"
                hyp.confidence = 0.0
                aborted.append(hyp)
        return aborted

    def _abort_condition_matches(
        self,
        hyp: "Hypothesis",
        state: CTFState,
        observed_signal: str | None,
    ) -> bool:
        """检测 hyp.abort_condition 是否被当前 counter_evidence 或 observed_signal 满足。"""
        cond = str(hyp.abort_condition or "").strip().lower()
        if not cond:
            return False

        # "uniform_failure_surface × N" → 计 counter_evidence 中已有多少次
        if "uniform_failure_surface" in cond:
            # 提取阈值：× 后面的数字，默认 2
            threshold = 2
            for part in cond.split("×"):
                candidate = part.strip()
                if candidate.isdigit():
                    threshold = int(candidate)
                    break
            return hyp.counter_evidence.count("uniform_failure_surface") >= threshold

        # 通用字符串匹配：检查 observed_signal 是否包含条件文本
        observed_lower = str(observed_signal or "").lower()
        return cond in observed_lower

    def _rule_based_hypotheses(self, state: CTFState) -> list[Hypothesis]:
        hypotheses: list[Hypothesis] = []
        kind = str(state.detected_type or "").strip().lower()
        endpoint_blob = self._endpoint_blob(state)
        source_hint_blob = "\n".join(
            str(obs.value or "")
            for obs in state.observations
            if str(getattr(obs, "kind", "") or "").strip() == "local_challenge_source_hint"
        ).lower()
        has_visit = "/visit" in endpoint_blob or "/visit" in source_hint_blob
        has_admin = "/admin" in endpoint_blob or "/admin" in source_hint_blob
        has_backup = self._has_backup_artifact(state)
        has_login_form = any(
            (
                "username" in obs.value.lower()
                and "password" in obs.value.lower()
                for obs in state.observations
            )
        )

        if kind == "sqli":
            has_sql_error_signal = self._has_sql_error_signal(state)
            has_login_form = self._has_login_form(state)
            has_generic_get_sqli_surface = self._has_generic_get_sqli_surface(state)

            if has_login_form or not has_generic_get_sqli_surface:
                self._upsert_hypothesis(
                    hypotheses,
                    self._hypothesis(
                        "auth_form_sqli",
                        "auth_form_sqli",
                        0.82 if has_login_form else 0.62,
                        ["detected_type:sqli"],
                        ["submit auth form with SQLi bypass"],
                    )
                )

            if has_generic_get_sqli_surface:
                supports = ["detected_type:sqli", "surface:get_form_param"]
                if has_sql_error_signal:
                    supports.append("error:sql_error")
                self._upsert_hypothesis(
                    hypotheses,
                    self._hypothesis(
                        "generic_param_sqli",
                        "generic_param_sqli",
                        0.84 if has_sql_error_signal else 0.74,
                        supports,
                        ["probe GET parameter with quote payload and stacked-query follow-up"],
                    )
                )

        if kind == "xss" or (has_visit and has_admin):
            self._upsert_hypothesis(
                hypotheses,
                self._hypothesis(
                    "xss_admin_bot_sid",
                    "xss_admin_bot_sid",
                    0.78 if has_visit and has_admin else 0.6,
                    [
                        "endpoints:/visit+/admin" if has_visit and has_admin else "detected_type:web",
                        "login-like flow" if has_login_form else "browser-rendered evidence",
                    ],
                    ["payload -> /visit -> sid -> /admin"],
                )
            )

        if kind == "lfi":
            self._upsert_hypothesis(
                hypotheses,
                self._hypothesis(
                    "lfi",
                    "lfi",
                    0.75,
                    ["detected_type:lfi"],
                    ["enumerate file parameters"],
                )
            )

        if kind in {"cmdi", "cmd"}:
            self._upsert_hypothesis(
                hypotheses,
                self._hypothesis(
                    "cmdi",
                    "cmdi",
                    0.74,
                    ["detected_type:cmdi"],
                    ["try shell metacharacters"],
                )
            )

        if kind == "ssrf":
            self._upsert_hypothesis(
                hypotheses,
                self._hypothesis(
                    "ssrf",
                    "ssrf",
                    0.74,
                    ["detected_type:ssrf"],
                    ["probe localhost and file:// targets"],
                )
            )

        if kind == "upload":
            self._upsert_hypothesis(
                hypotheses,
                self._hypothesis(
                    "upload",
                    "upload",
                    0.76,
                    ["detected_type:upload"],
                    ["probe upload extension filtering"],
                )
            )

        if kind == "misc" or self._has_attachment_artifact(state):
            self._upsert_hypothesis(
                hypotheses,
                self._hypothesis(
                    "artifact_forensics",
                    "artifact_forensics",
                    0.8 if self._has_attachment_artifact(state) else 0.62,
                    ["detected_type:misc" if kind == "misc" else "attachment artifact discovered"],
                    ["download candidate artifacts, extract metadata, recover text fragments, decode or re-rank"],
                )
            )

        if has_backup or any(
            kw in self._observation_blob(state)
            for kw in ("backup", "压缩包", "source code", ".zip", ".bak", "源码")
        ):
            backup_confidence = 0.83
            if self._backup_clue_is_false(state) and not has_backup:
                backup_confidence = min(backup_confidence, 0.2)
            self._upsert_hypothesis(
                hypotheses,
                self._hypothesis(
                    "backup_source_leak",
                    "backup_source_leak",
                    backup_confidence,
                    ["backup/source clue", "artifact/source leak"],
                    ["fetch backup archive, inspect source, then re-verify runtime"],
                )
            )

        if "unserialize" in self._observation_blob(state) and "__destruct" in self._observation_blob(state):
            self._upsert_hypothesis(
                hypotheses,
                self._hypothesis(
                    "php_unserialize_magic_method",
                    "php_unserialize_magic_method",
                    0.8,
                    ["source contains unserialize + magic method"],
                    ["build serialized object payload"],
                )
            )

        # Phase 7 §1: structural_rules 扩展为 6 元组，第 6 项为 abort_condition（可为 None）
        structural_rules: list[tuple[bool, str, float, list[str], list[str], str | None]] = [
            (
                self._has_unicode_numeric_form_surface(state),
                "unicode_numeric_form_bypass",
                0.78,
                ["single-char price form", "unicode numeric business flow"],
                ["submit high-value item with single-character Unicode numeric payload"],
                "uniform_failure_surface × 2",
            ),
            (
                self._has_file_and_hash_param(state),
                "hash_guarded_file_read",
                0.6,
                ["url params: filename+filehash"],
                ["reconstruct or bypass filehash guard"],
                "uniform_failure_surface × 1",  # 一次 WAF 命中即放弃
            ),
            (
                self._has_file_and_hash_param(state),
                "hash_reconstruction_attack",
                0.55,
                ["url params: filename+filehash"],
                ["derive the hash algorithm and fetch hinted files"],
                "uniform_failure_surface × 1",
            ),
            (
                self._has_tornado_feature(state),
                "tornado_ssti",
                0.55,
                ["tornado runtime clue"],
                ["probe SSTI with Tornado template expressions"],
                "uniform_failure_surface × 2",
            ),
            (
                self._has_hint_files(state),
                "hint_chain_followup",
                0.65,
                ["hint files discovered"],
                ["read hinted files before switching hypotheses"],
                None,  # 不预设中止条件
            ),
            (
                self._has_render_param(state),
                "ssti_via_render_parameter",
                0.6,
                ["render/template parameter surface"],
                ["mutate render-like parameter and inspect template output"],
                "uniform_failure_surface × 2",
            ),
            (
                self._has_jwt_surface(state),
                "jwt_manipulation",
                0.68,
                ["authorization bearer surface", "jwt secret or admin-token clue"],
                ["mutate bearer token with admin claims and leaked secret candidates"],
                "uniform_failure_surface × 2",
            ),
            (
                self._has_file_endpoint(state),
                "path_traversal",
                0.5,
                ["file/download endpoint discovered"],
                ["test path traversal against file endpoint"],
                "uniform_failure_surface × 2",
            ),
            (
                self._has_file_endpoint(state),
                "file_read_endpoint",
                0.5,
                ["file/download endpoint discovered"],
                ["read local challenge files through the endpoint"],
                "uniform_failure_surface × 2",
            ),
        ]
        for enabled, hypothesis_kind, confidence, supports, next_steps, abort_cond in structural_rules:
            if not enabled:
                continue
            self._upsert_hypothesis(
                hypotheses,
                self._hypothesis(
                    hypothesis_kind,
                    hypothesis_kind,
                    confidence,
                    supports,
                    next_steps,
                    abort_condition=abort_cond,
                ),
            )

        self._apply_uniform_failure_counterevidence(state, hypotheses)

        # 注:曲库 miss 一等信号(``CTFState.repertoire_miss``)**不**在这里按
        # ``not hypotheses`` 计算——那个定义在真实 web 解题路径上恒 False:recon 会主动
        # 探 /www.zip、/.git 等备份路径并记进 endpoint_blob,使 backup_source_leak 的松门控
        # (_has_backup_artifact)恒真 ⇒ 任意 web 题几乎必产 ≥1 条 baseline 假设 ⇒ 永不为空。
        # 改用「give-up 点法」:终局收敛停且未拿到 flag 时置位,见 recovery.finalize()。
        if not hypotheses:
            self._upsert_hypothesis(
                hypotheses,
                self._hypothesis(
                    "generic_web_recon",
                    "generic_web_recon",
                    0.35,
                    ["fallback:web"],
                    ["recon source, HTML, scripts, routes"],
                )
            )

        return hypotheses

    def _llm_placeholder_hypotheses(
        self, state: CTFState, existing: list[Hypothesis]
    ) -> list[Hypothesis]:
        # Phase 3 keeps the door open for future LLM expansion, but this repo
        # currently stays deterministic. Provide a second fallback hypothesis so
        # ordering logic always has at least two candidates.
        if len(existing) >= 2:
            return []
        fallback = Hypothesis(
            id="generic_web_recon",
            kind="generic_web_recon",
            description="Deterministic fallback recon hypothesis.",
            confidence=0.3,
            status="active",
            supporting_observations=["deterministic fallback"],
            counter_evidence=[],
            next_experiments=["recon page source"],
        )
        if any(item.id == fallback.id for item in existing):
            return []
        return [fallback]

    def _llm_driven_exploration_hypothesis(
        self,
        existing: list[Hypothesis],
    ) -> Hypothesis:
        other_hypotheses = [
            hypothesis
            for hypothesis in existing
            if hypothesis.kind != "llm_driven_exploration"
            and hypothesis.status not in {"rejected", "exhausted"}
        ]
        confidence = 0.55 if not other_hypotheses else 0.15
        return Hypothesis(
            id="llm_driven_exploration",
            kind="llm_driven_exploration",
            description="LLM-driven fallback exploration hypothesis.",
            confidence=confidence,
            status="active",
            supporting_observations=["fallback:llm"] if not other_hypotheses else [],
            counter_evidence=[],
            next_experiments=["ask llm for next action under reasoning guardrails"],
        )

    def _hypothesis(
        self,
        hypothesis_id: str,
        kind: str,
        confidence: float,
        supporting_observations: list[str],
        next_experiments: list[str],
        *,
        abort_condition: str | None = None,
        fallback_plan: str | None = None,
        value_score: float = 0.5,
    ) -> Hypothesis:
        return Hypothesis(
            id=hypothesis_id,
            kind=kind,
            description=f"Generated {kind} hypothesis",
            confidence=confidence,
            status="active",
            supporting_observations=supporting_observations,
            counter_evidence=[],
            next_experiments=next_experiments,
            abort_condition=abort_condition,
            fallback_plan=fallback_plan,
            value_score=value_score,
        )

    def _upsert_hypothesis(self, hypotheses: list[Hypothesis], candidate: Hypothesis) -> None:
        for existing in hypotheses:
            if existing.kind != candidate.kind:
                continue
            existing.confidence = max(existing.confidence, candidate.confidence)
            for support in candidate.supporting_observations:
                if support not in existing.supporting_observations:
                    existing.supporting_observations.append(support)
            for next_step in candidate.next_experiments:
                if next_step not in existing.next_experiments:
                    existing.next_experiments.append(next_step)
            return
        hypotheses.append(candidate)

    def _exploration_weight(self, state: CTFState) -> float:
        """N9 主动探索权重（O1=C·C5）：常开 base + 卡死递增，上限封顶。纯确定性。

        ``state.no_progress_count`` 是活信号（CTFState.mark_no_progress 维护）。
        阈值内返回常开权重（档1），越过阈值后每多卡 1 轮线性递增（档2），到上限封顶。
        """
        no_progress = max(0, int(getattr(state, "no_progress_count", 0) or 0))
        stuck_over = max(0, no_progress - _EXPLORATION_STUCK_THRESHOLD + 1)
        weight = _EXPLORATION_BASE_WEIGHT + _EXPLORATION_STUCK_STEP * stuck_over
        return min(_EXPLORATION_WEIGHT_CAP, weight)

    def _base_score(
        self,
        hypothesis: Hypothesis,
        *,
        max_obs: int,
        seen_experiments: set[str],
        exploration_weight: float = _EXPLORATION_BASE_WEIGHT,
    ) -> float:
        confidence = max(0.0, min(1.0, float(hypothesis.confidence)))
        if hypothesis.kind == "llm_driven_exploration":
            return confidence
        support_score = min(1.0, len(hypothesis.supporting_observations) / max_obs)
        # N9: 未试假设拿 exploration_weight（档1 常开 + 档2 卡死升级），已试拿 0。
        # 加成有意义但从属于证据（confidence×0.6 主导 + 证据地板 capped_ids 封顶
        # 无观察假设），且只影响排序不改链集合（C1 覆盖底线见模块常量注释）。
        novelty_bonus = exploration_weight if hypothesis.id not in seen_experiments else 0.0
        return confidence * 0.6 + support_score * 0.3 + novelty_bonus

    def _effective_memory_adjustment(
        self,
        state: CTFState,
        *,
        hypothesis: Hypothesis,
        base_score: float,
        max_obs_score: float | None,
    ) -> float:
        raw_adjustment = float(
            state.hypothesis_memory_adjustments.get(
                hypothesis.kind,
                state.hypothesis_memory_adjustments.get(hypothesis.id, 0.0),
            )
        )
        clamped_adjustment = max(-0.25, min(0.25, raw_adjustment))
        trace = self._memory_atomic_fact_trace(state, hypothesis.kind)

        if self._is_memory_contradicted(state, hypothesis.kind):
            state.hypothesis_memory_adjustments[hypothesis.kind] = 0.0
            state.meta_reasonings.append(
                {
                    "type": "hypothesis_memory_adjustment",
                    "kind": hypothesis.kind,
                    "applied_adjustment": 0.0,
                    "metadata": {
                        "reason": "contradiction_zeroed",
                        "current_atomic_facts": trace.get("current_atomic_facts") or [],
                        "required_atomic_facts": trace.get("required_atomic_facts") or [],
                    },
                }
            )
            return 0.0

        adjusted = clamped_adjustment
        reason = "memory_adjustment_applied"
        if adjusted > 0:
            adjusted, reason = self._apply_atomic_fact_support(
                adjusted,
                trace=trace,
            )

        if max_obs_score is not None and not hypothesis.supporting_observations and clamped_adjustment > 0:
            capped_score = min(base_score + adjusted, max_obs_score + 0.1)
            adjusted = capped_score - base_score
            if adjusted < clamped_adjustment:
                reason = "observation_floor_capped"

        state.hypothesis_memory_adjustments[hypothesis.kind] = adjusted
        if raw_adjustment != 0.0:
            state.meta_reasonings.append(
                {
                    "type": "hypothesis_memory_adjustment",
                    "kind": hypothesis.kind,
                    "applied_adjustment": adjusted,
                    "metadata": {
                        "reason": reason,
                        "raw_adjustment": raw_adjustment,
                        "current_atomic_facts": trace.get("current_atomic_facts") or [],
                        "required_atomic_facts": trace.get("required_atomic_facts") or [],
                        "matched_atomic_facts": trace.get("matched_atomic_facts") or [],
                        "matched_entry_ids": trace.get("matched_entry_ids") or [],
                    },
                }
            )
        return adjusted

    def _is_memory_contradicted(self, state: CTFState, hypothesis_kind: str) -> bool:
        if hypothesis_kind == "backup_source_leak":
            return self._backup_clue_is_false(state) and not self._has_backup_artifact(state)
        if hypothesis_kind == "auth_form_sqli":
            return not self._has_login_form(state)
        if hypothesis_kind == "generic_param_sqli":
            return not self._has_generic_get_sqli_surface(state)
        if hypothesis_kind == "php_unserialize_magic_method":
            return "php" not in self._state_blob(state).lower()
        if hypothesis_kind == "tornado_ssti":
            return not self._has_tornado_feature(state)
        return False

    def _apply_atomic_fact_support(
        self,
        adjustment: float,
        *,
        trace: dict[str, object],
    ) -> tuple[float, str]:
        required = set(trace.get("required_atomic_facts") or [])
        matched = set(trace.get("matched_atomic_facts") or [])
        if not required:
            return adjustment, "memory_adjustment_applied"
        if not matched:
            return min(adjustment, 0.05), "atomic_fact_weak_support"
        support_bonus = min(0.05, 0.02 * len(matched))
        return min(0.25, adjustment + support_bonus), "atomic_fact_supported"

    def _memory_atomic_fact_trace(
        self,
        state: CTFState,
        hypothesis_kind: str,
    ) -> dict[str, object]:
        audit = self._latest_strategy_memory_audit(state)
        current_atomic_facts = set(
            str(item).strip().lower()
            for item in (audit.get("current_atomic_facts") or self._derive_current_atomic_facts(state))
            if str(item).strip()
        )
        required_atomic_facts = self._required_atomic_facts_for_hypothesis(hypothesis_kind)
        matched_entry_ids: list[str] = []
        historical_atomic_facts: set[str] = set()

        for item in audit.get("matched_entries") or []:
            if not isinstance(item, dict):
                continue
            winning = {
                str(kind).strip()
                for kind in (item.get("winning_hypothesis_kinds") or [])
                if str(kind).strip()
            }
            failed = {
                str(kind).strip()
                for kind in (item.get("failed_hypothesis_kinds") or [])
                if str(kind).strip()
            }
            if hypothesis_kind not in winning and hypothesis_kind not in failed:
                continue
            matched_entry_ids.append(str(item.get("id") or "").strip())
            historical_atomic_facts.update(
                str(fact).strip().lower()
                for fact in (item.get("atomic_facts") or [])
                if str(fact).strip()
            )

        matched_atomic_facts = sorted(
            historical_atomic_facts & current_atomic_facts & required_atomic_facts
        )
        return {
            "current_atomic_facts": sorted(current_atomic_facts),
            "required_atomic_facts": sorted(required_atomic_facts),
            "matched_atomic_facts": matched_atomic_facts,
            "matched_entry_ids": [item for item in matched_entry_ids if item],
        }

    def _latest_strategy_memory_audit(self, state: CTFState) -> dict[str, object]:
        for item in reversed(state.meta_reasonings):
            if isinstance(item, dict) and item.get("type") == "strategy_memory_audit":
                return item
        return {}

    def _required_atomic_facts_for_hypothesis(self, hypothesis_kind: str) -> set[str]:
        mapping = {
            "backup_source_leak": {
                "artifact:backup_archive",
                "signal:source_hint",
                "web_subtype:backup_source",
            },
            "unicode_numeric_form_bypass": {
                "surface:price_form",
                "surface:single_char_price",
                "route:charge_form",
            },
            "auth_form_sqli": {
                "signal:login_form",
                "auth:form_login",
                "type:sqli",
                "error:sql_error",
            },
            "generic_param_sqli": {
                "surface:get_form_param",
                "type:sqli",
                "error:sql_error",
            },
            "php_unserialize_magic_method": {
                "tech:php",
            },
            "tornado_ssti": {
                "framework:tornado",
                "web_subtype:tornado",
            },
            "hash_guarded_file_read": {
                "surface:file_hash_guard",
                "web_subtype:file_hash_guard",
            },
            "hash_reconstruction_attack": {
                "surface:file_hash_guard",
                "web_subtype:file_hash_guard",
                "route:hint_file",
            },
            "hint_chain_followup": {
                "route:hint_file",
                "web_subtype:hint_file",
            },
            "ssti_via_render_parameter": {
                "surface:render_param",
                "web_subtype:render_param",
            },
        }
        return set(mapping.get(hypothesis_kind, set()))

    def _derive_current_atomic_facts(self, state: CTFState) -> list[str]:
        facts: set[str] = set()
        if state.detected_type:
            facts.add(f"type:{str(state.detected_type).strip().lower()}")
        if self._has_login_form(state):
            facts.add("signal:login_form")
            facts.add("auth:form_login")
        if self._has_generic_get_sqli_surface(state):
            facts.add("surface:get_form_param")
        if self._has_unicode_numeric_form_surface(state):
            facts.add("surface:price_form")
            facts.add("route:charge_form")
        if self._has_single_char_price_clue(state):
            facts.add("surface:single_char_price")
        if self._has_backup_artifact(state):
            facts.add("artifact:backup_archive")
            facts.add("signal:source_hint")
        if self._has_tornado_feature(state):
            facts.add("framework:tornado")
            facts.add("web_subtype:tornado")
        if self._has_file_and_hash_param(state):
            facts.add("surface:file_hash_guard")
            facts.add("web_subtype:file_hash_guard")
        if self._has_hint_files(state):
            facts.add("route:hint_file")
            facts.add("web_subtype:hint_file")
        if self._has_render_param(state):
            facts.add("surface:render_param")
            facts.add("web_subtype:render_param")
        blob = self._state_blob(state).lower()
        if "sql syntax" in blob or "sqlstate" in blob:
            facts.add("error:sql_error")
        if "php" in blob or ".php" in blob or "unserialize" in blob:
            facts.add("tech:php")
        return sorted(facts)

    def _has_login_form(self, state: CTFState) -> bool:
        blob = self._state_blob(state).lower()
        if "username" in blob and "password" in blob:
            return True
        user_tokens = ("username", "user", "email", "login", "account")
        pass_tokens = ("password", "pass", "pwd")
        for form in self._forms_from_state(state):
            if not isinstance(form, dict):
                continue
            input_names = {
                str(item.get("name") or "").strip().lower()
                for item in (form.get("inputs") or [])
                if isinstance(item, dict) and str(item.get("name") or "").strip()
            }
            has_user_field = any(any(token in name for token in user_tokens) for name in input_names)
            has_pass_field = any(any(token in name for token in pass_tokens) for name in input_names)
            if has_user_field and has_pass_field:
                return True
        return False

    def _has_generic_get_sqli_surface(self, state: CTFState) -> bool:
        for form in self._forms_from_state(state):
            if not isinstance(form, dict):
                continue
            method = str(form.get("method") or "GET").strip().upper()
            if method != "GET":
                continue
            for item in form.get("inputs") or []:
                if not isinstance(item, dict):
                    continue
                name = str(item.get("name") or "").strip()
                if not name:
                    continue
                field_type = str(item.get("type") or "text").strip().lower()
                if field_type in {"submit", "button", "image", "reset", "hidden"}:
                    continue
                return True
        return False

    def _has_sql_error_signal(self, state: CTFState) -> bool:
        blob = self._state_blob(state).lower()
        return any(token in blob for token in ("sql syntax", "sqlstate", "mariadb", "mysql"))

    def _has_backup_artifact(self, state: CTFState) -> bool:
        artifact_blob = self._artifact_blob(state).lower()
        endpoint_blob = self._endpoint_blob(state).lower()
        concrete_tokens = ("www.zip", ".zip", ".tar", ".bak", ".phps", "flag.php")
        return any(token in artifact_blob or token in endpoint_blob for token in concrete_tokens)

    def _has_attachment_artifact(self, state: CTFState) -> bool:
        blob = (self._artifact_blob(state) + "\n" + self._endpoint_blob(state) + "\n" + self._state_blob(state)).lower()
        return any(
            token in blob
            for token in (".zip", ".db", ".sqlite", ".sqlite3", ".wal", ".pcap", ".7z", ".rar", "directory listing")
        )

    def _backup_clue_is_false(self, state: CTFState) -> bool:
        for obs in state.observations:
            metadata = obs.metadata if isinstance(obs.metadata, dict) else {}
            if "backup_clue" in metadata and metadata.get("backup_clue") is False:
                return True
        return "backup_clue=false" in self._state_blob(state).lower()

    def _has_file_and_hash_param(self, state: CTFState) -> bool:
        if "file_hash_guard" in self._web_subtypes(state):
            return True
        return any(
            self._url_has_params(candidate, {"filename", "filehash"})
            for candidate in self._iter_url_candidates(state)
        )

    def _has_tornado_feature(self, state: CTFState) -> bool:
        return "tornado" in self._web_subtypes(state) or "tornado" in self._state_blob(state).lower()

    def _has_hint_files(self, state: CTFState) -> bool:
        if "hint_file" in self._web_subtypes(state):
            return True
        blob = self._state_blob(state).lower()
        return any(token in blob for token in ("/hints.txt", "/welcome.txt", "/flag.txt"))

    def _has_render_param(self, state: CTFState) -> bool:
        if "render_param" in self._web_subtypes(state):
            return True
        for candidate in self._iter_url_candidates(state):
            parsed = urlparse(str(candidate or ""))
            params = set(parse_qs(parsed.query).keys())
            if params.intersection({"msg", "message", "error", "render", "template"}):
                return True
            lowered = str(candidate or "").lower()
            if any(f"{name}=" in lowered for name in ("msg", "message", "error", "render", "template")):
                return True
        return False

    def _has_jwt_surface(self, state: CTFState) -> bool:
        blob = self._state_blob(state).lower()
        return (
            "authorization: bearer" in blob
            or "bearer " in blob
            or "jwt_secret" in blob
            or "secret_key" in blob
            or ("jwt" in blob and "role=admin" in blob)
            or ("jwt" in blob and "is_admin" in blob)
        )

    def _apply_uniform_failure_counterevidence(
        self,
        state: CTFState,
        hypotheses: list[Hypothesis],
    ) -> None:
        exhausted_kinds = self._uniform_failure_strategy_kinds(state)
        if not exhausted_kinds:
            return

        affected_by_surface = {
            "ssti_via_render_parameter": {"ssti_via_render_parameter"},
            "tornado_ssti": {"ssti_via_render_parameter", "tornado_ssti"},
            "hash_guarded_file_read": {"hash_guarded_file_read"},
        }
        for hypothesis in hypotheses:
            trigger_kinds = affected_by_surface.get(hypothesis.kind)
            if not trigger_kinds or not (trigger_kinds & exhausted_kinds):
                continue
            hypothesis.confidence = min(hypothesis.confidence, 0.08)
            if "uniform failure surface observed" not in hypothesis.counter_evidence:
                hypothesis.counter_evidence.append("uniform failure surface observed")
            if hypothesis.kind in {"ssti_via_render_parameter", "tornado_ssti"}:
                hypothesis.status = "exhausted"

    def _uniform_failure_strategy_kinds(self, state: CTFState) -> set[str]:
        strategy_kinds: set[str] = set()
        for obs in state.observations:
            if obs.kind not in {"uniform_failure_surface", "strategy_surface_exhausted"}:
                continue
            metadata = obs.metadata if isinstance(obs.metadata, dict) else {}
            strategy_kind = str(metadata.get("strategy_kind") or "").strip()
            if strategy_kind:
                strategy_kinds.add(strategy_kind)
        return strategy_kinds

    def _has_file_endpoint(self, state: CTFState) -> bool:
        if {"file_endpoint", "file_hash_guard"} & self._web_subtypes(state):
            return True
        for candidate in self._iter_url_candidates(state):
            parsed = urlparse(candidate)
            params = set(parse_qs(parsed.query).keys())
            if parsed.path.startswith("/file") and "filename" in params:
                return True
            if parsed.path.startswith("/download") and "name" in params:
                return True
            if params.intersection({"file", "path", "page", "include", "filename"}):
                return True
            lowered = candidate.lower()
            if "/file?filename=" in lowered or "/download?name=" in lowered:
                return True
        return False

    def _has_unicode_numeric_form_surface(self, state: CTFState) -> bool:
        forms = self._forms_from_state(state)
        if not forms:
            return False

        saw_price_form = False
        saw_charge_route = False
        for form in forms:
            if not isinstance(form, dict):
                continue
            action = str(form.get("action") or "").strip().lower()
            input_names = {
                str(item.get("name") or "").strip().lower()
                for item in (form.get("inputs") or [])
                if isinstance(item, dict) and str(item.get("name") or "").strip()
            }
            if {"id", "price"}.issubset(input_names):
                saw_price_form = True
            if "/charge" in action or action.endswith("charge"):
                saw_charge_route = True

        if not saw_price_form:
            return False

        if saw_charge_route:
            return True

        page_blob = self._state_blob(state).lower()
        semantic_tokens = (
            "purchase",
            "price",
            "item id",
            "only one char",
            "one char",
            "unicorn shop",
        )
        return any(token in page_blob for token in semantic_tokens)

    def _has_single_char_price_clue(self, state: CTFState) -> bool:
        page_blob = self._state_blob(state).lower()
        return any(
            token in page_blob
            for token in (
                "only one char",
                "one char",
                "single char",
                "1 char",
            )
        )

    def _url_has_params(self, candidate: str, expected: set[str]) -> bool:
        parsed = urlparse(str(candidate or ""))
        params = set(parse_qs(parsed.query).keys())
        if expected.issubset(params):
            return True
        lowered = str(candidate or "").lower()
        return all(f"{name}=" in lowered for name in expected)

    def _iter_url_candidates(self, state: CTFState) -> list[str]:
        candidates: list[str] = []
        for obs in state.observations:
            candidates.extend(self._stringify_observation(obs))
            metadata = obs.metadata if isinstance(obs.metadata, dict) else {}
            endpoints = metadata.get("endpoints")
            if isinstance(endpoints, list):
                candidates.extend(str(endpoint) for endpoint in endpoints)
        for artifact in state.artifacts:
            candidates.extend(
                str(item)
                for item in [artifact.name, artifact.location, artifact.source]
                if item
            )
            if isinstance(artifact.metadata, dict):
                for value in artifact.metadata.values():
                    candidates.append(str(value))
        return [candidate for candidate in candidates if candidate]

    def _forms_from_state(self, state: CTFState) -> list[dict[str, object]]:
        forms: list[dict[str, object]] = []
        for obs in state.observations:
            metadata = obs.metadata if isinstance(obs.metadata, dict) else {}
            for key in ("forms_detail", "forms"):
                raw = metadata.get(key)
                if not isinstance(raw, list):
                    continue
                for item in raw:
                    if isinstance(item, dict):
                        forms.append(item)
        return forms

    def _stringify_observation(self, observation) -> list[str]:
        values = [observation.kind, observation.value, observation.source]
        if isinstance(observation.metadata, dict):
            values.extend(str(value) for value in observation.metadata.values())
        return [str(value) for value in values if value]

    def _state_blob(self, state: CTFState) -> str:
        return "\n".join(
            [
                self._observation_blob(state),
                self._artifact_blob(state),
                self._endpoint_blob(state),
                str(state.detected_type or ""),
            ]
        )

    def _web_subtypes(self, state: CTFState) -> set[str]:
        values: list[str] = []
        for obs in state.observations:
            metadata = obs.metadata if isinstance(obs.metadata, dict) else {}
            raw = metadata.get("web_subtype")
            if isinstance(raw, list):
                values.extend(str(item).strip().lower() for item in raw if str(item).strip())
            elif isinstance(raw, str) and raw.strip():
                values.append(raw.strip().lower())
        return set(values)

    def _find_hypothesis(self, state: CTFState, hypothesis_id: str) -> Hypothesis | None:
        for hypothesis in state.hypotheses:
            if hypothesis.id == hypothesis_id:
                return hypothesis
        return None

    def _find_experiment(self, state: CTFState, experiment_id: str | None) -> Experiment | None:
        if not experiment_id:
            return None
        for experiment in state.experiments:
            if experiment.id == experiment_id:
                return experiment
        return None

    def _observation_blob(self, state: CTFState) -> str:
        return "\n".join(
            "\n".join(
                str(item)
                for item in [
                    obs.kind,
                    obs.value,
                    obs.source,
                    obs.metadata,
                ]
            )
            for obs in state.observations
        )

    def _artifact_blob(self, state: CTFState) -> str:
        return "\n".join(
            "\n".join(
                str(item)
                for item in [artifact.name, artifact.location, artifact.source, artifact.metadata]
                if item is not None
            )
            for artifact in state.artifacts
        )

    def _endpoint_blob(self, state: CTFState) -> str:
        parts: list[str] = []
        for obs in state.observations:
            endpoints = obs.metadata.get("endpoints") if obs.metadata else []
            if isinstance(endpoints, list):
                parts.extend(str(endpoint) for endpoint in endpoints)
        return "\n".join(parts)


__all__ = ["HypothesisEngine"]
