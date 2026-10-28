import asyncio
import json
import pytest
from aiohttp import web
from bridge.alerts_bridge import Broadcaster


@pytest.mark.asyncio
async def test_broadcaster_chat_history_buffer():
    b = Broadcaster()
    assert len(b.chat_history) == 0

    # Add 35 chat messages
    for i in range(35):
        await b.broadcast({
            "type": "chat",
            "user": f"user_{i}",
            "text": f"message {i}"
        })

    # Circular buffer maxlen=30: only the last 30 messages should remain
    assert len(b.chat_history) == 30
    assert b.chat_history[0]["user"] == "user_5"
    assert b.chat_history[-1]["user"] == "user_34"

    # chat_clear should wipe the buffer
    await b.broadcast({"type": "chat_clear"})
    assert len(b.chat_history) == 0


@pytest.mark.asyncio
async def test_broadcaster_caches_and_delivers_on_attach(aiohttp_client):
    b = Broadcaster()
    b.last_sounds_config = {"type": "sounds_update", "masterVolume": 0.8, "sounds": {}}
    await b.broadcast({"type": "chat", "user": "voki", "text": "hello stream"})

    app = web.Application()

    async def ws_handler(request):
        return await b.attach(request)

    app.router.add_get("/events", ws_handler)
    client = await aiohttp_client(app)

    async with client.ws_connect("/events") as ws:
        # Client should receive cached sounds_update and chat_history
        received_types = []
        for _ in range(2):
            raw = await ws.receive_str()
            data = json.loads(raw)
            received_types.append(data.get("type"))

        assert "sounds_update" in received_types
        assert "chat_history" in received_types


@pytest.mark.asyncio
async def test_broadcaster_connection_limit(aiohttp_client):
    b = Broadcaster()
    # Force client set to 50
    b.clients = set(range(50))

    app = web.Application()
    async def ws_handler(request):
        return await b.attach(request)

    app.router.add_get("/events", ws_handler)
    client = await aiohttp_client(app)

    # 51st client should receive HTTP 503
    resp = await client.get("/events")
    assert resp.status == 503
    text = await resp.text()
    assert "Too many connections" in text
