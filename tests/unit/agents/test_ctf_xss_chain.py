from flaghunter.agents.pa_agent.ctf_dispatcher import CTFTaskDispatcher


def test_xss_chain_entrypoints_live_in_xss_chain_mixin():
    assert (
        CTFTaskDispatcher._execute_xss_route.__module__
        == "flaghunter.agents.pa_agent.chains.xss"
    )
    assert (
        CTFTaskDispatcher._execute_xss_chain.__module__
        == "flaghunter.agents.pa_agent.chains.xss"
    )
