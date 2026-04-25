"""
命令行接口模块

提供命令行参数解析和各种管理命令
"""

import argparse
import asyncio
import sys
from pathlib import Path
from typing import Optional, List

from src.config.settings import Settings
from src.config.validator import ConfigValidator
from src.utils.logger import setup_logger
from src.utils.exceptions import ConfigurationError, AITunnelError


class CLI:
    """命令行接口类
    
    提供以下功能：
    - 命令行参数解析
    - 启动命令
    - 配置验证命令
    - 配置生成命令
    - 版本信息
    """
    
    def __init__(self):
        """初始化命令行接口"""
        self.parser = self._create_parser()
        self.logger = None
    
    def _create_parser(self) -> argparse.ArgumentParser:
        """创建参数解析器
        
        Returns:
            argparse.ArgumentParser: 参数解析器
        """
        parser = argparse.ArgumentParser(
            prog="ai_tunnel",
            description="AI Tunnel - AI API 隧道代理服务",
            formatter_class=argparse.RawDescriptionHelpFormatter,
            epilog="""
示例:
  ai_tunnel start                      # 使用默认配置启动服务
  ai_tunnel start -c config.json       # 使用指定配置文件启动
  ai_tunnel validate -c config.json    # 验证配置文件
  ai_tunnel init                       # 生成配置示例文件
            """
        )
        
        parser.add_argument(
            "-v", "--version",
            action="version",
            version=f"%(prog)s {self._get_version()}"
        )
        
        subparsers = parser.add_subparsers(
            dest="command",
            title="可用命令",
            description="选择要执行的命令"
        )
        
        self._create_start_command(subparsers)
        self._create_validate_command(subparsers)
        self._create_init_command(subparsers)
        self._create_show_command(subparsers)
        
        return parser
    
    def _get_version(self) -> str:
        """获取版本号
        
        Returns:
            str: 版本号
        """
        return "1.0.0"
    
    def _create_start_command(self, subparsers: argparse._SubParsersAction) -> None:
        """创建启动命令
        
        Args:
            subparsers: 子解析器
        """
        start_parser = subparsers.add_parser(
            "start",
            help="启动 AI Tunnel 服务",
            description="启动 AI Tunnel HTTP 服务器"
        )
        
        start_parser.add_argument(
            "-c", "--config",
            type=str,
            default=None,
            metavar="PATH",
            help="配置文件路径 (默认：configs/config.json)"
        )
        
        start_parser.add_argument(
            "--host",
            type=str,
            default=None,
            metavar="HOST",
            help="监听主机地址 (默认：0.0.0.0)"
        )
        
        start_parser.add_argument(
            "-p", "--port",
            type=int,
            default=None,
            metavar="PORT",
            help="监听端口 (默认：8080)"
        )
        
        start_parser.add_argument(
            "--debug",
            action="store_true",
            help="启用调试模式"
        )
        
        start_parser.add_argument(
            "--ssl",
            action="store_true",
            help="启用 SSL"
        )
        
        start_parser.set_defaults(func=self._cmd_start)
    
    def _create_validate_command(self, subparsers: argparse._SubParsersAction) -> None:
        """创建配置验证命令
        
        Args:
            subparsers: 子解析器
        """
        validate_parser = subparsers.add_parser(
            "validate",
            help="验证配置文件",
            description="验证配置文件的语法和内容是否正确"
        )
        
        validate_parser.add_argument(
            "-c", "--config",
            type=str,
            required=True,
            metavar="PATH",
            help="配置文件路径"
        )
        
        validate_parser.add_argument(
            "--strict",
            action="store_true",
            help="严格模式：将警告视为错误"
        )
        
        validate_parser.set_defaults(func=self._cmd_validate)
    
    def _create_init_command(self, subparsers: argparse._SubParsersAction) -> None:
        """创建初始化命令
        
        Args:
            subparsers: 子解析器
        """
        init_parser = subparsers.add_parser(
            "init",
            help="生成配置示例文件",
            description="在当前目录生成配置示例文件"
        )
        
        init_parser.add_argument(
            "-o", "--output",
            type=str,
            default="config.json",
            metavar="PATH",
            help="输出文件路径 (默认：config.json)"
        )
        
        init_parser.add_argument(
            "--force",
            action="store_true",
            help="覆盖已存在的文件"
        )
        
        init_parser.set_defaults(func=self._cmd_init)
    
    def _create_show_command(self, subparsers: argparse._SubParsersAction) -> None:
        """创建显示配置命令
        
        Args:
            subparsers: 子解析器
        """
        show_parser = subparsers.add_parser(
            "show",
            help="显示当前配置",
            description="显示加载后的配置信息"
        )
        
        show_parser.add_argument(
            "-c", "--config",
            type=str,
            default=None,
            metavar="PATH",
            help="配置文件路径"
        )
        
        show_parser.add_argument(
            "--json",
            action="store_true",
            help="以 JSON 格式输出"
        )
        
        show_parser.set_defaults(func=self._cmd_show)
    
    def _cmd_start(self, args: argparse.Namespace) -> int:
        """启动命令处理函数
        
        Args:
            args: 命令行参数
            
        Returns:
            int: 退出码
        """
        from src.main import AITunnel
        
        config_path = args.config
        
        if not config_path:
            default_paths = [
                "configs/config.json",
                "config.json",
            ]
            for path in default_paths:
                if Path(path).exists():
                    config_path = path
                    break
        
        print(f"[信息] 启动 AI Tunnel 服务...")
        if config_path:
            print(f"[信息] 配置文件：{config_path}")
        
        try:
            tunnel = AITunnel(config_path=config_path)
            
            if args.debug:
                import os
                os.environ["AI_TUNNEL_LOG_LEVEL"] = "DEBUG"
            
            if args.host:
                import os
                os.environ["AI_TUNNEL_HOST"] = args.host
            
            if args.port:
                import os
                os.environ["AI_TUNNEL_PORT"] = str(args.port)
            
            # 使用自定义的事件循环来处理 Windows 信号
            if sys.platform == "win32":
                # Windows 平台需要特殊处理
                loop = asyncio.new_event_loop()
                asyncio.set_event_loop(loop)
                try:
                    loop.run_until_complete(tunnel.start())
                    return 0
                except KeyboardInterrupt:
                    print("\n[信息] 服务已中断")
                    return 0
                finally:
                    loop.close()
            else:
                # Unix/Linux 平台使用标准方式
                asyncio.run(tunnel.start())
                return 0
            
        except KeyboardInterrupt:
            print("\n[信息] 服务已中断")
            return 0
        except ConfigurationError as e:
            print(f"[错误] 配置错误：{e}", file=sys.stderr)
            return 1
        except AITunnelError as e:
            print(f"[错误] {e}", file=sys.stderr)
            return 1
        except Exception as e:
            print(f"[错误] 服务启动失败：{e}", file=sys.stderr)
            return 1
    
    def _cmd_validate(self, args: argparse.Namespace) -> int:
        """验证配置命令处理函数
        
        Args:
            args: 命令行参数
            
        Returns:
            int: 退出码
        """
        config_path = args.config
        
        if not Path(config_path).exists():
            print(f"[错误] 配置文件不存在：{config_path}", file=sys.stderr)
            return 1
        
        print(f"[信息] 验证配置文件：{config_path}")
        
        try:
            settings = Settings(config_path)
            settings.validate()
            
            print("[成功] 配置文件验证通过")
            
            if args.strict:
                print("[信息] 严格模式：无警告")
            
            return 0
            
        except ConfigurationError as e:
            print(f"[错误] 配置验证失败：{e}", file=sys.stderr)
            return 1
        except Exception as e:
            print(f"[错误] 验证过程出错：{e}", file=sys.stderr)
            return 1
    
    def _cmd_init(self, args: argparse.Namespace) -> int:
        """初始化配置命令处理函数
        
        Args:
            args: 命令行参数
            
        Returns:
            int: 退出码
        """
        output_path = Path(args.output)
        
        if output_path.exists() and not args.force:
            print(f"[错误] 文件已存在：{output_path}", file=sys.stderr)
            print("[提示] 使用 --force 参数覆盖文件", file=sys.stderr)
            return 1
        
        config_content = self._generate_config_template()
        
        try:
            output_path.parent.mkdir(parents=True, exist_ok=True)
            output_path.write_text(config_content, encoding="utf-8")
            
            print(f"[成功] 配置示例文件已生成：{output_path}")
            print("[提示] 请根据实际情况修改配置文件")
            
            return 0
            
        except Exception as e:
            print(f"[错误] 生成文件失败：{e}", file=sys.stderr)
            return 1
    
    def _cmd_show(self, args: argparse.Namespace) -> int:
        """显示配置命令处理函数
        
        Args:
            args: 命令行参数
            
        Returns:
            int: 退出码
        """
        config_path = args.config
        
        if not config_path:
            print("[错误] 请指定配置文件路径", file=sys.stderr)
            return 1
        
        if not Path(config_path).exists():
            print(f"[错误] 配置文件不存在：{config_path}", file=sys.stderr)
            return 1
        
        try:
            settings = Settings(config_path)
            settings.validate()
            
            if args.json:
                import json
                config_dict = {
                    "server": {
                        "host": settings.server.host,
                        "port": settings.server.port,
                        "ssl_enabled": settings.server.ssl_enabled,
                    },
                    "security": {
                        "api_key": "***" if settings.security.api_key else None,
                        "allowed_origins": settings.security.allowed_origins,
                        "rate_limit": settings.security.rate_limit,
                    },
                    "logging": {
                        "level": settings.logging.level,
                        "file": settings.logging.file,
                    }
                }
                print(json.dumps(config_dict, indent=2))
            else:
                print("=" * 60)
                print("AI Tunnel 配置信息")
                print("=" * 60)
                print(f"\n服务器配置:")
                print(f"  主机：{settings.server.host}")
                print(f"  端口：{settings.server.port}")
                print(f"  SSL: {'启用' if settings.server.ssl_enabled else '禁用'}")
                
                print(f"\n安全配置:")
                print(f"  API 密钥：{'已设置' if settings.security.api_key else '未设置'}")
                print(f"  允许源：{', '.join(settings.security.allowed_origins)}")
                print(f"  速率限制：{settings.security.rate_limit} 请求/分钟")
                
                print(f"\n日志配置:")
                print(f"  级别：{settings.logging.level}")
                print(f"  文件：{settings.logging.file or '未设置'}")
                
                print("\n" + "=" * 60)
            
            return 0
            
        except ConfigurationError as e:
            print(f"[错误] 配置加载失败：{e}", file=sys.stderr)
            return 1
        except Exception as e:
            print(f"[错误] 显示配置失败：{e}", file=sys.stderr)
            return 1
    
    def _generate_config_template(self) -> str:
        """生成配置模板
        
        Returns:
            str: 配置模板内容
        """
        return """# AI Tunnel 配置文件
# 请根据实际情况修改以下配置

# 服务器配置
[server]
host = "0.0.0.0"
port = 8080
ssl_enabled = false
# ssl_cert_path = "/path/to/cert.pem"
# ssl_key_path = "/path/to/key.pem"

# 安全配置
[security]
# api_key = "your-api-key-here"
allowed_origins = ["*"]
rate_limit = 100

# 日志配置
[logging]
level = "INFO"
# file = "logs/ai_tunnel.log"

# 提供者配置示例
# [providers]
#   [providers.openai]
#   name = "OpenAI"
#   api_endpoint = "https://api.openai.com/v1"
#   api_key = "your-openai-key"
#   models = { gpt-4 = "gpt-4", gpt-3.5-turbo = "gpt-3.5-turbo" }
"""
    
    def run(self, args: Optional[List[str]] = None) -> int:
        """运行命令行接口
        
        Args:
            args: 命令行参数列表，为 None 时使用 sys.argv
            
        Returns:
            int: 退出码
        """
        parsed_args = self.parser.parse_args(args)
        
        if not hasattr(parsed_args, "func"):
            self.parser.print_help()
            return 0
        
        return parsed_args.func(parsed_args)


def main() -> int:
    """CLI 入口点
    
    Returns:
        int: 退出码
    """
    cli = CLI()
    return cli.run()


if __name__ == "__main__":
    sys.exit(main())
