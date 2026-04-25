from src.server.admin.auth import (
    generate_token,
    verify_token,
    create_login_handler,
    create_auth_middleware,
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
    clear_logs,
)
from src.server.admin.dashboard import (
    create_dashboard_handler,
    create_system_status_handler,
    create_restart_handler,
)
from src.server.admin.routes import (
    register_admin_routes,
    auth_required,
)

__all__ = [
    "generate_token",
    "verify_token",
    "create_login_handler",
    "create_auth_middleware",
    "create_list_providers_handler",
    "create_add_provider_handler",
    "create_update_provider_handler",
    "create_delete_provider_handler",
    "create_toggle_provider_handler",
    "create_get_config_handler",
    "create_update_config_handler",
    "create_get_logs_handler",
    "setup_log_memory_handler",
    "clear_logs",
    "create_dashboard_handler",
    "create_system_status_handler",
    "create_restart_handler",
    "register_admin_routes",
    "auth_required",
]
