from flaghunter.agents.pa_agent.ctf_dispatcher import CTFTaskDispatcher

_AUDIT_INFRA_MODULE = "flaghunter.agents.pa_agent.audit_infra"


def test_audit_infra_methods_live_in_audit_infra_mixin():
    for name in (
        "_setup_session_ledger",
        "_setup_artifact_registry",
        "_setup_checkpoint_store",
        "_record_session_event",
        "_write_checkpoint",
        "_register_artifact_record",
        "_record_recovery_decision",
        "_resolve_registered_local_challenge_paths",
        "_resolve_registered_local_key_files",
        "_ingest_registered_local_source_hints",
        "_runtime_browser_action",
        "_runtime_proxy_action",
        "_runtime_execute_command",
    ):
        assert getattr(CTFTaskDispatcher, name).__module__ == _AUDIT_INFRA_MODULE
