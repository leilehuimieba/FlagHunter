"""契约测试 — 锁定 ConsensusMechanism.get_vote_status 公共 API 行为。

背景(卡 C6)：``get_vote_status(self, vote_id)`` 是挂在已接线类
``ConsensusMechanism`` 上的公共方法，全仓零调用点。但其兄弟方法
``propose_binary`` / ``vote`` / ``propose_priority_ranking`` 被
``swarm_commands.py`` 真实消费（``/swarm propose|vote|consensus`` 命令），
``get_vote_status`` 在语义上与 ``propose`` / ``vote`` / ``close_vote`` 对称——
属投票状态查询契约，是预留对外的 swarm 协议接口而非纯遗弃死代码。

判定：保留，并用本测试把"无人调的公共方法"转成"有测试锁定的契约"。

锁定的契约（见 get_vote_status docstring）：
  * 返回 dict，含 total_votes / options / deadline / is_open 四个键。
  * 未知 vote_id → 空状态（0 票、空选项、deadline=0.0、is_open=False）。
  * 开放投票 → is_open=True、total_votes 反映已记录票数、
    options 回显原始选项、deadline == start_time + timeout。
  * 关闭投票 → is_open=False。
"""
from __future__ import annotations

import time

import pytest

from flaghunter.cpa_modules.m5_swarm_link.consensus_mechanism import (
    ConsensusMechanism,
)


class _StubMessenger:
    """最小 messenger 替身：仅暴露 get_vote_status / vote 实际触达的属性。

    get_vote_status 只读 self._active_votes，不碰 messenger；
    vote() 会调用 messenger.send(...)，故提供一个吞掉调用的异步 send。
    """

    def __init__(self, agent_id: str = "tester") -> None:
        self.agent_id = agent_id
        self.blackboard = None

    async def send(self, *args, **kwargs) -> None:
        return None


def _make_mechanism() -> ConsensusMechanism:
    """构造一个带 stub messenger 的共识机制（不触发任何网络/黑板 IO）。"""
    return ConsensusMechanism(messenger=_StubMessenger())  # type: ignore[arg-type]


def test_get_vote_status_unknown_vote_returns_empty():
    """未知 vote_id → 空状态字典，键齐全。"""
    cm = _make_mechanism()
    status = cm.get_vote_status("does_not_exist")
    assert status == {
        "total_votes": 0,
        "options": [],
        "deadline": 0.0,
        "is_open": False,
    }


def test_get_vote_status_open_vote_reports_contract():
    """开放投票 → is_open=True，total_votes/options/deadline 全部正确。"""
    cm = _make_mechanism()
    vote_id = "vote_abc123"
    start = time.time()
    timeout = 30.0
    # 直接铺设一条开放投票记录（镜像 propose() 写入 _active_votes 的形态）
    cm._active_votes[vote_id] = {
        "question": "Q?",
        "options": ["yes", "no"],
        "votes": [
            {"vote_id": vote_id, "choice": "yes", "confidence": 1.0, "voter": "a"},
            {"vote_id": vote_id, "choice": "no", "confidence": 1.0, "voter": "b"},
        ],
        "start_time": start,
        "timeout": timeout,
        "status": "open",
    }

    status = cm.get_vote_status(vote_id)
    assert status["is_open"] is True
    assert status["total_votes"] == 2
    assert status["options"] == ["yes", "no"]
    assert status["deadline"] == pytest.approx(start + timeout)


def test_get_vote_status_closed_vote_is_not_open():
    """关闭投票 → is_open=False，但票数/选项仍可查询。"""
    cm = _make_mechanism()
    vote_id = "vote_closed1"
    start = time.time()
    cm._active_votes[vote_id] = {
        "question": "Q?",
        "options": ["a", "b", "c"],
        "votes": [{"vote_id": vote_id, "choice": "a", "confidence": 1.0, "voter": "x"}],
        "start_time": start,
        "timeout": 10.0,
        "status": "closed",
    }

    status = cm.get_vote_status(vote_id)
    assert status["is_open"] is False
    assert status["total_votes"] == 1
    assert status["options"] == ["a", "b", "c"]


@pytest.mark.asyncio
async def test_get_vote_status_after_vote_records_ballot():
    """端到端：开票后用公共 vote() 投一票，get_vote_status 计入该票。

    走真实公共路径（vote() 把 ballot 追加进 _active_votes），坐实
    get_vote_status 的 total_votes 与 vote() 的写入语义一致。
    """
    cm = _make_mechanism()
    vote_id = "vote_e2e001"
    cm._active_votes[vote_id] = {
        "question": "deploy?",
        "options": ["yes", "no"],
        "votes": [],
        "start_time": time.time(),
        "timeout": 5.0,
        "status": "open",
    }

    before = cm.get_vote_status(vote_id)
    assert before["total_votes"] == 0
    assert before["is_open"] is True

    await cm.vote(vote_id, choice="yes", confidence=0.9)

    after = cm.get_vote_status(vote_id)
    assert after["total_votes"] == 1
    assert after["is_open"] is True
