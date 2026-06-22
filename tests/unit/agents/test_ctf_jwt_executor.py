from types import SimpleNamespace

from flaghunter.agents.pa_agent.ctf_dispatcher import CTFTaskDispatcher
from flaghunter.agents.pa_agent.jwt_executor import JWTExecutor

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


def test_jwt_executor_is_stateless():
    """JWTExecutor holds no eager instance state — state is injected per call."""
    executor = JWTExecutor()
    assert vars(executor) == {}


def test_collect_candidate_jwts_reads_per_call_state():
    """State observations/artifacts are scanned for tokens via the per-call state arg."""
    executor = JWTExecutor()
    token = "eyJhbGciOiJIUzI1NiJ9.eyJ1c2VyIjoiYm9iIn0.sig"
    state = SimpleNamespace(
        observations=[
            SimpleNamespace(value=f"leaked token {token}", metadata={}),
        ],
        artifacts=[],
    )
    # Without state the page features alone carry no token.
    assert executor.collect_candidate_jwts("http://t", {}, state=None) == []
    # With state, the observation token is discovered.
    found = executor.collect_candidate_jwts("http://t", {}, state=state)
    assert any(c["token"] == token and c["source"] == "text" for c in found)


def test_jwt_secret_candidates_injects_source_hints_and_leaks():
    """source_hint_secrets callback + cookie_secret_leaked obs are prepended in order."""
    executor = JWTExecutor()
    state = SimpleNamespace(
        observations=[
            SimpleNamespace(kind="cookie_secret_leaked", value="leaked_key"),
            SimpleNamespace(kind="other", value="ignored"),
        ],
        artifacts=[],
    )
    seeds = executor.jwt_secret_candidates(
        state=state,
        source_hint_secrets=lambda: ["hinted_secret"],
    )
    # Defaults remain present.
    assert "secret" in seeds and "" in seeds
    # Both injected secrets are present and ahead of the static defaults.
    assert "hinted_secret" in seeds
    assert "leaked_key" in seeds
    assert seeds.index("hinted_secret") < seeds.index("secret")
    assert seeds.index("leaked_key") < seeds.index("secret")
    # De-duplicated.
    assert len(seeds) == len(set(seeds))


def test_jwt_mutation_and_alg_and_headers_are_pure():
    """Pure helpers need no state and match the documented behaviour."""
    executor = JWTExecutor()
    variants = executor.jwt_mutation_candidates({"role": "user"})
    assert {"role": "user"} in variants
    assert any(v.get("role") == "admin" for v in variants)

    assert executor.jwt_algorithm_candidates({"alg": "RS256"}) == ["none", "HS256", "HS512"]
    assert executor.jwt_algorithm_candidates({"alg": "HS384"}) == ["none", "HS384"]

    headers = executor.jwt_request_headers({"header_name": "X-Auth", "location": "sess"}, "tok")
    assert {"X-Auth": "Bearer tok"} in headers
    assert {"Cookie": "sess=tok"} in headers
