import json

KIND_TITLES = {
    "sub": "NEW SUB",
    "resub": "RESUB",
    "gift": "GIFT SUB",
    "raid": "RAID",
    "cheer": "CHEER",
    "donate": "DONATION",
    "follow": "NEW FOLLOWER",
}


def normalize(payload: dict) -> dict:
    msg_type = payload.get("type", "alert")
    if msg_type in ("chat", "7tv_emotes", "room_info", "status"):
        return payload
    kind = str(payload.get("kind", "donate")).lower()
    title = payload.get("title") or KIND_TITLES.get(kind, kind.upper())
    body = payload.get("body") or payload.get("user") or ""
    return {"type": "alert", "title": str(title).upper(), "body": str(body)}


def encode(payload: dict) -> str:
    return json.dumps(normalize(payload), ensure_ascii=False)
