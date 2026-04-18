"""
配置验证器模块

提供配置完整性和有效性验证功能。
"""
from pathlib import Path
from typing import Optional
from src.models.config import Config, Provider, SSLConfig, ServerConfig


class ValidationError(Exception):
    """配置验证异常类"""
    pass


class ConfigValidator:
    """
    配置验证器类
    
    对配置对象进行完整性和有效性验证。
    """
    
    # 有效的日志级别
    VALID_LOG_LEVELS = ["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"]
    
    # 有效的 TLS 版本
    VALID_TLS_VERSIONS = ["TLSv1.2", "TLSv1.3"]
    
    # 端口范围
    MIN_PORT = 1
    MAX_PORT = 65535
    
    def __init__(self, config: Config) -> None:
        """
        初始化配置验证器
        
        Args:
            config: 待验证的配置对象
        """
        self.config = config
        self._errors: list[str] = []
    
    def validate(self) -> bool:
        """
        执行完整验证
        
        Returns:
            验证是否通过
            
        Raises:
            ValidationError: 验证失败时抛出异常
        """
        self._errors = []
        
        # 验证基础配置
        self._validate_base_config()
        
        # 验证服务器配置
        if self.config.server:
            self._validate_server_config()
        
        # 验证提供商配置
        self._validate_providers()
        
        # 如果有错误，抛出异常
        if self._errors:
            error_message = "配置验证失败:\n" + "\n".join(f"  - {e}" for e in self._errors)
            raise ValidationError(error_message)
        
        return True
    
    def validate_safe(self) -> tuple[bool, list[str]]:
        """
        安全验证（不抛出异常）
        
        Returns:
            (验证是否通过，错误信息列表)
        """
        self._errors = []
        
        self._validate_base_config()
        
        if self.config.server:
            self._validate_server_config()
        
        self._validate_providers()
        
        return (len(self._errors) == 0, self._errors)
    
    def _validate_base_config(self) -> None:
        """验证基础配置"""
        # 验证应用名称
        if not self.config.app_name:
            self._errors.append("应用名称不能为空")
        
        # 验证日志级别
        if self.config.log_level not in self.VALID_LOG_LEVELS:
            self._errors.append(
                f"无效的日志级别：{self.config.log_level}，"
                f"有效值为：{', '.join(self.VALID_LOG_LEVELS)}"
            )
    
    def _validate_server_config(self) -> None:
        """验证服务器配置"""
        if not self.config.server:
            return
        
        server = self.config.server
        
        # 验证主机地址
        if not server.host:
            self._errors.append("服务器主机地址不能为空")
        
        # 验证端口号
        if not (self.MIN_PORT <= server.port <= self.MAX_PORT):
            self._errors.append(
                f"端口号必须在 {self.MIN_PORT}-{self.MAX_PORT} 范围内，"
                f"当前值：{server.port}"
            )
        
        # 验证工作进程数
        if server.workers <= 0:
            self._errors.append("工作进程数必须大于 0")
        
        # 验证最大连接数
        if server.max_connections <= 0:
            self._errors.append("最大连接数必须大于 0")
        
        # 验证超时配置
        if server.keep_alive_timeout < 0:
            self._errors.append("保持连接超时不能为负数")
        
        if server.request_timeout <= 0:
            self._errors.append("请求超时必须大于 0")
        
        # 验证 SSL 配置
        if server.ssl:
            self._validate_ssl_config(server.ssl)
    
    def _validate_ssl_config(self, ssl: SSLConfig) -> None:
        """验证 SSL 配置"""
        # 如果启用了 SSL，验证证书文件
        if ssl.cert_path or ssl.key_path:
            if not ssl.cert_path:
                self._errors.append("启用 SSL 时必须提供证书文件路径")
            elif not Path(ssl.cert_path).exists():
                self._errors.append(f"证书文件不存在：{ssl.cert_path}")
            
            if not ssl.key_path:
                self._errors.append("启用 SSL 时必须提供私钥文件路径")
            elif not Path(ssl.key_path).exists():
                self._errors.append(f"私钥文件不存在：{ssl.key_path}")
        
        # 验证 CA 证书包
        if ssl.ca_bundle and not Path(ssl.ca_bundle).exists():
            self._errors.append(f"CA 证书包不存在：{ssl.ca_bundle}")
        
        # 验证 TLS 版本
        if ssl.min_version not in self.VALID_TLS_VERSIONS:
            self._errors.append(
                f"无效的 TLS 版本：{ssl.min_version}，"
                f"有效值为：{', '.join(self.VALID_TLS_VERSIONS)}"
            )
    
    def _validate_providers(self) -> None:
        """验证提供商配置"""
        if not self.config.providers:
            return
        
        for name, provider in self.config.providers.items():
            self._validate_single_provider(name, provider)
    
    def _validate_single_provider(
        self, name: str, provider: Provider
    ) -> None:
        """验证单个提供商配置"""
        # 验证名称
        if not provider.name:
            self._errors.append(f"提供商 {name} 的名称不能为空")
        
        # 验证 API 端点
        if not provider.api_endpoint:
            self._errors.append(f"提供商 {name} 的 API 端点不能为空")
        else:
            # 简单的 URL 格式验证
            if not (
                provider.api_endpoint.startswith("http://")
                or provider.api_endpoint.startswith("https://")
            ):
                self._errors.append(
                    f"提供商 {name} 的 API 端点必须是有效的 URL "
                    f"(http:// 或 https://)"
                )
        
        # 验证 API 密钥
        if not provider.api_key:
            self._errors.append(f"提供商 {name} 的 API 密钥不能为空")
        
        # 验证超时时间
        if provider.timeout <= 0:
            self._errors.append(
                f"提供商 {name} 的超时时间必须大于 0"
            )
        
        # 验证重试次数
        if provider.retry_attempts < 0:
            self._errors.append(
                f"提供商 {name} 的重试次数不能为负数"
            )
    
    def get_errors(self) -> list[str]:
        """
        获取所有验证错误
        
        Returns:
            错误信息列表
        """
        return self._errors.copy()
    
    @classmethod
    def validate_config(cls, config: Config) -> bool:
        """
        类方法：直接验证配置对象
        
        Args:
            config: 待验证的配置对象
            
        Returns:
            验证是否通过
            
        Raises:
            ValidationError: 验证失败时抛出异常
        """
        validator = cls(config)
        return validator.validate()
