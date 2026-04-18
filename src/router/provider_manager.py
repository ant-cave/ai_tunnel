"""
API 提供者管理器模块

负责管理多个 API 提供者，根据模型名称选择合适的提供者，
并支持"auto"模型的自动选择功能。
"""

from dataclasses import dataclass, field
from typing import Dict, List, Optional, Any
from enum import Enum
import logging

logger = logging.getLogger(__name__)


class ProviderType(Enum):
    """API 提供者类型枚举"""
    OPENAI = "openai"
    ANTHROPIC = "anthropic"
    AZURE = "azure"
    CUSTOM = "custom"


@dataclass
class ProviderConfig:
    """API 提供者配置数据类"""
    name: str
    provider_type: ProviderType
    base_url: str
    api_key: str
    models: List[str] = field(default_factory=list)
    priority: int = 0
    enabled: bool = True
    extra_config: Dict[str, Any] = field(default_factory=dict)

    def supports_model(self, model_name: str) -> bool:
        """检查提供者是否支持指定模型"""
        if not self.enabled:
            return False
        if not self.models:
            return True
        return model_name in self.models or "*" in self.models


class APIProvider:
    """API 提供者类，封装单个提供者的信息和能力"""

    def __init__(self, config: ProviderConfig):
        self.config = config
        self._healthy = True

    @property
    def name(self) -> str:
        return self.config.name

    @property
    def provider_type(self) -> ProviderType:
        return self.config.provider_type

    @property
    def base_url(self) -> str:
        return self.config.base_url

    @property
    def api_key(self) -> str:
        return self.config.api_key

    @property
    def models(self) -> List[str]:
        return self.config.models

    @property
    def priority(self) -> int:
        return self.config.priority

    @property
    def enabled(self) -> bool:
        return self.config.enabled

    @property
    def is_healthy(self) -> bool:
        return self._healthy and self.enabled

    def mark_unhealthy(self):
        """标记提供者为不健康状态"""
        self._healthy = False
        logger.warning(f"提供者 {self.name} 已标记为不健康")

    def mark_healthy(self):
        """标记提供者为健康状态"""
        self._healthy = True
        logger.info(f"提供者 {self.name} 已恢复健康")

    def supports_model(self, model_name: str) -> bool:
        """检查是否支持指定模型"""
        return self.config.supports_model(model_name)

    def get_extra_config(self, key: str, default: Any = None) -> Any:
        """获取额外配置项"""
        return self.config.extra_config.get(key, default)


class ProviderManager:
    """
    API 提供者管理器
    
    负责管理多个 API 提供者，提供以下功能：
    - 添加/移除提供者
    - 根据模型名称选择提供者
    - 支持"auto"模型自动选择
    - 提供者健康状态管理
    """

    AUTO_MODEL_NAME = "auto"

    def __init__(self):
        self._providers: Dict[str, APIProvider] = {}
        self._model_provider_map: Dict[str, str] = {}
        self._default_provider: Optional[str] = None

    def add_provider(self, config: ProviderConfig) -> APIProvider:
        """
        添加 API 提供者
        
        Args:
            config: 提供者配置
            
        Returns:
            创建的 APIProvider 实例
            
        Raises:
            ValueError: 当提供者名称已存在时
        """
        if config.name in self._providers:
            raise ValueError(f"提供者 {config.name} 已存在")

        provider = APIProvider(config)
        self._providers[config.name] = provider

        # 更新模型到提供者的映射
        for model in config.models:
            if model not in self._model_provider_map:
                self._model_provider_map[model] = config.name

        # 如果没有默认提供者，设置第一个添加的为默认
        if self._default_provider is None:
            self._default_provider = config.name

        logger.info(f"已添加提供者：{config.name}")
        return provider
    
    def update_provider_models(self, name: str, models: list) -> bool:
        """
        更新提供者的模型列表
        
        Args:
            name: 提供者名称
            models: 新的模型列表
            
        Returns:
            是否成功更新
        """
        if name not in self._providers:
            logger.warning(f"提供者 {name} 不存在，无法更新模型列表")
            return False
        
        provider = self._providers[name]
        provider.config.models = models
        
        # 更新模型到提供者的映射
        # 先清除旧的映射
        for model, provider_name in list(self._model_provider_map.items()):
            if provider_name == name:
                del self._model_provider_map[model]
        
        # 添加新的映射
        for model in models:
            if model not in self._model_provider_map:
                self._model_provider_map[model] = name
        
        logger.info(f"已更新提供者 {name} 的模型列表：{len(models)} 个模型")
        return True

    def remove_provider(self, name: str) -> bool:
        """
        移除 API 提供者
        
        Args:
            name: 提供者名称
            
        Returns:
            是否成功移除
        """
        if name not in self._providers:
            return False

        provider = self._providers[name]
        del self._providers[name]

        # 清理模型映射
        for model in list(self._model_provider_map.keys()):
            if self._model_provider_map[model] == name:
                del self._model_provider_map[model]

        # 如果移除的是默认提供者，重新设置默认
        if self._default_provider == name:
            self._default_provider = next(iter(self._providers.keys()), None)

        logger.info(f"已移除提供者：{name}")
        return True

    def get_provider(self, name: str) -> Optional[APIProvider]:
        """
        获取指定名称的提供者
        
        Args:
            name: 提供者名称
            
        Returns:
            APIProvider 实例，不存在则返回 None
        """
        return self._providers.get(name)

    def get_all_providers(self) -> List[APIProvider]:
        """获取所有提供者列表"""
        return list(self._providers.values())

    def get_enabled_providers(self) -> List[APIProvider]:
        """获取所有启用的提供者列表"""
        return [p for p in self._providers.values() if p.enabled]

    def get_healthy_providers(self) -> List[APIProvider]:
        """获取所有健康的提供者列表"""
        return [p for p in self._providers.values() if p.is_healthy]

    def select_provider_for_model(self, model_name: str) -> Optional[APIProvider]:
        """
        为指定模型选择最合适的提供者
        
        选择逻辑：
        1. 如果模型名为"auto"，自动选择优先级最高的健康提供者
        2. 查找明确支持该模型的提供者
        3. 如果没有明确匹配，返回默认提供者
        
        Args:
            model_name: 模型名称
            
        Returns:
            选中的 APIProvider 实例，找不到则返回 None
        """
        if not self._providers:
            logger.warning("没有可用的提供者")
            return None

        # 处理"auto"模型
        if model_name.lower() == self.AUTO_MODEL_NAME:
            return self._select_auto_provider()

        # 查找明确支持该模型的提供者
        for provider in self._providers.values():
            if provider.supports_model(model_name) and provider.is_healthy:
                logger.debug(f"为模型 {model_name} 选择提供者 {provider.name}")
                return provider

        # 检查模型映射
        if model_name in self._model_provider_map:
            provider_name = self._model_provider_map[model_name]
            provider = self._providers.get(provider_name)
            if provider and provider.is_healthy:
                return provider

        # 返回默认提供者
        if self._default_provider:
            default = self._providers.get(self._default_provider)
            if default and default.is_healthy:
                logger.warning(
                    f"未找到模型 {model_name} 的专属提供者，使用默认提供者 {default.name}"
                )
                return default

        logger.error(f"无法为模型 {model_name} 找到合适的提供者")
        return None

    def _select_auto_provider(self) -> Optional[APIProvider]:
        """
        自动选择最优提供者
        
        选择策略：
        1. 优先选择优先级高的
        2. 在优先级相同的情况下，选择健康的提供者
        3. 如果都不可用，返回第一个启用的提供者
        
        Returns:
            选中的 APIProvider 实例
        """
        healthy_providers = self.get_healthy_providers()

        if not healthy_providers:
            logger.warning("没有健康的提供者，尝试返回启用的提供者")
            enabled_providers = self.get_enabled_providers()
            if enabled_providers:
                return enabled_providers[0]
            return None

        # 按优先级排序
        sorted_providers = sorted(
            healthy_providers,
            key=lambda p: p.priority,
            reverse=True
        )

        selected = sorted_providers[0]
        logger.info(f"Auto 模式选择提供者：{selected.name} (优先级：{selected.priority})")
        return selected

    def set_default_provider(self, name: str) -> bool:
        """
        设置默认提供者
        
        Args:
            name: 提供者名称
            
        Returns:
            是否设置成功
        """
        if name not in self._providers:
            logger.error(f"无法设置默认提供者：{name} 不存在")
            return False

        self._default_provider = name
        logger.info(f"默认提供者已设置为：{name}")
        return True

    def get_default_provider(self) -> Optional[APIProvider]:
        """获取默认提供者"""
        if not self._default_provider:
            return None
        return self._providers.get(self._default_provider)

    def clear(self):
        """清空所有提供者"""
        self._providers.clear()
        self._model_provider_map.clear()
        self._default_provider = None
        logger.info("已清空所有提供者")

    def __len__(self) -> int:
        """获取提供者数量"""
        return len(self._providers)

    def __contains__(self, name: str) -> bool:
        """检查提供者是否存在"""
        return name in self._providers
