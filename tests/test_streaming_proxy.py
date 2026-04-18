"""
流式转发器单元测试
"""

import pytest
import asyncio
from unittest.mock import AsyncMock, MagicMock, patch
from typing import AsyncIterator

from src.router.streaming_proxy import (
    StreamingProxy,
    StreamingConfig,
    StreamForwarder,
    StreamContext,
    forward_stream_request,
    create_streaming_proxy,
)
from src.router.provider_manager import APIProvider, ProviderConfig, ProviderType
from src.router.request_transformer import TransformedRequest
from src.router.response_transformer import StreamChunk
from src.utils.exceptions import StreamingError, UpstreamAPIError


class TestStreamingConfig:
    """StreamingConfig 配置测试"""

    def test_default_config(self):
        """测试默认配置"""
        config = StreamingConfig()
        
        assert config.buffer_size == 4096
        assert config.chunk_timeout == 30.0
        assert config.connect_timeout == 10.0
        assert config.max_retries == 3
        assert config.retry_delay == 1.0
        assert config.enable_compression is True
        assert config.keep_alive is True

    def test_custom_config(self):
        """测试自定义配置"""
        config = StreamingConfig(
            buffer_size=8192,
            chunk_timeout=60.0,
            max_retries=5,
        )
        
        assert config.buffer_size == 8192
        assert config.chunk_timeout == 60.0
        assert config.max_retries == 5


class TestStreamContext:
    """StreamContext 上下文测试"""

    def test_create_context(self):
        """测试创建流式上下文"""
        provider_config = ProviderConfig(
            name="test_provider",
            provider_type=ProviderType.OPENAI,
            base_url="https://api.test.com",
            api_key="test_key",
        )
        provider = APIProvider(provider_config)
        
        request = TransformedRequest(
            url="https://api.test.com/v1/chat",
            method="POST",
            body={"model": "gpt-3.5"},
        )
        
        config = StreamingConfig()
        context = StreamContext(
            provider=provider,
            request=request,
            config=config,
        )
        
        assert context.provider.name == "test_provider"
        assert context.chunks_sent == 0
        assert context.bytes_sent == 0
        assert context.metadata == {}


class TestStreamingProxy:
    """StreamingProxy 代理测试"""

    @pytest.mark.asyncio
    async def test_context_manager(self):
        """测试异步上下文管理器"""
        async with create_streaming_proxy() as proxy:
            assert proxy._client is not None
        
        # 退出上下文后客户端应关闭
        assert proxy._client is None

    @pytest.mark.asyncio
    async def test_generate_stream_id(self):
        """测试生成流式 ID"""
        proxy = StreamingProxy()
        
        stream_id1 = proxy._generate_stream_id()
        stream_id2 = proxy._generate_stream_id()
        
        assert stream_id1.startswith("stream_")
        assert stream_id2.startswith("stream_")
        assert stream_id1 != stream_id2  # 应该是唯一的

    @pytest.mark.asyncio
    async def test_forward_stream_without_client(self):
        """测试在没有客户端时转发流式请求"""
        proxy = StreamingProxy()
        
        provider_config = ProviderConfig(
            name="test",
            provider_type=ProviderType.OPENAI,
            base_url="https://test.com",
            api_key="key",
        )
        provider = APIProvider(provider_config)
        
        request = TransformedRequest(
            url="https://test.com/api",
            body={},
        )
        
        # 应该抛出 StreamingError
        with pytest.raises(StreamingError, match="HTTP 客户端未初始化"):
            async for chunk in proxy.forward_stream(request, provider):
                pass

    @pytest.mark.asyncio
    async def test_get_stream_stats(self):
        """测试获取流式统计"""
        proxy = StreamingProxy()
        
        provider_config = ProviderConfig(
            name="test",
            provider_type=ProviderType.OPENAI,
            base_url="https://test.com",
            api_key="key",
        )
        provider = APIProvider(provider_config)
        
        request = TransformedRequest(url="https://test.com/api", body={})
        config = StreamingConfig()
        
        context = StreamContext(
            provider=provider,
            request=request,
            config=config,
            chunks_sent=10,
            bytes_sent=1024,
        )
        
        stats = proxy.get_stream_stats(context)
        
        assert stats["chunks_sent"] == 10
        assert stats["bytes_sent"] == 1024
        assert stats["provider"] == "test"


class TestStreamForwarder:
    """StreamForwarder 转发器测试"""

    def test_create_forwarder(self):
        """测试创建转发器"""
        forwarder = StreamForwarder()
        
        assert forwarder.config is not None
        assert forwarder._proxies == {}

    def test_forwarder_with_custom_config(self):
        """测试使用自定义配置创建转发器"""
        config = StreamingConfig(buffer_size=2048)
        forwarder = StreamForwarder(config)
        
        assert forwarder.config.buffer_size == 2048


class TestForwardStreamRequest:
    """forward_stream_request 便捷函数测试"""

    @pytest.mark.asyncio
    async def test_forward_stream_request_basic(self):
        """测试基本的流式请求转发"""
        provider_config = ProviderConfig(
            name="test",
            provider_type=ProviderType.OPENAI,
            base_url="https://test.com",
            api_key="key",
        )
        provider = APIProvider(provider_config)
        
        request = TransformedRequest(
            url="https://test.com/api",
            body={"stream": True},
        )
        
        config = StreamingConfig()
        
        # 由于没有真实的 HTTP 客户端，这里会抛出异常
        # 这个测试主要验证函数签名和基本的错误处理
        with pytest.raises(Exception):
            async for chunk in forward_stream_request(request, provider, config):
                pass


class TestStreamingErrorHandling:
    """流式错误处理测试"""

    @pytest.mark.asyncio
    async def test_upstream_api_error(self):
        """测试上游 API 错误"""
        from src.utils.exceptions import UpstreamAPIError
        
        error = UpstreamAPIError(
            "Service unavailable",
            status_code=503,
            provider_type=ProviderType.OPENAI,
        )
        
        assert error.status_code == 503
        assert error.provider_type == ProviderType.OPENAI
        assert "Service unavailable" in str(error)

    @pytest.mark.asyncio
    async def test_streaming_error(self):
        """测试流式错误"""
        error = StreamingError(
            "Connection lost",
            provider_type=ProviderType.ANTHROPIC,
        )
        
        assert error.provider_type == ProviderType.ANTHROPIC
        assert "Connection lost" in str(error)

    @pytest.mark.asyncio
    async def test_streaming_error_with_providers(self):
        """测试带提供者列表的流式错误"""
        error = StreamingError(
            "All providers failed",
            providers=["provider1", "provider2"],
        )
        
        assert error.providers == ["provider1", "provider2"]


class TestStreamingProxyIntegration:
    """StreamingProxy 集成测试"""

    @pytest.mark.asyncio
    async def test_mock_streaming(self):
        """测试模拟流式传输"""
        # 创建模拟的流式响应
        async def mock_stream_iterator():
            chunks = [
                b'data: {"id":"1","choices":[{"delta":{"content":"Hello"}}]}\n\n',
                b'data: {"id":"1","choices":[{"delta":{"content":" World"}}]}\n\n',
                b'data: [DONE]\n\n',
            ]
            for chunk in chunks:
                yield chunk
        
        # 验证 SSE 解析
        from src.utils.sse_parser import StreamingSSEParser
        
        parser = StreamingSSEParser()
        all_events = []
        
        async for chunk in mock_stream_iterator():
            events = parser.feed(chunk)
            all_events.extend(events)
        
        assert len(all_events) == 3
        assert all_events[2].is_done()

    @pytest.mark.asyncio
    async def test_provider_health_tracking(self):
        """测试提供者健康跟踪"""
        provider_config = ProviderConfig(
            name="test",
            provider_type=ProviderType.OPENAI,
            base_url="https://test.com",
            api_key="key",
        )
        provider = APIProvider(provider_config)
        
        # 初始状态应该是健康的
        assert provider.is_healthy is True
        
        # 标记为不健康
        provider.mark_unhealthy()
        assert provider.is_healthy is False
        
        # 恢复健康
        provider.mark_healthy()
        assert provider.is_healthy is True


class TestStreamChunk:
    """流式块测试（与转发器相关）"""

    def test_stream_chunk_to_sse(self):
        """测试流式块转换为 SSE 格式"""
        chunk = StreamChunk(
            id="chat-1",
            model="gpt-3.5",
            choices=[{
                "index": 0,
                "delta": {"content": "Hello"},
                "finish_reason": None,
            }],
        )
        
        sse = chunk.to_sse()
        assert sse.startswith("data: ")
        assert "Hello" in sse

    def test_stream_chunk_is_done(self):
        """测试流式块结束检测"""
        chunk = StreamChunk(
            id="chat-1",
            choices=[{
                "index": 0,
                "delta": {},
                "finish_reason": "stop",
            }],
        )
        
        assert chunk.is_done() is True
        
        # 未结束的块
        chunk2 = StreamChunk(
            id="chat-1",
            choices=[{
                "index": 0,
                "delta": {"content": "test"},
                "finish_reason": None,
            }],
        )
        
        assert chunk2.is_done() is False

    def test_stream_chunk_get_content(self):
        """测试获取流式块内容"""
        chunk = StreamChunk(
            id="chat-1",
            choices=[
                {
                    "index": 0,
                    "delta": {"content": "Hello"},
                },
                {
                    "index": 1,
                    "delta": {"content": " World"},
                },
            ],
        )
        
        content = chunk.get_content()
        assert content == "Hello World"

    def test_stream_chunk_with_usage(self):
        """测试带 usage 信息的流式块"""
        from src.router.response_transformer import UsageInfo
        
        chunk = StreamChunk(
            id="chat-1",
            usage=UsageInfo(
                prompt_tokens=10,
                completion_tokens=20,
                total_tokens=30,
            ),
        )
        
        result = chunk.to_dict()
        assert "usage" in result
        assert result["usage"]["total_tokens"] == 30


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
