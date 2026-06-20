from flaghunter.agents.pa_agent.ctf_dispatcher import CTFTaskDispatcher

_PLATFORM_EXECUTOR_MODULE = "flaghunter.agents.pa_agent.platform_executor"


def test_platform_executor_cluster_lives_in_platform_executor_mixin():
    for name in (
        "_snapshot_platform_context",
        "_infer_platform_profile",
        "_infer_challenge_id",
        "_align_platform_challenge",
        "_build_already_solved_reason",
    ):
        assert getattr(CTFTaskDispatcher, name).__module__ == _PLATFORM_EXECUTOR_MODULE
