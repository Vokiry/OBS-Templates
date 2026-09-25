import asyncio
import json
import logging
import re
import aiohttp
import websockets

log = logging.getLogger("bridge.donatex")

NEGOTIATE_URL = "https://donatex.gg/api/controls-hub/negotiate?negotiateVersion=1"
HUB_URL = "wss://donatex.gg/api/controls-hub"
RECORD_SEP = "\x1e"

YOUTUBE_REGEX = re.compile(
    r'(?:https?://)?(?:www\.|m\.|music\.)?(?:youtu\.be/|youtube\.com/(?:watch\?v=|shorts/|live/|embed/))([A-Za-z0-9_-]{11})',
    re.IGNORECASE
)


def extract_youtube_id(text: str) -> str | None:
    if not text:
        return None
    match = YOUTUBE_REGEX.search(text)
    return match.group(1) if match else None


class DonateXAdapter:
    def __init__(self, token: str, broadcast):
        self.token = token
        self.broadcast = broadcast

    async def run(self) -> None:
        headers = {"Authorization": f"Bearer {self.token}"}
        
        # 1. Negotiate SignalR connection
        async with aiohttp.ClientSession() as session:
            async with session.post(NEGOTIATE_URL, headers=headers) as resp:
                if resp.status == 401:
                    log.error("donatex: invalid token or unauthorized (HTTP 401)")
                    await asyncio.sleep(30)
                    return
                resp.raise_for_status()
                data = await resp.json()

        connection_id = data.get("connectionId")
        if not connection_id:
            log.error("donatex: no connectionId in negotiate response: %s", data)
            await asyncio.sleep(10)
            return

        ws_url = f"{HUB_URL}?id={connection_id}&access_token={self.token}"
        log.info("connecting to DonateX SignalR Hub...")

        async with websockets.connect(ws_url) as ws:
            # 2. Handshake
            await ws.send(json.dumps({"protocol": "json", "version": 1}) + RECORD_SEP)
            handshake = await ws.recv()
            log.info("donatex connected & handshake complete")

            # Background keepalive ping task
            async def ping_loop():
                try:
                    while True:
                        await asyncio.sleep(15)
                        await ws.send(json.dumps({"type": 6}) + RECORD_SEP)
                except asyncio.CancelledError:
                    pass

            ping_task = asyncio.create_task(ping_loop())
            try:
                buffer = ""
                async for raw in ws:
                    buffer += raw
                    while RECORD_SEP in buffer:
                        message_str, buffer = buffer.split(RECORD_SEP, 1)
                        if not message_str.strip():
                            continue
                        try:
                            msg = json.loads(message_str)
                            await self.handle_message(msg)
                        except Exception as e:
                            log.warning("error handling donatex message: %s", e)
            finally:
                ping_task.cancel()

    async def handle_message(self, msg: dict) -> None:
        msg_type = msg.get("type")
        if msg_type != 1:  # Type 1 is Invocation
            return

        target = msg.get("target")
        args = msg.get("arguments") or []
        if not args:
            return

        data = args[0]
        if not isinstance(data, dict):
            return

        if target == "ReceiveDonation":
            user = data.get("username") or data.get("name") or "anonymous"
            amount = data.get("amount") or data.get("amount_formatted") or ""
            currency = data.get("currency") or "₽"
            message = (data.get("message") or "").strip()
            amount_str = f"{amount} {currency}".strip()
            body = f"{user} · {amount_str}".strip(" ·")

            youtube_id = extract_youtube_id(message)

            payload = {
                "type": "alert",
                "kind": "donate",
                "user": user,
                "amount": amount_str,
                "message": message,
                "body": body,
            }
            if youtube_id:
                payload["youtubeId"] = youtube_id

            await self.broadcast(payload)

            # If user requested a YouTube track via donation message:
            if youtube_id:
                log.info("detected YouTube track order from %s: %s", user, youtube_id)
                await self.broadcast({
                    "type": "media_request",
                    "user": user,
                    "amount": amount_str,
                    "message": message,
                    "youtubeId": youtube_id,
                })

        elif target == "ReceiveNewSong":
            # Native DonateX music order event
            donor = data.get("donor") or data.get("username") or "anonymous"
            link = data.get("link") or data.get("url") or ""
            youtube_id = data.get("videoId") or extract_youtube_id(link)
            title = data.get("title") or "YouTube Track"
            if youtube_id:
                log.info("DonateX ReceiveNewSong: %s (id: %s)", title, youtube_id)
                await self.broadcast({
                    "type": "media_request",
                    "user": donor,
                    "title": title,
                    "youtubeId": youtube_id,
                    "link": link,
                })

        elif target == "SongSkipped" or target == "PlayNextSong":
            await self.broadcast({
                "type": "media_control",
                "action": "skip",
            })


async def run(config: dict, broadcast) -> None:
    token = config.get("token") or config.get("api_key") or config.get("widget_id") or ""
    token = token.strip()
    if not token:
        log.warning("donatex: token/api_key not configured, adapter disabled")
        return

    adapter = DonateXAdapter(token, broadcast)
    while True:
        try:
            await adapter.run()
        except asyncio.CancelledError:
            raise
        except Exception as exc:
            log.warning("donatex connection dropped (%s), reconnecting in 10s...", exc)
            await asyncio.sleep(10)
