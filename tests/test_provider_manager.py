"""
提供者管理器单元测试

测试 provider_manager.py 中的核心功能
"""

import unittest
import sys
from pathlib import Path

# 添加 src 目录到路径
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from router.provider_manager import (
    ProviderManager,
    ProviderConfig,
    ProviderType,
    APIProvider,
)


class TestProviderConfig(unittest.TestCase):
    """测试 ProviderConfig 数据类"""

    def test_create_provider_config(self):
        """测试创建提供者配置"""
        config = ProviderConfig(
            name="test_provider",
            provider_type=ProviderType.OPENAI,
            base_url="https://api.test.com",
            api_key="test_key",
            models=["gpt-3.5", "gpt-4"],
            priority=10,
        )

        self.assertEqual(config.name, "test_provider")
        self.assertEqual(config.provider_type, ProviderType.OPENAI)
        self.assertEqual(config.base_url, "https://api.test.com")
        self.assertEqual(config.api_key, "test_key")
        self.assertEqual(config.models, ["gpt-3.5", "gpt-4"])
        self.assertEqual(config.priority, 10)
        self.assertTrue(config.enabled)

    def test_supports_model(self):
        """测试模型支持检查"""
        config = ProviderConfig(
            name="test",
            provider_type=ProviderType.OPENAI,
            base_url="https://api.test.com",
            api_key="key",
            models=["model1", "model2"],
        )

        self.assertTrue(config.supports_model("model1"))
        self.assertTrue(config.supports_model("model2"))
        self.assertFalse(config.supports_model("model3"))

    def test_supports_model_wildcard(self):
        """测试通配符模型支持"""
        config = ProviderConfig(
            name="test",
            provider_type=ProviderType.OPENAI,
            base_url="https://api.test.com",
            api_key="key",
            models=["*"],
        )

        self.assertTrue(config.supports_model("any_model"))

    def test_supports_model_disabled(self):
        """测试禁用的提供者不支持模型"""
        config = ProviderConfig(
            name="test",
            provider_type=ProviderType.OPENAI,
            base_url="https://api.test.com",
            api_key="key",
            models=["model1"],
            enabled=False,
        )

        self.assertFalse(config.supports_model("model1"))


class TestAPIProvider(unittest.TestCase):
    """测试 APIProvider 类"""

    def setUp(self):
        """设置测试固件"""
        self.config = ProviderConfig(
            name="test_provider",
            provider_type=ProviderType.OPENAI,
            base_url="https://api.test.com",
            api_key="test_key",
            models=["gpt-3.5", "gpt-4"],
            priority=5,
        )
        self.provider = APIProvider(self.config)

    def test_provider_properties(self):
        """测试提供者属性"""
        self.assertEqual(self.provider.name, "test_provider")
        self.assertEqual(self.provider.provider_type, ProviderType.OPENAI)
        self.assertEqual(self.provider.base_url, "https://api.test.com")
        self.assertEqual(self.provider.api_key, "test_key")
        self.assertEqual(self.provider.priority, 5)
        self.assertTrue(self.provider.enabled)
        self.assertTrue(self.provider.is_healthy)

    def test_mark_unhealthy(self):
        """测试标记不健康状态"""
        self.assertTrue(self.provider.is_healthy)
        self.provider.mark_unhealthy()
        self.assertFalse(self.provider.is_healthy)

    def test_mark_healthy(self):
        """测试恢复健康状态"""
        self.provider.mark_unhealthy()
        self.assertFalse(self.provider.is_healthy)
        self.provider.mark_healthy()
        self.assertTrue(self.provider.is_healthy)

    def test_supports_model(self):
        """测试模型支持"""
        self.assertTrue(self.provider.supports_model("gpt-3.5"))
        self.assertTrue(self.provider.supports_model("gpt-4"))
        self.assertFalse(self.provider.supports_model("claude-3"))

    def test_get_extra_config(self):
        """测试获取额外配置"""
        self.assertEqual(self.provider.get_extra_config("key1", "default"), "default")

        self.config.extra_config = {"api_version": "2023-05-15", "timeout": 60}
        self.assertEqual(self.provider.get_extra_config("api_version"), "2023-05-15")
        self.assertEqual(self.provider.get_extra_config("timeout"), 60)


class TestProviderManager(unittest.TestCase):
    """测试 ProviderManager 类"""

    def setUp(self):
        """设置测试固件"""
        self.manager = ProviderManager()
        self.config1 = ProviderConfig(
            name="openai_provider",
            provider_type=ProviderType.OPENAI,
            base_url="https://api.openai.com",
            api_key="key1",
            models=["gpt-3.5", "gpt-4"],
            priority=10,
        )
        self.config2 = ProviderConfig(
            name="anthropic_provider",
            provider_type=ProviderType.ANTHROPIC,
            base_url="https://api.anthropic.com",
            api_key="key2",
            models=["claude-3"],
            priority=5,
        )

    def test_add_provider(self):
        """测试添加提供者"""
        provider = self.manager.add_provider(self.config1)

        self.assertEqual(len(self.manager), 1)
        self.assertIn("openai_provider", self.manager)
        self.assertEqual(provider.name, "openai_provider")

    def test_add_duplicate_provider(self):
        """测试添加重复提供者"""
        self.manager.add_provider(self.config1)

        with self.assertRaises(ValueError):
            self.manager.add_provider(self.config1)

    def test_remove_provider(self):
        """测试移除提供者"""
        self.manager.add_provider(self.config1)
        self.assertEqual(len(self.manager), 1)

        result = self.manager.remove_provider("openai_provider")
        self.assertTrue(result)
        self.assertEqual(len(self.manager), 0)

    def test_remove_nonexistent_provider(self):
        """测试移除不存在的提供者"""
        result = self.manager.remove_provider("nonexistent")
        self.assertFalse(result)

    def test_get_provider(self):
        """测试获取提供者"""
        self.manager.add_provider(self.config1)

        provider = self.manager.get_provider("openai_provider")
        self.assertIsNotNone(provider)
        self.assertEqual(provider.name, "openai_provider")

    def test_get_all_providers(self):
        """测试获取所有提供者"""
        self.manager.add_provider(self.config1)
        self.manager.add_provider(self.config2)

        providers = self.manager.get_all_providers()
        self.assertEqual(len(providers), 2)

    def test_get_enabled_providers(self):
        """测试获取启用的提供者"""
        self.manager.add_provider(self.config1)

        disabled_config = ProviderConfig(
            name="disabled_provider",
            provider_type=ProviderType.CUSTOM,
            base_url="https://disabled.com",
            api_key="key3",
            enabled=False,
        )
        self.manager.add_provider(disabled_config)

        enabled = self.manager.get_enabled_providers()
        self.assertEqual(len(enabled), 1)
        self.assertEqual(enabled[0].name, "openai_provider")

    def test_select_provider_for_model(self):
        """测试为模型选择提供者"""
        self.manager.add_provider(self.config1)
        self.manager.add_provider(self.config2)

        # 选择支持 gpt-3.5 的提供者
        provider = self.manager.select_provider_for_model("gpt-3.5")
        self.assertIsNotNone(provider)
        self.assertEqual(provider.name, "openai_provider")

        # 选择支持 claude-3 的提供者
        provider = self.manager.select_provider_for_model("claude-3")
        self.assertIsNotNone(provider)
        self.assertEqual(provider.name, "anthropic_provider")

    def test_select_provider_auto_model(self):
        """测试 auto 模型选择"""
        self.manager.add_provider(self.config1)
        self.manager.add_provider(self.config2)

        # auto 应该选择优先级最高的
        provider = self.manager.select_provider_for_model("auto")
        self.assertIsNotNone(provider)
        self.assertEqual(provider.name, "openai_provider")
        self.assertEqual(provider.priority, 10)

    def test_select_provider_no_match(self):
        """测试没有匹配模型时的选择"""
        self.manager.add_provider(self.config1)

        # 没有匹配的模型，应该返回默认提供者
        provider = self.manager.select_provider_for_model("unknown_model")
        self.assertIsNotNone(provider)
        self.assertEqual(provider.name, "openai_provider")

    def test_select_provider_no_providers(self):
        """测试没有提供者时"""
        provider = self.manager.select_provider_for_model("gpt-3.5")
        self.assertIsNone(provider)

    def test_select_provider_unhealthy(self):
        """测试提供者不健康时的选择"""
        self.manager.add_provider(self.config1)
        self.manager.add_provider(self.config2)

        # 标记 openai 提供者为不健康
        openai_provider = self.manager.get_provider("openai_provider")
        openai_provider.mark_unhealthy()

        # auto 应该选择 anthropic（下一个优先级）
        provider = self.manager.select_provider_for_model("auto")
        self.assertIsNotNone(provider)
        self.assertEqual(provider.name, "anthropic_provider")

    def test_set_default_provider(self):
        """测试设置默认提供者"""
        self.manager.add_provider(self.config1)
        self.manager.add_provider(self.config2)

        result = self.manager.set_default_provider("anthropic_provider")
        self.assertTrue(result)

        default = self.manager.get_default_provider()
        self.assertEqual(default.name, "anthropic_provider")

    def test_set_default_nonexistent_provider(self):
        """测试设置不存在的默认提供者"""
        result = self.manager.set_default_provider("nonexistent")
        self.assertFalse(result)

    def test_clear(self):
        """测试清空所有提供者"""
        self.manager.add_provider(self.config1)
        self.manager.add_provider(self.config2)

        self.manager.clear()
        self.assertEqual(len(self.manager), 0)
        self.assertIsNone(self.manager.get_default_provider())


if __name__ == "__main__":
    unittest.main()
