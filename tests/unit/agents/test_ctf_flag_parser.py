from flaghunter.agents.pa_agent.ctf_dispatcher import CTFTaskDispatcher

_FLAG_PARSER_MODULE = "flaghunter.agents.pa_agent.flag_parser"


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
