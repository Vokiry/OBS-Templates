"""Security, authentication, and HTTP middleware utilities."""

import hmac
import logging
from urllib.parse import urlparse

from aiohttp import web

log = logging.getLogger("bridge.security")

# Global API key for protecting state-changing and sensitive endpoints
API_KEY: str = ""
REQUIRE_API_KEY = False
ALLOWED_REQUEST_HOSTS = {"127.0.0.1", "localhost", "::1"}

PROTECTED_PATHS = {
    "/notify",
    "/api/config",
    "/api/sounds/upload",
    "/api/media/control",
    "/api/media/skip",
    "/api/donations/skip",
    "/api/tts/stop",
    "/api/backup/import",
}

SENSITIVE_GET_PATHS = {
    "/api/config",
    "/api/backup/export",
}


def set_api_key(key: str, require_for_external: bool = False) -> None:
    """Set runtime API key and whether same-origin browser trust is disabled."""
    global API_KEY, REQUIRE_API_KEY
    API_KEY = key
    REQUIRE_API_KEY = require_for_external


def api_key_required() -> bool:
    """Return whether privileged clients must explicitly authenticate."""
    return REQUIRE_API_KEY


def configure_allowed_host(host: str) -> None:
    """Pin Host validation to the configured bind address instead of trusting arbitrary hosts."""
    global ALLOWED_REQUEST_HOSTS
    normalized = host.strip("[]").lower()
    if normalized in ("0.0.0.0", "::"):
        ALLOWED_REQUEST_HOSTS = set()  # External mode additionally requires the session key.
    elif normalized in ("127.0.0.1", "localhost", "::1"):
        ALLOWED_REQUEST_HOSTS = {"127.0.0.1", "localhost", "::1"}
    else:
        ALLOWED_REQUEST_HOSTS = {normalized}


def get_api_key() -> str:
    """Get current runtime API key."""
    return API_KEY


def mask_secret(value: str) -> str:
    """Mask sensitive credentials without exposing any original characters."""
    return "********" if value else ""


def is_same_origin(request: web.Request, source: str) -> bool:
    """Compare an Origin/Referer with the request scheme, host, and effective port."""
    if not source:
        return False
    try:
        parsed = urlparse(source)
        request_url = request.url
        request_host = (request_url.host or "").strip("[]").lower()
        if ALLOWED_REQUEST_HOSTS and request_host not in ALLOWED_REQUEST_HOSTS:
            return False
        if parsed.scheme not in ("http", "https") or not parsed.hostname:
            return False
        source_port = parsed.port or (443 if parsed.scheme == "https" else 80)
        request_port = request_url.port or (443 if request_url.scheme == "https" else 80)
        return (
            parsed.scheme == request_url.scheme
            and parsed.hostname.lower() == (request_url.host or "").lower()
            and source_port == request_port
        )
    except (TypeError, ValueError):
        return False


def has_valid_api_key(request: web.Request) -> bool:
    """Validate a Bearer token or an explicit WebSocket key query parameter."""
    if not API_KEY:
        return False
    auth_header = request.headers.get("Authorization", "")
    supplied = auth_header.removeprefix("Bearer ") if auth_header.startswith("Bearer ") else ""
    if not supplied:
        supplied = request.query.get("key", "")
    return bool(supplied) and hmac.compare_digest(supplied, API_KEY)


@web.middleware
async def auth_middleware(request, handler):
    """Require strict same-origin Referer or Bearer API_KEY on sensitive endpoints."""
    is_protected_post = request.method == "POST" and request.path in PROTECTED_PATHS
    is_sensitive_get = request.method == "GET" and request.path in SENSITIVE_GET_PATHS
    if is_protected_post or is_sensitive_get:
        is_same = is_same_origin(request, request.headers.get("Referer", "")) and not REQUIRE_API_KEY
        if not is_same and not has_valid_api_key(request):
            log.warning("Unauthorized %s to %s", request.method, request.path)
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
