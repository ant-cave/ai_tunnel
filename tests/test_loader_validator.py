"""
配置加载器和验证器单元测试
"""
import pytest
from pathlib import Path
from src.config.loader import ConfigLoader
from src.config.validator import ConfigValidator, ValidationError
from src.models.config import Config, Provider, ServerConfig, SSLConfig


class TestConfigLoader:
    """ConfigLoader 类测试"""
    
    def test_load_from_dict(self) -> None:
        """测试从字典加载配置"""
        config_dict = {
            "app_name": "test_app",
            "debug": True,
            "log_level": "DEBUG",
            "server": {
                "host": "127.0.0.1",
                "port": 9000,
                "workers": 2
            }
        }
        
        loader = ConfigLoader()
        config = loader.load_from_dict(config_dict)
        
        assert config.app_name == "test_app"
        assert config.debug is True
        assert config.log_level == "DEBUG"
        assert config.server is not None
        assert config.server.host == "127.0.0.1"
        assert config.server.port == 9000
    
    def test_load_from_file(self, tmp_path: Path) -> None:
        """测试从文件加载配置"""
        # 创建临时配置文件
        config_file = tmp_path / "config.toml"
        config_content = """
app_name = "file_test_app"
debug = false
log_level = "WARNING"

[server]
host = "0.0.0.0"
port = 8888
workers = 4
"""
        config_file.write_text(config_content)
        
        loader = ConfigLoader()
        config = loader.load(str(config_file))
        
        assert config.app_name == "file_test_app"
        assert config.debug is False
        assert config.log_level == "WARNING"
        assert config.server.port == 8888
    
    def test_load_nonexistent_file(self) -> None:
        """测试加载不存在的文件"""
        loader = ConfigLoader()
        
        with pytest.raises(FileNotFoundError):
            loader.load("/nonexistent/path/config.toml")
    
    def test_load_without_path(self) -> None:
        """测试未指定路径时加载"""
        loader = ConfigLoader()
        
        with pytest.raises(FileNotFoundError, match="未指定配置文件路径"):
            loader.load()
    
    def test_load_with_providers(self) -> None:
        """测试加载带提供商的配置"""
        config_dict = {
            "app_name": "test",
            "server": {"port": 8080},
            "providers": {
                "openai": {
                    "name": "OpenAI",
                    "api_endpoint": "https://api.openai.com",
                    "api_key": "sk-test",
                    "models": {"gpt-4": "gpt-4-turbo"},
                    "timeout": 60
                }
            }
        }
        
        loader = ConfigLoader()
        config = loader.load_from_dict(config_dict)
        
        assert "openai" in config.providers
        assert config.providers["openai"].name == "OpenAI"
        assert config.providers["openai"].timeout == 60
    
    def test_load_with_ssl(self, tmp_path: Path) -> None:
        """测试加载带 SSL 配置的配置"""
        # 创建临时证书文件
        cert_file = tmp_path / "cert.pem"
        key_file = tmp_path / "key.pem"
        cert_file.touch()
        key_file.touch()
        
        config_dict = {
            "app_name": "ssl_test",
            "server": {
                "port": 443,
                "ssl": {
                    "cert_path": str(cert_file),
                    "key_path": str(key_file),
                    "verify_client": True,
                    "min_version": "TLSv1.3"
                }
            }
        }
        
        loader = ConfigLoader()
        config = loader.load_from_dict(config_dict)
        
        assert config.server is not None
        assert config.server.use_ssl is True
        assert config.server.ssl.verify_client is True
        assert config.server.ssl.min_version == "TLSv1.3"
    
    def test_validate_config(self) -> None:
        """测试配置验证"""
        config_dict = {
            "app_name": "test",
            "providers": {
                "openai": {
                    "api_endpoint": "https://api.openai.com",
                    "api_key": "sk-test"
                }
            }
        }
        
        loader = ConfigLoader()
        loader.load_from_dict(config_dict)
        
        assert loader.validate() is True
    
    def test_validate_missing_endpoint(self) -> None:
        """测试验证缺少 API 端点"""
        config_dict = {
            "app_name": "test",
            "providers": {
                "openai": {
                    "api_key": "sk-test"
                }
            }
        }
        
        loader = ConfigLoader()
        loader.load_from_dict(config_dict)
        
        with pytest.raises(ValueError, match="缺少 api_endpoint 配置"):
            loader.validate()
    
    def test_get_raw_config(self) -> None:
        """测试获取原始配置"""
        config_dict = {"app_name": "test", "debug": True}
        
        loader = ConfigLoader()
        loader.load_from_dict(config_dict)
        
        raw = loader.get_raw_config()
        assert raw == config_dict


class TestConfigValidator:
    """ConfigValidator 类测试"""
    
    def test_validate_valid_config(self) -> None:
        """测试验证有效的配置"""
        config = Config.create_default()
        
        validator = ConfigValidator(config)
        assert validator.validate() is True
    
    def test_validate_invalid_log_level(self) -> None:
        """测试验证无效的日志级别"""
        config = Config(log_level="INVALID")
        
        validator = ConfigValidator(config)
        is_valid, errors = validator.validate_safe()
        
        assert is_valid is False
        assert any("无效的日志级别" in e for e in errors)
    
    def test_validate_invalid_port(self) -> None:
        """测试验证无效的端口号"""
        config = Config(
            server=ServerConfig(host="0.0.0.0", port=0)
        )
        
        validator = ConfigValidator(config)
        is_valid, errors = validator.validate_safe()
        
        assert is_valid is False
        assert any("端口号" in e for e in errors)
    
    def test_validate_invalid_workers(self) -> None:
        """测试验证无效的工作进程数"""
        config = Config(
            server=ServerConfig(host="0.0.0.0", port=8080, workers=0)
        )
        
        validator = ConfigValidator(config)
        is_valid, errors = validator.validate_safe()
        
        assert is_valid is False
        assert any("工作进程数" in e for e in errors)
    
    def test_validate_invalid_provider_endpoint(self) -> None:
        """测试验证无效的提供商端点"""
        provider = Provider(
            name="test",
            api_endpoint="",  # 空端点
            api_key="key"
        )
        config = Config(providers={"test": provider})
        
        validator = ConfigValidator(config)
        is_valid, errors = validator.validate_safe()
        
        assert is_valid is False
        assert any("API 端点不能为空" in e for e in errors)
    
    def test_validate_invalid_provider_url_format(self) -> None:
        """测试验证无效的 URL 格式"""
        provider = Provider(
            name="test",
            api_endpoint="not-a-url",  # 无效的 URL
            api_key="key"
        )
        config = Config(providers={"test": provider})
        
        validator = ConfigValidator(config)
        is_valid, errors = validator.validate_safe()
        
        assert is_valid is False
        assert any("必须是有效的 URL" in e for e in errors)
    
    def test_validate_ssl_nonexistent_cert(self, tmp_path: Path) -> None:
        """测试验证不存在的证书文件"""
        ssl = SSLConfig(
            cert_path=str(tmp_path / "nonexistent.pem"),
            key_path=str(tmp_path / "key.pem")
        )
        config = Config(
            server=ServerConfig(
                host="0.0.0.0",
                port=443,
                ssl=ssl
            )
        )
        
        validator = ConfigValidator(config)
        is_valid, errors = validator.validate_safe()
        
        assert is_valid is False
        assert any("证书文件不存在" in e for e in errors)
    
    def test_validate_ssl_invalid_tls_version(self, tmp_path: Path) -> None:
        """测试验证无效的 TLS 版本"""
        # 创建临时文件
        cert_file = tmp_path / "cert.pem"
        key_file = tmp_path / "key.pem"
        cert_file.touch()
        key_file.touch()
        
        ssl = SSLConfig(
            cert_path=str(cert_file),
            key_path=str(key_file),
            min_version="TLSv1.0"  # 无效的版本
        )
        config = Config(
            server=ServerConfig(ssl=ssl)
        )
        
        validator = ConfigValidator(config)
        is_valid, errors = validator.validate_safe()
        
        assert is_valid is False
        assert any("无效的 TLS 版本" in e for e in errors)
    
    def test_validate_raise_exception(self) -> None:
        """测试验证抛出异常"""
        config = Config(log_level="INVALID")
        
        validator = ConfigValidator(config)
        
        with pytest.raises(ValidationError, match="配置验证失败"):
            validator.validate()
    
    def test_get_errors(self) -> None:
        """测试获取错误列表"""
        config = Config(log_level="INVALID")
        
        validator = ConfigValidator(config)
        validator.validate_safe()
        
        errors = validator.get_errors()
        assert len(errors) > 0
    
    def test_classmethod_validate(self) -> None:
        """测试类方法验证"""
        config = Config.create_default()
        
        assert ConfigValidator.validate_config(config) is True


class TestConfigLoaderValidatorIntegration:
    """加载器和验证器集成测试"""
    
    def test_load_and_validate(self, tmp_path: Path) -> None:
        """测试加载并验证配置"""
        # 创建临时配置文件
        config_file = tmp_path / "config.toml"
        config_content = """
app_name = "integration_test"
debug = true
log_level = "DEBUG"

[server]
host = "127.0.0.1"
port = 9999
workers = 2

[providers.openai]
name = "OpenAI"
api_endpoint = "https://api.openai.com"
api_key = "sk-test-key"
timeout = 60
"""
        config_file.write_text(config_content)
        
        # 加载配置
        loader = ConfigLoader()
        config = loader.load(str(config_file))
        
        # 验证配置
        validator = ConfigValidator(config)
        assert validator.validate() is True
    
    def test_load_invalid_and_validate(self, tmp_path: Path) -> None:
        """测试加载无效配置并验证"""
        config_file = tmp_path / "config.toml"
        config_content = """
app_name = "invalid_test"
log_level = "INVALID_LEVEL"

[server]
host = "0.0.0.0"
port = 99999

[providers.test]
api_endpoint = "not-a-url"
api_key = "key"
"""
        config_file.write_text(config_content)
        
        loader = ConfigLoader()
        config = loader.load(str(config_file))
        
        validator = ConfigValidator(config)
        is_valid, errors = validator.validate_safe()
        
        assert is_valid is False
        assert len(errors) > 0
    
    def test_full_workflow(self, tmp_path: Path) -> None:
        """测试完整的工作流程"""
        # 创建临时证书文件
        cert_file = tmp_path / "cert.pem"
        key_file = tmp_path / "key.pem"
        cert_file.touch()
        key_file.touch()
        
        # 使用正斜杠路径（TOML 标准格式）
        cert_path = cert_file.as_posix()
        key_path = key_file.as_posix()
        
        # 创建完整的配置文件
        config_file = tmp_path / "full_config.toml"
        config_content = f"""
app_name = "production_app"
debug = false
log_level = "INFO"

[server]
host = "0.0.0.0"
port = 443
workers = 8
max_connections = 2000

[server.ssl]
cert_path = "{cert_path}"
key_path = "{key_path}"
min_version = "TLSv1.3"

[providers.openai]
name = "OpenAI"
api_endpoint = "https://api.openai.com"
api_key = "sk-prod-key"
timeout = 60
retry_attempts = 5

[providers.openai.models]
gpt-4 = "gpt-4-turbo"
gpt-3.5 = "gpt-3.5-turbo"

[providers.anthropic]
name = "Anthropic"
api_endpoint = "https://api.anthropic.com"
api_key = "sk-anthropic-key"
enabled = true
"""
        config_file.write_text(config_content)
        
        # 加载并验证
        loader = ConfigLoader()
        config = loader.load(str(config_file))
        
        # 验证配置完整性
        validator = ConfigValidator(config)
        assert validator.validate() is True
        
        # 验证配置值
        assert config.app_name == "production_app"
        assert config.server.use_ssl is True
        assert len(config.providers) == 2
        assert config.get_provider("openai") is not None
        assert config.get_provider("anthropic") is not None
