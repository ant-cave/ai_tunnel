"""
请求转换器单元测试

测试 request_transformer.py 中的核心功能
"""

import unittest
import sys
from pathlib import Path

# 添加 src 目录到路径
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from router.provider_manager import ProviderConfig, ProviderType, APIProvider
from router.request_transformer import (
    ClientRequest,
    RequestTransformerFactory,
    OpenAIRequestTransformer,
    AnthropicRequestTransformer,
    RawRequestTransformer,
    transform_request,
)


class TestClientRequest(unittest.TestCase):
    """测试 ClientRequest 数据类"""

    def test_create_basic_request(self):
        """测试创建基本请求"""
        request = ClientRequest(
            model="gpt-3.5",
            messages=[{"role": "user", "content": "Hello"}],
        )

        self.assertEqual(request.model, "gpt-3.5")
        self.assertEqual(len(request.messages), 1)
        self.assertFalse(request.stream)
        self.assertIsNone(request.temperature)

    def test_create_full_request(self):
        """测试创建完整请求"""
        request = ClientRequest(
            model="gpt-4",
            messages=[
                {"role": "system", "content": "You are helpful"},
                {"role": "user", "content": "Hi"},
            ],
            temperature=0.7,
            max_tokens=1000,
            stream=True,
            top_p=0.9,
            stop=["\n", "."],
            extra_body={"user_id": "123"},
        )

        self.assertEqual(request.model, "gpt-4")
        self.assertEqual(len(request.messages), 2)
        self.assertEqual(request.temperature, 0.7)
        self.assertEqual(request.max_tokens, 1000)
        self.assertTrue(request.stream)
        self.assertEqual(request.top_p, 0.9)
        self.assertEqual(request.stop, ["\n", "."])
        self.assertEqual(request.extra_body["user_id"], "123")


class TestOpenAIRequestTransformer(unittest.TestCase):
    """测试 OpenAI 请求转换器"""

    def setUp(self):
        """设置测试固件"""
        self.config = ProviderConfig(
            name="openai",
            provider_type=ProviderType.OPENAI,
            base_url="https://api.openai.com",
            api_key="sk-test123",
            models=["gpt-3.5", "gpt-4"],
        )
        self.provider = APIProvider(self.config)
        self.transformer = OpenAIRequestTransformer()

    def test_supports_provider(self):
        """测试支持的提供者类型"""
        self.assertTrue(self.transformer.supports_provider(ProviderType.OPENAI))
        self.assertTrue(self.transformer.supports_provider(ProviderType.AZURE))
        self.assertFalse(self.transformer.supports_provider(ProviderType.ANTHROPIC))

    def test_transform_basic_request(self):
        """测试转换基本请求"""
        request = ClientRequest(
            model="gpt-3.5",
            messages=[{"role": "user", "content": "Hello"}],
        )

        transformed = self.transformer.transform(request, self.provider)

        self.assertEqual(transformed.method, "POST")
        self.assertEqual(
            transformed.url, "https://api.openai.com/v1/chat/completions"
        )
        self.assertIn("Authorization", transformed.headers)
        self.assertEqual(
            transformed.headers["Authorization"], "Bearer sk-test123"
        )
        self.assertEqual(transformed.body["model"], "gpt-3.5")
        self.assertEqual(len(transformed.body["messages"]), 1)

    def test_transform_with_options(self):
        """测试转换带选项的请求"""
        request = ClientRequest(
            model="gpt-4",
            messages=[{"role": "user", "content": "Hi"}],
            temperature=0.8,
            max_tokens=500,
            stream=True,
            top_p=0.95,
        )

        transformed = self.transformer.transform(request, self.provider)

        self.assertEqual(transformed.body["temperature"], 0.8)
        self.assertEqual(transformed.body["max_tokens"], 500)
        self.assertTrue(transformed.body["stream"])
        self.assertEqual(transformed.body["top_p"], 0.95)

    def test_transform_with_extra_body(self):
        """测试转换带额外参数的请求"""
        request = ClientRequest(
            model="gpt-3.5",
            messages=[{"role": "user", "content": "Hi"}],
            extra_body={"custom_param": "value"},
        )

        transformed = self.transformer.transform(request, self.provider)

        self.assertEqual(transformed.body["custom_param"], "value")


class TestAzureRequestTransformer(unittest.TestCase):
    """测试 Azure 请求转换器（使用 OpenAI 转换器）"""

    def setUp(self):
        """设置测试固件"""
        self.config = ProviderConfig(
            name="azure",
            provider_type=ProviderType.AZURE,
            base_url="https://my-resource.openai.azure.com",
            api_key="azure-key-123",
            models=["gpt-35-turbo"],
            extra_config={"api_version": "2023-05-15"},
        )
        self.provider = APIProvider(self.config)
        self.transformer = OpenAIRequestTransformer()

    def test_transform_azure_request(self):
        """测试转换 Azure 请求"""
        request = ClientRequest(
            model="gpt-35-turbo",
            messages=[{"role": "user", "content": "Hello"}],
        )

        transformed = self.transformer.transform(request, self.provider)

        # Azure 使用不同的 URL 格式
        expected_url = (
            "https://my-resource.openai.azure.com/openai/deployments/"
            "gpt-35-turbo/chat/completions?api-version=2023-05-15"
        )
        self.assertEqual(transformed.url, expected_url)

        # Azure 使用 api-key 头
        self.assertEqual(
            transformed.headers["api-key"], "azure-key-123"
        )


class TestAnthropicRequestTransformer(unittest.TestCase):
    """测试 Anthropic 请求转换器"""

    def setUp(self):
        """设置测试固件"""
        self.config = ProviderConfig(
            name="anthropic",
            provider_type=ProviderType.ANTHROPIC,
            base_url="https://api.anthropic.com",
            api_key="sk-ant-123",
            models=["claude-3"],
        )
        self.provider = APIProvider(self.config)
        self.transformer = AnthropicRequestTransformer()

    def test_supports_provider(self):
        """测试支持的提供者类型"""
        self.assertTrue(self.transformer.supports_provider(ProviderType.ANTHROPIC))
        self.assertFalse(self.transformer.supports_provider(ProviderType.OPENAI))

    def test_transform_basic_request(self):
        """测试转换基本请求"""
        request = ClientRequest(
            model="claude-3",
            messages=[{"role": "user", "content": "Hello"}],
        )

        transformed = self.transformer.transform(request, self.provider)

        self.assertEqual(
            transformed.url, "https://api.anthropic.com/v1/messages"
        )
        self.assertEqual(
            transformed.headers["x-api-key"], "sk-ant-123"
        )
        self.assertEqual(transformed.body["model"], "claude-3")
        self.assertEqual(len(transformed.body["messages"]), 1)

    def test_transform_system_message(self):
        """测试转换包含 system 消息的请求"""
        request = ClientRequest(
            model="claude-3",
            messages=[
                {"role": "system", "content": "You are helpful"},
                {"role": "user", "content": "Hi"},
            ],
        )

        transformed = self.transformer.transform(request, self.provider)

        # System 消息应该被过滤掉
        messages = transformed.body["messages"]
        self.assertEqual(len(messages), 1)
        self.assertEqual(messages[0]["role"], "user")

    def test_transform_with_max_tokens(self):
        """测试转换带 max_tokens 的请求"""
        request = ClientRequest(
            model="claude-3",
            messages=[{"role": "user", "content": "Hi"}],
            max_tokens=2048,
        )

        transformed = self.transformer.transform(request, self.provider)

        self.assertEqual(transformed.body["max_tokens"], 2048)

    def test_transform_default_max_tokens(self):
        """测试默认 max_tokens"""
        request = ClientRequest(
            model="claude-3",
            messages=[{"role": "user", "content": "Hi"}],
        )

        transformed = self.transformer.transform(request, self.provider)

        # Anthropic 需要 max_tokens，默认值应该是 1024
        self.assertEqual(transformed.body["max_tokens"], 1024)


class TestRawRequestTransformer(unittest.TestCase):
    """测试原始请求转换器"""

    def setUp(self):
        """设置测试固件"""
        self.config = ProviderConfig(
            name="custom",
            provider_type=ProviderType.CUSTOM,
            base_url="https://custom.api.com",
            api_key="custom-key",
        )
        self.provider = APIProvider(self.config)
        self.transformer = RawRequestTransformer()

    def test_supports_provider(self):
        """测试支持的提供者类型"""
        self.assertTrue(self.transformer.supports_provider(ProviderType.CUSTOM))
        self.assertFalse(self.transformer.supports_provider(ProviderType.OPENAI))

    def test_transform_request(self):
        """测试转换原始请求"""
        request = ClientRequest(
            model="custom-model",
            messages=[{"role": "user", "content": "Hello"}],
            extra_body={"custom": "data"},
        )

        transformed = self.transformer.transform(request, self.provider)

        self.assertEqual(transformed.url, "https://custom.api.com")
        self.assertEqual(transformed.body["model"], "custom-model")
        self.assertEqual(transformed.body["custom"], "data")


class TestRequestTransformerFactory(unittest.TestCase):
    """测试请求转换器工厂"""

    def setUp(self):
        """设置测试固件"""
        self.factory = RequestTransformerFactory()

    def test_get_openai_transformer(self):
        """测试获取 OpenAI 转换器"""
        transformer = self.factory.get_transformer(ProviderType.OPENAI)
        self.assertIsInstance(transformer, OpenAIRequestTransformer)

    def test_get_anthropic_transformer(self):
        """测试获取 Anthropic 转换器"""
        transformer = self.factory.get_transformer(ProviderType.ANTHROPIC)
        self.assertIsInstance(transformer, AnthropicRequestTransformer)

    def test_get_unknown_transformer(self):
        """测试获取未知转换器（应该返回 RawRequestTransformer）"""
        transformer = self.factory.get_transformer(ProviderType.CUSTOM)
        self.assertIsInstance(transformer, RawRequestTransformer)

    def test_transform_with_provider(self):
        """测试使用提供者转换请求"""
        config = ProviderConfig(
            name="openai",
            provider_type=ProviderType.OPENAI,
            base_url="https://api.openai.com",
            api_key="key",
        )
        provider = APIProvider(config)
        request = ClientRequest(
            model="gpt-3.5",
            messages=[{"role": "user", "content": "Hi"}],
        )

        transformed = self.factory.transform(request, provider)

        self.assertIsNotNone(transformed)
        self.assertEqual(transformed.body["model"], "gpt-3.5")


class TestTransformRequestFunction(unittest.TestCase):
    """测试便捷函数 transform_request"""

    def test_transform_request_convenience_function(self):
        """测试便捷转换函数"""
        config = ProviderConfig(
            name="openai",
            provider_type=ProviderType.OPENAI,
            base_url="https://api.openai.com",
            api_key="key",
        )
        provider = APIProvider(config)
        request = ClientRequest(
            model="gpt-3.5",
            messages=[{"role": "user", "content": "Hello"}],
        )

        transformed = transform_request(request, provider)

        self.assertIsNotNone(transformed)
        self.assertIn("Bearer key", transformed.headers["Authorization"])


if __name__ == "__main__":
    unittest.main()
