"""Media Coordinator — arbitrates between local playback and ordered tracks.

Handles auto-pausing background music (MPRIS / SMTC) when a viewer orders
a YouTube track via DonateX or Twitch Channel Points, and resumes local music
when the request queue empties.
"""

from __future__ import annotations

import logging
from typing import Any

log = logging.getLogger("bridge.coordinator.media")


class MediaCoordinator:
    """Coordinates priority between ordered media requests and local player."""

    def __init__(self, media_service, broadcaster, auto_pause: bool = True) -> None:
        self.media_service = media_service
        self.broadcaster = broadcaster
        self.auto_pause_enabled = auto_pause
        self.current_mode: str = "local"  # "local" | "request"
        self._was_playing_before_request: bool = False
        self._active_request: dict[str, Any] | None = None
        self.request_queue_len: int = 0

    async def handle_media_request_started(self, payload: dict) -> None:
        """Called when a media request (DonateX / Channel Points) starts playback."""
        self._active_request = payload
        self.current_mode = "request"

        log.info(
            "media_coordinator: request started: %s (by %s)",
            payload.get("title", "Unknown"),
            payload.get("user", "viewer"),
        )

        # Auto-pause local music player if active
        if self.auto_pause_enabled and self.media_service:
            local_status = self.media_service.last_track_state.get("status")
            if local_status == "Playing":
                log.info("media_coordinator: auto-pausing local player during media request")
                self._was_playing_before_request = True
                await self.media_service.pause()

        await self.broadcaster.broadcast({
            "type": "media_mode",
            "mode": "request",
            "request": payload,
        })

    async def handle_media_request_ended(self) -> None:
        """Called when a media request video finishes or queue empties."""
        log.info("media_coordinator: media request playback completed, restoring local playback")
        self._active_request = None
        self.current_mode = "local"
        self._was_playing_before_request = False

        # Resume local music player if enabled
        if self.auto_pause_enabled and self.media_service:
            log.info("media_coordinator: resuming local player after media request")
            await self.media_service.play()

        await self.broadcaster.broadcast({
            "type": "media_mode",
            "mode": "local",
            "request": None,
        })

    async def skip_current(self) -> bool:
        """Unified skip command: skips media request if active, else skips local track."""
        if self.current_mode == "request":
            from adapters import donatex

            log.info("media_coordinator: skipping active media request")
            return await donatex.skip_track()
        elif self.media_service:
            log.info("media_coordinator: skipping local player track")
            return await self.media_service.next_track()
        return False
