"""Application factory assembling middlewares, services, and route modules."""

import json
import logging
from pathlib import Path

from aiohttp import web

from core.broadcaster import Broadcaster
from core.security import auth_middleware, no_cache_middleware
from server.routes.auth_routes import register_auth_routes
from server.routes.config_routes import register_config_routes
from server.routes.events_routes import register_events_routes
from server.routes.media_routes import register_media_routes
from server.routes.static_routes import register_static_routes
from server.routes.system_routes import register_system_routes

log = logging.getLogger("bridge.server.app")


def build_app(
    broadcaster: Broadcaster,
    config: dict,
    enable_settings: bool = False,
    adapter_mgr=None,
    config_path: Path | None = None,
) -> web.Application:
    """Build and configure the aiohttp web application."""
    project_root = Path(__file__).parent.parent.parent
    src_dir = project_root / "src"
    target_config_path = config_path or (project_root / "bridge" / "config.toml")
    target_backup_path = target_config_path.with_name(f"{target_config_path.name}.bak")

    # 1. Pre-cache sound catalog
    sounds_json_path = src_dir / "sounds" / "sounds.json"
    if sounds_json_path.exists():
        try:
            raw_sounds = json.loads(sounds_json_path.read_text(encoding="utf-8"))
            broadcaster.last_sounds_config = {
                "type": "sounds_update",
                "sounds": raw_sounds.get("sounds", {}),
                "masterVolume": raw_sounds.get("masterVolume", 0.7),
            }
        except Exception:
            pass

    # 2. Pre-cache chat config
    tc_cfg_init = config.get("twitch_chat", {})
    broadcaster.last_chat_config = {
        "type": "chat_config",
        "fadeSeconds": int(tc_cfg_init.get("fade_seconds", 45)),
    }

    # 3. Pre-cache donation goal
    goal_cfg = dict(config.get("goal", {}))
    broadcaster.init_goal(goal_cfg, broadcaster.config_path or target_config_path)

    # 4. Initialize TTS
    tts_cfg = dict(config.get("tts", {}))
    broadcaster.init_tts(tts_cfg)

    # 5. Initialize Appearance & Theme
    if "appearance" in config:
        broadcaster.init_appearance(config["appearance"])

    adapter_states = {
        name: bool(config.get(name, {}).get("enabled"))
        for name in ("twitch", "twitch_chat", "donationalerts", "donatex")
    }

    # 6. Create web application with security middlewares
    app = web.Application(middlewares=[auth_middleware, no_cache_middleware])

    # 7. Register modular routes
    register_static_routes(app, src_dir, enable_settings)
    register_events_routes(app, broadcaster)
    register_system_routes(
        app=app,
        broadcaster=broadcaster,
        config=config,
        adapter_mgr=adapter_mgr,
        adapter_states=adapter_states,
        project_root=project_root,
        src_dir=src_dir,
        target_config_path=target_config_path,
        target_backup_path=target_backup_path,
        enable_settings=enable_settings,
    )
    register_config_routes(
        app=app,
        broadcaster=broadcaster,
        config=config,
        adapter_mgr=adapter_mgr,
        project_root=project_root,
        src_dir=src_dir,
        target_config_path=target_config_path,
        target_backup_path=target_backup_path,
        enable_settings=enable_settings,
    )
    register_media_routes(app, broadcaster, config)
    register_auth_routes(app, config, enable_settings)

    return app
