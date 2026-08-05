import base64

from flaghunter.agents.pa_agent.ctf_dispatcher import CTFTaskDispatcher
from flaghunter.agents.pa_agent.flag_parser import FlagParserMixin

_FLAG_PARSER_MODULE = "flaghunter.agents.pa_agent.flag_parser"


class _BareFlagParser(FlagParserMixin):
    """Minimal host: _extract_flag resolves entirely against the mixin."""

    state = None


def test_extract_flag_decodes_data_uri_base64_iframe():
    # Real Fakebook shape: the file:// SSRF read of flag.php is rendered back
    # into an <iframe src='data:text/html;base64,...'>, so the flag only exists
    # base64-encoded. The raw-body scan must fall through to a decode + re-scan.
    flag = "CTF2{ba8c0ee4-cf5b-4133-a1e0-252913ef440d}"
    payload = f'<?php\n\n$flag = "{flag}";\nexit(0);\n'
    encoded = base64.b64encode(payload.encode()).decode()
    body = (
        "<p>the contents of his/her blog</p>"
        f"<iframe width='100%' height='10em' src='data:text/html;base64,{encoded}'>"
        "</iframe>"
    )
    assert _BareFlagParser()._extract_flag(body) == flag


def test_extract_flag_prefers_plaintext_over_base64_decode():
    plain = "CTF2{plain-body-flag}"
    encoded = base64.b64encode(b"CTF2{decoded-flag}").decode()
    body = f"{plain} <img src='data:image/png;base64,{encoded}'>"
    assert _BareFlagParser()._extract_flag(body) == plain


def test_extract_flag_ignores_non_flag_base64_blobs():
    encoded = base64.b64encode(b"just an ordinary inline image, no flag here").decode()
    body = f"<img src='data:image/png;base64,{encoded}'>"
    assert _BareFlagParser()._extract_flag(body) is None


def test_flag_parser_cluster_lives_in_flag_parser_mixin():
    for name in (
        "_extract_flag",
        "_extract_php_var_dump_strings",
        "_extract_runtime_flag",
        "_is_rejected_flag",
        "_looks_like_css_false_flag",
        "_load_rejected_flags",
        "_store_flag_candidate",
    ):
        assert getattr(CTFTaskDispatcher, name).__module__ == _FLAG_PARSER_MODULE
