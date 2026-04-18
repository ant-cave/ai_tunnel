"""
应用设置模块

定义应用程序的所有配置项，支持从 TOML 文件加载
"""

import os
from dataclasses import dataclass, field
from typing import Optional, List
from pathlib import Path

from src.config.config_loader import ConfigLoader
from src.utils.exceptions import ConfigurationError


@dataclass
class ServerConfig:
    """服务器配置"""
    host: str = "0.0.0.0"
    port: int = 8080
    ssl_enabled: bool = False
    ssl_cert_path: Optional[str] = None
    ssl_key_path: Optional[str] = None
    workers: int = 4
    max_connections: int = 1000
    keep_alive_timeout: int = 60
    request_timeout: int = 30


@dataclass
class SecurityConfig:
    """安全配置"""
    api_key: Optional[str] = None
    allowed_origins: List[str] = field(default_factory=lambda: ["*"])
    rate_limit: int = 100  # 每分钟请求数限制
    encryption_enabled: bool = True


@dataclass
class LoggingConfig:
    """日志配置"""
    level: str = "INFO"
    format: str = "%(asctime)s - %(name)s - %(levelname)s - %(message)s"
    file: Optional[str] = None
    max_size: int = 10 * 1024 * 1024  # 10MB
    backup_count: int = 5


@dataclass
class Settings:
    """应用设置主类
    
    整合所有配置模块，提供统一的配置访问接口
    """
    
    # 服务器配置
    server: ServerConfig = field(default_factory=ServerConfig)
    
    # 安全配置
    security: SecurityConfig = field(default_factory=SecurityConfig)
    
    # 日志配置
    logging: LoggingConfig = field(default_factory=LoggingConfig)
    
    # 便捷属性
    @property
    def log_level(self) -> str:
        """获取日志级别"""
        return self.logging.level
    
    @property
    def log_file(self) -> Optional[str]:
        """获取日志文件路径"""
        return self.logging.file
    
    def __post_init__(self) -> None:
        """dataclass 初始化后处理
        
        在 dataclass 自动初始化后执行额外的初始化逻辑
        """
        if not hasattr(self, '_initialized'):
            self._initialized = True
    
    def __init__(self, config_path: Optional[str] = None):
        """初始化设置
        
        Args:
            config_path: 配置文件路径
        """
        # 先初始化 dataclass 的默认属性
        self.server = ServerConfig()
        self.security = SecurityConfig()
        self.logging = LoggingConfig()
        
        # 然后根据配置路径加载
        if config_path:
            self._load_from_file(config_path)
        else:
            self._load_from_env()
    
    def _load_from_file(self, config_path: str) -> None:
        """从文件加载配置
        
        Args:
            config_path: 配置文件路径
            
        Raises:
            ConfigurationError: 配置文件加载失败
        """
        try:
            loader = ConfigLoader(config_path)
            config_data = loader.load()
            
            # 更新服务器配置
            if "server" in config_data:
                server_data = config_data["server"]
                self.server = ServerConfig(**server_data)
            
            # 更新安全配置
            if "security" in config_data:
                security_data = config_data["security"]
                self.security = SecurityConfig(**security_data)
            
            # 更新日志配置
            if "logging" in config_data:
                logging_data = config_data["logging"]
                self.logging = LoggingConfig(**logging_data)
                
        except Exception as e:
            raise ConfigurationError(f"配置文件加载失败：{str(e)}")
    
    def _load_from_env(self) -> None:
        """从环境变量加载配置
        
        使用默认配置，可通过环境变量覆盖
        """
        # 从环境变量加载服务器配置
        self.server.host = os.getenv("AI_TUNNEL_HOST", self.server.host)
        self.server.port = int(os.getenv("AI_TUNNEL_PORT", self.server.port))
        
        # 从环境变量加载日志配置
        self.logging.level = os.getenv("AI_TUNNEL_LOG_LEVEL", self.logging.level)
    
    def validate(self) -> None:
        """验证配置的有效性
        
        Raises:
            ConfigurationError: 配置验证失败
        """
        # 验证端口范围
        if not (0 < self.server.port < 65536):
            raise ConfigurationError(f"无效端口号：{self.server.port}")
        
        # 验证 SSL 配置
        if self.server.ssl_enabled:
            if not self.server.ssl_cert_path or not self.server.ssl_key_path:
                raise ConfigurationError("SSL 启用时必须提供证书和密钥路径")
            
            if not Path(self.server.ssl_cert_path).exists():
                raise ConfigurationError(f"SSL 证书文件不存在：{self.server.ssl_cert_path}")
            
            if not Path(self.server.ssl_key_path).exists():
                raise ConfigurationError(f"SSL 密钥文件不存在：{self.server.ssl_key_path}")
        
        # 验证日志级别
        valid_levels = ["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"]
        if self.logging.level not in valid_levels:
            raise ConfigurationError(f"无效的日志级别：{self.logging.level}")
