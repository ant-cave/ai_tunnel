import logging

from aiohttp import web
from aiohttp.web_request import Request

from src.config.settings import Settings
from src.server.admin.auth import create_login_handler, create_auth_middleware
from src.server.admin.dashboard import (
    create_dashboard_handler,
    create_system_status_handler,
    create_restart_handler,
)
from src.server.admin.providers import (
    create_list_providers_handler,
    create_add_provider_handler,
    create_update_provider_handler,
    create_delete_provider_handler,
    create_toggle_provider_handler,
)
from src.server.admin.config_api import (
    create_get_config_handler,
    create_update_config_handler,
)
from src.server.admin.logs import (
    create_get_logs_handler,
    setup_log_memory_handler,
)

logger = logging.getLogger("ai_tunnel.admin.routes")


def auth_required(auth_middleware):
    """认证中间件装饰器

    包装 handler，在调用前先执行认证检查
    """
    def decorator(handler):
        async def wrapped(request: Request, **kwargs) -> web.Response:
            auth_result = await auth_middleware(request)
            if auth_result is not None:
                return auth_result
            return await handler(request, **kwargs)
        return wrapped
    return decorator


def register_admin_routes(server, settings: Settings, router, config_path=None, app=None):
    """注册管理后台所有路由

    Args:
        server: HTTPServer 或 DualModeServer 实例
        settings: 应用配置
        router: 异步路由器实例
        config_path: 配置文件路径（可选）
        app: aiohttp Application 实例（可选）
    """
    server.add_static("/admin", "src/server/static/admin")

    setup_log_memory_handler()

    login_handler = create_login_handler(settings)
    server.add_route("/admin/api/auth/login", login_handler, method="POST")

    auth_middleware = create_auth_middleware(settings)
    protect = auth_required(auth_middleware)

    server.add_route("/admin/api/dashboard", protect(create_dashboard_handler(settings, router)), method="GET")

    server.add_route("/admin/api/providers", protect(create_list_providers_handler(router)), method="GET")
    server.add_route("/admin/api/providers", protect(create_add_provider_handler(router)), method="POST")
    server.add_route("/admin/api/providers/{name}", protect(create_update_provider_handler(router)), method="PUT")
    server.add_route("/admin/api/providers/{name}", protect(create_delete_provider_handler(router)), method="DELETE")
    server.add_route("/admin/api/providers/{name}/toggle", protect(create_toggle_provider_handler(router)), method="POST")

    server.add_route("/admin/api/config", protect(create_get_config_handler(settings)), method="GET")
    server.add_route("/admin/api/config", protect(create_update_config_handler(settings, config_path)), method="PUT")

    server.add_route("/admin/api/logs", protect(create_get_logs_handler()), method="GET")

    server.add_route("/admin/api/status", protect(create_system_status_handler(settings, router)), method="GET")
    server.add_route("/admin/api/restart", protect(create_restart_handler(app)), method="POST")

    logger.info("管理后台路由注册完成")
