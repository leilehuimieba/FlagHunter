from flaghunter.agents.pa_agent.ctf_dispatcher import CTFTaskDispatcher

_XSS_COLLECTOR_MODULE = "flaghunter.agents.pa_agent.xss_collector_chain"


def test_xss_collector_chain_methods_live_in_mixin():
    for name in (
        "_attempt_stored_xss_chain",
        "_attempt_visit_url_chain",
        "_attempt_docker_loopback_visit_chain",
        "_resolve_loopback_target_container",
        "_handle_collector_hit",
        "_fetch_admin_with_sid",
    ):
        assert getattr(CTFTaskDispatcher, name).__module__ == _XSS_COLLECTOR_MODULE
