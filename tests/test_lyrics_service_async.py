"""Async integration tests for LyricsService."""

from __future__ import annotations

import tempfile
from pathlib import Path

import pytest

from bridge.services.lyrics_service import LyricsService


@pytest.mark.asyncio
async def test_get_lyrics_unknown_empty() -> None:
    with tempfile.TemporaryDirectory() as tmpdir:
        service = LyricsService(cache_dir=Path(tmpdir))
        result = await service.get_lyrics(artist="", title="Unknown")
        assert result["has_synced"] is False
        assert result["source"] == "none"


@pytest.mark.asyncio
async def test_get_lyrics_local_preferred() -> None:
    with tempfile.TemporaryDirectory() as tmpdir:
        tmp = Path(tmpdir)
        audio = tmp / "my_song.flac"
        audio.write_bytes(b"dummy")
        lrc = tmp / "my_song.lrc"
        lrc.write_text("[00:03.50]Local Line One\n[00:08.00]Local Line Two", encoding="utf-8")

        service = LyricsService(cache_dir=tmp / "cache")
        result = await service.get_lyrics(artist="Band", title="Song", local_file=audio)
        assert result["has_synced"] is True
        assert result["source"] == "local"
        assert len(result["lines"]) == 2
        assert result["lines"][0]["text"] == "Local Line One"
