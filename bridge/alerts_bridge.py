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
        self.last_status = None
        self.last_7tv_emotes = None

    async def attach(self, request) -> web.WebSocketResponse:
        socket = web.WebSocketResponse(heartbeat=20)
        await socket.prepare(request)
        self.clients.add(socket)
        log.info("overlay attached (%d total)", len(self.clients))

        # Immediately send cached state to newly attached overlay
        try:
            if self.last_status:
                await socket.send_str(base.encode(self.last_status))
            if self.last_7tv_emotes:
                await socket.send_str(base.encode(self.last_7tv_emotes))
        except Exception:
            pass

        try:
            async for msg in socket:
                if msg.type == WSMsgType.TEXT:
                    try:
                        data = json.loads(msg.data)
                        if isinstance(data, dict):
                            await self.handle_client_event(data)
                    except Exception:
                        pass
                elif msg.type == WSMsgType.ERROR:
                    break
        finally:
            self.clients.discard(socket)
            log.info("overlay detached (%d total)", len(self.clients))
        return socket

    async def handle_client_event(self, data: dict) -> None:
        msg_type = data.get("type")
        if msg_type == "media_finished":
            log.info("media playback finished, notifying DonateX skip...")
            from adapters import donatex
            await donatex.skip_track()
        elif msg_type == "media_control" and data.get("action") == "skip":
            log.info("media skip requested by client")
            from adapters import donatex
            await donatex.skip_track()
            await self.broadcast(data)
        elif msg_type in ("status", "countdown_control", "chat_clear"):
            await self.broadcast(data)

    async def broadcast(self, payload: dict) -> None:
        msg_type = payload.get("type")
        if msg_type == "status":
            self.last_status = payload
        elif msg_type == "7tv_emotes":
            self.last_7tv_emotes = payload

        message = base.encode(payload)
        for socket in list(self.clients):
            try:
                await socket.send_str(message)
            except Exception:
                self.clients.discard(socket)


def build_app(broadcaster: Broadcaster, config: dict) -> web.Application:
    project_root = Path(__file__).parent.parent
    src_dir = project_root / "src"

    adapter_states = {
        name: bool(config.get(name, {}).get("enabled"))
        for name in ("twitch", "twitch_chat", "donationalerts", "donatex")
    }

    async def events(request):
        return await broadcaster.attach(request)

    async def notify(request):
        try:
            payload = await request.json()
        except Exception:
            return web.json_response({"error": "invalid json"}, status=400)
        if not isinstance(payload, dict):
            return web.json_response({"error": "object expected"}, status=400)

        # Handle media skip directly if requested
        if payload.get("type") == "media_control" and payload.get("action") == "skip":
            from adapters import donatex
            await donatex.skip_track()

        await broadcaster.broadcast(payload)
        return web.json_response({"ok": True})

    async def health(request):
        return web.json_response({
            "status": "running",
            "overlays": len(broadcaster.clients),
            "adapters": adapter_states,
        })

    async def root_redirect(request):
        return web.HTTPFound("/dock")

    async def dock_redirect(request):
        return web.HTTPFound("/src/dock/index.html")

    async def resolve_media_api(request):
        url = request.query.get("url", "")
        if not url:
            return web.json_response({"url": ""}, headers={"Access-Control-Allow-Origin": "*"})
        from adapters.twitch_chat import resolve_drisnya_media
        resolved = await resolve_drisnya_media(url)
        return web.json_response({"url": resolved}, headers={"Access-Control-Allow-Origin": "*"})

    tc_cfg = config.get("twitch_chat", {})
    tv_source = str(tc_cfg.get("seven_tv_source", "direct")).strip().lower()
    tv_mirror = str(tc_cfg.get("seven_tv_mirror", "https://enhanced.jeetbot.cc")).strip().rstrip("/")

    async def get_7tv_config(request):
        cdn = "https://cdn.7tv.app/emote" if tv_source != "mirror" else f"{tv_mirror}/https://cdn.7tv.app/emote"
        return web.json_response({
            "source": tv_source,
            "cdnBase": cdn,
            "mirror": tv_mirror,
        }, headers={"Access-Control-Allow-Origin": "*"})

    async def proxy_7tv_global(request):
        import aiohttp
        direct_url = "https://7tv.io/v3/emote-sets/global"
        mirror_url = f"{tv_mirror}/https://7tv.io/v3/emote-sets/global"

        if tv_source == "mirror":
            urls = [(mirror_url, f"{tv_mirror}/https://cdn.7tv.app/emote")]
        elif tv_source == "direct":
            urls = [(direct_url, "https://cdn.7tv.app/emote")]
        else:  # auto
            urls = [
                (direct_url, "https://cdn.7tv.app/emote"),
                (mirror_url, f"{tv_mirror}/https://cdn.7tv.app/emote"),
            ]

        for u, cdn in urls:
            try:
                async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=3.5)) as s:
                    async with s.get(u) as resp:
                        if resp.status == 200:
                            data = await resp.read()
                            return web.Response(
                                body=data,
                                content_type="application/json",
                                headers={
                                    "Access-Control-Allow-Origin": "*",
                                    "X-7TV-CDN-Base": cdn,
                                }
                            )
            except Exception:
                pass
        return web.json_response({"emotes": []}, headers={"Access-Control-Allow-Origin": "*"})

    async def proxy_7tv_channel(request):
        import aiohttp
        room_id = request.match_info["room_id"]
        direct_url = f"https://7tv.io/v3/users/twitch/{room_id}"
        mirror_url = f"{tv_mirror}/https://7tv.io/v3/users/twitch/{room_id}"

        if tv_source == "mirror":
            urls = [(mirror_url, f"{tv_mirror}/https://cdn.7tv.app/emote")]
        elif tv_source == "direct":
            urls = [(direct_url, "https://cdn.7tv.app/emote")]
        else:  # auto
            urls = [
                (direct_url, "https://cdn.7tv.app/emote"),
                (mirror_url, f"{tv_mirror}/https://cdn.7tv.app/emote"),
            ]

        for u, cdn in urls:
            try:
                async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=3.5)) as s:
                    async with s.get(u) as resp:
                        if resp.status == 200:
                            data = await resp.read()
                            return web.Response(
                                body=data,
                                content_type="application/json",
                                headers={
                                    "Access-Control-Allow-Origin": "*",
                                    "X-7TV-CDN-Base": cdn,
                                }
                            )
            except Exception:
                pass
        return web.json_response({}, headers={"Access-Control-Allow-Origin": "*"})

    async def media_skip_api(request):
        from adapters import donatex
        skipped = await donatex.skip_track()
        await broadcaster.broadcast({"type": "media_control", "action": "skip"})
        return web.json_response({"ok": True, "donatex_skipped": skipped}, headers={"Access-Control-Allow-Origin": "*"})

    async def da_callback(request):
        code = request.query.get("code")
        if not code:
            error = request.query.get("error_description") or request.query.get("error") or "Код авторизации не найден"
            log.error("DonationAlerts OAuth error: %s", error)
            return web.Response(
                text=f"<h1>[ SYSTEM ]</h1><p style='font-family: monospace;'>Ошибка от DonationAlerts: {error}</p>",
                content_type="text/html",
                status=400
            )

        da_cfg = config.get("donationalerts", {})
        client_id = str(da_cfg.get("client_id", "")).strip()
        client_secret = str(da_cfg.get("client_secret", "")).strip()
        if not client_secret:
            raw_token = str(da_cfg.get("access_token", "")).strip()
            if len(raw_token) == 40 and not raw_token.startswith("eyJ"):
                client_secret = raw_token

        if not client_id or not client_secret:
            log.error("DonationAlerts missing client_id or client_secret")
            return web.Response(
                text="<h1>[ SYSTEM ]</h1><p style='font-family: monospace;'>Ошибка: укажите client_id и client_secret в bridge/config.toml</p>",
                content_type="text/html",
                status=400
            )

        from adapters.donationalerts import exchange_da_code
        try:
            redirect_uri = "http://localhost:8787/api/da/callback"
            await exchange_da_code(client_id, client_secret, redirect_uri, code)
            return web.Response(
                text=(
                    "<!DOCTYPE html><html><head><meta charset='utf-8'><title>SYSTEM // DA OK</title></head>"
                    "<body style='background:#0B0F14;color:#63E6BE;font-family:monospace;padding:40px;text-align:center;'>"
                    "<h1>[ SYSTEM // DONATIONALERTS CONNECTED ]</h1>"
                    "<p style='color:#E8EEF2;'>DonationAlerts успешно авторизован! Окно можно закрыть, мост уже подключился.</p>"
                    "</body></html>"
                ),
                content_type="text/html"
            )
        except Exception as e:
            log.error("DonationAlerts auth callback error: %s", e)
            return web.Response(
                text=(
                    f"<!DOCTYPE html><html><head><meta charset='utf-8'><title>SYSTEM // DA ERROR</title></head>"
                    f"<body style='background:#0B0F14;color:#E5484D;font-family:monospace;padding:40px;'>"
                    f"<h1>[ Ошибка авторизации DonationAlerts ]</h1>"
                    f"<p style='color:#E8EEF2;'>{e}</p>"
                    f"</body></html>"
                ),
                content_type="text/html",
                status=500
            )

    app = web.Application()
    app.router.add_get("/", root_redirect)
    app.router.add_get("/dock", dock_redirect)
    app.router.add_get("/events", events)
    app.router.add_post("/notify", notify)
    app.router.add_get("/health", health)
    app.router.add_get("/api/resolve-media", resolve_media_api)
    app.router.add_get("/api/7tv/config", get_7tv_config)
    app.router.add_get("/api/7tv/global", proxy_7tv_global)
    app.router.add_get("/api/7tv/channel/{room_id}", proxy_7tv_channel)
    app.router.add_post("/api/media/skip", media_skip_api)
    app.router.add_get("/api/da/callback", da_callback)

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
        log.info("starting adapter: %s", name)
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

    log.info("initializing bridge on http://%s:%d...", host, port)

    broadcaster = Broadcaster()
    tasks = spawn_adapters(config, broadcaster.broadcast)

    app = build_app(broadcaster, config)
    runner = web.AppRunner(app)
    await runner.setup()
    site = web.TCPSite(runner, host, port)
    await site.start()
    log.info("unified server ready at ws://%s:%d/events", host, port)

    await asyncio.gather(*tasks, asyncio.Event().wait())


if __name__ == "__main__":
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] [%(name)s] %(message)s",
        datefmt="%H:%M:%S"
    )
    # Silence repetitive HTTP polling access logs (such as GET /health every 3s)
    logging.getLogger("aiohttp.access").setLevel(logging.WARNING)

    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        pass