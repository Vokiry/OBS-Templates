"""WebSocket event streaming and notification endpoints."""

import logging

from aiohttp import web

log = logging.getLogger("bridge.routes.events")


def register_events_routes(app: web.Application, broadcaster) -> None:
    """Register /events (WebSocket) and /notify (HTTP alert dispatch) endpoints."""

    async def events_handler(request: web.Request) -> web.WebSocketResponse:
        return await broadcaster.attach(request)

    async def notify_handler(request: web.Request) -> web.Response:
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
        elif payload.get("type") == "alert_skip":
            from adapters import donatex, donationalerts

            await donatex.skip_donation()
            await donationalerts.skip_donation()
        elif payload.get("type") == "tts_stop":
            await broadcaster.stop_tts()
            return web.json_response({"ok": True})
        elif payload.get("type") == "tts_test":
            broadcaster.enqueue_tts(
                username=payload.get("user", "Tester"),
                text=payload.get("text", "Проверка синтеза речи."),
                force=True,
                force_voice=payload.get("voice"),
                force_speed=payload.get("speed"),
                force_emotion=payload.get("emotion"),
            )
            return web.json_response({"ok": True})

        await broadcaster.broadcast(payload)
        return web.json_response({"ok": True})

    app.router.add_get("/events", events_handler)
    app.router.add_post("/notify", notify_handler)
