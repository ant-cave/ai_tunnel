"""
配置加载器模块

负责加载和解析 TOML 配置文件，提供默认值处理。
"""
import tomllib
from pathlib import Path
from typing import Optional
from src.models.config import (
    Config,
    Provider,
    SSLConfig,
    ServerConfig,
)


class ConfigLoader:
    """
    配置加载器类
    
    从 TOML 文件加载配置，并提供默认值填充功能。
    """
    
    # 默认配置值
    DEFAULT_APP_NAME = "ai_tunnel"
    DEFAULT_DEBUG = False
    DEFAULT_LOG_LEVEL = "INFO"
    
    DEFAULT_SERVER_HOST = "0.0.0.0"
    DEFAULT_SERVER_PORT = 8080
    DEFAULT_SERVER_WORKERS = 4
    DEFAULT_MAX_CONNECTIONS = 1000
    DEFAULT_KEEP_ALIVE_TIMEOUT = 60
    DEFAULT_REQUEST_TIMEOUT = 30
    
    DEFAULT_PROVIDER_TIMEOUT = 30
    DEFAULT_PROVIDER_RETRY_ATTEMPTS = 3
    DEFAULT_PROVIDER_ENABLED = True
    
    def __init__(self, config_path: Optional[str] = None) -> None:
        """
        初始化配置加载器
        
        Args:
            config_path: 配置文件路径，可选
        """
        self.config_path = Path(config_path) if config_path else None
        self._raw_config: dict = {}
    
    def load(self, config_path: Optional[str] = None) -> Config:
        """
        加载配置文件
        
        Args:
            config_path: 配置文件路径，如果为 None 则使用初始化时传入的路径
            
        Returns:
            配置对象
            
        Raises:
            FileNotFoundError: 配置文件不存在
            tomllib.TOMLDecodeError: TOML 文件解析失败
        """
        if config_path:
            self.config_path = Path(config_path)
        
        if not self.config_path:
            raise FileNotFoundError("未指定配置文件路径")
        
        if not self.config_path.exists():
            raise FileNotFoundError(f"配置文件不存在：{self.config_path}")
        
        # 读取并解析 TOML 文件
        with open(self.config_path, "rb") as f:
            self._raw_config = tomllib.load(f)
        
        return self._build_config()
    
    def load_from_dict(self, config_dict: dict) -> Config:
        """
        从字典加载配置
        
        Args:
            config_dict: 配置字典
            
        Returns:
            配置对象
        """
        self._raw_config = config_dict
        return self._build_config()
    
    def _build_config(self) -> Config:
        """
        构建配置对象
        
        Returns:
            完整的配置对象
        """
        # 构建基础配置
        config = Config(
            app_name=self._raw_config.get("app_name", self.DEFAULT_APP_NAME),
            debug=self._raw_config.get("debug", self.DEFAULT_DEBUG),
            log_level=self._raw_config.get("log_level", self.DEFAULT_LOG_LEVEL),
            config_path=str(self.config_path) if self.config_path else None,
        )
        
        # 构建服务器配置
        if "server" in self._raw_config:
            config.server = self._build_server_config(self._raw_config["server"])
        else:
            config.server = ServerConfig(
                host=self.DEFAULT_SERVER_HOST,
                port=self.DEFAULT_SERVER_PORT,
                workers=self.DEFAULT_SERVER_WORKERS,
            )
        
        # 构建提供商配置
        if "providers" in self._raw_config:
            config.providers = self._build_providers(self._raw_config["providers"])
        
        return config
    
    def _build_server_config(self, server_data: dict) -> ServerConfig:
        """
        构建服务器配置
        
        Args:
            server_data: 服务器配置数据
            
        Returns:
            服务器配置对象
        """
        # 处理 SSL 配置
        ssl_config = None
        if "ssl" in server_data:
            ssl_data = server_data["ssl"]
            ssl_config = SSLConfig(
                cert_path=ssl_data.get("cert_path"),
                key_path=ssl_data.get("key_path"),
                ca_bundle=ssl_data.get("ca_bundle"),
                verify_client=ssl_data.get("verify_client", False),
                min_version=ssl_data.get("min_version", "TLSv1.2"),
            )
        
        return ServerConfig(
            host=server_data.get("host", self.DEFAULT_SERVER_HOST),
            port=server_data.get("port", self.DEFAULT_SERVER_PORT),
            workers=server_data.get("workers", self.DEFAULT_SERVER_WORKERS),
            max_connections=server_data.get("max_connections", self.DEFAULT_MAX_CONNECTIONS),
            keep_alive_timeout=server_data.get(
                "keep_alive_timeout", self.DEFAULT_KEEP_ALIVE_TIMEOUT
            ),
            request_timeout=server_data.get(
                "request_timeout", self.DEFAULT_REQUEST_TIMEOUT
            ),
            ssl=ssl_config,
        )
    
    def _build_providers(self, providers_data: dict) -> dict[str, Provider]:
        """
        构建提供商配置字典
        
        Args:
            providers_data: 提供商配置数据
            
        Returns:
            提供商配置字典
        """
        providers = {}
        
        for name, data in providers_data.items():
            providers[name] = Provider(
                name=data.get("name", name),
                api_endpoint=data.get("api_endpoint", ""),
                api_key=data.get("api_key", ""),
                models=data.get("models", {}),
                timeout=data.get("timeout", self.DEFAULT_PROVIDER_TIMEOUT),
                retry_attempts=data.get(
                    "retry_attempts", self.DEFAULT_PROVIDER_RETRY_ATTEMPTS
                ),
                enabled=data.get("enabled", self.DEFAULT_PROVIDER_ENABLED),
            )
        
        return providers
    
    def validate(self) -> bool:
        """
        验证配置文件的完整性
        
        Returns:
            验证是否通过
            
        Raises:
            ValueError: 配置验证失败时抛出
        """
        if not self._raw_config:
            raise ValueError("未加载任何配置")
        
        # 验证必填字段
        required_fields = ["app_name"]
        for field_name in required_fields:
            if field_name not in self._raw_config:
                raise ValueError(f"缺少必填配置字段：{field_name}")
        
        # 验证 providers 配置
        if "providers" in self._raw_config:
            for name, data in self._raw_config["providers"].items():
                if "api_endpoint" not in data:
                    raise ValueError(f"提供商 {name} 缺少 api_endpoint 配置")
                if "api_key" not in data:
                    raise ValueError(f"提供商 {name} 缺少 api_key 配置")
        
        return True
    
    def get_raw_config(self) -> dict:
        """
        获取原始配置字典
        
        Returns:
            原始配置字典
        """
        return self._raw_config.copy()
