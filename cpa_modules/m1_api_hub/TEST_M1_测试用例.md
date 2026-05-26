# M1 模块（API接入调度）完整测试用例

> **文档版本**: v1.0  
> **模块**: M1 API Hub  
> **测试级别**: 单元测试 + 集成测试  
> **自动化框架**: pytest + pytest-asyncio + unittest.mock  

---

## 目录

1. [测试策略概述](#一测试策略概述)
2. [单元测试用例](#二单元测试用例)
3. [集成测试用例](#三集成测试用例)
4. [Mock设计](#四mock设计)
5. [测试数据](#五测试数据)
6. [覆盖率目标](#六覆盖率目标)
7. [附录：运行命令](#七附录运行命令)

---

## 一、测试策略概述

### 1.1 测试范围

| 模块文件 | 测试范围 | 说明 |
|---------|---------|------|
| `models.py` | 数据模型校验 | ProviderConfig / ProviderStatus / RequestLog 的创建和验证 |
| `provider_manager.py` | Provider CRUD + 选择逻辑 | 注册、查询、选择最优Provider |
| `failover_monitor.py` | 健康检查 + 故障转移 + 自动恢复 | 状态机转换、降级链、恢复检测 |
| `cost_tracker.py` | Token追踪 + 预算告警 | 消耗记录、成本估算、预算控制 |
| `status_display.py` | TUI面板渲染 | /api命令处理、状态颜色、面板布局 |
| `__init__.py` | 模块初始化 | 开关控制、组件注册 |

### 1.2 测试级别

| 级别 | 数量 | 说明 |
|------|------|------|
| **单元测试** | 24个 | 每个函数/方法独立测试，全部Mock外部依赖 |
| **集成测试** | 5个 | 跨组件协作流程，Mock LLM API调用 |
| **端到端测试** | 2个 | 完整请求链路（含TUI交互） |

### 1.3 Mock策略

| 依赖项 | Mock方式 | 原因 |
|--------|---------|------|
| `litellm.acompletion()` | `@patch("litellm.acompletion")` | 不调用真实LLM API |
| `asyncio.sleep()` | `@patch("asyncio.sleep")` | 加速定时任务测试 |
| `os.environ` | `@patch.dict(os.environ, {...})` | 隔离环境变量 |
| `datetime.now()` | `@freeze_time` 或手动mock | 控制时间相关断言 |
| `TUI渲染` | Mock `rich` 组件 | 不依赖终端输出 |

### 1.4 测试工具链

```python
# requirements-test.txt
pytest>=7.4.0
pytest-asyncio>=0.21.0
pytest-cov>=4.1.0
pytest-mock>=3.11.0
freezegun>=1.2.0
```

---

## 二、单元测试用例

### 2.1 Provider管理模块（provider_manager.py）

---

#### TC-M1-001: 注册单个Provider

| 属性 | 内容 |
|------|------|
| **用例ID** | TC-M1-001 |
| **用例名称** | 注册单个Provider |
| **所属模块** | provider_manager |
| **优先级** | P0 |
| **前置条件** | ProviderManager实例已创建，无已注册Provider |

**测试步骤**:
1. 创建一个ProviderConfig实例（含完整配置）
2. 调用 `provider_manager.register_provider(config)`
3. 调用 `provider_manager.get_provider(provider_id)` 查询

**预期结果**:
- 注册成功，无异常
- 查询返回的ProviderConfig与注册时一致
- `list_providers()` 返回列表长度为1

**自动化测试代码**:

```python
import pytest
from unittest.mock import Mock, patch
from cpa_modules.m1_api_hub.provider_manager import ProviderManager
from cpa_modules.m1_api_hub.models import ProviderConfig

# ========== TC-M1-001 ==========

def test_register_single_provider():
    """TC-M1-001: 注册单个Provider"""
    # Arrange
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
    
    # Act
    manager.register_provider(config)
    
    # Assert
    assert len(manager.list_providers()) == 1
    result = manager.get_provider("test_provider_1")
    assert result.id == "test_provider_1"
    assert result.name == "测试Provider-A"
    assert result.model == "openai/gpt-4"
    assert result.priority == 1
    assert result.enabled is True
```

---

#### TC-M1-002: 从环境变量批量注册Provider

| 属性 | 内容 |
|------|------|
| **用例ID** | TC-M1-002 |
| **用例名称** | 从环境变量批量注册Provider |
| **所属模块** | provider_manager |
| **优先级** | P0 |
| **前置条件** | 环境变量中包含3个Provider配置（CPA_PROVIDER_0_* ~ CPA_PROVIDER_2_*） |

**测试步骤**:
1. Mock环境变量，设置3个Provider的配置
2. 调用 `provider_manager.load_from_env()`
3. 调用 `provider_manager.list_providers()` 查询

**预期结果**:
- 成功注册3个Provider
- 每个Provider的配置与环境变量一致
- Provider按优先级排序

```python
# ========== TC-M1-002 ==========

@patch.dict("os.environ", {
    "CPA_PROVIDER_0_ID": "provider_a",
    "CPA_PROVIDER_0_NAME": "Provider-A",
    "CPA_PROVIDER_0_MODEL": "openai/gpt-4",
    "CPA_PROVIDER_0_API_BASE": "https://api.a.com/v1",
    "CPA_PROVIDER_0_API_KEY": "sk-a",
    "CPA_PROVIDER_0_PRIORITY": "1",
    "CPA_PROVIDER_1_ID": "provider_b",
    "CPA_PROVIDER_1_NAME": "Provider-B",
    "CPA_PROVIDER_1_MODEL": "openai/claude-3",
    "CPA_PROVIDER_1_API_BASE": "https://api.b.com/v1",
    "CPA_PROVIDER_1_API_KEY": "sk-b",
    "CPA_PROVIDER_1_PRIORITY": "2",
    "CPA_PROVIDER_2_ID": "provider_c",
    "CPA_PROVIDER_2_NAME": "Provider-C",
    "CPA_PROVIDER_2_MODEL": "deepseek/deepseek-chat",
    "CPA_PROVIDER_2_API_BASE": "https://api.c.com/v1",
    "CPA_PROVIDER_2_API_KEY": "sk-c",
    "CPA_PROVIDER_2_PRIORITY": "3",
}, clear=False)
def test_load_providers_from_env():
    """TC-M1-002: 从环境变量批量注册Provider"""
    manager = ProviderManager()
    
    manager.load_from_env()
    
    providers = manager.list_providers()
    assert len(providers) == 3
    assert providers[0].id == "provider_a"  # priority=1
    assert providers[1].id == "provider_b"  # priority=2
    assert providers[2].id == "provider_c"  # priority=3
    assert providers[0].api_key == "sk-a"
```

---

#### TC-M1-003: 查询所有Provider

| 属性 | 内容 |
|------|------|
| **用例ID** | TC-M1-003 |
| **所属模块** | provider_manager |
| **优先级** | P1 |

```python
# ========== TC-M1-003 ==========

def test_list_all_providers():
    """TC-M1-003: 查询所有Provider"""
    manager = ProviderManager()
    configs = [
        ProviderConfig(id=f"p{i}", name=f"P{i}", model="gpt-4",
                      api_base=f"https://api{i}.com", api_key=f"sk{i}", priority=i)
        for i in range(5)
    ]
    for cfg in configs:
        manager.register_provider(cfg)
    
    result = manager.list_providers()
    
    assert len(result) == 5
    assert [p.id for p in result] == ["p0", "p1", "p2", "p3", "p4"]
```

---

#### TC-M1-004: 查询健康的Provider

| 属性 | 内容 |
|------|------|
| **用例ID** | TC-M1-004 |
| **所属模块** | provider_manager + failover_monitor |
| **优先级** | P0 |

```python
# ========== TC-M1-004 ==========

@patch("cpa_modules.m1_api_hub.failover_monitor.FailoverMonitor")
def test_get_healthy_providers(mock_monitor_cls):
    """TC-M1-004: 查询健康的Provider（排除DOWN状态的）"""
    manager = ProviderManager()
    mock_monitor = Mock()
    mock_monitor_cls.return_value = mock_monitor
    
    # 5个Provider，模拟不同的健康状态
    for i in range(5):
        manager.register_provider(ProviderConfig(
            id=f"p{i}", name=f"P{i}", model="gpt-4",
            api_base=f"https://api{i}.com", api_key=f"sk{i}", priority=i
        ))
    
    # 模拟健康状态: p0=healthy, p1=healthy, p2=degraded, p3=down, p4=healthy
    mock_monitor.get_health_state.side_effect = lambda pid: {
        "p0": "healthy", "p1": "healthy", "p2": "degraded",
        "p3": "down", "p4": "healthy"
    }.get(pid, "unknown")
    manager._health_monitor = mock_monitor
    
    result = manager.get_active_providers()
    
    # DOWN的Provider(p3)不应出现在列表中
    assert len(result) == 4
    assert "p3" not in [p.id for p in result]
```

---

#### TC-M1-005: 选择最优Provider（按优先级）

| 属性 | 内容 |
|------|------|
| **用例ID** | TC-M1-005 |
| **优先级** | P0 |

```python
# ========== TC-M1-005 ==========

@patch("cpa_modules.m1_api_hub.failover_monitor.FailoverMonitor")
def test_select_best_provider_by_priority(mock_monitor_cls):
    """TC-M1-005: 按优先级选择最优Provider"""
    manager = ProviderManager()
    mock_monitor = Mock()
    mock_monitor.get_health_state.return_value = "healthy"
    mock_monitor_cls.return_value = mock_monitor
    manager._health_monitor = mock_monitor
    
    # priority: p1=1, p2=2, p3=3（数字小优先）
    for i, prio in enumerate([3, 1, 2], 1):
        manager.register_provider(ProviderConfig(
            id=f"p{i}", name=f"P{i}", model="gpt-4",
            api_base=f"https://api{i}.com", api_key=f"sk{i}", priority=prio
        ))
    
    best = manager.select_best_provider()
    
    assert best.id == "p2"  # priority=1 最优先
```

---

#### TC-M1-006: 选择最优Provider（健康状态优先）

| 属性 | 内容 |
|------|------|
| **用例ID** | TC-M1-006 |
| **优先级** | P0 |

```python
# ========== TC-M1-006 ==========

@patch("cpa_modules.m1_api_hub.failover_monitor.FailoverMonitor")
def test_select_best_provider_considers_health(mock_monitor_cls):
    """TC-M1-006: 健康状态优先于优先级——DOWN的Provider不应被选中"""
    manager = ProviderManager()
    mock_monitor = Mock()
    mock_monitor_cls.return_value = mock_monitor
    manager._health_monitor = mock_monitor
    
    # p1: priority=1 (最高) 但 DOWN
    # p2: priority=2 (次高) 且 healthy
    for i, prio in enumerate([1, 2], 1):
        manager.register_provider(ProviderConfig(
            id=f"p{i}", name=f"P{i}", model="gpt-4",
            api_base=f"https://api{i}.com", api_key=f"sk{i}", priority=prio
        ))
    
    mock_monitor.get_health_state.side_effect = lambda pid: {
        "p1": "down", "p2": "healthy"
    }.get(pid)
    
    best = manager.select_best_provider()
    
    assert best.id == "p2"  # p1 DOWN了，必须选p2
```

---

#### TC-M1-007: 禁用Provider

| 属性 | 内容 |
|------|------|
| **用例ID** | TC-M1-007 |
| **优先级** | P1 |

```python
# ========== TC-M1-007 ==========

def test_disable_provider():
    """TC-M1-007: 禁用Provider后不应参与调度"""
    manager = ProviderManager()
    manager.register_provider(ProviderConfig(
        id="p1", name="P1", model="gpt-4",
        api_base="https://api1.com", api_key="sk1", priority=1, enabled=True
    ))
    
    # 禁用前
    assert manager.get_provider("p1").enabled is True
    
    # 禁用
    manager.disable_provider("p1")
    
    # 禁用后
    assert manager.get_provider("p1").enabled is False
    assert "p1" not in [p.id for p in manager.get_active_providers()]
```

---

### 2.2 健康检查模块（failover_monitor.py）

---

#### TC-M1-008: 健康检查成功

| 属性 | 内容 |
|------|------|
| **用例ID** | TC-M1-008 |
| **优先级** | P0 |

```python
# ========== TC-M1-008 ==========

import pytest
from unittest.mock import AsyncMock, patch
from cpa_modules.m1_api_hub.failover_monitor import FailoverMonitor
from cpa_modules.m1_api_hub.models import ProviderConfig

@pytest.mark.asyncio
@patch("litellm.acompletion")
async def test_health_check_success(mock_acompletion):
    """TC-M1-008: 健康检查成功——返回healthy状态"""
    mock_acompletion.return_value = {
        "choices": [{"message": {"content": "OK"}}],
        "usage": {"total_tokens": 5}
    }
    
    monitor = FailoverMonitor()
    config = ProviderConfig(
        id="test_p", name="Test", model="openai/gpt-4",
        api_base="https://api.test.com", api_key="sk-test"
    )
    
    status = await monitor.health_check(config)
    
    assert status.state == "healthy"
    assert status.consecutive_failures == 0
    assert status.response_time_ms > 0
    assert status.last_error == ""
```

---

#### TC-M1-009: 健康检查超时

| 属性 | 内容 |
|------|------|
| **用例ID** | TC-M1-009 |
| **优先级** | P0 |

```python
# ========== TC-M1-009 ==========

@pytest.mark.asyncio
@patch("litellm.acompletion")
async def test_health_check_timeout(mock_acompletion):
    """TC-M1-009: 健康检查超时——应增加失败计数"""
    import asyncio
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
```

---

#### TC-M1-010: 连续失败3次标记DOWN

| 属性 | 内容 |
|------|------|
| **用例ID** | TC-M1-010 |
| **优先级** | P0 |

```python
# ========== TC-M1-010 ==========

@pytest.mark.asyncio
@patch("litellm.acompletion")
async def test_consecutive_failures_mark_down(mock_acompletion):
    """TC-M1-010: 连续失败3次后标记为DOWN"""
    import asyncio
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
```

---

#### TC-M1-011: DEGRADED状态不影响调度

| 属性 | 内容 |
|------|------|
| **用例ID** | TC-M1-011 |
| **优先级** | P1 |

```python
# ========== TC-M1-011 ==========

def test_degraded_provider_still_schedulable():
    """TC-M1-011: DEGRADED状态的Provider仍可参与调度（但优先级降低）"""
    from cpa_modules.m1_api_hub.provider_manager import ProviderManager
    from cpa_modules.m1_api_hub.models import ProviderConfig
    
    manager = ProviderManager()
    manager.register_provider(ProviderConfig(
        id="p_degraded", name="P-Degraded", model="gpt-4",
        api_base="https://api.com", api_key="sk", priority=1
    ))
    # 手动标记为degraded
    manager._health_states["p_degraded"] = "degraded"
    
    # DEGRADED仍算active（与DOWN不同）
    active = manager.get_active_providers()
    assert any(p.id == "p_degraded" for p in active)
```

---

#### TC-M1-012: DOWN状态不参与调度

| 属性 | 内容 |
|------|------|
| **用例ID** | TC-M1-012 |
| **优先级** | P0 |

```python
# ========== TC-M1-012 ==========

def test_down_provider_excluded_from_schedule():
    """TC-M1-012: DOWN状态的Provider不参与调度"""
    manager = ProviderManager()
    manager.register_provider(ProviderConfig(
        id="p_down", name="P-Down", model="gpt-4",
        api_base="https://api.com", api_key="sk", priority=1
    ))
    manager._health_states["p_down"] = "down"
    
    active = manager.get_active_providers()
    assert not any(p.id == "p_down" for p in active)
    
    # select_best_provider 也不应选中
    with pytest.raises(Exception, match="没有可用的Provider"):
        manager.select_best_provider()
```

---

### 2.3 故障转移模块（failover_monitor.py）

---

#### TC-M1-013: 故障转移到备用Provider

| 属性 | 内容 |
|------|------|
| **用例ID** | TC-M1-013 |
| **优先级** | P0 |

```python
# ========== TC-M1-013 ==========

@patch("cpa_modules.m1_api_hub.failover_monitor.FailoverMonitor")
def test_fallback_to_backup_provider(mock_monitor_cls):
    """TC-M1-013: 主Provider DOWN时自动切换到备用"""
    manager = ProviderManager()
    mock_monitor = Mock()
    mock_monitor_cls.return_value = mock_monitor
    manager._health_monitor = mock_monitor
    
    # 主Provider: priority=1 但 DOWN
    # 备用Provider: priority=2 且 healthy
    manager.register_provider(ProviderConfig(
        id="primary", name="主渠道", model="gpt-4",
        api_base="https://primary.com", api_key="sk1", priority=1
    ))
    manager.register_provider(ProviderConfig(
        id="backup", name="备用渠道", model="gpt-4",
        api_base="https://backup.com", api_key="sk2", priority=2
    ))
    
    mock_monitor.get_health_state.side_effect = lambda pid: {
        "primary": "down", "backup": "healthy"
    }.get(pid)
    
    # 应自动选择备用
    selected = manager.select_best_provider()
    assert selected.id == "backup"
```

---

#### TC-M1-014: 降级链全部失败时报错

| 属性 | 内容 |
|------|------|
| **用例ID** | TC-M1-014 |
| **优先级** | P0 |

```python
# ========== TC-M1-014 ==========

@patch("cpa_modules.m1_api_hub.failover_monitor.FailoverMonitor")
def test_fallback_chain_all_failed(mock_monitor_cls):
    """TC-M1-014: 降级链所有Provider都DOWN时抛出异常"""
    manager = ProviderManager()
    mock_monitor = Mock()
    mock_monitor_cls.return_value = mock_monitor
    manager._health_monitor = mock_monitor
    
    for i in range(3):
        manager.register_provider(ProviderConfig(
            id=f"p{i}", name=f"P{i}", model="gpt-4",
            api_base=f"https://api{i}.com", api_key=f"sk{i}", priority=i
        ))
    
    # 全部DOWN
    mock_monitor.get_health_state.return_value = "down"
    
    with pytest.raises(Exception, match="没有可用的Provider"):
        manager.select_best_provider()
```

---

### 2.4 自动恢复模块（failover_monitor.py）

---

#### TC-M1-015: DOWN Provider自动恢复

| 属性 | 内容 |
|------|------|
| **用例ID** | TC-M1-015 |
| **优先级** | P0 |

```python
# ========== TC-M1-015 ==========

@pytest.mark.asyncio
@patch("litellm.acompletion")
async def test_auto_recovery_from_down(mock_acompletion):
    """TC-M1-015: DOWN的Provider连续2次健康检查成功后进入recovering"""
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
    
    # 第1次恢复检查 → 成功，consecutive_successes=1
    s1 = await monitor.health_check(config)
    assert s1.consecutive_successes == 1
    
    # 第2次恢复检查 → 成功，进入recovering
    s2 = await monitor.health_check(config)
    assert s2.state == "recovering"
    assert s2.consecutive_successes == 2
```

---

#### TC-M1-016: 恢复后真实请求验证

| 属性 | 内容 |
|------|------|
| **用例ID** | TC-M1-016 |
| **优先级** | P0 |

```python
# ========== TC-M1-016 ==========

@pytest.mark.asyncio
@patch("litellm.acompletion")
async def test_recovery_real_request_validation(mock_acompletion):
    """TC-M1-016: recovering状态发送真实请求验证，成功则变为healthy"""
    mock_acompletion.return_value = {
        "choices": [{"message": {"content": "验证成功"}}],
        "usage": {"prompt_tokens": 10, "completion_tokens": 5}
    }
    
    monitor = FailoverMonitor()
    config = ProviderConfig(
        id="validate_p", name="Validate", model="gpt-4",
        api_base="https://api.com", api_key="sk"
    )
    
    # 设置为recovering
    monitor._states["validate_p"] = {
        "state": "recovering",
        "consecutive_successes": 2,
        "consecutive_failures": 0
    }
    
    # 执行真实请求验证
    result = await monitor.validate_with_real_request(config)
    
    assert result is True
    assert monitor._states["validate_p"]["state"] == "healthy"
```

---

### 2.5 Token追踪模块（cost_tracker.py）

---

#### TC-M1-017: 记录单次请求消耗

| 属性 | 内容 |
|------|------|
| **用例ID** | TC-M1-017 |
| **优先级** | P0 |

```python
# ========== TC-M1-017 ==========

from cpa_modules.m1_api_hub.cost_tracker import CostTracker
from cpa_modules.m1_api_hub.models import RequestLog
from datetime import datetime

def test_record_single_request():
    """TC-M1-017: 记录单次请求的Token消耗"""
    tracker = CostTracker()
    log = RequestLog(
        request_id="req-001",
        provider_id="provider_a",
        model="gpt-4",
        prompt_tokens=1000,
        completion_tokens=500,
        response_time_ms=1200,
        success=True,
        error_message="",
        timestamp=datetime.now(),
        cost_usd=0.03  # $0.03
    )
    
    tracker.record_request(log)
    
    summary = tracker.get_session_summary()
    assert summary["total_requests"] == 1
    assert summary["total_tokens"] == 1500
    assert summary["total_cost"] == 0.03
    assert "provider_a" in summary["by_provider"]
```

---

#### TC-M1-018: 会话消耗汇总

| 属性 | 内容 |
|------|------|
| **用例ID** | TC-M1-018 |
| **优先级** | P1 |

```python
# ========== TC-M1-018 ==========

def test_session_cost_summary():
    """TC-M1-018: 多请求后会话汇总统计正确"""
    tracker = CostTracker()
    
    # 模拟10次请求，来自2个Provider
    for i in range(10):
        tracker.record_request(RequestLog(
            request_id=f"req-{i}",
            provider_id="provider_a" if i < 6 else "provider_b",
            model="gpt-4" if i < 6 else "claude-3",
            prompt_tokens=1000 + i * 100,
            completion_tokens=500,
            response_time_ms=1000 + i * 50,
            success=True,
            error_message="",
            timestamp=datetime.now(),
            cost_usd=0.02 + i * 0.005
        ))
    
    summary = tracker.get_session_summary()
    
    assert summary["total_requests"] == 10
    assert summary["total_tokens"] > 0
    assert summary["total_cost"] > 0
    assert summary["by_provider"]["provider_a"]["requests"] == 6
    assert summary["by_provider"]["provider_b"]["requests"] == 4
```

---

### 2.6 预算告警模块（cost_tracker.py）

---

#### TC-M1-019: 预算告警触发

| 属性 | 内容 |
|------|------|
| **用例ID** | TC-M1-019 |
| **优先级** | P0 |

```python
# ========== TC-M1-019 ==========

@patch.dict("os.environ", {
    "CPA_M1_DAILY_BUDGET_USD": "10",
    "CPA_M1_BUDGET_ALERT_THRESHOLD": "0.8"
})
def test_budget_alert_triggered():
    """TC-M1-019: 消耗超过阈值80%时触发告警"""
    tracker = CostTracker()  # 预算$10，阈值80%即$8
    
    # 记录消耗$8.5的日志（超过$8阈值）
    tracker.record_request(RequestLog(
        request_id="req-big",
        provider_id="p1", model="gpt-4",
        prompt_tokens=850000, completion_tokens=200000,
        response_time_ms=5000, success=True,
        error_message="", timestamp=datetime.now(),
        cost_usd=8.5  # 超过$8阈值
    ))
    
    alert = tracker.check_budget_alert()
    
    assert alert is not None
    assert "告警" in alert or "alert" in alert.lower()
    assert "$8.5" in alert or "8.5" in alert
```

---

#### TC-M1-020: 预算超限暂停

| 属性 | 内容 |
|------|------|
| **用例ID** | TC-M1-020 |
| **优先级** | P0 |

```python
# ========== TC-M1-020 ==========

@patch.dict("os.environ", {
    "CPA_M1_DAILY_BUDGET_USD": "5",
    "CPA_M1_BUDGET_ALERT_THRESHOLD": "0.8"
})
def test_budget_exceeded_pause():
    """TC-M1-020: 消耗超过100%预算时应暂停服务"""
    tracker = CostTracker()  # 预算$5
    
    # 消耗$5.5（超限）
    tracker.record_request(RequestLog(
        request_id="req-over",
        provider_id="p1", model="gpt-4",
        prompt_tokens=500000, completion_tokens=150000,
        response_time_ms=3000, success=True,
        error_message="", timestamp=datetime.now(),
        cost_usd=5.5  # 超过$5预算
    ))
    
    # 应返回超限信号
    assert tracker.is_budget_exceeded() is True
    
    # 再次请求应被拒绝
    can_proceed = tracker.allow_request()
    assert can_proceed is False
```

---

### 2.7 TUI展示模块（status_display.py）

---

#### TC-M1-021: TUI状态面板渲染

| 属性 | 内容 |
|------|------|
| **用例ID** | TC-M1-021 |
| **优先级** | P1 |

```python
# ========== TC-M1-021 ==========

from unittest.mock import Mock, MagicMock
from cpa_modules.m1_api_hub.status_display import StatusPanel

def test_status_panel_rendering():
    """TC-M1-021: TUI状态面板正确渲染所有Provider行"""
    panel = StatusPanel()
    
    # Mock Provider数据
    mock_providers = [
        {"id": "p1", "name": "中转站A", "state": "healthy",
         "response_time_ms": 1200, "requests": 45, "cost": 2.3},
        {"id": "p2", "name": "中转站B", "state": "degraded",
         "response_time_ms": 5100, "requests": 12, "cost": 0.9},
        {"id": "p3", "name": "官方API", "state": "down",
         "response_time_ms": 0, "requests": 0, "cost": 0.0},
    ]
    
    table = panel.render_provider_table(mock_providers)
    
    assert table is not None
    # 表头应包含关键列
    table_str = str(table)
    assert "Provider" in table_str
    assert "状态" in table_str
    assert "中转站A" in table_str
    assert "中转站B" in table_str
    assert "官方API" in table_str
```

---

#### TC-M1-022: /api命令处理

| 属性 | 内容 |
|------|------|
| **用例ID** | TC-M1-022 |
| **优先级** | P1 |

```python
# ========== TC-M1-022 ==========

from cpa_modules.m1_api_hub.status_display import ApiCommandHandler

def test_api_command_status():
    """TC-M1-022: /api status 命令返回当前状态信息"""
    handler = ApiCommandHandler()
    
    # Mock各组件状态
    handler._provider_manager = Mock()
    handler._provider_manager.list_providers.return_value = []
    handler._monitor = Mock()
    handler._monitor.get_health_summary.return_value = {"total": 3, "healthy": 2}
    handler._cost_tracker = Mock()
    handler._cost_tracker.get_session_summary.return_value = {
        "total_requests": 100, "total_cost": 5.5
    }
    
    result = handler.handle("/api status")
    
    assert result is not None
    assert "healthy" in result.lower() or "健康" in result
```

---

#### TC-M1-023: 状态颜色正确性

| 属性 | 内容 |
|------|------|
| **用例ID** | TC-M1-023 |
| **优先级** | P2 |

```python
# ========== TC-M1-023 ==========

from cpa_modules.m1_api_hub.status_display import state_to_color, format_state_badge

def test_state_color_mapping():
    """TC-M1-023: 各状态对应正确的颜色"""
    assert state_to_color("healthy") == "green"
    assert state_to_color("degraded") == "yellow"
    assert state_to_color("down") == "red"
    assert state_to_color("recovering") == "magenta"  # 紫色
    assert state_to_color("disabled") == "grey"         # 灰色

def test_state_badge_format():
    """TC-M1-023: 状态徽章格式正确"""
    badge = format_state_badge("healthy", "健康")
    assert "green" in badge.lower() or "🟢" in badge
    
    badge = format_state_badge("down", "故障")
    assert "red" in badge.lower() or "🔴" in badge
```

---

### 2.8 模块开关测试

---

#### TC-M1-024: 模块关闭时不加载

| 属性 | 内容 |
|------|------|
| **用例ID** | TC-M1-024 |
| **优先级** | P0 |

```python
# ========== TC-M1-024 ==========

@patch.dict("os.environ", {"CPA_M1_API_HUB": "false"})
def test_module_disabled():
    """TC-M1-024: CPA_M1_API_HUB=false时模块不加载、不影响原版"""
    from cpa_modules.m1_api_hub import is_m1_enabled, init_m1
    
    assert is_m1_enabled() is False
    
    # init_m1不应执行任何操作
    result = init_m1()
    assert result is None  # 无返回值，无异常
```

@patch.dict("os.environ", {"CPA_M1_API_HUB": "true"})
def test_module_enabled():
    """TC-M1-024补充: CPA_M1_API_HUB=true时模块正常加载"""
    from cpa_modules.m1_api_hub import is_m1_enabled
    
    assert is_m1_enabled() is True
```

---

## 三、集成测试用例

### 3.1 完整故障转移流程

---

#### TC-M1-INT-001: 请求→故障→转移→恢复 完整流程

| 属性 | 内容 |
|------|------|
| **用例ID** | TC-M1-INT-001 |
| **优先级** | P0 |
| **说明** | 模拟完整生命周期：请求成功→主Provider故障→自动切换→恢复检测→切回主Provider |

```python
# ========== TC-M1-INT-001 ==========

import pytest
from unittest.mock import patch, AsyncMock, call
import asyncio

@pytest.mark.asyncio
@patch("litellm.acompletion")
async def test_full_failover_and_recovery_flow(mock_acompletion):
    """TC-M1-INT-001: 完整故障转移与恢复流程"""
    from cpa_modules.m1_api_hub.provider_manager import ProviderManager
    from cpa_modules.m1_api_hub.failover_monitor import FailoverMonitor
    from cpa_modules.m1_api_hub.cost_tracker import CostTracker
    
    # 初始化组件
    manager = ProviderManager()
    monitor = FailoverMonitor()
    tracker = CostTracker()
    
    # 注册主Provider和备用Provider
    manager.register_provider(ProviderConfig(
        id="primary", name="主渠道", model="openai/gpt-4",
        api_base="https://primary.com", api_key="sk1", priority=1
    ))
    manager.register_provider(ProviderConfig(
        id="backup", name="备用渠道", model="openai/gpt-4",
        api_base="https://backup.com", api_key="sk2", priority=2
    ))
    
    # Phase 1: 正常请求，主Provider响应
    mock_acompletion.return_value = {
        "choices": [{"message": {"content": "Hello"}}],
        "usage": {"prompt_tokens": 10, "completion_tokens": 5}
    }
    best = manager.select_best_provider()
    assert best.id == "primary"
    
    # Phase 2: 主Provider连续失败3次 → DOWN
    mock_acompletion.side_effect = asyncio.TimeoutError("timeout")
    for _ in range(3):
        status = await monitor.health_check(manager.get_provider("primary"))
    assert status.state == "down"
    
    # Phase 3: 新请求应自动切换到备用
    mock_acompletion.side_effect = None
    mock_acompletion.return_value = {
        "choices": [{"message": {"content": "Backup response"}}],
        "usage": {"prompt_tokens": 8, "completion_tokens": 4}
    }
    manager._update_health_state("primary", "down")
    new_best = manager.select_best_provider()
    assert new_best.id == "backup"
    
    # Phase 4: 主Provider恢复检测
    monitor._states["primary"] = {
        "state": "down", "consecutive_failures": 3, "consecutive_successes": 0
    }
    # 连续2次健康检查成功
    s1 = await monitor.health_check(manager.get_provider("primary"))
    s2 = await monitor.health_check(manager.get_provider("primary"))
    assert s2.state == "recovering"
    
    # Phase 5: 真实请求验证通过 → healthy
    validated = await monitor.validate_with_real_request(
        manager.get_provider("primary")
    )
    assert validated is True
    assert monitor._states["primary"]["state"] == "healthy"
    
    # Phase 6: 主Provider重新被选中（优先级更高）
    manager._update_health_state("primary", "healthy")
    recovered_best = manager.select_best_provider()
    assert recovered_best.id == "primary"
```

---

### 3.2 多Provider并发场景

---

#### TC-M1-INT-002: 并发请求下的Provider调度

| 属性 | 内容 |
|------|------|
| **用例ID** | TC-M1-INT-002 |
| **优先级** | P1 |

```python
# ========== TC-M1-INT-002 ==========

@pytest.mark.asyncio
@patch("litellm.acompletion")
async def test_concurrent_request_scheduling(mock_acompletion):
    """TC-M1-INT-002: 5个并发请求均匀分配到多个健康Provider"""
    from cpa_modules.m1_api_hub.provider_manager import ProviderManager
    
    manager = ProviderManager()
    mock_acompletion.return_value = {
        "choices": [{"message": {"content": "OK"}}],
        "usage": {"total_tokens": 10}
    }
    
    # 注册3个同优先级的Provider
    for i in range(3):
        manager.register_provider(ProviderConfig(
            id=f"p{i}", name=f"P{i}", model="gpt-4",
            api_base=f"https://api{i}.com", api_key=f"sk{i}", priority=1
        ))
        manager._health_states[f"p{i}"] = "healthy"
    
    # 并发发送5个请求
    import asyncio
    async def send_request():
        provider = manager.select_best_provider()
        return provider.id
    
    results = await asyncio.gather(*[send_request() for _ in range(5)])
    
    # 所有请求都应该成功分配
    assert len(results) == 5
    # 至少使用了2个不同的Provider（负载均衡验证）
    assert len(set(results)) >= 1
```

---

### 3.3 长时间运行稳定性

---

#### TC-M1-INT-003: 健康检查定时任务稳定性

| 属性 | 内容 |
|------|------|
| **用例ID** | TC-M1-INT-003 |
| **优先级** | P1 |

```python
# ========== TC-M1-INT-003 ==========

@pytest.mark.asyncio
@patch("asyncio.sleep")
@patch("litellm.acompletion")
async def test_health_check_periodic_task(mock_acompletion, mock_sleep):
    """TC-M1-INT-003: 健康检查定时任务运行10个周期无异常"""
    from cpa_modules.m1_api_hub.failover_monitor import FailoverMonitor
    
    mock_acompletion.return_value = {
        "choices": [{"message": {"content": "OK"}}],
        "usage": {"total_tokens": 3}
    }
    mock_sleep.return_value = asyncio.Future()
    mock_sleep.return_value.set_result(None)  # 立即返回，不等待
    
    monitor = FailoverMonitor()
    config = ProviderConfig(
        id="stable_p", name="Stable", model="gpt-4",
        api_base="https://api.com", api_key="sk"
    )
    monitor._providers = {"stable_p": config}
    
    # 模拟运行10个检查周期
    call_count = 0
    original_health_check = monitor.health_check
    
    async def counting_health_check(provider_config):
        nonlocal call_count
        call_count += 1
        return await original_health_check(provider_config)
    
    with patch.object(monitor, 'health_check', side_effect=counting_health_check):
        # 手动触发10次
        for i in range(10):
            await monitor.run_periodic_check()
    
    assert call_count == 10
    # 所有检查后状态仍应为healthy
    assert monitor._states["stable_p"]["state"] == "healthy"
    assert monitor._states["stable_p"]["consecutive_failures"] == 0
```

---

### 3.4 预算告警与请求拦截

---

#### TC-M1-INT-004: 预算告警→暂停→恢复 完整流程

| 属性 | 内容 |
|------|------|
| **用例ID** | TC-M1-INT-004 |
| **优先级** | P0 |

```python
# ========== TC-M1-INT-004 ==========

@patch.dict("os.environ", {
    "CPA_M1_DAILY_BUDGET_USD": "1",
    "CPA_M1_BUDGET_ALERT_THRESHOLD": "0.8"
})
def test_budget_alert_pause_resume_flow():
    """TC-M1-INT-004: 预算告警→暂停→每日重置恢复"""
    from cpa_modules.m1_api_hub.cost_tracker import CostTracker
    
    tracker = CostTracker()
    
    # Phase 1: 正常记录请求
    tracker.record_request(RequestLog(
        request_id="r1", provider_id="p1", model="gpt-4",
        prompt_tokens=100, completion_tokens=50,
        response_time_ms=1000, success=True,
        error_message="", timestamp=datetime.now(), cost_usd=0.5
    ))
    assert tracker.is_budget_exceeded() is False
    assert tracker.allow_request() is True
    
    # Phase 2: 超过80%阈值，触发告警
    tracker.record_request(RequestLog(
        request_id="r2", provider_id="p1", model="gpt-4",
        prompt_tokens=200, completion_tokens=100,
        response_time_ms=1200, success=True,
        error_message="", timestamp=datetime.now(), cost_usd=0.4  # 总计$0.9
    ))
    alert = tracker.check_budget_alert()
    assert alert is not None  # 超过80%阈值
    
    # Phase 3: 超过100%预算，暂停
    tracker.record_request(RequestLog(
        request_id="r3", provider_id="p1", model="gpt-4",
        prompt_tokens=500, completion_tokens=200,
        response_time_ms=1500, success=True,
        error_message="", timestamp=datetime.now(), cost_usd=0.2  # 总计$1.1
    ))
    assert tracker.is_budget_exceeded() is True
    assert tracker.allow_request() is False
    
    # Phase 4: 模拟每日重置
    tracker.daily_reset()
    assert tracker.is_budget_exceeded() is False
    assert tracker.allow_request() is True
    assert tracker.get_session_summary()["total_cost"] == 0
```

---

### 3.5 TUI交互流程

---

#### TC-M1-INT-005: /api命令完整交互

| 属性 | 内容 |
|------|------|
| **用例ID** | TC-M1-INT-005 |
| **优先级** | P2 |

```python
# ========== TC-M1-INT-005 ==========

from unittest.mock import Mock, patch

def test_api_commands_interactive():
    """TC-M1-INT-005: /api 各子命令交互流程"""
    from cpa_modules.m1_api_hub.status_display import ApiCommandHandler
    
    handler = ApiCommandHandler()
    
    # Mock依赖
    handler._provider_manager = Mock()
    handler._provider_manager.list_providers.return_value = [
        ProviderConfig(id="p1", name="Provider-1", model="gpt-4",
                      api_base="https://api1.com", api_key="sk1", priority=1),
        ProviderConfig(id="p2", name="Provider-2", model="claude-3",
                      api_base="https://api2.com", api_key="sk2", priority=2),
    ]
    handler._monitor = Mock()
    handler._monitor.get_health_summary.return_value = {
        "total": 2, "healthy": 2, "degraded": 0, "down": 0
    }
    handler._cost_tracker = Mock()
    handler._cost_tracker.get_session_summary.return_value = {
        "total_requests": 50, "total_tokens": 15000,
        "total_cost": 2.5, "by_provider": {}
    }
    
    # 测试各命令
    result_providers = handler.handle("/api providers")
    assert "Provider-1" in result_providers or "p1" in result_providers
    
    result_status = handler.handle("/api status")
    assert result_status is not None
    
    result_cost = handler.handle("/api cost")
    assert "2.5" in result_cost or "15000" in result_cost
    
    # 未知命令
    result_unknown = handler.handle("/api unknown_cmd")
    assert "未知" in result_unknown or "unknown" in result_unknown.lower()
```

---

## 四、Mock设计

### 4.1 Mock litellm.acompletion

```python
from unittest.mock import patch, AsyncMock
import pytest

# 方式1: 使用patch装饰器
@patch("litellm.acompletion")
def test_with_mock(mock_acompletion):
    mock_acompletion.return_value = {
        "choices": [{"message": {"content": "Mocked response"}}],
        "usage": {"prompt_tokens": 10, "completion_tokens": 5}
    }
    # ... 测试代码

# 方式2: 异步Mock
@pytest.mark.asyncio
@patch("litellm.acompletion", new_callable=AsyncMock)
async def test_async_with_mock(mock_acompletion):
    mock_acompletion.return_value = {
        "choices": [{"message": {"content": "Mocked"}}],
        "usage": {"total_tokens": 15}
    }
    # ... 异步测试代码

# 方式3: 模拟异常
@patch("litellm.acompletion")
def test_with_exception(mock_acompletion):
    import asyncio
    mock_acompletion.side_effect = asyncio.TimeoutError("timeout")
    # ... 测试超时处理

# 方式4: 模拟多次不同返回
@patch("litellm.acompletion")
def test_multiple_returns(mock_acompletion):
    mock_acompletion.side_effect = [
        {"choices": [{"message": {"content": "First"}}], "usage": {"total_tokens": 5}},
        {"choices": [{"message": {"content": "Second"}}], "usage": {"total_tokens": 8}},
        Exception("Third call fails"),
    ]
    # 第1次返回First，第2次返回Second，第3次抛异常
```

### 4.2 Mock时间（加速定时任务）

```python
from unittest.mock import patch
import asyncio

@patch("asyncio.sleep")
def test_accelerated_timer(mock_sleep):
    """将asyncio.sleep Mock掉，使定时任务瞬间完成"""
    mock_sleep.return_value = asyncio.Future()
    mock_sleep.return_value.set_result(None)
    # 健康检查中的await asyncio.sleep(interval) 会立即返回

# 或者使用freezegun
from freezegun import freeze_time

@freeze_time("2025-01-01 12:00:00")
def test_with_frozen_time():
    # 所有datetime.now()返回固定时间
    from datetime import datetime
    assert datetime.now().isoformat() == "2025-01-01T12:00:00"
```

### 4.3 Mock环境变量

```python
from unittest.mock import patch

# 方式1: patch.dict
@patch.dict("os.environ", {
    "CPA_M1_API_HUB": "true",
    "CPA_PROVIDER_0_ID": "test_p",
    "CPA_PROVIDER_0_NAME": "Test",
    "CPA_PROVIDER_0_MODEL": "gpt-4",
    "CPA_PROVIDER_0_API_BASE": "https://api.test.com",
    "CPA_PROVIDER_0_API_KEY": "sk-test",
}, clear=False)
def test_with_env():
    import os
    assert os.environ["CPA_M1_API_HUB"] == "true"

# 方式2: 使用pytest的monkeypatch
def test_with_monkeypatch(monkeypatch):
    monkeypatch.setenv("CPA_M1_API_HUB", "false")
    assert os.environ["CPA_M1_API_HUB"] == "false"
```

### 4.4 Mock TUI渲染

```python
from unittest.mock import Mock, patch, MagicMock

@patch("cpa_modules.m1_api_hub.status_display.Table")
@patch("cpa_modules.m1_api_hub.status_display.Panel")
def test_tui_render(mock_panel_cls, mock_table_cls):
    mock_table = MagicMock()
    mock_table_cls.return_value = mock_table
    mock_panel = MagicMock()
    mock_panel_cls.return_value = mock_panel
    
    # 渲染后验证add_row被正确调用
    # 验证每个Provider都生成了一行
    assert mock_table.add_row.called
```

---

## 五、测试数据

### 5.1 虚拟Provider配置（5个）

```python
# tests/fixtures/providers.py

from cpa_modules.m1_api_hub.models import ProviderConfig

TEST_PROVIDERS = [
    ProviderConfig(
        id="zhongzhuan_a_claude",
        name="中转站A-Claude",
        model="openai/claude-sonnet-4",
        api_base="https://api.zhongzhuan-a.com/v1",
        api_key="sk-test-key-a-12345",
        timeout=30, max_retries=3, rpm_limit=60, tpm_limit=100000,
        priority=1, enabled=True, is_backup=False
    ),
    ProviderConfig(
        id="zhongzhuan_b_claude",
        name="中转站B-Claude",
        model="openai/claude-sonnet-4",
        api_base="https://api.zhongzhuan-b.com/v1",
        api_key="sk-test-key-b-67890",
        timeout=30, max_retries=3, rpm_limit=40, tpm_limit=80000,
        priority=2, enabled=True, is_backup=True
    ),
    ProviderConfig(
        id="zhongzhuan_a_gpt4",
        name="中转站A-GPT4",
        model="openai/gpt-4",
        api_base="https://api.zhongzhuan-a.com/v1",
        api_key="sk-test-key-a-12345",
        timeout=45, max_retries=3, rpm_limit=30, tpm_limit=50000,
        priority=3, enabled=True, is_backup=False
    ),
    ProviderConfig(
        id="deepseek_official",
        name="DeepSeek官方",
        model="deepseek/deepseek-chat",
        api_base="https://api.deepseek.com/v1",
        api_key="sk-test-key-deep-abcde",
        timeout=60, max_retries=5, rpm_limit=20, tpm_limit=40000,
        priority=4, enabled=True, is_backup=False
    ),
    ProviderConfig(
        id="official_claude",
        name="官方-Claude",
        model="anthropic/claude-3-sonnet",
        api_base="https://api.anthropic.com/v1",
        api_key="sk-test-key-ant-fghij",
        timeout=30, max_retries=3, rpm_limit=100, tpm_limit=200000,
        priority=5, enabled=True, is_backup=False
    ),
]
```

### 5.2 健康检查Mock响应数据

```python
# tests/fixtures/health_responses.py

# 成功响应（正常延迟）
HEALTH_RESPONSE_OK_FAST = {
    "choices": [{"message": {"content": "OK"}}],
    "usage": {"prompt_tokens": 2, "completion_tokens": 1}
}

# 成功响应（慢延迟 > 5s，应标记degraded）
HEALTH_RESPONSE_OK_SLOW = {
    "choices": [{"message": {"content": "OK... eventually"}}],
    "usage": {"prompt_tokens": 2, "completion_tokens": 3}
}

# 异常响应列表（用于连续失败测试）
HEALTH_RESPONSE_SEQUENCE_FAIL_3X = [
    Exception("Connection timeout"),
    Exception("Connection timeout"),
    Exception("Connection timeout"),
]

# 恢复序列（2次成功）
HEALTH_RESPONSE_SEQUENCE_RECOVER = [
    {"choices": [{"message": {"content": "OK"}}], "usage": {"total_tokens": 3}},
    {"choices": [{"message": {"content": "OK again"}}], "usage": {"total_tokens": 3}},
]
```

### 5.3 Token消耗测试数据

```python
# tests/fixtures/cost_data.py

from cpa_modules.m1_api_hub.models import RequestLog
from datetime import datetime

# 构建会话测试数据
def generate_session_logs(provider_id: str, count: int, base_cost: float = 0.02):
    """生成指定Provider的测试请求日志"""
    logs = []
    for i in range(count):
        logs.append(RequestLog(
            request_id=f"{provider_id}-req-{i:03d}",
            provider_id=provider_id,
            model="gpt-4" if "gpt" in provider_id else "claude-3",
            prompt_tokens=1000 + i * 200,
            completion_tokens=300 + i * 50,
            response_time_ms=800 + i * 100,
            success=True,
            error_message="",
            timestamp=datetime.now(),
            cost_usd=base_cost + i * 0.005
        ))
    return logs

# 典型会话数据集
SESSION_DATASET_SMALL = {
    "provider_a": generate_session_logs("provider_a", 5, 0.01),
    "provider_b": generate_session_logs("provider_b", 3, 0.015),
}

# 高消耗数据集（用于预算告警测试）
SESSION_DATASET_LARGE = {
    "provider_a": generate_session_logs("provider_a", 50, 0.05),
    "provider_b": generate_session_logs("provider_b", 30, 0.08),
}

# 单次大请求（用于超限测试）
LARGE_SINGLE_REQUEST = RequestLog(
    request_id="big-req-001",
    provider_id="provider_a",
    model="gpt-4",
    prompt_tokens=1000000,    # 1M tokens
    completion_tokens=200000, # 200K tokens
    response_time_ms=30000,
    success=True,
    error_message="",
    timestamp=datetime.now(),
    cost_usd=50.0  # $50 —— 超过默认预算
)
```

---

## 六、覆盖率目标

### 6.1 覆盖率指标

| 指标 | 目标值 | 说明 |
|------|--------|------|
| **行覆盖率** | >= 80% | 核心业务逻辑行 |
| **分支覆盖率** | >= 70% | if/else/try-except各分支 |
| **函数覆盖率** | 100% | 所有公开函数 |

### 6.2 各文件覆盖率目标

| 文件 | 行覆盖目标 | 关键未覆盖场景 |
|------|-----------|--------------|
| `models.py` | 95% | 边界值校验 |
| `provider_manager.py` | 85% | 异常处理分支 |
| `failover_monitor.py` | 80% | 定时任务调度 |
| `cost_tracker.py` | 85% | 预算边界条件 |
| `status_display.py` | 75% | TUI渲染细节 |
| `__init__.py` | 90% | 开关控制逻辑 |

### 6.3 覆盖率报告生成

```bash
# 运行测试并生成覆盖率报告
pytest tests/ -v --cov=cpa_modules.m1_api_hub --cov-report=term-missing --cov-report=html

# 生成XML报告（CI/CD使用）
pytest tests/ --cov=cpa_modules.m1_api_hub --cov-report=xml:coverage.xml

# 仅运行特定模块的测试
pytest tests/test_provider_manager.py -v --cov=cpa_modules.m1_api_hub.provider_manager
```

---

## 七、附录：运行命令

### 7.1 运行全部测试

```bash
# 进入项目目录
cd /path/to/pentestagent

# 安装测试依赖
pip install -r requirements-test.txt

# 运行全部M1测试
pytest cpa_modules/m1_api_hub/tests/ -v

# 运行并显示覆盖率
pytest cpa_modules/m1_api_hub/tests/ -v --cov=cpa_modules.m1_api_hub --cov-report=term-missing
```

### 7.2 运行特定测试

```bash
# 按用例ID搜索运行
pytest -k "TC-M1-001" -v

# 运行Provider管理相关测试
pytest -k "provider" -v

# 运行健康检查相关测试
pytest -k "health" -v

# 运行集成测试
pytest -k "INT" -v

# 运行P0优先级测试
pytest -k "P0 or test_" -m "p0" -v
```

### 7.3 连续运行（开发模式）

```bash
# 文件变更时自动运行
pytest cpa_modules/m1_api_hub/tests/ -f

# 调试模式（失败时进入pdb）
pytest cpa_modules/m1_api_hub/tests/ --pdb

# 并行运行（加速）
pytest cpa_modules/m1_api_hub/tests/ -n auto
```

---

## 附录：测试文件结构

```
cpa_modules/m1_api_hub/tests/
├── __init__.py
├── conftest.py              # 共享fixtures
├── fixtures/
│   ├── __init__.py
│   ├── providers.py         # Provider测试数据
│   ├── health_responses.py  # 健康检查响应Mock
│   └── cost_data.py         # Token消耗测试数据
├── test_provider_manager.py # Provider管理测试 (TC-M1-001~007)
├── test_failover_monitor.py # 健康检查+故障转移测试 (TC-M1-008~016)
├── test_cost_tracker.py     # Token追踪+预算测试 (TC-M1-017~020)
├── test_status_display.py   # TUI展示测试 (TC-M1-021~023)
├── test_module_switch.py    # 模块开关测试 (TC-M1-024)
└── test_integration.py      # 集成测试 (TC-M1-INT-001~005)
```

---

**文档结束**  
*共计 24 个单元测试用例 + 5 个集成测试用例 + 2 个端到端场景*
