"""
故障转移模块单元测试

测试故障转移策略、重试配置、故障转移执行器等
"""

import pytest
import asyncio
from datetime import datetime
from typing import Dict, Any, List

from src.router.failover import (
    FailoverStrategyType,
    FailoverConfig,
    FailoverResult,
    FailoverExecutor,
    FailoverStrategy,
    FailureType,
    RetryConfig,
    SequentialFailoverStrategy,
    FastFailoverStrategy,
    PriorityFailoverStrategy,
    ProviderState,
    create_failover_strategy,
    detect_failure_type,
)


class TestRetryConfig:
    """测试重试配置"""
    
    def test_default_retry_config(self):
        """测试默认重试配置"""
        config = RetryConfig()
        
        assert config.max_retries == 3
        assert config.initial_delay == 1.0
        assert config.max_delay == 60.0
        assert config.exponential_base == 2.0
        assert config.jitter is True
    
    def test_get_delay_no_jitter(self):
        """测试获取延迟（无抖动）"""
        config = RetryConfig(jitter=False)
        
        # 第 0 次重试
        assert config.get_delay(0) == 1.0
        # 第 1 次重试
        assert config.get_delay(1) == 2.0
        # 第 2 次重试
        assert config.get_delay(2) == 4.0
        # 第 3 次重试
        assert config.get_delay(3) == 8.0
    
    def test_get_delay_with_max_delay(self):
        """测试最大延迟限制"""
        config = RetryConfig(max_delay=10.0, jitter=False)
        
        # 超过最大延迟
        assert config.get_delay(10) == 10.0
        assert config.get_delay(20) == 10.0
    
    def test_get_delay_with_jitter(self):
        """测试带抖动的延迟"""
        config = RetryConfig(initial_delay=1.0, jitter=True)
        
        # 抖动应该在一定范围内
        delay = config.get_delay(0)
        assert 0.9 <= delay <= 1.1


class TestFailoverConfig:
    """测试故障转移配置"""
    
    def test_default_failover_config(self):
        """测试默认故障转移配置"""
        config = FailoverConfig()
        
        assert config.strategy == FailoverStrategyType.SEQUENTIAL
        assert config.timeout == 30.0
        assert config.max_retries == 5
        assert config.enabled is True


class TestProviderState:
    """测试提供者状态"""
    
    def test_initial_state(self):
        """测试初始状态"""
        state = ProviderState(name="test_provider")
        
        assert state.name == "test_provider"
        assert state.is_healthy is True
        assert state.failure_count == 0
        assert state.consecutive_failures == 0
        assert state.total_requests == 0
    
    def test_record_failure(self):
        """测试记录失败"""
        state = ProviderState(name="test_provider")
        
        state.record_failure(FailureType.TIMEOUT)
        
        assert state.failure_count == 1
        assert state.consecutive_failures == 1
        assert state.total_failures == 1
        assert state.last_failure_time is not None
    
    def test_record_success(self):
        """测试记录成功"""
        state = ProviderState(name="test_provider")
        
        # 先记录失败
        state.record_failure(FailureType.TIMEOUT)
        assert state.consecutive_failures == 1
        
        # 再记录成功
        state.record_success(0.5)
        
        assert state.consecutive_failures == 0
        assert state.last_success_time is not None
        assert state.avg_response_time > 0
    
    def test_should_circuit_break(self):
        """测试是否应该熔断"""
        config = FailoverConfig(max_failures=3)
        state = ProviderState(name="test_provider")
        
        # 未达到熔断阈值
        assert state.should_circuit_break(config) is False
        
        # 达到熔断阈值
        for _ in range(3):
            state.record_failure(FailureType.TIMEOUT)
        
        assert state.should_circuit_break(config) is True
    
    def test_can_recover(self):
        """测试是否可以恢复"""
        config = FailoverConfig(recovery_timeout=1.0)
        state = ProviderState(name="test_provider")
        
        # 没有失败记录时可以恢复
        assert state.can_recover(config) is True
        
        # 记录失败后不能立即恢复
        state.record_failure(FailureType.TIMEOUT)
        assert state.can_recover(config) is False
        
        # 等待恢复超时后可以恢复
        import time
        time.sleep(1.1)
        assert state.can_recover(config) is True


class TestFailoverResult:
    """测试故障转移结果"""
    
    def test_successful_result(self):
        """测试成功结果"""
        result = FailoverResult(
            success=True,
            provider_name="provider1",
            response={"data": "test"},
            attempts=1,
            total_time=0.5
        )
        
        assert result.success is True
        assert result.provider_name == "provider1"
        assert result.error is None
        assert result.failover_occurred is False
    
    def test_failed_result(self):
        """测试失败结果"""
        result = FailoverResult(
            success=False,
            error="Connection timeout",
            error_type=FailureType.TIMEOUT,
            attempts=3,
            tried_providers=["provider1", "provider2", "provider3"],
            failover_occurred=True
        )
        
        assert result.success is False
        assert result.error == "Connection timeout"
        assert result.error_type == FailureType.TIMEOUT
        assert result.failover_occurred is True


class TestSequentialFailoverStrategy:
    """测试顺序故障转移策略"""
    
    @pytest.mark.asyncio
    async def test_select_next_provider(self):
        """测试选择下一个提供者"""
        config = FailoverConfig()
        strategy = SequentialFailoverStrategy(config)
        
        providers = ["provider1", "provider2", "provider3"]
        
        # 初始化提供者状态
        for p in providers:
            strategy.initialize_provider(p)
        
        # 选择 provider1 的下一个
        next_provider = await strategy.select_next_provider(
            "provider1",
            providers,
            FailureType.TIMEOUT
        )
        
        assert next_provider == "provider2"
    
    @pytest.mark.asyncio
    async def test_skip_unhealthy_provider(self):
        """测试跳过不健康的提供者"""
        config = FailoverConfig()
        strategy = SequentialFailoverStrategy(config)
        
        providers = ["provider1", "provider2", "provider3"]
        
        # 初始化并标记 provider2 为不健康
        for p in providers:
            strategy.initialize_provider(p)
        
        strategy.provider_states["provider2"].is_healthy = False
        
        # 应该跳过 provider2
        next_provider = await strategy.select_next_provider(
            "provider1",
            providers,
            FailureType.TIMEOUT
        )
        
        assert next_provider == "provider3"
    
    @pytest.mark.asyncio
    async def test_no_failover_for_auth_error(self):
        """测试认证错误不触发故障转移"""
        config = FailoverConfig()
        strategy = SequentialFailoverStrategy(config)
        
        providers = ["provider1", "provider2"]
        
        next_provider = await strategy.select_next_provider(
            "provider1",
            providers,
            FailureType.AUTHENTICATION_ERROR
        )
        
        assert next_provider is None


class TestFastFailoverStrategy:
    """测试快速失败故障转移策略"""
    
    @pytest.mark.asyncio
    async def test_fast_failover_on_timeout(self):
        """测试超时快速故障转移"""
        config = FailoverConfig(fast_failover_threshold=5.0)
        strategy = FastFailoverStrategy(config)
        
        providers = ["provider1", "provider2"]
        
        # 初始化提供者状态
        for p in providers:
            strategy.initialize_provider(p)
        
        # provider2 响应时间较快
        strategy.provider_states["provider2"].avg_response_time = 2.0
        
        # 超时应该触发快速故障转移
        next_provider = await strategy.select_next_provider(
            "provider1",
            providers,
            FailureType.TIMEOUT
        )
        
        assert next_provider == "provider2"


class TestPriorityFailoverStrategy:
    """测试优先级故障转移策略"""
    
    @pytest.mark.asyncio
    async def test_select_by_priority(self):
        """测试按优先级选择"""
        config = FailoverConfig()
        priorities = {
            "provider1": 3,
            "provider2": 1,
            "provider3": 2
        }
        
        strategy = PriorityFailoverStrategy(config, priorities)
        
        providers = ["provider1", "provider2", "provider3"]
        
        # 初始化提供者状态
        for p in providers:
            strategy.initialize_provider(p)
        
        # 应该按优先级顺序选择
        next_provider = await strategy.select_next_provider(
            "provider1",  # 优先级 3
            providers,
            FailureType.TIMEOUT
        )
        
        # 下一个应该是 provider3（优先级 2）
        assert next_provider == "provider3"


class TestFailoverExecutor:
    """测试故障转移执行器"""
    
    @pytest.mark.asyncio
    async def test_execute_success_first_try(self):
        """测试第一次尝试成功"""
        config = FailoverConfig()
        strategy = SequentialFailoverStrategy(config)
        executor = FailoverExecutor(strategy, config)
        
        async def request_func(provider_name: str):
            return {"status": "success", "provider": provider_name}
        
        result = await executor.execute_with_failover(
            request_func=request_func,
            provider_name="provider1",
            available_providers=["provider1", "provider2"],
            detect_failure_type=detect_failure_type
        )
        
        assert result.success is True
        assert result.provider_name == "provider1"
        assert result.attempts == 1
    
    @pytest.mark.asyncio
    async def test_execute_failover_on_failure(self):
        """测试失败时故障转移"""
        config = FailoverConfig(max_retries=2, timeout=5.0)
        strategy = SequentialFailoverStrategy(config)
        executor = FailoverExecutor(strategy, config)
        
        call_count = 0
        
        async def request_func(provider_name: str):
            nonlocal call_count
            call_count += 1
            
            if provider_name == "provider1":
                raise asyncio.TimeoutError("Timeout")
            elif provider_name == "provider2":
                return {"status": "success", "provider": provider_name}
            else:
                raise Exception("Unknown provider")
        
        result = await executor.execute_with_failover(
            request_func=request_func,
            provider_name="provider1",
            available_providers=["provider1", "provider2"],
            detect_failure_type=detect_failure_type
        )
        
        assert result.success is True
        assert result.provider_name == "provider2"
        assert result.failover_occurred is True
        assert len(result.tried_providers) >= 2
    
    @pytest.mark.asyncio
    async def test_execute_all_providers_fail(self):
        """测试所有提供者都失败"""
        config = FailoverConfig(max_retries=1, timeout=1.0)
        strategy = SequentialFailoverStrategy(config)
        executor = FailoverExecutor(strategy, config)
        
        async def request_func(provider_name: str):
            raise asyncio.TimeoutError("Timeout")
        
        result = await executor.execute_with_failover(
            request_func=request_func,
            provider_name="provider1",
            available_providers=["provider1", "provider2"],
            detect_failure_type=detect_failure_type
        )
        
        assert result.success is False
        assert result.error_type == FailureType.TIMEOUT
        assert len(result.tried_providers) >= 2


class TestCreateFailoverStrategy:
    """测试创建故障转移策略"""
    
    def test_create_sequential_strategy(self):
        """测试创建顺序策略"""
        config = FailoverConfig()
        strategy = create_failover_strategy(
            FailoverStrategyType.SEQUENTIAL,
            config
        )
        
        assert isinstance(strategy, SequentialFailoverStrategy)
    
    def test_create_fast_failover_strategy(self):
        """测试创建快速失败策略"""
        config = FailoverConfig()
        strategy = create_failover_strategy(
            FailoverStrategyType.FAST_FAILOVER,
            config
        )
        
        assert isinstance(strategy, FastFailoverStrategy)
    
    def test_create_priority_strategy(self):
        """测试创建优先级策略"""
        config = FailoverConfig()
        strategy = create_failover_strategy(
            FailoverStrategyType.PRIORITY_BASED,
            config,
            provider_priorities={"p1": 1, "p2": 2}
        )
        
        assert isinstance(strategy, PriorityFailoverStrategy)
    
    def test_create_invalid_strategy(self):
        """测试创建无效策略"""
        with pytest.raises(ValueError, match="不支持的故障转移策略"):
            create_failover_strategy(
                "invalid_strategy",  # type: ignore
                FailoverConfig()
            )


class TestDetectFailureType:
    """测试失败类型检测"""
    
    def test_detect_timeout(self):
        """测试检测超时"""
        exception = asyncio.TimeoutError("Request timed out")
        failure_type = detect_failure_type(exception)
        
        assert failure_type == FailureType.TIMEOUT
    
    def test_detect_network_error(self):
        """测试检测网络错误"""
        # 简单测试，避免复杂的 aiohttp 异常
        exception = ConnectionError("Network connection failed")
        failure_type = detect_failure_type(exception)
        
        # ConnectionError 应该被识别为网络错误
        assert failure_type == FailureType.NETWORK_ERROR
    
    def test_detect_unknown(self):
        """测试检测未知错误"""
        exception = ValueError("Some random error")
        failure_type = detect_failure_type(exception)
        
        assert failure_type == FailureType.UNKNOWN
    
    def test_detect_service_unavailable(self):
        """测试检测服务不可用"""
        # 通过错误消息检测
        exception = Exception("503 Service Unavailable")
        failure_type = detect_failure_type(exception)
        
        assert failure_type == FailureType.SERVICE_UNAVAILABLE
    
    def test_detect_rate_limited(self):
        """测试检测速率限制"""
        # 通过错误消息检测
        exception = Exception("429 Too Many Requests - rate limit exceeded")
        failure_type = detect_failure_type(exception)
        
        assert failure_type == FailureType.RATE_LIMITED


class TestFailoverIntegration:
    """故障转移集成测试"""
    
    @pytest.mark.asyncio
    async def test_auto_failover_flow(self):
        """测试自动故障转移流程"""
        config = FailoverConfig(
            strategy=FailoverStrategyType.SEQUENTIAL,
            timeout=2.0,
            max_retries=2
        )
        
        strategy = create_failover_strategy(FailoverStrategyType.SEQUENTIAL, config)
        executor = FailoverExecutor(strategy, config)
        
        # 模拟提供者故障序列
        failure_sequence = {
            "provider1": 2,  # 前 2 次失败
            "provider2": 0,  # 立即成功
        }
        
        call_counts: Dict[str, int] = {}
        
        async def request_func(provider_name: str):
            call_counts[provider_name] = call_counts.get(provider_name, 0) + 1
            
            remaining_failures = failure_sequence.get(provider_name, 0)
            if remaining_failures > 0:
                failure_sequence[provider_name] -= 1
                raise asyncio.TimeoutError("Simulated timeout")
            
            return {"provider": provider_name, "status": "success"}
        
        result = await executor.execute_with_failover(
            request_func=request_func,
            provider_name="provider1",
            available_providers=["provider1", "provider2"],
            detect_failure_type=detect_failure_type
        )
        
        assert result.success is True
        assert result.provider_name == "provider2"
        assert result.failover_occurred is True
        assert call_counts["provider1"] == 2
        assert call_counts["provider2"] == 1


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
