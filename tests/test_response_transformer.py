"""
响应转换器单元测试

测试 response_transformer.py 中的核心功能
"""

import unittest
import sys
import json
from pathlib import Path

# 添加 src 目录到路径
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from router.provider_manager import ProviderConfig, ProviderType, APIProvider
from router.response_transformer import (
    UnifiedResponse,
    StreamChunk,
    ErrorResponse,
    UsageInfo,
    ChatMessage,
    ChatChoice,
    ResponseStatus,
    ResponseTransformerFactory,
    OpenAIResponseTransformer,
    AnthropicResponseTransformer,
    transform_response,
    transform_error,
)


class TestUsageInfo(unittest.TestCase):
    """测试 UsageInfo 数据类"""

    def test_create_usage_info(self):
        """测试创建使用量信息"""
        usage = UsageInfo(
            prompt_tokens=100,
            completion_tokens=50,
            total_tokens=150,
        )

        self.assertEqual(usage.prompt_tokens, 100)
        self.assertEqual(usage.completion_tokens, 50)
        self.assertEqual(usage.total_tokens, 150)

    def test_usage_to_dict(self):
        """测试转换为字典"""
        usage = UsageInfo(prompt_tokens=100, completion_tokens=50, total_tokens=150)
        usage_dict = usage.to_dict()

        self.assertEqual(usage_dict["prompt_tokens"], 100)
        self.assertEqual(usage_dict["completion_tokens"], 50)
        self.assertEqual(usage_dict["total_tokens"], 150)


class TestChatMessage(unittest.TestCase):
    """测试 ChatMessage 数据类"""

    def test_create_message(self):
        """测试创建消息"""
        msg = ChatMessage(role="assistant", content="Hello")

        self.assertEqual(msg.role, "assistant")
        self.assertEqual(msg.content, "Hello")

    def test_message_to_dict(self):
        """测试转换为字典"""
        msg = ChatMessage(role="assistant", content="Hi there")
        msg_dict = msg.to_dict()

        self.assertEqual(msg_dict["role"], "assistant")
        self.assertEqual(msg_dict["content"], "Hi there")

    def test_message_with_function_call(self):
        """测试带函数调用的消息"""
        msg = ChatMessage(
            role="assistant",
            content=None,
            function_call={"name": "get_weather", "arguments": '{"city": "Beijing"}'},
        )
        msg_dict = msg.to_dict()

        self.assertEqual(msg_dict["role"], "assistant")
        self.assertIsNotNone(msg_dict["function_call"])


class TestChatChoice(unittest.TestCase):
    """测试 ChatChoice 数据类"""

    def test_create_choice(self):
        """测试创建选择"""
        message = ChatMessage(role="assistant", content="Hello")
        choice = ChatChoice(index=0, message=message, finish_reason="stop")

        self.assertEqual(choice.index, 0)
        self.assertEqual(choice.message.role, "assistant")
        self.assertEqual(choice.finish_reason, "stop")

    def test_choice_to_dict(self):
        """测试转换为字典"""
        message = ChatMessage(role="assistant", content="Hi")
        choice = ChatChoice(index=0, message=message)
        choice_dict = choice.to_dict()

        self.assertEqual(choice_dict["index"], 0)
        self.assertEqual(choice_dict["message"]["role"], "assistant")


class TestUnifiedResponse(unittest.TestCase):
    """测试 UnifiedResponse 数据类"""

    def test_create_response(self):
        """测试创建响应"""
        message = ChatMessage(role="assistant", content="Hello")
        choice = ChatChoice(index=0, message=message)

        response = UnifiedResponse(
            id="resp-123",
            model="gpt-3.5",
            choices=[choice],
        )

        self.assertEqual(response.id, "resp-123")
        self.assertEqual(response.model, "gpt-3.5")
        self.assertEqual(len(response.choices), 1)
        self.assertEqual(response.status, ResponseStatus.SUCCESS)

    def test_response_to_dict(self):
        """测试转换为字典"""
        message = ChatMessage(role="assistant", content="Hi")
        choice = ChatChoice(index=0, message=message)
        usage = UsageInfo(prompt_tokens=10, completion_tokens=5, total_tokens=15)

        response = UnifiedResponse(
            id="resp-123",
            model="gpt-3.5",
            choices=[choice],
            usage=usage,
        )

        response_dict = response.to_dict()

        self.assertEqual(response_dict["id"], "resp-123")
        self.assertEqual(response_dict["model"], "gpt-3.5")
        self.assertEqual(len(response_dict["choices"]), 1)
        self.assertEqual(response_dict["usage"]["total_tokens"], 15)

    def test_response_to_json(self):
        """测试转换为 JSON"""
        message = ChatMessage(role="assistant", content="Hi")
        choice = ChatChoice(index=0, message=message)

        response = UnifiedResponse(id="resp-123", model="gpt-3.5", choices=[choice])
        json_str = response.to_json()

        parsed = json.loads(json_str)
        self.assertEqual(parsed["id"], "resp-123")

    def test_error_response(self):
        """测试错误响应"""
        response = UnifiedResponse(
            id="",
            model="",
            status=ResponseStatus.ERROR,
            error="Something went wrong",
            error_code="api_error",
        )

        response_dict = response.to_dict()
        self.assertIn("error", response_dict)
        self.assertEqual(response_dict["error"]["message"], "Something went wrong")


class TestStreamChunk(unittest.TestCase):
    """测试 StreamChunk 数据类"""

    def test_create_chunk(self):
        """测试创建流式块"""
        chunk = StreamChunk(
            id="chunk-123",
            model="gpt-3.5",
            choices=[{"index": 0, "delta": {"content": "Hello"}}],
        )

        self.assertEqual(chunk.id, "chunk-123")
        self.assertEqual(chunk.model, "gpt-3.5")

    def test_chunk_to_dict(self):
        """测试转换为字典"""
        chunk = StreamChunk(
            id="chunk-123",
            model="gpt-3.5",
            choices=[{"index": 0, "delta": {"content": "Hi"}}],
        )

        chunk_dict = chunk.to_dict()
        self.assertEqual(chunk_dict["id"], "chunk-123")
        self.assertEqual(chunk_dict["choices"][0]["delta"]["content"], "Hi")

    def test_chunk_to_sse(self):
        """测试转换为 SSE 格式"""
        chunk = StreamChunk(
            id="chunk-123",
            model="gpt-3.5",
            choices=[{"index": 0, "delta": {"content": "Hi"}}],
        )

        sse_str = chunk.to_sse()
        self.assertTrue(sse_str.startswith("data: "))
        self.assertIn("chunk-123", sse_str)


class TestErrorResponse(unittest.TestCase):
    """测试 ErrorResponse 数据类"""

    def test_create_error_response(self):
        """测试创建错误响应"""
        error = ErrorResponse(
            error="API timeout",
            error_code="timeout",
            status_code=504,
        )

        self.assertEqual(error.error, "API timeout")
        self.assertEqual(error.error_code, "timeout")
        self.assertEqual(error.status_code, 504)

    def test_error_to_dict(self):
        """测试转换为字典"""
        error = ErrorResponse(
            error="Invalid request",
            error_code="bad_request",
            status_code=400,
        )

        error_dict = error.to_dict()
        self.assertEqual(error_dict["error"]["message"], "Invalid request")
        self.assertEqual(error_dict["error"]["code"], "bad_request")

    def test_error_to_json(self):
        """测试转换为 JSON"""
        error = ErrorResponse(error="Error", error_code="error")
        json_str = error.to_json()

        parsed = json.loads(json_str)
        self.assertIn("error", parsed)


class TestOpenAIResponseTransformer(unittest.TestCase):
    """测试 OpenAI 响应转换器"""

    def setUp(self):
        """设置测试固件"""
        self.config = ProviderConfig(
            name="openai",
            provider_type=ProviderType.OPENAI,
            base_url="https://api.openai.com",
            api_key="key",
        )
        self.provider = APIProvider(self.config)
        self.transformer = OpenAIResponseTransformer()

    def test_supports_provider(self):
        """测试支持的提供者类型"""
        self.assertTrue(self.transformer.supports_provider(ProviderType.OPENAI))
        self.assertTrue(self.transformer.supports_provider(ProviderType.AZURE))

    def test_transform_basic_response(self):
        """测试转换基本响应"""
        raw_response = {
            "id": "resp-123",
            "model": "gpt-3.5",
            "choices": [
                {
                    "index": 0,
                    "message": {"role": "assistant", "content": "Hello"},
                    "finish_reason": "stop",
                }
            ],
            "usage": {
                "prompt_tokens": 10,
                "completion_tokens": 5,
                "total_tokens": 15,
            },
        }

        response = self.transformer.transform(raw_response, self.provider)

        self.assertEqual(response.id, "resp-123")
        self.assertEqual(response.model, "gpt-3.5")
        self.assertEqual(len(response.choices), 1)
        self.assertEqual(response.choices[0].message.content, "Hello")
        self.assertEqual(response.usage.total_tokens, 15)

    def test_transform_stream_chunk(self):
        """测试转换流式块"""
        chunk_data = {
            "id": "chunk-123",
            "model": "gpt-3.5",
            "choices": [
                {
                    "index": 0,
                    "delta": {"content": "Hello"},
                    "finish_reason": None,
                }
            ],
        }

        chunk = self.transformer.transform_stream_chunk(chunk_data, self.provider)

        self.assertIsNotNone(chunk)
        self.assertEqual(chunk.id, "chunk-123")
        self.assertEqual(chunk.choices[0]["delta"]["content"], "Hello")

    def test_transform_done_chunk(self):
        """测试转换结束块"""
        # [DONE] 标记应该返回 None
        result = self.transformer.transform_stream_chunk("[DONE]", self.provider)
        self.assertIsNone(result)

    def test_transform_error(self):
        """测试转换错误"""
        error = Exception("API error")
        error_response = self.transformer.transform_error(error, 500, self.provider)

        self.assertEqual(error_response.error, "API error")
        self.assertEqual(error_response.status_code, 500)


class TestAnthropicResponseTransformer(unittest.TestCase):
    """测试 Anthropic 响应转换器"""

    def setUp(self):
        """设置测试固件"""
        self.config = ProviderConfig(
            name="anthropic",
            provider_type=ProviderType.ANTHROPIC,
            base_url="https://api.anthropic.com",
            api_key="key",
        )
        self.provider = APIProvider(self.config)
        self.transformer = AnthropicResponseTransformer()

    def test_supports_provider(self):
        """测试支持的提供者类型"""
        self.assertTrue(self.transformer.supports_provider(ProviderType.ANTHROPIC))
        self.assertFalse(self.transformer.supports_provider(ProviderType.OPENAI))

    def test_transform_basic_response(self):
        """测试转换基本响应"""
        raw_response = {
            "id": "msg-123",
            "model": "claude-3",
            "content": [{"type": "text", "text": "Hello"}],
            "usage": {"input_tokens": 10, "output_tokens": 5},
            "stop_reason": "end_turn",
        }

        response = self.transformer.transform(raw_response, self.provider)

        self.assertEqual(response.id, "msg-123")
        self.assertEqual(response.model, "claude-3")
        self.assertEqual(response.choices[0].message.content, "Hello")
        self.assertEqual(response.choices[0].finish_reason, "end_turn")
        self.assertEqual(response.usage.total_tokens, 15)

    def test_transform_stream_chunk(self):
        """测试转换流式块"""
        chunk_data = {
            "type": "content_block_delta",
            "message_id": "msg-123",
            "model": "claude-3",
            "delta": {"text": "Hello"},
        }

        chunk = self.transformer.transform_stream_chunk(chunk_data, self.provider)

        self.assertIsNotNone(chunk)
        self.assertEqual(chunk.choices[0]["delta"]["content"], "Hello")


class TestResponseTransformerFactory(unittest.TestCase):
    """测试响应转换器工厂"""

    def setUp(self):
        """设置测试固件"""
        self.factory = ResponseTransformerFactory()

    def test_get_openai_transformer(self):
        """测试获取 OpenAI 转换器"""
        transformer = self.factory.get_transformer(ProviderType.OPENAI)
        self.assertIsInstance(transformer, OpenAIResponseTransformer)

    def test_get_anthropic_transformer(self):
        """测试获取 Anthropic 转换器"""
        transformer = self.factory.get_transformer(ProviderType.ANTHROPIC)
        self.assertIsInstance(transformer, AnthropicResponseTransformer)

    def test_transform_response(self):
        """测试转换响应"""
        config = ProviderConfig(
            name="openai",
            provider_type=ProviderType.OPENAI,
            base_url="https://api.openai.com",
            api_key="key",
        )
        provider = APIProvider(config)

        raw_response = {
            "id": "resp-123",
            "model": "gpt-3.5",
            "choices": [
                {
                    "index": 0,
                    "message": {"role": "assistant", "content": "Hi"},
                }
            ],
        }

        response = self.factory.transform(raw_response, provider)

        self.assertEqual(response.id, "resp-123")
        self.assertEqual(response.choices[0].message.content, "Hi")


class TestTransformErrorFunction(unittest.TestCase):
    """测试便捷函数 transform_error"""

    def test_transform_error_convenience_function(self):
        """测试便捷错误转换函数"""
        error = Exception("Test error")
        error_response = transform_error(error, 500)

        self.assertEqual(error_response.error, "Test error")
        self.assertEqual(error_response.status_code, 500)


if __name__ == "__main__":
    unittest.main()
