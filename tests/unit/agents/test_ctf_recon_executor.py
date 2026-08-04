import asyncio

from flaghunter.agents.pa_agent.ctf_dispatcher import CTFTaskDispatcher
from flaghunter.agents.pa_agent.dispatcher_helpers import (
    _looks_like_robots_txt,
    _robots_disclosed_paths,
)
from flaghunter.agents.pa_agent.recon_executor import ReconExecContext, ReconExecutor

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


def test_robots_disclosed_paths_extracts_concrete_backup_path():
    body = (
        "User-agent: *\n"
        "Disallow: /user.php.bak\n"
        "Disallow: /admin/\n"
        "Disallow: /*.zip$\n"  # wildcard pattern -> not fetchable, skipped
        "Allow: /public/data.json\n"
        "Disallow: /\n"  # bare root -> skipped
        "# a comment line\n"
        "Sitemap: https://host/sitemap.xml   # trailing comment\n"
    )
    paths = _robots_disclosed_paths(body)
    # The whole point: a hidden backup-source path is surfaced.
    assert "/user.php.bak" in paths
    assert "/admin/" in paths
    assert "/public/data.json" in paths
    # Inline comments are stripped from directive values.
    assert "https://host/sitemap.xml" in paths
    # Wildcard patterns and the bare root carry no fetchable target.
    assert not any("*" in path for path in paths)
    assert "/" not in paths


def test_looks_like_robots_txt_rejects_soft_404_html():
    # A genuine robots body carries at least one directive keyword.
    assert _looks_like_robots_txt("User-agent: *\nDisallow: /secret")
    assert _looks_like_robots_txt("Sitemap: https://host/sitemap.xml")
    # Many CTF apps answer /robots.txt with their normal HTML page (HTTP 200);
    # that must NOT be mined for paths.
    assert not _looks_like_robots_txt("<html><body>Not found</body></html>")
    assert not _looks_like_robots_txt("")


def _build_recon_ctx(*, runtime, proxy_get, runtime_proxy_action):
    async def _noop_async(*args, **kwargs):
        return None

    return ReconExecContext(
        state=None,
        runtime=runtime,
        reasoning_layer=None,
        framework_conventional_routes={},
        runtime_browser_action=_noop_async,
        is_legacy_browser_runtime_probe=lambda probe: False,
        proxy_get_with_retry=proxy_get,
        runtime_proxy_action=runtime_proxy_action,
        scan_and_store=_noop_async,
        store_note=_noop_async,
        should_ignore_exploration_candidate=lambda url, **kwargs: False,
        extract_embedded_links=lambda text, base: [],
        emit=lambda msg: None,
        fingerprint_framework=lambda features: None,
        classify_exploration_hint_strength=lambda a, b: 0,
        form_action_url=lambda t, f: t,
    )


def test_phase_recon_folds_robots_disclosures_into_raw_links():
    # Fakebook-class reachability: robots.txt discloses the backup-source path the
    # challenge means to hide. Recon must fetch robots.txt and fold /user.php.bak
    # into raw_links, where the backup-source-leak strategy's .bak filter picks it
    # up. Before the fix, recon never fetched robots.txt at all, so the path stayed
    # structurally unreachable.
    landing_html = "<html><body><h1>Fakebook</h1></body></html>"
    robots_body = "User-agent: *\nDisallow: /user.php.bak\n"

    class _FakeRuntime:
        # Only the presence of proxy_action (and absence of browser_action) is
        # probed by phase_recon via hasattr; the actual calls go through the
        # injected ctx callables below.
        proxy_action = True

    robots_requested: list[str] = []

    async def _proxy_get(url, **kwargs):
        return {"body": landing_html, "headers": {}}

    async def _runtime_proxy_action(action, url="", **kwargs):
        if str(url).endswith("/robots.txt"):
            robots_requested.append(str(url))
            return {"body": robots_body}
        return {"body": ""}

    ctx = _build_recon_ctx(
        runtime=_FakeRuntime(),
        proxy_get=_proxy_get,
        runtime_proxy_action=_runtime_proxy_action,
    )

    features = asyncio.run(ReconExecutor().phase_recon("http://fakebook.local/", ctx))

    raw_links = features.get("raw_links") or []
    assert robots_requested, "recon must fetch /robots.txt"
    assert any(
        link.endswith("/user.php.bak") for link in raw_links
    ), f"disclosed backup path missing from raw_links: {raw_links}"


def test_phase_recon_ignores_soft_404_robots():
    # If /robots.txt returns the app's HTML page (a soft 404), no bogus paths
    # should be mined from it — the negative control for the disclosure fold.
    landing_html = "<html><body><a href='/home'>home</a></body></html>"
    soft_404 = "<html><body>page not found</body></html>"

    class _FakeRuntime:
        proxy_action = True

    async def _proxy_get(url, **kwargs):
        return {"body": landing_html, "headers": {}}

    async def _runtime_proxy_action(action, url="", **kwargs):
        if str(url).endswith("/robots.txt"):
            return {"body": soft_404}
        return {"body": ""}

    ctx = _build_recon_ctx(
        runtime=_FakeRuntime(),
        proxy_get=_proxy_get,
        runtime_proxy_action=_runtime_proxy_action,
    )

    features = asyncio.run(ReconExecutor().phase_recon("http://fakebook.local/", ctx))

    raw_links = features.get("raw_links") or []
    # No path token from the soft-404 body should have leaked in as a disclosure.
    assert not any("not found" in link.lower() for link in raw_links)
    assert not any(link.endswith("/robots.txt") for link in raw_links)
