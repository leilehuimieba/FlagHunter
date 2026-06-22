from flaghunter.agents.pa_agent.ctf_dispatcher import CTFTaskDispatcher
from flaghunter.agents.pa_agent.recon_executor import ReconExecutor

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


def test_recon_executor_is_stateless():
    # Detached from any dispatcher: the executor holds no eager state of its own.
    # State / runtime / reasoning_layer / siblings are injected per call via
    # ReconExecContext, so a fresh instance must have an empty __dict__ (no stale
    # CTFState / runtime handle captured across replay/fork swaps).
    executor = ReconExecutor()
    assert vars(executor) == {}


def test_recon_executor_find_registration_form_pure():
    executor = ReconExecutor()
    login_form = {"action": "/login", "method": "POST", "inputs": []}
    register_form = {
        "action": "/register",
        "method": "POST",
        "inputs": [
            {"name": "username", "type": "text"},
            {"name": "email", "type": "email"},
            {"name": "password", "type": "password"},
        ],
    }
    forms = [login_form, register_form]
    assert executor.find_registration_form(forms, login_form=login_form) is register_form
    # No register-like form present -> None
    assert executor.find_registration_form([login_form], login_form=login_form) is None


def test_recon_executor_build_account_form_submission_pure():
    executor = ReconExecutor()
    form = {
        "inputs": [
            {"name": "user", "type": "text"},
            {"name": "email", "type": "email"},
            {"name": "pwd", "type": "password"},
            {"name": "csrf", "type": "hidden", "value": "tok"},
            {"name": "go", "type": "submit"},
        ]
    }
    submission = executor.build_account_form_submission(
        form, username="alice", email="a@example.com", password="secret"
    )
    assert submission["user"] == "alice"
    assert submission["email"] == "a@example.com"
    assert submission["pwd"] == "secret"
    assert submission["csrf"] == "tok"
    # submit-type fields are dropped
    assert "go" not in submission
