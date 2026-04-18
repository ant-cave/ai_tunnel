"""
响应转换器流式功能单元测试
"""

import pytest
import json

from src.router.response_transformer import (
    StreamChunk,
    ResponseTransformerFactory,
    OpenAIResponseTransformer,
    AnthropicResponseTransformer,
    UsageInfo,
    ProviderType,
    APIProvider,
)
from src.router.provider_manager import ProviderConfig


class TestStreamChunkBasic:
    """StreamChunk 基础测试"""

    def test_create_stream_chunk(self):
        """测试创建流式块"""
        chunk = StreamChunk(
            id="chat-1",
            model="gpt-3.5",
            choices=[{
                "index": 0,
                "delta": {"content": "Hello"},
                "finish_reason": None,
            }],
        )
        
        assert chunk.id == "chat-1"
        assert chunk.model == "gpt-3.5"
        assert len(chunk.choices) == 1

    def test_stream_chunk_to_dict(self):
        """测试流式块转换为字典"""
        chunk = StreamChunk(
            id="chat-1",
            choices=[{
                "index": 0,
                "delta": {"content": "test"},
            }],
        )
        
        result = chunk.to_dict()
        
        assert result["id"] == "chat-1"
        assert result["object"] == "chat.completion.chunk"
        assert len(result["choices"]) == 1
        assert result["choices"][0]["delta"]["content"] == "test"

    def test_stream_chunk_to_sse(self):
        """测试流式块转换为 SSE 格式"""
        chunk = StreamChunk(
            id="chat-1",
            choices=[{
                "index": 0,
                "delta": {"content": "Hello"},
            }],
        )
        
        sse = chunk.to_sse()
        
        assert sse.startswith("data: ")
        assert sse.endswith("\n\n")
        assert "Hello" in sse

    def test_stream_chunk_with_usage(self):
        """测试带 usage 的流式块"""
        usage = UsageInfo(
            prompt_tokens=10,
            completion_tokens=20,
            total_tokens=30,
        )
        
        chunk = StreamChunk(
            id="chat-1",
            usage=usage,
        )
        
        result = chunk.to_dict()
        
        assert "usage" in result
        assert result["usage"]["prompt_tokens"] == 10
        assert result["usage"]["total_tokens"] == 30


class TestStreamChunkMethods:
    """StreamChunk 方法测试"""

    def test_is_done_with_finish_reason(self):
        """测试结束检测 - 有 finish_reason"""
        chunk = StreamChunk(
            id="chat-1",
            choices=[{
                "index": 0,
                "delta": {},
                "finish_reason": "stop",
            }],
        )
        
        assert chunk.is_done() is True

    def test_is_done_without_finish_reason(self):
        """测试结束检测 - 无 finish_reason"""
        chunk = StreamChunk(
            id="chat-1",
            choices=[{
                "index": 0,
                "delta": {"content": "test"},
                "finish_reason": None,
            }],
        )
        
        assert chunk.is_done() is False

    def test_get_content_single_choice(self):
        """测试获取内容 - 单个选择"""
        chunk = StreamChunk(
            id="chat-1",
            choices=[{
                "index": 0,
                "delta": {"content": "Hello World"},
            }],
        )
        
        content = chunk.get_content()
        assert content == "Hello World"

    def test_get_content_multiple_choices(self):
        """测试获取内容 - 多个选择"""
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

    def test_get_content_empty_delta(self):
        """测试获取内容 - 空 delta"""
        chunk = StreamChunk(
            id="chat-1",
            choices=[{
                "index": 0,
                "delta": {},
            }],
        )
        
        content = chunk.get_content()
        assert content == ""

    def test_get_role(self):
        """测试获取角色"""
        chunk = StreamChunk(
            id="chat-1",
            choices=[{
                "index": 0,
                "delta": {"role": "assistant", "content": "test"},
            }],
        )
        
        role = chunk.get_role()
        assert role == "assistant"

    def test_get_role_none(self):
        """测试获取角色 - 无角色信息"""
        chunk = StreamChunk(
            id="chat-1",
            choices=[{
                "index": 0,
                "delta": {"content": "test"},
            }],
        )
        
        role = chunk.get_role()
        assert role is None


class TestOpenAIResponseTransformer:
    """OpenAI 响应转换器流式测试"""

    def create_transformer(self):
        """创建 OpenAI 转换器"""
        return OpenAIResponseTransformer()

    def create_provider(self):
        """创建测试提供者"""
        config = ProviderConfig(
            name="test_openai",
            provider_type=ProviderType.OPENAI,
            base_url="https://api.test.com",
            api_key="test_key",
        )
        return APIProvider(config)

    def test_transform_openai_stream_chunk_basic(self):
        """测试转换 OpenAI 流式块 - 基础"""
        transformer = self.create_transformer()
        provider = self.create_provider()
        
        chunk_data = {
            "id": "chat-1",
            "model": "gpt-3.5",
            "choices": [{
                "index": 0,
                "delta": {"content": "Hello"},
                "finish_reason": None,
            }],
        }
        
        result = transformer.transform_stream_chunk(chunk_data, provider)
        
        assert result is not None
        assert result.id == "chat-1"
        assert result.model == "gpt-3.5"
        assert result.get_content() == "Hello"

    def test_transform_openai_stream_chunk_from_string(self):
        """测试转换 OpenAI 流式块 - 从字符串"""
        transformer = self.create_transformer()
        provider = self.create_provider()
        
        chunk_str = 'data: {"id":"chat-1","choices":[{"delta":{"content":"test"}}]}'
        
        result = transformer.transform_stream_chunk(chunk_str, provider)
        
        assert result is not None
        assert result.get_content() == "test"

    def test_transform_openai_stream_chunk_from_bytes(self):
        """测试转换 OpenAI 流式块 - 从字节"""
        transformer = self.create_transformer()
        provider = self.create_provider()
        
        chunk_bytes = b'data: {"id":"chat-1","choices":[{"delta":{"content":"test"}}]}'
        
        result = transformer.transform_stream_chunk(chunk_bytes, provider)
        
        assert result is not None
        assert result.get_content() == "test"

    def test_transform_openai_stream_done_marker(self):
        """测试转换 OpenAI 流式结束标记"""
        transformer = self.create_transformer()
        provider = self.create_provider()
        
        # [DONE] 标记
        result = transformer.transform_stream_chunk("[DONE]", provider)
        assert result is None
        
        # finish_reason 为 stop
        chunk_data = {
            "id": "chat-1",
            "choices": [{
                "index": 0,
                "delta": {},
                "finish_reason": "stop",
            }],
        }
        result = transformer.transform_stream_chunk(chunk_data, provider)
        
        # 应该返回结束块而不是 None
        assert result is not None
        assert result.is_done()

    def test_transform_openai_stream_with_usage(self):
        """测试转换 OpenAI 流式块 - 带 usage"""
        transformer = self.create_transformer()
        provider = self.create_provider()
        
        chunk_data = {
            "id": "chat-1",
            "choices": [{
                "index": 0,
                "delta": {"content": "test"},
            }],
            "usage": {
                "prompt_tokens": 10,
                "completion_tokens": 20,
                "total_tokens": 30,
            },
        }
        
        result = transformer.transform_stream_chunk(chunk_data, provider)
        
        assert result is not None
        assert result.usage is not None
        assert result.usage.total_tokens == 30

    def test_transform_openai_stream_with_tool_calls(self):
        """测试转换 OpenAI 流式块 - 带 tool_calls"""
        transformer = self.create_transformer()
        provider = self.create_provider()
        
        chunk_data = {
            "id": "chat-1",
            "choices": [{
                "index": 0,
                "delta": {
                    "role": "assistant",
                    "tool_calls": [{
                        "id": "call_1",
                        "function": {
                            "name": "get_weather",
                            "arguments": "{}",
                        },
                    }],
                },
            }],
        }
        
        result = transformer.transform_stream_chunk(chunk_data, provider)
        
        assert result is not None
        assert result.choices[0]["delta"]["tool_calls"] is not None

    def test_transform_openai_stream_error_handling(self):
        """测试转换 OpenAI 流式块 - 错误处理"""
        transformer = self.create_transformer()
        provider = self.create_provider()
        
        # 无效的 JSON
        result = transformer.transform_stream_chunk("invalid json", provider)
        assert result is None
        
        # 空的 chunk
        result = transformer.transform_stream_chunk({}, provider)
        assert result is None


class TestAnthropicResponseTransformer:
    """Anthropic 响应转换器流式测试"""

    def create_transformer(self):
        """创建 Anthropic 转换器"""
        return AnthropicResponseTransformer()

    def create_provider(self):
        """创建测试提供者"""
        config = ProviderConfig(
            name="test_anthropic",
            provider_type=ProviderType.ANTHROPIC,
            base_url="https://api.test.com",
            api_key="test_key",
        )
        return APIProvider(config)

    def test_transform_anthropic_content_block_delta(self):
        """测试转换 Anthropic content_block_delta 事件"""
        transformer = self.create_transformer()
        provider = self.create_provider()
        
        chunk_data = {
            "type": "content_block_delta",
            "message_id": "msg-1",
            "delta": {"text": "Hello"},
        }
        
        result = transformer.transform_stream_chunk(chunk_data, provider)
        
        assert result is not None
        assert result.get_content() == "Hello"

    def test_transform_anthropic_message_delta(self):
        """测试转换 Anthropic message_delta 事件"""
        transformer = self.create_transformer()
        provider = self.create_provider()
        
        chunk_data = {
            "type": "message_delta",
            "message_id": "msg-1",
            "delta": {"stop_reason": "end_turn"},
        }
        
        result = transformer.transform_stream_chunk(chunk_data, provider)
        
        assert result is not None
        assert result.is_done()
        assert result.choices[0]["finish_reason"] == "end_turn"

    def test_transform_anthropic_message_stop(self):
        """测试转换 Anthropic message_stop 事件"""
        transformer = self.create_transformer()
        provider = self.create_provider()
        
        # 从字符串
        result = transformer.transform_stream_chunk(
            "event: message_stop",
            provider
        )
        assert result is not None
        assert result.is_done()
        
        # 从字典
        chunk_data = {"type": "message_stop"}
        result = transformer.transform_stream_chunk(chunk_data, provider)
        assert result is None  # 字典格式的 message_stop 返回 None

    def test_transform_anthropic_content_block_start(self):
        """测试转换 Anthropic content_block_start 事件"""
        transformer = self.create_transformer()
        provider = self.create_provider()
        
        chunk_data = {
            "type": "content_block_start",
            "message_id": "msg-1",
            "content_block": {"type": "text"},
        }
        
        result = transformer.transform_stream_chunk(chunk_data, provider)
        
        assert result is not None
        assert result.get_role() == "assistant"

    def test_transform_anthropic_from_sse_string(self):
        """测试从 SSE 字符串转换 Anthropic 流式块"""
        transformer = self.create_transformer()
        provider = self.create_provider()
        
        chunk_str = 'data: {"type":"content_block_delta","delta":{"text":"test"}}'
        
        result = transformer.transform_stream_chunk(chunk_str, provider)
        
        assert result is not None
        assert result.get_content() == "test"


class TestResponseTransformerFactory:
    """响应转换器工厂流式测试"""

    def test_factory_get_openai_transformer(self):
        """测试工厂获取 OpenAI 转换器"""
        factory = ResponseTransformerFactory()
        
        transformer = factory.get_transformer(ProviderType.OPENAI)
        assert isinstance(transformer, OpenAIResponseTransformer)

    def test_factory_get_anthropic_transformer(self):
        """测试工厂获取 Anthropic 转换器"""
        factory = ResponseTransformerFactory()
        
        transformer = factory.get_transformer(ProviderType.ANTHROPIC)
        assert isinstance(transformer, AnthropicResponseTransformer)

    def test_factory_transform_stream_chunk_openai(self):
        """测试工厂转换流式块 - OpenAI"""
        factory = ResponseTransformerFactory()
        
        provider_config = ProviderConfig(
            name="test",
            provider_type=ProviderType.OPENAI,
            base_url="https://test.com",
            api_key="key",
        )
        provider = APIProvider(provider_config)
        
        chunk_data = {
            "id": "chat-1",
            "choices": [{"delta": {"content": "test"}}],
        }
        
        result = factory.transform_stream_chunk(chunk_data, provider)
        
        assert result is not None

    def test_factory_transform_stream_chunk_anthropic(self):
        """测试工厂转换流式块 - Anthropic"""
        factory = ResponseTransformerFactory()
        
        provider_config = ProviderConfig(
            name="test",
            provider_type=ProviderType.ANTHROPIC,
            base_url="https://test.com",
            api_key="key",
        )
        provider = APIProvider(provider_config)
        
        chunk_data = {
            "type": "content_block_delta",
            "delta": {"text": "test"},
        }
        
        result = factory.transform_stream_chunk(chunk_data, provider)
        
        assert result is not None


class TestStreamChunkIntegration:
    """流式块集成测试"""

    def test_complete_stream_sequence(self):
        """测试完整的流式序列"""
        chunks = [
            StreamChunk(
                id="chat-1",
                choices=[{
                    "index": 0,
                    "delta": {"role": "assistant"},
                }],
            ),
            StreamChunk(
                id="chat-1",
                choices=[{
                    "index": 0,
                    "delta": {"content": "Hello"},
                }],
            ),
            StreamChunk(
                id="chat-1",
                choices=[{
                    "index": 0,
                    "delta": {"content": " World"},
                }],
            ),
            StreamChunk(
                id="chat-1",
                choices=[{
                    "index": 0,
                    "delta": {},
                    "finish_reason": "stop",
                }],
            ),
        ]
        
        # 验证流式序列
        assert chunks[0].get_role() == "assistant"
        assert chunks[0].is_done() is False
        
        content = "".join(chunk.get_content() for chunk in chunks)
        assert content == "Hello World"
        
        assert chunks[-1].is_done() is True

    def test_stream_to_sse_format(self):
        """测试流式转换为 SSE 格式"""
        chunk = StreamChunk(
            id="chat-1",
            model="gpt-3.5",
            choices=[{
                "index": 0,
                "delta": {"content": "Hello"},
            }],
        )
        
        sse = chunk.to_sse()
        
        # 验证 SSE 格式
        assert sse.startswith("data: ")
        assert sse.endswith("\n\n")
        
        # 解析验证内容
        import json
        data = json.loads(sse[6:-2])  # 去掉 "data: " 和 "\n\n"
        assert data["choices"][0]["delta"]["content"] == "Hello"


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
