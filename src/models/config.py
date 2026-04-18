"""
配置数据模型模块

定义系统所需的所有配置类，使用 dataclass 实现。
"""
from dataclasses import dataclass, field
from typing import Optional
from pathlib import Path


@dataclass
class Provider:
    """
    API 提供商配置类
    
    用于配置不同 AI 服务提供商的连接信息和模型映射。
    """
    name: str = ""  # 提供商名称
    api_endpoint: str = ""  # API 端点 URL
    api_key: str = ""  # API 密钥
    models: dict[str, str] = field(default_factory=dict)  # 模型名称映射 {本地名称：提供商模型名称}
    timeout: int = 30  # 请求超时时间（秒）
    retry_attempts: int = 3  # 重试次数
    enabled: bool = True  # 是否启用该提供商


@dataclass
class SSLConfig:
    """
    SSL/TLS 配置类
    
    用于配置 HTTPS 证书相关参数。
    """
    cert_path: Optional[str] = None  # 证书文件路径
    key_path: Optional[str] = None  # 私钥文件路径
    ca_bundle: Optional[str] = None  # CA 证书包路径
    verify_client: bool = False  # 是否验证客户端证书
    min_version: str = "TLSv1.2"  # 最低 TLS 版本
    
    @property
    def is_enabled(self) -> bool:
        """检查 SSL 是否已启用"""
        return self.cert_path is not None and self.key_path is not None


@dataclass
class ServerConfig:
    """
    服务器配置类
    
    用于配置 HTTP/HTTPS 服务器的运行参数。
    """
    host: str = "0.0.0.0"  # 监听地址
    port: int = 8080  # 监听端口
    workers: int = 4  # 工作进程数
    max_connections: int = 1000  # 最大连接数
    keep_alive_timeout: int = 60  # 保持连接超时时间（秒）
    request_timeout: int = 30  # 请求超时时间（秒）
    ssl: Optional[SSLConfig] = None  # SSL 配置
    
    @property
    def use_ssl(self) -> bool:
        """检查是否启用 SSL"""
        return self.ssl is not None and self.ssl.is_enabled
    
    @property
    def listen_address(self) -> str:
        """获取完整的监听地址"""
        return f"{self.host}:{self.port}"


@dataclass
class Config:
    """
    主配置类
    
    整合所有配置模块，提供统一的配置访问接口。
    """
    app_name: str = "ai_tunnel"  # 应用名称
    debug: bool = False  # 调试模式
    log_level: str = "INFO"  # 日志级别
    providers: dict[str, Provider] = field(default_factory=dict)  # API 提供商配置
    server: Optional[ServerConfig] = None  # 服务器配置
    config_path: Optional[str] = None  # 配置文件路径
    
    def get_provider(self, name: str) -> Optional[Provider]:
        """
        获取指定的提供商配置
        
        Args:
            name: 提供商名称
            
        Returns:
            提供商配置对象，不存在则返回 None
        """
        return self.providers.get(name)
    
    def get_enabled_providers(self) -> list[Provider]:
        """
        获取所有已启用的提供商配置
        
        Returns:
            已启用的提供商配置列表
        """
        return [p for p in self.providers.values() if p.enabled]
    
    @classmethod
    def create_default(cls) -> "Config":
        """
        创建默认配置
        
        Returns:
            包含默认值的配置对象
        """
        return cls(
            app_name="ai_tunnel",
            debug=False,
            log_level="INFO",
            server=ServerConfig(
                host="0.0.0.0",
                port=8080,
                workers=4,
            )
        )
