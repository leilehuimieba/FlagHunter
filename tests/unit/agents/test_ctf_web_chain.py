from flaghunter.agents.pa_agent.ctf_dispatcher import CTFTaskDispatcher


def test_web_chain_entrypoints_live_in_web_chain_mixin():
    assert (
        CTFTaskDispatcher._execute_web_route.__module__
        == "flaghunter.agents.pa_agent.chains.web"
    )
    assert (
        CTFTaskDispatcher._execute_web_chain.__module__
        == "flaghunter.agents.pa_agent.chains.web"
    )
