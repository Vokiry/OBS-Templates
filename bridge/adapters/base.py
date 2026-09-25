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
    if msg_type in ("chat", "7tv_emotes", "room_info", "status", "countdown_control", "chat_clear"):
        return payload
    kind = str(payload.get("kind", "donate")).lower()
    title = payload.get("title") or KIND_TITLES.get(kind, kind.upper())
    body = payload.get("body") or payload.get("user") or ""
    res = {
        "type": "alert",
        "kind": kind,
        "title": str(title).upper(),
        "body": str(body),
    }
    if "user" in payload:
        res["user"] = str(payload["user"])
    if "amount" in payload:
        res["amount"] = str(payload["amount"])
    if "message" in payload:
        res["message"] = str(payload["message"])
    return res


def encode(payload: dict) -> str:
    return json.dumps(normalize(payload), ensure_ascii=False)
