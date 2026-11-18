"""Synchronized lyrics (LRC) service for SYSTEM broadcast overlays.

Fetches synchronized lyrics from LRCLIB (open-source database) and falls back
to local .lrc files alongside media files. Results are cached in memory and on disk.
"""

from __future__ import annotations

import hashlib
import json
import logging
import re
import socket
from pathlib import Path

import aiohttp

log = logging.getLogger("bridge.services.lyrics")

LRCLIB_API_URL = "https://lrclib.net/api/get"
USER_AGENT = "SYSTEM-OBS-Templates/1.2.0 (https://github.com/vokiry/OBS-Templates)"


def parse_lrc(lrc_text: str) -> list[dict[str, int | str]]:
    """Parse standard or enhanced LRC text into sorted timeline cues.

    Returns:
        List of cues: [{'t': <milliseconds>, 'text': <line_text>}, ...]
    """
    if not lrc_text:
        return []

    cues: list[dict[str, int | str]] = []
    # Match one or more [mm:ss.xx] timestamps followed by line content
    pattern = re.compile(r"\[(\d{1,3}):(\d{2}(?:\.\d+)?)\]")

    for raw in lrc_text.splitlines():
        line = raw.strip()
        if not line:
            continue

        # Skip metadata header tags like [ar: Artist], [ti: Title], [offset: 0]
        if re.match(r"^\[[a-zA-Z]+:", line):
            continue

        timestamps = list(pattern.finditer(line))
        if not timestamps:
            continue

        # Strip all timestamp tags to extract pure lyric text
        text = pattern.sub("", line).strip()
        # Clean any remaining inline word timestamps from enhanced LRC (e.g. <00:12.34>)
        text = re.sub(r"<\d{1,3}:\d{2}(?:\.\d+)?>", "", text)
        text = re.sub(r"\s+", " ", text).strip()

        for match in timestamps:
            mins = int(match.group(1))
            secs = float(match.group(2))
            ms = int(round((mins * 60 + secs) * 1000))
            cues.append({"t": ms, "text": text})

    cues.sort(key=lambda x: int(x["t"]))
    return cues


class LyricsService:
    """Manages fetching, parsing, and caching synchronized lyrics."""

    def __init__(self, cache_dir: Path | None = None) -> None:
        self.cache_dir = cache_dir or (Path(__file__).parent.parent / ".lyrics_cache")
        self._memory_cache: dict[str, dict] = {}
        try:
            self.cache_dir.mkdir(parents=True, exist_ok=True)
        except Exception as e:
            log.warning("could not create lyrics cache dir: %s", e)

    def _make_key(self, artist: str, title: str) -> str:
        clean = f"{artist.strip().lower()}:::{title.strip().lower()}"
        return hashlib.md5(clean.encode("utf-8")).hexdigest()

    def _read_disk_cache(self, key: str) -> dict | None:
        if not self.cache_dir.exists():
            return None
        target = self.cache_dir / f"{key}.json"
        if target.exists():
            try:
                return json.loads(target.read_text(encoding="utf-8"))
            except Exception:
                pass
        return None

    def _write_disk_cache(self, key: str, data: dict) -> None:
        if not self.cache_dir.exists():
            return
        target = self.cache_dir / f"{key}.json"
        try:
            target.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
        except Exception as e:
            log.debug("failed to write lyrics disk cache: %s", e)

    def get_local_lrc(self, file_path: str | Path | None) -> list[dict[str, int | str]] | None:
        """Attempt to read local .lrc file alongside an audio file."""
        if not file_path:
            return None
        try:
            p = Path(file_path)
            lrc_path = p.with_suffix(".lrc")
            if lrc_path.exists() and lrc_path.is_file():
                content = lrc_path.read_text(encoding="utf-8", errors="replace")
                parsed = parse_lrc(content)
                if parsed:
                    log.info("loaded local lyrics from %s (%d lines)", lrc_path.name, len(parsed))
                    return parsed
        except Exception as e:
            log.debug("error reading local lrc: %s", e)
        return None

    async def get_lyrics(
        self,
        artist: str,
        title: str,
        album: str = "",
        duration_sec: int | None = None,
        local_file: str | Path | None = None,
    ) -> dict:
        """Retrieve synchronized lyrics for a track.

        Returns:
            {
                "track": "Artist — Title",
                "instrumental": bool,
                "has_synced": bool,
                "lines": [{'t': ms, 'text': '...'}, ...],
                "source": "local" | "lrclib" | "none"
            }
        """
        track_display = f"{artist} — {title}" if artist and title else (title or "Unknown Track")

        # 1. Check local .lrc file first
        local_cues = self.get_local_lrc(local_file)
        if local_cues:
            return {
                "track": track_display,
                "instrumental": False,
                "has_synced": True,
                "lines": local_cues,
                "source": "local",
            }

        # 2. Check memory and disk caches
        key = self._make_key(artist, title)
        if key in self._memory_cache:
            return self._memory_cache[key]

        disk = self._read_disk_cache(key)
        if disk:
            self._memory_cache[key] = disk
            return disk

        # 3. If missing artist or title, cannot query LRCLIB
        if not title or title.lower() in ("unknown", "unknown track", "stopped"):
            return {
                "track": track_display,
                "instrumental": False,
                "has_synced": False,
                "lines": [],
                "source": "none",
            }

        # 4. Fetch from LRCLIB API with strict IPv4 connection (avoids Cloudflare IPv6 handshake error)
        params: dict[str, str | int] = {"track_name": title}
        if artist:
            params["artist_name"] = artist
        if album:
            params["album_name"] = album
        if duration_sec and 1 <= duration_sec <= 3600:
            params["duration"] = int(duration_sec)

        result = {
            "track": track_display,
            "instrumental": False,
            "has_synced": False,
            "lines": [],
            "source": "none",
        }

        try:
            connector = aiohttp.TCPConnector(family=socket.AF_INET)
            timeout = aiohttp.ClientTimeout(total=4.5)
            headers = {"User-Agent": USER_AGENT}

            async with aiohttp.ClientSession(connector=connector, timeout=timeout) as session:
                async with session.get(LRCLIB_API_URL, params=params, headers=headers) as resp:
                    if resp.status == 200:
                        data = await resp.json()
                        instrumental = bool(data.get("instrumental", False))
                        synced = data.get("syncedLyrics") or ""
                        lines = parse_lrc(synced) if synced else []

                        result = {
                            "track": track_display,
                            "instrumental": instrumental,
                            "has_synced": bool(lines),
                            "lines": lines,
                            "source": "lrclib",
                        }
                    elif resp.status == 404:
                        log.debug("lrclib: no lyrics found for %s", track_display)
                    else:
                        log.debug("lrclib: status %d for %s", resp.status, track_display)
        except Exception as e:
            log.debug("lrclib fetch failed for %s: %s", track_display, e)

        # Cache valid or negative result
        self._memory_cache[key] = result
        self._write_disk_cache(key, result)
        return result
