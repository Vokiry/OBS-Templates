import asyncio
import logging
from pathlib import Path
from urllib.parse import urlparse

log = logging.getLogger("bridge.twitch")


def normalize_twitch(kind: str, user: str, detail: str) -> dict:
    return {"kind": kind, "body": f"{user} · {detail}".strip(" ·")}


async def run(config: dict, broadcast) -> None:
    from twitchAPI.eventsub.websocket import EventSubWebsocket
    from twitchAPI.helper import first
    from twitchAPI.oauth import UserAuthenticationStorageHelper, UserAuthenticator
    from twitchAPI.twitch import Twitch
    from twitchAPI.type import AuthScope

    scopes = [
        AuthScope.BITS_READ,
        AuthScope.CHANNEL_READ_SUBSCRIPTIONS,
        AuthScope.CHANNEL_READ_POLLS,
        AuthScope.CHANNEL_READ_PREDICTIONS,
        AuthScope.CHANNEL_READ_REDEMPTIONS,
    ]
    if config.get("include_follows"):
        scopes.append(AuthScope.MODERATOR_READ_FOLLOWERS)

    storage_path = Path(__file__).parent.parent / ".twitch_token.json"
    redirect_url = str(config.get("redirect_url", "http://localhost:3000")).strip()
    parsed = urlparse(redirect_url)
    redirect_port = parsed.port or 3000

    async def auth_gen(tw, sc):
        log.info("Twitch authorization required. Opening %s...", redirect_url)
        auth = UserAuthenticator(tw, sc, force_verify=False, url=redirect_url, port=redirect_port)
        return await auth.authenticate()

    def make_handler(kind, extract):
        async def handler(data):
            try:
                await broadcast(extract(data.event))
            except Exception:
                log.exception("%s handler failed", kind)
        return handler

    def sub_event(event):
        tier = int(event.tier) // 1000
        return normalize_twitch("sub", event.user_name, f"tier {tier}")

    def resub_event(event):
        months = event.cumulative_months
        return normalize_twitch("resub", event.user_name, f"{months} months")

    def gift_event(event):
        gifter = "anonymous" if event.is_anonymous else (event.user_name or "anonymous")
        return normalize_twitch("gift", gifter, f"× {event.total}")

    def cheer_event(event):
        return normalize_twitch("cheer", event.user_name, str(event.bits))

    def raid_event(event):
        return normalize_twitch("raid", event.from_broadcaster_user_name, f"{event.viewers} viewers")

    def follow_event(event):
        return normalize_twitch("follow", event.user_name, "")

    def poll_event(kind):
        def extractor(event):
            choices = []
            total_votes = sum(c.votes for c in event.choices) if event.choices else 0
            for c in event.choices:
                pct = round((c.votes / total_votes * 100), 1) if total_votes > 0 else 0
                choices.append({
                    "id": c.id,
                    "title": c.title,
                    "votes": c.votes,
                    "percent": pct,
                })
            ends_at = event.ends_at.isoformat() if getattr(event, "ends_at", None) else None
            status = getattr(event, "status", "active")
            return {
                "type": "poll",
                "action": kind,
                "id": event.id,
                "title": event.title,
                "choices": choices,
                "totalVotes": total_votes,
                "status": str(status).lower(),
                "endsAt": ends_at,
            }
        return extractor

    def prediction_event(kind):
        def extractor(event):
            outcomes = []
            total_points = sum(o.channel_points for o in event.outcomes) if event.outcomes else 0
            winning_outcome_id = getattr(event, "winning_outcome_id", None)
            for o in event.outcomes:
                pct = round((o.channel_points / total_points * 100), 1) if total_points > 0 else 0
                outcomes.append({
                    "id": o.id,
                    "title": o.title,
                    "color": getattr(o, "color", "blue"),
                    "points": o.channel_points,
                    "users": getattr(o, "users", 0),
                    "percent": pct,
                    "isWinner": o.id == winning_outcome_id,
                })
            return {
                "type": "prediction",
                "action": kind,
                "id": event.id,
                "title": event.title,
                "status": getattr(event, "status", "active"),
                "outcomes": outcomes,
                "totalPoints": total_points,
                "winningOutcomeId": winning_outcome_id,
            }
        return extractor

    def redemption_event(event):
        reward = getattr(event, "reward", None)
        reward_title = getattr(reward, "title", "Награда") if reward else "Награда"
        reward_cost = getattr(reward, "cost", 0) if reward else 0
        return {
            "type": "chat",
            "subtype": "reward",
            "user": event.user_name or event.user_login or "Viewer",
            "rewardTitle": reward_title,
            "rewardCost": reward_cost,
            "text": event.user_input or "",
        }

    while True:
        try:
            twitch = await Twitch(config["client_id"], config["client_secret"])
            helper = UserAuthenticationStorageHelper(twitch, scopes, storage_path=storage_path, auth_generator_func=auth_gen)
            await helper.bind()
            user = await first(twitch.get_users())
            user_id = user.id
            log.info("twitch authenticated as %s (%s)", user.display_name, user_id)

            eventsub = EventSubWebsocket(twitch)
            eventsub.start()

            # 1. Cheers (bits:read)
            try:
                await eventsub.listen_channel_cheer(user_id, make_handler("cheer", cheer_event))
            except Exception as e:
                log.warning("twitch cheer subscription failed: %s", e)

            # 2. Subscriptions (channel:read:subscriptions)
            try:
                await eventsub.listen_channel_subscribe(user_id, make_handler("sub", sub_event))
                await eventsub.listen_channel_subscription_message(user_id, make_handler("resub", resub_event))
                await eventsub.listen_channel_subscription_gift(user_id, make_handler("gift", gift_event))
            except Exception as e:
                log.warning("twitch subscription listeners failed (channel may not be affiliate/partner): %s", e)

            # 3. Raids (no scope required)
            try:
                await eventsub.listen_channel_raid(make_handler("raid", raid_event), to_broadcaster_user_id=user_id)
            except Exception as e:
                log.warning("twitch raid listener failed: %s", e)

            # 4. Follows (moderator:read:followers)
            if config.get("include_follows"):
                try:
                    await eventsub.listen_channel_follow_v2(user_id, user_id, make_handler("follow", follow_event))
                except Exception as e:
                    log.warning("twitch follow listener failed: %s", e)

            # 5. Polls (channel:read:polls)
            try:
                await eventsub.listen_channel_poll_begin(user_id, make_handler("poll_begin", poll_event("begin")))
                await eventsub.listen_channel_poll_progress(user_id, make_handler("poll_progress", poll_event("progress")))
                await eventsub.listen_channel_poll_end(user_id, make_handler("poll_end", poll_event("end")))
            except Exception as e:
                log.warning("twitch poll listeners failed (channel may not be affiliate/partner): %s", e)

            # 6. Predictions (channel:read:predictions)
            try:
                await eventsub.listen_channel_prediction_begin(user_id, make_handler("pred_begin", prediction_event("begin")))
                await eventsub.listen_channel_prediction_progress(user_id, make_handler("pred_prog", prediction_event("progress")))
                await eventsub.listen_channel_prediction_lock(user_id, make_handler("pred_lock", prediction_event("lock")))
                await eventsub.listen_channel_prediction_end(user_id, make_handler("pred_end", prediction_event("end")))
            except Exception as e:
                log.warning("twitch prediction listeners failed: %s", e)

            # 7. Channel Points Redemptions (channel:read:redemptions)
            try:
                await eventsub.listen_channel_points_custom_reward_redemption_add(user_id, make_handler("redemption", redemption_event))
            except Exception as e:
                log.warning("twitch redemption listener failed: %s", e)

            log.info("twitch eventsub active")
            while True:
                await asyncio.sleep(3600)
        except asyncio.CancelledError:
            raise
        except Exception as exc:
            log.warning("twitch connection lost (%s), reconnecting in 10s", exc)
            await asyncio.sleep(10)
