import asyncio
import logging
import random
import re
import aiohttp
import websockets

log = logging.getLogger("bridge.twitch_chat")

IRC_WS_URL = "wss://irc-ws.chat.twitch.tv:443"


async def fetch_7tv_emotes(room_id: str) -> dict:
    urls = [
        f"https://enhanced.jeetbot.cc/https://7tv.io/v3/users/twitch/{room_id}",
        f"https://7tv.io/v3/users/twitch/{room_id}",
    ]
    for url in urls:
        try:
            async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=5)) as session:
                async with session.get(url) as resp:
                    if resp.status == 200:
                        data = await resp.json()
                        emotes = {}
                        for e in data.get("emote_set", {}).get("emotes", []):
                            name = e.get("name")
                            eid = e.get("id")
                            if name and eid:
                                emotes[name] = f"https://enhanced.jeetbot.cc/https://cdn.7tv.app/emote/{eid}/2x.webp"
                        log.info("loaded %d 7TV channel emotes for room %s", len(emotes), room_id)
                        return emotes
        except Exception as e:
            log.debug("could not fetch 7TV emotes from %s: %s", url, e)
    return {}


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


def parse_privmsg(line: str, channel: str) -> dict | None:
    if f"PRIVMSG #{channel}" not in line:
        return None
    tags = {}
    if line.startswith("@"):
        try:
            tag_str, rest = line[1:].split(" ", 1)
            for pair in tag_str.split(";"):
                if "=" in pair:
                    k, v = pair.split("=", 1)
                    tags[k] = v
        except ValueError:
            rest = line
    else:
        rest = line

    parts = rest.split(f"PRIVMSG #{channel} :", 1)
    if len(parts) < 2:
        return None
    text = parts[1].rstrip("\r\n")
    prefix = parts[0].strip()
    nick = prefix.split("!")[0].lstrip(":")
    user = tags.get("display-name") or nick
    color = tags.get("color") or None

    twitch_emotes = []
    emotes_tag = tags.get("emotes")
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

    return {
        "type": "chat",
        "user": user,
        "text": text,
        "color": color,
        "emotes": twitch_emotes,
    }


async def run(config: dict, broadcast) -> None:
    channel = config.get("channel", "").strip().lstrip("#").lower()
    if not channel:
        log.warning("twitch_chat: channel is not specified in config, chat listener disabled")
        return

    async def broadcast_7tv(room_id: str):
        emotes = await fetch_7tv_emotes(room_id)
        if emotes:
            await broadcast({"type": "7tv_emotes", "channel": channel, "emotes": emotes})

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
                            await ws.send(line.replace("PING", "PONG"))
                            continue
                        if not room_id_fetched and "room-id=" in line:
                            for item in line.split(";"):
                                if "room-id=" in item:
                                    try:
                                        val = item.split("room-id=")[1].split()[0]
                                        room_id_fetched = True
                                        asyncio.create_task(broadcast_7tv(val))
                                    except Exception:
                                        pass
                                    break
                        msg = parse_privmsg(line, channel)
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
