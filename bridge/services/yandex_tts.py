"""Yandex Alice TTS service via Uniproxy WebSocket.

Generates high-quality Ogg Opus audio from text using the internal
Yandex Browser SpeechKit endpoint. Zero external dependencies beyond
aiohttp (already in the project).
"""

import json
import logging
import re
import uuid
import zlib
from typing import Optional

import aiohttp

log = logging.getLogger("tts")

# ---------------------------------------------------------------------------
# Protocol constants (Yandex Browser desktop integration)
# ---------------------------------------------------------------------------
DEFAULT_WS_ENDPOINT = "wss://uniproxy.alice.yandex.net/uni.ws"
DEFAULT_AUTH_TOKEN = "14e2f152-e03a-439d-9abe-f470c27db24e"

WS_HEADERS_TEMPLATE = {
    "User-Agent": "WebSocket++/0.8.2",
    "X-UPRX-APP-ID": "YaBro",
    "X-UPRX-APP-VERSION": "Windows",
    "X-UPRX-OS-VERSION": "10.0.22631",
    "X-UPRX-PLATFORM": "Windows",
    "X-UPRX-SPEECHKIT-VERSION": "4.15.0",
}

# ---------------------------------------------------------------------------
# Available voices (verified working on Uniproxy)
# ---------------------------------------------------------------------------
VOICES = {
    # Female
    "shitova.us": "Алиса (Татьяна Шитова)",
    "jane": "Джейн",
    "oksana": "Оксана",
    "alyss": "Алисса",
    "omazh": "Омаж",
    # Male
    "ermil": "Ермил",
    "zahar": "Захар",
    "kolya": "Коля",
    "kostya": "Костя",
    "valtz": "Вальц",
    "sasha": "Саша",
    # Special / fun
    "krosh": "Крош (Смешарики)",
    "robot": "Робот",
}

DEFAULT_RANDOM_POOL = [
    "ermil", "zahar", "jane", "alyss", "omazh", "oksana",
    "kolya", "valtz", "kostya", "sasha", "krosh", "robot",
]

FALLBACK_VOICE = "shitova.us"

# ---------------------------------------------------------------------------
# Text preprocessing for safe and clean TTS output
# ---------------------------------------------------------------------------
_RE_URL = re.compile(r"https?://\S+", re.IGNORECASE)
_RE_CHAR_SPAM = re.compile(r"(.)\1{4,}")          # ааааааа → аа
_RE_WORD_SPAM = re.compile(r"\b(\S+)(?:\s+\1){2,}\b", re.IGNORECASE)  # kek kek kek → kek
_RE_COMMAND = re.compile(r"^[!/.]")                # !command, /me, .бот

BOT_NAMES = frozenset({
    "nightbot", "streamelements", "moobot", "fossabot", "streamlabs",
    "wizebot", "botrix", "soundalerts", "pretzelrocks", "sery_bot",
})


def preprocess_text(text: str, max_length: int = 200) -> str:
    """Clean chat message text for TTS synthesis."""
    if not text:
        return ""
    # Skip bot commands
    if _RE_COMMAND.match(text.strip()):
        return ""
    # Remove URLs
    text = _RE_URL.sub("ссылка", text)
    # Collapse character spam (ааааааааа → аа)
    text = _RE_CHAR_SPAM.sub(r"\1\1", text)
    # Collapse word spam (kekw kekw kekw kekw → kekw)
    text = _RE_WORD_SPAM.sub(r"\1", text)
    # Trim whitespace
    text = " ".join(text.split())
    # Enforce length limit
    if len(text) > max_length:
        text = text[:max_length].rsplit(" ", 1)[0] + "…"
    return text.strip()


def is_bot(username: str) -> bool:
    """Check if a username belongs to a known chat bot."""
    return username.lower().strip() in BOT_NAMES


def pick_voice(username: str, pool: list[str] | None = None) -> str:
    """Deterministic voice selection via CRC32 hash of lowercase nick."""
    if not pool:
        pool = DEFAULT_RANDOM_POOL
    if not pool:
        return FALLBACK_VOICE
    idx = zlib.crc32(username.lower().encode("utf-8")) % len(pool)
    return pool[idx]


# ---------------------------------------------------------------------------
# TTS generator
# ---------------------------------------------------------------------------
_DEVICE_UUID = str(uuid.uuid4())


async def generate(
    text: str,
    voice: str = FALLBACK_VOICE,
    speed: str = "1.0",
    emotion: str = "neutral",
    lang: str = "ru-RU",
    endpoint: str = DEFAULT_WS_ENDPOINT,
    auth_token: str = DEFAULT_AUTH_TOKEN,
    timeout_sec: float = 25.0,
) -> Optional[bytes]:
    """Generate Ogg Opus audio from text via Yandex Uniproxy.

    Returns raw Ogg Opus bytes on success, or None on failure.
    """
    session_id = str(uuid.uuid4())
    device_uuid = _DEVICE_UUID

    headers = dict(WS_HEADERS_TEMPLATE)
    headers["X-UPRX-AUTH-TOKEN"] = auth_token
    headers["X-UPRX-SSID"] = session_id
    headers["X-UPRX-UUID"] = device_uuid

    timeout = aiohttp.ClientTimeout(total=timeout_sec, connect=5.0, sock_read=18.0)

    try:
        async with aiohttp.ClientSession(timeout=timeout) as session:
            async with session.ws_connect(endpoint, headers=headers) as ws:
                # 1. SynchronizeState
                sync_event = {
                    "event": {
                        "header": {
                            "messageId": str(uuid.uuid4()),
                            "name": "SynchronizeState",
                            "namespace": "System",
                        },
                        "payload": {
                            "accept_invalid_auth": True,
                            "auth_token": auth_token,
                            "device": " ",
                            "device_manufacturer": "",
                            "device_model": "",
                            "device_revision": "",
                            "emotion": emotion,
                            "network_type": "",
                            "oauth_token": "",
                            "platform_info": "Windows",
                            "speechkit_version": "4.15.0",
                            "speed": str(speed),
                            "uuid": device_uuid,
                            "voice": voice,
                            "yandexuid": "",
                            "vins": {
                                "application": {
                                    "app_id": "YaBro",
                                    "app_version": "Windows",
                                    "device_manufacturer": "",
                                    "device_model": "",
                                    "device_revision": "",
                                    "os_version": "10.0.22631",
                                    "platform": "Windows",
                                    "uuid": device_uuid,
                                }
                            },
                        },
                    }
                }
                await ws.send_str(json.dumps(sync_event))

                # Wait for SynchronizeStateResponse
                async for msg in ws:
                    if msg.type == aiohttp.WSMsgType.TEXT:
                        if "SynchronizeStateResponse" in msg.data:
                            break
                    elif msg.type in (aiohttp.WSMsgType.CLOSED, aiohttp.WSMsgType.ERROR):
                        log.warning("tts: ws closed during sync")
                        return None

                # 2. Generate TTS
                speed_num = 1.0
                try:
                    speed_num = float(speed)
                except (ValueError, TypeError):
                    pass

                # Prepend acoustic lead-in pause to eliminate audio driver buffer ramp-up stutter
                clean_text = text.strip()
                if not clean_text.startswith("..."):
                    clean_text = "... " + clean_text

                gen_event = {
                    "event": {
                        "header": {
                            "messageId": str(uuid.uuid4()),
                            "name": "Generate",
                            "namespace": "TTS",
                        },
                        "payload": {
                            "emotion": emotion,
                            "format": "audio/opus",
                            "lang": lang,
                            "oauth_token": "",
                            "quality": "UltraHigh",
                            "text": clean_text,
                            "voice": voice,
                            "speed": speed_num,
                        },
                    }
                }
                await ws.send_str(json.dumps(gen_event))

                # 3. Collect audio stream
                audio = bytearray()
                async for msg in ws:
                    if msg.type == aiohttp.WSMsgType.BINARY:
                        # First 4 bytes are internal transport header — skip
                        if len(msg.data) > 4:
                            audio.extend(msg.data[4:])
                    elif msg.type == aiohttp.WSMsgType.TEXT:
                        if "streamcontrol" in msg.data:
                            # Confirm speech finished
                            fin_event = {
                                "event": {
                                    "header": {
                                        "messageId": str(uuid.uuid4()),
                                        "name": "SpeechFinished",
                                        "namespace": "TTS",
                                    },
                                    "payload": {},
                                }
                            }
                            await ws.send_str(json.dumps(fin_event))
                            break
                        if "error" in msg.data.lower():
                            log.warning("tts: server error: %s", msg.data[:200])
                            return None

                if audio:
                    return bytes(audio)
                return None

    except asyncio.TimeoutError:
        log.warning("tts: generation timed out for voice=%s len=%d", voice, len(text))
        return None
    except Exception as e:
        log.warning("tts: generation failed: %s", e)
        return None


# Make asyncio importable at module level for timeout handling
import asyncio  # noqa: E402
