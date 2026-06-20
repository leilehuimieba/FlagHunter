from flaghunter.agents.pa_agent.ctf_dispatcher import CTFTaskDispatcher

_JWT_EXECUTOR_MODULE = "flaghunter.agents.pa_agent.jwt_executor"


def test_jwt_executor_cluster_lives_in_jwt_executor_mixin():
    for name in (
        "_collect_candidate_jwts",
        "_jwt_mutation_candidates",
        "_jwt_algorithm_candidates",
        "_jwt_secret_candidates",
        "_encode_none_jwt",
        "_jwt_request_headers",
    ):
        assert getattr(CTFTaskDispatcher, name).__module__ == _JWT_EXECUTOR_MODULE
