from flaghunter.agents.pa_agent.ctf_dispatcher import CTFTaskDispatcher

_RENDER_SURFACE_MODULE = "flaghunter.agents.pa_agent.render_surface"


def test_render_surface_methods_live_in_render_surface_mixin():
    for name in (
        "_collect_render_surface_urls",
        "_normalize_render_surface_url",
        "_strategy_surface_signature",
        "_was_strategy_surface_exhausted",
        "_mark_strategy_surface_exhausted",
        "_response_fingerprint",
        "_inject_render_payload",
        "_extract_cookie_secret_candidate",
        "_collect_candidate_filenames",
    ):
        assert getattr(CTFTaskDispatcher, name).__module__ == _RENDER_SURFACE_MODULE
