"""
路由器故障转移集成单元测试

测试路由器与故障转移、健康检查的集成
"""

import pytest
import asyncio
from typing import Dict, Any, List

from src.router.router import (
    Router,
    AsyncRouter,
    RouterConfig,
    ClientRequest,
)
from src.router.provider_manager import ProviderConfig, ProviderType
from src.router.failover import FailoverStrategyType, FailureType
from src.router.health_check import HealthStatus


class TestRouterFailoverConfig:
    """测试路由器故障转移配置"""
    
    def test_router_with_failover_config(self):
        """测试带故障转移配置的路由器"""
        config = RouterConfig(
            enable_failover=True,
            failover_strategy=FailoverStrategyType.SEQUENTIAL,
            failover_timeout=10.0,
            failover_max_retries=2
        )
        
        router = Router(config)
        
        assert router.config.enable_failover is True
        assert router.failover_strategy is not None
        assert router.failover_executor is not None
    
    def test_router_without_failover(self):
        """测试禁用故障转移的路由器"""
        config = RouterConfig(
            enable_failover=False
        )
        
        router = Router(config)
        
        assert router.config.enable_failover is False
        assert router.failover_strategy is None
        assert router.failover_executor is None
    
    def test_router_with_health_check(self):
        """测试带健康检查的路由器"""
        config = RouterConfig(
            enable_health_check=True,
            health_check_interval=30
        )
        
        router = Router(config)
        
        assert router.config.enable_health_check is True
        assert router.health_checker is not None
        assert router.passive_health_checker is not None


class TestRouterProviderHealth:
    """测试路由器提供者健康管理"""
    
    def test_add_provider_initializes_health(self):
        """测试添加提供者时初始化健康检查"""
        config = RouterConfig(enable_health_check=True)
        router = Router(config)
        
        provider_config = ProviderConfig(
            name="test_provider",
            provider_type=ProviderType.OPENAI,
            base_url="http://localhost:8000",
            api_key="test_key",
            models=["gpt-3.5"]
        )
        
        provider = router.add_provider(provider_config)
        
        # 健康检查应该初始化
        assert router.health_checker is not None
        metrics = router.health_checker.get_provider_metrics("test_provider")
        assert metrics is not None
    
    def test_mark_provider_unhealthy(self):
        """测试标记提供者为不健康"""
        router = Router()
        
        provider_config = ProviderConfig(
            name="test_provider",
            provider_type=ProviderType.OPENAI,
            base_url="http://localhost:8000",
            api_key="test_key"
        )
        
        router.add_provider(provider_config)
        
        # 初始健康
        provider = router.get_provider("test_provider")
        assert provider.is_healthy is True
        
        # 标记为不健康
        router.mark_provider_unhealthy("test_provider")
        
        assert provider.is_healthy is False
    
    def test_mark_provider_healthy(self):
        """测试标记提供者为健康"""
        router = Router()
        
        provider_config = ProviderConfig(
            name="test_provider",
            provider_type=ProviderType.OPENAI,
            base_url="http://localhost:8000",
            api_key="test_key"
        )
        
        provider = router.add_provider(provider_config)
        
        # 先标记为不健康
        router.mark_provider_unhealthy("test_provider")
        assert provider.is_healthy is False
        
        # 再标记为健康
        router.mark_provider_healthy("test_provider")
        
        assert provider.is_healthy is True


class TestAsyncRouterFailover:
    """测试异步路由器故障转移"""
    
    @pytest.mark.asyncio
    async def test_execute_with_failover_disabled(self):
        """测试禁用故障转移时的执行"""
        config = RouterConfig(enable_failover=False)
        router = AsyncRouter(config)
        
        async def request_func(provider_name: str):
            return {"status": "success"}
        
        result = await router.execute_with_failover(
            request_func=request_func,
            model_name="gpt-3.5"
        )
        
        # 应该直接执行成功
        assert result.success is True
        assert result.attempts == 1
    
    @pytest.mark.asyncio
    async def test_execute_with_failover_no_provider(self):
        """测试没有提供者时的故障转移"""
        config = RouterConfig(enable_failover=True)
        router = AsyncRouter(config)
        
        async def request_func(provider_name: str):
            return {"status": "success"}
        
        result = await router.execute_with_failover(
            request_func=request_func,
            model_name="gpt-3.5"
        )
        
        # 应该失败，因为没有提供者
        assert result.success is False
        assert "没有可用的提供者" in result.error
    
    @pytest.mark.asyncio
    async def test_execute_with_failover_success(self):
        """测试故障转移成功"""
        config = RouterConfig(
            enable_failover=True,
            enable_health_check=False
        )
        router = AsyncRouter(config)
        
        # 添加提供者
        provider_config = ProviderConfig(
            name="test_provider",
            provider_type=ProviderType.OPENAI,
            base_url="http://localhost:8000",
            api_key="test_key",
            models=["gpt-3.5"]
        )
        router.add_provider(provider_config)
        
        async def request_func(provider_name: str):
            return {"status": "success", "provider": provider_name}
        
        result = await router.execute_with_failover(
            request_func=request_func,
            model_name="gpt-3.5"
        )
        
        assert result.success is True
        assert result.provider_name == "test_provider"
        assert result.attempts == 1
    
    @pytest.mark.asyncio
    async def test_execute_with_failover_and_retry(self):
        """测试故障转移和重试"""
        config = RouterConfig(
            enable_failover=True,
            failover_max_retries=2,
            failover_timeout=5.0,
            enable_health_check=False
        )
        router = AsyncRouter(config)
        
        # 添加两个提供者
        provider_config1 = ProviderConfig(
            name="provider1",
            provider_type=ProviderType.OPENAI,
            base_url="http://localhost:8000",
            api_key="test_key",
            models=["gpt-3.5"]
        )
        provider_config2 = ProviderConfig(
            name="provider2",
            provider_type=ProviderType.ANTHROPIC,
            base_url="http://localhost:8001",
            api_key="test_key",
            models=["claude-3"]
        )
        router.add_provider(provider_config1)
        router.add_provider(provider_config2)
        
        call_count = 0
        
        async def request_func(provider_name: str):
            nonlocal call_count
            call_count += 1
            
            if provider_name == "provider1":
                raise asyncio.TimeoutError("Simulated timeout")
            elif provider_name == "provider2":
                return {"status": "success", "provider": provider_name}
            else:
                raise Exception("Unknown provider")
        
        result = await router.execute_with_failover(
            request_func=request_func,
            model_name="gpt-3.5"
        )
        
        # 应该故障转移到 provider2 成功
        assert result.success is True
        assert result.provider_name == "provider2"
        assert result.failover_occurred is True


class TestRouterAutoFailover:
    """测试路由器自动故障转移（auto 模型）"""
    
    @pytest.mark.asyncio
    async def test_send_request_with_auto_failover(self):
        """测试 auto 模型的自动故障转移"""
        config = RouterConfig(
            enable_failover=True,
            enable_health_check=False,
            failover_timeout=5.0
        )
        router = AsyncRouter(config)
        
        # 添加提供者
        provider_config = ProviderConfig(
            name="test_provider",
            provider_type=ProviderType.OPENAI,
            base_url="http://localhost:8000",
            api_key="test_key",
            models=["gpt-3.5"]
        )
        router.add_provider(provider_config)
        
        # 创建 auto 模型请求
        request = ClientRequest(
            model="auto",
            messages=[{"role": "user", "content": "Hello"}],
            stream=False
        )
        
        async def send_func(transformed_request, provider):
            return {"status": "success"}
        
        # 执行请求
        response = await router.send_request_with_auto_failover(
            client_request=request,
            send_func=send_func
        )
        
        assert response is not None
        assert response["status"] == "success"
    
    @pytest.mark.asyncio
    async def test_auto_failover_multiple_providers(self):
        """测试多个提供者的 auto 故障转移"""
        config = RouterConfig(
            enable_failover=True,
            enable_health_check=False,
            failover_timeout=5.0
        )
        router = AsyncRouter(config)
        
        # 添加多个提供者
        for i in range(3):
            provider_config = ProviderConfig(
                name=f"provider{i}",
                provider_type=ProviderType.OPENAI,
                base_url=f"http://localhost:800{i}",
                api_key="test_key",
                models=["model"]
            )
            router.add_provider(provider_config)
        
        request = ClientRequest(
            model="auto",
            messages=[{"role": "user", "content": "Hello"}],
            stream=False
        )
        
        tried_providers = []
        
        async def send_func(transformed_request, provider):
            tried_providers.append(provider.name)
            
            # 前两个提供者失败
            if provider.name in ["provider0", "provider1"]:
                raise asyncio.TimeoutError("Simulated timeout")
            
            return {"status": "success", "provider": provider.name}
        
        response = await router.send_request_with_auto_failover(
            client_request=request,
            send_func=send_func
        )
        
        # 应该尝试了至少 2 个提供者
        assert len(tried_providers) >= 2
        assert response["status"] == "success"


class TestRouterHealthCheckIntegration:
    """测试路由器健康检查集成"""
    
    def test_router_status_with_health_check(self):
        """测试带健康检查的路由器状态"""
        config = RouterConfig(
            enable_failover=True,
            enable_health_check=True
        )
        router = Router(config)
        
        # 添加提供者
        provider_config = ProviderConfig(
            name="test_provider",
            provider_type=ProviderType.OPENAI,
            base_url="http://localhost:8000",
            api_key="test_key"
        )
        router.add_provider(provider_config)
        
        status = router.get_status()
        
        assert "failover_enabled" in status
        assert "health_check" in status
        assert status["failover_strategy"] == "sequential"
    
    def test_passive_health_check_on_request(self):
        """测试请求时的被动健康检查"""
        config = RouterConfig(
            enable_failover=True,
            enable_health_check=True
        )
        router = AsyncRouter(config)
        
        provider_config = ProviderConfig(
            name="test_provider",
            provider_type=ProviderType.OPENAI,
            base_url="http://localhost:8000",
            api_key="test_key",
            models=["gpt-3.5"]
        )
        router.add_provider(provider_config)
        
        # 记录被动检查
        router.passive_health_checker.record_request(
            "test_provider",
            success=True,
            response_time=0.5
        )
        
        # 检查指标
        metrics = router.passive_health_checker._metrics["test_provider"]
        assert metrics.total_successes == 1


class TestRouterFailoverStrategies:
    """测试不同故障转移策略"""
    
    def test_sequential_strategy(self):
        """测试顺序故障转移策略"""
        config = RouterConfig(
            enable_failover=True,
            failover_strategy=FailoverStrategyType.SEQUENTIAL
        )
        router = Router(config)
        
        assert router.failover_strategy is not None
        assert router.config.failover_strategy == FailoverStrategyType.SEQUENTIAL
    
    def test_fast_failover_strategy(self):
        """测试快速失败策略"""
        config = RouterConfig(
            enable_failover=True,
            failover_strategy=FailoverStrategyType.FAST_FAILOVER
        )
        router = Router(config)
        
        assert router.failover_strategy is not None
        assert router.config.failover_strategy == FailoverStrategyType.FAST_FAILOVER
    
    def test_priority_strategy(self):
        """测试优先级策略"""
        config = RouterConfig(
            enable_failover=True,
            failover_strategy=FailoverStrategyType.PRIORITY_BASED
        )
        router = Router(config)
        
        assert router.failover_strategy is not None
        assert router.config.failover_strategy == FailoverStrategyType.PRIORITY_BASED


class TestRouterClear:
    """测试路由器清空"""
    
    def test_clear_with_health_check(self):
        """测试带健康检查的清空"""
        config = RouterConfig(enable_health_check=True)
        router = Router(config)
        
        provider_config = ProviderConfig(
            name="test_provider",
            provider_type=ProviderType.OPENAI,
            base_url="http://localhost:8000",
            api_key="test_key"
        )
        router.add_provider(provider_config)
        
        # 清空
        router.clear()
        
        # 检查所有状态已清空
        assert len(router.provider_manager._providers) == 0
        assert len(router._request_log) == 0
        if router.health_checker:
            assert len(router.health_checker._provider_metrics) == 0


class TestRouterErrorHandling:
    """测试路由器错误处理"""
    
    @pytest.mark.asyncio
    async def test_timeout_error_handling(self):
        """测试超时错误处理"""
        config = RouterConfig(
            enable_failover=True,
            failover_timeout=1.0,
            enable_health_check=False
        )
        router = AsyncRouter(config)
        
        provider_config = ProviderConfig(
            name="slow_provider",
            provider_type=ProviderType.OPENAI,
            base_url="http://localhost:8000",
            api_key="test_key"
        )
        router.add_provider(provider_config)
        
        async def slow_request(provider_name: str):
            await asyncio.sleep(10)  # 模拟慢请求
            return {"status": "success"}
        
        result = await router.execute_with_failover(
            request_func=slow_request,
            model_name="gpt-3.5"
        )
        
        # 应该超时失败
        assert result.success is False
        assert result.error_type == FailureType.TIMEOUT
    
    @pytest.mark.asyncio
    async def test_network_error_handling(self):
        """测试网络错误处理"""
        config = RouterConfig(
            enable_failover=True,
            enable_health_check=False
        )
        router = AsyncRouter(config)
        
        provider_config = ProviderConfig(
            name="test_provider",
            provider_type=ProviderType.OPENAI,
            base_url="http://localhost:8000",
            api_key="test_key"
        )
        router.add_provider(provider_config)
        
        async def network_error_request(provider_name: str):
            raise ConnectionError("Network error")
        
        result = await router.execute_with_failover(
            request_func=network_error_request,
            model_name="gpt-3.5"
        )
        
        # 应该失败
        assert result.success is False


class TestRouterFailoverMetrics:
    """测试路由器故障转移指标"""
    
    @pytest.mark.asyncio
    async def test_failover_metrics_collection(self):
        """测试故障转移指标收集"""
        config = RouterConfig(
            enable_failover=True,
            enable_health_check=True,
            failover_timeout=5.0
        )
        router = AsyncRouter(config)
        
        provider_config = ProviderConfig(
            name="test_provider",
            provider_type=ProviderType.OPENAI,
            base_url="http://localhost:8000",
            api_key="test_key",
            models=["gpt-3.5"]
        )
        router.add_provider(provider_config)
        
        # 模拟多次请求
        for i in range(5):
            success = i % 2 == 0
            router.passive_health_checker.record_request(
                "test_provider",
                success=success,
                response_time=0.3 if success else 0.0
            )
        
        # 检查指标
        metrics = router.passive_health_checker._metrics["test_provider"]
        assert metrics.total_requests == 5
        assert metrics.total_successes == 3
        assert metrics.total_failures == 2


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
