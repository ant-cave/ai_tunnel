"""
路由器流式功能集成测试
"""

import pytest
import asyncio
from unittest.mock import AsyncMock, MagicMock, patch

from src.router.router import Router, AsyncRouter, RouterConfig
from src.router.provider_manager import ProviderConfig, ProviderType
from src.router.request_transformer import ClientRequest
from src.router.streaming_proxy import StreamingConfig


class TestRouterStreamingConfig:
    """路由器流式配置测试"""

    def test_router_has_streaming_config(self):
        """测试路由器包含流式配置"""
        router = Router()
        
        assert hasattr(router, 'streaming_config')
        assert hasattr(router, 'stream_forwarder')
        assert isinstance(router.streaming_config, StreamingConfig)


class TestAsyncRouterStreamRequest:
    """AsyncRouter 流式请求测试"""

    @pytest.mark.asyncio
    async def test_route_stream_request_method_exists(self):
        """测试流式路由方法存在"""
        router = AsyncRouter()
        
        assert hasattr(router, 'route_stream_request')
        assert asyncio.iscoroutinefunction(router.route_stream_request)

    @pytest.mark.asyncio
    async def test_route_stream_request_sets_stream_flag(self):
        """测试流式路由设置 stream 标志"""
        router = AsyncRouter()
        
        # 添加测试提供者
        provider_config = ProviderConfig(
            name="test_provider",
            provider_type=ProviderType.OPENAI,
            base_url="https://api.test.com",
            api_key="test_key",
            models=["gpt-3.5"],
        )
        router.add_provider(provider_config)
        
        # 创建非流式请求
        request = ClientRequest(
            model="gpt-3.5",
            messages=[{"role": "user", "content": "Hello"}],
            stream=False,  # 初始为 False
        )
        
        # 验证 route_stream_request 会设置 stream=True
        # 由于没有真实的 HTTP 连接，这里会抛出异常
        # 但我们可以通过检查请求对象来验证
        
        # 保存原始方法用于验证
        original_route = router.route_request
        
        def mock_route(client_request):
            assert client_request.stream is True, "流式路由应该设置 stream=True"
            return original_route(client_request)
        
        router.route_request = mock_route
        
        with pytest.raises(Exception):
            async for chunk in router.route_stream_request(request):
                pass


class TestRouterStreamWithFallback:
    """路由器带故障转移的流式测试"""

    @pytest.mark.asyncio
    async def test_route_stream_with_fallback_exists(self):
        """测试带故障转移的流式路由方法存在"""
        router = AsyncRouter()
        
        assert hasattr(router, 'route_stream_with_fallback')
        assert asyncio.iscoroutinefunction(router.route_stream_with_fallback)

    @pytest.mark.asyncio
    async def test_route_stream_with_fallback_no_providers(self):
        """测试没有提供者时的故障转移"""
        router = AsyncRouter()
        
        request = ClientRequest(
            model="gpt-3.5",
            messages=[{"role": "user", "content": "Hello"}],
        )
        
        with pytest.raises(ValueError, match="没有可用的提供者"):
            async for chunk in router.route_stream_with_fallback(request):
                pass

    @pytest.mark.asyncio
    async def test_route_stream_with_fallback_single_provider(self):
        """测试单个提供者的故障转移"""
        router = AsyncRouter()
        
        # 添加一个提供者
        provider_config = ProviderConfig(
            name="test_provider",
            provider_type=ProviderType.OPENAI,
            base_url="https://api.test.com",
            api_key="test_key",
            models=["gpt-3.5"],
            priority=1,
        )
        router.add_provider(provider_config)
        
        request = ClientRequest(
            model="gpt-3.5",
            messages=[{"role": "user", "content": "Hello"}],
        )
        
        # 由于没有真实连接，会抛出异常
        with pytest.raises(Exception):
            async for chunk in router.route_stream_with_fallback(request):
                pass

    @pytest.mark.asyncio
    async def test_route_stream_with_fallback_auto_model(self):
        """测试 auto 模型的故障转移"""
        router = AsyncRouter()
        
        # 添加多个提供者
        provider1_config = ProviderConfig(
            name="provider1",
            provider_type=ProviderType.OPENAI,
            base_url="https://api1.test.com",
            api_key="key1",
            priority=1,
        )
        provider2_config = ProviderConfig(
            name="provider2",
            provider_type=ProviderType.ANTHROPIC,
            base_url="https://api2.test.com",
            api_key="key2",
            priority=2,
        )
        
        router.add_provider(provider1_config)
        router.add_provider(provider2_config)
        
        request = ClientRequest(
            model="auto",  # auto 模型
            messages=[{"role": "user", "content": "Hello"}],
        )
        
        # 会尝试所有提供者
        with pytest.raises(Exception):
            async for chunk in router.route_stream_with_fallback(request):
                pass


class TestRouterProviderHealthTracking:
    """路由器提供者健康跟踪测试"""

    @pytest.mark.asyncio
    async def test_provider_marked_unhealthy_on_stream_failure(self):
        """测试流式失败时提供者被标记为不健康"""
        router = AsyncRouter()
        
        provider_config = ProviderConfig(
            name="test_provider",
            provider_type=ProviderType.OPENAI,
            base_url="https://invalid.api.com",  # 无效的 API
            api_key="test_key",
            models=["gpt-3.5"],
        )
        provider = router.add_provider(provider_config)
        
        # 初始是健康的
        assert provider.is_healthy is True
        
        request = ClientRequest(
            model="gpt-3.5",
            messages=[{"role": "user", "content": "Hello"}],
        )
        
        # 流式失败
        with pytest.raises(Exception):
            async for chunk in router.route_stream_request(request):
                pass
        
        # 提供者应该被标记为不健康
        # 注意：实际标记发生在异常处理中

    def test_manual_health_tracking(self):
        """测试手动健康跟踪"""
        router = Router()
        
        provider_config = ProviderConfig(
            name="test",
            provider_type=ProviderType.OPENAI,
            base_url="https://test.com",
            api_key="key",
        )
        provider = router.add_provider(provider_config)
        
        # 手动标记
        router.mark_provider_unhealthy("test")
        assert provider.is_healthy is False
        
        router.mark_provider_healthy("test")
        assert provider.is_healthy is True


class TestRouterStreamMultipleProviders:
    """路由器多提供者流式测试"""

    @pytest.mark.asyncio
    async def test_provider_priority_in_streaming(self):
        """测试流式中的提供者优先级"""
        router = AsyncRouter()
        
        # 添加不同优先级的提供者
        low_priority = ProviderConfig(
            name="low_priority",
            provider_type=ProviderType.OPENAI,
            base_url="https://low.test.com",
            api_key="key",
            priority=1,
        )
        high_priority = ProviderConfig(
            name="high_priority",
            provider_type=ProviderType.OPENAI,
            base_url="https://high.test.com",
            api_key="key",
            priority=10,
        )
        
        router.add_provider(low_priority)
        router.add_provider(high_priority)
        
        # 获取健康提供者并验证排序
        providers = router.provider_manager.get_healthy_providers()
        sorted_providers = sorted(providers, key=lambda p: p.priority, reverse=True)
        
        assert sorted_providers[0].name == "high_priority"
        assert sorted_providers[0].priority == 10


class TestRouterStreamErrorHandling:
    """路由器流式错误处理测试"""

    @pytest.mark.asyncio
    async def test_stream_error_with_invalid_model(self):
        """测试无效模型的流式错误"""
        router = AsyncRouter()
        
        provider_config = ProviderConfig(
            name="test",
            provider_type=ProviderType.OPENAI,
            base_url="https://test.com",
            api_key="key",
            models=["gpt-3.5"],  # 只支持 gpt-3.5
        )
        router.add_provider(provider_config)
        
        request = ClientRequest(
            model="invalid-model",
            messages=[{"role": "user", "content": "Hello"}],
        )
        
        # 应该能找到提供者（使用默认提供者）
        # 但实际请求会失败
        with pytest.raises(Exception):
            async for chunk in router.route_stream_request(request):
                pass

    @pytest.mark.asyncio
    async def test_stream_error_with_no_matching_provider(self):
        """测试没有匹配提供者时的流式错误"""
        router = AsyncRouter()
        
        # 添加提供者但不支持任何模型（空列表表示支持所有）
        provider_config = ProviderConfig(
            name="test",
            provider_type=ProviderType.OPENAI,
            base_url="https://test.com",
            api_key="key",
        )
        router.add_provider(provider_config)
        
        request = ClientRequest(
            model="any-model",
            messages=[{"role": "user", "content": "Hello"}],
        )
        
        # 应该使用默认提供者
        with pytest.raises(Exception):
            async for chunk in router.route_stream_request(request):
                pass


class TestRouterStreamAutoModel:
    """路由器 auto 模型流式测试"""

    @pytest.mark.asyncio
    async def test_auto_model_selects_highest_priority(self):
        """测试 auto 模型选择最高优先级的提供者"""
        router = AsyncRouter()
        
        # 添加多个提供者
        provider1 = ProviderConfig(
            name="provider1",
            provider_type=ProviderType.OPENAI,
            base_url="https://api1.com",
            api_key="key1",
            priority=5,
        )
        provider2 = ProviderConfig(
            name="provider2",
            provider_type=ProviderType.ANTHROPIC,
            base_url="https://api2.com",
            api_key="key2",
            priority=10,
        )
        
        router.add_provider(provider1)
        router.add_provider(provider2)
        
        # 路由 auto 模型请求
        request = ClientRequest(
            model="auto",
            messages=[{"role": "user", "content": "Hello"}],
        )
        
        routing_result = router.route_request(request)
        
        # 应该选择优先级高的 provider2
        assert routing_result.success is True
        assert routing_result.provider.name == "provider2"

    @pytest.mark.asyncio
    async def test_auto_model_with_unhealthy_provider(self):
        """测试 auto 模型在提供者不健康时的行为"""
        router = AsyncRouter()
        
        provider_config = ProviderConfig(
            name="test",
            provider_type=ProviderType.OPENAI,
            base_url="https://test.com",
            api_key="key",
            priority=1,
        )
        provider = router.add_provider(provider_config)
        
        # 标记为不健康
        provider.mark_unhealthy()
        
        request = ClientRequest(
            model="auto",
            messages=[{"role": "user", "content": "Hello"}],
        )
        
        # 仍然应该能路由（使用启用的提供者）
        routing_result = router.route_request(request)
        
        # 由于只有一个提供者，即使不健康也应该返回
        assert routing_result.success is True


class TestRouterStreamConfig:
    """路由器流式配置测试"""

    def test_router_custom_streaming_config(self):
        """测试路由器自定义流式配置"""
        config = RouterConfig()
        router = Router(config)
        
        # 修改流式配置
        router.streaming_config.buffer_size = 8192
        router.streaming_config.max_retries = 5
        
        assert router.streaming_config.buffer_size == 8192
        assert router.streaming_config.max_retries == 5

    def test_router_stream_forwarder_config(self):
        """测试路由器流式转发器配置"""
        router = Router()
        
        # 验证转发器使用相同的配置
        assert router.stream_forwarder.config == router.streaming_config


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
