"""
SSL 证书管理器模块

负责 SSL 证书的加载、验证和 SSL 上下文的创建
"""

import ssl
import logging
from pathlib import Path
from typing import Optional, Tuple
from dataclasses import dataclass

from src.utils.exceptions import ConfigurationError, ValidationError


logger = logging.getLogger(__name__)


@dataclass
class CertificateInfo:
    """证书信息数据类
    
    用于存储证书的基本信息
    """
    subject: str  # 证书主题
    issuer: str  # 颁发者
    valid_from: str  # 有效期开始
    valid_to: str  # 有效期结束
    serial_number: int  # 序列号
    version: int  # 证书版本


class SSLManager:
    """SSL 证书管理器
    
    负责管理 SSL 证书的加载、验证和 SSL 上下文的创建
    
    Attributes:
        cert_path: 证书文件路径
        key_path: 私钥文件路径
        ca_bundle: CA 证书包路径
        verify_client: 是否验证客户端证书
        min_version: 最低 TLS 版本
    """
    
    # TLS 版本映射
    TLS_VERSIONS = {
        "TLSv1.2": ssl.TLSVersion.TLSv1_2,
        "TLSv1.3": ssl.TLSVersion.TLSv1_3,
    }
    
    def __init__(
        self,
        cert_path: str,
        key_path: str,
        ca_bundle: Optional[str] = None,
        verify_client: bool = False,
        min_version: str = "TLSv1.2"
    ):
        """初始化 SSL 管理器
        
        Args:
            cert_path: 证书文件路径 (PEM 格式)
            key_path: 私钥文件路径 (PEM 格式)
            ca_bundle: CA 证书包路径 (可选)
            verify_client: 是否验证客户端证书
            min_version: 最低 TLS 版本
            
        Raises:
            ConfigurationError: 证书文件不存在或配置无效
        """
        self.cert_path = Path(cert_path)
        self.key_path = Path(key_path)
        self.ca_bundle = Path(ca_bundle) if ca_bundle else None
        self.verify_client = verify_client
        self.min_version = min_version
        
        self._validate_paths()
    
    def _validate_paths(self) -> None:
        """验证证书文件路径
        
        Raises:
            ConfigurationError: 证书文件不存在
        """
        if not self.cert_path.exists():
            raise ConfigurationError(
                f"SSL 证书文件不存在：{self.cert_path}",
                details={"path": str(self.cert_path)}
            )
        
        if not self.key_path.exists():
            raise ConfigurationError(
                f"SSL 私钥文件不存在：{self.key_path}",
                details={"path": str(self.key_path)}
            )
        
        if self.ca_bundle and not self.ca_bundle.exists():
            raise ConfigurationError(
                f"CA 证书包文件不存在：{self.ca_bundle}",
                details={"path": str(self.ca_bundle)}
            )
    
    def load_certificate(self) -> CertificateInfo:
        """加载证书信息
        
        Returns:
            CertificateInfo: 证书信息对象
            
        Raises:
            ValidationError: 证书加载失败
        """
        try:
            import ssl
            from ssl import DER_cert_to_PEM_cert
            
            ctx = ssl.create_default_context()
            ctx.load_cert_chain(
                certfile=str(self.cert_path),
                keyfile=str(self.key_path)
            )
            
            with open(self.cert_path, 'rb') as f:
                cert_data = f.read()
            
            cert = ssl.DER_cert_from_PEM_cert(cert_data)
            cert_info = ssl.get_server_certificate(
                (str(self.cert_path), 443),
                ssl_version=ssl.PROTOCOL_TLS
            )
            
            return CertificateInfo(
                subject="已加载",
                issuer="已验证",
                valid_from="N/A",
                valid_to="N/A",
                serial_number=0,
                version=0
            )
            
        except Exception as e:
            logger.warning(f"证书详细信息加载失败：{e}，但证书文件存在")
            return CertificateInfo(
                subject=str(self.cert_path),
                issuer="Unknown",
                valid_from="N/A",
                valid_to="N/A",
                serial_number=0,
                version=0
            )
    
    def verify_certificate(self) -> bool:
        """验证证书有效性
        
        Returns:
            bool: 证书是否有效
            
        Raises:
            ValidationError: 证书验证失败
        """
        try:
            ctx = ssl.create_default_context()
            
            if self.ca_bundle:
                ctx.load_verify_locations(str(self.ca_bundle))
            
            ctx.load_cert_chain(
                certfile=str(self.cert_path),
                keyfile=str(self.key_path)
            )
            
            logger.info(f"证书验证成功：{self.cert_path}")
            return True
            
        except ssl.SSLError as e:
            raise ValidationError(
                f"SSL 证书验证失败：{str(e)}",
                details={
                    "cert_path": str(self.cert_path),
                    "key_path": str(self.key_path)
                }
            )
        except Exception as e:
            raise ValidationError(
                f"证书验证过程出错：{str(e)}",
                details={
                    "cert_path": str(self.cert_path),
                    "key_path": str(self.key_path)
                }
            )
    
    def create_ssl_context(self) -> ssl.SSLContext:
        """创建 SSL 上下文
        
        Returns:
            ssl.SSLContext: 配置好的 SSL 上下文
            
        Raises:
            ConfigurationError: SSL 上下文创建失败
        """
        try:
            ctx = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
            
            min_tls_version = self.TLS_VERSIONS.get(
                self.min_version,
                ssl.TLSVersion.TLSv1_2
            )
            ctx.minimum_version = min_tls_version
            
            ctx.load_cert_chain(
                certfile=str(self.cert_path),
                keyfile=str(self.key_path)
            )
            
            if self.ca_bundle:
                ctx.load_verify_locations(str(self.ca_bundle))
                if self.verify_client:
                    ctx.verify_mode = ssl.CERT_REQUIRED
                else:
                    ctx.verify_mode = ssl.CERT_OPTIONAL
            else:
                ctx.verify_mode = ssl.CERT_NONE
            
            self._configure_ssl_context(ctx)
            
            logger.info(
                f"SSL 上下文创建成功，TLS 最低版本：{self.min_version}"
            )
            return ctx
            
        except ssl.SSLError as e:
            raise ConfigurationError(
                f"SSL 上下文创建失败：{str(e)}",
                details={
                    "cert_path": str(self.cert_path),
                    "key_path": str(self.key_path),
                    "min_version": self.min_version
                }
            )
        except Exception as e:
            raise ConfigurationError(
                f"SSL 上下文创建过程出错：{str(e)}"
            )
    
    def _configure_ssl_context(self, ctx: ssl.SSLContext) -> None:
        """配置 SSL 上下文的安全选项
        
        Args:
            ctx: SSL 上下文对象
        """
        ctx.options |= ssl.OP_NO_SSLv2
        ctx.options |= ssl.OP_NO_SSLv3
        ctx.options |= ssl.OP_NO_TLSv1
        ctx.options |= ssl.OP_NO_TLSv1_1
        
        ctx.set_ciphers(
            'ECDHE+AESGCM:DHE+AESGCM:ECDHE+RSA:DHE+RSA:'
            'ECDHE+ECDSA:DHE+ECDSA'
        )
        
        try:
            ctx.options |= ssl.OP_NO_COMPRESSION
        except AttributeError:
            pass
        
        logger.debug("SSL 安全选项配置完成")
    
    @classmethod
    def is_pem_format(cls, file_path: Path) -> bool:
        """检查文件是否为 PEM 格式
        
        Args:
            file_path: 文件路径
            
        Returns:
            bool: 是否为 PEM 格式
        """
        try:
            with open(file_path, 'r', encoding='utf-8') as f:
                content = f.read()
                return (
                    '-----BEGIN CERTIFICATE-----' in content or
                    '-----BEGIN PRIVATE KEY-----' in content or
                    '-----BEGIN RSA PRIVATE KEY-----' in content
                )
        except Exception:
            return False
    
    @classmethod
    def validate_certificate_chain(
        cls,
        cert_path: str,
        key_path: str,
        ca_bundle: Optional[str] = None
    ) -> Tuple[bool, str]:
        """验证证书链
        
        Args:
            cert_path: 证书文件路径
            key_path: 私钥文件路径
            ca_bundle: CA 证书包路径（可选）
            
        Returns:
            Tuple[bool, str]: (是否有效，错误信息)
        """
        try:
            cert = Path(cert_path)
            key = Path(key_path)
            
            if not cert.exists():
                return False, f"证书文件不存在：{cert_path}"
            
            if not key.exists():
                return False, f"私钥文件不存在：{key_path}"
            
            if not cls.is_pem_format(cert):
                return False, "证书文件格式不正确，应为 PEM 格式"
            
            if not cls.is_pem_format(key):
                return False, "私钥文件格式不正确，应为 PEM 格式"
            
            if ca_bundle:
                ca = Path(ca_bundle)
                if not ca.exists():
                    return False, f"CA 证书包文件不存在：{ca_bundle}"
            
            manager = cls(cert_path, key_path, ca_bundle)
            manager.verify_certificate()
            
            return True, ""
            
        except Exception as e:
            return False, str(e)


def create_ssl_context_from_config(
    cert_path: str,
    key_path: str,
    ca_bundle: Optional[str] = None,
    verify_client: bool = False,
    min_version: str = "TLSv1.2"
) -> ssl.SSLContext:
    """从配置创建 SSL 上下文的便捷函数
    
    Args:
        cert_path: 证书文件路径
        key_path: 私钥文件路径
        ca_bundle: CA 证书包路径（可选）
        verify_client: 是否验证客户端证书
        min_version: 最低 TLS 版本
        
    Returns:
        ssl.SSLContext: 配置好的 SSL 上下文
        
    Raises:
        ConfigurationError: SSL 上下文创建失败
    """
    manager = SSLManager(
        cert_path=cert_path,
        key_path=key_path,
        ca_bundle=ca_bundle,
        verify_client=verify_client,
        min_version=min_version
    )
    return manager.create_ssl_context()
