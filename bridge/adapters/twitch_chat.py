import asyncio
import json
import logging
import os
from pathlib import Path
import random
import re
import aiohttp
import websockets

log = logging.getLogger("bridge.twitch_chat")

IRC_WS_URL = "wss://irc-ws.chat.twitch.tv:443"


async def fetch_7tv_emotes(room_id: str, source: str = "direct", mirror: str = "https://enhanced.jeetbot.cc") -> tuple[dict, str]:
    source = (source or "direct").lower()
    mirror_clean = (mirror or "https://enhanced.jeetbot.cc").rstrip("/")
    direct_api = f"https://7tv.io/v3/users/twitch/{room_id}"
    mirror_api = f"{mirror_clean}/https://7tv.io/v3/users/twitch/{room_id}"
    direct_cdn = "https://cdn.7tv.app/emote"
    mirror_cdn = f"{mirror_clean}/https://cdn.7tv.app/emote"

    if source == "mirror":
        targets = [(mirror_api, mirror_cdn, "mirror")]
    elif source == "direct":
        targets = [(direct_api, direct_cdn, "direct")]
    else:  # "auto"
        targets = [
            (direct_api, direct_cdn, "direct"),
            (mirror_api, mirror_cdn, "mirror"),
        ]

    for url, cdn, mode in targets:
        try:
            async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=4)) as session:
                async with session.get(url) as resp:
                    if resp.status == 200:
                        data = await resp.json()
                        emotes = {}
                        for e in data.get("emote_set", {}).get("emotes", []):
                            name = e.get("name")
                            eid = e.get("id")
                            if name and eid:
                                emotes[name] = f"{cdn}/{eid}/2x.webp"
                        log.info("loaded %d 7TV channel emotes for room %s (source: %s)", len(emotes), room_id, mode)
                        return emotes, cdn
        except Exception as e:
            log.debug("could not fetch 7TV emotes from %s: %s", url, e)
    return {}, direct_cdn


MEDIA_REGEX = re.compile(
    r'(https?://(?:[a-zA-Z0-9-]+\.)*drisnya\.online/[^\s]+|https?://(?:[a-zA-Z0-9-]+\.)*tenor\.com/[^\s]+|https?://(?:[a-zA-Z0-9-]+\.)*giphy\.com/[^\s]+|https?://(?:[a-zA-Z0-9-]+\.)*imgur\.com/[^\s]+)',
    re.IGNORECASE
)


async def resolve_drisnya_media(url: str) -> str:
    m = re.search(r"drisnya\.online/post/([A-Za-z0-9_-]+)", url)
    if not m:
        return url
    slug = m.group(1)
    api_url = f"https://img.drisnya.online/api/posts/{slug}"
    try:
        async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=4)) as session:
            async with session.get(api_url, headers={"Accept": "application/json"}) as resp:
                if resp.status == 200:
                    payload = await resp.json()
                    cdn_base = (payload.get("cdnBase") or "").rstrip("/")
                    media_list = payload.get("media") or []
                    if media_list and isinstance(media_list, list):
                        media = media_list[0]
                        file_path = (media.get("filePath") or media.get("thumbnailPath") or "").lstrip("/")
                        if cdn_base and file_path:
                            return f"{cdn_base}/{file_path}"
            # Fallback: scrape og:image from the HTML page
            async with session.get(f"https://img.drisnya.online/post/{slug}", headers={"Accept": "text/html"}) as resp:
                if resp.status == 200:
                    html = await resp.text()
                    og_match = re.search(r'<meta\s+property=["\x27]og:image["\x27]\s+content=["\x27]([^"\x27]+)["\x27]', html)
                    if og_match:
                        return og_match.group(1)
    except Exception as e:
        log.debug("could not resolve drisnya post %s: %s", slug, e)
    return url


SEED_BADGES = {
    "broadcaster/1": "https://static-cdn.jtvnw.net/badges/v1/5527c58c-fb7d-422d-b71b-f309dcb85cc1/2",
    "moderator/1": "https://static-cdn.jtvnw.net/badges/v1/3267646d-33f0-4b17-b3df-f923a41db1d0/2",
    "vip/1": "https://static-cdn.jtvnw.net/badges/v1/b817aba4-fad8-49e2-b88a-7cc744dfa6ec/2",
    "subscriber/0": "https://static-cdn.jtvnw.net/badges/v1/5d9f2208-5dd8-11e7-8513-2ff4b9e6b4f5/2",
    "subscriber/1": "https://static-cdn.jtvnw.net/badges/v1/5d9f2208-5dd8-11e7-8513-2ff4b9e6b4f5/2",
    "partner/1": "https://static-cdn.jtvnw.net/badges/v1/d12a2e27-16f6-41d0-ab77-b780518f00a3/2",
    "turbo/1": "https://static-cdn.jtvnw.net/badges/v1/bd444ec6-8794-4c9f-8640-f759d9869422/2",
    "premium/1": "https://static-cdn.jtvnw.net/badges/v1/bbbe0db0-a598-423e-86d0-f9fb98ca1933/2",
    "sub-gifter/1": "https://static-cdn.jtvnw.net/badges/v1/f1d2543e-a1cf-41c1-be5a-2cb79f1c7d7e/2",
    "sub-gift-leader/1": "https://static-cdn.jtvnw.net/badges/v1/f1d2543e-a1cf-41c1-be5a-2cb79f1c7d7e/2",
    "bits/1": "https://static-cdn.jtvnw.net/badges/v1/73b5c3fb-245e-4f5c-add5-bdae25160bdf/2",
    "bits-leader/1": "https://static-cdn.jtvnw.net/badges/v1/73b5c3fb-245e-4f5c-add5-bdae25160bdf/2",
    "artist-badge/1": "https://static-cdn.jtvnw.net/badges/v1/4300a897-d3c8-43e6-ac07-55e2d1eb97d1/2",
}


BADGES_CACHE_FILE = Path(__file__).parent.parent / ".twitch_badges_cache.json"
cached_badge_map = dict(SEED_BADGES)

if BADGES_CACHE_FILE.exists():
    try:
        loaded_cached = json.loads(BADGES_CACHE_FILE.read_text("utf-8"))
        cached_badge_map.update(loaded_cached)
    except Exception:
        pass


def get_cached_badges() -> dict:
    return cached_badge_map


async def fetch_all_twitch_badges(client_id: str = "", client_secret: str = "", room_id: str | None = None) -> dict:
    global cached_badge_map

    if not client_id or not client_secret:
        return cached_badge_map

    try:
        async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=8)) as session:
            # 1. Get Twitch App Access Token (POST body, not URL params — per OWASP)
            async with session.post(
                "https://id.twitch.tv/oauth2/token",
                data={
                    "client_id": client_id,
                    "client_secret": client_secret,
                    "grant_type": "client_credentials",
                }
            ) as r:
                if r.status != 200:
                    return cached_badge_map
                app_token = (await r.json()).get("access_token")

            if not app_token:
                return cached_badge_map

            headers = {"Client-Id": client_id, "Authorization": f"Bearer {app_token}"}

            # 2. Fetch ALL global chat badges (Staff, Admin, VIP, Founder, partner, and EVERY drop / event badge)
            async with session.get("https://api.twitch.tv/helix/chat/badges/global", headers=headers) as r:
                if r.status == 200:
                    global_data = await r.json()
                    for b in global_data.get("data", []):
                        set_id = b.get("set_id")
                        for v in b.get("versions", []):
                            v_id = v.get("id")
                            img_url = v.get("image_url_2x") or v.get("image_url_1x") or v.get("image_url_4x")
                            if set_id and v_id and img_url:
                                cached_badge_map[f"{set_id}/{v_id}"] = img_url
                    log.info("loaded %d Twitch global badge versions from Helix API", len(cached_badge_map))

            # 3. Fetch channel-specific badges if room_id is known (subscriber tiers, bits, etc.)
            if room_id:
                async with session.get(f"https://api.twitch.tv/helix/chat/badges?broadcaster_id={room_id}", headers=headers) as r:
                    if r.status == 200:
                        chan_data = await r.json()
                        for b in chan_data.get("data", []):
                            set_id = b.get("set_id")
                            for v in b.get("versions", []):
                                v_id = v.get("id")
                                img_url = v.get("image_url_2x") or v.get("image_url_1x") or v.get("image_url_4x")
                                if set_id and v_id and img_url:
                                    cached_badge_map[f"{set_id}/{v_id}"] = img_url
                        log.info("loaded channel badges for room %s", room_id)

            fd = os.open(str(BADGES_CACHE_FILE), os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
            try:
                os.write(fd, json.dumps(cached_badge_map).encode("utf-8"))
            finally:
                os.close(fd)
    except Exception as e:
        log.debug("could not fetch Twitch badges from Helix: %s", e)

    return cached_badge_map


def parse_badges(badges_tag: str | None) -> list[dict]:
    badges = []
    if badges_tag:
        for item in badges_tag.split(","):
            if "/" in item:
                s, v = item.split("/", 1)
                badges.append({"set": s, "version": v})
    return badges


def parse_emotes(emotes_tag: str | None) -> list[dict]:
    twitch_emotes = []
    if emotes_tag:
        for group in emotes_tag.split("/"):
            if ":" in group:
                emote_id, ranges = group.split(":", 1)
                for r in ranges.split(","):
                    if "-" in r:
                        try:
                            start, end = map(int, r.split("-", 1))
                            twitch_emotes.append({
                                "id": emote_id,
                                "start": start,
                                "end": end + 1,
                                "url": f"https://static-cdn.jtvnw.net/emoticons/v2/{emote_id}/default/dark/2.0",
                            })
                        except ValueError:
                            pass
    return twitch_emotes


def parse_irc_message(line: str, channel: str) -> dict | None:
    tags = {}
    rest = line
    if line.startswith("@"):
        try:
            tag_str, rest = line[1:].split(" ", 1)
            for pair in tag_str.split(";"):
                if "=" in pair:
                    k, v = pair.split("=", 1)
                    v = v.replace(r"\s", " ").replace(r"\:", ";").replace(r"\r", "\r").replace(r"\n", "\n").replace(r"\\", "\\")
                    tags[k] = v
        except ValueError:
            rest = line

    # 1. Standard Chat PRIVMSG
    if f"PRIVMSG #{channel}" in rest:
        parts = rest.split(f"PRIVMSG #{channel} :", 1)
        if len(parts) < 2:
            return None
        text = parts[1].rstrip("\r\n")
        prefix = parts[0].strip()
        nick = prefix.split("!")[0].lstrip(":")
        user = tags.get("display-name") or nick
        color = tags.get("color") or None
        twitch_emotes = parse_emotes(tags.get("emotes"))
        badges = parse_badges(tags.get("badges"))

        subtype = "message"
        custom_reward_id = tags.get("custom-reward-id")
        if custom_reward_id:
            subtype = "reward"

        msg_data = {
            "type": "chat",
            "subtype": subtype,
            "user": user,
            "text": text,
            "color": color,
            "emotes": twitch_emotes,
            "badges": badges,
        }
        if custom_reward_id:
            msg_data["customRewardId"] = custom_reward_id
        return msg_data

    # 2. Announcement via USERNOTICE
    if f"USERNOTICE #{channel}" in rest:
        msg_id = tags.get("msg-id", "").lower()
        if msg_id == "announcement":
            parts = rest.split(f"USERNOTICE #{channel}", 1)
            after = parts[1].strip()
            text = ""
            if after.startswith(":"):
                text = after[1:].rstrip("\r\n")
            elif " :" in after:
                text = after.split(" :", 1)[1].rstrip("\r\n")

            prefix = parts[0].strip()
            nick = prefix.split("!")[0].lstrip(":") if "!" in prefix else tags.get("login", "")
            user = tags.get("display-name") or nick or "announcement"
            color = tags.get("color") or None
            announcement_color = tags.get("msg-param-color", "PRIMARY").upper()
            twitch_emotes = parse_emotes(tags.get("emotes"))
            badges = parse_badges(tags.get("badges"))

            return {
                "type": "chat",
                "subtype": "announcement",
                "user": user,
                "text": text,
                "color": color,
                "announcementColor": announcement_color,
                "emotes": twitch_emotes,
                "badges": badges,
            }

    return None


async def run(config: dict, broadcast) -> None:
    channel = config.get("channel", "").strip().lstrip("#").lower()
    if not channel:
        log.warning("twitch_chat: channel is not specified in config, chat listener disabled")
        return

    source = config.get("seven_tv_source", "direct")
    mirror = config.get("seven_tv_mirror", "https://enhanced.jeetbot.cc")
    client_id = config.get("client_id", "")
    client_secret = config.get("client_secret", "")

    # Preload and broadcast all global badges (including all game drops and event badges)
    all_badges = await fetch_all_twitch_badges(client_id, client_secret)
    await broadcast({"type": "twitch_badges", "badges": all_badges})

    async def broadcast_badges_and_7tv(room_id: str):
        # Fetch channel-specific badges (subscriber tiers, bits, etc.)
        badges = await fetch_all_twitch_badges(client_id, client_secret, room_id)
        await broadcast({"type": "twitch_badges", "badges": badges})
        emotes, cdn_base = await fetch_7tv_emotes(room_id, source=source, mirror=mirror)
        if emotes:
            await broadcast({
                "type": "7tv_emotes",
                "channel": channel,
                "roomId": room_id,
                "cdnBase": cdn_base,
                "emotes": emotes,
            })

    while True:
        try:
            nick = f"justinfan{random.randint(10000, 99999)}"
            log.info("connecting to Twitch IRC chat for #%s...", channel)
            async with websockets.connect(IRC_WS_URL) as ws:
                await ws.send("CAP REQ :twitch.tv/tags twitch.tv/commands")
                await ws.send(f"PASS oauth:{nick}")
                await ws.send(f"NICK {nick}")
                await ws.send(f"JOIN #{channel}")
                log.info("connected and listening to #%s chat", channel)

                room_id_fetched = False
                async for raw in ws:
                    for line in raw.splitlines():
                        if not line:
                            continue
                        if line.startswith("PING"):
                            await ws.send("PONG" + line[4:])
                            continue
                        if not room_id_fetched and "room-id=" in line:
                            for item in line.split(";"):
                                if "room-id=" in item:
                                    try:
                                        val = item.split("room-id=")[1].split()[0]
                                        room_id_fetched = True
                                        _task = asyncio.create_task(broadcast_badges_and_7tv(val))
                                        _task.add_done_callback(lambda t: t.result() if not t.cancelled() and not t.exception() else None)
                                    except Exception:
                                        pass
                                    break
                        msg = parse_irc_message(line, channel)
                        if msg:
                            m_match = MEDIA_REGEX.search(msg["text"])
                            if m_match:
                                raw_url = m_match.group(1).rstrip(".,!?;:)\"")
                                resolved_url = await resolve_drisnya_media(raw_url)
                                msg["mediaUrl"] = resolved_url
                            await broadcast(msg)
        except asyncio.CancelledError:
            raise
        except Exception as exc:
            log.warning("twitch_chat connection dropped (%s), reconnecting in 5s...", exc)
            await asyncio.sleep(5)
