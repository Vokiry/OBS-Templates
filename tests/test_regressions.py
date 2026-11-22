"""Regression tests for security and lifecycle defects found during the full review."""

import asyncio
import io
import json
import stat
import zipfile
from unittest.mock import AsyncMock

import pytest
from aiohttp import FormData, web

from bridge.adapters import donatex, donationalerts
from bridge.alerts_bridge import Broadcaster, build_app, yandex_tts
from bridge.core.media_coordinator import MediaCoordinator
from bridge.services import backup_service
from bridge.services.backup_service import restore_backup_zip
from bridge.services.media_service import DummyMediaTracker, MediaService


def referer(client, path="/settings"):
    return {"Referer": str(client.make_url(path))}


@pytest.mark.asyncio
async def test_config_secrets_are_masked_and_preserved(aiohttp_client, tmp_path):
    config_path = tmp_path / "config.toml"
    config_path.write_text("[server]\nport=8787\n")
    config = {
        "server": {"host": "127.0.0.1", "port": 8787},
        "twitch": {"client_id": "public-id", "client_secret": "TW_SECRET"},
        "donationalerts": {"client_secret": "DA_SECRET", "access_token": "DA_TOKEN"},
        "donatex": {"token": "DX_TOKEN"},
        "tts": {"auth_token": "TTS_TOKEN"},
    }
    client = await aiohttp_client(build_app(Broadcaster(), config, enable_settings=True, config_path=config_path))

    assert (await client.get("/api/config")).status == 401
    assert (await client.get("/api/config", headers={"Referer": "http://localhost/"})).status == 401
    response = await client.get("/api/config", headers=referer(client))
    assert response.status == 200
    assert "Access-Control-Allow-Origin" not in response.headers
    body = await response.text()
    for secret in ("TW_SECRET", "DA_SECRET", "DA_TOKEN", "DX_TOKEN", "TTS_TOKEN"):
        assert secret not in body
    public = json.loads(body)["config"]
    assert public["twitch"]["client_secret"] == "********"
    assert public["donationalerts"]["access_token"] == "********"

    # Masked fields are omitted by the frontend; unchanged secrets survive serialization.
    save = await client.post("/api/config", json={"twitch": {"client_id": "new-id"}}, headers=referer(client))
    assert save.status == 200
    assert config["twitch"]["client_secret"] == "TW_SECRET"
    assert config["donationalerts"]["access_token"] == "DA_TOKEN"
    assert "TW_SECRET" in config_path.read_text()
    assert stat.S_IMODE(config_path.stat().st_mode) == 0o600


@pytest.mark.asyncio
async def test_external_mode_requires_bearer_even_with_spoofed_referer(aiohttp_client):
    from core.security import set_api_key

    set_api_key("session-secret", require_for_external=True)
    try:
        client = await aiohttp_client(build_app(Broadcaster(), {}, enable_settings=True))
        spoofed = {"Referer": str(client.make_url("/settings"))}
        assert (await client.post("/notify", json={"type": "chat_clear"}, headers=spoofed)).status == 401
        authorized = {**spoofed, "Authorization": "Bearer session-secret"}
        assert (await client.post("/notify", json={"type": "chat_clear"}, headers=authorized)).status == 200
    finally:
        set_api_key("")


@pytest.mark.asyncio
async def test_spoofed_host_and_matching_referer_are_rejected(aiohttp_client, tmp_path):
    client = await aiohttp_client(
        build_app(Broadcaster(), {}, enable_settings=True, config_path=tmp_path / "config.toml")
    )
    headers = {"Host": "attacker.example", "Referer": "http://attacker.example/settings"}
    assert (await client.post("/notify", json={"type": "chat_clear"}, headers=headers)).status == 401
    assert (await client.get("/api/backup/export", headers=headers)).status == 401
    ws_headers = {"Host": "attacker.example", "Origin": "http://attacker.example"}
    assert (await client.get("/events", headers=ws_headers)).status == 403


@pytest.mark.asyncio
async def test_media_control_rejects_cross_origin_form(aiohttp_client):
    broadcaster = Broadcaster()
    tracker = DummyMediaTracker(lambda state: None)
    service = MediaService(broadcaster, {"media": {"enabled": True}}, tracker=tracker)
    tracker.on_update = service._handle_tracker_update
    await tracker.start()
    client = await aiohttp_client(build_app(broadcaster, {"media": {"enabled": True}}, media_service=service))
    response = await client.post(
        "/api/media/control",
        data={"anything": "x"},
        headers={"Origin": "https://attacker.example", "Referer": "https://attacker.example/form"},
    )
    assert response.status == 401
    assert service.last_track_state["status"] == "Playing"


@pytest.mark.asyncio
async def test_websocket_requires_authorization_for_control(aiohttp_client):
    broadcaster = Broadcaster()
    app = web.Application()
    app.router.add_get("/events", broadcaster.attach)
    client = await aiohttp_client(app)

    async with client.ws_connect("/events") as socket:
        await socket.send_str(json.dumps({"type": "dnd_control", "active": True}))
        await asyncio.sleep(0.03)
        assert broadcaster.dnd_active is False

    origin = str(client.make_url("/")).rstrip("/")
    async with client.ws_connect("/events", headers={"Origin": origin}) as socket:
        await socket.send_str(json.dumps({"type": "dnd_control", "active": True}))
        message = json.loads(await socket.receive_str())
        assert message == {"type": "dnd_status", "active": True}
        assert broadcaster.dnd_active is True


@pytest.mark.asyncio
async def test_http_dnd_replay_and_donation_goal_exclusions(aiohttp_client, tmp_path):
    broadcaster = Broadcaster()
    client = await aiohttp_client(
        build_app(broadcaster, {}, enable_settings=True, config_path=tmp_path / "config.toml")
    )
    await broadcaster.broadcast({"type": "goal_update", "enabled": True})
    broadcaster.init_goal({"enabled": True, "current": 0, "target": 1000})
    headers = referer(client, "/dock")

    real = {"type": "alert", "kind": "donate", "title": "DONATION", "amount": "100 RUB"}
    assert (await client.post("/notify", json=real, headers=headers)).status == 200
    assert broadcaster.goal_config["current"] == 100
    assert (await client.post("/notify", json={"type": "alert_replay"}, headers=headers)).status == 200
    assert broadcaster.last_alert["is_replay"] is True
    assert broadcaster.goal_config["current"] == 100

    for marker in ({"isTest": True}, {"isRerun": True}):
        await client.post("/notify", json={**real, **marker}, headers=headers)
        assert broadcaster.goal_config["current"] == 100

    assert (await client.post("/notify", json={"type": "dnd_control", "active": True}, headers=headers)).status == 200
    assert broadcaster.dnd_active is True
    health = await (await client.get("/health")).json()
    assert health["dnd_active"] is True


@pytest.mark.asyncio
async def test_back_to_back_tts_enqueues_share_one_worker(monkeypatch):
    broadcaster = Broadcaster()
    broadcaster.init_tts({"mode": "all"})
    active = maximum_active = calls = 0
    release = asyncio.Event()

    async def fake_generate(**kwargs):
        nonlocal active, maximum_active, calls
        active += 1
        calls += 1
        maximum_active = max(maximum_active, active)
        await release.wait()
        active -= 1
        return None

    monkeypatch.setattr(yandex_tts, "generate", fake_generate)
    broadcaster.enqueue_tts("one", "first")
    broadcaster.enqueue_tts("two", "second")
    await asyncio.sleep(0.02)
    assert calls == 1
    assert maximum_active == 1
    release.set()
    await asyncio.sleep(0.05)
    assert calls == 2
    assert maximum_active == 1
    assert broadcaster._tts_worker_task is None


@pytest.mark.asyncio
async def test_stop_tts_suppresses_result_even_if_generation_ignores_cancellation(monkeypatch):
    broadcaster = Broadcaster()
    broadcaster.init_tts({"mode": "all"})
    started = asyncio.Event()
    release = asyncio.Event()
    events = []

    async def fake_generate(**kwargs):
        started.set()
        try:
            await release.wait()
        except asyncio.CancelledError:
            pass
        return b"audio"

    original_broadcast = broadcaster.broadcast

    async def recording(payload):
        events.append(payload["type"])
        await original_broadcast(payload)

    broadcaster.broadcast = recording
    monkeypatch.setattr(yandex_tts, "generate", fake_generate)
    broadcaster.enqueue_tts("reviewer", "test")
    await asyncio.wait_for(started.wait(), 1)
    await broadcaster.stop_tts()
    release.set()
    await asyncio.sleep(0.05)
    assert events == ["tts_stop"]
    assert broadcaster._tts_worker_task is None


def make_archive(config: bytes, extra: dict[str, bytes] | None = None) -> bytes:
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w", zipfile.ZIP_DEFLATED) as archive:
        archive.writestr("config.toml", config)
        for name, content in (extra or {}).items():
            archive.writestr(name, content)
    return buffer.getvalue()


def test_backup_rejects_invalid_toml_without_touching_files(tmp_path):
    config_path = tmp_path / "config.toml"
    config_path.write_text("[server]\nport=8787\n")
    original = config_path.read_bytes()
    data = make_archive(b"not = [valid", {"sounds/sounds.json": b'{"masterVolume": 0.1}'})
    with pytest.raises(ValueError, match="invalid config.toml"):
        restore_backup_zip(data, tmp_path, config_path, tmp_path / "backup.toml", tmp_path / "src")
    assert config_path.read_bytes() == original
    assert not (tmp_path / "src" / "sounds" / "sounds.json").exists()


def test_backup_rejects_semantically_invalid_goal_without_touching_files(tmp_path):
    config_path = tmp_path / "config.toml"
    config_path.write_text("[server]\nport=8787\n")
    original = config_path.read_bytes()
    data = make_archive(b'[goal]\ncurrent = "not-a-number"\n')
    with pytest.raises(ValueError, match="goal.current"):
        restore_backup_zip(data, tmp_path, config_path, tmp_path / "backup.toml", tmp_path / "src")
    assert config_path.read_bytes() == original


def test_backup_rejects_excessive_uncompressed_size(tmp_path, monkeypatch):
    monkeypatch.setattr(backup_service, "MAX_TOTAL_UNCOMPRESSED_BYTES", 8)
    data = make_archive(b"[server]\nport=8787\n")
    with pytest.raises(ValueError, match="uncompressed"):
        restore_backup_zip(data, tmp_path, tmp_path / "config.toml", tmp_path / "backup.toml", tmp_path / "src")


@pytest.mark.asyncio
async def test_multipart_above_old_one_mib_limit_reaches_validation(aiohttp_client, tmp_path):
    client = await aiohttp_client(
        build_app(Broadcaster(), {}, enable_settings=True, config_path=tmp_path / "config.toml")
    )
    form = FormData()
    form.add_field("file", b"0" * (2 * 1024 * 1024), filename="large.zip", content_type="application/zip")
    response = await client.post("/api/backup/import", data=form, headers=referer(client))
    assert response.status == 400
    assert response.status != 413
    assert "invalid zip" in (await response.json())["error"]


@pytest.mark.asyncio
async def test_backup_runtime_failure_rolls_back_files_and_config(aiohttp_client, tmp_path):
    config_path = tmp_path / "config.toml"
    original_text = "[server]\nhost = \"127.0.0.1\"\nport = 8787\n"
    config_path.write_text(original_text)

    class FailingReload:
        def __init__(self):
            self.calls = 0

        async def reload_if_changed(self, config):
            self.calls += 1
            if self.calls == 1:
                raise RuntimeError("simulated apply failure")

    manager = FailingReload()
    old_config = {"server": {"host": "127.0.0.1", "port": 8787}}
    broadcaster = Broadcaster()
    client = await aiohttp_client(
        build_app(
            broadcaster, old_config, enable_settings=True, adapter_mgr=manager, config_path=config_path
        )
    )
    archive = make_archive(
        b"[server]\nhost = \"127.0.0.1\"\nport = 8787\n[goal]\ncurrent = 10.0\ntarget = 100.0\n"
        b"[appearance]\ntheme = \"mocha-harmony\"\n"
    )
    form = FormData()
    form.add_field("file", archive, filename="backup.zip", content_type="application/zip")
    response = await client.post("/api/backup/import", data=form, headers=referer(client))
    assert response.status == 500
    assert config_path.read_text() == original_text
    assert old_config == {"server": {"host": "127.0.0.1", "port": 8787}}
    assert broadcaster.current_theme == "mocha-teal"
    assert manager.calls == 2


@pytest.mark.asyncio
async def test_media_settings_are_applied_live(aiohttp_client, tmp_path):
    broadcaster = Broadcaster()
    tracker = DummyMediaTracker(lambda state: None)
    config = {"media": {"enabled": False, "auto_pause": False, "show_lyrics": False}}
    service = MediaService(broadcaster, config, tracker=tracker)
    tracker.on_update = service._handle_tracker_update
    coordinator = MediaCoordinator(service, broadcaster, auto_pause=False)
    client = await aiohttp_client(
        build_app(
            broadcaster,
            config,
            enable_settings=True,
            config_path=tmp_path / "config.toml",
            media_service=service,
            media_coordinator=coordinator,
        )
    )
    response = await client.post(
        "/api/config",
        json={"media": {"enabled": True, "auto_pause": True, "show_lyrics": True, "youtube_domain": "youtube.com"}},
        headers=referer(client),
    )
    assert response.status == 200
    assert service.enabled is True
    assert tracker.is_running is True
    assert coordinator.auto_pause_enabled is True
    media_config = await (await client.get("/api/media/config")).json()
    assert media_config == {"youtubeDomain": "youtube.com", "configured": True}
    await service.stop()


@pytest.mark.asyncio
async def test_show_lyrics_false_disables_fetch():
    broadcaster = Broadcaster()
    lyrics = AsyncMock()
    lyrics.get_lyrics = AsyncMock()
    tracker = DummyMediaTracker(lambda state: None)
    service = MediaService(
        broadcaster,
        {"media": {"enabled": True, "show_lyrics": False}},
        lyrics_service=lyrics,
        tracker=tracker,
    )
    tracker.on_update = service._handle_tracker_update
    await tracker.start()
    await asyncio.sleep(0.02)
    assert service._lyrics_fetch_task is None
    lyrics.get_lyrics.assert_not_called()
    await service.stop()


@pytest.mark.asyncio
async def test_media_queue_and_previous_pause_state():
    broadcaster = Broadcaster()
    tracker = DummyMediaTracker(lambda state: None)
    service = MediaService(broadcaster, {"media": {"enabled": True}}, tracker=tracker)
    tracker.on_update = service._handle_tracker_update
    await tracker.start()
    coordinator = MediaCoordinator(service, broadcaster, auto_pause=True)

    await coordinator.handle_media_request_started({"youtubeId": "first", "user": "one"})
    await coordinator.handle_media_request_started({"youtubeId": "second", "user": "two"})
    assert service.last_track_state["status"] == "Paused"
    await coordinator.handle_media_request_ended()
    assert coordinator.current_mode == "request"
    assert coordinator.request_queue_len == 1
    assert broadcaster.last_media_request["youtubeId"] == "second"
    assert service.last_track_state["status"] == "Paused"
    await coordinator.handle_media_request_ended()
    assert coordinator.current_mode == "local"
    assert service.last_track_state["status"] == "Playing"

    await service.pause()
    await coordinator.handle_media_request_started({"youtubeId": "third"})
    await coordinator.handle_media_request_ended()
    assert service.last_track_state["status"] == "Paused"
    await service.stop()


@pytest.mark.asyncio
async def test_stale_completion_and_duplicate_video_requests():
    broadcaster = Broadcaster()
    coordinator = MediaCoordinator(None, broadcaster)
    first = {"requestId": "a", "donationId": "a", "youtubeId": "same-video"}
    second = {"requestId": "b", "donationId": "b", "youtubeId": "same-video"}
    await coordinator.handle_media_request_started(first)
    await coordinator.handle_media_request_started(second)
    await coordinator.handle_media_request_started(first)
    assert coordinator.request_queue_len == 2
    assert await coordinator.handle_media_request_ended("a", "a") is True
    assert broadcaster.last_media_request["requestId"] == "b"
    assert await coordinator.handle_media_request_ended("a", "a") is False
    assert coordinator.request_queue_len == 1
    assert await coordinator.handle_media_request_ended("b", "b") is True
    assert coordinator.current_mode == "local"


@pytest.mark.asyncio
async def test_skip_and_natural_finish_cannot_remove_two_requests(monkeypatch):
    from adapters import donatex as runtime_donatex

    release = asyncio.Event()

    async def slow_skip(donation_id=None):
        await release.wait()
        return False

    monkeypatch.setattr(runtime_donatex, "skip_track", slow_skip)
    broadcaster = Broadcaster()
    coordinator = MediaCoordinator(None, broadcaster)
    broadcaster.media_coordinator = coordinator
    await coordinator.handle_media_request_started({"requestId": "a", "donationId": "a"})
    await coordinator.handle_media_request_started({"requestId": "b", "donationId": "b"})
    skip_task = asyncio.create_task(coordinator.skip_current())
    await asyncio.sleep(0)
    natural_task = asyncio.create_task(coordinator.handle_media_request_ended("a", "a"))
    release.set()
    await asyncio.gather(skip_task, natural_task)
    await asyncio.sleep(0.03)
    assert coordinator.request_queue_len == 1
    assert broadcaster.last_media_request["requestId"] == "b"
    result = await skip_task
    assert result == {"ok": True, "donatex_skipped": False, "scope": "request"}


@pytest.mark.asyncio
async def test_auto_pause_restore_uses_captured_state():
    broadcaster = Broadcaster()
    tracker = DummyMediaTracker(lambda state: None)
    service = MediaService(broadcaster, {"media": {"enabled": True}}, tracker=tracker)
    tracker.on_update = service._handle_tracker_update
    await tracker.start()
    coordinator = MediaCoordinator(service, broadcaster, auto_pause=True)
    await coordinator.handle_media_request_started({"requestId": "a"})
    assert service.last_track_state["status"] == "Paused"
    coordinator.auto_pause_enabled = False
    await coordinator.handle_media_request_ended("a")
    assert service.last_track_state["status"] == "Playing"
    await service.stop()


class FakeResponse:
    def __init__(self, status=200, payload=None):
        self.status = status
        self.payload = payload or {}

    async def __aenter__(self):
        return self

    async def __aexit__(self, *args):
        return None

    async def json(self):
        return self.payload

    async def text(self):
        return ""


@pytest.mark.asyncio
async def test_donatex_successful_rest_skip_does_not_use_signalr(monkeypatch):
    calls = []

    class FakeSession:
        def __init__(self, *args, **kwargs):
            pass

        async def __aenter__(self):
            return self

        async def __aexit__(self, *args):
            return None

        def post(self, url, **kwargs):
            calls.append(url)
            return FakeResponse(200)

    class FakeSocket:
        closed = False

        async def send_str(self, value):
            raise AssertionError("SignalR fallback must not run after a successful REST skip")

    monkeypatch.setattr(donatex.aiohttp, "ClientSession", FakeSession)
    adapter = donatex.DonateXAdapter("token", AsyncMock())
    adapter.widget_id = "widget"
    adapter.current_donation_id = "donation"
    adapter.music_ws = FakeSocket()
    assert await adapter.skip_current_track() is True
    assert calls == [donatex.MUSIC_SKIP_API]


@pytest.mark.asyncio
async def test_donationalerts_refresh_replaces_stale_configured_token(monkeypatch, tmp_path):
    token_file = tmp_path / "da.json"
    token_file.write_text('{"refresh_token": "refresh", "access_token": "old"}')
    monkeypatch.setattr(donationalerts, "TOKEN_FILE", token_file)
    monkeypatch.setattr(
        donationalerts,
        "refresh_da_token",
        AsyncMock(return_value={"access_token": "new", "refresh_token": "refresh"}),
    )
    seen = []

    class FakeAdapter:
        def __init__(self, token, broadcast):
            seen.append(token)

        async def run(self):
            if seen[-1] == "old":
                raise ValueError("HTTP 401")
            asyncio.current_task().cancel()
            await asyncio.sleep(0)

    monkeypatch.setattr(donationalerts, "DonationAlertsAdapter", FakeAdapter)
    with pytest.raises(asyncio.CancelledError):
        await donationalerts.run(
            {"access_token": "old", "client_id": "id", "client_secret": "secret"}, AsyncMock()
        )
    assert seen == ["old", "new"]


def test_missing_config_has_nonzero_exit_code():
    import subprocess
    import sys

    result = subprocess.run(
        [sys.executable, "bridge/alerts_bridge.py", "--config", "/tmp/definitely-missing-obs-config.toml"],
        capture_output=True,
        timeout=10,
        check=False,
    )
    assert result.returncode == 1
