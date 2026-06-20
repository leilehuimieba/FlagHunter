from flaghunter.agents.pa_agent.ctf_dispatcher import CTFTaskDispatcher

_FLAG_PROOF_MODULE = "flaghunter.agents.pa_agent.flag_proof"


def test_flag_proof_cluster_lives_in_flag_proof_mixin():
    for name in (
        "_record_wrong_flag_feedback",
        "_hydrate_flag_proof",
        "_recent_relevant_observations",
        "_observation_reference",
        "_format_reproduction_steps",
    ):
        assert getattr(CTFTaskDispatcher, name).__module__ == _FLAG_PROOF_MODULE
