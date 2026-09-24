import asyncio
import logging
import random
import aiohttp
import websockets

log = logging.getLogger("bridge.twitch_chat")

IRC_WS_URL = "wss://irc-ws.chat.twitch.tv:443"


async def fetch_7tv_emotes(room_id: str) -> dict:
    url = f"https://7tv.io/v3/users/twitch/{room_id}"
    try:
        async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=8)) as session:
            async with session.get(url) as resp:
                if resp.status == 200:
                    data = await resp.json()
                    emotes = {}
                    for e in data.get("emote_set", {}).get("emotes", []):
                        name = e.get("name")
                        host = e.get("data", {}).get("host", {}).get("url", "")
                        if host.startswith("//"):
                            host = "https:" + host
                        if name and host:
                            emotes[name] = f"{host}/2x.webp"
                    log.info("loaded %d 7TV channel emotes for room %s", len(emotes), room_id)
                    return emotes
    except Exception as e:
        log.warning("could not fetch 7TV emotes for room %s: %s", room_id, e)
    return {}


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
    return {
        "type": "chat",
        "user": user,
        "text": text,
        "color": color,
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
                            await broadcast(msg)
        except asyncio.CancelledError:
            raise
        except Exception as exc:
            log.warning("twitch_chat connection dropped (%s), reconnecting in 5s...", exc)
            await asyncio.sleep(5)
            raise
        except Exception as exc:
            log.warning("twitch_chat connection dropped (%s), reconnecting in 5s...", exc)
            await asyncio.sleep(5)
