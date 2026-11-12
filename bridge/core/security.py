"""Security, authentication, and HTTP middleware utilities."""

import logging
from urllib.parse import urlparse

from aiohttp import web

log = logging.getLogger("bridge.security")

# Global API key for protecting state-changing POST endpoints
API_KEY: str = ""

PROTECTED_PATHS = {
    "/notify",
    "/api/config",
    "/api/sounds/upload",
    "/api/media/skip",
    "/api/donations/skip",
    "/api/tts/stop",
    "/api/backup/import",
}


def set_api_key(key: str) -> None:
    """Set runtime API key."""
    global API_KEY
    API_KEY = key


def get_api_key() -> str:
    """Get current runtime API key."""
    return API_KEY


def mask_secret(value: str) -> str:
    """Mask sensitive credentials for safe API responses (e.g. 'abc***wxyz')."""
    if not value or len(value) <= 7:
        return "********"
    return f"{value[:3]}***{value[-4:]}"


@web.middleware
async def auth_middleware(request, handler):
    """Enforce Same-Origin Referer or Bearer API_KEY on protected POST endpoints."""
    if request.method == "POST" and request.path in PROTECTED_PATHS:
        referer = request.headers.get("Referer", "")
        host_header = request.headers.get("Host", "")
        ref_parsed = urlparse(referer)
        ref_host = (
            f"{ref_parsed.hostname}:{ref_parsed.port}" if ref_parsed.port else (ref_parsed.hostname or "")
        )
        is_same_origin = ref_host == host_header or ref_parsed.hostname in ("localhost", "127.0.0.1")

        auth_header = request.headers.get("Authorization", "")
        has_valid_key = (auth_header == f"Bearer {API_KEY}") if API_KEY else False

        if not is_same_origin and not has_valid_key:
            log.warning("Unauthorized POST to %s from referer %s", request.path, referer)
            return web.json_response({"error": "unauthorized"}, status=401)
    return await handler(request)


@web.middleware
async def no_cache_middleware(request, handler):
    """Ensure dynamic responses are never cached by browser or proxies."""
    response = await handler(request)
    response.headers["Cache-Control"] = "no-cache, no-store, must-revalidate"
    response.headers["Pragma"] = "no-cache"
    response.headers["Expires"] = "0"
    return response
