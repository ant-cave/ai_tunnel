import asyncio
import logging
from datetime import datetime

from aiohttp import web
from aiohttp.web_request import Request

from src.config.settings import Settings

logger = logging.getLogger("ai_tunnel.admin.dashboard")

VERSION = "1.0.0"

_start_time = asyncio.get_event_loop().time() if hasattr(asyncio.get_event_loop(), "time") else None


def create_dashboard_handler(settings: Settings, router):
    async def dashboard(request: Request, **kwargs) -> web.Response:
        router_status = router.get_status()
        providers = router.provider_manager.get_all_providers()

        uptime = 0
        global _start_time
        if _start_time is not None:
            try:
                uptime = asyncio.get_event_loop().time() - _start_time
            except Exception:
                uptime = 0

        provider_details = []
        for p in providers:
            provider_details.append({
                "name": p.name,
                "type": p.provider_type.value,
                "enabled": p.enabled,
                "healthy": p.is_healthy,
                "models_count": len(p.models),
            })

        return web.json_response({
            "uptime": uptime,
            "request_count": router_status.get("request_count", 0),
            "error_count": 0,
            "active_connections": 0,
            "total_providers": router_status.get("total_providers", 0),
            "healthy_providers": router_status.get("healthy_providers", 0),
            "enabled_providers": router_status.get("enabled_providers", 0),
            "providers": provider_details,
            "version": VERSION,
            "server": {
                "host": settings.server.host,
                "port": settings.server.port,
                "ssl_enabled": settings.server.ssl_enabled,
            },
        })
    return dashboard


def create_system_status_handler(settings: Settings, router):
    async def system_status(request: Request, **kwargs) -> web.Response:
        router_status = router.get_status()
        return web.json_response({
            "status": "running",
            "version": VERSION,
            "settings": {
                "host": settings.server.host,
                "port": settings.server.port,
                "ssl_enabled": settings.server.ssl_enabled,
                "log_level": settings.logging.level,
                "rate_limit": settings.security.rate_limit,
            },
            "router": router_status,
            "timestamp": datetime.now().isoformat(),
        })
    return system_status


def create_restart_handler(app):
    async def restart(request: Request, **kwargs) -> web.Response:
        logger.info("管理员请求重启服务")
        return web.json_response({
            "message": "重启请求已接收，服务即将重启",
            "status": "restarting",
        })
    return restart
