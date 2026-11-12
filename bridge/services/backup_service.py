"""Full system backup export and import service."""

import io
import re
import zipfile
from datetime import datetime
from pathlib import Path

from tomllib import load as toml_load


def create_backup_zip(project_root: Path, config_path: Path, src_dir: Path) -> tuple[bytes, str]:
    """Package configuration, custom sounds, and scene collection into an in-memory zip."""
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as z:
        if config_path.exists():
            z.write(config_path, arcname="config.toml")
        sounds_json = src_dir / "sounds" / "sounds.json"
        if sounds_json.exists():
            z.write(sounds_json, arcname="sounds/sounds.json")
        sounds_dir = src_dir / "sounds"
        if sounds_dir.exists():
            for f in sounds_dir.iterdir():
                if f.is_file() and f.suffix.lower() in (".wav", ".mp3", ".ogg", ".flac"):
                    z.write(f, arcname=f"sounds/{f.name}")
        tmpl_obs = project_root / "obs" / "SYSTEM_Scene_Collection.json"
        if tmpl_obs.exists():
            z.write(tmpl_obs, arcname="obs/SYSTEM_Scene_Collection.json")

    filename = f"SYSTEM_Backup_{datetime.now().strftime('%Y-%m-%d')}.zip"
    return buf.getvalue(), filename


def restore_backup_zip(
    data: bytes,
    project_root: Path,
    config_path: Path,
    backup_path: Path,
    src_dir: Path,
) -> dict:
    """Validate zip archive against Zip Slip, restore files, and return parsed config dict."""
    if len(data) > 60 * 1024 * 1024:
        raise ValueError("backup file exceeds 60MB limit")

    buf = io.BytesIO(data)
    with zipfile.ZipFile(buf, "r") as z:
        # Zip Slip security check
        for name in z.namelist():
            if ".." in name or name.startswith("/") or name.startswith("\\"):
                raise ValueError("malicious zip archive (path traversal)")

        if config_path.exists():
            backup_path.write_bytes(config_path.read_bytes())

        for name in z.namelist():
            if name == "config.toml":
                config_path.write_bytes(z.read(name))
            elif name == "sounds/sounds.json":
                (src_dir / "sounds" / "sounds.json").write_bytes(z.read(name))
            elif name.startswith("sounds/") and not name.endswith("/"):
                filename = Path(name).name
                safe_name = re.sub(r"[^a-zA-Z0-9_.-]", "_", filename)
                (src_dir / "sounds" / safe_name).write_bytes(z.read(name))
            elif name == "obs/SYSTEM_Scene_Collection.json":
                (project_root / "obs" / "SYSTEM_Scene_Collection.json").write_bytes(z.read(name))

    with open(config_path, "rb") as handle:
        return toml_load(handle)
