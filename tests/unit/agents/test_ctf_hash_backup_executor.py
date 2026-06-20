from flaghunter.agents.pa_agent.ctf_dispatcher import CTFTaskDispatcher

_HASH_BACKUP_MODULE = "flaghunter.agents.pa_agent.hash_backup_executor"


def test_hash_backup_methods_live_in_hash_backup_executor_mixin():
    for name in (
        "_run_hash_guarded_file_read_strategy",
        "_run_hash_reconstruction_attack_strategy",
        "_run_backup_source_leak_strategy",
        "_looks_like_warmup_include_source",
        "_attempt_warmup_include_bypass",
        "_extract_warmup_flag_filenames",
    ):
        assert getattr(CTFTaskDispatcher, name).__module__ == _HASH_BACKUP_MODULE


def test_backup_path_constants_moved_with_cluster():
    from flaghunter.agents.pa_agent.hash_backup_executor import (
        _COMMON_BACKUP_PATHS,
        _DJANGO_STATIC_SOURCE_PROBES,
    )

    assert "/www.zip" in _COMMON_BACKUP_PATHS
    assert "/static../views.py" in _DJANGO_STATIC_SOURCE_PROBES
