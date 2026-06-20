from flaghunter.agents.pa_agent.ctf_dispatcher import CTFTaskDispatcher

_SQLI_MODULE = "flaghunter.agents.pa_agent.sqli_executor"


def test_sqli_methods_live_in_sqli_executor_mixin():
    for name in (
        "_run_unicode_numeric_form_bypass_strategy",
        "_attempt_auth_form_sqli",
        "_attempt_sqlmap_sqli",
        "_attempt_generic_param_sqli",
        "_attempt_local_challenge_log_pivot",
    ):
        assert getattr(CTFTaskDispatcher, name).__module__ == _SQLI_MODULE


def test_sqli_auth_bypass_payloads_constant_moved_with_cluster():
    from flaghunter.agents.pa_agent.sqli_executor import _SQLI_AUTH_BYPASS_PAYLOADS

    assert "1' or 1=1#" in _SQLI_AUTH_BYPASS_PAYLOADS
