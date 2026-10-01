import asyncio
import logging
import mimetypes
import shutil
import time
from pathlib import Path
from urllib.parse import unquote, urlparse

log = logging.getLogger("bridge.player")

current_cover_path = None
current_cover_url = None


def format_seconds(secs: float | int) -> str:
    secs = max(0, int(secs))
    m = secs // 60
    s = secs % 60
    return f"{m:02d}:{s:02d}"


def get_current_cover_bytes() -> tuple[bytes | None, str]:
    global current_cover_path
    if not current_cover_path:
        return None, "image/png"
    p = Path(current_cover_path)
    if p.exists() and p.is_file():
        mime, _ = mimetypes.guess_type(p)
        return p.read_bytes(), mime or "image/jpeg"
    return None, "image/png"


async def query_windows_smtc() -> list[dict]:
    """Queries Windows Media Transport Controls (SMTC) for Windows media players."""
    try:
        import winsdk.windows.media.control as wmc
        manager = await wmc.GlobalSystemMediaTransportControlsSessionManager.request_async()
        session = manager.get_current_session()
        if not session:
            return []

        info = await session.try_get_media_properties_async()
        timeline = session.get_timeline_properties()
        playback_info = session.get_playback_info()

        status_map = {
            wmc.GlobalSystemMediaTransportControlsSessionPlaybackStatus.PLAYING: "Playing",
            wmc.GlobalSystemMediaTransportControlsSessionPlaybackStatus.PAUSED: "Paused",
            wmc.GlobalSystemMediaTransportControlsSessionPlaybackStatus.STOPPED: "Stopped",
        }
        status = status_map.get(playback_info.playback_status, "Playing") if playback_info else "Playing"

        length_sec = timeline.end_time.total_seconds() if timeline and timeline.end_time else 0
        pos_sec = timeline.position.total_seconds() if timeline and timeline.position else 0

        return [{
            "player": session.source_app_user_model_id or "WindowsMedia",
            "status": status,
            "title": info.title or "",
            "artist": info.artist or "",
            "album": info.album_title or "",
            "artUrl": "",
            "length": length_sec,
            "position": pos_sec,
        }]
    except Exception:
        return []


async def query_mpris_players() -> list[dict]:
    """Queries all media players via playerctl/busctl on Linux or SMTC on Windows."""
    import sys
    if sys.platform == "win32":
        return await query_windows_smtc()

    has_playerctl = shutil.which("playerctl") is not None
    players = []

    if has_playerctl:
        try:
            cmd = [
                "playerctl", "-a", "metadata", "--format",
                "{{playerName}}\t{{status}}\t{{title}}\t{{artist}}\t{{album}}\t{{mpris:artUrl}}\t{{mpris:length}}\t{{position}}"
            ]
            proc = await asyncio.create_subprocess_exec(
                *cmd,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.DEVNULL
            )
            stdout, _ = await proc.communicate()
            if proc.returncode == 0 and stdout:
                lines = stdout.decode("utf-8", errors="replace").splitlines()
                for line in lines:
                    parts = line.split("\t")
                    if len(parts) >= 8:
                        name, status, title, artist, album, art_url, length_raw, pos_raw = parts[:8]
                        try:
                            # Length in microseconds
                            length_sec = int(length_raw) / 1_000_000 if length_raw.isdigit() else 0
                        except Exception:
                            length_sec = 0

                        try:
                            # Position in microseconds
                            pos_sec = float(pos_raw) / 1_000_000 if pos_raw else 0
                        except Exception:
                            pos_sec = 0

                        players.append({
                            "player": name.strip(),
                            "status": status.strip(),
                            "title": title.strip(),
                            "artist": artist.strip(),
                            "album": album.strip(),
                            "artUrl": art_url.strip(),
                            "length": length_sec,
                            "position": pos_sec,
                        })
        except Exception as e:
            log.debug("error querying playerctl: %s", e)

    return players


def pick_active_player(players: list[dict], preferred: str) -> dict | None:
    if not players:
        return None

    preferred_lower = preferred.strip().lower() if preferred else ""

    # 1. Preferred player playing
    if preferred_lower:
        for p in players:
            if preferred_lower in p["player"].lower() and p["status"].lower() == "playing":
                return p

    # 2. Any player playing
    for p in players:
        if p["status"].lower() == "playing":
            return p

    # 3. Preferred player paused
    if preferred_lower:
        for p in players:
            if preferred_lower in p["player"].lower() and p["status"].lower() == "paused":
                return p

    # 4. Any player paused
    for p in players:
        if p["status"].lower() == "paused":
            return p

    return players[0] if players else None


async def run(config: dict, broadcast) -> None:
    global current_cover_path, current_cover_url
    preferred = config.get("player_name", "kopuz")
    poll_interval = float(config.get("poll_interval", 1.0))
    last_broadcast_state = None

    log.info("player adapter started (preferred: %s, interval: %.1fs)", preferred, poll_interval)

    while True:
        try:
            players = await query_mpris_players()
            active = pick_active_player(players, preferred)

            if not active or not active["title"]:
                # No active track
                if last_broadcast_state != "stopped":
                    current_cover_path = None
                    current_cover_url = None
                    last_broadcast_state = "stopped"
                    await broadcast({
                        "type": "now_playing",
                        "status": "Stopped",
                        "active": False,
                    })
            else:
                art_raw = active["artUrl"]
                cover_local = None
                if art_raw.startswith("file://"):
                    cover_local = unquote(urlparse(art_raw).path)
                elif art_raw.startswith("/") and Path(art_raw).exists():
                    cover_local = art_raw

                current_cover_path = cover_local
                current_cover_url = art_raw if (art_raw.startswith("http://") or art_raw.startswith("https://")) else None

                length_sec = int(active["length"])
                pos_sec = min(length_sec, int(active["position"])) if length_sec > 0 else int(active["position"])
                progress = min(1.0, max(0.0, pos_sec / length_sec)) if length_sec > 0 else 0.0

                art_endpoint = "/api/player/art" if (cover_local or current_cover_url) else ""

                payload = {
                    "type": "now_playing",
                    "status": active["status"],
                    "active": True,
                    "player": active["player"],
                    "title": active["title"],
                    "artist": active["artist"],
                    "album": active["album"],
                    "artUrl": art_endpoint,
                    "hasCover": bool(art_endpoint),
                    "position": pos_sec,
                    "positionFormatted": format_seconds(pos_sec),
                    "length": length_sec,
                    "lengthFormatted": format_seconds(length_sec),
                    "progress": round(progress, 3),
                }

                last_broadcast_state = f"{active['player']}:{active['title']}:{active['status']}"
                await broadcast(payload)

        except asyncio.CancelledError:
            raise
        except Exception as e:
            log.debug("player adapter error: %s", e)

        await asyncio.sleep(poll_interval)
