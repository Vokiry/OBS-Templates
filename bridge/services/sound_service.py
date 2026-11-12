"""Sound catalog management service."""

import json
from pathlib import Path


def get_sounds_catalog(src_dir: Path) -> dict:
    """Read sounds directory and return available files, current mappings, and volume."""
    sounds_dir = src_dir / "sounds"
    audio_exts = {".wav", ".mp3", ".ogg", ".flac"}
    available_files = []
    if sounds_dir.exists():
        available_files = sorted([f.name for f in sounds_dir.iterdir() if f.suffix.lower() in audio_exts])

    mapping = {
        "donate": "donate.wav",
        "sub": "sub.wav",
        "resub": "sub.wav",
        "gift": "sub.wav",
        "raid": "raid.wav",
        "cheer": "cheer.wav",
        "follow": "follow.wav",
        "default": "default.wav",
    }
    master_volume = 0.7
    sounds_json_path = sounds_dir / "sounds.json"
    if sounds_json_path.exists():
        try:
            raw = json.loads(sounds_json_path.read_text(encoding="utf-8"))
            if "masterVolume" in raw:
                master_volume = float(raw["masterVolume"])
            for k, v in raw.get("sounds", {}).items():
                f = v.get("file", "")
                if "/" in f:
                    f = f.split("/")[-1]
                mapping[k] = f
        except Exception:
            pass

    return {
        "available_files": available_files,
        "mapping": mapping,
        "masterVolume": master_volume,
    }


def save_sounds_catalog(src_dir: Path, mapping: dict, master_volume: float = 0.7) -> dict:
    """Save sound mappings and master volume to sounds.json."""
    sounds_dir = src_dir / "sounds"
    sounds_json_path = sounds_dir / "sounds.json"
    data = {
        "masterVolume": max(0.0, min(1.0, float(master_volume))),
        "sounds": {k: {"file": f"../sounds/{fname}", "volume": 0.8} for k, fname in mapping.items()},
    }
    sounds_json_path.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")
    return data
