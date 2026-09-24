import asyncio
import argparse
import json
import logging
import sys
from pathlib import Path
from tomllib import load as toml_load

from aiohttp import WSMsgType, web

sys.path.insert(0, str(Path(__file__).parent))

from adapters import base

log = logging.getLogger("bridge")


class Broadcaster:
    def __init__(self):
        self.clients = set()

    async def attach(self, request) -> web.WebSocketResponse:
        socket = web.WebSocketResponse(heartbeat=20)
        await socket.prepare(request)
        self.clients.add(socket)
        log.info("overlay attached (%d total)", len(self.clients))
        try:
            async for msg in socket:
                if msg.type == WSMsgType.ERROR:
                    break
        finally:
            self.clients.discard(socket)
            log.info("overlay detached (%d total)", len(self.clients))
        return socket

    async def broadcast(self, payload: dict) -> None:
        message = base.encode(payload)
        for socket in list(self.clients):
            try:
                await socket.send_str(message)
            except Exception:
                self.clients.discard(socket)


def build_app(broadcaster: Broadcaster, adapter_states: dict) -> web.Application:
    project_root = Path(__file__).parent.parent
    src_dir = project_root / "src"

    async def events(request):
        return await broadcaster.attach(request)

    async def notify(request):
        try:
            payload = await request.json()
        except Exception:
            return web.json_response({"error": "invalid json"}, status=400)
        if not isinstance(payload, dict):
            return web.json_response({"error": "object expected"}, status=400)
        await broadcaster.broadcast(payload)
        return web.json_response({"ok": True})

    async def health(request):
        return web.json_response({
            "status": "running",
            "overlays": len(broadcaster.clients),
            "adapters": adapter_states,
        })

    async def root_redirect(request):
        return web.HTTPFound("/src/preview/index.html")

    async def dock_redirect(request):
        return web.HTTPFound("/src/dock/index.html")

    app = web.Application()
    app.router.add_get("/", root_redirect)
    app.router.add_get("/dock", dock_redirect)
    app.router.add_get("/events", events)
    app.router.add_post("/notify", notify)
    app.router.add_get("/health", health)

    if src_dir.exists():
        app.router.add_static("/src", path=str(src_dir))

    return app


def spawn_adapters(config: dict, broadcast) -> list:
    tasks = []
    sections = {
        "twitch": ("adapters.twitch", config.get("twitch", {})),
        "twitch_chat": ("adapters.twitch_chat", config.get("twitch_chat", {})),
        "donationalerts": ("adapters.donationalerts", config.get("donationalerts", {})),
        "donatex": ("adapters.donatex", config.get("donatex", {})),
    }
    for name, (module_path, section) in sections.items():
        if not section.get("enabled"):
            continue
        module = __import__(module_path, fromlist=["run"])
        tasks.append(asyncio.create_task(watch(name, module.run(section, broadcast))))
    return tasks


async def watch(name: str, coro) -> None:
    try:
        await coro
    except Exception:
        log.exception("adapter %s crashed", name)


async def main() -> None:
    parser = argparse.ArgumentParser(description="SYSTEM alerts bridge")
    parser.add_argument("--config", default=str(Path(__file__).parent / "config.toml"))
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

    broadcaster = Broadcaster()
    tasks = spawn_adapters(config, broadcaster.broadcast)

    app = build_app(broadcaster, {name: bool(config.get(name, {}).get("enabled")) for name in ("twitch", "twitch_chat", "donationalerts", "donatex")})
    runner = web.AppRunner(app)
    await runner.setup()
    site = web.TCPSite(runner, host, port)
    await site.start()
    log.info("listening on ws://%s:%d/events", host, port)

    await asyncio.gather(*tasks, asyncio.Event().wait())


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(name)s %(levelname)s %(message)s")
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        pass