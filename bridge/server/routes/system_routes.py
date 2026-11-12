"""System health, diagnostics, and backup export/import routes."""

import logging
from pathlib import Path

from aiohttp import web

from services.backup_service import create_backup_zip, restore_backup_zip
from services.doctor_service import collect_doctor_diagnostics
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
) -> None:
    """Register /health, /api/system/doctor, /api/backup/export, and /api/backup/import."""

    async def health_handler(request: web.Request) -> web.Response:
        states = adapter_mgr.states if adapter_mgr else adapter_states
        return web.json_response(
            {
                "status": "running",
                "overlays": len(broadcaster.clients),
                "adapters": states,
                "settings_enabled": enable_settings,
                "stream_stats": broadcaster.last_stream_stats,
                "theme": broadcaster.current_theme,
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
            headers={
                "Content-Disposition": f'attachment; filename="{filename}"',
                "Access-Control-Allow-Origin": "*",
            },
        )

    async def import_backup_handler(request: web.Request) -> web.Response:
        if not request.content_type.startswith("multipart/"):
            return web.json_response({"error": "multipart content expected"}, status=400)
        reader = await request.multipart()
        field = await reader.next()
        if not field or not field.filename:
            return web.json_response({"error": "no backup file provided"}, status=400)

        data = await field.read()
        try:
            new_cfg = restore_backup_zip(
                data=data,
                project_root=project_root,
                config_path=target_config_path,
                backup_path=target_backup_path,
                src_dir=src_dir,
            )
            config.clear()
            config.update(new_cfg)

            broadcaster.init_goal(config.get("goal", {}), target_config_path)
            broadcaster.init_tts(config.get("tts", {}))
            sounds_data = get_sounds_catalog(src_dir)
            await broadcaster.broadcast(
                {
                    "type": "sounds_update",
                    "sounds": sounds_data.get("mapping", {}),
                    "masterVolume": sounds_data.get("masterVolume", 0.7),
                }
            )
            if adapter_mgr:
                await adapter_mgr.reload_if_changed(config)

            from obs.sync_scenes import get_default_obs_path, sync_collection

            default_obs = get_default_obs_path()
            if default_obs.exists():
                sync_collection(default_obs, dry_run=False, backup=True)

            log.info("backup imported and applied successfully")
            return web.json_response({"ok": True}, headers={"Access-Control-Allow-Origin": "*"})
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
