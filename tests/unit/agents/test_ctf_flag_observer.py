from flaghunter.agents.pa_agent.ctf_dispatcher import CTFTaskDispatcher

_FLAG_OBSERVER_MODULE = "flaghunter.agents.pa_agent.flag_observer"


def test_observe_flag_lives_in_flag_observer_mixin():
    assert CTFTaskDispatcher._observe_flag.__module__ == _FLAG_OBSERVER_MODULE
