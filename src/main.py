"""
AI Tunnel 主程序模块

负责应用程序的启动、配置加载和生命周期管理
整合所有模块：HTTP 服务器、路由、端点处理等
"""

import asyncio
import logging
import signal
from typing import Optional, List
from pathlib import Path

from src.config.settings import Settings
from src.utils.logger import setup_logger, get_logger
from src.utils.exceptions import AITunnelError, ConfigurationError
from src.server.http_server import HTTPServer
from src.server.endpoints import create_endpoint_handlers
from src.router.router import AsyncRouter, RouterConfig
from src.router.provider_manager import ProviderConfig, ProviderType


class AITunnel:
    """AI Tunnel 主应用类
    
    负责管理整个应用程序的生命周期，包括：
    - 配置加载和验证
    - 日志初始化
    - HTTP 服务器启动和停止
    - 路由和端点管理
    - 优雅关闭处理
    """
    
    def __init__(self, config_path: Optional[str] = None):
        """初始化 AI Tunnel 应用
        
        Args:
            config_path: 配置文件路径，默认为 None 时使用默认路径
        """
        self.config_path = config_path
        self.settings: Optional[Settings] = None
        self.logger: Optional[logging.Logger] = None
        self.server: Optional[HTTPServer] = None
        self.router: Optional[AsyncRouter] = None
        self._running: bool = False
        self._shutdown_event = asyncio.Event()
        
        self._setup_signal_handlers()
    
    def _setup_signal_handlers(self) -> None:
        """设置信号处理器"""
        try:
            signal.signal(signal.SIGINT, self._signal_handler)
            signal.signal(signal.SIGTERM, self._signal_handler)
        except ValueError:
            pass
    
    def _signal_handler(self, signum, frame) -> None:
        """信号处理函数
        
        Args:
            signum: 信号编号
            frame: 当前帧
        """
        sig_name = signal.Signals(signum).name
        if self.logger:
            self.logger.info(f"接收到信号：{sig_name}，正在关闭服务...")
        self._shutdown_event.set()
    
    async def initialize(self) -> None:
        """初始化应用程序
        
        加载配置、设置日志、初始化各模块
        
        Raises:
            AITunnelError: 初始化失败
        """
        try:
            self.logger = setup_logger(
                name="ai_tunnel",
                level="INFO",
                log_file=None
            )
            
            self.logger.info("开始初始化 AI Tunnel...")
            
            self.settings = self._load_config()
            
            self.logger = setup_logger(
                name="ai_tunnel",
                level=self.settings.log_level,
                log_file=self.settings.log_file
            )
            
            self.router = self._init_router()
            
            await self._init_providers()
            
            self.server = HTTPServer.from_settings(self.settings, self.logger)
            
            self._setup_routes()
            
            self.logger.info("AI Tunnel 初始化成功")
            
        except ConfigurationError as e:
            self._log_error("配置错误", e)
            raise AITunnelError(f"配置加载失败：{str(e)}")
        except Exception as e:
            self._log_error("初始化失败", e)
            raise AITunnelError(f"初始化失败：{str(e)}")
    
    def _load_config(self) -> Settings:
        """加载配置
        
        Returns:
            Settings: 配置对象
        """
        if self.config_path:
            self.logger.info(f"从文件加载配置：{self.config_path}")
            settings = Settings(self.config_path)
        else:
            default_paths = [
                "configs/config.json",
                "config.json",
                Path(__file__).parent.parent / "configs" / "config.json",
            ]
            
            for path in default_paths:
                if Path(path).exists():
                    self.logger.info(f"从默认路径加载配置：{path}")
                    settings = Settings(str(path))
                    break
            else:
                self.logger.warning("未找到配置文件，使用默认配置")
                settings = Settings()
        
        settings.validate()
        self.logger.debug(f"配置加载完成：host={settings.server.host}, port={settings.server.port}")
        
        return settings
    
    def _init_router(self) -> AsyncRouter:
        """初始化路由器
        
        Returns:
            AsyncRouter: 异步路由器
        """
        router_config = RouterConfig(
            default_timeout=self.settings.server.request_timeout,
            max_retries=3,
            enable_fallback=True,
            enable_health_check=True,
            log_requests=True,
            log_responses=False,
        )
        
        router = AsyncRouter(router_config)
        self.logger.info("路由器初始化成功")
        
        return router
    
    async def _init_providers(self) -> None:
        """初始化提供者
        
        从配置加载所有提供者，并自动获取模型列表
        如果自动获取失败，会启动后台任务持续尝试获取
        """
        self.logger.info("初始化提供者...")
        
        provider_configs = self._load_provider_configs()
        
        self.logger.info(f"加载了 {len(provider_configs)} 个提供者配置")
        
        for name, config in provider_configs.items():
            try:
                self.logger.info(f"处理提供者：{name}, 已有模型数：{len(config.models) if config.models else 0}")
                
                # 自动获取模型列表
                if not config.models:
                    self.logger.info(f"正在从 {name} 获取模型列表...")
                    config.models = await self._fetch_models_from_provider(config)
                    if config.models:
                        self.logger.info(f"从 {name} 获取到 {len(config.models)} 个模型")
                    else:
                        self.logger.warning(f"未能从 {name} 获取模型列表，将启动后台任务持续获取")
                        # 启动后台任务持续获取模型列表
                        asyncio.create_task(self._background_fetch_models(config))
                else:
                    self.logger.info(f"提供者 {name} 已有配置的模型列表，跳过自动获取")
                
                self.router.add_provider(config)
                self.logger.info(f"添加提供者：{name} 成功")
            except Exception as e:
                self.logger.exception(f"添加提供者 {name} 失败：{e}")
        
        self.logger.info("提供者初始化完成")
    
    async def _background_fetch_models(self, config: ProviderConfig, interval: int = 10, max_attempts: int = 30):
        """后台持续获取模型列表
        
        Args:
            config: 提供者配置
            interval: 重试间隔（秒）
            max_attempts: 最大尝试次数
        """
        import asyncio
        
        self.logger.info(f"启动后台任务：持续从 {config.name} 获取模型列表，间隔 {interval} 秒")
        
        for attempt in range(max_attempts):
            try:
                # 等待一段时间
                await asyncio.sleep(interval)
                
                # 尝试获取模型列表
                models = await self._fetch_models_from_provider(config)
                
                if models:
                    # 成功获取，更新配置
                    config.models = models
                    self.router.update_provider_models(config.name, models)
                    self.logger.info(f"后台任务成功从 {config.name} 获取到 {len(models)} 个模型")
                    return  # 成功后退出
                    
            except Exception as e:
                self.logger.warning(f"后台任务从 {config.name} 获取模型列表失败 (尝试 {attempt + 1}/{max_attempts}): {e}")
        
        self.logger.error(f"后台任务从 {config.name} 获取模型列表：所有 {max_attempts} 次尝试都失败")
    
    def _load_provider_configs(self) -> dict:
        """加载提供者配置
        
        Returns:
            dict: 提供者配置字典
        """
        providers = {}
        
        try:
            from src.config.config_loader import ConfigLoader
            
            if self.config_path and Path(self.config_path).exists():
                loader = ConfigLoader(self.config_path)
                data = loader.load()
                
                if "providers" in data:
                    for name, config in data["providers"].items():
                        # 处理模型配置，确保是列表格式
                        models = config.get("models", {})
                        if isinstance(models, dict):
                            # 如果是字典，使用字典的键作为模型名称
                            model_list = list(models.keys())
                        elif isinstance(models, list):
                            # 如果已经是列表，直接使用
                            model_list = models
                        else:
                            # 其他情况，使用空列表
                            model_list = []
                        
                        provider_config = ProviderConfig(
                            name=config.get("name", name),
                            provider_type=ProviderType.OPENAI,
                            base_url=config.get("api_endpoint", ""),
                            api_key=config.get("api_key", ""),
                            models=model_list,
                            enabled=config.get("enabled", True),
                        )
                        providers[name] = provider_config
        except Exception as e:
            self.logger.warning(f"加载提供者配置失败：{e}")
        
        return providers
    
    async def _fetch_models_from_provider(self, config: ProviderConfig) -> list:
        """从提供者 API 获取模型列表
        
        Args:
            config: 提供者配置
            
        Returns:
            list: 模型名称列表
        """
        import requests
        import urllib3
        
        # 禁用 SSL 警告
        urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)
        
        # 最多重试 3 次
        for attempt in range(3):
            try:
                url = f"{config.base_url}/v1/models"
                headers = {
                    "Authorization": f"Bearer {config.api_key}",
                    "Content-Type": "application/json"
                }
                
                self.logger.info(f"请求 {url} 获取模型列表 (尝试 {attempt + 1}/3)")
                
                # 使用 requests 库，禁用 SSL 验证
                response = requests.get(
                    url,
                    headers=headers,
                    timeout=30,
                    verify=False,  # 禁用 SSL 验证
                )
                
                self.logger.info(f"响应状态码：{response.status_code}")
                
                if response.status_code == 200:
                    data = response.json()
                    if "data" in data:
                        # 提取所有模型的 ID
                        models = [model["id"] for model in data["data"] if "id" in model]
                        self.logger.info(f"获取到 {len(models)} 个模型：{models[:5]}...")
                        return models
                    else:
                        self.logger.warning(f"从 {config.name} 获取模型列表格式异常：{data}")
                        return []
                else:
                    self.logger.warning(f"从 {config.name} 获取模型列表失败，状态码：{response.status_code}, 响应：{response.text[:200]}")
                    return []
                        
            except Exception as e:
                self.logger.warning(f"从 {config.name} 获取模型列表失败 (尝试 {attempt + 1}/3): {type(e).__name__}: {e}")
                if attempt < 2:  # 如果不是最后一次尝试，等待一段时间
                    await asyncio.sleep(2 ** attempt)  # 指数退避：1s, 2s
        
        self.logger.error(f"从 {config.name} 获取模型列表：所有尝试都失败")
        return []
    
    def _setup_routes(self) -> None:
        """设置路由
        
        注册所有 API 端点
        """
        self.logger.info("设置路由...")
        
        handlers = create_endpoint_handlers(self.settings, self.router)
        
        self.server.add_get("/health", handlers["health"].handle, name="health")
        self.server.add_get("/v1/models", handlers["models"].handle, name="models")
        self.server.add_post("/v1/chat/completions", handlers["chat"].handle, name="chat_completions")
        self.server.add_get("/status", handlers["status"].handle, name="status")
        
        self.logger.info(f"注册了 {len(handlers)} 个端点")
    
    async def start(self) -> None:
        """启动 AI Tunnel 服务
        
        Raises:
            AITunnelError: 启动失败
        """
        if not self.settings:
            await self.initialize()
        
        self._running = True
        self.logger.info("=" * 60)
        self.logger.info("AI Tunnel 服务启动")
        self.logger.info(f"监听地址：http://{self.settings.server.host}:{self.settings.server.port}")
        if self.settings.server.ssl_enabled:
            self.logger.info(f"HTTPS 地址：https://{self.settings.server.host}:{self.settings.server.port}")
        self.logger.info("=" * 60)
        
        try:
            await self.server.start()
            
            await self._wait_for_shutdown()
            
        except KeyboardInterrupt:
            self.logger.info("接收到键盘中断信号")
        except Exception as e:
            self.logger.exception(f"服务运行异常：{e}")
            raise AITunnelError(f"服务运行失败：{str(e)}")
        finally:
            await self.stop()
    
    async def _wait_for_shutdown(self) -> None:
        """等待关闭信号"""
        await self._shutdown_event.wait()
    
    async def stop(self) -> None:
        """停止 AI Tunnel 服务
        
        执行优雅关闭，确保所有请求处理完成
        """
        if not self._running:
            return
        
        self._running = False
        self.logger.info("正在停止 AI Tunnel 服务...")
        
        if self.server:
            await self.server.stop(timeout=30)
        
        self.logger.info("AI Tunnel 服务已停止")
        self.logger.info("感谢使用 AI Tunnel！")
    
    def is_running(self) -> bool:
        """检查服务是否正在运行
        
        Returns:
            bool: 服务运行状态
        """
        return self._running
    
    def _log_error(self, message: str, error: Exception) -> None:
        """记录错误日志
        
        Args:
            message: 错误消息
            error: 异常对象
        """
        if self.logger:
            self.logger.exception(f"{message}: {error}")
        else:
            print(f"[ERROR] {message}: {error}")


async def main(config_path: Optional[str] = None) -> None:
    """程序入口点
    
    Args:
        config_path: 配置文件路径
    """
    tunnel = AITunnel(config_path=config_path)
    await tunnel.start()


def run() -> None:
    """命令行入口点"""
    import sys
    
    config_path = None
    if len(sys.argv) > 1:
        if sys.argv[1] in ["-c", "--config"]:
            if len(sys.argv) > 2:
                config_path = sys.argv[2]
        else:
            config_path = sys.argv[1]
    
    try:
        asyncio.run(main(config_path))
    except KeyboardInterrupt:
        print("\n服务已中断")
    except Exception as e:
        print(f"[错误] 服务启动失败：{e}")
        import sys
        sys.exit(1)


if __name__ == "__main__":
    run()
