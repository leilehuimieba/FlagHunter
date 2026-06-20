from flaghunter.agents.pa_agent.ctf_dispatcher import CTFTaskDispatcher

_UPLOAD_MODULE = "flaghunter.agents.pa_agent.chains.upload"
_DISPATCHER_MODULE = "flaghunter.agents.pa_agent.ctf_dispatcher"


def test_upload_exclusive_methods_folded_into_upload_chain_mixin():
    for name in (
        "_form_action_url",
        "_default_upload_form_fields",
        "_generic_upload_payloads",
        "_upload_followup_urls",
        "_follow_uploaded_payloads",
    ):
        assert getattr(CTFTaskDispatcher, name).__module__ == _UPLOAD_MODULE


def test_shared_submit_form_request_stays_on_dispatcher():
    # _submit_form_request is a shared 11-site form helper, not upload-specific.
    assert CTFTaskDispatcher._submit_form_request.__module__ == _DISPATCHER_MODULE
