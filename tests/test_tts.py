import asyncio
import json
import pytest
from aiohttp import web
from bridge.alerts_bridge import Broadcaster, serialize_toml
from bridge.services import yandex_tts


def test_preprocess_text():
    # Commands are filtered out
    assert yandex_tts.preprocess_text("!song") == ""
    assert yandex_tts.preprocess_text("/me hello") == ""
    assert yandex_tts.preprocess_text(".bot command") == ""

    # URLs replaced with word "ссылка"
    assert yandex_tts.preprocess_text("check this https://youtube.com/watch?v=123 out") == "check this ссылка out"

    # Character spam collapsed
    assert yandex_tts.preprocess_text("привееееееет") == "привеет"
    assert yandex_tts.preprocess_text("ааааааааааа") == "аа"

    # Word spam collapsed
    assert yandex_tts.preprocess_text("KEKW KEKW KEKW KEKW") == "KEKW"
    assert yandex_tts.preprocess_text("да да да стример") == "да стример"

    # Max length truncation
    long_text = "слово раз два три четыре пять шесть семь восемь девять десять одиннадцать двенадцать тринадцать"
    cleaned = yandex_tts.preprocess_text(long_text, max_length=40)
    assert len(cleaned) <= 45  # plus ellipsis
    assert cleaned.endswith("…")


def test_is_bot():
    assert yandex_tts.is_bot("Nightbot") is True
    assert yandex_tts.is_bot("streamelements") is True
    assert yandex_tts.is_bot("moobot") is True
    assert yandex_tts.is_bot("regular_viewer") is False
    assert yandex_tts.is_bot("vokiry") is False


def test_pick_voice_deterministic():
    pool = ["ermil", "zahar", "krosh", "robot"]

    # Same user always gets identical voice
    v1 = yandex_tts.pick_voice("pavel", pool)
    v2 = yandex_tts.pick_voice("pavel", pool)
    v3 = yandex_tts.pick_voice("PAVEL", pool)  # case-insensitive
    assert v1 == v2 == v3
    assert v1 in pool

    # Different users distribute across pool
    voices = {yandex_tts.pick_voice(f"user_{i}", pool) for i in range(20)}
    assert len(voices) > 1  # multiple voices distributed


def test_vip_voice_lookup():
    b = Broadcaster()
    b.init_tts({
        "mode": "all",
        "voice": "shitova.us",
        "random_pool": ["ermil", "zahar"],
        "vip_voices": {
            "best_friend": "krosh",
            "moderator": "robot"
        }
    })

    # VIP voices take strict precedence
    assert b._tts_voice_for_user("best_friend") == "krosh"
    assert b._tts_voice_for_user("BEST_FRIEND") == "krosh"
    assert b._tts_voice_for_user("moderator") == "robot"

    # Normal users get voice from random pool
    assert b._tts_voice_for_user("random_viewer") in ["ermil", "zahar"]


@pytest.mark.asyncio
async def test_broadcaster_tts_modes():
    b = Broadcaster()

    # 1. Mode: "off" -> nothing enqueued
    b.init_tts({"mode": "off"})
    b.enqueue_tts("viewer", "hello stream")
    assert len(b._tts_queue) == 0

    # 2. Mode: "rewards" -> standard message ignored
    b.init_tts({"mode": "rewards", "reward_name": "TTS"})
    b.enqueue_tts("viewer", "hello stream", is_reward=False)
    assert len(b._tts_queue) == 0

    # 3. Mode: "rewards" -> reward message enqueued
    b.enqueue_tts("viewer", "read this via reward", is_reward=True)
    assert len(b._tts_queue) == 1
    assert b._tts_queue[0]["show_card"] is True
    assert b._tts_queue[0]["text"] == "read this via reward"
    b._tts_queue.clear()

    # 4. Mode: "all" -> all messages enqueued, show_card is False
    b.init_tts({"mode": "all"})
    b.enqueue_tts("viewer", "hello everyone", is_reward=False)
    assert len(b._tts_queue) == 1
    assert b._tts_queue[0]["show_card"] is False
    assert b._tts_queue[0]["text"] == "hello everyone"
    b._tts_queue.clear()


@pytest.mark.asyncio
async def test_stop_tts():
    b = Broadcaster()
    b.init_tts({"mode": "all"})
    b._tts_queue.append({"username": "u1", "text": "t1", "voice": "ermil", "show_card": False})
    b._tts_queue.append({"username": "u2", "text": "t2", "voice": "zahar", "show_card": False})
    assert len(b._tts_queue) == 2

    # Stop TTS should empty queue
    await b.stop_tts()
    assert len(b._tts_queue) == 0


def test_serialize_toml_tts():
    cfg = {
        "server": {"host": "127.0.0.1", "port": 8787},
        "tts": {
            "mode": "rewards",
            "voice": "shitova.us",
            "speed": "1.1",
            "emotion": "good",
            "max_length": 180,
            "reward_name": "TTS Речь",
            "auth_token": "custom-token-123",
            "random_pool": ["krosh", "robot"],
            "vip_voices": {
                "admin": "robot",
                "friend": "krosh"
            }
        }
    }
    toml_str = serialize_toml(cfg)

    assert '[tts]' in toml_str
    assert 'mode = "rewards"' in toml_str
    assert 'speed = "1.1"' in toml_str
    assert 'emotion = "good"' in toml_str
    assert 'max_length = 180' in toml_str
    assert 'reward_name = "TTS Речь"' in toml_str
    assert 'auth_token = "custom-token-123"' in toml_str
    assert 'random_pool = ["krosh", "robot"]' in toml_str
    assert '[tts.vip_voices]' in toml_str
    assert 'admin = "robot"' in toml_str
    assert 'friend = "krosh"' in toml_str


@pytest.mark.asyncio
async def test_tts_stop_api(aiohttp_client):
    from bridge.alerts_bridge import build_app
    b = Broadcaster()
    b.init_tts({"mode": "all"})
    b._tts_queue.append({"username": "u1", "text": "t1", "voice": "ermil", "show_card": False})

    app = build_app(b, {"tts": {"mode": "all"}}, enable_settings=True)
    client = await aiohttp_client(app)

    headers = {"Referer": "http://127.0.0.1:8787/dock"}
    res = await client.post("/api/tts/stop", headers=headers)
    assert res.status == 200
    assert len(b._tts_queue) == 0


@pytest.mark.asyncio
async def test_tts_notify_test_trigger(aiohttp_client):
    from unittest.mock import patch, AsyncMock
    from bridge.alerts_bridge import build_app
    b = Broadcaster()
    b.init_tts({"mode": "off"})  # Even if off, tts_test forces enqueuing

    app = build_app(b, {"tts": {"mode": "off"}}, enable_settings=True)
    client = await aiohttp_client(app)

    headers = {"Referer": "http://127.0.0.1:8787/settings"}
    with patch("bridge.alerts_bridge.yandex_tts.generate", new_callable=AsyncMock) as mock_gen:
        mock_gen.return_value = b"OggOpusFakeAudioData"
        res = await client.post("/notify", json={
            "type": "tts_test",
            "user": "Tester",
            "text": "Тестовое сообщение",
            "voice": "krosh"
        }, headers=headers)
        assert res.status == 200

        # Allow background worker to execute
        await asyncio.sleep(0.05)
        mock_gen.assert_awaited_once()
        assert mock_gen.call_args.kwargs["voice"] == "krosh"
        assert mock_gen.call_args.kwargs["text"] == "Тестовое сообщение"
