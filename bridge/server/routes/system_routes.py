"""System health, diagnostics, and backup export/import routes."""

import copy
import logging
from pathlib import Path

from aiohttp import web

from services.backup_service import (
    commit_staged_restore,
    create_backup_zip,
    prepare_backup_restore,
    rollback_staged_restore,
)
from services.doctor_service import collect_doctor_diagnostics
from services.file_service import atomic_write_bytes
from services.sound_service import get_sounds_catalog

log = logging.getLogger("bridge.routes.system")


def register_system_routes(
    app: web.Application,
    broadcaster,
    config: dict,
    adapter_mgr,
    adapter_states: dict,
    project_root: Path,
    src_dir: Path,
    target_config_path: Path,
    target_backup_path: Path,
    enable_settings: bool,
    media_service=None,
    media_coordinator=None,
) -> None:
    """Register /health, /api/system/doctor, /api/backup/export, and /api/backup/import."""

    async def health_handler(request: web.Request) -> web.Response:
        statuses = (
            adapter_mgr.get_adapter_statuses()
            if adapter_mgr and hasattr(adapter_mgr, "get_adapter_statuses")
            else {
                name: {
                    "enabled": bool(adapter_states.get(name)),
                    "connected": bool(adapter_states.get(name)),
                    "status": "connected" if adapter_states.get(name) else "off",
                    "error": None,
                }
                for name in ("twitch", "twitch_chat", "donationalerts", "donatex")
            }
        )
        return web.json_response(
            {
                "status": "running",
                "overlays": len(broadcaster.clients),
                "adapters": {k: v["connected"] for k, v in statuses.items()},
                "adapter_details": statuses,
                "settings_enabled": enable_settings,
                "stream_stats": broadcaster.last_stream_stats,
                "theme": broadcaster.current_theme,
                "dnd_active": broadcaster.dnd_active,
            }
        )

    async def doctor_handler(request: web.Request) -> web.Response:
        diag = collect_doctor_diagnostics(
            config=config,
            broadcaster=broadcaster,
            project_root=project_root,
            src_dir=src_dir,
            adapter_mgr=adapter_mgr,
            adapter_states=adapter_states,
        )
        return web.json_response(diag, headers={"Access-Control-Allow-Origin": "*"})

    async def export_backup_handler(request: web.Request) -> web.Response:
        zip_bytes, filename = create_backup_zip(project_root, target_config_path, src_dir)
        return web.Response(
            body=zip_bytes,
            content_type="application/zip",
            headers={"Content-Disposition": f'attachment; filename="{filename}"'},
        )

    async def import_backup_handler(request: web.Request) -> web.Response:
        if not request.content_type.startswith("multipart/"):
            return web.json_response({"error": "multipart content expected"}, status=400)
        reader = await request.multipart()
        field = await reader.next()
        if not field or not field.filename:
            return web.json_response({"error": "no backup file provided"}, status=400)

        data = await field.read()
        old_cfg = copy.deepcopy(config)
        previous = previous_modes = None
        obs_previous = obs_mode = None
        default_obs = None

        async def apply_runtime(cfg):
            config.clear()
            config.update(copy.deepcopy(cfg))
            broadcaster.init_goal(config.get("goal", {}), target_config_path)
            broadcaster.init_tts(config.get("tts", {}))
            sounds_data = get_sounds_catalog(src_dir)
            await broadcaster.broadcast({
                "type": "sounds_update",
                "sounds": sounds_data.get("mapping", {}),
                "masterVolume": sounds_data.get("masterVolume", 0.7),
            })
            broadcaster.last_chat_config = {
                "type": "chat_config",
                "fadeSeconds": int(config.get("twitch_chat", {}).get("fade_seconds", 45)),
            }
            await broadcaster.broadcast(broadcaster.last_chat_config)
            broadcaster.init_appearance(config.get("appearance", {}))
            if broadcaster.last_theme:
                await broadcaster.broadcast(broadcaster.last_theme)
            if adapter_mgr:
                await adapter_mgr.reload_if_changed(config)
            if media_service:
                await media_service.reconfigure(config.get("media", {}))
                if media_coordinator:
                    media_coordinator.auto_pause_enabled = bool(config.get("media", {}).get("auto_pause", True))
            await broadcaster.broadcast({
                "type": "media_config",
                "youtubeDomain": config.get("media", {}).get("youtube_domain", "youtube-nocookie.com"),
            })

        try:
            new_cfg, staged = prepare_backup_restore(data, project_root, target_config_path, src_dir)
            previous, previous_modes = commit_staged_restore(staged, target_config_path, target_backup_path)
            from obs.sync_scenes import get_default_obs_path, sync_collection

            default_obs = get_default_obs_path()
            if default_obs.exists():
                obs_previous = default_obs.read_bytes()
                obs_mode = default_obs.stat().st_mode & 0o777
            try:
                await apply_runtime(new_cfg)
                if default_obs.exists():
                    sync_collection(default_obs, dry_run=False, backup=True)
            except Exception:
                rollback_staged_restore(staged, previous, previous_modes)
                if default_obs is not None:
                    if obs_previous is None:
                        default_obs.unlink(missing_ok=True)
                    else:
                        atomic_write_bytes(default_obs, obs_previous, mode=obs_mode or 0o600)
                try:
                    await apply_runtime(old_cfg)
                except Exception:
                    log.exception("failed to restore previous runtime after backup rollback")
                raise

            log.info("backup imported and applied successfully")
            return web.json_response({"ok": True})
        except ValueError as ve:
            return web.json_response({"error": str(ve)}, status=400)
        except Exception as e:
            log.exception("failed to import backup archive")
            return web.json_response({"error": f"import failed: {e}"}, status=500)

    app.router.add_get("/health", health_handler)
    if enable_settings:
        app.router.add_get("/api/doctor", doctor_handler)
        app.router.add_get("/api/system/doctor", doctor_handler)
        app.router.add_get("/api/backup/export", export_backup_handler)
        app.router.add_post("/api/backup/import", import_backup_handler)
