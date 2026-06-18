"""FlagHunter eval / replay harness.

确定性回归基底（治理文档点名的 agent 项目最高价值缺失层）：把"已解题"录成
``ReplayFixture``（脚本化的 recon 回显 + 探测响应 + 期望 flag），用 ``run_replay``
在确定性 ``ReplayRuntime`` 上重跑，断言同一 flag 被复现。策略/分发改动后跑回放，
一题回归即可见——无需 LLM、无需活体靶机。

详见 docs/dev/基准_验证与解题判定_2026-06-18_V1.md S5（确定性回归门）。
"""

from .replay import (
    ReplayFixture,
    ReplayResult,
    ReplayRuntime,
    list_fixtures,
    load_fixture,
    run_replay,
)

__all__ = [
    "ReplayFixture",
    "ReplayResult",
    "ReplayRuntime",
    "list_fixtures",
    "load_fixture",
    "run_replay",
]
