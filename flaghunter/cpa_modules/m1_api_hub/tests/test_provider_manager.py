"""
Provider管理模块测试
覆盖: TC-M1-001 ~ TC-M1-007
"""

import pytest
import os
from unittest.mock import Mock, patch, MagicMock

# 导入被测模块
from flaghunter.cpa_modules.m1_api_hub.provider_manager import ProviderManager
from flaghunter.cpa_modules.m1_api_hub.models import ProviderConfig


# ========== TC-M1-001: 注册单个Provider ==========

class TestTCM1001:
    """TC-M1-001: 注册单个Provider"""

    def test_register_single_provider(self):
        """注册单个Provider后能正确查询"""
        manager = ProviderManager()
        config = ProviderConfig(
            id="test_provider_1",
            name="测试Provider-A",
            model="openai/gpt-4",
            api_base="https://api.test-a.com/v1",
            api_key="sk-test-key-1",
            timeout=30,
            priority=1,
            enabled=True
        )
        
        manager.register_provider(config)
        
        assert len(manager.list_providers()) == 1
        result = manager.get_provider("test_provider_1")
        assert result is not None
        assert result.id == "test_provider_1"
        assert result.name == "测试Provider-A"
        assert result.model == "openai/gpt-4"
        assert result.priority == 1
        assert result.enabled is True

    def test_register_duplicate_updates(self):
        """重复注册同一ID应覆盖"""
        manager = ProviderManager()
        manager.register_provider(ProviderConfig(
            id="same", name="Original", model="gpt-4",
            api_base="https://orig.com", api_key="sk1", priority=1
        ))
        manager.register_provider(ProviderConfig(
            id="same", name="Updated", model="claude-3",
            api_base="https://new.com", api_key="sk2", priority=2
        ))
        
        result = manager.get_provider("same")
        assert result.name == "Updated"
        assert result.model == "claude-3"
        assert len(manager.list_providers()) == 1


# ========== TC-M1-002: 从环境变量批量注册Provider ==========

class TestTCM1002:
    """TC-M1-002: 从环境变量批量注册Provider"""

    @patch.dict(os.environ, {
        "CPA_PROVIDER_0_ID": "provider_a",
        "CPA_PROVIDER_0_NAME": "Provider-A",
        "CPA_PROVIDER_0_MODEL": "openai/gpt-4",
        "CPA_PROVIDER_0_API_BASE": "https://api.a.com/v1",
        "CPA_PROVIDER_0_API_KEY": "sk-a",
        "CPA_PROVIDER_0_PRIORITY": "1",
        "CPA_PROVIDER_0_ENABLED": "true",
        "CPA_PROVIDER_1_ID": "provider_b",
        "CPA_PROVIDER_1_NAME": "Provider-B",
        "CPA_PROVIDER_1_MODEL": "openai/claude-3",
        "CPA_PROVIDER_1_API_BASE": "https://api.b.com/v1",
        "CPA_PROVIDER_1_API_KEY": "sk-b",
        "CPA_PROVIDER_1_PRIORITY": "2",
        "CPA_PROVIDER_1_ENABLED": "true",
        "CPA_PROVIDER_2_ID": "provider_c",
        "CPA_PROVIDER_2_NAME": "Provider-C",
        "CPA_PROVIDER_2_MODEL": "deepseek/deepseek-chat",
        "CPA_PROVIDER_2_API_BASE": "https://api.c.com/v1",
        "CPA_PROVIDER_2_API_KEY": "sk-c",
        "CPA_PROVIDER_2_PRIORITY": "3",
        "CPA_PROVIDER_2_ENABLED": "true",
    }, clear=False)
    def test_load_providers_from_env(self):
        """从环境变量加载3个Provider，按优先级排序"""
        manager = ProviderManager()
        
        manager.load_from_env()
        
        providers = manager.list_providers()
        assert len(providers) == 3
        assert providers[0].id == "provider_a"  # priority=1
        assert providers[1].id == "provider_b"  # priority=2
        assert providers[2].id == "provider_c"  # priority=3
        assert providers[0].api_key == "sk-a"
        assert providers[1].model == "openai/claude-3"
        assert providers[2].api_base == "https://api.c.com/v1"

    def test_load_from_env_empty(self):
        """无Provider环境变量时应加载为空"""
        manager = ProviderManager()
        manager.load_from_env()
        assert len(manager.list_providers()) == 0


# ========== TC-M1-003: 查询所有Provider ==========

class TestTCM1003:
    """TC-M1-003: 查询所有Provider"""

    def test_list_all_providers(self):
        """注册5个Provider后应能列出全部"""
        manager = ProviderManager()
        for i in range(5):
            manager.register_provider(ProviderConfig(
                id=f"p{i}", name=f"P{i}", model="gpt-4",
                api_base=f"https://api{i}.com", api_key=f"sk{i}", priority=i+1
            ))
        
        result = manager.list_providers()
        
        assert len(result) == 5
        assert [p.id for p in result] == ["p0", "p1", "p2", "p3", "p4"]

    def test_list_empty(self):
        """无Provider时应返回空列表"""
        manager = ProviderManager()
        assert manager.list_providers() == []

    def test_list_sorted_by_priority(self):
        """Provider列表应按优先级排序"""
        manager = ProviderManager()
        priorities = [3, 1, 2]
        for i, prio in enumerate(priorities):
            manager.register_provider(ProviderConfig(
                id=f"p{prio}", name=f"P{prio}", model="gpt-4",
                api_base=f"https://api.com", api_key="sk", priority=prio
            ))
        
        result = manager.list_providers()
        assert [p.priority for p in result] == [1, 2, 3]


# ========== TC-M1-004: 查询健康的Provider ==========

class TestTCM1004:
    """TC-M1-004: 查询健康的Provider"""

    def test_get_healthy_providers(self):
        """应排除DOWN状态的Provider"""
        manager = ProviderManager()
        
        for i in range(5):
            manager.register_provider(ProviderConfig(
                id=f"p{i}", name=f"P{i}", model="gpt-4",
                api_base=f"https://api{i}.com", api_key=f"sk{i}", priority=i+1
            ))
        
        # 设置健康状态
        manager._health_states = {
            "p0": "healthy", "p1": "healthy", "p2": "degraded",
            "p3": "down", "p4": "healthy"
        }
        
        result = manager.get_active_providers()
        
        assert len(result) == 4
        assert "p3" not in [p.id for p in result]
        assert set(p.id for p in result) == {"p0", "p1", "p2", "p4"}

    def test_get_active_with_disabled(self):
        """禁用的Provider也不应出现在active列表"""
        manager = ProviderManager()
        manager.register_provider(ProviderConfig(
            id="enabled_p", name="Enabled", model="gpt-4",
            api_base="https://api.com", api_key="sk", priority=1, enabled=True
        ))
        manager.register_provider(ProviderConfig(
            id="disabled_p", name="Disabled", model="gpt-4",
            api_base="https://api.com", api_key="sk", priority=2, enabled=False
        ))
        
        result = manager.get_active_providers()
        assert len(result) == 1
        assert result[0].id == "enabled_p"


# ========== TC-M1-005: 选择最优Provider（按优先级） ==========

class TestTCM1005:
    """TC-M1-005: 选择最优Provider（按优先级）"""

    def test_select_best_by_priority(self):
        """应返回优先级最高的健康Provider"""
        manager = ProviderManager()
        # priority: p2=1, p3=2, p1=3（数字小优先）
        for i, prio in enumerate([3, 1, 2], 1):
            manager.register_provider(ProviderConfig(
                id=f"p{i}", name=f"P{i}", model="gpt-4",
                api_base=f"https://api{i}.com", api_key=f"sk{i}", priority=prio
            ))
        
        best = manager.select_best_provider()
        assert best.id == "p2"  # priority=1 最优先

    def test_select_single_provider(self):
        """只有一个Provider时直接返回"""
        manager = ProviderManager()
        manager.register_provider(ProviderConfig(
            id="only", name="Only", model="gpt-4",
            api_base="https://api.com", api_key="sk", priority=1
        ))
        
        best = manager.select_best_provider()
        assert best.id == "only"


# ========== TC-M1-006: 选择最优Provider（健康状态优先） ==========

class TestTCM1006:
    """TC-M1-006: 健康状态优先于优先级"""

    def test_healthy_over_degraded(self):
        """healthy的Provider优先于degraded的"""
        manager = ProviderManager()
        # p1: priority=1 (最高) 但 degraded
        # p2: priority=2 (次高) 且 healthy
        manager.register_provider(ProviderConfig(
            id="p_degraded", name="P-Degraded", model="gpt-4",
            api_base="https://api1.com", api_key="sk1", priority=1
        ))
        manager.register_provider(ProviderConfig(
            id="p_healthy", name="P-Healthy", model="gpt-4",
            api_base="https://api2.com", api_key="sk2", priority=2
        ))
        
        manager._health_states = {"p_degraded": "degraded", "p_healthy": "healthy"}
        
        best = manager.select_best_provider()
        # 虽然p_degraded优先级更高，但它是degraded
        # p_healthy是healthy，应该优先
        assert best.id == "p_healthy"

    def test_down_provider_excluded(self):
        """DOWN的Provider应被排除"""
        manager = ProviderManager()
        manager.register_provider(ProviderConfig(
            id="p_down", name="P-Down", model="gpt-4",
            api_base="https://api.com", api_key="sk", priority=1
        ))
        manager.register_provider(ProviderConfig(
            id="p_ok", name="P-OK", model="gpt-4",
            api_base="https://api.com", api_key="sk", priority=2
        ))
        
        manager._health_states = {"p_down": "down", "p_ok": "healthy"}
        
        best = manager.select_best_provider()
        assert best.id == "p_ok"

    def test_degraded_when_no_healthy(self):
        """没有healthy时，degraded的Provider也可被选中"""
        manager = ProviderManager()
        manager.register_provider(ProviderConfig(
            id="p_deg", name="P-Deg", model="gpt-4",
            api_base="https://api.com", api_key="sk", priority=1
        ))
        manager._health_states = {"p_deg": "degraded"}
        
        best = manager.select_best_provider()
        assert best.id == "p_deg"


# ========== TC-M1-007: 禁用Provider ==========

class TestTCM1007:
    """TC-M1-007: 禁用Provider"""

    def test_disable_provider(self):
        """禁用后不应参与调度"""
        manager = ProviderManager()
        manager.register_provider(ProviderConfig(
            id="p1", name="P1", model="gpt-4",
            api_base="https://api1.com", api_key="sk1", priority=1, enabled=True
        ))
        
        assert manager.get_provider("p1").enabled is True
        
        manager.disable_provider("p1")
        
        assert manager.get_provider("p1").enabled is False
        assert "p1" not in [p.id for p in manager.get_active_providers()]

    def test_enable_provider(self):
        """重新启用后应能参与调度"""
        manager = ProviderManager()
        manager.register_provider(ProviderConfig(
            id="p1", name="P1", model="gpt-4",
            api_base="https://api.com", api_key="sk", priority=1, enabled=False
        ))
        
        assert "p1" not in [p.id for p in manager.get_active_providers()]
        
        manager.enable_provider("p1")
        
        assert "p1" in [p.id for p in manager.get_active_providers()]

    def test_disable_nonexistent(self):
        """禁用不存在的Provider不应报错"""
        manager = ProviderManager()
        manager.disable_provider("nonexistent")  # 不应抛出异常

    def test_unregister_provider(self):
        """注销Provider后应完全移除"""
        manager = ProviderManager()
        manager.register_provider(ProviderConfig(
            id="p_remove", name="P-Remove", model="gpt-4",
            api_base="https://api.com", api_key="sk", priority=1
        ))
        assert manager.get_provider("p_remove") is not None
        
        manager.unregister_provider("p_remove")
        
        assert manager.get_provider("p_remove") is None
        assert len(manager.list_providers()) == 0
