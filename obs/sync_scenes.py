"""Smart scene collection synchronizer for OBS Studio.

Safely merges new SYSTEM browser sources (like SYSTEM: Goal, SYSTEM: TTS)
into an existing user OBS scene collection WITHOUT overwriting, removing,
or reordering any user-configured sources (PipeWire, ALSA, DroidCam, etc.).
"""

import json
import logging
import shutil
import sys
from datetime import datetime
from pathlib import Path

# Add project root to sys.path
PROJECT_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from obs.generate_collection import build_collection

log = logging.getLogger("sync_scenes")


def sync_collection(
    target_path: Path,
    dry_run: bool = False,
    backup: bool = True
) -> dict:
    """Safely inject missing SYSTEM sources into an existing OBS collection.

    Returns a summary dict with added sources and scenes modified.
    """
    if not target_path.exists():
        log.warning("target collection does not exist: %s", target_path)
        return {"status": "not_found", "added_sources": [], "scenes_updated": []}

    target_data = json.loads(target_path.read_text(encoding="utf-8"))
    template_data = build_collection()

    existing_sources_by_name = {
        s.get("name"): s for s in target_data.get("sources", [])
    }
    template_sources_by_name = {
        s.get("name"): s for s in template_data.get("sources", [])
    }

    added_sources = []
    scenes_updated = set()

    # 1. Identify missing SYSTEM browser sources
    for name, tmpl_source in template_sources_by_name.items():
        if not name.startswith("SYSTEM: "):
            continue
        # Skip scenes in this step (scenes are handled in step 2)
        if tmpl_source.get("id") == "scene":
            continue

        if name not in existing_sources_by_name:
            target_data["sources"].append(tmpl_source)
            existing_sources_by_name[name] = tmpl_source
            added_sources.append(name)
        else:
            # Sync critical visual settings (restart_when_active, fps, resolution)
            # DO NOT overwrite user's audio routing (reroute_audio / monitoring_type)
            curr = existing_sources_by_name[name]
            curr_settings = curr.setdefault("settings", {})
            tmpl_settings = tmpl_source.get("settings", {})
            for key in ("restart_when_active", "fps", "width", "height"):
                if key in tmpl_settings:
                    curr_settings[key] = tmpl_settings[key]

    # 2. Inject missing items into existing scenes
    template_scenes = {
        s.get("name"): s for s in template_data.get("sources", []) if s.get("id") == "scene"
    }

    for target_source in target_data.get("sources", []):
        if target_source.get("id") != "scene":
            continue
        scene_name = target_source.get("name")
        tmpl_scene = template_scenes.get(scene_name)
        if not tmpl_scene:
            continue  # User-created scene (e.g. 'camera') — DO NOT TOUCH!

        scene_settings = target_source.setdefault("settings", {})
        scene_items = scene_settings.setdefault("items", [])
        existing_item_names = {it.get("name") for it in scene_items}

        # Find highest ID currently in use
        max_id = max((it.get("id", 0) for it in scene_items), default=0)

        # Check which template items are missing in this scene
        for tmpl_item in tmpl_scene.get("settings", {}).get("items", []):
            item_name = tmpl_item.get("name")
            if item_name not in existing_item_names:
                # Add item to scene with next available ID
                max_id += 1
                new_item = dict(tmpl_item)
                new_item["id"] = max_id
                # Ensure source_uuid matches the actual source in target_data
                actual_source = existing_sources_by_name.get(item_name)
                if actual_source:
                    new_item["source_uuid"] = actual_source.get("uuid", new_item["source_uuid"])
                scene_items.append(new_item)
                existing_item_names.add(item_name)
                scenes_updated.add(scene_name)

        scene_settings["id_counter"] = max_id + 1

    if (added_sources or scenes_updated) and not dry_run:
        # Create timestamped backup
        if backup:
            ts = datetime.now().strftime("%Y%m%d_%H%M%S")
            bak_path = target_path.with_name(f"{target_path.name}.bak.{ts}")
            shutil.copy2(target_path, bak_path)
            log.info("created safety backup: %s", bak_path)

        # Save merged collection
        target_path.write_text(json.dumps(target_data, indent=4, ensure_ascii=False), encoding="utf-8")
        log.info("synchronized collection: %s (added %d sources, updated %d scenes)",
                 target_path, len(added_sources), len(scenes_updated))

    return {
        "status": "updated" if (added_sources or scenes_updated) else "in_sync",
        "added_sources": added_sources,
        "scenes_updated": sorted(list(scenes_updated))
    }


def main():
    logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
    default_obs_path = Path.home() / ".config/obs-studio/basic/scenes/SYSTEM.json"

    import argparse
    parser = argparse.ArgumentParser(description="Safely sync SYSTEM sources into active OBS collection")
    parser.add_argument("--target", default=str(default_obs_path), help="Path to SYSTEM.json")
    parser.add_argument("--dry-run", action="store_true", help="Inspect changes without writing")
    args = parser.parse_args()

    target = Path(args.target)
    res = sync_collection(target, dry_run=args.dry_run)
    print(f"Sync result: {res['status']}")
    if res["added_sources"]:
        print(f"Added sources: {', '.join(res['added_sources'])}")
    if res["scenes_updated"]:
        print(f"Updated scenes: {', '.join(res['scenes_updated'])}")
    if res["status"] == "in_sync":
        print("All SYSTEM sources are already up to date!")


if __name__ == "__main__":
    main()
