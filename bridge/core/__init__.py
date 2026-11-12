"""Bridge core: broadcaster, adapter manager, and security middleware."""

from core.adapter_manager import AdapterManager, watch
from core.broadcaster import Broadcaster
from core.security import (
    API_KEY,
    PROTECTED_PATHS,
    auth_middleware,
    get_api_key,
    mask_secret,
    no_cache_middleware,
    set_api_key,
)

__all__ = [
    "Broadcaster",
    "AdapterManager",
    "watch",
    "API_KEY",
    "PROTECTED_PATHS",
    "auth_middleware",
    "no_cache_middleware",
    "mask_secret",
    "set_api_key",
    "get_api_key",
]
