"""Full system backup export and validated transactional restore."""

import io
import json
import re
import zipfile
from datetime import datetime
from pathlib import Path

from tomllib import loads as toml_loads

from services.file_service import atomic_write_bytes
from services.toml_service import serialize_toml

MAX_BACKUP_BYTES = 60 * 1024 * 1024
MAX_MEMBER_BYTES = 60 * 1024 * 1024
MAX_TOTAL_UNCOMPRESSED_BYTES = 120 * 1024 * 1024
AUDIO_EXTENSIONS = {".wav", ".mp3", ".ogg", ".flac"}


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
                if f.is_file() and f.suffix.lower() in AUDIO_EXTENSIONS:
                    z.write(f, arcname=f"sounds/{f.name}")
        tmpl_obs = project_root / "obs" / "SYSTEM_Scene_Collection.json"
        if tmpl_obs.exists():
            z.write(tmpl_obs, arcname="obs/SYSTEM_Scene_Collection.json")

    filename = f"SYSTEM_Backup_{datetime.now().strftime('%Y-%m-%d')}.zip"
    return buf.getvalue(), filename


def _read_member(archive: zipfile.ZipFile, info: zipfile.ZipInfo) -> bytes:
    if info.file_size > MAX_MEMBER_BYTES:
        raise ValueError(f"backup member is too large: {info.filename}")
    try:
        data = archive.read(info)
    except (zipfile.BadZipFile, RuntimeError, NotImplementedError) as exc:
        raise ValueError(f"cannot read backup member: {info.filename}") from exc
    if len(data) != info.file_size:
        raise ValueError(f"corrupt backup member: {info.filename}")
    return data


def prepare_backup_restore(data: bytes, project_root: Path, config_path: Path, src_dir: Path) -> tuple[dict, dict[Path, bytes]]:
    if len(data) > MAX_BACKUP_BYTES:
        raise ValueError("backup file exceeds 60MB limit")
    try:
        archive_context = zipfile.ZipFile(io.BytesIO(data), "r")
    except zipfile.BadZipFile as exc:
        raise ValueError("invalid zip archive") from exc

    staged: dict[Path, bytes] = {}
    names_to_data: dict[str, bytes] = {}
    with archive_context as archive:
        infos = archive.infolist()
        total_size = sum(info.file_size for info in infos if not info.is_dir())
        if total_size > MAX_TOTAL_UNCOMPRESSED_BYTES:
            raise ValueError("backup uncompressed contents are too large")

        for info in infos:
            name = info.filename
            if ".." in name or name.startswith(("/", "\\")):
                raise ValueError("malicious zip archive (path traversal)")
            if info.is_dir():
                continue
            if name == "config.toml":
                names_to_data[name] = _read_member(archive, info)
            elif name == "sounds/sounds.json":
                names_to_data[name] = _read_member(archive, info)
            elif name == "obs/SYSTEM_Scene_Collection.json":
                names_to_data[name] = _read_member(archive, info)
            elif name.startswith("sounds/") and Path(name).suffix.lower() in AUDIO_EXTENSIONS:
                names_to_data[name] = _read_member(archive, info)

    config_data = names_to_data.get("config.toml")
    if config_data is None:
        raise ValueError("backup does not contain config.toml")
    try:
        new_cfg = toml_loads(config_data.decode("utf-8"))
    except (UnicodeDecodeError, ValueError) as exc:
        raise ValueError("invalid config.toml in backup") from exc
    if not isinstance(new_cfg, dict):
        raise ValueError("invalid config.toml in backup")
    try:
        serialize_toml(new_cfg)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"invalid configuration values: {exc}") from exc

    for json_name in ("sounds/sounds.json", "obs/SYSTEM_Scene_Collection.json"):
        if json_name in names_to_data:
            try:
                parsed = json.loads(names_to_data[json_name].decode("utf-8"))
            except (UnicodeDecodeError, json.JSONDecodeError) as exc:
                raise ValueError(f"invalid JSON in {json_name}") from exc
            if not isinstance(parsed, dict):
                raise ValueError(f"invalid JSON in {json_name}")

    staged[config_path] = config_data
    if "sounds/sounds.json" in names_to_data:
        staged[src_dir / "sounds" / "sounds.json"] = names_to_data["sounds/sounds.json"]
    if "obs/SYSTEM_Scene_Collection.json" in names_to_data:
        staged[project_root / "obs" / "SYSTEM_Scene_Collection.json"] = names_to_data["obs/SYSTEM_Scene_Collection.json"]
    for name, content in names_to_data.items():
        if name.startswith("sounds/") and name != "sounds/sounds.json":
            filename = Path(name).name
            safe_name = re.sub(r"[^a-zA-Z0-9_.-]", "_", filename)
            if safe_name.strip("._"):
                staged[src_dir / "sounds" / safe_name] = content
    return new_cfg, staged


def rollback_staged_restore(staged: dict[Path, bytes], previous: dict, previous_modes: dict) -> None:
    """Restore previous bytes and modes after any failed apply step."""
    for path in staged:
        content = previous[path]
        if content is None:
            path.unlink(missing_ok=True)
        else:
            atomic_write_bytes(path, content, mode=previous_modes[path] or 0o600)


def commit_staged_restore(staged: dict[Path, bytes], config_path: Path, backup_path: Path) -> tuple[dict, dict]:
    """Commit prepared files and return the state needed for a later rollback."""
    previous = {path: path.read_bytes() if path.exists() else None for path in staged}
    previous_modes = {path: path.stat().st_mode & 0o777 if path.exists() else None for path in staged}
    try:
        if config_path.exists():
            atomic_write_bytes(backup_path, config_path.read_bytes())
        for path, content in staged.items():
            mode = 0o600 if path == config_path else 0o644
            atomic_write_bytes(path, content, mode=mode)
    except Exception:
        rollback_staged_restore(staged, previous, previous_modes)
        raise
    return previous, previous_modes


def restore_backup_zip(
    data: bytes,
    project_root: Path,
    config_path: Path,
    backup_path: Path,
    src_dir: Path,
) -> dict:
    """Validate the complete archive before atomically applying a rollback-safe restore."""
    new_cfg, staged = prepare_backup_restore(data, project_root, config_path, src_dir)
    commit_staged_restore(staged, config_path, backup_path)
    return new_cfg
