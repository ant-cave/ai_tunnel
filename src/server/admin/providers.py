import json
import logging

from aiohttp import web
from aiohttp.web_request import Request

from src.router.provider_manager import ProviderConfig, ProviderType

logger = logging.getLogger("ai_tunnel.admin.providers")


def create_list_providers_handler(router):
    async def list_providers(request: Request, **kwargs) -> web.Response:
        providers = router.provider_manager.get_all_providers()
        result = []
        for p in providers:
            result.append({
                "name": p.name,
                "provider_type": p.provider_type.value,
                "base_url": p.base_url,
                "models": p.models,
                "enabled": p.enabled,
                "is_healthy": p.is_healthy,
                "priority": p.priority,
            })
        return web.json_response({"providers": result})
    return list_providers


def create_add_provider_handler(router):
    async def add_provider(request: Request, **kwargs) -> web.Response:
        try:
            data = await request.json()
        except Exception:
            return web.json_response(
                {"error": {"message": "请求体格式错误", "code": "invalid_request"}},
                status=400,
            )
        name = data.get("name")
        if not name:
            return web.json_response(
                {"error": {"message": "缺少提供者名称", "code": "validation_error"}},
                status=400,
            )
        provider_type_str = data.get("provider_type", "openai")
        try:
            provider_type = ProviderType(provider_type_str)
        except ValueError:
            return web.json_response(
                {"error": {"message": f"无效的提供者类型：{provider_type_str}", "code": "validation_error"}},
                status=400,
            )
        config = ProviderConfig(
            name=name,
            provider_type=provider_type,
            base_url=data.get("base_url", ""),
            api_key=data.get("api_key", ""),
            models=data.get("models", []),
            enabled=data.get("enabled", True),
        )
        try:
            router.add_provider(config)
            logger.info(f"管理员添加提供者：{name}")
            return web.json_response({
                "message": f"提供者 {name} 添加成功",
                "provider": {
                    "name": name,
                    "provider_type": provider_type.value,
                    "base_url": config.base_url,
                    "models": config.models,
                    "enabled": config.enabled,
                },
            })
        except ValueError as e:
            return web.json_response(
                {"error": {"message": str(e), "code": "conflict"}},
                status=409,
            )
        except Exception as e:
            logger.exception(f"添加提供者失败：{e}")
            return web.json_response(
                {"error": {"message": f"添加提供者失败：{str(e)}", "code": "internal_error"}},
                status=500,
            )
    return add_provider


def create_update_provider_handler(router):
    async def update_provider(request: Request, **kwargs) -> web.Response:
        name = request.match_info.get("name")
        if not name:
            return web.json_response(
                {"error": {"message": "缺少提供者名称", "code": "validation_error"}},
                status=400,
            )
        existing = router.provider_manager.get_provider(name)
        if not existing:
            return web.json_response(
                {"error": {"message": f"提供者 {name} 不存在", "code": "not_found"}},
                status=404,
            )
        try:
            data = await request.json()
        except Exception:
            return web.json_response(
                {"error": {"message": "请求体格式错误", "code": "invalid_request"}},
                status=400,
            )
        provider_type_str = data.get("provider_type", existing.provider_type.value)
        try:
            provider_type = ProviderType(provider_type_str)
        except ValueError:
            return web.json_response(
                {"error": {"message": f"无效的提供者类型：{provider_type_str}", "code": "validation_error"}},
                status=400,
            )
        config = ProviderConfig(
            name=name,
            provider_type=provider_type,
            base_url=data.get("base_url", existing.base_url),
            api_key=data.get("api_key", existing.api_key),
            models=data.get("models", existing.models),
            enabled=data.get("enabled", existing.enabled),
        )
        router.remove_provider(name)
        router.add_provider(config)
        logger.info(f"管理员更新提供者：{name}")
        return web.json_response({
            "message": f"提供者 {name} 更新成功",
            "provider": {
                "name": name,
                "provider_type": provider_type.value,
                "base_url": config.base_url,
                "models": config.models,
                "enabled": config.enabled,
            },
        })
    return update_provider


def create_delete_provider_handler(router):
    async def delete_provider(request: Request, **kwargs) -> web.Response:
        name = request.match_info.get("name")
        if not name:
            return web.json_response(
                {"error": {"message": "缺少提供者名称", "code": "validation_error"}},
                status=400,
            )
        existing = router.provider_manager.get_provider(name)
        if not existing:
            return web.json_response(
                {"error": {"message": f"提供者 {name} 不存在", "code": "not_found"}},
                status=404,
            )
        router.remove_provider(name)
        logger.info(f"管理员删除提供者：{name}")
        return web.json_response({"message": f"提供者 {name} 删除成功"})
    return delete_provider


def create_toggle_provider_handler(router):
    async def toggle_provider(request: Request, **kwargs) -> web.Response:
        name = request.match_info.get("name")
        if not name:
            return web.json_response(
                {"error": {"message": "缺少提供者名称", "code": "validation_error"}},
                status=400,
            )
        provider = router.provider_manager.get_provider(name)
        if not provider:
            return web.json_response(
                {"error": {"message": f"提供者 {name} 不存在", "code": "not_found"}},
                status=404,
            )
        new_enabled = not provider.enabled
        provider.config.enabled = new_enabled
        logger.info(f"管理员切换提供者 {name} 状态为：{'启用' if new_enabled else '禁用'}")
        return web.json_response({
            "message": f"提供者 {name} 已{'启用' if new_enabled else '禁用'}",
            "provider": {
                "name": name,
                "enabled": new_enabled,
            },
        })
    return toggle_provider
