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


@pytest.mark.asyncio
async def test_broadcaster_cswsh_origin_protection(aiohttp_client):
    b = Broadcaster()
    app = web.Application()
    app.router.add_get("/events", b.attach)
    client = await aiohttp_client(app)

    # 1. Foreign origin must be rejected with 403 Forbidden
    evil_resp = await client.get("/events", headers={"Origin": "http://evil-hacker.com"})
    assert evil_resp.status == 403
    assert "Origin not allowed" in (await evil_resp.text())

    # 2. Localhost origin must be allowed
    async with client.ws_connect("/events", headers={"Origin": "http://localhost:8787"}) as ws:
        assert not ws.closed

    # 3. No origin (OBS Browser Source native) must be allowed
    async with client.ws_connect("/events") as ws:
        assert not ws.closed


@pytest.mark.asyncio
async def test_broadcaster_client_events_handling(aiohttp_client):
    b = Broadcaster()
    b.init_tts({"mode": "all"})
    # Put something in TTS queue
    b._tts_queue.append({"username": "u1", "text": "t1", "voice": "ermil", "show_card": False})
    assert len(b._tts_queue) == 1

    app = web.Application()
    app.router.add_get("/events", b.attach)
    client = await aiohttp_client(app)

    async with client.ws_connect("/events") as ws:
        # Client sends tts_stop event
        await ws.send_str(json.dumps({"type": "tts_stop"}))
        await asyncio.sleep(0.05)
        # TTS queue must be cleared
        assert len(b._tts_queue) == 0
