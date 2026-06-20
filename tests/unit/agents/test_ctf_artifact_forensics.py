from flaghunter.agents.pa_agent.ctf_dispatcher import CTFTaskDispatcher

_ARTIFACT_MODULE = "flaghunter.agents.pa_agent.artifact_forensics"


def test_artifact_forensics_methods_live_in_artifact_forensics_mixin():
    for name in (
        "_run_artifact_forensics_strategy",
        "_collect_artifact_candidates",
        "_ingest_local_challenge_artifacts",
        "_expand_artifact_candidates_from_directory_pages",
        "_collect_attachment_research_context",
        "_analyze_attachment_artifact",
    ):
        assert getattr(CTFTaskDispatcher, name).__module__ == _ARTIFACT_MODULE


def test_attachment_clue_regex_moved_intact():
    from flaghunter.agents.pa_agent.artifact_forensics import _ATTACHMENT_CLUE_RE

    # word-boundary semantics preserved (\b after .db), Chinese clue intact
    assert _ATTACHMENT_CLUE_RE.search("see attachment.sqlite3 here")
    assert _ATTACHMENT_CLUE_RE.search("有附件压缩包")
    assert not _ATTACHMENT_CLUE_RE.search("plaindbword")
