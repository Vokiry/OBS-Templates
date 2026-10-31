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

    data = save_sounds_catalog(src_dir, mapping, master_volume=0.85)
    assert data["sounds"]["donate"]["file"] == "../sounds/burn.wav"
    assert data["sounds"]["follow"]["file"] == "../sounds/magic_sound.wav"
    assert data["masterVolume"] == 0.85

    catalog = get_sounds_catalog(src_dir)
    assert "burn.wav" in catalog["available_files"]
    assert "magic_sound.wav" in catalog["available_files"]
    assert catalog["mapping"]["donate"] == "burn.wav"
    assert catalog["mapping"]["follow"] == "magic_sound.wav"
    assert catalog["masterVolume"] == 0.85


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


@pytest.mark.asyncio
async def test_hot_reload_adapters_and_settings(aiohttp_client, tmp_path):
    from bridge.alerts_bridge import AdapterManager
    b = Broadcaster()
    b.init_tts({"mode": "all", "volume": 0.8, "speed": "1.0"})
    
    config = {
        "server": {"host": "127.0.0.1", "port": 8787},
        "twitch_chat": {"enabled": False, "channel": "old_channel"},
        "twitch": {"enabled": False},
        "donationalerts": {"enabled": False},
        "donatex": {"enabled": False},
        "goal": {"enabled": True, "title": "Старый сбор", "current": 0.0, "target": 5000.0},
        "tts": {"mode": "all", "volume": 0.8, "speed": "1.0"}
    }
    
    mgr = AdapterManager(b.broadcast)
    await mgr.start_all(config)
    
    test_cfg_path = tmp_path / "test_config.toml"
    test_cfg_path.write_text("[server]\nhost = \"127.0.0.1\"\nport = 8787\n")
    app = build_app(b, config, enable_settings=True, adapter_mgr=mgr, config_path=test_cfg_path)
    client = await aiohttp_client(app)
    
    headers = {"Referer": "http://127.0.0.1:8787/settings"}
    save_payload = {
        "goal": {"enabled": True, "title": "Новый сбор", "current": 100.0, "target": 10000.0},
        "tts": {"mode": "all", "volume": 0.45, "speed": "1.2"},
        "twitch_chat": {"enabled": False, "channel": "new_streamer"}
    }
    
    res = await client.post("/api/config", json=save_payload, headers=headers)
    assert res.status == 200
    res_data = await res.json()
    assert res_data.get("ok") is True
    
    # 1. Goal updated live
    assert b.last_goal["title"] == "Новый сбор"
    assert b.last_goal["target"] == 10000.0
    
    # 2. TTS volume and speed updated live
    assert b.tts_config["volume"] == 0.45
    assert b.tts_config["speed"] == "1.2"
    
    # 3. Adapter manager updated config live without server restart
    assert mgr.configs["twitch_chat"]["channel"] == "new_streamer"
    
    await mgr.stop_all()
