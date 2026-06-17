"""
健康检查与故障转移模块测试
覆盖: TC-M1-008 ~ TC-M1-016
"""

import pytest
import asyncio
from unittest.mock import Mock, patch, AsyncMock, MagicMock
from datetime import datetime

from flaghunter.cpa_modules.m1_api_hub.failover_monitor import FailoverMonitor
from flaghunter.cpa_modules.m1_api_hub.models import ProviderConfig, ProviderStatus


# ========== TC-M1-008: 健康检查成功 ==========

class TestTCM1008:
    """TC-M1-008: 健康检查成功"""

    @pytest.mark.asyncio
    @patch("litellm.acompletion")
    async def test_health_check_success(self, mock_acompletion):
        """健康检查成功返回healthy状态"""
        mock_acompletion.return_value = {
            "choices": [{"message": {"content": "OK"}}],
            "usage": {"prompt_tokens": 2, "completion_tokens": 1}
        }
        
        monitor = FailoverMonitor()
        config = ProviderConfig(
            id="test_p", name="Test", model="openai/gpt-4",
            api_base="https://api.test.com", api_key="sk-test", timeout=5
        )
        
        status = await monitor.health_check(config)
        
        assert status.state == "healthy"
        assert status.consecutive_failures == 0
        assert status.response_time_ms > 0
        assert status.last_error == ""

    @pytest.mark.asyncio
    @patch("litellm.acompletion")
    async def test_health_check_tracks_response_time(self, mock_acompletion):
        """健康检查应记录响应时间"""
        mock_acompletion.return_value = {
            "choices": [{"message": {"content": "OK"}}],
            "usage": {"total_tokens": 3}
        }
        
        monitor = FailoverMonitor()
        config = ProviderConfig(
            id="test_p", name="Test", model="openai/gpt-4",
            api_base="https://api.test.com", api_key="sk-test"
        )
        
        status = await monitor.health_check(config)
        
        assert 0 <= status.response_time_ms < 5000  # 应在合理范围内


# ========== TC-M1-009: 健康检查超时 ==========

class TestTCM1009:
    """TC-M1-009: 健康检查超时"""

    @pytest.mark.asyncio
    @patch("litellm.acompletion")
    async def test_health_check_timeout(self, mock_acompletion):
        """超时后应增加失败计数，标记为degraded"""
        mock_acompletion.side_effect = asyncio.TimeoutError("Request timeout")
        
        monitor = FailoverMonitor()
        config = ProviderConfig(
            id="test_p", name="Test", model="openai/gpt-4",
            api_base="https://api.test.com", api_key="sk-test", timeout=1
        )
        
        status = await monitor.health_check(config)
        
        assert status.state == "degraded"
        assert status.consecutive_failures == 1
        assert "timeout" in status.last_error.lower()

    @pytest.mark.asyncio
    @patch("litellm.acompletion")
    async def test_health_check_connection_error(self, mock_acompletion):
        """连接错误也应标记为失败"""
        mock_acompletion.side_effect = ConnectionError("Connection refused")
        
        monitor = FailoverMonitor()
        config = ProviderConfig(
            id="test_p", name="Test", model="openai/gpt-4",
            api_base="https://api.test.com", api_key="sk-test"
        )
        
        status = await monitor.health_check(config)
        
        assert status.consecutive_failures == 1
        assert "connection" in status.last_error.lower()

    @pytest.mark.asyncio
    @patch("litellm.acompletion")
    async def test_health_check_auth_error(self, mock_acompletion):
        """认证错误也应标记为失败"""
        mock_acompletion.side_effect = Exception("401 Unauthorized")
        
        monitor = FailoverMonitor()
        config = ProviderConfig(
            id="test_p", name="Test", model="openai/gpt-4",
            api_base="https://api.test.com", api_key="sk-test"
        )
        
        status = await monitor.health_check(config)
        
        assert status.consecutive_failures == 1
        assert "401" in status.last_error


# ========== TC-M1-010: 连续失败3次标记DOWN ==========

class TestTCM1010:
    """TC-M1-010: 连续失败3次标记DOWN"""

    @pytest.mark.asyncio
    @patch("litellm.acompletion")
    async def test_consecutive_3_failures_mark_down(self, mock_acompletion):
        """连续失败3次后状态应为down"""
        mock_acompletion.side_effect = asyncio.TimeoutError("timeout")
        
        monitor = FailoverMonitor()
        config = ProviderConfig(
            id="test_p", name="Test", model="openai/gpt-4",
            api_base="https://api.test.com", api_key="sk-test", timeout=1
        )
        
        # 第1次检查
        s1 = await monitor.health_check(config)
        assert s1.state == "degraded"
        assert s1.consecutive_failures == 1
        
        # 第2次检查
        s2 = await monitor.health_check(config)
        assert s2.state == "degraded"
        assert s2.consecutive_failures == 2
        
        # 第3次检查 → DOWN
        s3 = await monitor.health_check(config)
        assert s3.state == "down"
        assert s3.consecutive_failures == 3

    @pytest.mark.asyncio
    @patch("litellm.acompletion")
    async def test_failure_counter_resets_on_success(self, mock_acompletion):
        """成功一次后失败计数应重置"""
        # 第1次超时，第2次成功
        monitor = FailoverMonitor()
        config = ProviderConfig(
            id="test_p", name="Test", model="openai/gpt-4",
            api_base="https://api.test.com", api_key="sk-test", timeout=1
        )
        
        # 第1次: 超时
        mock_acompletion.side_effect = asyncio.TimeoutError("timeout")
        s1 = await monitor.health_check(config)
        assert s1.consecutive_failures == 1
        
        # 第2次: 成功
        mock_acompletion.side_effect = None
        mock_acompletion.return_value = {
            "choices": [{"message": {"content": "OK"}}],
            "usage": {"total_tokens": 3}
        }
        s2 = await monitor.health_check(config)
        assert s2.consecutive_failures == 0
        assert s2.consecutive_successes == 1
        assert s2.state == "healthy"

    def test_mark_failed_increments_counter(self):
        """mark_failed应递增失败计数"""
        monitor = FailoverMonitor()
        
        monitor.mark_failed("p1")
        assert monitor._states["p1"]["consecutive_failures"] == 1
        assert monitor._states["p1"]["state"] == "degraded"
        
        monitor.mark_failed("p1")
        assert monitor._states["p1"]["consecutive_failures"] == 2
        assert monitor._states["p1"]["state"] == "degraded"
        
        monitor.mark_failed("p1")
        assert monitor._states["p1"]["consecutive_failures"] == 3
        assert monitor._states["p1"]["state"] == "down"


# ========== TC-M1-011: DEGRADED状态不影响调度 ==========

class TestTCM1011:
    """TC-M1-011: DEGRADED状态不影响调度"""

    def test_degraded_is_active(self):
        """DEGRADED状态的Provider仍算active"""
        from flaghunter.cpa_modules.m1_api_hub.provider_manager import ProviderManager
        
        manager = ProviderManager()
        manager.register_provider(ProviderConfig(
            id="p_degraded", name="P-Degraded", model="gpt-4",
            api_base="https://api.com", api_key="sk", priority=1
        ))
        manager._health_states["p_degraded"] = "degraded"
        
        active = manager.get_active_providers()
        assert any(p.id == "p_degraded" for p in active)

    def test_degraded_over_down(self):
        """DEGRADED优于DOWN——只有healthy和degraded能参与调度"""
        from flaghunter.cpa_modules.m1_api_hub.provider_manager import ProviderManager
        
        manager = ProviderManager()
        manager.register_provider(ProviderConfig(
            id="p_deg", name="P-Deg", model="gpt-4",
            api_base="https://api.com", api_key="sk", priority=1
        ))
        manager.register_provider(ProviderConfig(
            id="p_down", name="P-Down", model="gpt-4",
            api_base="https://api.com", api_key="sk", priority=2
        ))
        manager._health_states = {"p_deg": "degraded", "p_down": "down"}
        
        active = manager.get_active_providers()
        assert any(p.id == "p_deg" for p in active)
        assert not any(p.id == "p_down" for p in active)


# ========== TC-M1-012: DOWN状态不参与调度 ==========

class TestTCM1012:
    """TC-M1-012: DOWN状态不参与调度"""

    def test_down_excluded(self):
        """DOWN的Provider不在active列表"""
        from flaghunter.cpa_modules.m1_api_hub.provider_manager import ProviderManager
        
        manager = ProviderManager()
        manager.register_provider(ProviderConfig(
            id="p_down", name="P-Down", model="gpt-4",
            api_base="https://api.com", api_key="sk", priority=1
        ))
        manager._health_states["p_down"] = "down"
        
        active = manager.get_active_providers()
        assert not any(p.id == "p_down" for p in active)

    def test_select_best_raises_when_all_down(self):
        """全部DOWN时应抛出异常"""
        from flaghunter.cpa_modules.m1_api_hub.provider_manager import ProviderManager
        
        manager = ProviderManager()
        for i in range(3):
            manager.register_provider(ProviderConfig(
                id=f"p{i}", name=f"P{i}", model="gpt-4",
                api_base=f"https://api{i}.com", api_key=f"sk{i}", priority=i
            ))
            manager._health_states[f"p{i}"] = "down"
        
        with pytest.raises(Exception, match="没有可用的Provider"):
            manager.select_best_provider()


# ========== TC-M1-013: 故障转移到备用Provider ==========

class TestTCM1013:
    """TC-M1-013: 故障转移到备用Provider"""

    def test_fallback_to_backup(self):
        """主Provider DOWN时自动切换到备用"""
        from flaghunter.cpa_modules.m1_api_hub.provider_manager import ProviderManager
        
        manager = ProviderManager()
        manager.register_provider(ProviderConfig(
            id="primary", name="主渠道", model="gpt-4",
            api_base="https://primary.com", api_key="sk1", priority=1
        ))
        manager.register_provider(ProviderConfig(
            id="backup", name="备用渠道", model="gpt-4",
            api_base="https://backup.com", api_key="sk2", priority=2
        ))
        
        manager._health_states = {"primary": "down", "backup": "healthy"}
        
        selected = manager.select_best_provider()
        assert selected.id == "backup"

    def test_fallback_skips_disabled(self):
        """故障转移时跳过禁用的Provider"""
        from flaghunter.cpa_modules.m1_api_hub.provider_manager import ProviderManager
        
        manager = ProviderManager()
        manager.register_provider(ProviderConfig(
            id="primary", name="主渠道", model="gpt-4",
            api_base="https://pri.com", api_key="sk1", priority=1, enabled=False
        ))
        manager.register_provider(ProviderConfig(
            id="backup", name="备用渠道", model="gpt-4",
            api_base="https://bak.com", api_key="sk2", priority=2, enabled=True
        ))
        
        manager._health_states = {"primary": "healthy", "backup": "healthy"}
        
        selected = manager.select_best_provider()
        assert selected.id == "backup"  # primary被禁用，只能选backup

    @pytest.mark.asyncio
    @patch("litellm.acompletion")
    async def test_fallback_chain_monitors_all(self, mock_acompletion):
        """FailoverMonitor应监控所有Provider"""
        monitor = FailoverMonitor()
        
        for i in range(3):
            config = ProviderConfig(
                id=f"p{i}", name=f"P{i}", model="gpt-4",
                api_base=f"https://api{i}.com", api_key=f"sk{i}"
            )
            monitor.register_provider(config)
        
        assert len(monitor._providers) == 3
        assert len(monitor._states) == 3


# ========== TC-M1-014: 降级链全部失败时报错 ==========

class TestTCM1014:
    """TC-M1-014: 降级链全部失败时报错"""

    def test_all_providers_down_raises(self):
        """全部DOWN时抛出异常"""
        from flaghunter.cpa_modules.m1_api_hub.provider_manager import ProviderManager
        
        manager = ProviderManager()
        for i in range(3):
            manager.register_provider(ProviderConfig(
                id=f"p{i}", name=f"P{i}", model="gpt-4",
                api_base=f"https://api{i}.com", api_key=f"sk{i}", priority=i
            ))
            manager._health_states[f"p{i}"] = "down"
        
        with pytest.raises(Exception) as exc_info:
            manager.select_best_provider()
        
        assert "没有可用的Provider" in str(exc_info.value)

    def test_all_disabled_raises(self):
        """全部禁用时也抛出异常"""
        from flaghunter.cpa_modules.m1_api_hub.provider_manager import ProviderManager
        
        manager = ProviderManager()
        manager.register_provider(ProviderConfig(
            id="p1", name="P1", model="gpt-4",
            api_base="https://api.com", api_key="sk", priority=1, enabled=False
        ))
        
        with pytest.raises(Exception, match="没有可用的Provider"):
            manager.select_best_provider()

    def test_get_fallback_chain(self):
        """获取降级链应返回可用Provider列表"""
        monitor = FailoverMonitor()
        
        for i in range(3):
            config = ProviderConfig(
                id=f"p{i}", name=f"P{i}", model="gpt-4",
                api_base=f"https://api{i}.com", api_key=f"sk{i}", priority=i+1
            )
            monitor.register_provider(config)
        
        monitor._states["p2"]["state"] = "down"  # p2 DOWN
        
        chain = monitor.get_fallback_chain("gpt-4")
        assert "p2" not in chain  # DOWN的不在链中
        assert chain == ["p0", "p1"]  # 按优先级排序


# ========== TC-M1-015: DOWN Provider自动恢复 ==========

class TestTCM1015:
    """TC-M1-015: DOWN Provider自动恢复"""

    @pytest.mark.asyncio
    @patch("litellm.acompletion")
    async def test_auto_recovery_sequence(self, mock_acompletion):
        """DOWN的Provider连续2次成功后进入recovering"""
        mock_acompletion.return_value = {
            "choices": [{"message": {"content": "OK"}}],
            "usage": {"total_tokens": 3}
        }
        
        monitor = FailoverMonitor()
        config = ProviderConfig(
            id="recover_p", name="Recover", model="gpt-4",
            api_base="https://api.com", api_key="sk", timeout=5
        )
        
        # 先标记为DOWN
        monitor._states["recover_p"] = {
            "state": "down",
            "consecutive_failures": 3,
            "consecutive_successes": 0,
            "last_check_time": None,
            "last_error": "connection refused"
        }
        
        # 第1次恢复检查 → 成功
        s1 = await monitor.health_check(config)
        assert s1.consecutive_successes == 1
        assert s1.state == "down"  # 还需要1次
        
        # 第2次恢复检查 → 成功，进入recovering
        s2 = await monitor.health_check(config)
        assert s2.consecutive_successes == 2
        assert s2.state == "recovering"

    def test_mark_recovered(self):
        """mark_recovered应重置状态为healthy"""
        monitor = FailoverMonitor()
        monitor._states["p1"] = {
            "state": "down",
            "consecutive_failures": 3,
            "consecutive_successes": 0,
            "last_error": "timeout"
        }
        
        monitor.mark_recovered("p1")
        
        assert monitor._states["p1"]["state"] == "healthy"
        assert monitor._states["p1"]["consecutive_failures"] == 0
        assert monitor._states["p1"]["last_error"] == ""


# ========== TC-M1-016: 恢复后真实请求验证 ==========

class TestTCM1016:
    """TC-M1-016: 恢复后真实请求验证"""

    @pytest.mark.asyncio
    @patch("litellm.acompletion")
    async def test_validate_with_real_request_success(self, mock_acompletion):
        """真实请求验证成功后变为healthy"""
        mock_acompletion.return_value = {
            "choices": [{"message": {"content": "验证成功"}}],
            "usage": {"prompt_tokens": 10, "completion_tokens": 5}
        }
        
        monitor = FailoverMonitor()
        config = ProviderConfig(
            id="validate_p", name="Validate", model="openai/gpt-4",
            api_base="https://api.com", api_key="sk"
        )
        
        # 设置为recovering
        monitor._states["validate_p"] = {
            "state": "recovering",
            "consecutive_successes": 2,
            "consecutive_failures": 0
        }
        
        result = await monitor.validate_with_real_request(config)
        
        assert result is True
        assert monitor._states["validate_p"]["state"] == "healthy"

    @pytest.mark.asyncio
    @patch("litellm.acompletion")
    async def test_validate_with_real_request_failure(self, mock_acompletion):
        """真实请求验证失败后回到down"""
        mock_acompletion.side_effect = asyncio.TimeoutError("still down")
        
        monitor = FailoverMonitor()
        config = ProviderConfig(
            id="validate_p", name="Validate", model="openai/gpt-4",
            api_base="https://api.com", api_key="sk"
        )
        
        monitor._states["validate_p"] = {
            "state": "recovering",
            "consecutive_successes": 2,
            "consecutive_failures": 0
        }
        
        result = await monitor.validate_with_real_request(config)
        
        assert result is False
        assert monitor._states["validate_p"]["state"] == "down"
        assert monitor._states["validate_p"]["consecutive_failures"] == 2

    def test_recovery_callback(self):
        """恢复时应触发回调"""
        monitor = FailoverMonitor()
        callback_called = []
        
        def on_recover(provider_id):
            callback_called.append(provider_id)
        
        monitor.on_provider_recovered(on_recover)
        monitor._states["p1"] = {"state": "down", "consecutive_failures": 3}
        
        monitor.mark_recovered("p1")
        
        assert "p1" in callback_called
