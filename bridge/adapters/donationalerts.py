import asyncio
import json
import logging

import aiohttp
import websockets

log = logging.getLogger("bridge.donationalerts")

WS_URL = "wss://centrifugo.donationalerts.com/connection/websocket"
SUBSCRIBE_API = "https://www.donationalerts.com/api/v1/centrifuge/subscribe"
CHANNEL = "$alerts:donation"

METHOD_PUBLISH = 5
TYPE_REPLY = 0
TYPE_PUSH = 1


def normalize_donation(data: dict) -> dict:
    username = data.get("username") or data.get("name") or "anonymous"
    amount = data.get("amount")
    currency = data.get("currency", "")
    message = (data.get("message") or "").strip()
    amount_str = f"{amount} {currency}".strip()
    body = f"{username} · {amount_str}".strip(" ·")
    return {
        "kind": "donate",
        "user": username,
        "amount": amount_str,
        "message": message,
        "body": body,
    }


class DonationAlertsAdapter:
    def __init__(self, token: str, broadcast):
        self.token = token
        self.broadcast = broadcast

    async def run(self) -> None:
        async with websockets.connect(WS_URL) as ws:
            await ws.send(json.dumps({
                "method": 1,
                "params": {"token": self.token, "name": "obs-system-bridge"},
            }))
            client = None
            while client is None:
                reply = json.loads(await ws.recv())
                data = reply.get("data")
                if isinstance(data, dict) and "client" in data:
                    client = data["client"]

            log.info("donationalerts connected (client %s)", client)
            await self._subscribe_channels(ws, client)

            async for raw in ws:
                await self._handle(json.loads(raw))

    async def _subscribe_channels(self, ws, client: str) -> None:
        async with aiohttp.ClientSession() as session:
            async with session.post(
                SUBSCRIBE_API,
                headers={"Authorization": f"Bearer {self.token}"},
                json={"client": client, "channels": [CHANNEL]},
            ) as response:
                response.raise_for_status()
                payload = await response.json()
        for channel in payload.get("channels", []):
            await ws.send(json.dumps({
                "method": METHOD_PUBLISH,
                "params": {
                    "channel": channel["channel"],
                    "token": channel["token"],
                    "sign": channel["sign"],
                },
            }))
            log.info("subscribed to %s", channel["channel"])

    async def _handle(self, message: dict) -> None:
        if message.get("method") != METHOD_PUBLISH or message.get("type") != TYPE_PUSH + 0:
            return
        push = message.get("push") or {}
        if push.get("channel") != CHANNEL:
            return
        donation = (push.get("data") or {}).get("data") or {}
        if isinstance(donation, str):
            try:
                donation = json.loads(donation)
            except Exception:
                pass
        if not donation or not isinstance(donation, dict):
            return
        await self.broadcast(normalize_donation(donation))


async def run(config: dict, broadcast) -> None:
    adapter = DonationAlertsAdapter(config["access_token"], broadcast)
    while True:
        try:
            await adapter.run()
        except Exception as exc:
            log.warning("connection lost (%s), retrying in 5s", exc)
        await asyncio.sleep(5)
