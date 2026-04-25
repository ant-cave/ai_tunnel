import json
import logging

from aiohttp import web
from aiohttp.web_request import Request

from src.config.settings import Settings, ServerConfig, SecurityConfig, LoggingConfig

logger = logging.getLogger("ai_tunnel.admin.config_api")


def _serialize_settings(settings: Settings) -> dict:
    return {
        "server": {
            "host": settings.server.host,
            "port": settings.server.port,
            "ssl_enabled": settings.server.ssl_enabled,
            "ssl_cert_path": settings.server.ssl_cert_path,
            "ssl_key_path": settings.server.ssl_key_path,
            "workers": settings.server.workers,
            "max_connections": settings.server.max_connections,
            "keep_alive_timeout": settings.server.keep_alive_timeout,
            "request_timeout": settings.server.request_timeout,
        },
        "security": {
            "api_key": bool(settings.security.api_key),
            "allowed_origins": settings.security.allowed_origins,
            "rate_limit": settings.security.rate_limit,
            "encryption_enabled": settings.security.encryption_enabled,
            "admin_username": settings.security.admin_username,
        },
        "logging": {
            "level": settings.logging.level,
            "format": settings.logging.format,
            "file": settings.logging.file,
            "max_size": settings.logging.max_size,
            "backup_count": settings.logging.backup_count,
        },
    }


def create_get_config_handler(settings: Settings):
    async def get_config(request: Request, **kwargs) -> web.Response:
        config_dict = _serialize_settings(settings)
        return web.json_response({"config": config_dict})
    return get_config


def create_update_config_handler(settings: Settings, config_path=None):
    async def update_config(request: Request, **kwargs) -> web.Response:
        try:
            data = await request.json()
        except Exception:
            return web.json_response(
                {"error": {"message": "请求体格式错误", "code": "invalid_request"}},
                status=400,
            )

        if not data:
            return web.json_response(
                {"error": {"message": "请求体不能为空", "code": "validation_error"}},
                status=400,
            )

        try:
            if "server" in data:
                server_data = data["server"]
                for key, value in server_data.items():
                    if hasattr(settings.server, key):
                        setattr(settings.server, key, value)

            if "security" in data:
                security_data = data["security"]
                for key, value in security_data.items():
                    if hasattr(settings.security, key):
                        setattr(settings.security, key, value)

            if "logging" in data:
                logging_data = data["logging"]
                for key, value in logging_data.items():
                    if hasattr(settings.logging, key):
                        setattr(settings.logging, key, value)

            if config_path and ("server" in data or "logging" in data or "security" in data):
                try:
                    with open(config_path, "r", encoding="utf-8") as f:
                        existing_config = json.load(f)
                except Exception:
                    existing_config = {}

                for section in ["server", "security", "logging"]:
                    if section in data:
                        existing_config[section] = data[section]

                with open(config_path, "w", encoding="utf-8") as f:
                    json.dump(existing_config, f, ensure_ascii=False, indent=2)
                logger.info(f"配置文件已更新并保存到：{config_path}")

            logger.info("管理员更新配置成功")
            return web.json_response({
                "message": "配置更新成功",
                "config": _serialize_settings(settings),
            })

        except Exception as e:
            logger.exception(f"更新配置失败：{e}")
            return web.json_response(
                {"error": {"message": f"更新配置失败：{str(e)}", "code": "internal_error"}},
                status=500,
            )
    return update_config
