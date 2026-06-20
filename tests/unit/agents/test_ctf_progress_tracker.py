from flaghunter.agents.pa_agent.ctf_dispatcher import CTFTaskDispatcher

_PROGRESS_TRACKER_MODULE = "flaghunter.agents.pa_agent.progress_tracker"


def test_progress_delta_methods_live_in_progress_tracker_mixin():
    for name in ("_snapshot_flag_counts", "_derive_progress_delta"):
        assert getattr(CTFTaskDispatcher, name).__module__ == _PROGRESS_TRACKER_MODULE
