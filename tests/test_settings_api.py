import json
import pytest
from pathlib import Path
from aiohttp import web
from bridge.alerts_bridge import (
    Broadcaster,
    build_app,
    toml_escape,
    serialize_toml,
    get_sounds_catalog,
    save_sounds_catalog
)


def test_toml_escaping():
    assert toml_escape('hello "world"') == r'hello \"world\"'
    assert toml_escape("path\\to\\file") == r'path\\to\\file'
    assert toml_escape("line1\nline2") == "line1line2"
    assert toml_escape(None) == ""


def test_toml_serialization_roundtrip(tmp_path):
    cfg = {
        "server": {"host": "127.0.0.1", "port": 8787},
        "twitch_chat": {"enabled": True, "channel": "vokkiry", "seven_tv_source": "direct"},
        "twitch": {"enabled": False, "client_id": "test_id", "client_secret": "test_secret"},
        "donationalerts": {"enabled": False, "client_id": "da_id"},
        "donatex": {"enabled": True, "token": "dx_token"}
    }
    serialized = serialize_toml(cfg)
    assert 'channel = "vokkiry"' in serialized
    assert 'enabled = true' in serialized
    assert 'token = "dx_token"' in serialized


def test_sounds_catalog_save_and_load(tmp_path):
    src_dir = tmp_path / "src"
    sounds_dir = src_dir / "sounds"
    sounds_dir.mkdir(parents=True)

    # Place mock wav files
    (sounds_dir / "burn.wav").write_bytes(b"RIFFmock")
    (sounds_dir / "magic_sound.wav").write_bytes(b"RIFFmock")

    mapping = {
        "donate": "burn.wav",
        "follow": "magic_sound.wav"
    }

    data = save_sounds_catalog(src_dir, mapping)
    assert data["sounds"]["donate"]["file"] == "../sounds/burn.wav"
    assert data["sounds"]["follow"]["file"] == "../sounds/magic_sound.wav"

    catalog = get_sounds_catalog(src_dir)
    assert "burn.wav" in catalog["available_files"]
    assert "magic_sound.wav" in catalog["available_files"]
    assert catalog["mapping"]["donate"] == "burn.wav"
    assert catalog["mapping"]["follow"] == "magic_sound.wav"


@pytest.mark.asyncio
async def test_notify_endpoint_and_test_alerts(aiohttp_client):
    b = Broadcaster()
    config = {
        "server": {"host": "127.0.0.1", "port": 8787},
        "twitch_chat": {"enabled": False},
        "twitch": {"enabled": False},
        "donationalerts": {"enabled": False},
        "donatex": {"enabled": False}
    }
    app = build_app(b, config, enable_settings=True)
    client = await aiohttp_client(app)

    # Check health
    res = await client.get("/health")
    assert res.status == 200
    health_data = await res.json()
    assert health_data["status"] == "running"

    # Fire test donate alert as done from /settings
    donate_payload = {
        "type": "alert",
        "kind": "donate",
        "user": "system_dev",
        "amount": "500 ₽",
        "message": "Тестовый донат из панели настроек"
    }
    headers = {"Referer": "http://127.0.0.1:8787/settings"}
    res_notify = await client.post("/notify", json=donate_payload, headers=headers)
    assert res_notify.status == 200
    notify_data = await res_notify.json()
    assert notify_data.get("ok") is True
