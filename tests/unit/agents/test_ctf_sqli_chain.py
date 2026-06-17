from flaghunter.agents.pa_agent.ctf_dispatcher import CTFTaskDispatcher


def test_sqli_chain_entrypoint_lives_in_sqli_chain_mixin():
    assert (
        CTFTaskDispatcher._execute_sqli_chain.__module__
        == "flaghunter.agents.pa_agent.chains.sqli"
    )
