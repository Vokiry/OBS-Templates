"""Unit tests for bridge/services/media_service.py and media_coordinator.py."""

from __future__ import annotations

import pytest

from bridge.core.media_coordinator import MediaCoordinator
from bridge.services.media_service import DummyMediaTracker, MediaService, parse_mpris_line


def test_parse_mpris_line_active_track() -> None:
    # 0: playerName, 1: status, 2: title, 3: artist, 4: album, 5: length (us), 6: pos (us), 7: artUrl, 8: url
    line = "vlc\tPlaying\tSong Title\tArtist Name\tAlbum Name\t180000000\t15000000\tfile:///tmp/cover.jpg\tfile:///tmp/song.mp3"
    parsed = parse_mpris_line(line)
    assert parsed is not None
    assert parsed["available"] is True
    assert parsed["player"] == "vlc"
    assert parsed["status"] == "Playing"
    assert parsed["title"] == "Song Title"
    assert parsed["artist"] == "Artist Name"
    assert parsed["album"] == "Album Name"
    assert parsed["duration_ms"] == 180000
    assert parsed["position_ms"] == 15000
    assert parsed["has_cover"] is True
    assert parsed["art_url"] == "file:///tmp/cover.jpg"
    assert parsed["local_file"] == "/tmp/song.mp3"


def test_parse_mpris_line_empty_stopped() -> None:
    parsed = parse_mpris_line("")
    assert parsed is not None
    assert parsed["available"] is False
    assert parsed["status"] == "Stopped"


def test_parse_mpris_line_live_stream_duration() -> None:
    # YouTube livestream length is ~9223372036854000000 us (> 24 hours) -> duration_ms should be None
    line = "firefox\tPlaying\tLive Stream\tStreamer\t\t9223372036854000000\t5000000\t\t"
    parsed = parse_mpris_line(line)
    assert parsed is not None
    assert parsed["duration_ms"] is None
    assert parsed["position_ms"] == 5000


def test_parse_mpris_line_title_fallback_from_url() -> None:
    # When title is empty, extracts stem of file:///path/track_one.mp3
    line = "vlc\tPlaying\t\t\t\t30000000\t1000000\t\tfile:///home/user/Music/track_one.mp3"
    parsed = parse_mpris_line(line)
    assert parsed is not None
    assert parsed["title"] == "track_one"


class MockBroadcaster:
    def __init__(self) -> None:
        self.broadcasted: list[dict] = []

    async def broadcast(self, payload: dict) -> None:
        self.broadcasted.append(payload)


@pytest.mark.asyncio
async def test_dummy_media_service_flow() -> None:
    broadcaster = MockBroadcaster()
    tracker = DummyMediaTracker(lambda s: None)
    service = MediaService(broadcaster, {"media": {"enabled": True}}, tracker=tracker)

    # Wire update to service handler
    tracker.on_update = service._handle_tracker_update
    await service.start()

    assert service.last_track_state["title"] == "Mock Title"
    assert service.last_track_state["status"] == "Playing"
    assert len(broadcaster.broadcasted) > 0
    assert broadcaster.broadcasted[-1]["type"] == "now_playing"

    # Test pause
    await service.pause()
    assert service.last_track_state["status"] == "Paused"

    await service.stop()


@pytest.mark.asyncio
async def test_media_coordinator_auto_pause_and_resume() -> None:
    broadcaster = MockBroadcaster()
    tracker = DummyMediaTracker(lambda s: None)
    service = MediaService(broadcaster, {"media": {"enabled": True}}, tracker=tracker)
    tracker.on_update = service._handle_tracker_update
    await tracker.start()

    coordinator = MediaCoordinator(service, broadcaster, auto_pause=True)
    assert coordinator.current_mode == "local"

    # Local player is Playing -> Media request arrives
    await coordinator.handle_media_request_started({"title": "Ordered Song", "user": "DonorBob"})
    assert coordinator.current_mode == "request"
    assert coordinator._was_playing_before_request is True
    # Local player should be paused
    assert service.last_track_state["status"] == "Paused"

    # Media request ends
    await coordinator.handle_media_request_ended()
    assert coordinator.current_mode == "local"
    assert coordinator._was_playing_before_request is False
    # Local player should be resumed
    assert service.last_track_state["status"] == "Playing"


@pytest.mark.asyncio
async def test_broadcaster_media_finished_and_skip_resumes_local() -> None:
    from bridge.alerts_bridge import Broadcaster

    broadcaster = Broadcaster()
    tracker = DummyMediaTracker(lambda s: None)
    service = MediaService(broadcaster, {"media": {"enabled": True}}, tracker=tracker)
    tracker.on_update = service._handle_tracker_update
    await tracker.start()

    coordinator = MediaCoordinator(service, broadcaster, auto_pause=True)
    broadcaster.media_coordinator = coordinator

    # 1. Start media request -> pauses local music
    await broadcaster.broadcast({"type": "media_request", "youtubeId": "abc", "user": "Bob"})
    await coordinator.handle_media_request_started({"type": "media_request", "youtubeId": "abc"})
    assert service.last_track_state["status"] == "Paused"
    assert broadcaster.last_media_request is not None

    # 2. Client sends media_finished -> must clear last_media_request and resume local music
    await broadcaster.handle_client_event({"type": "media_finished", "source": "donatex"})
    assert broadcaster.last_media_request is None
    assert coordinator.current_mode == "local"
    assert service.last_track_state["status"] == "Playing"

    # 3. Start another media request -> pause again, then skip via media_control
    await coordinator.handle_media_request_started({"type": "media_request", "youtubeId": "xyz"})
    assert service.last_track_state["status"] == "Paused"
    await broadcaster.broadcast({"type": "media_control", "action": "skip"})
    # Allow background task to run
    import asyncio

    await asyncio.sleep(0.05)
    assert coordinator.current_mode == "local"
    assert service.last_track_state["status"] == "Playing"
