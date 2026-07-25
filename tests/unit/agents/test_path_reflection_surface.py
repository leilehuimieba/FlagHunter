"""Unit coverage for path-segment reflection surface derivation + injection.

Guards the SSTI reachability fix at the helper level, independent of a full
dispatcher run: (1) a discovered internal route that is NOT in the common-route
seed list is still derived as a path-reflection surface, and (2) the payload is
injected as the final path segment for such surfaces while query surfaces keep
their existing query-injection behaviour.
"""

from __future__ import annotations

from flaghunter.agents.pa_agent.render_surface import RenderSurfaceMixin


class _Surface(RenderSurfaceMixin):
    state = None


def test_discovered_non_seed_route_derived_as_path_surface():
    surface = _Surface()
    base = "http://target.example:8080"
    # /temple/ is intentionally NOT in _COMMON_PATH_REFLECTION_ROUTES.
    got = surface._collect_path_reflection_surfaces(base, ["/temple/", "/temple/enter"])
    assert f"{base}/temple/" in got


def test_offsite_links_ignored():
    surface = _Surface()
    base = "http://target.example"
    got = surface._collect_path_reflection_surfaces(base, ["http://evil.example/x/"])
    assert all("evil.example" not in u for u in got)


def test_seed_routes_present_as_fallback():
    surface = _Surface()
    base = "http://target.example"
    got = surface._collect_path_reflection_surfaces(base, [])
    assert f"{base}/shrine/" in got


def test_inject_path_surface_appends_segment():
    surface = _Surface()
    injected = surface._inject_render_payload("http://target.example/shrine/", "{{7*7}}")
    # payload becomes the final path segment (URL-encoded), no query string
    assert injected.startswith("http://target.example/shrine/")
    assert "?" not in injected
    assert "%7B%7B7%2A7%7D%7D" in injected


def test_inject_query_surface_unchanged():
    surface = _Surface()
    injected = surface._inject_render_payload("http://target.example/error?msg=Error", "{{7*7}}")
    assert injected.startswith("http://target.example/error?")
    assert "msg=" in injected


def test_inject_bare_root_stays_query():
    # A bare '/' path must NOT be treated as a path-injection surface.
    surface = _Surface()
    injected = surface._inject_render_payload("http://target.example/", "{{7*7}}")
    assert "msg=" in injected
