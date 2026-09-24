import asyncio
import logging
import random
import websockets

log = logging.getLogger("bridge.twitch_chat")

IRC_WS_URL = "wss://irc-ws.chat.twitch.tv:443"


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

                async for raw in ws:
                    for line in raw.splitlines():
                        if not line:
                            continue
                        if line.startswith("PING"):
                            await ws.send(line.replace("PING", "PONG"))
                            continue
                        msg = parse_privmsg(line, channel)
                        if msg:
                            await broadcast(msg)
        except asyncio.CancelledError:
            raise
        except Exception as exc:
            log.warning("twitch_chat connection dropped (%s), reconnecting in 5s...", exc)
            await asyncio.sleep(5)
