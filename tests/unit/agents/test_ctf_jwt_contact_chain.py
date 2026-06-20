from flaghunter.agents.pa_agent.ctf_dispatcher import CTFTaskDispatcher

_JWT_CONTACT_MODULE = "flaghunter.agents.pa_agent.jwt_contact_chain"


def test_jwt_contact_chain_methods_live_in_mixin():
    for name in (
        "_run_jwt_manipulation_strategy",
        "_run_hint_chain_followup_strategy",
        "_run_file_read_endpoint_strategy",
        "_run_contact_report_chain_strategy",
        "_has_prior_contact_report_submission",
        "_is_contact_submission_success",
        "_attempt_contact_captcha_bypass",
    ):
        assert getattr(CTFTaskDispatcher, name).__module__ == _JWT_CONTACT_MODULE


def test_contact_pow_challenge_regex_moved_intact():
    from flaghunter.agents.pa_agent.jwt_contact_chain import _CONTACT_POW_CHALLENGE_RE

    # word-boundary semantics preserved (no backspace corruption), digit_token shape intact
    assert "\x08" not in _CONTACT_POW_CHALLENGE_RE.pattern
    m = _CONTACT_POW_CHALLENGE_RE.search("solve 12_abcDEF please")
    assert m and m.group(1) == "12_abcDEF"
    assert not _CONTACT_POW_CHALLENGE_RE.search("plainword")
