import json
import pytest
from pathlib import Path
from obs.sync_scenes import sync_collection


def test_sync_collection_preserves_user_sources(tmp_path):
    target_file = tmp_path / "SYSTEM.json"

    # Simulate a user's active SYSTEM.json with custom PipeWire, webcam, microphone
    user_scene_collection = {
        "name": "SYSTEM Broadcast Templates",
        "sources": [
            {
                "name": "SYSTEM: Background",
                "id": "browser_source",
                "uuid": "uuid-bg",
                "settings": {"url": "http://localhost:8787/src/overlays/background.html"}
            },
            {
                "name": "SYSTEM: Alerts",
                "id": "browser_source",
                "uuid": "uuid-alerts",
                "settings": {"url": "http://localhost:8787/src/overlays/alerts.html"}
            },
            # Custom user sources
            {
                "name": "Screen Capture (PipeWire)",
                "id": "pipewire_screen_capture",
                "uuid": "uuid-pipewire",
                "settings": {}
            },
            {
                "name": "DroidCam OBS",
                "id": "droidcam_source",
                "uuid": "uuid-droidcam",
                "settings": {}
            },
            # Main scene with user sources mixed with SYSTEM sources
            {
                "name": "SYSTEM: Main (Gameplay)",
                "id": "scene",
                "uuid": "uuid-scene-main",
                "settings": {
                    "id_counter": 10,
                    "items": [
                        {"name": "SYSTEM: Background", "id": 1, "visible": True},
                        {"name": "Screen Capture (PipeWire)", "id": 9, "visible": True},
                        {"name": "SYSTEM: Alerts", "id": 5, "visible": True}
                    ]
                }
            },
            # Custom user scene
            {
                "name": "camera",
                "id": "scene",
                "uuid": "uuid-scene-camera",
                "settings": {
                    "id_counter": 2,
                    "items": [
                        {"name": "DroidCam OBS", "id": 1, "visible": True}
                    ]
                }
            }
        ]
    }

    target_file.write_text(json.dumps(user_scene_collection), encoding="utf-8")

    # 1. Run sync
    res = sync_collection(target_file, dry_run=False, backup=True)
    assert res["status"] == "updated"
    assert "SYSTEM: TTS" in res["added_sources"]
    assert "SYSTEM: Goal" in res["added_sources"]
    assert "SYSTEM: Main (Gameplay)" in res["scenes_updated"]

    # Verify backup was created
    backups = list(tmp_path.glob("SYSTEM.json.bak.*"))
    assert len(backups) == 1

    # 2. Inspect updated content
    updated_data = json.loads(target_file.read_text(encoding="utf-8"))
    source_names = [s["name"] for s in updated_data["sources"]]

    # User sources MUST be preserved
    assert "Screen Capture (PipeWire)" in source_names
    assert "DroidCam OBS" in source_names
    assert "camera" in source_names

    # New SYSTEM sources MUST be added
    assert "SYSTEM: TTS" in source_names
    assert "SYSTEM: Goal" in source_names

    # Check scene items in 'SYSTEM: Main (Gameplay)'
    main_scene = next(s for s in updated_data["sources"] if s["name"] == "SYSTEM: Main (Gameplay)")
    item_names = [it["name"] for it in main_scene["settings"]["items"]]
    item_ids = [it["id"] for it in main_scene["settings"]["items"]]

    # Both user item and new SYSTEM items present
    assert "Screen Capture (PipeWire)" in item_names
    assert "SYSTEM: TTS" in item_names
    assert "SYSTEM: Goal" in item_names

    # IDs must be unique
    assert len(item_ids) == len(set(item_ids))
    # User's id 9 was preserved
    pipewire_item = next(it for it in main_scene["settings"]["items"] if it["name"] == "Screen Capture (PipeWire)")
    assert pipewire_item["id"] == 9

    # Custom scene 'camera' was untouched
    camera_scene = next(s for s in updated_data["sources"] if s["name"] == "camera")
    assert len(camera_scene["settings"]["items"]) == 1
    assert camera_scene["settings"]["items"][0]["name"] == "DroidCam OBS"

    # 3. Idempotency: run sync again -> must be "in_sync" with 0 changes
    res_second = sync_collection(target_file, dry_run=False, backup=True)
    assert res_second["status"] == "in_sync"
    assert len(res_second["added_sources"]) == 0
    assert len(res_second["scenes_updated"]) == 0


def test_sync_collection_preserves_audio_routing(tmp_path):
    target_file = tmp_path / "SYSTEM.json"

    # User manually unchecked "Control audio via OBS" and set monitor off
    collection = {
        "name": "SYSTEM Broadcast Templates",
        "sources": [
            {
                "name": "SYSTEM: Alerts",
                "id": "browser_source",
                "uuid": "uuid-alerts",
                "settings": {
                    "url": "http://localhost:8787/src/overlays/alerts.html",
                    "reroute_audio": False,
                    "restart_when_active": True
                },
                "monitoring_type": 0  # Monitor Off
            },
            {
                "name": "SYSTEM: Main (Gameplay)",
                "id": "scene",
                "uuid": "uuid-main",
                "settings": {
                    "id_counter": 2,
                    "items": [
                        {"name": "SYSTEM: Alerts", "id": 1, "visible": True}
                    ]
                }
            }
        ]
    }
    target_file.write_text(json.dumps(collection), encoding="utf-8")

    # Run sync
    res = sync_collection(target_file, dry_run=False, backup=False)

    # Inspect results
    updated = json.loads(target_file.read_text(encoding="utf-8"))
    alerts_src = next(s for s in updated["sources"] if s["name"] == "SYSTEM: Alerts")

    # Audio routing settings MUST NOT be overwritten
    assert alerts_src["settings"]["reroute_audio"] is False
    assert alerts_src["monitoring_type"] == 0
