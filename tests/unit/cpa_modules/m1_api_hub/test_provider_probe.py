"""provider 存活探针报告渲染测试(需求 #5/#6,纯函数,无网络)。"""

from flaghunter.cpa_modules.m1_api_hub.provider_probe import format_providers_report


def _row(pid, prio, enabled, tags, live=None, detail=""):
    return {
        "id": pid, "name": pid, "model": f"openai/{pid}",
        "api_base": "http://x/v1", "priority": prio,
        "tags": tags, "enabled": enabled, "live": live, "detail": detail,
    }


def test_list_mode_shows_enabled_disabled():
    rows = [_row("a", 1, True, ["heavy"]), _row("z", 9, False, [])]
    out = format_providers_report(rows, refreshed=False)
    assert "enabled" in out and "disabled" in out
    assert "a" in out and "z" in out
    assert "LIVE" not in out  # 未刷新不显示存活列


def test_refresh_mode_marks_live_and_down_with_reason():
    rows = [
        _row("a", 1, True, ["heavy"], live=True, detail="ok"),
        _row("b", 2, True, ["cheap"], live=False, detail="APIError: blocked"),
        _row("z", 9, False, [], live=None, detail="disabled"),
    ]
    out = format_providers_report(rows, refreshed=True)
    assert "LIVE" in out and "DOWN" in out
    assert "APIError: blocked" in out          # #5 给出不可用原因
    assert "不可用: b" in out                    # 汇总列出挂掉的
    assert "存活 1/2 enabled" in out            # b down → 1/2


def test_empty_pool_message():
    assert "no providers" in format_providers_report([], refreshed=False)
