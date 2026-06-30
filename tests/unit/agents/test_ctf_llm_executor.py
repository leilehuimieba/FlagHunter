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


# --- §3.5 detection/correction separation: explain_signal_miss ---------------

def test_explain_signal_miss_empty_when_signal_met():
    e = LLMExecutor()
    out = e.explain_signal_miss(
        {"expected_signal": "flag", "action_type": "http_request"},
        "flag{x}",
        {"status_code": "200"},
        expected_signal_met=True,
    )
    assert out == ""


def test_explain_signal_miss_empty_when_no_expected_signal():
    e = LLMExecutor()
    out = e.explain_signal_miss(
        {"action_type": "http_request"}, "hi", {}, expected_signal_met=False
    )
    assert out == ""


def test_explain_signal_miss_states_expected_vs_observed_without_scripting_fix():
    e = LLMExecutor()
    out = e.explain_signal_miss(
        {"expected_signal": "body contains 49", "action_type": "http_request", "payload": {"url": "/calc?num=7*7"}},
        "no math here",
        {"status_code": "200"},
        expected_signal_met=False,
    )
    # Detection: names the expected signal and that it was not observed (factual).
    assert "body contains 49" in out
    assert "not observed" in out.lower()
    # Correction is left to the model — we steer ("change the ...") but don't script
    # a specific replacement payload.
    assert "do not repeat" in out.lower()
    assert "change the injection point" in out.lower()
