"""
配置数据模型单元测试
"""
import pytest
from pathlib import Path
from src.models.config import Provider, SSLConfig, ServerConfig, Config


class TestProvider:
    """Provider 类测试"""
    
    def test_create_provider(self) -> None:
        """测试创建基本的 Provider"""
        provider = Provider(
            name="test",
            api_endpoint="https://api.test.com",
            api_key="test-key"
        )
        
        assert provider.name == "test"
        assert provider.api_endpoint == "https://api.test.com"
        assert provider.api_key == "test-key"
        assert provider.timeout == 30
        assert provider.retry_attempts == 3
        assert provider.enabled is True
    
    def test_provider_with_models(self) -> None:
        """测试带模型映射的 Provider"""
        models = {"gpt-4": "gpt-4-turbo", "gpt-3.5": "gpt-3.5-turbo"}
        provider = Provider(
            name="openai",
            api_endpoint="https://api.openai.com",
            api_key="key",
            models=models
        )
        
        assert provider.models == models
        assert provider.models["gpt-4"] == "gpt-4-turbo"
    
    def test_provider_default_values(self) -> None:
        """测试 Provider 默认值"""
        provider = Provider()
        
        assert provider.timeout == 30
        assert provider.retry_attempts == 3
        assert provider.enabled is True
        assert provider.models == {}
    
    def test_provider_empty_fields(self) -> None:
        """测试空字段"""
        provider = Provider()
        
        assert provider.name == ""
        assert provider.api_endpoint == ""
        assert provider.api_key == ""


class TestSSLConfig:
    """SSLConfig 类测试"""
    
    def test_create_ssl_config(self) -> None:
        """测试创建基本的 SSL 配置"""
        ssl = SSLConfig(
            cert_path="/path/to/cert.pem",
            key_path="/path/to/key.pem"
        )
        
        assert ssl.cert_path == "/path/to/cert.pem"
        assert ssl.key_path == "/path/to/key.pem"
        assert ssl.verify_client is False
        assert ssl.min_version == "TLSv1.2"
    
    def test_ssl_is_enabled(self) -> None:
        """测试 SSL 启用状态"""
        ssl_enabled = SSLConfig(
            cert_path="/path/to/cert.pem",
            key_path="/path/to/key.pem"
        )
        assert ssl_enabled.is_enabled is True
        
        ssl_disabled = SSLConfig()
        assert ssl_disabled.is_enabled is False
        
        ssl_partial = SSLConfig(cert_path="/path/to/cert.pem")
        assert ssl_partial.is_enabled is False
    
    def test_ssl_default_values(self) -> None:
        """测试 SSL 默认值"""
        ssl = SSLConfig()
        
        assert ssl.cert_path is None
        assert ssl.key_path is None
        assert ssl.ca_bundle is None
        assert ssl.verify_client is False
        assert ssl.min_version == "TLSv1.2"


class TestServerConfig:
    """ServerConfig 类测试"""
    
    def test_create_server_config(self) -> None:
        """测试创建基本的服务器配置"""
        server = ServerConfig(
            host="127.0.0.1",
            port=8080,
            workers=4
        )
        
        assert server.host == "127.0.0.1"
        assert server.port == 8080
        assert server.workers == 4
        assert server.max_connections == 1000
        assert server.keep_alive_timeout == 60
        assert server.request_timeout == 30
    
    def test_server_use_ssl(self) -> None:
        """测试服务器 SSL 启用状态"""
        ssl = SSLConfig(cert_path="/cert.pem", key_path="/key.pem")
        server_with_ssl = ServerConfig(
            host="0.0.0.0",
            port=443,
            ssl=ssl
        )
        assert server_with_ssl.use_ssl is True
        
        server_without_ssl = ServerConfig()
        assert server_without_ssl.use_ssl is False
    
    def test_server_listen_address(self) -> None:
        """测试监听地址"""
        server = ServerConfig(host="0.0.0.0", port=8080)
        assert server.listen_address == "0.0.0.0:8080"
    
    def test_server_default_values(self) -> None:
        """测试服务器默认值"""
        server = ServerConfig()
        
        assert server.host == "0.0.0.0"
        assert server.port == 8080
        assert server.workers == 4
        assert server.ssl is None


class TestConfig:
    """Config 类测试"""
    
    def test_create_default_config(self) -> None:
        """测试创建默认配置"""
        config = Config.create_default()
        
        assert config.app_name == "ai_tunnel"
        assert config.debug is False
        assert config.log_level == "INFO"
        assert config.server is not None
        assert config.server.port == 8080
    
    def test_config_with_providers(self) -> None:
        """测试带提供商的配置"""
        provider1 = Provider(
            name="openai",
            api_endpoint="https://api.openai.com",
            api_key="key1"
        )
        provider2 = Provider(
            name="anthropic",
            api_endpoint="https://api.anthropic.com",
            api_key="key2",
            enabled=False
        )
        
        config = Config(
            app_name="test_app",
            providers={"openai": provider1, "anthropic": provider2}
        )
        
        assert config.get_provider("openai") == provider1
        assert config.get_provider("anthropic") == provider2
        assert config.get_provider("nonexistent") is None
    
    def test_config_get_enabled_providers(self) -> None:
        """测试获取已启用的提供商"""
        providers = {
            "provider1": Provider(
                name="p1",
                api_endpoint="https://api.p1.com",
                api_key="key1",
                enabled=True
            ),
            "provider2": Provider(
                name="p2",
                api_endpoint="https://api.p2.com",
                api_key="key2",
                enabled=False
            ),
            "provider3": Provider(
                name="p3",
                api_endpoint="https://api.p3.com",
                api_key="key3",
                enabled=True
            ),
        }
        
        config = Config(providers=providers)
        enabled = config.get_enabled_providers()
        
        assert len(enabled) == 2
        assert all(p.enabled for p in enabled)
    
    def test_config_default_values(self) -> None:
        """测试配置默认值"""
        config = Config()
        
        assert config.app_name == "ai_tunnel"
        assert config.debug is False
        assert config.log_level == "INFO"
        assert config.providers == {}
        assert config.server is None


class TestConfigIntegration:
    """配置集成测试"""
    
    def test_full_config_creation(self, tmp_path: Path) -> None:
        """测试完整的配置创建"""
        # 创建临时证书文件
        cert_file = tmp_path / "cert.pem"
        key_file = tmp_path / "key.pem"
        cert_file.touch()
        key_file.touch()
        
        # 创建 SSL 配置
        ssl = SSLConfig(
            cert_path=str(cert_file),
            key_path=str(key_file),
            min_version="TLSv1.3"
        )
        
        # 创建服务器配置
        server = ServerConfig(
            host="0.0.0.0",
            port=443,
            workers=8,
            ssl=ssl
        )
        
        # 创建提供商配置
        provider = Provider(
            name="openai",
            api_endpoint="https://api.openai.com",
            api_key="sk-test",
            models={"gpt-4": "gpt-4-turbo"},
            timeout=60
        )
        
        # 创建完整配置
        config = Config(
            app_name="ai_tunnel_prod",
            debug=True,
            log_level="DEBUG",
            server=server,
            providers={"openai": provider}
        )
        
        # 验证配置
        assert config.app_name == "ai_tunnel_prod"
        assert config.debug is True
        assert config.log_level == "DEBUG"
        assert config.server.use_ssl is True
        assert config.server.ssl.min_version == "TLSv1.3"
        assert len(config.get_enabled_providers()) == 1
