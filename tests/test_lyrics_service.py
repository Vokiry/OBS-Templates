"""Unit tests for bridge/services/lyrics_service.py."""

from __future__ import annotations

import tempfile
from pathlib import Path

from bridge.services.lyrics_service import LyricsService, parse_lrc


def test_parse_lrc_standard() -> None:
    text = """
    [00:12.50]Line one text
    [00:15.80]Line two text
    [01:05.10]Line three in next minute
    """
    cues = parse_lrc(text)
    assert len(cues) == 3
    assert cues[0]["t"] == 12500
    assert cues[0]["text"] == "Line one text"
    assert cues[1]["t"] == 15800
    assert cues[2]["t"] == 65100
    assert cues[2]["text"] == "Line three in next minute"


def test_parse_lrc_enhanced_with_word_timestamps() -> None:
    text = """
    [00:10.00]<00:10.00> Hello <00:11.00> world <00:12.00>
    [00:15.00] Plain text line
    """
    cues = parse_lrc(text)
    assert len(cues) == 2
    assert cues[0]["text"] == "Hello world"
    assert cues[0]["t"] == 10000


def test_parse_lrc_skips_metadata_headers() -> None:
    text = """
    [ti:Song Title]
    [ar:Artist Name]
    [al:Album Name]
    [offset:0]
    [00:05.00]Actual first lyric
    """
    cues = parse_lrc(text)
    assert len(cues) == 1
    assert cues[0]["text"] == "Actual first lyric"
    assert cues[0]["t"] == 5000


def test_parse_lrc_empty_and_garbage() -> None:
    assert parse_lrc("") == []
    assert parse_lrc("Just random text without brackets") == []
    assert parse_lrc("[] [not a time] invalid") == []


def test_local_lrc_fallback() -> None:
    with tempfile.TemporaryDirectory() as tmpdir:
        tmp = Path(tmpdir)
        audio = tmp / "test_song.mp3"
        audio.write_bytes(b"dummy")
        lrc = tmp / "test_song.lrc"
        lrc.write_text("[00:01.00]Local lyric line", encoding="utf-8")

        service = LyricsService(cache_dir=tmp / "cache")
        cues = service.get_local_lrc(audio)
        assert cues is not None
        assert len(cues) == 1
        assert cues[0]["text"] == "Local lyric line"
        assert cues[0]["t"] == 1000


def test_caching_and_hashing() -> None:
    with tempfile.TemporaryDirectory() as tmpdir:
        tmp = Path(tmpdir)
        service = LyricsService(cache_dir=tmp / "cache")
        key = service._make_key(" Linkin Park ", " Numb ")
        assert key == service._make_key("linkin park", "numb")

        data = {"track": "Linkin Park — Numb", "synced": True, "lines": []}
        service._write_disk_cache(key, data)
        loaded = service._read_disk_cache(key)
        assert loaded == data
