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
async def test_upload_sound_api_validation(aiohttp_client):
    b = Broadcaster()
    app = build_app(b, {"server": {"host": "127.0.0.1", "port": 8787}}, enable_settings=True)
    client = await aiohttp_client(app)
    headers = {"Referer": "http://127.0.0.1:8787/settings"}

    # 1. Disallowed format (.exe) must be rejected with 400
    from aiohttp import FormData
    data = FormData()
    data.add_field("file", b"fake binary", filename="malicious.exe", content_type="application/octet-stream")
    res = await client.post("/api/sounds/upload", data=data, headers=headers)
    assert res.status == 400
    res_json = await res.json()
    assert "unsupported audio format" in res_json["error"]

    # 2. No file provided must be rejected with 400
    empty_data = FormData()
    res = await client.post("/api/sounds/upload", data=empty_data, headers=headers)
    assert res.status == 400


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


@pytest.mark.asyncio
async def test_panels_redirect_route(aiohttp_client):
    b = Broadcaster()
    app = build_app(b, {"server": {"host": "127.0.0.1", "port": 8787}}, enable_settings=True)
    client = await aiohttp_client(app)

    res = await client.get("/panels", allow_redirects=False)
    assert res.status == 302
    assert res.headers.get("Location") == "/src/panels/index.html"

    # Verify static panels files are served
    res_html = await client.get("/src/panels/index.html")
    assert res_html.status == 200
    assert "TWITCH PANELS" in (await res_html.text())

    res_css = await client.get("/src/panels/panels.css")
    assert res_css.status == 200

@pytest.mark.asyncio
async def test_system_doctor_api(aiohttp_client):
    from bridge.alerts_bridge import AdapterManager
    b = Broadcaster()
    b.init_tts({"mode": "all", "voice": "shitova.us", "volume": 0.8})

    config = {
        "server": {"host": "127.0.0.1", "port": 8787},
        "twitch_chat": {"enabled": True, "channel": "test_ch", "fade_seconds": 60},
        "twitch": {"enabled": False},
        "donationalerts": {"enabled": False},
        "donatex": {"enabled": False},
        "tts": {"mode": "all", "voice": "shitova.us", "volume": 0.8}
    }
    mgr = AdapterManager(b.broadcast)
    await mgr.start_all(config)

    app = build_app(b, config, enable_settings=True, adapter_mgr=mgr)
    client = await aiohttp_client(app)

    res = await client.get("/api/doctor")
    assert res.status == 200
    d = await res.json()

    assert d["status"] == "ok"
    assert d["server"]["port"] == 8787
    assert d["twitch_chat"]["channel"] == "test_ch"
    assert d["twitch_chat"]["fade_seconds"] == 60
    assert d["tts"]["mode"] == "all"
    assert d["tts"]["voice"] == "shitova.us"
    assert "overlays" in d
    assert "sounds" in d

    await mgr.stop_all()

@pytest.mark.asyncio
async def test_backup_export_and_import(aiohttp_client, tmp_path):
    import io
    import zipfile
    from aiohttp import FormData
    b = Broadcaster()

    # Isolated test config path
    test_cfg = tmp_path / "test_config.toml"
    test_cfg.write_text("[server]\nhost = \"127.0.0.1\"\nport = 8787\n[twitch_chat]\nchannel = \"backup_streamer\"\n", encoding="utf-8")

    app = build_app(b, {"server": {"host": "127.0.0.1", "port": 8787}}, enable_settings=True, config_path=test_cfg)
    client = await aiohttp_client(app)
    headers = {"Referer": "http://127.0.0.1:8787/settings"}

    # 1. Export backup zip
    res = await client.get("/api/backup/export")
    assert res.status == 200
    assert "application/zip" in res.headers.get("Content-Type", "")
    assert "SYSTEM_Backup_" in res.headers.get("Content-Disposition", "")

    zip_bytes = await res.read()
    with zipfile.ZipFile(io.BytesIO(zip_bytes), "r") as z:
        names = z.namelist()
        assert "config.toml" in names
        assert "sounds/sounds.json" in names
        assert "obs/SYSTEM_Scene_Collection.json" in names

    # 2. Test import malicious path traversal rejected
    bad_buf = io.BytesIO()
    with zipfile.ZipFile(bad_buf, "w") as bz:
        bz.writestr("../../evil.txt", "evil data")

    bad_form = FormData()
    bad_form.add_field("file", bad_buf.getvalue(), filename="malicious.zip", content_type="application/zip")
    res_bad = await client.post("/api/backup/import", data=bad_form, headers=headers)
    assert res_bad.status == 400
    assert "malicious" in (await res_bad.json()).get("error", "")

    # 3. Test valid backup import restores files cleanly
    valid_buf = io.BytesIO()
    with zipfile.ZipFile(valid_buf, "w") as vz:
        vz.writestr("config.toml", "[server]\nhost = \"127.0.0.1\"\nport = 8787\n[twitch_chat]\nchannel = \"restored_pro\"\n")

    valid_form = FormData()
    valid_form.add_field("file", valid_buf.getvalue(), filename="valid_backup.zip", content_type="application/zip")
    res_import = await client.post("/api/backup/import", data=valid_form, headers=headers)
    assert res_import.status == 200
    assert (await res_import.json()).get("ok") is True

    # Verify restored config
    restored_txt = test_cfg.read_text(encoding="utf-8")
    assert "restored_pro" in restored_txt


def test_appearance_theme_serialization():
    cfg = {
        "appearance": {
            "theme": "mocha-harmony"
        }
    }
    serialized = serialize_toml(cfg)
    assert "[appearance]" in serialized
    assert 'theme = "mocha-harmony"' in serialized


@pytest.mark.asyncio
async def test_appearance_theme_api_and_broadcast(aiohttp_client, tmp_path):
    test_cfg = tmp_path / "config.toml"
    test_cfg.write_text("[server]\nhost = \"127.0.0.1\"\nport = 8787\n[appearance]\ntheme = \"mocha-teal\"\n", encoding="utf-8")

    broadcaster = Broadcaster()
    broadcaster.init_appearance({"theme": "mocha-teal"})

    config = {
        "server": {"host": "127.0.0.1", "port": 8787},
        "appearance": {"theme": "mocha-teal"}
    }

    app = build_app(broadcaster, config, enable_settings=True, config_path=test_cfg)
    client = await aiohttp_client(app)

    # 1. Verify health returns current theme
    health_res = await client.get("/health")
    assert health_res.status == 200
    health_data = await health_res.json()
    assert health_data.get("theme") == "mocha-teal"

    # 2. Change theme to mocha-harmony via /api/config
    headers = {"Referer": "http://127.0.0.1:8787/settings"}
    save_res = await client.post("/api/config", json={
        "appearance": {
            "theme": "mocha-harmony"
        }
    }, headers=headers)

    assert save_res.status == 200
    assert (await save_res.json()).get("ok") is True

    # 3. Verify Broadcaster state updated
    assert broadcaster.current_theme == "mocha-harmony"
    assert broadcaster.last_theme == {"type": "theme_update", "theme": "mocha-harmony"}

    # 4. Verify config.toml persisted on disk
    saved_toml = test_cfg.read_text(encoding="utf-8")
    assert 'theme = "mocha-harmony"' in saved_toml
