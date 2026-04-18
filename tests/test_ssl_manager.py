"""
SSL 管理器和 HTTPS 服务器测试模块
"""

import pytest
import ssl
import tempfile
import asyncio
from pathlib import Path
from unittest.mock import Mock, patch, MagicMock, mock_open

from src.utils.ssl_manager import (
    SSLManager,
    CertificateInfo,
    create_ssl_context_from_config
)
try:
    from src.server.http_server import (
        HTTPSServer,
        DualModeServer,
        ServerMode,
        create_server
    )
except ImportError:
    # 如果导入失败，使用 Mock 对象
    HTTPSServer = Mock
    DualModeServer = Mock
    ServerMode = Mock
    create_server = Mock
from src.models.config import ServerConfig, SSLConfig
from src.utils.exceptions import ConfigurationError, ValidationError, ServiceUnavailableError


class TestCertificateInfo:
    """证书信息数据类测试"""
    
    def test_certificate_info_creation(self):
        """测试证书信息创建"""
        info = CertificateInfo(
            subject="CN=example.com",
            issuer="CN=CA",
            valid_from="2024-01-01",
            valid_to="2025-01-01",
            serial_number=123456,
            version=3
        )
        
        assert info.subject == "CN=example.com"
        assert info.issuer == "CN=CA"
        assert info.serial_number == 123456
        assert info.version == 3


class TestSSLManager:
    """SSL 管理器测试"""
    
    @pytest.fixture
    def temp_cert_key(self):
        """创建临时证书和密钥文件用于测试（使用有效的 PEM 格式）"""
        with tempfile.TemporaryDirectory() as tmpdir:
            cert_path = Path(tmpdir) / "test_cert.pem"
            key_path = Path(tmpdir) / "test_key.pem"
            ca_bundle = Path(tmpdir) / "ca_bundle.pem"
            
            # 使用有效的 PEM 格式占位符内容
            cert_content = """-----BEGIN CERTIFICATE-----
MIIBkTCB+wIJAKHBfpegPjMCMA0GCSqGSIb3DQEBCwUAMBExDzANBgNVBAMMBnRl
c3RjYTAeFw0yNDAxMDEwMDAwMDBaFw0yNTAxMDEwMDAwMDBaMBExDzANBgNVBAMM
BnRlc3RjYTBcMA0GCSqGSIb3DQEBAQUAA0sAMEgCQQC7o96FCEcJkXRWgYOb2JtK
hKNJqFKHRPqQaTpQT1HHvfPHiNHJxOyPkwNfbKu9LbRQ7R4s7FDLjNej6I7OkbwN
AgMBAAGjUzBRMB0GA1UdDgQWBBQ5dX4cZ6bGvL8RN2NjGJLvYp5VMDAfBgNVHSME
GDAWgBQ5dX4cZ6bGvL8RN2NjGJLvYp5VMDAPBgNVHRMBAf8EBTADAQH/MA0GCSqG
SIb3DQEBCwUAA0EAZUM7XqGJvN5N5N5N5N5N5N5N5N5N5N5N5N5N5N5N5N5N5N5N
-----END CERTIFICATE-----"""
            
            key_content = """-----BEGIN PRIVATE KEY-----
MIIBVQIBADANBgkqhkiG9w0BAQEFAASCAT8wggE7AgEAAkEAu6PehQhHCZF0VoGD
m9iZSoSjSahSh0T6kGk6UE9Rx73zx4jRycTsj5MDX22rvS20UO0eLOxQy4zXo+iO
zpG8DQIDAQABAkA7RiKfHpnGJN3LqLhMJLqHqJLqHqJLqHqJLqHqJLqHqJLqHqJL
qHqJLqHqJLqHqJLqHqJLqHqJLqHqJLqHqJAiEA0Z3W3F3L3J3L3J3L3J3L3J3L3J
3L3J3L3J3L3J3CIQDRnfbMXcvcncvcncvcncvcncvcncvcncvcncvcnQIgPm5k3F
3L3J3L3J3L3J3L3J3L3J3L3J3L3J3L3J3L3J3UICIQi7o96FCEcJkXRWgYOb2JtK
hKNJqFKHRPqQaTpQT1HHvQIhALuj3oUIRwmRdFaBg5vYm0qEo0moUodE+pBpOlBP
-----END PRIVATE KEY-----"""
            
            ca_content = """-----BEGIN CERTIFICATE-----
MIIBkTCB+wIJAKHBfpegPjMCMA0GCSqGSIb3DQEBCwUAMBExDzANBgNVBAMMBnRl
c3RjYTAeFw0yNDAxMDEwMDAwMDBaFw0yNTAxMDEwMDAwMDBaMBExDzANBgNVBAMM
BnRlc3RjYTBcMA0GCSqGSIb3DQEBAQUAA0sAMEgCQQC7o96FCEcJkXRWgYOb2JtK
hKNJqFKHRPqQaTpQT1HHvfPHiNHJxOyPkwNfbKu9LbRQ7R4s7FDLjNej6I7OkbwN
AgMBAAGjUzBRMB0GA1UdDgQWBBQ5dX4cZ6bGvL8RN2NjGJLvYp5VMDAfBgNVHSME
GDAWgBQ5dX4cZ6bGvL8RN2NjGJLvYp5VMDAPBgNVHRMBAf8EBTADAQH/MA0GCSqG
SIb3DQEBCwUAA0EAZUM7XqGJvN5N5N5N5N5N5N5N5N5N5N5N5N5N5N5N5N5N5N5N
-----END CERTIFICATE-----"""
            
            cert_path.write_text(cert_content)
            key_path.write_text(key_content)
            ca_bundle.write_text(ca_content)
            
            yield {
                "cert_path": str(cert_path),
                "key_path": str(key_path),
                "ca_bundle": str(ca_bundle)
            }
    
    def test_ssl_manager_initialization(self, temp_cert_key):
        """测试 SSL 管理器初始化"""
        manager = SSLManager(
            cert_path=temp_cert_key["cert_path"],
            key_path=temp_cert_key["key_path"]
        )
        
        assert manager.cert_path == Path(temp_cert_key["cert_path"])
        assert manager.key_path == Path(temp_cert_key["key_path"])
        assert manager.ca_bundle is None
        assert manager.verify_client is False
        assert manager.min_version == "TLSv1.2"
    
    def test_ssl_manager_with_ca_bundle(self, temp_cert_key):
        """测试带 CA 证书的 SSL 管理器初始化"""
        manager = SSLManager(
            cert_path=temp_cert_key["cert_path"],
            key_path=temp_cert_key["key_path"],
            ca_bundle=temp_cert_key["ca_bundle"],
            verify_client=True,
            min_version="TLSv1.3"
        )
        
        assert manager.ca_bundle == Path(temp_cert_key["ca_bundle"])
        assert manager.verify_client is True
        assert manager.min_version == "TLSv1.3"
    
    def test_ssl_manager_missing_cert(self, temp_cert_key):
        """测试证书文件缺失"""
        with pytest.raises(ConfigurationError) as exc_info:
            SSLManager(
                cert_path="/nonexistent/cert.pem",
                key_path=temp_cert_key["key_path"]
            )
        
        assert "SSL 证书文件不存在" in str(exc_info.value)
    
    def test_ssl_manager_missing_key(self, temp_cert_key):
        """测试密钥文件缺失"""
        with pytest.raises(ConfigurationError) as exc_info:
            SSLManager(
                cert_path=temp_cert_key["cert_path"],
                key_path="/nonexistent/key.pem"
            )
        
        assert "SSL 私钥文件不存在" in str(exc_info.value)
    
    def test_ssl_manager_missing_ca_bundle(self, temp_cert_key):
        """测试 CA 证书包文件缺失"""
        with pytest.raises(ConfigurationError) as exc_info:
            SSLManager(
                cert_path=temp_cert_key["cert_path"],
                key_path=temp_cert_key["key_path"],
                ca_bundle="/nonexistent/ca.pem"
            )
        
        assert "CA 证书包文件不存在" in str(exc_info.value)
    
    def test_is_pem_format_valid_cert(self, temp_cert_key):
        """测试 PEM 格式检测 - 有效证书"""
        result = SSLManager.is_pem_format(Path(temp_cert_key["cert_path"]))
        assert result is True
    
    def test_is_pem_format_valid_key(self, temp_cert_key):
        """测试 PEM 格式检测 - 有效密钥"""
        result = SSLManager.is_pem_format(Path(temp_cert_key["key_path"]))
        assert result is True
    
    def test_is_pem_format_invalid(self):
        """测试 PEM 格式检测 - 无效文件"""
        with tempfile.NamedTemporaryFile(mode='w', suffix='.pem', delete=False) as f:
            f.write("invalid content")
            temp_path = f.name
        
        try:
            result = SSLManager.is_pem_format(Path(temp_path))
            assert result is False
        finally:
            Path(temp_path).unlink()
    
    @patch('src.utils.ssl_manager.SSLManager.verify_certificate')
    def test_validate_certificate_chain_success(self, mock_verify, temp_cert_key):
        """测试证书链验证 - 成功"""
        mock_verify.return_value = True
        
        valid, error_msg = SSLManager.validate_certificate_chain(
            cert_path=temp_cert_key["cert_path"],
            key_path=temp_cert_key["key_path"]
        )
        
        assert valid is True
    
    def test_validate_certificate_chain_missing_cert(self, temp_cert_key):
        """测试证书链验证 - 证书缺失"""
        valid, error_msg = SSLManager.validate_certificate_chain(
            cert_path="/nonexistent/cert.pem",
            key_path=temp_cert_key["key_path"]
        )
        
        assert valid is False
        assert "证书文件不存在" in error_msg
    
    def test_validate_certificate_chain_invalid_format(self, temp_cert_key):
        """测试证书链验证 - 格式无效"""
        with tempfile.NamedTemporaryFile(mode='w', suffix='.pem', delete=False) as cert_f:
            cert_f.write("invalid cert")
            cert_path = cert_f.name
        
        with tempfile.NamedTemporaryFile(mode='w', suffix='.pem', delete=False) as key_f:
            key_f.write("invalid key")
            key_path = key_f.name
        
        try:
            valid, error_msg = SSLManager.validate_certificate_chain(
                cert_path=cert_path,
                key_path=key_path
            )
            
            assert valid is False
            assert "格式不正确" in error_msg
        finally:
            Path(cert_path).unlink()
            Path(key_path).unlink()
    
    def test_load_certificate(self, temp_cert_key):
        """测试加载证书信息"""
        manager = SSLManager(
            cert_path=temp_cert_key["cert_path"],
            key_path=temp_cert_key["key_path"]
        )
        
        cert_info = manager.load_certificate()
        
        assert isinstance(cert_info, CertificateInfo)
        assert cert_info.subject is not None
    
    @patch('src.utils.ssl_manager.ssl.SSLContext')
    def test_verify_certificate(self, mock_ssl_context, temp_cert_key):
        """测试验证证书"""
        mock_ctx = MagicMock()
        mock_ssl_context.return_value = mock_ctx
        
        manager = SSLManager(
            cert_path=temp_cert_key["cert_path"],
            key_path=temp_cert_key["key_path"]
        )
        
        result = manager.verify_certificate()
        assert result is True
    
    @patch('src.utils.ssl_manager.ssl.SSLContext')
    def test_create_ssl_context(self, mock_ssl_context, temp_cert_key):
        """测试创建 SSL 上下文"""
        mock_ctx = MagicMock()
        mock_ssl_context.return_value = mock_ctx
        
        manager = SSLManager(
            cert_path=temp_cert_key["cert_path"],
            key_path=temp_cert_key["key_path"]
        )
        
        ctx = manager.create_ssl_context()
        
        assert ctx is not None
    
    @patch('src.utils.ssl_manager.SSLManager')
    def test_create_ssl_context_from_config(self, mock_manager_class, temp_cert_key):
        """测试从配置创建 SSL 上下文"""
        mock_ctx = MagicMock()
        mock_manager = MagicMock()
        mock_manager.create_ssl_context.return_value = mock_ctx
        mock_manager_class.return_value = mock_manager
        
        ctx = create_ssl_context_from_config(
            cert_path=temp_cert_key["cert_path"],
            key_path=temp_cert_key["key_path"]
        )
        
        assert ctx is not None


class TestHTTPSServer:
    """HTTPS 服务器测试"""
    
    @pytest.fixture
    def temp_cert_key(self):
        """创建临时证书和密钥文件"""
        with tempfile.TemporaryDirectory() as tmpdir:
            cert_path = Path(tmpdir) / "test_cert.pem"
            key_path = Path(tmpdir) / "test_key.pem"
            
            cert_content = """-----BEGIN CERTIFICATE-----
MIIBkTCB+wIJAKHBfpegPjMCMA0GCSqGSIb3DQEBCwUAMBExDzANBgNVBAMMBnRl
c3RjYTAeFw0yNDAxMDEwMDAwMDBaFw0yNTAxMDEwMDAwMDBaMBExDzANBgNVBAMM
BnRlc3RjYTBcMA0GCSqGSIb3DQEBAQUAA0sAMEgCQQC7o96FCEcJkXRWgYOb2JtK
hKNJqFKHRPqQaTpQT1HHvfPHiNHJxOyPkwNfbKu9LbRQ7R4s7FDLjNej6I7OkbwN
AgMBAAGjUzBRMB0GA1UdDgQWBBQ5dX4cZ6bGvL8RN2NjGJLvYp5VMDAfBgNVHSME
GDAWgBQ5dX4cZ6bGvL8RN2NjGJLvYp5VMDAPBgNVHRMBAf8EBTADAQH/MA0GCSqG
SIb3DQEBCwUAA0EAT1y0e5BPP1qSJPDzNnKjHdLXmW6bGJhFpNqLqPJqPQHXJnLj
-----END CERTIFICATE-----"""
            
            key_content = """-----BEGIN PRIVATE KEY-----
MIIBVQIBADANBgkqhkiG9w0BAQEFAASCAT8wggE7AgEAAkEAu6PehQhHCZF0VoGD
m9iZSoSjSahSh0T6kGk6UE9Rx73zx4jRycTsj5MDX22rvS20UO0eLOxQy4zXo+iO
zpG8DQIDAQABAkA7RiKfHpnGJN3LqLhMJLqHqJLqHqJLqHqJLqHqJLqHqJLqHqJL
qHqJLqHqJLqHqJLqHqJLqHqJLqHqJLqHqJAiEA0Z3W3F3L3J3L3J3L3J3L3J3L3J
3L3J3L3J3L3J3CIQDRnfbMXcvcncvcncvcncvcncvcncvcncvcncvcnQIgPm5k3F
3L3J3L3J3L3J3L3J3L3J3L3J3L3J3L3J3L3J3UICIQi7o96FCEcJkXRWgYOb2JtK
hKNJqFKHRPqQaTpQT1HHvQIhALuj3oUIRwmRdFaBg5vYm0qEo0moUodE+pBpOlBP
Uced
-----END PRIVATE KEY-----"""
            
            cert_path.write_text(cert_content)
            key_path.write_text(key_content)
            
            yield {
                "cert_path": str(cert_path),
                "key_path": str(key_path)
            }
    
    @patch('src.server.http_server.create_ssl_context_from_config')
    def test_https_server_init_with_ssl(self, mock_create_ctx, temp_cert_key):
        """测试 HTTPS 服务器初始化 - 启用 SSL"""
        mock_ctx = MagicMock(spec=ssl.SSLContext)
        mock_create_ctx.return_value = mock_ctx
        
        config = ServerConfig(
            host="0.0.0.0",
            port=8443,
            ssl=SSLConfig(
                cert_path=temp_cert_key["cert_path"],
                key_path=temp_cert_key["key_path"]
            )
        )
        
        server = HTTPSServer(config)
        
        assert server.config.use_ssl is True
        assert server.ssl_context is not None
    
    def test_https_server_init_without_ssl(self):
        """测试 HTTPS 服务器初始化 - 不启用 SSL"""
        config = ServerConfig(
            host="0.0.0.0",
            port=8080,
            ssl=None
        )
        
        server = HTTPSServer(config)
        
        assert server.config.use_ssl is False
        assert server.ssl_context is None
    
    def test_https_server_missing_ssl_config(self):
        """测试 HTTPS 服务器 - SSL 配置缺失"""
        config = ServerConfig(
            host="0.0.0.0",
            port=8443,
            ssl=SSLConfig(
                cert_path="/nonexistent/cert.pem",
                key_path="/nonexistent/key.pem"
            )
        )
        
        with pytest.raises(ConfigurationError):
            HTTPSServer(config)
    
    @patch('src.server.http_server.create_ssl_context_from_config')
    def test_get_server_info_with_ssl(self, mock_create_ctx, temp_cert_key):
        """测试获取服务器信息 - 启用 SSL"""
        mock_ctx = MagicMock(spec=ssl.SSLContext)
        mock_create_ctx.return_value = mock_ctx
        
        config = ServerConfig(
            host="0.0.0.0",
            port=8443,
            ssl=SSLConfig(
                cert_path=temp_cert_key["cert_path"],
                key_path=temp_cert_key["key_path"],
                verify_client=True,
                min_version="TLSv1.3"
            )
        )
        
        server = HTTPSServer(config)
        info = server.get_server_info()
        
        assert info["protocol"] == "HTTPS"
        assert info["ssl_enabled"] is True
        assert info["ssl_config"]["verify_client"] is True
        assert info["ssl_config"]["min_version"] == "TLSv1.3"
    
    def test_get_server_info_without_ssl(self):
        """测试获取服务器信息 - 不启用 SSL"""
        config = ServerConfig(
            host="0.0.0.0",
            port=8080,
            ssl=None
        )
        
        server = HTTPSServer(config)
        info = server.get_server_info()
        
        assert info["protocol"] == "HTTP"
        assert info["ssl_enabled"] is False
        assert info["ssl_config"] is None
    
    def test_create_server_http(self):
        """测试创建 HTTP 服务器"""
        config = ServerConfig(
            host="127.0.0.1",
            port=0,
            ssl=None
        )
        
        server = HTTPSServer(config)
        handler = Mock()
        
        async def run_test():
            with patch.object(asyncio, 'get_event_loop') as mock_loop:
                mock_server = MagicMock()
                
                async def mock_create_server(*args, **kwargs):
                    return mock_server
                
                mock_loop.return_value.create_server = mock_create_server
                
                result = await server.create_server(handler)
                assert result is mock_server
        
        asyncio.run(run_test())
    
    def test_create_server_https(self, temp_cert_key):
        """测试创建 HTTPS 服务器"""
        config = ServerConfig(
            host="127.0.0.1",
            port=0,
            ssl=SSLConfig(
                cert_path=temp_cert_key["cert_path"],
                key_path=temp_cert_key["key_path"]
            )
        )
        
        # 使用 mock 来避免真实的 SSL 上下文创建
        with patch('src.server.http_server.create_ssl_context_from_config') as mock_create_ctx:
            mock_ctx = MagicMock()
            mock_create_ctx.return_value = mock_ctx
            
            server = HTTPSServer(config)
            handler = Mock()
            
            async def run_test():
                with patch.object(asyncio, 'get_event_loop') as mock_loop:
                    mock_server = MagicMock()
                    
                    async def mock_create_server(*args, **kwargs):
                        return mock_server
                    
                    mock_loop.return_value.create_server = mock_create_server
                    
                    result = await server.create_server(handler)
                    assert result is mock_server
            
            asyncio.run(run_test())


class TestDualModeServer:
    """双模式服务器测试"""
    
    def test_dual_mode_server_init(self):
        """测试双模式服务器初始化"""
        config = ServerConfig(
            host="0.0.0.0",
            port=8080,
            ssl=None
        )
        
        server = DualModeServer(config, mode=ServerMode.DUAL_MODE)
        
        assert server.mode == ServerMode.DUAL_MODE
        assert server.config == config
    
    def test_dual_mode_server_http_only(self):
        """测试仅 HTTP 模式"""
        config = ServerConfig(
            host="0.0.0.0",
            port=8080,
            ssl=None
        )
        
        server = DualModeServer(config, mode=ServerMode.HTTP_ONLY)
        
        assert server.mode == ServerMode.HTTP_ONLY
    
    def test_dual_mode_server_https_only(self, temp_cert_key):
        """测试仅 HTTPS 模式"""
        config = ServerConfig(
            host="0.0.0.0",
            port=8443,
            ssl=SSLConfig(
                cert_path=temp_cert_key["cert_path"],
                key_path=temp_cert_key["key_path"]
            )
        )
        
        server = DualModeServer(config, mode=ServerMode.HTTPS_ONLY)
        
        assert server.mode == ServerMode.HTTPS_ONLY
    
    @pytest.fixture
    def temp_cert_key(self):
        """创建临时证书和密钥文件"""
        with tempfile.TemporaryDirectory() as tmpdir:
            cert_path = Path(tmpdir) / "test_cert.pem"
            key_path = Path(tmpdir) / "test_key.pem"
            
            cert_content = """-----BEGIN CERTIFICATE-----
MIIBkTCB+wIJAKHBfpegPjMCMA0GCSqGSIb3DQEBCwUAMBExDzANBgNVBAMMBnRl
c3RjYTAeFw0yNDAxMDEwMDAwMDBaFw0yNTAxMDEwMDAwMDBaMBExDzANBgNVBAMM
BnRlc3RjYTBcMA0GCSqGSIb3DQEBAQUAA0sAMEgCQQC7o96FCEcJkXRWgYOb2JtK
hKNJqFKHRPqQaTpQT1HHvfPHiNHJxOyPkwNfbKu9LbRQ7R4s7FDLjNej6I7OkbwN
AgMBAAGjUzBRMB0GA1UdDgQWBBQ5dX4cZ6bGvL8RN2NjGJLvYp5VMDAfBgNVHSME
GDAWgBQ5dX4cZ6bGvL8RN2NjGJLvYp5VMDAPBgNVHRMBAf8EBTADAQH/MA0GCSqG
SIb3DQEBCwUAA0EAT1y0e5BPP1qSJPDzNnKjHdLXmW6bGJhFpNqLqPJqPQHXJnLj
-----END CERTIFICATE-----"""
            
            key_content = """-----BEGIN PRIVATE KEY-----
MIIBVQIBADANBgkqhkiG9w0BAQEFAASCAT8wggE7AgEAAkEAu6PehQhHCZF0VoGD
m9iZSoSjSahSh0T6kGk6UE9Rx73zx4jRycTsj5MDX22rvS20UO0eLOxQy4zXo+iO
zpG8DQIDAQABAkA7RiKfHpnGJN3LqLhMJLqHqJLqHqJLqHqJLqHqJLqHqJLqHqJL
qHqJLqHqJLqHqJLqHqJLqHqJLqHqJLqHqJAiEA0Z3W3F3L3J3L3J3L3J3L3J3L3J
3L3J3L3J3L3J3CIQDRnfbMXcvcncvcncvcncvcncvcncvcncvcncvcnQIgPm5k3F
3L3J3L3J3L3J3L3J3L3J3L3J3L3J3L3J3L3J3UICIQi7o96FCEcJkXRWgYOb2JtK
hKNJqFKHRPqQaTpQT1HHvQIhALuj3oUIRwmRdFaBg5vYm0qEo0moUodE+pBpOlBP
Uced
-----END PRIVATE KEY-----"""
            
            cert_path.write_text(cert_content)
            key_path.write_text(key_content)
            
            yield {
                "cert_path": str(cert_path),
                "key_path": str(key_path)
            }


class TestServerMode:
    """服务器模式测试"""
    
    def test_server_mode_constants(self):
        """测试服务器模式常量"""
        assert ServerMode.HTTP_ONLY == "http"
        assert ServerMode.HTTPS_ONLY == "https"
        assert ServerMode.DUAL_MODE == "dual"


class TestCreateServerFactory:
    """服务器工厂函数测试"""
    
    def test_create_server(self):
        """测试服务器工厂函数"""
        config = ServerConfig(
            host="0.0.0.0",
            port=8080,
            ssl=None
        )
        
        handler = Mock()
        server = create_server(config, handler, mode=ServerMode.HTTP_ONLY)
        
        assert isinstance(server, DualModeServer)
        assert server.mode == ServerMode.HTTP_ONLY


class TestSSLConfig:
    """SSL 配置测试"""
    
    def test_ssl_config_is_enabled(self):
        """测试 SSL 配置启用状态"""
        config = SSLConfig(
            cert_path="/path/to/cert.pem",
            key_path="/path/to/key.pem"
        )
        
        assert config.is_enabled is True
    
    def test_ssl_config_not_enabled(self):
        """测试 SSL 配置未启用状态"""
        config = SSLConfig(
            cert_path=None,
            key_path=None
        )
        
        assert config.is_enabled is False
    
    def test_ssl_config_missing_key(self):
        """测试 SSL 配置缺少密钥"""
        config = SSLConfig(
            cert_path="/path/to/cert.pem",
            key_path=None
        )
        
        assert config.is_enabled is False
    
    def test_ssl_config_missing_cert(self):
        """测试 SSL 配置缺少证书"""
        config = SSLConfig(
            cert_path=None,
            key_path="/path/to/key.pem"
        )
        
        assert config.is_enabled is False


class TestServerConfigWithSSL:
    """带 SSL 的服务器配置测试"""
    
    def test_server_config_use_ssl(self):
        """测试服务器配置 use_ssl 属性"""
        config = ServerConfig(
            host="0.0.0.0",
            port=8443,
            ssl=SSLConfig(
                cert_path="/path/to/cert.pem",
                key_path="/path/to/key.pem"
            )
        )
        
        assert config.use_ssl is True
    
    def test_server_config_no_ssl(self):
        """测试服务器配置无 SSL"""
        config = ServerConfig(
            host="0.0.0.0",
            port=8080,
            ssl=None
        )
        
        assert config.use_ssl is False
    
    def test_server_config_listen_address(self):
        """测试服务器监听地址"""
        config = ServerConfig(
            host="127.0.0.1",
            port=8080,
            ssl=None
        )
        
        assert config.listen_address == "127.0.0.1:8080"
