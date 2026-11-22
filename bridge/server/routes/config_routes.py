"""Configuration management and sound file upload endpoints."""

import copy
import logging
import os
import re
import tempfile
import time
from pathlib import Path

from aiohttp import web

from core.security import mask_secret
from services import yandex_tts
from services.file_service import atomic_write_bytes, atomic_write_text
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
    media_service=None,
    media_coordinator=None,
) -> None:
    """Register /api/config (GET/POST) and /api/sounds/upload endpoints."""

    if not enable_settings:
        return

    async def get_config_handler(request: web.Request) -> web.Response:
        sounds_info = get_sounds_catalog(src_dir)
        has_twitch_token = (project_root / "bridge" / ".twitch_token.json").exists()
        has_da_token = (project_root / "bridge" / ".da_token.json").exists()
        public_config = copy.deepcopy(config)
        for section, keys in {
            "twitch": ("client_secret",),
            "donationalerts": ("client_secret", "access_token"),
            "donatex": ("token",),
            "tts": ("auth_token",),
        }.items():
            for key in keys:
                if key in public_config.get(section, {}):
                    public_config[section][key] = mask_secret(public_config[section][key])

        return web.json_response(
            {
                "config": public_config,
                "sounds": sounds_info,
                "tts_voices": yandex_tts.VOICES,
                "auth": {
                    "twitch": has_twitch_token,
                    "donationalerts": has_da_token,
                },
            }
        )

    async def save_config_handler(request: web.Request) -> web.Response:
        try:
            payload = await request.json()
        except Exception:
            return web.json_response({"error": "invalid json"}, status=400)

        if not isinstance(payload, dict):
            return web.json_response({"error": "object expected"}, status=400)
        section_names = {
            "server", "twitch", "twitch_chat", "donationalerts", "donatex", "goal",
            "tts", "appearance", "transitions", "media",
        }
        if any(name in payload and not isinstance(payload[name], dict) for name in section_names):
            return web.json_response({"error": "configuration sections must be objects"}, status=400)

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
        if "transitions" in payload:
            config.setdefault("transitions", {}).update(payload["transitions"])
        if "media" in payload:
            config.setdefault("media", {}).update(payload["media"])

        # Backup existing config
        if target_config_path.exists():
            atomic_write_bytes(target_backup_path, target_config_path.read_bytes())

        # Write clean TOML without exposing secrets to other local users.
        toml_str = serialize_toml(config)
        atomic_write_text(target_config_path, toml_str)

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

        # 3. Hot-reload adapters and media without restarting the server.
        if adapter_mgr:
            await adapter_mgr.reload_if_changed(config)
        if "media" in payload and media_service:
            await media_service.reconfigure(config["media"])
            if media_coordinator:
                media_coordinator.auto_pause_enabled = bool(config["media"].get("auto_pause", True))
            await broadcaster.broadcast({
                "type": "media_config",
                "youtubeDomain": config["media"].get("youtube_domain", "youtube-nocookie.com"),
            })

        log.info("configuration saved via web settings panel (applied live)")
        return web.json_response({"ok": True})

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
        fd, temporary_name = tempfile.mkstemp(prefix=".sound-upload-", dir=sounds_dir)
        temporary = Path(temporary_name)
        try:
            with os.fdopen(fd, "wb") as stream:
                while True:
                    chunk = await field.read_chunk()
                    if not chunk:
                        break
                    size += len(chunk)
                    if size > 15 * 1024 * 1024:
                        exceeded = True
                        break
                    stream.write(chunk)
            if exceeded:
                return web.json_response({"error": "file exceeds 15MB limit"}, status=400)
            os.chmod(temporary, 0o644)
            os.replace(temporary, dest)
        finally:
            temporary.unlink(missing_ok=True)
        log.info("uploaded new sound file: %s (%d bytes)", safe_name, size)
        return web.json_response({"ok": True, "filename": safe_name})

    app.router.add_get("/api/config", get_config_handler)
    app.router.add_post("/api/config", save_config_handler)
    app.router.add_post("/api/sounds/upload", upload_sound_handler)
