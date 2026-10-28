import json
import pytest
from pathlib import Path
from aiohttp import web
from bridge.alerts_bridge import Broadcaster, build_app, parse_amount
from bridge.adapters.base import normalize


def test_parse_amount_various_formats():
    assert parse_amount("500 ₽") == 500.0
    assert parse_amount("1 500,50 RUB") == 1500.5
    assert parse_amount("25.00 $") == 25.0
    assert parse_amount("10 000") == 10000.0
    assert parse_amount(250) == 250.0
    assert parse_amount(149.99) == 149.99
    assert parse_amount(None) == 0.0
    assert parse_amount("") == 0.0


def test_normalize_goal_update():
    payload = {
        "type": "goal_update",
        "enabled": True,
        "title": "Новый микрофон",
        "current": 5000.0,
        "target": 20000.0,
        "currency": "RUB",
        "percent": 25.0
    }
    assert normalize(payload) == payload


@pytest.mark.asyncio
async def test_goal_auto_increment_on_donate(tmp_path, aiohttp_client):
    cfg_file = tmp_path / "config.toml"
    cfg_file.write_text("""[goal]
enabled = true
title = "Тестовый сбор"
current = 1000.0
target = 10000.0
currency = "RUB"
""", encoding="utf-8")

    b = Broadcaster()
    goal_cfg = {
        "enabled": True,
        "title": "Тестовый сбор",
        "current": 1000.0,
        "target": 10000.0,
        "currency": "RUB"
    }
    b.init_goal(goal_cfg, cfg_file)
    assert b.last_goal["current"] == 1000.0
    assert b.last_goal["percent"] == 10.0

    app = build_app(b, {"goal": goal_cfg, "server": {"host": "127.0.0.1", "port": 8787}}, enable_settings=True)
    client = await aiohttp_client(app)

    async with client.ws_connect("/events") as ws:
        # Initial connect receives cached goal
        received_goal = False
        for _ in range(4):
            raw = await ws.receive_str()
            data = json.loads(raw)
            if data.get("type") == "goal_update":
                received_goal = True
                assert data["current"] == 1000.0
                assert data["percent"] == 10.0
                break
        assert received_goal, "Expected initial goal_update on connect"

        # Fire a donation alert through broadcast
        donate_alert = {
            "type": "alert",
            "kind": "donate",
            "user": "Dave",
            "amount": "1 500 ₽",
            "message": "Удачи со сбором!"
        }
        await b.broadcast(donate_alert)

        # Overlay receives updated goal event
        while True:
            raw = await ws.receive_str()
            data = json.loads(raw)
            if data.get("type") == "goal_update":
                assert data["current"] == 2500.0
                assert data["percent"] == 25.0
                break

    # Check persistence in config.toml
    saved_text = cfg_file.read_text("utf-8")
    assert "2500.0" in saved_text
