import hashlib
import hmac
import json
import base64
import time
import logging

from aiohttp import web
from aiohttp.web_request import Request

from src.config.settings import Settings

logger = logging.getLogger("ai_tunnel.admin.auth")


def _base64url_encode(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).rstrip(b"=").decode("ascii")


def _base64url_decode(data: str) -> bytes:
    padded = data + "=" * (4 - len(data) % 4)
    return base64.urlsafe_b64decode(padded)


def generate_token(settings: Settings) -> str:
    header = {"alg": "HS256", "typ": "JWT"}
    payload = {
        "username": settings.security.admin_username,
        "password": settings.security.admin_password,
        "iat": int(time.time()),
        "exp": int(time.time()) + 86400,
    }
    header_b64 = _base64url_encode(json.dumps(header, separators=(",", ":")).encode())
    payload_b64 = _base64url_encode(json.dumps(payload, separators=(",", ":")).encode())
    signing_input = f"{header_b64}.{payload_b64}"
    secret = settings.security.admin_token_secret.encode("utf-8")
    signature = hmac.new(secret, signing_input.encode("utf-8"), hashlib.sha256).digest()
    signature_b64 = _base64url_encode(signature)
    return f"{signing_input}.{signature_b64}"


def verify_token(token: str, settings: Settings) -> bool:
    try:
        parts = token.split(".")
        if len(parts) != 3:
            return False
        header_b64, payload_b64, signature_b64 = parts
        signing_input = f"{header_b64}.{payload_b64}"
        secret = settings.security.admin_token_secret.encode("utf-8")
        expected_sig = hmac.new(secret, signing_input.encode("utf-8"), hashlib.sha256).digest()
        expected_sig_b64 = _base64url_encode(expected_sig)
        if not hmac.compare_digest(signature_b64, expected_sig_b64):
            return False
        payload = json.loads(_base64url_decode(payload_b64))
        if payload.get("username") != settings.security.admin_username:
            return False
        if payload.get("password") != settings.security.admin_password:
            return False
        if payload.get("exp", 0) < time.time():
            return False
        return True
    except Exception:
        return False


def create_login_handler(settings: Settings):
    async def login_handler(request: Request) -> web.Response:
        try:
            data = await request.json()
        except Exception:
            return web.json_response(
                {"error": {"message": "请求体格式错误", "code": "invalid_request"}},
                status=400,
            )
        username = data.get("username", "")
        password = data.get("password", "")
        if username == settings.security.admin_username and password == settings.security.admin_password:
            token = generate_token(settings)
            return web.json_response({
                "token": token,
                "username": username,
            })
        return web.json_response(
            {"error": {"message": "用户名或密码错误", "code": "authentication_error"}},
            status=401,
        )
    return login_handler


def create_auth_middleware(settings: Settings):
    async def auth_middleware(request: Request) -> web.Response:
        auth_header = request.headers.get("Authorization", "")
        if not auth_header.startswith("Bearer "):
            return web.json_response(
                {"error": {"message": "未授权访问", "code": "unauthorized"}},
                status=401,
            )
        token = auth_header[7:]
        if not verify_token(token, settings):
            return web.json_response(
                {"error": {"message": "未授权访问", "code": "unauthorized"}},
                status=401,
            )
        return None
    return auth_middleware
