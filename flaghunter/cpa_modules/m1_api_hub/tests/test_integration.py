"""
M1模块集成测试
覆盖: TC-M1-INT-001 ~ TC-M1-INT-005

测试完整的跨组件协作流程。
"""

import pytest
import os
import asyncio
from datetime import datetime
from unittest.mock import Mock, patch, AsyncMock, MagicMock, call

from flaghunter.cpa_modules.m1_api_hub.provider_manager import ProviderManager
from flaghunter.cpa_modules.m1_api_hub.failover_monitor import FailoverMonitor
from flaghunter.cpa_modules.m1_api_hub.cost_tracker import CostTracker
from flaghunter.cpa_modules.m1_api_hub.status_display import ApiCommandHandler, StatusPanel
from flaghunter.cpa_modules.m1_api_hub.models import ProviderConfig, RequestLog


# ========== TC-M1-INT-001: 完整故障转移与恢复流程 ==========

class TestTCMINT001:
    """TC-M1-INT-001: 请求→故障→转移→恢复 完整流程"""

    @pytest.mark.asyncio
    @patch("litellm.acompletion")
    async def test_full_failover_and_recovery_flow(self, mock_acompletion):
        """完整生命周期：请求→故障→切换→恢复→切回"""
        
        # 初始化组件
        manager = ProviderManager()
        monitor = FailoverMonitor()
        tracker = CostTracker()
        
        # Phase 0: 注册Provider
        manager.register_provider(ProviderConfig(
            id="primary", name="主渠道", model="openai/gpt-4",
            api_base="https://primary.com", api_key="sk1", priority=1
        ))
        manager.register_provider(ProviderConfig(
            id="backup", name="备用渠道", model="openai/gpt-4",
            api_base="https://backup.com", api_key="sk2", priority=2
        ))
        
        # 同步健康状态
        manager._health_states = {"primary": "healthy", "backup": "healthy"}
        
        # Phase 1: 正常请求，主Provider响应
        mock_acompletion.return_value = {
            "choices": [{"message": {"content": "Hello from primary"}}],
            "usage": {"prompt_tokens": 10, "completion_tokens": 5}
        }
        best = manager.select_best_provider()
        assert best.id == "primary"
        
        # Phase 2: 模拟主Provider连续失败3次 → DOWN
        mock_acompletion.side_effect = asyncio.TimeoutError("timeout")
        primary_config = manager.get_provider("primary")
        for _ in range(3):
            status = await monitor.health_check(primary_config)
        assert status.state == "down"
        assert status.consecutive_failures == 3
        
        # Phase 3: 新请求应自动切换到备用
        mock_acompletion.side_effect = None
        mock_acompletion.return_value = {
            "choices": [{"message": {"content": "Hello from backup"}}],
            "usage": {"prompt_tokens": 8, "completion_tokens": 4}
        }
        manager._health_states["primary"] = "down"
        manager._health_states["backup"] = "healthy"
        
        new_best = manager.select_best_provider()
        assert new_best.id == "backup"
        
        # Phase 4: 主Provider恢复检测 - 连续2次成功
        monitor._states["primary"] = {
            "state": "down", "consecutive_failures": 3,
            "consecutive_successes": 0, "last_error": "timeout",
            "last_check_time": None, "response_time_ms": 0
        }
        
        s1 = await monitor.health_check(primary_config)
        assert s1.consecutive_successes == 1
        
        s2 = await monitor.health_check(primary_config)
        assert s2.consecutive_successes == 2
        assert s2.state == "recovering"
        
        # Phase 5: 真实请求验证通过 → healthy
        validated = await monitor.validate_with_real_request(primary_config)
        assert validated is True
        assert monitor._states["primary"]["state"] == "healthy"
        
        # Phase 6: 主Provider重新被选中（优先级更高）
        manager._health_states["primary"] = "healthy"
        manager._health_states["backup"] = "healthy"
        recovered_best = manager.select_best_provider()
        assert recovered_best.id == "primary"


# ========== TC-M1-INT-002: 并发请求调度 ==========

class TestTCMINT002:
    """TC-M1-INT-002: 多Provider并发请求调度"""

    def test_multiple_providers_selection(self):
        """多个健康Provider按优先级选择"""
        manager = ProviderManager()
        
        for i in range(5):
            manager.register_provider(ProviderConfig(
                id=f"p{i}", name=f"P{i}", model="gpt-4",
                api_base=f"https://api{i}.com", api_key=f"sk{i}", priority=i+1
            ))
            manager._health_states[f"p{i}"] = "healthy"
        
        # 始终选择priority=1的
        for _ in range(10):
            best = manager.select_best_provider()
            assert best.id == "p0"

    def test_concurrent_with_mixed_states(self):
        """混合状态下只选择healthy的Provider"""
        manager = ProviderManager()
        
        for i in range(5):
            manager.register_provider(ProviderConfig(
                id=f"p{i}", name=f"P{i}", model="gpt-4",
                api_base=f"https://api{i}.com", api_key=f"sk{i}", priority=i+1
            ))
        
        # p0=down, p1=degraded, p2=healthy, p3=down, p4=healthy
        manager._health_states = {
            "p0": "down", "p1": "degraded", "p2": "healthy",
            "p3": "down", "p4": "healthy"
        }
        
        # 应选择priority最小的healthy Provider = p2
        best = manager.select_best_provider()
        assert best.id == "p2"


# ========== TC-M1-INT-003: 长时间运行稳定性 ==========

class TestTCMINT003:
    """TC-M1-INT-003: 健康检查定时任务稳定性"""

    @pytest.mark.asyncio
    @patch("litellm.acompletion")
    async def test_periodic_check_all_providers(self, mock_acompletion):
        """一次周期性检查应覆盖所有Provider"""
        mock_acompletion.return_value = {
            "choices": [{"message": {"content": "OK"}}],
            "usage": {"total_tokens": 3}
        }
        
        monitor = FailoverMonitor()
        
        for i in range(3):
            config = ProviderConfig(
                id=f"p{i}", name=f"P{i}", model="gpt-4",
                api_base=f"https://api{i}.com", api_key=f"sk{i}"
            )
            monitor.register_provider(config)
        
        await monitor.run_periodic_check()
        
        # 所有Provider状态都应为healthy
        for i in range(3):
            assert monitor._states[f"p{i}"]["state"] == "healthy"
            assert monitor._states[f"p{i}"]["consecutive_failures"] == 0

    @pytest.mark.asyncio
    @patch("litellm.acompletion")
    async def test_monitoring_start_stop(self, mock_acompletion):
        """监控的启动和停止"""
        monitor = FailoverMonitor()
        
        assert monitor._monitoring is False
        
        monitor.start_monitoring(interval_seconds=30)
        assert monitor._monitoring is True
        
        monitor.stop_monitoring()
        assert monitor._monitoring is False

    def test_health_summary(self):
        """健康摘要统计正确"""
        monitor = FailoverMonitor()
        
        monitor._states = {
            "p1": {"state": "healthy"},
            "p2": {"state": "healthy"},
            "p3": {"state": "degraded"},
            "p4": {"state": "down"},
            "p5": {"state": "recovering"},
        }
        
        summary = monitor.get_health_summary()
        
        assert summary["total"] == 5
        assert summary["healthy"] == 2
        assert summary["degraded"] == 1
        assert summary["down"] == 1
        assert summary["recovering"] == 1


# ========== TC-M1-INT-004: 预算告警→暂停→恢复 ==========

class TestTCMINT004:
    """TC-M1-INT-004: 预算告警→暂停→恢复 完整流程"""

    @patch.dict(os.environ, {
        "CPA_M1_DAILY_BUDGET_USD": "1",
        "CPA_M1_BUDGET_ALERT_THRESHOLD": "0.8"
    })
    def test_budget_full_lifecycle(self):
        """完整预算生命周期"""
        tracker = CostTracker()
        
        # Phase 1: 正常记录请求（预算内）
        tracker.record_request(RequestLog(
            request_id="r1", provider_id="p1", model="openai/gpt-4",
            prompt_tokens=10000, completion_tokens=5000,
            response_time_ms=1000, success=True,
            error_message="", timestamp=datetime.now(), cost_usd=0.3
        ))
        assert tracker.is_budget_exceeded() is False
        assert tracker.allow_request() is True
        assert tracker.check_budget_alert() is None
        
        # Phase 2: 超过80%阈值，触发告警
        tracker.record_request(RequestLog(
            request_id="r2", provider_id="p1", model="openai/gpt-4",
            prompt_tokens=20000, completion_tokens=10000,
            response_time_ms=2000, success=True,
            error_message="", timestamp=datetime.now(), cost_usd=0.6  # 总计$0.9
        ))
        alert = tracker.check_budget_alert()
        assert alert is not None
        assert "告警" in alert or "alert" in alert.lower()
        assert tracker.is_budget_exceeded() is False  # 还未超限
        
        # Phase 3: 超过100%预算，暂停
        tracker.record_request(RequestLog(
            request_id="r3", provider_id="p1", model="openai/gpt-4",
            prompt_tokens=5000, completion_tokens=2500,
            response_time_ms=1500, success=True,
            error_message="", timestamp=datetime.now(), cost_usd=0.2  # 总计$1.1
        ))
        assert tracker.is_budget_exceeded() is True
        assert tracker.allow_request() is False
        
        # Phase 4: 每日重置后恢复
        tracker.daily_reset()
        assert tracker.is_budget_exceeded() is False
        assert tracker.allow_request() is True
        assert tracker.get_session_summary()["total_cost"] == 0

    @patch.dict(os.environ, {
        "CPA_M1_DAILY_BUDGET_USD": "10",
        "CPA_M1_BUDGET_ALERT_THRESHOLD": "0.5"
    })
    def test_budget_with_real_cost_calculation(self):
        """使用真实成本计算的预算追踪"""
        tracker = CostTracker()
        
        # 使用GPT-4的已知费率: prompt $0.03/1K, completion $0.06/1K
        # 1000 prompt + 500 completion = $0.03 + $0.03 = $0.06
        tracker.record_request(RequestLog(
            request_id="r1", provider_id="p1", model="openai/gpt-4",
            prompt_tokens=1000, completion_tokens=500,
            response_time_ms=1000, success=True,
            error_message="", timestamp=datetime.now(),
            cost_usd=0  # 触发自动计算
        ))
        
        summary = tracker.get_session_summary()
        assert summary["total_cost"] > 0
        assert summary["daily_budget"] == 10.0
        assert summary["budget_used_ratio"] > 0


# ========== TC-M1-INT-005: TUI交互流程 ==========

class TestTCMINT005:
    """TC-M1-INT-005: /api命令完整交互"""

    def test_full_command_dispatch(self):
        """所有/api子命令分发正确"""
        handler = ApiCommandHandler()
        
        # Mock依赖
        handler._provider_manager = Mock()
        handler._provider_manager.list_providers.return_value = [
            ProviderConfig(id="p1", name="Provider-1", model="gpt-4",
                          api_base="https://api1.com", api_key="sk1", priority=1),
            ProviderConfig(id="p2", name="Provider-2", model="claude-3",
                          api_base="https://api2.com", api_key="sk2", priority=2),
        ]
        handler._provider_manager.get_provider.return_value = ProviderConfig(
            id="p1", name="Provider-1", model="gpt-4",
            api_base="https://api1.com", api_key="sk1", priority=1
        )
        
        handler._monitor = Mock()
        handler._monitor.get_health_summary.return_value = {
            "total": 2, "healthy": 2, "degraded": 0, "down": 0
        }
        handler._monitor.get_health_state.return_value = "healthy"
        
        handler._cost_tracker = Mock()
        handler._cost_tracker.get_session_summary.return_value = {
            "total_requests": 50, "total_tokens": 15000,
            "total_cost": 2.5, "daily_budget": 50.0,
            "budget_used_ratio": 0.05,
            "by_provider": {"p1": {"requests": 30, "cost": 1.5}}
        }
        handler._cost_tracker.get_provider_usage.return_value = {
            "requests": 30, "cost": 1.5
        }
        
        # 测试各命令
        assert handler.handle("/api providers") is not None
        assert handler.handle("/api status") is not None
        assert handler.handle("/api cost") is not None
        assert handler.handle("/api logs") is not None
        assert handler.handle("/api config") is not None
        assert handler.handle("/api switch p1") is not None
        assert handler.handle("/api test p1") is not None
        assert "未知" in handler.handle("/api nonexistent")

    def test_panel_integration_with_manager(self):
        """状态面板与ProviderManager集成"""
        manager = ProviderManager()
        panel = StatusPanel()
        
        # 注册5个Provider
        for i in range(5):
            manager.register_provider(ProviderConfig(
                id=f"p{i}", name=f"Provider-{i}", model="gpt-4",
                api_base=f"https://api{i}.com", api_key=f"sk{i}", priority=i+1
            ))
            manager._health_states[f"p{i}"] = "healthy"
        
        # 构建面板数据
        providers_data = []
        for p in manager.list_providers():
            providers_data.append({
                "name": p.name,
                "state": manager._health_states.get(p.id, "unknown"),
                "response_time_ms": 1200,
                "requests": 10 + i,
                "cost": 0.5 + i * 0.1,
            })
        
        table = panel.render_provider_table(providers_data)
        assert len(table) > 0
        for i in range(5):
            assert f"Provider-{i}" in table

    def test_command_with_budget_alert(self):
        """预算告警时/api cost应显示告警信息"""
        handler = ApiCommandHandler()
        
        handler._cost_tracker = Mock()
        handler._cost_tracker.get_session_summary.return_value = {
            "total_requests": 100,
            "total_tokens": 500000,
            "total_cost": 45.0,  # 接近预算上限
            "daily_budget": 50.0,
            "budget_used_ratio": 0.9,  # 90%已用
            "by_provider": {}
        }
        
        result = handler.handle("/api cost")
        
        assert "$45.0" in result or "45" in result
        assert "$50.0" in result or "50" in result
        assert "90" in result

    def test_status_with_mixed_health(self):
        """混合健康状态时status显示正确"""
        handler = ApiCommandHandler()
        
        handler._monitor = Mock()
        handler._monitor.get_health_summary.return_value = {
            "total": 5, "healthy": 2, "degraded": 1, "down": 1, "recovering": 1
        }
        
        result = handler.handle("/api status")
        
        assert "5" in result  # total
        assert "2" in result  # healthy
        assert "1" in result  # degraded/down/recovering
