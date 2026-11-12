#!/usr/bin/env python3
"""SYSTEM — OBS Broadcast Templates unified aiohttp server & WebSocket bridge."""

import argparse
import asyncio
import logging
import os
import secrets
import signal
import sys
from pathlib import Path

from aiohttp import web
from tomllib import load as toml_load

# Ensure bridge directory is on sys.path for direct script execution
sys.path.insert(0, str(Path(__file__).parent))

from core.adapter_manager import AdapterManager, watch
from core.broadcaster import Broadcaster
from core.security import API_KEY, set_api_key
from server.app import build_app
from services import yandex_tts
from services.goal_service import parse_amount
from services.sound_service import get_sounds_catalog, save_sounds_catalog
from services.toml_service import serialize_toml, toml_escape

log = logging.getLogger("bridge")

__all__ = [
    "Broadcaster",
    "AdapterManager",
    "build_app",
    "parse_amount",
    "toml_escape",
    "serialize_toml",
    "get_sounds_catalog",
    "save_sounds_catalog",
    "watch",
    "API_KEY",
    "yandex_tts",
]


async def main() -> None:
    parser = argparse.ArgumentParser(description="SYSTEM alerts bridge")
    parser.add_argument("--config", default=str(Path(__file__).parent / "config.toml"))
    parser.add_argument(
        "--settings", action="store_true", help="Enable web settings panel and configuration API"
    )
    parser.add_argument(
        "--open-browser", action="store_true", help="Open default web browser to dashboard on start"
    )
    args = parser.parse_args()

    config_path = Path(args.config)
    if not config_path.exists():
        log.error("config not found: %s (copy config.example.toml)", config_path)
        sys.exit(1)
    with open(config_path, "rb") as handle:
        config = toml_load(handle)

    server_cfg = config.get("server", {})
    host = server_cfg.get("host", "127.0.0.1")
    port = int(server_cfg.get("port", 8787))

    log.info("initializing bridge on http://%s:%d...", host, port)

    # Generate session API key for protecting state-changing endpoints
    session_key = secrets.token_urlsafe(24)
    set_api_key(session_key)

    broadcaster = Broadcaster()
    adapter_mgr = AdapterManager(broadcaster.broadcast)
    await adapter_mgr.start_all(config)

    app = build_app(
        broadcaster=broadcaster,
        config=config,
        enable_settings=args.settings,
        adapter_mgr=adapter_mgr,
        config_path=config_path,
    )
    if args.settings:
        log.info("SETTINGS MODE ACTIVE: web dashboard at http://%s:%d/settings", host, port)
    else:
        log.info("STREAM MODE ACTIVE: lightweight broadcast server (use --settings to configure)")
    runner = web.AppRunner(app)
    await runner.setup()
    site = web.TCPSite(runner, host, port)
    await site.start()
    log.info("unified server ready at ws://%s:%d/events", host, port)

    loop = asyncio.get_running_loop()
    stop_event = asyncio.Event()

    if args.open_browser:
        import webbrowser

        target_url = f"http://{host}:{port}/settings" if args.settings else f"http://{host}:{port}/dock"
        loop.call_later(0.6, webbrowser.open, target_url)
    if host != "127.0.0.1":
        log.info("API key for external access: %s", session_key)

    for sig in (signal.SIGINT, signal.SIGTERM):
        try:
            loop.add_signal_handler(sig, stop_event.set)
        except NotImplementedError:
            pass  # Windows doesn't support add_signal_handler

    try:
        await stop_event.wait()
    except (asyncio.CancelledError, KeyboardInterrupt):
        pass
    finally:
        log.info("shutting down...")
        await adapter_mgr.stop_all()
        # Cancel any pending broadcaster background tasks (TTS worker, delay clears, etc.)
        for t in list(broadcaster._background_tasks):
            t.cancel()
        if broadcaster._background_tasks:
            try:
                await asyncio.wait_for(
                    asyncio.gather(*broadcaster._background_tasks, return_exceptions=True),
                    timeout=1.0,
                )
            except asyncio.TimeoutError:
                pass
        # Close all WebSocket connections cleanly
        for ws in list(broadcaster.clients):
            try:
                await ws.close()
            except Exception:
                pass
        try:
            await asyncio.wait_for(runner.cleanup(), timeout=2.0)
        except Exception:
            pass
        log.info("shutdown complete")


if __name__ == "__main__":
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] [%(name)s] %(message)s",
        datefmt="%H:%M:%S",
    )
    # Silence repetitive HTTP polling access logs (such as GET /health every 3s)
    logging.getLogger("aiohttp.access").setLevel(logging.WARNING)

    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        pass
    except Exception:
        log.exception("fatal server error")
    finally:
        os._exit(0)
