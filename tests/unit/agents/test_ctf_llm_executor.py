from flaghunter.agents.pa_agent.ctf_dispatcher import CTFTaskDispatcher

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
