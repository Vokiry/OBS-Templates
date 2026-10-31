import json
import pytest
from bridge.adapters.base import normalize, encode


def test_normalize_alert_donate():
    payload = {
        "kind": "donate",
        "user": "Alice",
        "amount": "500 ₽",
        "message": "gl hf!"
    }
    norm = normalize(payload)
    assert norm["type"] == "alert"
    assert norm["kind"] == "donate"
    assert norm["title"] == "DONATION"
    assert norm["user"] == "Alice"
    assert norm["amount"] == "500 ₽"
    assert norm["message"] == "gl hf!"


def test_normalize_alert_sub_kinds():
    for kind, expected_title in [
        ("sub", "NEW SUB"),
        ("resub", "RESUB"),
        ("gift", "GIFT SUB"),
        ("raid", "RAID"),
        ("cheer", "CHEER"),
        ("follow", "NEW FOLLOWER"),
    ]:
        norm = normalize({"kind": kind, "user": "Bob"})
        assert norm["type"] == "alert"
        assert norm["kind"] == kind
        assert norm["title"] == expected_title
        assert norm["body"] == "Bob"


def test_normalize_passthrough_types():
    passthroughs = [
        {"type": "chat", "user": "User", "text": "Hi"},
        {"type": "chat_history", "messages": []},
        {"type": "sounds_update", "sounds": {}},
        {"type": "poll", "action": "begin"},
        {"type": "prediction", "action": "begin"},
        {"type": "7tv_emotes", "emotes": {}},
        {"type": "twitch_badges", "badges": {}},
        {"type": "chat_clear"},
        {"type": "tts_speak", "audio_b64": "AAA", "nickname": "voki", "text": "test", "show_card": True, "volume": 0.8},
        {"type": "tts_stop"},
        {"type": "goal_update", "enabled": True, "title": "Goal", "current": 100.0, "target": 500.0},
        {"type": "stream_stats", "live": True, "viewers": 10, "chatters": 8},
        {"type": "media_request", "user": "Fan", "youtubeId": "xyz123"},
        {"type": "media_control", "action": "skip"},
        {"type": "alert_skip"},
    ]
    for p in passthroughs:
        assert normalize(p) == p


def test_normalize_alert_custom_fields():
    # Rich alert with DonateX / DA voice URLs and AI responses
    payload = {
        "kind": "donate",
        "user": "GenerousDonor",
        "amount": "1000 ₽",
        "message": "Привет от донатера!",
        "voiceUrl": "https://cdn.donatex.gg/voice/123.mp3",
        "aiVoiceUrl": "https://cdn.donatex.gg/ai/456.mp3",
        "aiResponse": "Спасибо за донат, чемпион!"
    }
    norm = normalize(payload)
    assert norm["type"] == "alert"
    assert norm["voiceUrl"] == "https://cdn.donatex.gg/voice/123.mp3"
    assert norm["aiVoiceUrl"] == "https://cdn.donatex.gg/ai/456.mp3"
    assert norm["aiResponse"] == "Спасибо за донат, чемпион!"


def test_normalize_without_kind_defaults_to_donate():
    payload = {"user": "Anonymous", "message": "Just a message"}
    norm = normalize(payload)
    assert norm["type"] == "alert"
    assert norm["kind"] == "donate"
    assert norm["title"] == "DONATION"
    assert norm["user"] == "Anonymous"


def test_encode_roundtrip():
    data = {"type": "chat", "user": "Тестер", "text": "Привет, мир! 🚀"}
    encoded = encode(data)
    assert isinstance(encoded, str)
    decoded = json.loads(encoded)
    assert decoded == data
