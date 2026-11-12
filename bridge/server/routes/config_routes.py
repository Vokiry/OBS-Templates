"""Configuration management and sound file upload endpoints."""

import logging
import re
import time
from pathlib import Path

from aiohttp import web

from services import yandex_tts
from services.sound_service import get_sounds_catalog, save_sounds_catalog
from services.toml_service import serialize_toml

log = logging.getLogger("bridge.routes.config")


def register_config_routes(
    app: web.Application,
    broadcaster,
    config: dict,
    adapter_mgr,
    project_root: Path,
    src_dir: Path,
    target_config_path: Path,
    target_backup_path: Path,
    enable_settings: bool,
) -> None:
    """Register /api/config (GET/POST) and /api/sounds/upload endpoints."""

    if not enable_settings:
        return

    async def get_config_handler(request: web.Request) -> web.Response:
        sounds_info = get_sounds_catalog(src_dir)
        has_twitch_token = (project_root / "bridge" / ".twitch_token.json").exists()
        has_da_token = (project_root / "bridge" / ".da_token.json").exists()

        return web.json_response(
            {
                "config": config,
                "sounds": sounds_info,
                "tts_voices": yandex_tts.VOICES,
                "auth": {
                    "twitch": has_twitch_token,
                    "donationalerts": has_da_token,
                },
            },
            headers={"Access-Control-Allow-Origin": "*"},
        )

    async def save_config_handler(request: web.Request) -> web.Response:
        try:
            payload = await request.json()
        except Exception:
            return web.json_response({"error": "invalid json"}, status=400)

        # 1. Update config dict
        if "server" in payload:
            config.setdefault("server", {}).update(payload["server"])
        if "twitch" in payload:
            config.setdefault("twitch", {}).update(payload["twitch"])
        if "twitch_chat" in payload:
            config.setdefault("twitch_chat", {}).update(payload["twitch_chat"])
            fade_sec = int(config["twitch_chat"].get("fade_seconds", 45))
            broadcaster.last_chat_config = {"type": "chat_config", "fadeSeconds": fade_sec}
            await broadcaster.broadcast(broadcaster.last_chat_config)
        if "donationalerts" in payload:
            config.setdefault("donationalerts", {}).update(payload["donationalerts"])
        if "donatex" in payload:
            config.setdefault("donatex", {}).update(payload["donatex"])
        if "goal" in payload:
            config.setdefault("goal", {}).update(payload["goal"])
            broadcaster.init_goal(config["goal"], target_config_path)
            if broadcaster.last_goal:
                await broadcaster.broadcast(broadcaster.last_goal)
        if "tts" in payload:
            config.setdefault("tts", {}).update(payload["tts"])
            broadcaster.init_tts(config["tts"])
        if "appearance" in payload:
            config.setdefault("appearance", {}).update(payload["appearance"])
            broadcaster.init_appearance(config["appearance"])
            if broadcaster.last_theme:
                await broadcaster.broadcast(broadcaster.last_theme)

        # Backup existing config
        if target_config_path.exists():
            target_backup_path.write_bytes(target_config_path.read_bytes())

        # Write clean TOML
        toml_str = serialize_toml(config)
        target_config_path.write_text(toml_str, encoding="utf-8")

        # 2. Save sound mappings if provided
        if "sounds" in payload and "mapping" in payload["sounds"]:
            master_vol = payload["sounds"].get("masterVolume", 0.7)
            sound_data = save_sounds_catalog(src_dir, payload["sounds"]["mapping"], master_volume=master_vol)
            await broadcaster.broadcast(
                {
                    "type": "sounds_update",
                    "sounds": sound_data.get("sounds", {}),
                    "masterVolume": sound_data.get("masterVolume", master_vol),
                }
            )

        # 3. Hot-reload any changed adapters without restarting server
        if adapter_mgr:
            await adapter_mgr.reload_if_changed(config)

        log.info("configuration saved via web settings panel (applied live)")
        return web.json_response({"ok": True}, headers={"Access-Control-Allow-Origin": "*"})

    async def upload_sound_handler(request: web.Request) -> web.Response:
        if not request.content_type.startswith("multipart/"):
            return web.json_response({"error": "multipart content expected"}, status=400)
        sounds_dir = src_dir / "sounds"
        try:
            reader = await request.multipart()
            field = await reader.next()
        except Exception:
            return web.json_response({"error": "failed to parse multipart data"}, status=400)
        if not field or not field.filename:
            return web.json_response({"error": "no file uploaded"}, status=400)

        raw_filename = field.filename
        ext = Path(raw_filename).suffix.lower()
        if ext not in {".wav", ".mp3", ".ogg", ".flac"}:
            return web.json_response(
                {"error": "unsupported audio format (use .wav, .mp3, .ogg)"},
                status=400,
            )

        # Sanitize filename against path traversal
        clean_name = Path(raw_filename).name
        safe_name = re.sub(r"[^a-zA-Z0-9_.-]", "_", clean_name)
        if not safe_name.strip("._"):
            safe_name = f"sound_{int(time.time())}{ext}"
        dest = sounds_dir / safe_name
        size = 0
        exceeded = False
        with open(dest, "wb") as f:
            while True:
                chunk = await field.read_chunk()
                if not chunk:
                    break
                size += len(chunk)
                if size > 15 * 1024 * 1024:  # 15MB limit
                    exceeded = True
                    break
                f.write(chunk)

        if exceeded:
            dest.unlink(missing_ok=True)
            return web.json_response({"error": "file exceeds 15MB limit"}, status=400)

        log.info("uploaded new sound file: %s (%d bytes)", safe_name, size)
        return web.json_response(
            {"ok": True, "filename": safe_name}, headers={"Access-Control-Allow-Origin": "*"}
        )

    app.router.add_get("/api/config", get_config_handler)
    app.router.add_post("/api/config", save_config_handler)
    app.router.add_post("/api/sounds/upload", upload_sound_handler)
