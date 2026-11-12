"""WebSocket connection manager, state cache, and broadcast dispatcher."""

import asyncio
import base64
import json
import logging
import re
import time
from collections import deque as _deque
from datetime import datetime
from pathlib import Path
from urllib.parse import urlparse

from aiohttp import WSMsgType, web

from adapters import base
from services import yandex_tts
from services.goal_service import parse_amount

log = logging.getLogger("bridge.broadcaster")


class Broadcaster:
    """Manages WebSocket clients, caches broadcast states, and handles overlay events."""

    MAX_CLIENTS = 50  # prevent memory exhaustion from too many WebSocket connections

    def __init__(self):
        self.clients: set[web.WebSocketResponse] = set()
        self.last_status = None
        self.last_7tv_emotes = None
        self.last_twitch_badges = None
        self.last_sounds_config = None
        self.last_chat_config = None
        self.active_poll = None
        self.active_prediction = None
        self.chat_history: _deque = _deque(maxlen=30)
        self.last_stream_stats = None
        self.goal_config = None
        self.last_goal = None
        self.config_path: Path | None = None
        self.last_alert = None
        self.dnd_active = False
        self._background_tasks: set[asyncio.Task] = set()  # prevent GC of fire-and-forget tasks

        # Appearance & Theme
        self.current_theme = "mocha-teal"
        self.last_theme = None

        # TTS state
        self.tts_config: dict = {}
        self._tts_queue: _deque = _deque(maxlen=4)
        self._tts_worker_running = False

    def init_goal(self, goal_cfg: dict, config_path: Path | None = None) -> None:
        """Initialize donation goal configuration and pre-calculate percent."""
        self.goal_config = dict(goal_cfg)
        if config_path:
            self.config_path = config_path
        cur = float(self.goal_config.get("current", 0.0))
        tgt = max(0.01, float(self.goal_config.get("target", 10000.0)))
        pct = round(min(100.0, (cur / tgt) * 100), 1)
        self.last_goal = {
            "type": "goal_update",
            "enabled": bool(self.goal_config.get("enabled", True)),
            "title": str(self.goal_config.get("title", "Сбор на цель")),
            "current": cur,
            "target": tgt,
            "currency": str(self.goal_config.get("currency", "RUB")),
            "percent": pct,
        }

    def _persist_goal_current(self) -> None:
        """Persist updated goal progress to config.toml."""
        if not self.config_path or not self.config_path.exists() or not self.goal_config:
            return
        try:
            txt = self.config_path.read_text("utf-8")
            new_cur = f"{float(self.goal_config['current']):.1f}"
            new_txt = re.sub(r"(?m)^(current\s*=\s*)[0-9.]+", rf"\g<1>{new_cur}", txt)
            if new_txt != txt:
                self.config_path.write_text(new_txt, "utf-8")
        except Exception as e:
            log.warning("failed to persist goal progress to config.toml: %s", e)

    # ── Appearance & Theme ───────────────────────────────────────────────

    def init_appearance(self, appearance_cfg: dict) -> None:
        """Initialize active visual theme preset."""
        if not appearance_cfg:
            return
        theme = str(appearance_cfg.get("theme", "mocha-teal")).strip() or "mocha-teal"
        self.current_theme = theme
        self.last_theme = {"type": "theme_update", "theme": theme}

    # ── TTS integration ──────────────────────────────────────────────────

    def init_tts(self, tts_cfg: dict) -> None:
        """Initialize Text-To-Speech settings."""
        self.tts_config = dict(tts_cfg)

    def _tts_mode(self) -> str:
        return str(self.tts_config.get("mode", "off")).lower()

    def _tts_voice_for_user(self, username: str) -> str:
        # Check VIP assignments first
        vip = self.tts_config.get("vip_voices", {})
        if username.lower() in {k.lower() for k in vip}:
            for k, v in vip.items():
                if k.lower() == username.lower():
                    return v
        # Deterministic pick from random pool
        pool = self.tts_config.get("random_pool", yandex_tts.DEFAULT_RANDOM_POOL)
        if not pool:
            pool = yandex_tts.DEFAULT_RANDOM_POOL
        return yandex_tts.pick_voice(username, pool)

    def enqueue_tts(
        self,
        username: str,
        text: str,
        is_reward: bool = False,
        force: bool = False,
        force_voice: str | None = None,
        force_speed: str | None = None,
        force_emotion: str | None = None,
    ) -> None:
        """Sanitize and enqueue text for TTS synthesis."""
        mode = self._tts_mode()
        if not force:
            if mode == "off":
                return
            if mode == "rewards" and not is_reward:
                return
            if yandex_tts.is_bot(username):
                return
        blacklist = self.tts_config.get("blacklist", [])
        cleaned = yandex_tts.preprocess_text(
            text,
            max_length=int(self.tts_config.get("max_length", 200)),
            blacklist=blacklist,
        )
        if not cleaned:
            return
        show_card = (is_reward and mode == "rewards") or (force and is_reward)
        voice = force_voice or self._tts_voice_for_user(username)
        speed = str(force_speed or self.tts_config.get("speed", "1.0"))
        emotion = str(force_emotion or self.tts_config.get("emotion", "neutral"))
        self._tts_queue.append(
            {
                "username": username,
                "text": cleaned,
                "voice": voice,
                "speed": speed,
                "emotion": emotion,
                "show_card": show_card,
            }
        )
        if not self._tts_worker_running:
            self._create_background_task(self._tts_worker())

    async def _tts_worker(self) -> None:
        """Worker loop processing TTS queue with rate-limit protection."""
        self._tts_worker_running = True
        try:
            while self._tts_queue:
                item = self._tts_queue.popleft()
                speed = item.get("speed") or str(self.tts_config.get("speed", "1.0"))
                emotion = item.get("emotion") or str(self.tts_config.get("emotion", "neutral"))
                endpoint = str(self.tts_config.get("endpoint", yandex_tts.DEFAULT_WS_ENDPOINT))
                auth_token = str(self.tts_config.get("auth_token", yandex_tts.DEFAULT_AUTH_TOKEN))

                audio = await yandex_tts.generate(
                    text=item["text"],
                    voice=item["voice"],
                    speed=speed,
                    emotion=emotion,
                    endpoint=endpoint,
                    auth_token=auth_token,
                )
                if audio:
                    if self.dnd_active:
                        log.debug("tts: skipping speech delivery because DND is active")
                    else:
                        payload = {
                            "type": "tts_speak",
                            "audio_b64": base64.b64encode(audio).decode("ascii"),
                            "nickname": item["username"],
                            "text": item["text"],
                            "show_card": item["show_card"],
                            "volume": float(self.tts_config.get("volume", 0.8)),
                        }
                        await self.broadcast(payload)
                    # Minimum gap between TTS generations (rate-limit protection)
                    await asyncio.sleep(0.8)
                else:
                    log.debug("tts: skipping failed generation for %s", item["username"])
        except asyncio.CancelledError:
            pass
        except Exception as e:
            log.warning("tts: worker error: %s", e)
        finally:
            self._tts_worker_running = False

    async def stop_tts(self) -> None:
        """Clear TTS queue and broadcast tts_stop to all overlays."""
        self._tts_queue.clear()
        await self.broadcast({"type": "tts_stop"})

    # ── WebSocket Lifecycle ──────────────────────────────────────────────

    async def attach(self, request: web.Request) -> web.WebSocketResponse:
        """Handle incoming WebSocket connection with CSWSH protection and state caching."""
        origin = request.headers.get("Origin", "")
        host_header = request.headers.get("Host", "")
        if origin:
            parsed = urlparse(origin)
            origin_host = f"{parsed.hostname}:{parsed.port}" if parsed.port else parsed.hostname
            allowed_hosts = {
                host_header,
                "localhost",
                "127.0.0.1",
                f"localhost:{request.url.port}",
                f"127.0.0.1:{request.url.port}",
            }
            if origin_host not in allowed_hosts and parsed.hostname not in ("localhost", "127.0.0.1"):
                log.warning("WebSocket connection rejected: origin %s not allowed", origin)
                return web.Response(status=403, text="Origin not allowed")

        if len(self.clients) >= self.MAX_CLIENTS:
            log.warning("WebSocket connection rejected: max %d clients reached", self.MAX_CLIENTS)
            return web.Response(status=503, text="Too many connections")

        socket = web.WebSocketResponse(heartbeat=20)
        await socket.prepare(request)
        self.clients.add(socket)
        log.info("overlay attached (%d total)", len(self.clients))

        # Immediately send cached state to newly attached overlay
        try:
            if self.last_status:
                await socket.send_str(base.encode(self.last_status))
            if self.last_theme:
                await socket.send_str(base.encode(self.last_theme))
            if self.last_7tv_emotes:
                await socket.send_str(base.encode(self.last_7tv_emotes))
            if self.last_twitch_badges:
                await socket.send_str(base.encode(self.last_twitch_badges))
            if self.last_sounds_config:
                await socket.send_str(base.encode(self.last_sounds_config))
            if self.last_chat_config:
                await socket.send_str(base.encode(self.last_chat_config))
            if self.active_poll:
                ends_at = self.active_poll.get("endsAt")
                if ends_at:
                    try:
                        if datetime.fromisoformat(ends_at).timestamp() < time.time():
                            self.active_poll = None
                    except Exception:
                        pass
                if self.active_poll and self.active_poll.get("action") != "end":
                    await socket.send_str(base.encode(self.active_poll))
            if self.active_prediction:
                st = str(self.active_prediction.get("status", "")).lower()
                if st in ("resolved", "canceled") or self.active_prediction.get("action") == "end":
                    self.active_prediction = None
                else:
                    await socket.send_str(base.encode(self.active_prediction))
            if self.chat_history:
                await socket.send_str(
                    base.encode({"type": "chat_history", "messages": list(self.chat_history)})
                )
            if self.last_stream_stats:
                await socket.send_str(base.encode(self.last_stream_stats))
            if self.last_goal:
                await socket.send_str(base.encode(self.last_goal))
        except Exception:
            pass

        try:
            async for msg in socket:
                if msg.type == WSMsgType.TEXT:
                    try:
                        data = json.loads(msg.data)
                        if isinstance(data, dict):
                            await self.handle_client_event(data)
                    except Exception:
                        pass
                elif msg.type == WSMsgType.ERROR:
                    break
        finally:
            self.clients.discard(socket)
            log.info("overlay detached (%d total)", len(self.clients))
        return socket

    async def handle_client_event(self, data: dict) -> None:
        """Handle events received from client overlays or OBS dock."""
        msg_type = data.get("type")
        if msg_type == "media_finished":
            log.info("media playback finished, notifying DonateX skip...")
            from adapters import donatex

            await donatex.skip_track()
        elif msg_type == "media_control":
            if data.get("action") == "skip":
                log.info("media skip requested by client")
                from adapters import donatex

                await donatex.skip_track()
            await self.broadcast(data)
        elif msg_type == "alert_skip":
            log.info("alert skip requested by client")
            from adapters import donatex, donationalerts

            await donatex.skip_donation()
            await donationalerts.skip_donation()
            await self.broadcast({"type": "alert_skip"})
        elif msg_type == "tts_stop":
            log.info("TTS stop requested by client")
            await self.stop_tts()
        elif msg_type == "alert_replay":
            if self.last_alert:
                log.info("replaying last alert: %s", self.last_alert.get("title"))
                replay_payload = dict(self.last_alert)
                replay_payload.pop("dnd", None)
                replay_payload["is_replay"] = True
                await self.broadcast(replay_payload)
        elif msg_type == "dnd_control":
            self.dnd_active = bool(data.get("active"))
            log.info("DND mode toggled: %s", self.dnd_active)
            await self.broadcast({"type": "dnd_status", "active": self.dnd_active})
        elif msg_type == "tts_test":
            self.enqueue_tts(
                username=data.get("user", "Tester"),
                text=data.get("text", "Проверка синтеза речи."),
                force=True,
                force_voice=data.get("voice"),
                force_speed=data.get("speed"),
                force_emotion=data.get("emotion"),
            )
        elif msg_type in ("status", "countdown_control", "chat_clear"):
            await self.broadcast(data)

    def _create_background_task(self, coro):
        """Create a background task with proper reference tracking to prevent GC."""
        task = asyncio.create_task(coro)
        self._background_tasks.add(task)
        task.add_done_callback(self._background_tasks.discard)

    async def _clear_poll_delayed(self, delay: float):
        await asyncio.sleep(delay)
        self.active_poll = None

    async def _clear_prediction_delayed(self, delay: float):
        await asyncio.sleep(delay)
        self.active_prediction = None

    async def broadcast(self, payload: dict) -> None:
        """Concurrently broadcast a normalized payload to all connected clients."""
        msg_type = payload.get("type")
        if msg_type == "status":
            self.last_status = payload
        elif msg_type == "7tv_emotes":
            self.last_7tv_emotes = payload
        elif msg_type == "twitch_badges":
            self.last_twitch_badges = payload
        elif msg_type == "theme_update":
            self.last_theme = payload
            self.current_theme = payload.get("theme", self.current_theme)
        elif msg_type == "sounds_update":
            self.last_sounds_config = payload
        elif msg_type == "stream_stats":
            self.last_stream_stats = payload
        elif msg_type == "goal_update":
            self.last_goal = payload
        elif msg_type == "alert":
            self.last_alert = dict(payload)
            if self.dnd_active:
                payload["dnd"] = True
            if payload.get("kind") == "donate" and self.goal_config and self.goal_config.get("enabled"):
                amount_val = parse_amount(payload.get("amount"))
                if amount_val > 0:
                    self.goal_config["current"] = round(
                        float(self.goal_config.get("current", 0.0)) + amount_val, 2
                    )
                    cur = self.goal_config["current"]
                    tgt = max(0.01, float(self.goal_config.get("target", 10000.0)))
                    pct = round(min(100.0, (cur / tgt) * 100), 1)
                    goal_payload = {
                        "type": "goal_update",
                        "enabled": bool(self.goal_config.get("enabled", True)),
                        "title": str(self.goal_config.get("title", "Сбор на цель")),
                        "current": cur,
                        "target": tgt,
                        "currency": str(self.goal_config.get("currency", "RUB")),
                        "percent": pct,
                    }
                    self.last_goal = goal_payload
                    self._create_background_task(self.broadcast(goal_payload))
                    self._persist_goal_current()
        elif msg_type == "chat":
            self.chat_history.append(payload)
            # TTS: enqueue chat messages for speech synthesis
            subtype = payload.get("subtype", "message")
            username = payload.get("user", "")
            text = payload.get("text", "")
            if subtype == "reward":
                reward_name = str(payload.get("rewardTitle", "")).strip().lower()
                configured_name = str(self.tts_config.get("reward_name", "TTS")).strip().lower()
                if reward_name == configured_name:
                    self.enqueue_tts(username, text, is_reward=True)
            elif subtype == "message":
                self.enqueue_tts(username, text, is_reward=False)
        elif msg_type == "chat_clear":
            self.chat_history.clear()
        elif msg_type == "poll":
            action = payload.get("action")
            if action in ("begin", "progress"):
                self.active_poll = payload
            elif action == "end":
                self.active_poll = payload
                self._create_background_task(self._clear_poll_delayed(12))
        elif msg_type == "prediction":
            action = payload.get("action")
            if action in ("begin", "progress", "lock"):
                self.active_prediction = payload
            elif action == "end":
                self.active_prediction = payload
                self._create_background_task(self._clear_prediction_delayed(12))

        message = base.encode(payload)
        clients = list(self.clients)
        if not clients:
            return
        results = await asyncio.gather(
            *(socket.send_str(message) for socket in clients),
            return_exceptions=True,
        )
        for socket, result in zip(clients, results, strict=False):
            if isinstance(result, Exception):
                self.clients.discard(socket)
