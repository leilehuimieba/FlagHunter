from __future__ import annotations

import pytest

from flaghunter.cpa_modules.m2_ctf_kit.flag_submitter import (
    detect_platform_from_url,
    get_platform_snapshot,
)
from flaghunter.agents.pa_agent.ctf_dispatcher import CTFTaskDispatcher
from flaghunter.agents.pa_agent.ctf_state import CTFState
from tests.unit.agents.test_ctf_dispatcher import _DispatcherMissingReconDepsRuntime


def test_detect_platform_from_url_supports_buuoj_and_ctfshow():
    assert (
        detect_platform_from_url(
            "http://31beacc4-11c9-4f60-922d-7ef81c01556d.node5.buuoj.cn:81"
        )
        == "buuoj"
    )
    assert detect_platform_from_url("https://web.ctf.show/challenges") == "ctfshow"


@pytest.mark.asyncio
async def test_get_platform_snapshot_marks_buuoj_as_read_only_platform():
    snapshot = await get_platform_snapshot(
        platform_type="buuoj",
        base_url="http://node5.buuoj.cn:81",
    )

    assert snapshot["success"] is True
    assert snapshot["platform_type"] == "buuoj"
    assert snapshot["supports_submit"] is False


def test_ctf_dispatcher_infers_buuoj_platform_profile_from_target_url():
    dispatcher = CTFTaskDispatcher(
        runtime=_DispatcherMissingReconDepsRuntime(),
        progress_callback=None,
    )
    dispatcher.state = CTFState(
        target="http://31beacc4-11c9-4f60-922d-7ef81c01556d.node5.buuoj.cn:81",
        goal="拿到flag",
    )

    profile = dispatcher._infer_platform_profile(
        "http://31beacc4-11c9-4f60-922d-7ef81c01556d.node5.buuoj.cn:81"
    )

    assert profile["platform_type"] == "buuoj"
    assert profile["base_url"] == "http://31beacc4-11c9-4f60-922d-7ef81c01556d.node5.buuoj.cn:81"
    assert profile["auto_submit"] is False
    assert profile["challenge_id"] is None
