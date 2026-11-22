"""Media Coordinator — serializes an authoritative FIFO of requested tracks."""

from __future__ import annotations

import asyncio
import logging
import uuid
from collections import deque
from typing import Any

log = logging.getLogger("bridge.coordinator.media")


class MediaCoordinator:
    """Coordinates request identity, playback priority, and local-player restoration."""

    def __init__(self, media_service, broadcaster, auto_pause: bool = True) -> None:
        self.media_service = media_service
        self.broadcaster = broadcaster
        self.auto_pause_enabled = auto_pause
        self.current_mode: str = "local"  # "local" | "request"
        self._was_playing_before_request: bool = False
        self._should_resume_local: bool = False
        self._active_request: dict[str, Any] | None = None
        self._request_queue: deque[dict[str, Any]] = deque()
        self.request_queue_len: int = 0
        self._lock = asyncio.Lock()

    @staticmethod
    def _with_identity(payload: dict) -> dict:
        request = dict(payload)
        request_id = request.get("requestId") or request.get("donationId")
        request["requestId"] = str(request_id or uuid.uuid4())
        return request

    async def _broadcast_request_locked(self) -> None:
        self._active_request = self._request_queue[0] if self._request_queue else None
        self.broadcaster.last_media_request = self._active_request
        await self.broadcaster.broadcast({
            "type": "media_mode",
            "mode": "request",
            "request": self._active_request,
            "queue": list(self._request_queue),
            "queueLength": self.request_queue_len,
        })

    async def _finish_local_locked(self) -> None:
        self._active_request = None
        self.current_mode = "local"
        self.broadcaster.last_media_request = None
        should_resume = self._should_resume_local
        self._was_playing_before_request = False
        self._should_resume_local = False
        # Restoration depends on the state captured at request start, not a hot-reloaded preference.
        if should_resume and self.media_service:
            log.info("media_coordinator: restoring previously playing local player")
            await self.media_service.play()
        await self.broadcaster.broadcast({
            "type": "media_mode",
            "mode": "local",
            "request": None,
            "queue": [],
            "queueLength": 0,
            "track": self.media_service.last_track_state if self.media_service else None,
        })

    async def handle_media_request_started(self, payload: dict) -> None:
        """Add or enrich a uniquely identified request without duplicating the FIFO."""
        request = self._with_identity(payload)
        async with self._lock:
            for index, existing in enumerate(self._request_queue):
                if existing["requestId"] == request["requestId"]:
                    merged = {**existing, **{key: value for key, value in request.items() if value not in (None, "")}}
                    merged["requestId"] = existing["requestId"]
                    if existing.get("donationId"):
                        merged["donationId"] = existing["donationId"]
                    self._request_queue[index] = merged
                    await self._broadcast_request_locked()
                    return

            self._request_queue.append(request)
            self.request_queue_len = len(self._request_queue)
            if self.current_mode != "request":
                self.current_mode = "request"
                local_status = self.media_service.last_track_state.get("status") if self.media_service else None
                self._was_playing_before_request = local_status == "Playing"
                self._should_resume_local = self.auto_pause_enabled and self._was_playing_before_request
                if self._should_resume_local and self.media_service:
                    await self.media_service.pause()
            await self._broadcast_request_locked()

    async def handle_media_request_ended(
        self, request_id: str | None = None, donation_id: str | None = None
    ) -> bool:
        """Finish the active request only when its identity matches; stale events are ignored."""
        async with self._lock:
            if not self._request_queue:
                return False
            active = self._request_queue[0]
            if request_id and active["requestId"] != str(request_id):
                log.info("media_coordinator: ignored stale completion for %s", request_id)
                return False
            if donation_id and active.get("donationId") and active["donationId"] != donation_id:
                log.info("media_coordinator: ignored completion for stale donation %s", donation_id)
                return False

            self._request_queue.popleft()
            self.request_queue_len = len(self._request_queue)
            if self._request_queue:
                await self._broadcast_request_locked()
            else:
                await self._finish_local_locked()
            return True

    async def clear_requests(self) -> None:
        """Clear the complete request queue and restore the captured local state."""
        async with self._lock:
            if not self._request_queue and self.current_mode == "local":
                return
            self._request_queue.clear()
            self.request_queue_len = 0
            await self._finish_local_locked()

    async def skip_current(self) -> dict[str, bool | str]:
        """Serialize skip with completions and return separate local/DonateX outcomes."""
        async with self._lock:
            if self.current_mode == "request" and self._request_queue:
                from adapters import donatex

                active = self._request_queue[0]
                donation_id = active.get("donationId")
                donatex_skipped = await donatex.skip_track(donation_id=donation_id)
                await self.broadcaster.broadcast({
                    "type": "media_control",
                    "action": "skip",
                    "requestId": active["requestId"],
                    "donationId": donation_id or "",
                    "donatex_skipped": donatex_skipped,
                })
                return {"ok": True, "donatex_skipped": bool(donatex_skipped), "scope": "request"}
            if self.media_service:
                success = await self.media_service.next_track()
                return {"ok": bool(success), "donatex_skipped": False, "scope": "local"}
            return {"ok": False, "donatex_skipped": False, "scope": "local"}
