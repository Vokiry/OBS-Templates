import json
import pytest
from aiohttp import web
from bridge.alerts_bridge import Broadcaster, build_app
from bridge.adapters.base import normalize


def test_normalize_stream_stats():
    payload = {
        "type": "stream_stats",
        "live": True,
        "viewers": 42,
        "chatters": 35,
        "started_at": "2026-10-29T18:00:00Z"
    }
    assert normalize(payload) == payload


@pytest.mark.asyncio
async def test_stream_stats_caching_and_delivery(aiohttp_client):
    b = Broadcaster()
    stats_event = {
        "type": "stream_stats",
        "live": True,
        "viewers": 42,
        "chatters": 35,
        "started_at": "2026-10-29T18:00:00Z"
    }
    await b.broadcast(stats_event)
    assert b.last_stream_stats == stats_event

    config = {
        "server": {"host": "127.0.0.1", "port": 8787},
        "twitch_chat": {"enabled": False},
        "twitch": {"enabled": False},
        "donationalerts": {"enabled": False},
        "donatex": {"enabled": False}
    }
    app = build_app(b, config, enable_settings=False)
    client = await aiohttp_client(app)

    # Health endpoint must return stream_stats
    res = await client.get("/health")
    assert res.status == 200
    data = await res.json()
    assert data["stream_stats"] == stats_event
    assert data["stream_stats"]["viewers"] == 42
    assert data["stream_stats"]["chatters"] == 35

    # WebSocket client must receive stream_stats immediately on connect
    async with client.ws_connect("/events") as ws:
        received = False
        for _ in range(3):
            raw = await ws.receive_str()
            msg = json.loads(raw)
            if msg.get("type") == "stream_stats":
                received = True
                assert msg["live"] is True
                assert msg["viewers"] == 42
                assert msg["chatters"] == 35
                break
        assert received, "Expected stream_stats on WebSocket attach"
