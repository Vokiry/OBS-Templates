"""Integration tests for media player endpoints and System Doctor reporting."""

from __future__ import annotations

import pytest
from aiohttp.test_utils import TestClient

from bridge.alerts_bridge import Broadcaster, build_app
from bridge.services.media_service import DummyMediaTracker, MediaService


@pytest.fixture
async def media_client(aiohttp_client) -> TestClient:
    broadcaster = Broadcaster()
    tracker = DummyMediaTracker(lambda s: None)
    config = {
        "server": {"host": "127.0.0.1", "port": 8787},
        "media": {"enabled": True, "player": "auto", "auto_pause": True},
    }
    media_service = MediaService(broadcaster, config, tracker=tracker)
    tracker.on_update = media_service._handle_tracker_update
    await tracker.start()

    app = build_app(
        broadcaster=broadcaster,
        config=config,
        enable_settings=True,
        media_service=media_service,
    )
    return await aiohttp_client(app)


@pytest.mark.asyncio
async def test_media_status_endpoint(media_client: TestClient) -> None:
    resp = await media_client.get("/api/media/status")
    assert resp.status == 200
    data = await resp.json()
    assert data["enabled"] is True
    assert data["mode"] == "local"
    assert data["track"]["title"] == "Mock Title"
    assert data["track"]["status"] == "Playing"


@pytest.mark.asyncio
async def test_media_control_endpoint(media_client: TestClient) -> None:
    # Test pause
    resp = await media_client.post(
        "/api/media/control", json={"action": "pause"}, headers={"Referer": str(media_client.make_url("/dock"))}
    )
    assert resp.status == 200
    data = await resp.json()
    assert data["ok"] is True

    # Verify state updated
    status_resp = await media_client.get("/api/media/status")
    status_data = await status_resp.json()
    assert status_data["track"]["status"] == "Paused"

    # Test play
    resp = await media_client.post(
        "/api/media/control", json={"action": "play"}, headers={"Referer": str(media_client.make_url("/dock"))}
    )
    assert resp.status == 200
    status_resp = await media_client.get("/api/media/status")
    status_data = await status_resp.json()
    assert status_data["track"]["status"] == "Playing"


@pytest.mark.asyncio
async def test_media_doctor_diagnostics(media_client: TestClient) -> None:
    resp = await media_client.get("/api/doctor")
    assert resp.status == 200
    data = await resp.json()
    assert "media" in data
    med = data["media"]
    assert med["enabled"] is True
    assert med["status"] == "Playing"
    assert med["track"] == "Mock Artist — Mock Title"


@pytest.mark.asyncio
async def test_media_cover_endpoint_no_cover(media_client: TestClient) -> None:
    # Dummy tracker has no cover -> returns 404
    resp = await media_client.get("/api/media/cover")
    assert resp.status == 404
