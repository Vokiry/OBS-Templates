import asyncio
import json
import logging
import re
import time

import aiohttp

log = logging.getLogger("bridge.donatex")

PUBLIC_HUB_NEGOTIATE = "https://donatex.gg/api/public-donations-hub/negotiate?negotiateVersion=1"
PUBLIC_HUB_WS = "https://donatex.gg/api/public-donations-hub"

MUSIC_HUB_NEGOTIATE = "https://donatex.gg/api/music-widgets-hub/negotiate?negotiateVersion=1"
MUSIC_HUB_WS = "https://donatex.gg/api/music-widgets-hub"

MUSIC_CURRENT_API = "https://donatex.gg/api/v1/music/current"
MUSIC_SKIP_API = "https://donatex.gg/api/v1/music/skip-current"

RECORD_SEP = "\x1e"

YOUTUBE_REGEX = re.compile(
    r"(?:https?://)?(?:www\.|m\.|music\.)?(?:youtu\.be/|youtube\.com/(?:watch\?v=|shorts/|live/|embed/))([A-Za-z0-9_-]{11})",
    re.IGNORECASE,
)


def extract_youtube_id(text: str) -> str | None:
    if not text:
        return None
    match = YOUTUBE_REGEX.search(text)
    return match.group(1) if match else None


class DonateXAdapter:
    def __init__(self, token: str, broadcast):
        self.token = token.strip()
        self.broadcast = broadcast
        self.widget_id = None
        self.music_ws = None
        self.current_donation_id = None
        self.headers = {
            "Authorization": f"Bearer {self.token}",
            "X-External-Token": self.token,
        }

    async def fetch_music_widget_id(self) -> str | None:
        try:
            async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=8)) as session:
                async with session.get(MUSIC_CURRENT_API, headers=self.headers) as resp:
                    if resp.status == 200:
                        data = await resp.json()
                        self.widget_id = data.get("widgetId")
                        self.current_donation_id = data.get("donationId")
                        if data.get("hasTrack") and data.get("musicLink"):
                            yt_id = extract_youtube_id(data["musicLink"])
                            if yt_id:
                                log.info("donatex: queue has active track on startup: %s", data["musicLink"])
                                await self.broadcast(
                                    {
                                        "type": "media_request",
                                        "user": "",
                                        "amount": "",
                                        "message": "",
                                        "youtubeId": yt_id,
                                        "title": "YouTube Track",
                                        "source": "donatex",
                                        "donationId": self.current_donation_id,
                                    }
                                )
                        return self.widget_id
        except Exception as e:
            log.warning("could not fetch music widget ID from DonateX API: %s", e)
        return None

    async def skip_current_track(self, donation_id: str | None = None) -> bool:
        did = donation_id or self.current_donation_id
        success = False

        # If donationId not known, try fetching it from current music endpoint
        if not did:
            try:
                async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=4)) as session:
                    async with session.get(MUSIC_CURRENT_API, headers=self.headers) as resp:
                        if resp.status == 200:
                            cur_data = await resp.json()
                            did = cur_data.get("donationId")
                            if not self.widget_id:
                                self.widget_id = cur_data.get("widgetId")
            except Exception:
                pass

        # 1. Send SignalR PlayNextSong if connected to music-widgets-hub
        if self.music_ws and not self.music_ws.closed and self.widget_id:
            try:
                play_next_msg = (
                    json.dumps(
                        {
                            "type": 1,
                            "invocationId": f"next_{int(time.time() * 1000)}",
                            "target": "PlayNextSong",
                            "arguments": [self.widget_id],
                        }
                    )
                    + RECORD_SEP
                )
                await self.music_ws.send_str(play_next_msg)
                log.info("donatex: sent PlayNextSong via SignalR for widget %s", self.widget_id)
                success = True
            except Exception as e:
                log.debug("donatex: error sending SignalR PlayNextSong: %s", e)

        # 2. Call REST API /v1/music/skip-current
        try:
            async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=8)) as session:
                async with session.post(MUSIC_SKIP_API, headers=self.headers) as resp:
                    if resp.status == 200:
                        log.info("donatex: track marked as played/skipped via API")
                        success = True
                    else:
                        log.warning(
                            "donatex: skip-current returned status %d: %s",
                            resp.status,
                            await resp.text(),
                        )
        except Exception as e:
            log.warning("could not skip track via DonateX API: %s", e)

        # 3. Call widget complete-playback and set-music-as-played if donationId is available
        if did and self.widget_id:
            try:
                async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=6)) as session:
                    url_complete = f"https://donatex.gg/api/music-widgets/complete-playback?widgetId={self.widget_id}&donationId={did}"
                    async with session.post(url_complete, headers=self.headers) as resp:
                        if resp.status == 200:
                            log.info("donatex: complete-playback confirmed for donation %s", did)
                            success = True
                    url_played = f"https://donatex.gg/api/music-widgets/set-music-as-played?donationId={did}"
                    async with session.post(url_played, headers=self.headers) as resp:
                        if resp.status == 200:
                            log.info("donatex: set-music-as-played confirmed for donation %s", did)
                            success = True
            except Exception as e:
                log.debug("donatex: complete-playback error: %s", e)

        self.current_donation_id = None
        return success

    async def skip_current_donation(self) -> bool:
        try:
            async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=8)) as session:
                async with session.post(
                    "https://donatex.gg/api/v1/donations/skip-current", headers=self.headers
                ) as resp:
                    if resp.status == 200:
                        log.info("donatex: current donation skipped via API")
                        return True
        except Exception as e:
            log.warning("could not skip donation via DonateX API: %s", e)
        return False

    async def run_donations_hub(self) -> None:
        """Connects to public-donations-hub for real-time donations & alerts."""
        global is_connected, last_error
        while True:
            try:
                log.info("donatex: negotiating public donations hub...")
                async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=15)) as session:
                    async with session.post(PUBLIC_HUB_NEGOTIATE, headers=self.headers) as resp:
                        if resp.status == 401:
                            log.error(
                                "donatex: 401 Unauthorized. Check External token in donatex.gg -> Settings -> Api"
                            )
                            await asyncio.sleep(25)
                            continue
                        resp.raise_for_status()
                        data = await resp.json()

                    connection_token = data.get("connectionToken") or data.get("connectionId")
                    ws_url = f"{PUBLIC_HUB_WS}?id={connection_token}"

                    async with session.ws_connect(ws_url, headers=self.headers, heartbeat=15) as ws:
                        await ws.send_str(json.dumps({"protocol": "json", "version": 1}) + RECORD_SEP)
                        await ws.receive_str()
                        is_connected = True
                        last_error = None
                        log.info("donatex: donations hub connected & listening for donations!")

                        buffer = ""
                        async for msg in ws:
                            if msg.type == aiohttp.WSMsgType.TEXT:
                                buffer += msg.data
                                while RECORD_SEP in buffer:
                                    raw, buffer = buffer.split(RECORD_SEP, 1)
                                    if not raw.strip():
                                        continue
                                    try:
                                        await self.handle_donation_message(json.loads(raw))
                                    except Exception as e:
                                        log.warning("donatex donations hub parse error: %s", e)
                            elif msg.type in (aiohttp.WSMsgType.CLOSED, aiohttp.WSMsgType.ERROR):
                                break

            except asyncio.CancelledError:
                raise
            except Exception as e:
                is_connected = False
                last_error = str(e)
                log.warning("donatex donations hub error (%s), reconnecting in 10s...", e)
                await asyncio.sleep(10)

    async def run_music_hub(self) -> None:
        """Connects to music-widgets-hub to register widget presence and receive song orders."""
        while True:
            try:
                if not self.widget_id:
                    await self.fetch_music_widget_id()

                if not self.widget_id:
                    await asyncio.sleep(15)
                    continue

                log.info("donatex: negotiating music widget hub for %s...", self.widget_id)
                async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=15)) as session:
                    async with session.post(MUSIC_HUB_NEGOTIATE) as resp:
                        resp.raise_for_status()
                        data = await resp.json()

                    connection_token = data.get("connectionToken") or data.get("connectionId")
                    ws_url = f"{MUSIC_HUB_WS}?id={connection_token}"

                    async with session.ws_connect(ws_url, heartbeat=15) as ws:
                        self.music_ws = ws
                        await ws.send_str(json.dumps({"protocol": "json", "version": 1}) + RECORD_SEP)
                        await ws.receive_str()

                        # 1. Join widget group to report presence to DonateX dashboard
                        await ws.send_str(
                            json.dumps(
                                {
                                    "type": 1,
                                    "invocationId": "join_1",
                                    "target": "JoinWidget",
                                    "arguments": [self.widget_id],
                                }
                            )
                            + RECORD_SEP
                        )
                        log.info("donatex: music widget connected & joined group! (OBS widget online)")

                        # 2. Start periodic Heartbeat task
                        async def heartbeat_loop():
                            try:
                                hb_id = 1
                                while True:
                                    await asyncio.sleep(10)
                                    hb_id += 1
                                    await ws.send_str(
                                        json.dumps(
                                            {
                                                "type": 1,
                                                "invocationId": f"hb_{hb_id}",
                                                "target": "Heartbeat",
                                                "arguments": [],
                                            }
                                        )
                                        + RECORD_SEP
                                    )
                            except asyncio.CancelledError:
                                pass

                        hb_task = asyncio.create_task(heartbeat_loop())
                        try:
                            buffer = ""
                            async for msg in ws:
                                if msg.type == aiohttp.WSMsgType.TEXT:
                                    buffer += msg.data
                                    while RECORD_SEP in buffer:
                                        raw, buffer = buffer.split(RECORD_SEP, 1)
                                        if not raw.strip():
                                            continue
                                        try:
                                            await self.handle_music_message(json.loads(raw), ws)
                                        except Exception as e:
                                            log.warning("donatex music hub parse error: %s", e)
                                elif msg.type in (aiohttp.WSMsgType.CLOSED, aiohttp.WSMsgType.ERROR):
                                    break
                        finally:
                            hb_task.cancel()
                            self.music_ws = None

            except asyncio.CancelledError:
                raise
            except Exception as e:
                log.warning("donatex music hub error (%s), reconnecting in 10s...", e)
                await asyncio.sleep(10)

    async def handle_donation_message(self, msg: dict) -> None:
        if msg.get("type") != 1:
            return

        target = msg.get("target")
        args = msg.get("arguments") or []
        if not args or not isinstance(args[0], dict):
            return

        data = args[0]
        if target in ("DonationCreated", "DonationRerun"):
            user = data.get("username") or data.get("name") or "anonymous"
            amount = data.get("amount") or data.get("amountInRub") or ""
            currency = data.get("currency") or "RUB"
            message = (data.get("message") or "").strip()
            music_link = data.get("musicLink") or ""
            amount_str = f"{amount} {currency}".strip()
            body = f"{user} · {amount_str}".strip(" ·")

            youtube_id = extract_youtube_id(music_link) or extract_youtube_id(message)

            voice_file = data.get("voiceFilePath") or data.get("voice_file_path")
            ai_voice_file = data.get("aiResponseVoiceFilePath") or data.get("ai_response_voice_file_path")
            ai_response = data.get("aiResponse") or data.get("ai_response")

            payload = {
                "type": "alert",
                "kind": "donate",
                "user": user,
                "amount": amount_str,
                "message": message,
                "body": body,
                "isTest": data.get("isTest", False),
            }
            if youtube_id:
                payload["youtubeId"] = youtube_id
            if voice_file:
                payload["voiceUrl"] = voice_file
                log.info("donatex: donation includes voice audio: %s", voice_file)
            if ai_voice_file:
                payload["aiVoiceUrl"] = ai_voice_file
            if ai_response:
                payload["aiResponse"] = str(ai_response)

            log.info("donatex: %s from %s (%s)", target, user, amount_str)
            await self.broadcast(payload)

            if not music_link and youtube_id:
                log.info("donatex: ad-hoc YouTube link in donation message: %s", youtube_id)
                await self.broadcast(
                    {
                        "type": "media_request",
                        "user": user,
                        "amount": amount_str,
                        "message": message,
                        "youtubeId": youtube_id,
                        "title": "YouTube Track",
                        "source": "donation_message",
                    }
                )

    async def handle_music_message(self, msg: dict, ws) -> None:
        if msg.get("type") != 1:
            return

        target = msg.get("target")
        args = msg.get("arguments") or []
        data = args[0] if (args and isinstance(args[0], dict)) else {}

        if target == "ReceiveNewSong":
            donor = data.get("donor") or data.get("username") or "viewer"
            link = data.get("link") or data.get("musicLink") or ""
            title = data.get("title") or "YouTube Track"
            yt_id = data.get("videoId") or extract_youtube_id(link)
            self.current_donation_id = data.get("donationId") or data.get("id")

            if yt_id:
                log.info(
                    "donatex: ReceiveNewSong: %s (%s) [donationId: %s]",
                    title,
                    yt_id,
                    self.current_donation_id,
                )
                await self.broadcast(
                    {
                        "type": "media_request",
                        "user": donor,
                        "title": title,
                        "youtubeId": yt_id,
                        "link": link,
                        "source": "donatex",
                        "donationId": self.current_donation_id,
                    }
                )

        elif target in ("SongSkipped", "SkipSong", "PlayNextSong"):
            log.info("donatex: music skipped by server dashboard (%s)", target)
            self.current_donation_id = None
            await self.broadcast(
                {
                    "type": "media_control",
                    "action": "skip",
                    "origin": "donatex_server",
                }
            )

    async def run(self) -> None:
        await asyncio.gather(
            self.run_donations_hub(),
            self.run_music_hub(),
        )


active_adapter = None
is_connected: bool = False
last_error: str | None = None


def get_status() -> dict:
    return {
        "connected": is_connected,
        "error": last_error,
    }


async def skip_track(donation_id: str | None = None) -> bool:
    if active_adapter:
        return await active_adapter.skip_current_track(donation_id=donation_id)
    return False


async def skip_donation() -> bool:
    if active_adapter:
        return await active_adapter.skip_current_donation()
    return False


async def run(config: dict, broadcast) -> None:
    global active_adapter
    token = config.get("token") or config.get("api_key") or ""
    token = token.strip()
    if not token:
        log.warning("donatex: token is empty in config, adapter disabled")
        return

    adapter = DonateXAdapter(token, broadcast)
    active_adapter = adapter
    try:
        await adapter.run()
    finally:
        active_adapter = None
