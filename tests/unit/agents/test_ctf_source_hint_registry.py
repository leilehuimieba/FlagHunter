from flaghunter.agents.pa_agent.ctf_dispatcher import CTFTaskDispatcher

_SOURCE_HINT_MODULE = "flaghunter.agents.pa_agent.source_hint_registry"


def test_source_hint_registry_methods_live_in_mixin():
    for name in (
        "_has_recent_local_source_hint",
        "_recent_local_source_hint_count",
        "_recent_source_hint_backup_probe_paths",
        "_recent_local_source_hint_text",
        "_recent_local_source_hint_routes",
        "_recent_local_source_hint_secret_candidates",
        "_looks_like_source_code_blob",
        "_register_runtime_source_hint",
    ):
        assert getattr(CTFTaskDispatcher, name).__module__ == _SOURCE_HINT_MODULE


def test_source_hint_backup_probes_moved_with_cluster():
    from flaghunter.agents.pa_agent.source_hint_registry import (
        _SOURCE_HINT_BACKUP_PROBES,
    )

    assert _SOURCE_HINT_BACKUP_PROBES["app.py"] == (
        "/app.py.bak",
        "/app.py~",
        "/app.py.swp",
    )
    assert "index.php" in _SOURCE_HINT_BACKUP_PROBES
