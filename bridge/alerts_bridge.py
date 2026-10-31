import base64
import re
import asyncio
import argparse
import html as html_mod
import json
import logging
import secrets
import sys
import time
from collections import deque as _deque
from pathlib import Path
from tomllib import load as toml_load

from aiohttp import WSMsgType, web

sys.path.insert(0, str(Path(__file__).parent))

from adapters import base
from services import yandex_tts

log = logging.getLogger("bridge")

# API key for protecting state-changing endpoints (generated at startup)
API_KEY: str = ""


class Broadcaster:
    def __init__(self):
        self.clients = set()
        self.last_status = None
        self.last_7tv_emotes = None
        self.last_twitch_badges = None
        self.last_sounds_config = None
        self.active_poll = None
        self.active_prediction = None
        self.chat_history = _deque(maxlen=30)
        self.last_stream_stats = None
        self.goal_config = None
        self.last_goal = None
        self.config_path = None
        self._background_tasks = set()  # prevent GC of fire-and-forget tasks
        # TTS state
        self.tts_config: dict = {}
        self._tts_queue: _deque = _deque(maxlen=4)
        self._tts_worker_running = False

    MAX_CLIENTS = 50  # prevent memory exhaustion from too many WebSocket connections

    def init_goal(self, goal_cfg: dict, config_path: Path | None = None) -> None:
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
        if not self.config_path or not self.config_path.exists() or not self.goal_config:
            return
        try:
            txt = self.config_path.read_text("utf-8")
            import re
            new_cur = f'{float(self.goal_config["current"]):.1f}'
            new_txt = re.sub(r'(?m)^(current\s*=\s*)[0-9.]+', rf'\g<1>{new_cur}', txt)
            if new_txt != txt:
                self.config_path.write_text(new_txt, "utf-8")
        except Exception as e:
            log.warning("failed to persist goal progress to config.toml: %s", e)

    # ── TTS integration ──────────────────────────────────────────────────

    def init_tts(self, tts_cfg: dict) -> None:
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

    def enqueue_tts(self, username: str, text: str, is_reward: bool = False, force: bool = False, force_voice: str | None = None, force_speed: str | None = None, force_emotion: str | None = None) -> None:
        mode = self._tts_mode()
        if not force:
            if mode == "off":
                return
            if mode == "rewards" and not is_reward:
                return
            if yandex_tts.is_bot(username):
                return
        cleaned = yandex_tts.preprocess_text(
            text,
            max_length=int(self.tts_config.get("max_length", 200))
        )
        if not cleaned:
            return
        show_card = (is_reward and mode == "rewards") or (force and is_reward)
        voice = force_voice or self._tts_voice_for_user(username)
        speed = str(force_speed or self.tts_config.get("speed", "1.0"))
        emotion = str(force_emotion or self.tts_config.get("emotion", "neutral"))
        self._tts_queue.append({
            "username": username,
            "text": cleaned,
            "voice": voice,
            "speed": speed,
            "emotion": emotion,
            "show_card": show_card,
        })
        if not self._tts_worker_running:
            self._create_background_task(self._tts_worker())

    async def _tts_worker(self) -> None:
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
        self._tts_queue.clear()
        await self.broadcast({"type": "tts_stop"})

    async def attach(self, request) -> web.WebSocketResponse:
        # Validate Origin to prevent Cross-Site WebSocket Hijacking (CSWSH)
        origin = request.headers.get("Origin", "")
        host_header = request.headers.get("Host", "")
        if origin:
            from urllib.parse import urlparse
            parsed = urlparse(origin)
            origin_host = f"{parsed.hostname}:{parsed.port}" if parsed.port else parsed.hostname
            # Allow same-origin, localhost variants, and OBS browser sources (no origin)
            allowed_hosts = {host_header, "localhost", "127.0.0.1",
                             f"localhost:{request.url.port}", f"127.0.0.1:{request.url.port}"}
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
            if self.last_7tv_emotes:
                await socket.send_str(base.encode(self.last_7tv_emotes))
            if self.last_twitch_badges:
                await socket.send_str(base.encode(self.last_twitch_badges))
            if self.last_sounds_config:
                await socket.send_str(base.encode(self.last_sounds_config))
            if self.active_poll:
                await socket.send_str(base.encode(self.active_poll))
            if self.active_prediction:
                await socket.send_str(base.encode(self.active_prediction))
            if self.chat_history:
                await socket.send_str(base.encode({
                    "type": "chat_history",
                    "messages": list(self.chat_history)
                }))
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
        """Create a background task with proper reference tracking and error logging."""
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
        msg_type = payload.get("type")
        if msg_type == "status":
            self.last_status = payload
        elif msg_type == "7tv_emotes":
            self.last_7tv_emotes = payload
        elif msg_type == "twitch_badges":
            self.last_twitch_badges = payload
        elif msg_type == "sounds_update":
            self.last_sounds_config = payload
        elif msg_type == "stream_stats":
            self.last_stream_stats = payload
        elif msg_type == "goal_update":
            self.last_goal = payload
        elif msg_type == "alert" and payload.get("kind") == "donate":
            if self.goal_config and self.goal_config.get("enabled"):
                amount_val = parse_amount(payload.get("amount"))
                if amount_val > 0:
                    self.goal_config["current"] = round(float(self.goal_config.get("current", 0.0)) + amount_val, 2)
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
                # Channel points reward redemption
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
            return_exceptions=True
        )
        for socket, result in zip(clients, results):
            if isinstance(result, Exception):
                self.clients.discard(socket)



def parse_amount(val) -> float:
    """Extract numeric float from strings like '500 ₽', '1 500,50 RUB', or raw numbers."""
    if val is None:
        return 0.0
    if isinstance(val, (int, float)):
        return float(val)
    s = str(val).replace(" ", "").replace("\xa0", "").replace(",", ".")
    import re
    match = re.search(r"[-+]?\d*\.?\d+", s)
    if match:
        try:
            return float(match.group(0))
        except ValueError:
            pass
    return 0.0


def toml_escape(val) -> str:
    if val is None:
        return ""
    return str(val).replace("\\", "\\\\").replace('"', '\\"').replace("\n", "").replace("\r", "")


def serialize_toml(cfg: dict) -> str:
    lines = [
        "[server]",
        f'host = "{toml_escape(cfg.get("server", {}).get("host", "127.0.0.1"))}"',
        f'port = {int(cfg.get("server", {}).get("port", 8787))}',
        "",
        "[twitch]",
        f'enabled = {str(cfg.get("twitch", {}).get("enabled", False)).lower()}',
        f'client_id = "{toml_escape(cfg.get("twitch", {}).get("client_id", ""))}"',
        f'client_secret = "{toml_escape(cfg.get("twitch", {}).get("client_secret", ""))}"',
        f'include_follows = {str(cfg.get("twitch", {}).get("include_follows", False)).lower()}',
        f'redirect_url = "{toml_escape(cfg.get("twitch", {}).get("redirect_url", "http://localhost:3000"))}"',
        "",
        "[twitch_chat]",
        f'enabled = {str(cfg.get("twitch_chat", {}).get("enabled", False)).lower()}',
        f'channel = "{toml_escape(cfg.get("twitch_chat", {}).get("channel", ""))}"',
        f'seven_tv_source = "{toml_escape(cfg.get("twitch_chat", {}).get("seven_tv_source", "direct"))}"',
        f'seven_tv_mirror = "{toml_escape(cfg.get("twitch_chat", {}).get("seven_tv_mirror", "https://enhanced.jeetbot.cc"))}"',
        "",
        "[donationalerts]",
        f'enabled = {str(cfg.get("donationalerts", {}).get("enabled", False)).lower()}',
        f'client_id = "{toml_escape(cfg.get("donationalerts", {}).get("client_id", ""))}"',
        f'client_secret = "{toml_escape(cfg.get("donationalerts", {}).get("client_secret", ""))}"',
        f'access_token = "{toml_escape(cfg.get("donationalerts", {}).get("access_token", ""))}"',
        "",
        "[donatex]",
        f'enabled = {str(cfg.get("donatex", {}).get("enabled", False)).lower()}',
        f'token = "{toml_escape(cfg.get("donatex", {}).get("token", ""))}"',
        "",
        "[goal]",
        f'enabled = {str(cfg.get("goal", {}).get("enabled", False)).lower()}',
        f'title = "{toml_escape(cfg.get("goal", {}).get("title", "Сбор на цель"))}"',
        f'current = {float(cfg.get("goal", {}).get("current", 0.0)):.1f}',
        f'target = {float(cfg.get("goal", {}).get("target", 10000.0)):.1f}',
        f'currency = "{toml_escape(cfg.get("goal", {}).get("currency", "RUB"))}"',
        "",
        "# 6. TEXT-TO-SPEECH (YANDEX ALICE)",
        "[tts]",
        f'mode = "{toml_escape(cfg.get("tts", {}).get("mode", "off"))}"',
        f'voice = "{toml_escape(cfg.get("tts", {}).get("voice", "shitova.us"))}"',
        f'speed = "{toml_escape(cfg.get("tts", {}).get("speed", "1"))}"',
        f'emotion = "{toml_escape(cfg.get("tts", {}).get("emotion", "neutral"))}"',
        f'volume = {float(cfg.get("tts", {}).get("volume", 0.8)):.2f}',
        f'max_length = {int(cfg.get("tts", {}).get("max_length", 200))}',
        f'reward_name = "{toml_escape(cfg.get("tts", {}).get("reward_name", "TTS"))}"',
        f'auth_token = "{toml_escape(cfg.get("tts", {}).get("auth_token", yandex_tts.DEFAULT_AUTH_TOKEN))}"',
        "",
    ]

    # Serialize random_pool as TOML array
    pool = cfg.get("tts", {}).get("random_pool", yandex_tts.DEFAULT_RANDOM_POOL)
    pool_str = ", ".join(f'"{toml_escape(v)}"' for v in pool)
    lines.insert(-1, f"random_pool = [{pool_str}]")

    # Serialize vip_voices as [tts.vip_voices] sub-table
    vip = cfg.get("tts", {}).get("vip_voices", {})
    if vip:
        lines.append("[tts.vip_voices]")
        for nick, voice in vip.items():
            lines.append(f'{toml_escape(nick)} = "{toml_escape(voice)}"')
        lines.append("")

    return "\n".join(lines)


def get_sounds_catalog(src_dir: Path) -> dict:
    sounds_dir = src_dir / "sounds"
    audio_exts = {".wav", ".mp3", ".ogg", ".flac"}
    available_files = []
    if sounds_dir.exists():
        available_files = sorted([f.name for f in sounds_dir.iterdir() if f.suffix.lower() in audio_exts])

    mapping = {
        "donate": "donate.wav",
        "sub": "sub.wav",
        "resub": "sub.wav",
        "gift": "sub.wav",
        "raid": "raid.wav",
        "cheer": "cheer.wav",
        "follow": "follow.wav",
        "default": "default.wav",
    }
    master_volume = 0.7
    sounds_json_path = sounds_dir / "sounds.json"
    if sounds_json_path.exists():
        try:
            raw = json.loads(sounds_json_path.read_text("utf-8"))
            if "masterVolume" in raw:
                master_volume = float(raw["masterVolume"])
            for k, v in raw.get("sounds", {}).items():
                f = v.get("file", "")
                if "/" in f:
                    f = f.split("/")[-1]
                mapping[k] = f
        except Exception:
            pass

    return {
        "available_files": available_files,
        "mapping": mapping,
        "masterVolume": master_volume,
    }


def save_sounds_catalog(src_dir: Path, mapping: dict, master_volume: float = 0.7) -> dict:
    sounds_dir = src_dir / "sounds"
    sounds_json_path = sounds_dir / "sounds.json"
    data = {
        "masterVolume": max(0.0, min(1.0, float(master_volume))),
        "sounds": {
            k: {"file": f"../sounds/{fname}", "volume": 0.8}
            for k, fname in mapping.items()
        }
    }
    sounds_json_path.write_text(json.dumps(data, indent=2, ensure_ascii=False), "utf-8")
    return data

def build_app(broadcaster: Broadcaster, config: dict, enable_settings: bool = False) -> web.Application:
    project_root = Path(__file__).parent.parent
    src_dir = project_root / "src"

    # Pre-cache current sounds so connecting overlays receive them instantly
    sounds_json_path = src_dir / "sounds" / "sounds.json"
    if sounds_json_path.exists():
        try:
            raw_sounds = json.loads(sounds_json_path.read_text("utf-8"))
            broadcaster.last_sounds_config = {
                "type": "sounds_update",
                "sounds": raw_sounds.get("sounds", {}),
                "masterVolume": raw_sounds.get("masterVolume", 0.7)
            }
        except Exception:
            pass

    # Pre-cache donation goal
    goal_cfg = dict(config.get("goal", {}))
    default_config_path = project_root / "bridge" / "config.toml"
    broadcaster.init_goal(goal_cfg, broadcaster.config_path or default_config_path)

    # Initialize TTS
    tts_cfg = dict(config.get("tts", {}))
    broadcaster.init_tts(tts_cfg)

    adapter_states = {
        name: bool(config.get(name, {}).get("enabled"))
        for name in ("twitch", "twitch_chat", "donationalerts", "donatex")
    }

    async def events(request):
        return await broadcaster.attach(request)

    async def notify(request):
        try:
            payload = await request.json()
        except Exception:
            return web.json_response({"error": "invalid json"}, status=400)
        if not isinstance(payload, dict):
            return web.json_response({"error": "object expected"}, status=400)

        # Handle media skip directly if requested
        if payload.get("type") == "media_control" and payload.get("action") == "skip":
            from adapters import donatex
            await donatex.skip_track()
        elif payload.get("type") == "alert_skip":
            from adapters import donatex, donationalerts
            await donatex.skip_donation()
            await donationalerts.skip_donation()
        elif payload.get("type") == "tts_stop":
            await broadcaster.stop_tts()
            return web.json_response({"ok": True})
        elif payload.get("type") == "tts_test":
            broadcaster.enqueue_tts(
                username=payload.get("user", "Tester"),
                text=payload.get("text", "Проверка синтеза речи."),
                force=True,
                force_voice=payload.get("voice"),
                force_speed=payload.get("speed"),
                force_emotion=payload.get("emotion"),
            )
            return web.json_response({"ok": True})

        await broadcaster.broadcast(payload)
        return web.json_response({"ok": True})

    async def health(request):
        return web.json_response({
            "status": "running",
            "overlays": len(broadcaster.clients),
            "adapters": adapter_states,
            "settings_enabled": enable_settings,
            "stream_stats": broadcaster.last_stream_stats,
        })

    async def root_redirect(request):
        return web.HTTPFound("/dock")

    async def settings_redirect(request):
        return web.HTTPFound("/src/settings/index.html")

    async def get_config_api(request):
        project_root = Path(__file__).parent.parent
        src_dir = project_root / "src"
        sounds_info = get_sounds_catalog(src_dir)

        # Check auth tokens
        has_twitch_token = (project_root / "bridge" / ".twitch_token.json").exists()
        has_da_token = (project_root / "bridge" / ".da_token.json").exists()

        return web.json_response({
            "config": config,
            "sounds": sounds_info,
            "tts_voices": yandex_tts.VOICES,
            "auth": {
                "twitch": has_twitch_token,
                "donationalerts": has_da_token,
            }
        }, headers={"Access-Control-Allow-Origin": "*"})

    async def save_config_api(request):
        project_root = Path(__file__).parent.parent
        src_dir = project_root / "src"
        config_path = project_root / "bridge" / "config.toml"
        backup_path = project_root / "bridge" / "config.toml.bak"

        try:
            payload = await request.json()
        except Exception:
            return web.json_response({"error": "invalid json"}, status=400)

        # 1. Update config dict
        if "server" in payload:
            config.setdefault("server", {}).update(payload["server"])
        if "twitch" in payload:
            config.setdefault("twitch", {}).update(payload["twitch"])
        if "twitch_chat" in payload:
            config.setdefault("twitch_chat", {}).update(payload["twitch_chat"])
        if "donationalerts" in payload:
            config.setdefault("donationalerts", {}).update(payload["donationalerts"])
        if "donatex" in payload:
            config.setdefault("donatex", {}).update(payload["donatex"])
        if "goal" in payload:
            config.setdefault("goal", {}).update(payload["goal"])
            broadcaster.init_goal(config["goal"], config_path)
            if broadcaster.last_goal:
                await broadcaster.broadcast(broadcaster.last_goal)
        if "tts" in payload:
            config.setdefault("tts", {}).update(payload["tts"])
            broadcaster.init_tts(config["tts"])

        # Backup existing config
        if config_path.exists():
            backup_path.write_bytes(config_path.read_bytes())

        # Write clean TOML
        toml_str = serialize_toml(config)
        config_path.write_text(toml_str, encoding="utf-8")

        # 2. Save sound mappings if provided
        if "sounds" in payload and "mapping" in payload["sounds"]:
            master_vol = payload["sounds"].get("masterVolume", 0.7)
            sound_data = save_sounds_catalog(src_dir, payload["sounds"]["mapping"], master_volume=master_vol)
            await broadcaster.broadcast({
                "type": "sounds_update",
                "sounds": sound_data.get("sounds", {}),
                "masterVolume": sound_data.get("masterVolume", master_vol)
            })

        log.info("configuration saved via web settings panel")
        return web.json_response({"ok": True}, headers={"Access-Control-Allow-Origin": "*"})

    async def upload_sound_api(request):
        project_root = Path(__file__).parent.parent
        sounds_dir = project_root / "src" / "sounds"
        reader = await request.multipart()
        field = await reader.next()
        if not field or not field.filename:
            return web.json_response({"error": "no file uploaded"}, status=400)

        raw_filename = field.filename
        ext = Path(raw_filename).suffix.lower()
        if ext not in {".wav", ".mp3", ".ogg", ".flac"}:
            return web.json_response({"error": "unsupported audio format (use .wav, .mp3, .ogg)"}, status=400)

        # Sanitize filename against path traversal
        clean_name = Path(raw_filename).name
        safe_name = re.sub(r"[^a-zA-Z0-9_.-]", "_", clean_name)
        if not safe_name.strip("._"):
            safe_name = f"sound_{int(time.time())}{ext}"
        dest = sounds_dir / safe_name
        size = 0
        exceeded = False
        with open(dest, "wb") as f:
            while True:
                chunk = await field.read_chunk()
                if not chunk:
                    break
                size += len(chunk)
                if size > 15 * 1024 * 1024:  # 15MB limit
                    exceeded = True
                    break
                f.write(chunk)

        if exceeded:
            dest.unlink(missing_ok=True)
            return web.json_response({"error": "file exceeds 15MB limit"}, status=400)

        log.info("uploaded new sound file: %s (%d bytes)", safe_name, size)
        return web.json_response({"ok": True, "filename": safe_name}, headers={"Access-Control-Allow-Origin": "*"})

    async def get_da_auth_url(request):
        da_cfg = config.get("donationalerts", {})
        cid = str(da_cfg.get("client_id", "")).strip()
        redirect_uri = "http://localhost:8787/api/da/callback"
        url = (
            f"https://www.donationalerts.com/oauth/authorize?"
            f"client_id={cid}&redirect_uri={redirect_uri}&response_type=code&"
            f"scope=oauth-user-show%20oauth-donation-subscribe"
        )
        return web.json_response({"url": url}, headers={"Access-Control-Allow-Origin": "*"})

    async def dock_redirect(request):
        return web.HTTPFound("/src/dock/index.html")

    async def resolve_media_api(request):
        url = request.query.get("url", "")
        if not url:
            return web.json_response({"url": ""}, headers={"Access-Control-Allow-Origin": "*"})
        from adapters.twitch_chat import resolve_drisnya_media
        resolved = await resolve_drisnya_media(url)
        return web.json_response({"url": resolved}, headers={"Access-Control-Allow-Origin": "*"})

    tc_cfg = config.get("twitch_chat", {})
    tv_source = str(tc_cfg.get("seven_tv_source", "direct")).strip().lower()
    tv_mirror = str(tc_cfg.get("seven_tv_mirror", "https://enhanced.jeetbot.cc")).strip().rstrip("/")

    async def get_7tv_config(request):
        cdn = "https://cdn.7tv.app/emote" if tv_source != "mirror" else f"{tv_mirror}/https://cdn.7tv.app/emote"
        return web.json_response({
            "source": tv_source,
            "cdnBase": cdn,
            "mirror": tv_mirror,
        }, headers={"Access-Control-Allow-Origin": "*"})

    async def proxy_7tv_global(request):
        import aiohttp
        direct_url = "https://7tv.io/v3/emote-sets/global"
        mirror_url = f"{tv_mirror}/https://7tv.io/v3/emote-sets/global"

        if tv_source == "mirror":
            urls = [(mirror_url, f"{tv_mirror}/https://cdn.7tv.app/emote")]
        elif tv_source == "direct":
            urls = [(direct_url, "https://cdn.7tv.app/emote")]
        else:  # auto
            urls = [
                (direct_url, "https://cdn.7tv.app/emote"),
                (mirror_url, f"{tv_mirror}/https://cdn.7tv.app/emote"),
            ]

        for u, cdn in urls:
            try:
                async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=3.5)) as s:
                    async with s.get(u) as resp:
                        if resp.status == 200:
                            data = await resp.read()
                            return web.Response(
                                body=data,
                                content_type="application/json",
                                headers={
                                    "Access-Control-Allow-Origin": "*",
                                    "X-7TV-CDN-Base": cdn,
                                }
                            )
            except Exception:
                pass
        return web.json_response({"emotes": []}, headers={"Access-Control-Allow-Origin": "*"})

    async def proxy_7tv_channel(request):
        import aiohttp
        room_id = request.match_info["room_id"]
        direct_url = f"https://7tv.io/v3/users/twitch/{room_id}"
        mirror_url = f"{tv_mirror}/https://7tv.io/v3/users/twitch/{room_id}"

        if tv_source == "mirror":
            urls = [(mirror_url, f"{tv_mirror}/https://cdn.7tv.app/emote")]
        elif tv_source == "direct":
            urls = [(direct_url, "https://cdn.7tv.app/emote")]
        else:  # auto
            urls = [
                (direct_url, "https://cdn.7tv.app/emote"),
                (mirror_url, f"{tv_mirror}/https://cdn.7tv.app/emote"),
            ]

        for u, cdn in urls:
            try:
                async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=3.5)) as s:
                    async with s.get(u) as resp:
                        if resp.status == 200:
                            data = await resp.read()
                            return web.Response(
                                body=data,
                                content_type="application/json",
                                headers={
                                    "Access-Control-Allow-Origin": "*",
                                    "X-7TV-CDN-Base": cdn,
                                }
                            )
            except Exception:
                pass
        return web.json_response({}, headers={"Access-Control-Allow-Origin": "*"})

    async def media_skip_api(request):
        from adapters import donatex
        skipped = await donatex.skip_track()
        await broadcaster.broadcast({"type": "media_control", "action": "skip"})
        return web.json_response({"ok": True, "donatex_skipped": skipped}, headers={"Access-Control-Allow-Origin": "*"})

    async def donation_skip_api(request):
        from adapters import donatex, donationalerts
        await donatex.skip_donation()
        await donationalerts.skip_donation()
        await broadcaster.broadcast({"type": "alert_skip"})
        return web.json_response({"ok": True}, headers={"Access-Control-Allow-Origin": "*"})

    async def tts_stop_api(request):
        await broadcaster.stop_tts()
        return web.json_response({"ok": True}, headers={"Access-Control-Allow-Origin": "*"})

    async def da_callback(request):
        code = request.query.get("code")
        if not code:
            error = request.query.get("error_description") or request.query.get("error") or "Код авторизации не найден"
            log.error("DonationAlerts OAuth error: %s", error)
            safe_error = html_mod.escape(str(error))
            return web.Response(
                text=f"<h1>[ SYSTEM ]</h1><p style='font-family: monospace;'>Ошибка от DonationAlerts: {safe_error}</p>",
                content_type="text/html",
                status=400
            )

        da_cfg = config.get("donationalerts", {})
        client_id = str(da_cfg.get("client_id", "")).strip()
        client_secret = str(da_cfg.get("client_secret", "")).strip()
        if not client_secret:
            raw_token = str(da_cfg.get("access_token", "")).strip()
            if len(raw_token) == 40 and not raw_token.startswith("eyJ"):
                client_secret = raw_token

        if not client_id or not client_secret:
            log.error("DonationAlerts missing client_id or client_secret")
            return web.Response(
                text="<h1>[ SYSTEM ]</h1><p style='font-family: monospace;'>Ошибка: укажите client_id и client_secret в bridge/config.toml</p>",
                content_type="text/html",
                status=400
            )

        from adapters.donationalerts import exchange_da_code
        try:
            redirect_uri = "http://localhost:8787/api/da/callback"
            await exchange_da_code(client_id, client_secret, redirect_uri, code)
            return web.Response(
                text=(
                    "<!DOCTYPE html><html><head><meta charset='utf-8'><title>SYSTEM // DA OK</title></head>"
                    "<body style='background:#0B0F14;color:#63E6BE;font-family:monospace;padding:40px;text-align:center;'>"
                    "<h1>[ SYSTEM // DONATIONALERTS CONNECTED ]</h1>"
                    "<p style='color:#E8EEF2;'>DonationAlerts успешно авторизован! Окно можно закрыть, мост уже подключился.</p>"
                    "</body></html>"
                ),
                content_type="text/html"
            )
        except Exception as e:
            log.error("DonationAlerts auth callback error: %s", e)
            safe_err = html_mod.escape(str(e))
            return web.Response(
                text=(
                    f"<!DOCTYPE html><html><head><meta charset='utf-8'><title>SYSTEM // DA ERROR</title></head>"
                    f"<body style='background:#0B0F14;color:#E5484D;font-family:monospace;padding:40px;'>"
                    f"<h1>[ Ошибка авторизации DonationAlerts ]</h1>"
                    f"<p style='color:#E8EEF2;'>{safe_err}</p>"
                    f"</body></html>"
                ),
                content_type="text/html",
                status=500
            )

    async def get_twitch_badges(request):
        from adapters.twitch_chat import get_cached_badges
        badges = get_cached_badges()
        return web.json_response(badges, headers={"Access-Control-Allow-Origin": "*"})

    # Endpoints that require API key authentication (state-changing)
    PROTECTED_PATHS = {"/notify", "/api/config", "/api/sounds/upload",
                       "/api/media/skip", "/api/donations/skip", "/api/tts/stop"}

    @web.middleware
    async def auth_middleware(request, handler):
        if request.method == "POST" and request.path in PROTECTED_PATHS:
            # Allow requests from same-origin pages (Referer check) or with valid API key
            referer = request.headers.get("Referer", "")
            host_header = request.headers.get("Host", "")
            from urllib.parse import urlparse
            ref_parsed = urlparse(referer)
            ref_host = f"{ref_parsed.hostname}:{ref_parsed.port}" if ref_parsed.port else (ref_parsed.hostname or "")
            is_same_origin = ref_host == host_header or ref_parsed.hostname in ("localhost", "127.0.0.1")

            auth_header = request.headers.get("Authorization", "")
            has_valid_key = auth_header == f"Bearer {API_KEY}" if API_KEY else False

            if not is_same_origin and not has_valid_key:
                log.warning("Unauthorized POST to %s from referer %s", request.path, referer)
                return web.json_response({"error": "unauthorized"}, status=401)
        return await handler(request)

    @web.middleware
    async def no_cache_middleware(request, handler):
        response = await handler(request)
        response.headers["Cache-Control"] = "no-cache, no-store, must-revalidate"
        response.headers["Pragma"] = "no-cache"
        response.headers["Expires"] = "0"
        return response

    app = web.Application(middlewares=[auth_middleware, no_cache_middleware])
    app.router.add_get("/", root_redirect)
    app.router.add_get("/dock", dock_redirect)
    if enable_settings:
        app.router.add_get("/settings", settings_redirect)
        app.router.add_get("/api/config", get_config_api)
        app.router.add_post("/api/config", save_config_api)
        app.router.add_post("/api/sounds/upload", upload_sound_api)
        app.router.add_get("/api/da/auth-url", get_da_auth_url)
    app.router.add_get("/events", events)
    app.router.add_post("/notify", notify)
    app.router.add_get("/health", health)
    app.router.add_get("/api/resolve-media", resolve_media_api)
    app.router.add_get("/api/7tv/config", get_7tv_config)
    app.router.add_get("/api/7tv/global", proxy_7tv_global)
    app.router.add_get("/api/7tv/channel/{room_id}", proxy_7tv_channel)
    app.router.add_post("/api/media/skip", media_skip_api)
    app.router.add_post("/api/donations/skip", donation_skip_api)
    app.router.add_post("/api/tts/stop", tts_stop_api)
    app.router.add_get("/api/twitch/badges", get_twitch_badges)
    app.router.add_get("/api/da/callback", da_callback)

    if src_dir.exists():
        app.router.add_static("/src", path=str(src_dir))

    return app


def spawn_adapters(config: dict, broadcast) -> list:
    tasks = []
    tc_cfg = dict(config.get("twitch_chat", {}))
    tw_cfg = config.get("twitch", {})
    if tw_cfg.get("client_id") and not tc_cfg.get("client_id"):
        tc_cfg["client_id"] = tw_cfg["client_id"]
        tc_cfg["client_secret"] = tw_cfg.get("client_secret", "")

    sections = {
        "twitch": ("adapters.twitch", config.get("twitch", {})),
        "twitch_chat": ("adapters.twitch_chat", tc_cfg),
        "donationalerts": ("adapters.donationalerts", config.get("donationalerts", {})),
        "donatex": ("adapters.donatex", config.get("donatex", {})),
    }
    for name, (module_path, section) in sections.items():
        if not section.get("enabled"):
            continue
        log.info("starting adapter: %s", name)
        module = __import__(module_path, fromlist=["run"])
        tasks.append(asyncio.create_task(watch(name, module.run(section, broadcast))))
    return tasks


async def watch(name: str, coro) -> None:
    try:
        await coro
    except asyncio.CancelledError:
        pass
    except Exception:
        log.exception("adapter %s crashed", name)


async def main() -> None:
    parser = argparse.ArgumentParser(description="SYSTEM alerts bridge")
    parser.add_argument("--config", default=str(Path(__file__).parent / "config.toml"))
    parser.add_argument("--settings", action="store_true", help="Enable web settings panel and configuration API")
    args = parser.parse_args()

    config_path = Path(args.config)
    if not config_path.exists():
        log.error("config not found: %s (copy config.example.toml)", config_path)
        sys.exit(1)
    with open(config_path, "rb") as handle:
        config = toml_load(handle)

    server_cfg = config.get("server", {})
    host = server_cfg.get("host", "127.0.0.1")
    port = int(server_cfg.get("port", 8787))

    log.info("initializing bridge on http://%s:%d...", host, port)

    # Generate session API key for protecting state-changing endpoints
    global API_KEY
    API_KEY = secrets.token_urlsafe(24)

    broadcaster = Broadcaster()
    tasks = spawn_adapters(config, broadcaster.broadcast)

    app = build_app(broadcaster, config, enable_settings=args.settings)
    if args.settings:
        log.info("SETTINGS MODE ACTIVE: web dashboard at http://%s:%d/settings", host, port)
    else:
        log.info("STREAM MODE ACTIVE: lightweight broadcast server (use --settings to configure)")
    runner = web.AppRunner(app)
    await runner.setup()
    site = web.TCPSite(runner, host, port)
    await site.start()
    log.info("unified server ready at ws://%s:%d/events", host, port)
    if host != "127.0.0.1":
        log.info("API key for external access: %s", API_KEY)

    stop_event = asyncio.Event()
    loop = asyncio.get_event_loop()
    import signal
    for sig in (signal.SIGINT, signal.SIGTERM):
        try:
            loop.add_signal_handler(sig, stop_event.set)
        except NotImplementedError:
            pass  # Windows doesn't support add_signal_handler

    try:
        await stop_event.wait()
    except (asyncio.CancelledError, KeyboardInterrupt):
        pass
    finally:
        log.info("shutting down...")
        for t in tasks:
            t.cancel()
        if tasks:
            try:
                await asyncio.wait_for(asyncio.gather(*tasks, return_exceptions=True), timeout=2.0)
            except asyncio.TimeoutError:
                log.warning("some adapters timed out during shutdown")
        # Cancel any pending broadcaster background tasks (TTS worker, delay clears, etc.)
        for t in list(broadcaster._background_tasks):
            t.cancel()
        if broadcaster._background_tasks:
            try:
                await asyncio.wait_for(asyncio.gather(*broadcaster._background_tasks, return_exceptions=True), timeout=1.0)
            except asyncio.TimeoutError:
                pass
        # Close all WebSocket connections cleanly
        for ws in list(broadcaster.clients):
            try:
                await ws.close()
            except Exception:
                pass
        try:
            await asyncio.wait_for(runner.cleanup(), timeout=2.0)
        except Exception:
            pass
        log.info("shutdown complete")


if __name__ == "__main__":
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] [%(name)s] %(message)s",
        datefmt="%H:%M:%S"
    )
    # Silence repetitive HTTP polling access logs (such as GET /health every 3s)
    logging.getLogger("aiohttp.access").setLevel(logging.WARNING)

    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        pass
    finally:
        import os
        os._exit(0)