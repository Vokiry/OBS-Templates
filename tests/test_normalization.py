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
    ]
    for p in passthroughs:
        assert normalize(p) == p


def test_encode_roundtrip():
    data = {"type": "chat", "user": "Тестер", "text": "Привет, мир! 🚀"}
    encoded = encode(data)
    assert isinstance(encoded, str)
    decoded = json.loads(encoded)
    assert decoded == data
