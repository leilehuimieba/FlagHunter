from flaghunter.agents.pa_agent.ctf_dispatcher import CTFTaskDispatcher

_NOTE_STORE_MODULE = "flaghunter.agents.pa_agent.note_store"


def test_note_store_cluster_lives_in_note_store_mixin():
    for name in (
        "_store_secret_note",
        "_store_missing_tools",
        "_store_retrospective",
        "_store_note",
        "_derive_artifact_producer",
        "_derive_artifact_category",
    ):
        assert getattr(CTFTaskDispatcher, name).__module__ == _NOTE_STORE_MODULE
