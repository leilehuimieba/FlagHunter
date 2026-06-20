from flaghunter.agents.pa_agent.ctf_dispatcher import CTFTaskDispatcher

_SSTI_MODULE = "flaghunter.agents.pa_agent.ssti_executor"


def test_ssti_methods_live_in_ssti_executor_mixin():
    for name in (
        "_ssti_exploitation_gated_by_mode",
        "_run_render_parameter_ssti_strategy",
        "_run_tornado_ssti_strategy",
        "_run_ssti_probe_strategy",
        "_run_ssti_identify_strategy",
        "_run_ssti_exploit_strategy",
    ):
        assert getattr(CTFTaskDispatcher, name).__module__ == _SSTI_MODULE
