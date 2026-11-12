"""Media playback control, drisnya link resolver, and 7TV emote proxy routes."""

import aiohttp
from aiohttp import web


def register_media_routes(app: web.Application, broadcaster, config: dict) -> None:
    """Register media resolver, 7TV proxy, and skip control endpoints."""

    async def resolve_media_handler(request: web.Request) -> web.Response:
        url = request.query.get("url", "")
        if not url:
            return web.json_response({"url": ""}, headers={"Access-Control-Allow-Origin": "*"})
        from adapters.twitch_chat import resolve_drisnya_media

        resolved = await resolve_drisnya_media(url)
        return web.json_response({"url": resolved}, headers={"Access-Control-Allow-Origin": "*"})

    tc_cfg = config.get("twitch_chat", {})
    tv_source = str(tc_cfg.get("seven_tv_source", "direct")).strip().lower()
    tv_mirror = str(tc_cfg.get("seven_tv_mirror", "https://enhanced.jeetbot.cc")).strip().rstrip("/")

    async def get_7tv_config_handler(request: web.Request) -> web.Response:
        cdn = (
            "https://cdn.7tv.app/emote" if tv_source != "mirror" else f"{tv_mirror}/https://cdn.7tv.app/emote"
        )
        return web.json_response(
            {
                "source": tv_source,
                "cdnBase": cdn,
                "mirror": tv_mirror,
            },
            headers={"Access-Control-Allow-Origin": "*"},
        )

    async def proxy_7tv_global_handler(request: web.Request) -> web.Response:
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
                                },
                            )
            except Exception:
                pass
        return web.json_response({"emotes": []}, headers={"Access-Control-Allow-Origin": "*"})

    async def proxy_7tv_channel_handler(request: web.Request) -> web.Response:
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
                                },
                            )
            except Exception:
                pass
        return web.json_response({}, headers={"Access-Control-Allow-Origin": "*"})

    async def media_skip_handler(request: web.Request) -> web.Response:
        from adapters import donatex

        skipped = await donatex.skip_track()
        await broadcaster.broadcast({"type": "media_control", "action": "skip"})
        return web.json_response(
            {"ok": True, "donatex_skipped": skipped},
            headers={"Access-Control-Allow-Origin": "*"},
        )

    async def donation_skip_handler(request: web.Request) -> web.Response:
        from adapters import donatex, donationalerts

        await donatex.skip_donation()
        await donationalerts.skip_donation()
        await broadcaster.broadcast({"type": "alert_skip"})
        return web.json_response({"ok": True}, headers={"Access-Control-Allow-Origin": "*"})

    async def tts_stop_handler(request: web.Request) -> web.Response:
        await broadcaster.stop_tts()
        return web.json_response({"ok": True}, headers={"Access-Control-Allow-Origin": "*"})

    app.router.add_get("/api/resolve-media", resolve_media_handler)
    app.router.add_get("/api/7tv/config", get_7tv_config_handler)
    app.router.add_get("/api/7tv/global", proxy_7tv_global_handler)
    app.router.add_get("/api/7tv/channel/{room_id}", proxy_7tv_channel_handler)
    app.router.add_post("/api/media/skip", media_skip_handler)
    app.router.add_post("/api/donations/skip", donation_skip_handler)
    app.router.add_post("/api/tts/stop", tts_stop_handler)
