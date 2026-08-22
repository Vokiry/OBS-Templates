import asyncio
import logging

log = logging.getLogger("bridge.twitch")


def normalize_twitch(kind: str, user: str, detail: str) -> dict:
    return {"kind": kind, "body": f"{user} · {detail}".strip(" ·")}


async def run(config: dict, broadcast) -> None:
    from twitchAPI.helper import first
    from twitchAPI.twitch import Twitch
    from twitchAPI.type import AuthScope
    from twitchAPI.eventsub.websocket import EventSubWebsocket

    scopes = [AuthScope.BITS_READ]
    if config.get("include_follows"):
        scopes.append(AuthScope.MODERATOR_READ_FOLLOWERS)

    twitch = await Twitch(config["client_id"], config["client_secret"])
    helper = UserAuthenticationStorageHelper(twitch, scopes)
    await helper.bind()
    user = await first(twitch.get_users())
    user_id = user.id
    log.info("twitch authenticated as %s (%s)", user.display_name, user_id)

    def make_handler(kind, extract):
        async def handler(data):
            try:
                await broadcast(extract(data.event))
            except Exception:
                log.exception("%s handler failed", kind)
        return handler

    async def sub_event(event):
        tier = int(event.tier) // 1000
        return normalize_twitch("sub", event.user_name, f"tier {tier}")

    async def resub_event(event):
        months = event.cumulative_months
        return normalize_twitch("resub", event.user_name, f"{months} months")

    async def gift_event(event):
        gifter = "anonymous" if event.is_anonymous else (event.user_name or "anonymous")
        return normalize_twitch("gift", gifter, f"× {event.total}")

    async def cheer_event(event):
        return normalize_twitch("cheer", event.user_name, str(event.bits))

    async def raid_event(event):
        return normalize_twitch("raid", event.from_broadcaster_user_name, f"{event.viewers} viewers")

    async def follow_event(event):
        return normalize_twitch("follow", event.user_name, "")

    eventsub = EventSubWebsocket(twitch)
    eventsub.start()

    await eventsub.listen_channel_subscribe(user_id, make_handler("sub", sub_event))
    await eventsub.listen_channel_subscription_message(user_id, make_handler("resub", resub_event))
    await eventsub.listen_channel_subscription_gift(user_id, make_handler("gift", gift_event))
    await eventsub.listen_channel_cheer(user_id, make_handler("cheer", cheer_event))
    await eventsub.listen_channel_raid(make_handler("raid", raid_event), to_broadcaster_user_id=user_id)
    if config.get("include_follows"):
        await eventsub.listen_channel_follow_v2(user_id, user_id, make_handler("follow", follow_event))

    log.info("twitch eventsub active")
    while True:
        await asyncio.sleep(3600)
