from flaghunter.agents.pa_agent.ctf_dispatcher import CTFTaskDispatcher


def test_upload_chain_entrypoint_lives_in_upload_chain_mixin():
    assert (
        CTFTaskDispatcher._execute_upload_chain.__module__
        == "flaghunter.agents.pa_agent.chains.upload"
    )
