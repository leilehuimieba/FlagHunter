from flaghunter.agents.pa_agent.ctf_dispatcher import CTFTaskDispatcher
from flaghunter.agents.pa_agent.llm_executor import LLMExecutor

_LLM_EXECUTOR_MODULE = "flaghunter.agents.pa_agent.llm_executor"


def test_llm_executor_cluster_lives_in_llm_executor_mixin():
    for name in (
        "_run_llm_driven_exploration",
        "_call_llm_for_action",
        "_normalized_runtime_summary",
        "_recent_source_fetch_probe_targets",
        "_extract_llm_action_text",
        "_normalize_llm_http_payload",
        "_looks_like_loopback_or_file_target",
        "_normalize_llm_shell_command",
        "_build_source_fetch_write_output_urls",
        "_derive_source_fetch_write_llm_request",
        "_execute_llm_action",
        "_record_llm_reasoning",
        "_summarize_payload",
        "_summarize_response",
        "_expected_signal_met",
    ):
        assert getattr(CTFTaskDispatcher, name).__module__ == _LLM_EXECUTOR_MODULE


def test_llm_executor_is_stateless():
    # Detached from any dispatcher: the executor holds no eager state of its own.
    # State / llm / runtime / siblings are injected per call via LLMExecContext,
    # so a fresh instance must have an empty __dict__ (no stale CTFState / llm
    # handle captured across replay/fork swaps).
    executor = LLMExecutor()
    assert vars(executor) == {}


def test_llm_executor_expected_signal_met_pure():
    executor = LLMExecutor()
    # 200 + body contains marker -> matched
    assert executor.expected_signal_met(
        "status 200, body contains welcome",
        "<html>WELCOME admin</html>",
        {"status_code": "200"},
    )
    # flag marker present in body
    assert executor.expected_signal_met("flag found", "here is flag{abc}", {})
    # keyword: prefix
    assert executor.expected_signal_met("keyword:secret", "the secret value", {})
    # empty signal never matches
    assert not executor.expected_signal_met("", "anything", {})
    # signal not present in response
    assert not executor.expected_signal_met("nonexistent", "body text", {})


def test_llm_executor_extract_llm_action_text_pure():
    executor = LLMExecutor()

    class _Result:
        content = "hello"
        finish_reason = "stop"

    assert executor.extract_llm_action_text(_Result()) == ("hello", "stop")
    assert executor.extract_llm_action_text({"text": "x"}) == ("x", "")
    assert executor.extract_llm_action_text("raw") == ("raw", "")


def test_llm_executor_looks_like_loopback_or_file_target_pure():
    executor = LLMExecutor()
    assert executor.looks_like_loopback_or_file_target("file:///etc/passwd")
    assert executor.looks_like_loopback_or_file_target("http://127.0.0.1:8080/x")
    assert executor.looks_like_loopback_or_file_target("https://localhost/y")
    assert not executor.looks_like_loopback_or_file_target("http://example.com")
    assert not executor.looks_like_loopback_or_file_target("")
