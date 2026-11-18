"""Cross-platform media player tracking service (Linux MPRIS + Windows SMTC).

Tracks currently playing track, playback status, position timeline, album art,
and coordinates with LyricsService for real-time synchronized LRC lyrics.
"""

from __future__ import annotations

import asyncio
import hashlib
import logging
import shutil
import sys
import time
from abc import ABC, abstractmethod
from pathlib import Path
from urllib.parse import unquote, urlparse
from urllib.request import url2pathname

from services.lyrics_service import LyricsService

log = logging.getLogger("bridge.services.media")


def parse_mpris_line(line: str) -> dict | None:
    """Parse a tab-separated line from playerctl metadata --format."""
    clean = line.strip("\r\n")
    if not clean:
        return {
            "available": False,
            "player": "",
            "status": "Stopped",
            "title": "",
            "artist": "",
            "album": "",
            "position_ms": 0,
            "duration_ms": None,
            "has_cover": False,
            "art_url": "",
            "local_file": None,
        }

    parts = clean.split("\t")
    # Expected fields:
    # 0: playerName
    # 1: status
    # 2: xesam:title
    # 3: xesam:artist
    # 4: xesam:album
    # 5: mpris:length
    # 6: position
    # 7: mpris:artUrl
    # 8: xesam:url
    player = parts[0] if len(parts) > 0 else ""
    status = parts[1] if len(parts) > 1 else "Stopped"
    title = parts[2] if len(parts) > 2 else ""
    artist = parts[3] if len(parts) > 3 else ""
    album = parts[4] if len(parts) > 4 else ""
    raw_len = parts[5] if len(parts) > 5 else ""
    raw_pos = parts[6] if len(parts) > 6 else ""
    art_url = parts[7] if len(parts) > 7 else ""
    xesam_url = parts[8] if len(parts) > 8 else ""

    # Parse duration in microseconds -> milliseconds
    duration_ms: int | None = None
    try:
        if raw_len:
            micro_len = int(raw_len)
            ms = micro_len // 1000
            # If greater than 24 hours, likely a live stream without length
            if 0 < ms < 86_400_000:
                duration_ms = ms
    except (ValueError, TypeError):
        pass

    # Parse position in microseconds -> milliseconds
    position_ms = 0
    try:
        if raw_pos:
            position_ms = max(0, int(raw_pos) // 1000)
    except (ValueError, TypeError):
        pass

    # Local file path resolution from xesam:url
    local_file: str | None = None
    if xesam_url.startswith("file://"):
        try:
            local_file = url2pathname(unquote(urlparse(xesam_url).path))
        except Exception:
            pass

    # Title fallback: if title is empty but we have local file, extract filename
    if not title and local_file:
        title = Path(local_file).stem
    elif not title:
        title = "Unknown Track" if status == "Playing" else ""

    has_cover = bool(art_url)

    return {
        "available": bool(player and status in ("Playing", "Paused")),
        "player": player,
        "status": status if status in ("Playing", "Paused") else "Stopped",
        "title": title,
        "artist": artist,
        "album": album,
        "position_ms": position_ms,
        "duration_ms": duration_ms,
        "has_cover": has_cover,
        "art_url": art_url,
        "local_file": local_file,
    }


class BaseMediaTracker(ABC):
    """Abstract interface for OS-specific media trackers."""

    def __init__(self, on_update_callback) -> None:
        self.on_update = on_update_callback
        self.is_running = False

    @abstractmethod
    async def start(self) -> None:
        pass

    @abstractmethod
    async def stop(self) -> None:
        pass

    @abstractmethod
    async def get_cover_bytes(self) -> tuple[bytes | None, str]:
        """Return (image_bytes, mime_type) for the current cover."""
        pass

    @abstractmethod
    async def play(self) -> bool:
        pass

    @abstractmethod
    async def pause(self) -> bool:
        pass

    @abstractmethod
    async def toggle(self) -> bool:
        pass

    @abstractmethod
    async def next_track(self) -> bool:
        pass

    @abstractmethod
    async def previous_track(self) -> bool:
        pass


class LinuxMprisTracker(BaseMediaTracker):
    """Linux MPRIS tracker using playerctl CLI in streaming follow mode."""

    def __init__(
        self,
        on_update_callback,
        player: str = "auto",
        ignore_players: list[str] | None = None,
    ) -> None:
        super().__init__(on_update_callback)
        self.player_target = player or "auto"
        self.ignore_players = ignore_players or ["firefox"]
        self._proc: asyncio.subprocess.Process | None = None
        self._worker_task: asyncio.Task | None = None
        self._current_art_url: str = ""
        self._cached_cover_bytes: bytes | None = None
        self._cached_cover_mime: str = "image/jpeg"
        self._last_active_player: str = ""

    async def start(self) -> None:
        if not shutil.which("playerctl"):
            log.warning("playerctl binary not found on Linux — MPRIS player tracking unavailable")
            return
        self.is_running = True
        self._worker_task = asyncio.create_task(self._supervisor_loop())

    async def stop(self) -> None:
        self.is_running = False
        if self._proc:
            try:
                self._proc.terminate()
                await self._proc.wait()
            except Exception:
                pass
            self._proc = None
        if self._worker_task:
            self._worker_task.cancel()
            try:
                await self._worker_task
            except asyncio.CancelledError:
                pass

    async def _supervisor_loop(self) -> None:
        while self.is_running:
            try:
                await self._run_playerctl_follow()
            except asyncio.CancelledError:
                break
            except Exception as e:
                log.warning("playerctl follow error: %s, restarting in 3s...", e)
            if self.is_running:
                await asyncio.sleep(3.0)

    async def _run_playerctl_follow(self) -> None:
        fmt = (
            "{{playerName}}\t{{status}}\t{{xesam:title}}\t{{xesam:artist}}\t"
            "{{xesam:album}}\t{{mpris:length}}\t{{position}}\t{{mpris:artUrl}}\t{{xesam:url}}"
        )

        cmd = ["playerctl"]
        if self.player_target and self.player_target != "auto":
            cmd.extend(["-p", self.player_target])
        else:
            cmd.extend(["-p", "%any"])

        for ign in self.ignore_players:
            if ign:
                cmd.extend(["-i", ign])

        cmd.extend(["-F", "metadata", "--format", fmt])

        log.info("starting MPRIS tracker: %s", " ".join(cmd))
        self._proc = await asyncio.create_subprocess_exec(
            *cmd,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.DEVNULL,
        )

        assert self._proc.stdout is not None
        while self.is_running:
            line_bytes = await self._proc.stdout.readline()
            if not line_bytes:
                break  # EOF / process terminated
            line = line_bytes.decode("utf-8", errors="replace")
            parsed = parse_mpris_line(line)
            if parsed:
                self._last_active_player = parsed.get("player") or self._last_active_player
                # Invalidate or load cover when art_url changes
                new_art = parsed.get("art_url") or ""
                # Resolve spotify:image URI to CDN URL
                if new_art.startswith("spotify:image:"):
                    img_id = new_art.split(":")[-1]
                    new_art = f"https://i.scdn.co/image/{img_id}"
                    parsed["art_url"] = new_art

                # Fallback: if art_url is empty, check for local cover.jpg/folder.jpg in audio folder
                if not new_art and parsed.get("local_file"):
                    try:
                        audio_p = Path(parsed["local_file"])
                        for candidate_name in ("cover.jpg", "cover.png", "folder.jpg", "front.jpg", "album.jpg"):
                            c_path = audio_p.parent / candidate_name
                            if c_path.exists() and c_path.is_file():
                                new_art = c_path.as_uri()
                                parsed["art_url"] = new_art
                                break
                    except Exception:
                        pass

                if new_art != self._current_art_url:
                    self._current_art_url = new_art
                    self._cached_cover_bytes = None
                    if new_art.startswith("file://"):
                        try:
                            local_p = Path(url2pathname(unquote(urlparse(new_art).path)))
                            if local_p.exists() and local_p.is_file():
                                self._cached_cover_bytes = local_p.read_bytes()
                                ext = local_p.suffix.lower()
                                self._cached_cover_mime = "image/png" if ext == ".png" else "image/jpeg"
                        except Exception as e:
                            log.debug("error reading local cover art: %s", e)
                parsed["has_cover"] = bool(self._cached_cover_bytes or self._current_art_url.startswith("http"))
                await self.on_update(parsed)

    async def get_cover_bytes(self) -> tuple[bytes | None, str]:
        if self._cached_cover_bytes:
            return self._cached_cover_bytes, self._cached_cover_mime
        # If remote http URL, fetch once and cache
        if self._current_art_url.startswith("http://") or self._current_art_url.startswith("https://"):
            try:
                import aiohttp

                async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=4.0)) as s:
                    async with s.get(self._current_art_url) as r:
                        if r.status == 200:
                            data = await r.read()
                            ct = r.headers.get("Content-Type", "image/jpeg")
                            self._cached_cover_bytes = data
                            self._cached_cover_mime = ct
                            return data, ct
            except Exception as e:
                log.debug("error downloading remote cover art: %s", e)
        return None, "image/jpeg"

    async def _run_cmd(self, action: str) -> bool:
        player = self._last_active_player or (self.player_target if self.player_target != "auto" else "%any")
        cmd = ["playerctl"]
        if player:
            cmd.extend(["-p", player])
        cmd.append(action)
        try:
            p = await asyncio.create_subprocess_exec(*cmd, stdout=asyncio.subprocess.DEVNULL, stderr=asyncio.subprocess.DEVNULL)
            await p.wait()
            return p.returncode == 0
        except Exception:
            return False

    async def play(self) -> bool:
        return await self._run_cmd("play")

    async def pause(self) -> bool:
        return await self._run_cmd("pause")

    async def toggle(self) -> bool:
        return await self._run_cmd("play-pause")

    async def next_track(self) -> bool:
        return await self._run_cmd("next")

    async def previous_track(self) -> bool:
        return await self._run_cmd("previous")


class WindowsSmtcTracker(BaseMediaTracker):
    """Windows SMTC (System Media Transport Controls) tracker via WinRT."""

    def __init__(self, on_update_callback) -> None:
        super().__init__(on_update_callback)
        self._worker_task: asyncio.Task | None = None
        self._cached_cover_bytes: bytes | None = None
        self._cached_cover_mime: str = "image/jpeg"
        self._current_session = None

    async def start(self) -> None:
        try:
            import winrt.windows.media.control  # noqa: F401
            import winrt.windows.storage.streams  # noqa: F401
        except ImportError:
            log.warning("winrt modules not installed — Windows SMTC player tracking unavailable")
            return
        self.is_running = True
        self._worker_task = asyncio.create_task(self._poll_loop())

    async def stop(self) -> None:
        self.is_running = False
        if self._worker_task:
            self._worker_task.cancel()
            try:
                await self._worker_task
            except asyncio.CancelledError:
                pass

    async def _poll_loop(self) -> None:
        from winrt.windows.media.control import (
            GlobalSystemMediaTransportControlsSessionManager as SessionManager,
        )
        from winrt.windows.media.control import (
            GlobalSystemMediaTransportControlsSessionPlaybackStatus as PlaybackStatus,
        )
        from winrt.windows.storage.streams import Buffer, InputStreamOptions

        try:
            manager = await SessionManager.request_async()
        except Exception as e:
            log.warning("could not initialize WinRT SessionManager: %s", e)
            return

        last_title = ""
        last_status_name = ""

        while self.is_running:
            try:
                session = manager.get_current_session()
                self._current_session = session

                if not session:
                    if last_status_name != "Stopped":
                        last_status_name = "Stopped"
                        await self.on_update({
                            "available": False,
                            "player": "windows_media",
                            "status": "Stopped",
                            "title": "",
                            "artist": "",
                            "album": "",
                            "position_ms": 0,
                            "duration_ms": None,
                            "has_cover": False,
                            "art_url": "",
                            "local_file": None,
                        })
                    await asyncio.sleep(1.0)
                    continue

                playback_info = session.get_playback_info()
                status_enum = playback_info.playback_status if playback_info else None
                status = "Stopped"
                if status_enum == PlaybackStatus.PLAYING:
                    status = "Playing"
                elif status_enum == PlaybackStatus.PAUSED:
                    status = "Paused"

                props = await session.try_get_media_properties_async()
                title = props.title if (props and props.title) else ""
                artist = props.artist if (props and props.artist) else ""
                album = props.album_title if (props and props.album_title) else ""

                timeline = session.get_timeline_properties()
                pos_ms = 0
                dur_ms = None
                if timeline:
                    try:
                        pos_ms = int(timeline.position.total_seconds() * 1000)
                        if status == "Playing" and timeline.last_updated_time:
                            delta = time.time() - timeline.last_updated_time.timestamp()
                            if delta > 0:
                                pos_ms += int(delta * 1000)
                        end_sec = timeline.end_time.total_seconds()
                        if 0 < end_sec < 86400:
                            dur_ms = int(end_sec * 1000)
                    except Exception:
                        pass

                # Handle cover art update on track change
                if title != last_title and props and props.thumbnail:
                    last_title = title
                    try:
                        readable_stream = await props.thumbnail.open_read_async()
                        buf = Buffer(readable_stream.size)
                        await readable_stream.read_async(buf, buf.capacity, InputStreamOptions.READ_AHEAD)
                        self._cached_cover_bytes = bytes(buf)
                        self._cached_cover_mime = "image/jpeg"
                    except Exception as e:
                        log.debug("error reading Windows SMTC thumbnail: %s", e)
                        self._cached_cover_bytes = None
                elif title != last_title:
                    last_title = title
                    self._cached_cover_bytes = None

                last_status_name = status
                player_id = session.source_app_user_model_id or "windows_media"

                await self.on_update({
                    "available": status in ("Playing", "Paused"),
                    "player": player_id.split("!")[0].split(".")[-1].lower() or "windows_media",
                    "status": status,
                    "title": title or "Unknown Track",
                    "artist": artist,
                    "album": album,
                    "position_ms": max(0, pos_ms),
                    "duration_ms": dur_ms,
                    "has_cover": self._cached_cover_bytes is not None,
                    "art_url": "/api/media/cover" if self._cached_cover_bytes else "",
                    "local_file": None,
                })
            except Exception as e:
                log.debug("Windows SMTC loop error: %s", e)

            await asyncio.sleep(0.9)

    async def get_cover_bytes(self) -> tuple[bytes | None, str]:
        return self._cached_cover_bytes, self._cached_cover_mime

    async def play(self) -> bool:
        if self._current_session:
            try:
                return bool(await self._current_session.try_play_async())
            except Exception:
                pass
        return False

    async def pause(self) -> bool:
        if self._current_session:
            try:
                return bool(await self._current_session.try_pause_async())
            except Exception:
                pass
        return False

    async def toggle(self) -> bool:
        if self._current_session:
            try:
                return bool(await self._current_session.try_toggle_play_pause_async())
            except Exception:
                pass
        return False

    async def next_track(self) -> bool:
        if self._current_session:
            try:
                return bool(await self._current_session.try_skip_next_async())
            except Exception:
                pass
        return False

    async def previous_track(self) -> bool:
        if self._current_session:
            try:
                return bool(await self._current_session.try_skip_previous_async())
            except Exception:
                pass
        return False


class DummyMediaTracker(BaseMediaTracker):
    """In-memory dummy media tracker for unit tests and headless environments."""

    def __init__(self, on_update_callback) -> None:
        super().__init__(on_update_callback)
        self.state = {
            "available": True,
            "player": "mock_player",
            "status": "Playing",
            "title": "Mock Title",
            "artist": "Mock Artist",
            "album": "Mock Album",
            "position_ms": 15000,
            "duration_ms": 180000,
            "has_cover": False,
            "art_url": "",
            "local_file": None,
        }

    async def start(self) -> None:
        self.is_running = True
        await self.on_update(self.state)

    async def stop(self) -> None:
        self.is_running = False

    async def get_cover_bytes(self) -> tuple[bytes | None, str]:
        return None, "image/jpeg"

    async def play(self) -> bool:
        self.state["status"] = "Playing"
        await self.on_update(self.state)
        return True

    async def pause(self) -> bool:
        self.state["status"] = "Paused"
        await self.on_update(self.state)
        return True

    async def toggle(self) -> bool:
        self.state["status"] = "Paused" if self.state["status"] == "Playing" else "Playing"
        await self.on_update(self.state)
        return True

    async def next_track(self) -> bool:
        return True

    async def previous_track(self) -> bool:
        return True


class MediaService:
    """Unified media playback tracking and lyrics coordination service."""

    def __init__(
        self,
        broadcaster,
        config: dict,
        lyrics_service: LyricsService | None = None,
        tracker: BaseMediaTracker | None = None,
    ) -> None:
        self.broadcaster = broadcaster
        self.config = config.get("media", {})
        self.enabled = bool(self.config.get("enabled", False))
        self.lyrics_service = lyrics_service or LyricsService()

        # Last known states
        self.last_track_state: dict = {
            "type": "now_playing",
            "available": False,
            "player": "",
            "status": "Stopped",
            "title": "",
            "artist": "",
            "album": "",
            "position_ms": 0,
            "duration_ms": None,
            "has_cover": False,
            "cover_url": "",
            "track_id": "",
            "source": "local",
        }
        self.last_lyrics_state: dict = {
            "type": "lyrics_update",
            "track": "",
            "instrumental": False,
            "has_synced": False,
            "lines": [],
            "source": "none",
        }

        # Initialize OS-specific or custom tracker
        if tracker:
            self.tracker = tracker
        elif sys.platform == "win32":
            self.tracker = WindowsSmtcTracker(self._handle_tracker_update)
        else:
            player_opt = str(self.config.get("player", "auto"))
            ignore_opt = list(self.config.get("ignore", ["firefox"]))
            self.tracker = LinuxMprisTracker(self._handle_tracker_update, player=player_opt, ignore_players=ignore_opt)

        self._active_track_hash = ""
        self._lyrics_fetch_task: asyncio.Task | None = None

    async def start(self) -> None:
        if not self.enabled:
            log.info("media player tracking is disabled in config")
            return
        log.info("starting media service on platform: %s", sys.platform)
        await self.tracker.start()

    async def stop(self) -> None:
        if self._lyrics_fetch_task and not self._lyrics_fetch_task.done():
            self._lyrics_fetch_task.cancel()
        await self.tracker.stop()

    def _calc_track_hash(self, artist: str, title: str) -> str:
        clean = f"{artist.strip().lower()}:::{title.strip().lower()}"
        return hashlib.md5(clean.encode("utf-8")).hexdigest()

    async def _handle_tracker_update(self, raw_state: dict) -> None:
        """Handle raw state update from active OS tracker."""
        artist = raw_state.get("artist") or ""
        title = raw_state.get("title") or ""
        track_hash = self._calc_track_hash(artist, title) if (artist or title) else ""

        # Cover URL pointer
        cover_url = f"/api/media/cover?h={track_hash}" if raw_state.get("has_cover") else ""

        payload = {
            "type": "now_playing",
            "available": raw_state.get("available", False),
            "player": raw_state.get("player", ""),
            "status": raw_state.get("status", "Stopped"),
            "title": title,
            "artist": artist,
            "album": raw_state.get("album", ""),
            "position_ms": raw_state.get("position_ms", 0),
            "duration_ms": raw_state.get("duration_ms"),
            "has_cover": raw_state.get("has_cover", False),
            "cover_url": cover_url,
            "track_id": track_hash,
            "source": "local",
        }

        self.last_track_state = payload
        await self.broadcaster.broadcast(payload)

        # If track changed and status is Playing, fetch new synchronized lyrics in background
        if track_hash and track_hash != self._active_track_hash and payload.get("status") == "Playing":
            self._active_track_hash = track_hash
            if self._lyrics_fetch_task and not self._lyrics_fetch_task.done():
                self._lyrics_fetch_task.cancel()
            self._lyrics_fetch_task = asyncio.create_task(
                self._load_and_broadcast_lyrics(
                    artist=artist,
                    title=title,
                    album=raw_state.get("album", ""),
                    duration_sec=(payload.get("duration_ms") // 1000) if payload.get("duration_ms") else None,
                    local_file=raw_state.get("local_file"),
                )
            )

    async def _load_and_broadcast_lyrics(
        self,
        artist: str,
        title: str,
        album: str = "",
        duration_sec: int | None = None,
        local_file: str | Path | None = None,
    ) -> None:
        lyrics = await self.lyrics_service.get_lyrics(
            artist=artist,
            title=title,
            album=album,
            duration_sec=duration_sec,
            local_file=local_file,
        )
        lyrics_payload = {
            "type": "lyrics_update",
            "track": lyrics.get("track", f"{artist} — {title}"),
            "instrumental": lyrics.get("instrumental", False),
            "has_synced": lyrics.get("has_synced", False),
            "lines": lyrics.get("lines", []),
            "source": lyrics.get("source", "none"),
        }
        self.last_lyrics_state = lyrics_payload
        await self.broadcaster.broadcast(lyrics_payload)

    async def get_cover_bytes(self) -> tuple[bytes | None, str]:
        return await self.tracker.get_cover_bytes()

    async def play(self) -> bool:
        return await self.tracker.play()

    async def pause(self) -> bool:
        return await self.tracker.pause()

    async def toggle(self) -> bool:
        return await self.tracker.toggle()

    async def next_track(self) -> bool:
        return await self.tracker.next_track()

    async def previous_track(self) -> bool:
        return await self.tracker.previous_track()
