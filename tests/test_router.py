"""
路由器单元测试

测试 router.py 中的核心功能
"""

import unittest
import sys
from pathlib import Path

# 添加 src 目录到路径
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from router.provider_manager import ProviderConfig, ProviderType
from router.request_transformer import ClientRequest
from router.response_transformer import UnifiedResponse, ChatMessage, ChatChoice
from router.router import (
    Router,
    AsyncRouter,
    RouterConfig,
    RoutingResult,
    create_router,
    create_async_router,
)


class TestRouterConfig(unittest.TestCase):
    """测试 RouterConfig 数据类"""

    def test_default_config(self):
        """测试默认配置"""
        config = RouterConfig()

        self.assertEqual(config.default_timeout, 30)
        self.assertEqual(config.max_retries, 3)
        self.assertTrue(config.enable_fallback)
        self.assertTrue(config.enable_health_check)
        self.assertTrue(config.log_requests)
        self.assertFalse(config.log_responses)

    def test_custom_config(self):
        """测试自定义配置"""
        config = RouterConfig(
            default_timeout=60,
            max_retries=5,
            enable_fallback=False,
            log_responses=True,
        )

        self.assertEqual(config.default_timeout, 60)
        self.assertEqual(config.max_retries, 5)
        self.assertFalse(config.enable_fallback)
        self.assertTrue(config.log_responses)


class TestRoutingResult(unittest.TestCase):
    """测试 RoutingResult 数据类"""

    def test_success_result(self):
        """测试成功的路由结果"""
        result = RoutingResult(success=True)

        self.assertTrue(result.success)
        self.assertIsNone(result.error)

    def test_error_result(self):
        """测试失败的路由结果"""
        result = RoutingResult(
            success=False,
            error="No provider available",
            error_code="no_provider",
        )

        self.assertFalse(result.success)
        self.assertEqual(result.error, "No provider available")
        self.assertEqual(result.error_code, "no_provider")


class TestRouter(unittest.TestCase):
    """测试 Router 类"""

    def setUp(self):
        """设置测试固件"""
        self.router = Router()

        # 添加测试提供者
        self.openai_config = ProviderConfig(
            name="openai",
            provider_type=ProviderType.OPENAI,
            base_url="https://api.openai.com",
            api_key="sk-test",
            models=["gpt-3.5", "gpt-4"],
            priority=10,
        )
        self.anthropic_config = ProviderConfig(
            name="anthropic",
            provider_type=ProviderType.ANTHROPIC,
            base_url="https://api.anthropic.com",
            api_key="sk-ant-test",
            models=["claude-3"],
            priority=5,
        )

        self.router.add_provider(self.openai_config)
        self.router.add_provider(self.anthropic_config)

    def test_add_provider(self):
        """测试添加提供者"""
        router = Router()
        provider = router.add_provider(self.openai_config)

        self.assertEqual(provider.name, "openai")
        self.assertEqual(len(router.provider_manager), 1)

    def test_remove_provider(self):
        """测试移除提供者"""
        router = Router()
        router.add_provider(self.openai_config)

        result = router.remove_provider("openai")
        self.assertTrue(result)
        self.assertEqual(len(router.provider_manager), 0)

    def test_get_provider(self):
        """测试获取提供者"""
        provider = self.router.get_provider("openai")

        self.assertIsNotNone(provider)
        self.assertEqual(provider.name, "openai")

    def test_route_request_success(self):
        """测试成功路由请求"""
        request = ClientRequest(
            model="gpt-3.5",
            messages=[{"role": "user", "content": "Hello"}],
        )

        result = self.router.route_request(request)

        self.assertTrue(result.success)
        self.assertIsNotNone(result.provider)
        self.assertEqual(result.provider.name, "openai")
        self.assertIsNotNone(result.transformed_request)

    def test_route_request_anthropic(self):
        """测试路由到 Anthropic"""
        request = ClientRequest(
            model="claude-3",
            messages=[{"role": "user", "content": "Hello"}],
        )

        result = self.router.route_request(request)

        self.assertTrue(result.success)
        self.assertEqual(result.provider.name, "anthropic")

    def test_route_request_auto(self):
        """测试路由 auto 模型"""
        request = ClientRequest(
            model="auto",
            messages=[{"role": "user", "content": "Hello"}],
        )

        result = self.router.route_request(request)

        self.assertTrue(result.success)
        # auto 应该选择优先级最高的提供者
        self.assertEqual(result.provider.name, "openai")

    def test_route_request_no_provider(self):
        """测试没有提供者时的路由"""
        router = Router()
        request = ClientRequest(
            model="gpt-3.5",
            messages=[{"role": "user", "content": "Hello"}],
        )

        result = router.route_request(request)

        self.assertFalse(result.success)
        self.assertEqual(result.error_code, "no_provider")

    def test_route_request_metadata(self):
        """测试路由结果的元数据"""
        request = ClientRequest(
            model="gpt-3.5",
            messages=[{"role": "user", "content": "Hello"}],
        )

        result = self.router.route_request(request)

        self.assertIn("model", result.metadata)
        self.assertIn("provider_type", result.metadata)
        self.assertEqual(result.metadata["model"], "gpt-3.5")

    def test_process_response(self):
        """测试处理响应"""
        raw_response = {
            "id": "resp-123",
            "model": "gpt-3.5",
            "choices": [
                {
                    "index": 0,
                    "message": {"role": "assistant", "content": "Hello"},
                }
            ],
            "usage": {
                "prompt_tokens": 10,
                "completion_tokens": 5,
                "total_tokens": 15,
            },
        }

        provider = self.router.get_provider("openai")
        response = self.router.process_response(raw_response, provider)

        self.assertIsInstance(response, UnifiedResponse)
        self.assertEqual(response.id, "resp-123")
        self.assertEqual(response.choices[0].message.content, "Hello")

    def test_process_error(self):
        """测试处理错误"""
        error = Exception("API timeout")
        error_response = self.router.process_error(error, 500)

        self.assertEqual(error_response.error, "API timeout")
        self.assertEqual(error_response.status_code, 500)

    def test_mark_provider_unhealthy(self):
        """测试标记提供者不健康"""
        self.router.mark_provider_unhealthy("openai")

        provider = self.router.get_provider("openai")
        self.assertFalse(provider.is_healthy)

    def test_mark_provider_healthy(self):
        """测试标记提供者健康"""
        self.router.mark_provider_unhealthy("openai")
        self.router.mark_provider_healthy("openai")

        provider = self.router.get_provider("openai")
        self.assertTrue(provider.is_healthy)

    def test_get_status(self):
        """测试获取状态"""
        status = self.router.get_status()

        self.assertEqual(status["total_providers"], 2)
        self.assertEqual(status["healthy_providers"], 2)
        self.assertEqual(status["enabled_providers"], 2)

    def test_clear(self):
        """测试清空路由器"""
        self.router.clear()

        self.assertEqual(len(self.router.provider_manager), 0)

    def test_request_logging(self):
        """测试请求日志"""
        config = RouterConfig(log_requests=True)
        router = Router(config)
        router.add_provider(self.openai_config)

        request = ClientRequest(
            model="gpt-3.5",
            messages=[{"role": "user", "content": "Hello"}],
        )
        router.route_request(request)

        status = router.get_status()
        self.assertEqual(status["request_count"], 1)


class TestAsyncRouter(unittest.TestCase):
    """测试 AsyncRouter 类"""

    def setUp(self):
        """设置测试固件"""
        self.router = AsyncRouter()

        self.openai_config = ProviderConfig(
            name="openai",
            provider_type=ProviderType.OPENAI,
            base_url="https://api.openai.com",
            api_key="sk-test",
            models=["gpt-3.5"],
        )
        self.router.add_provider(self.openai_config)

    def test_async_router_creation(self):
        """测试异步路由器创建"""
        self.assertIsInstance(self.router, AsyncRouter)
        self.assertTrue(hasattr(self.router, "route_request_async"))
        self.assertTrue(hasattr(self.router, "process_response_async"))


class TestCreateRouterFunctions(unittest.TestCase):
    """测试创建路由器的便捷函数"""

    def test_create_router(self):
        """测试创建路由器"""
        router = create_router()

        self.assertIsInstance(router, Router)

    def test_create_router_with_config(self):
        """测试带配置创建路由器"""
        config = RouterConfig(default_timeout=60)
        router = create_router(config)

        self.assertEqual(router.config.default_timeout, 60)

    def test_create_async_router(self):
        """测试创建异步路由器"""
        router = create_async_router()

        self.assertIsInstance(router, AsyncRouter)


if __name__ == "__main__":
    unittest.main()
