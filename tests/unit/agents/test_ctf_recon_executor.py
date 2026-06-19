from flaghunter.agents.pa_agent.ctf_dispatcher import CTFTaskDispatcher


def test_recon_phase_lives_in_recon_executor_mixin():
    assert (
        CTFTaskDispatcher._phase_recon.__module__
        == "flaghunter.agents.pa_agent.recon_executor"
    )
