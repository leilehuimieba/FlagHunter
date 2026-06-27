"""N7-④ Guard tests: model_router vision-capable preference.

Covers:
  - _is_vision_capable detection (positive + negative).
  - _score_available_model adds a bonus for vision models / penalty for
    non-vision ones ONLY when require_vision=True.
  - route() prefers a vision-capable model when require_vision=True.
  - Regression: default (require_vision=False) scoring/routing is unchanged.
"""

from flaghunter.cpa_modules.m1_api_hub.model_router import (
    _is_vision_capable,
    _score_available_model,
    route,
)


# ---------------------------------------------------------------------------
# _is_vision_capable
# ---------------------------------------------------------------------------

class TestIsVisionCapable:
    def test_claude_sonnet_is_vision(self):
        assert _is_vision_capable("claude-sonnet-4-20250514") is True

    def test_claude_opus_is_vision(self):
        assert _is_vision_capable("claude-opus-4-5") is True

    def test_claude_haiku4_is_vision(self):
        assert _is_vision_capable("claude-haiku-4-20250514") is True

    def test_gpt4o_is_vision(self):
        assert _is_vision_capable("gpt-4o") is True

    def test_deepseek_vl_is_vision(self):
        assert _is_vision_capable("deepseek-vl2") is True

    def test_llava_is_vision(self):
        assert _is_vision_capable("ollama/llava:13b") is True

    def test_deepseek_chat_is_not_vision(self):
        assert _is_vision_capable("deepseek-chat") is False

    def test_plain_llama_is_not_vision(self):
        assert _is_vision_capable("ollama/llama3:8b") is False

    def test_empty_is_not_vision(self):
        assert _is_vision_capable("") is False


# ---------------------------------------------------------------------------
# _score_available_model — vision bonus / penalty
# ---------------------------------------------------------------------------

class TestScoreVision:
    def test_vision_model_gains_when_required(self):
        base = _score_available_model("claude-sonnet-4-20250514", "medium")
        boosted = _score_available_model(
            "claude-sonnet-4-20250514", "medium", require_vision=True
        )
        assert boosted > base

    def test_non_vision_model_penalised_when_required(self):
        base = _score_available_model("deepseek-chat", "medium")
        penalised = _score_available_model(
            "deepseek-chat", "medium", require_vision=True
        )
        assert penalised < base

    def test_no_change_when_vision_not_required(self):
        # Regression: default path must be byte-identical.
        for model in ("claude-sonnet-4-20250514", "deepseek-chat", "gpt-4o", "llava"):
            assert _score_available_model(model, "medium") == _score_available_model(
                model, "medium", require_vision=False
            )

    def test_vision_outranks_nonvision_when_required(self):
        # A vision model with NO tier base must still beat a tier-matching
        # non-vision model once vision is required (combined swing dominates).
        vision = _score_available_model("deepseek-vl2", "heavy", require_vision=True)
        nonvision = _score_available_model("deepseek-chat", "heavy", require_vision=True)
        assert vision > nonvision


# ---------------------------------------------------------------------------
# route() — vision preference
# ---------------------------------------------------------------------------

class TestRouteVision:
    def test_route_prefers_vision_model_when_required(self):
        # Both providers are in the recognised OpenAI family (so route reaches
        # the scoring stage); only one accepts images. With require_vision the
        # vision-capable sibling must be selected.
        providers = ["gpt-4-vision-preview", "gpt-4-32k"]
        chosen = route("summary", providers, require_vision=True)
        assert chosen == "gpt-4-vision-preview"

    def test_vision_flag_flips_choice_on_tie(self):
        # The two siblings tie on tier base score, so without the flag the
        # list order wins (non-vision listed first). The flag must flip the
        # selection to the vision-capable model -> proves the flag steers route.
        providers = ["gpt-4-32k", "gpt-4-vision-preview"]
        without_flag = route("summary", providers)
        with_flag = route("summary", providers, require_vision=True)
        assert without_flag == "gpt-4-32k"
        assert with_flag == "gpt-4-vision-preview"

    def test_route_default_unaffected_by_vision_flag_absence(self):
        # Regression: existing 2-arg callers keep prior behaviour.
        providers = ["claude-sonnet-4-20250514", "claude-haiku-4-20250514"]
        assert route("planning", providers) == route(
            "planning", providers, require_vision=False
        )

    def test_route_picks_claude_tier_when_vision_required_and_supported(self):
        # Claude tier models are all vision-capable; routing stays sane.
        providers = ["claude-opus-4-5", "claude-sonnet-4-20250514"]
        chosen = route("exploitation", providers, require_vision=True)
        assert _is_vision_capable(chosen)

    def test_route_falls_back_to_vision_capable_default_when_only_nonvision(self):
        # Only a non-vision provider is available, but the tier candidate
        # (a vision-capable claude/gpt model) is the safe fallback.
        providers = ["deepseek-chat"]
        chosen = route("planning", providers, require_vision=True)
        # deepseek-chat is penalised below the >0 threshold, so route falls
        # back to the tier candidate, which is vision-capable.
        assert _is_vision_capable(chosen)


# ---------------------------------------------------------------------------
# Regression: existing Claude / GPT scoring gradient preserved
# ---------------------------------------------------------------------------

class TestScoringRegression:
    def test_light_tier_haiku_beats_sonnet(self):
        assert _score_available_model(
            "claude-haiku-4-20250514", "light"
        ) > _score_available_model("claude-sonnet-4-20250514", "light")

    def test_heavy_tier_opus_beats_sonnet(self):
        assert _score_available_model(
            "claude-opus-4-5", "heavy"
        ) > _score_available_model("claude-sonnet-4-20250514", "heavy")

    def test_default_route_claude_medium(self):
        providers = ["claude-sonnet-4-20250514", "claude-haiku-4-20250514"]
        assert route("default", providers) == "claude-sonnet-4-20250514"
