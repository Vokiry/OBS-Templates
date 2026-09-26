import json
import uuid
from pathlib import Path

BASE_URL = "http://localhost:8787"


def make_uuid() -> str:
    return str(uuid.uuid4())


def make_browser_source(name: str, path: str, query: str = "") -> dict:
    url = f"{BASE_URL}/src/overlays/{path}"
    if query:
        url += f"?{query}"
    return {
        "prev_ver": 537001985,
        "name": name,
        "uuid": make_uuid(),
        "id": "browser_source",
        "versioned_id": "browser_source",
        "settings": {
            "url": url,
            "width": 1920,
            "height": 1080,
            "fps": 60,
            "reroute_audio": True,
            "restart_when_active": False,
            "shutdown": False,
        },
        "mixers": 255,
        "sync": 0,
        "flags": 0,
        "volume": 1.0,
        "balance": 0.5,
        "enabled": True,
        "muted": False,
        "push-to-mute": False,
        "push-to-mute-delay": 0,
        "push-to-talk": False,
        "push-to-talk-delay": 0,
        "hotkeys": {
            "ObsBrowser.Refresh": [],
        },
        "deinterlace_mode": 0,
        "deinterlace_field_order": 0,
        "monitoring_type": 1,  # Monitor and Output
        "private_settings": {},
    }


def make_scene(name: str, scene_sources: list) -> dict:
    scene_uuid = make_uuid()
    items = []
    for idx, item in enumerate(scene_sources):
        if isinstance(item, tuple):
            s, visible = item
        else:
            s, visible = item, True
        items.append({
            "name": s["name"],
            "source_uuid": s["uuid"],
            "visible": visible,
            "locked": True,
            "rot": 0.0,
            "pos": {"x": 0.0, "y": 0.0},
            "scale": {"x": 1.0, "y": 1.0},
            "scale_filter": "disable",
            "blend_method": "default",
            "blend_type": "normal",
            "id": idx + 1,
        })

    return {
        "prev_ver": 537001985,
        "name": name,
        "uuid": scene_uuid,
        "id": "scene",
        "versioned_id": "scene",
        "settings": {
            "id_counter": len(items) + 1,
            "custom_size": False,
            "items": items,
        },
        "mixers": 0,
        "sync": 0,
        "flags": 0,
        "volume": 1.0,
        "balance": 0.5,
        "enabled": True,
        "muted": False,
        "hotkeys": {},
        "private_settings": {},
    }


def build_collection() -> dict:
    # 1. Define atomic browser sources
    bg = make_browser_source("SYSTEM: Background", "background.html")
    alerts = make_browser_source("SYSTEM: Alerts", "alerts.html", "pos=top-center")
    pulse = make_browser_source("SYSTEM: Pulse", "activity-pulse.html", "pos=top-right")

    ind_starting = make_browser_source("SYSTEM: State [Starting]", "scene-indicator.html", "state=starting&pos=top-left")
    ind_main = make_browser_source("SYSTEM: State [Main]", "scene-indicator.html", "state=main&pos=top-left")
    ind_chatting = make_browser_source("SYSTEM: State [Chatting]", "scene-indicator.html", "state=chatting&pos=top-center")
    ind_focus = make_browser_source("SYSTEM: State [Focus]", "scene-indicator.html", "state=focus&pos=top-left")
    ind_brb = make_browser_source("SYSTEM: State [BRB]", "scene-indicator.html", "state=brb&pos=top-left")
    ind_ending = make_browser_source("SYSTEM: State [Ending]", "scene-indicator.html", "state=ending&pos=top-left")

    chat_half = make_browser_source("SYSTEM: Chat (Starting Soon)", "chat.html", "pos=top-right&layout=half")
    chat_main = make_browser_source("SYSTEM: Chat (Main Sidebar)", "chat.html", "pos=main-right")
    chat_standard = make_browser_source("SYSTEM: Chat", "chat.html", "pos=bottom-right")

    feed_right = make_browser_source("SYSTEM: Activity Feed", "activity-feed.html", "pos=top-right")

    np_compact = make_browser_source("SYSTEM: Now Playing", "now-playing.html", "variant=compact&pos=top-right")
    np_bottom_left = make_browser_source("SYSTEM: Now Playing (Bottom Left)", "now-playing.html", "variant=compact&pos=bottom-left")
    np_top_left = make_browser_source("SYSTEM: Now Playing (Top Left)", "now-playing.html", "variant=compact&pos=top-left")
    np_center = make_browser_source("SYSTEM: Now Playing (Center)", "now-playing.html", "variant=compact&pos=center")

    countdown = make_browser_source("SYSTEM: Countdown", "countdown.html", "minutes=10&pos=center-left")
    ending_card = make_browser_source("SYSTEM: Ending Card", "ending-card.html", "pos=center")
    media_request = make_browser_source("SYSTEM: Media Request", "media-request.html", "pos=bottom-left")

    all_browser_sources = [
        bg, alerts, pulse,
        ind_starting, ind_main, ind_chatting, ind_focus, ind_brb, ind_ending,
        chat_half, chat_main, chat_standard, (feed_right),
        np_compact, np_bottom_left, np_top_left, np_center,
        countdown, ending_card, media_request
    ]

    # 2. Build Scenes (ordered layers from bottom to top)
    scene_starting = make_scene("SYSTEM: Starting Soon", [
        bg, ind_starting, countdown, np_bottom_left, chat_half, alerts, media_request
    ])
    scene_main = make_scene("SYSTEM: Main (Gameplay)", [
        bg, ind_main, np_compact, chat_main, alerts, media_request
    ])
    scene_chatting = make_scene("SYSTEM: Chatting", [
        bg, ind_chatting, np_top_left, chat_standard, alerts, media_request
    ])
    scene_focus = make_scene("SYSTEM: Focus", [
        ind_focus, alerts
    ])
    scene_break = make_scene("SYSTEM: Break (BRB)", [
        bg, ind_brb, np_center, chat_standard, alerts, media_request
    ])
    scene_ending = make_scene("SYSTEM: Ending", [
        bg, ind_ending, ending_card
    ])

    all_scenes = [
        scene_starting,
        scene_main,
        scene_chatting,
        scene_focus,
        scene_break,
        scene_ending,
    ]

    return {
        "name": "SYSTEM Broadcast Templates",
        "current_scene": "SYSTEM: Main (Gameplay)",
        "current_program_scene": "SYSTEM: Main (Gameplay)",
        "scene_order": [{"name": s["name"]} for s in all_scenes],
        "sources": all_browser_sources + all_scenes,
        "version": 537001985,
        "resolution": {"x": 1920, "y": 1080},
    }


if __name__ == "__main__":
    collection = build_collection()
    out_path = Path(__file__).parent / "SYSTEM_Scene_Collection.json"
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(collection, f, indent=4, ensure_ascii=False)
    print(f"Generated {out_path} with {len(collection['scene_order'])} scenes and {len(collection['sources'])} sources.")
