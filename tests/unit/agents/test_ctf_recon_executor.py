from flaghunter.agents.pa_agent.ctf_dispatcher import CTFTaskDispatcher

_RECON_EXECUTOR_MODULE = "flaghunter.agents.pa_agent.recon_executor"


def test_recon_phase_lives_in_recon_executor_mixin():
    assert CTFTaskDispatcher._phase_recon.__module__ == _RECON_EXECUTOR_MODULE


def test_post_auth_recon_methods_live_in_recon_executor_mixin():
    for name in (
        "_candidate_auth_page_urls",
        "_harvest_auth_forms_from_routes",
        "_attempt_post_auth_recon",
        "_find_registration_form",
        "_build_account_form_submission",
    ):
        assert getattr(CTFTaskDispatcher, name).__module__ == _RECON_EXECUTOR_MODULE


def test_exploration_agenda_methods_live_in_recon_executor_mixin():
    for name in (
        "_populate_exploration_agenda_from_recon",
        "_seed_framework_conventional_routes",
        "_explore_agenda_items",
    ):
        assert getattr(CTFTaskDispatcher, name).__module__ == _RECON_EXECUTOR_MODULE
