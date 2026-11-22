"""TOML serialization, validation, and escaping service."""

import math

from services import yandex_tts


def toml_escape(val) -> str:
    """Escape string values for safe inclusion in TOML."""
    if val is None:
        return ""
    return str(val).replace("\\", "\\\\").replace('"', '\\"').replace("\n", "").replace("\r", "")


def validate_config(cfg: dict) -> None:
    """Reject syntactically valid but semantically unusable configuration values."""
    if not isinstance(cfg, dict):
        raise ValueError("configuration must be an object")
    section_names = (
        "server", "twitch", "twitch_chat", "donationalerts", "donatex", "goal",
        "tts", "appearance", "transitions", "media",
    )
    for name in section_names:
        if name in cfg and not isinstance(cfg[name], dict):
            raise ValueError(f"[{name}] must be a table")

    server = cfg.get("server", {})
    port = server.get("port", 8787)
    if isinstance(port, bool) or not isinstance(port, int) or not 1 <= port <= 65535:
        raise ValueError("server.port must be an integer between 1 and 65535")
    if not isinstance(server.get("host", "127.0.0.1"), str):
        raise ValueError("server.host must be a string")

    fade = cfg.get("twitch_chat", {}).get("fade_seconds", 45)
    if isinstance(fade, bool) or not isinstance(fade, int) or fade < 0:
        raise ValueError("twitch_chat.fade_seconds must be a non-negative integer")

    goal = cfg.get("goal", {})
    for key, default in (("current", 0.0), ("target", 10000.0)):
        try:
            value = float(goal.get(key, default))
        except (TypeError, ValueError) as exc:
            raise ValueError(f"goal.{key} must be numeric") from exc
        if not math.isfinite(value):
            raise ValueError(f"goal.{key} must be finite")
    if float(goal.get("target", 10000.0)) <= 0:
        raise ValueError("goal.target must be positive")

    tts = cfg.get("tts", {})
    try:
        volume = float(tts.get("volume", 0.8))
    except (TypeError, ValueError) as exc:
        raise ValueError("tts.volume must be numeric") from exc
    if not math.isfinite(volume) or not 0 <= volume <= 1:
        raise ValueError("tts.volume must be between 0 and 1")
    max_length = tts.get("max_length", 200)
    if isinstance(max_length, bool) or not isinstance(max_length, int) or max_length < 1:
        raise ValueError("tts.max_length must be a positive integer")
    for key in ("random_pool", "blacklist"):
        value = tts.get(key, [])
        if not isinstance(value, list) or any(not isinstance(item, str) for item in value):
            raise ValueError(f"tts.{key} must be an array of strings")
    if not isinstance(tts.get("vip_voices", {}), dict):
        raise ValueError("tts.vip_voices must be a table")

    media = cfg.get("media", {})
    if not isinstance(media.get("ignore", []), list):
        raise ValueError("media.ignore must be an array")
    if media.get("youtube_domain", "youtube-nocookie.com") not in ("youtube.com", "youtube-nocookie.com"):
        raise ValueError("media.youtube_domain is invalid")
    transitions = cfg.get("transitions", {})
    duration = transitions.get("duration_ms", 600)
    if isinstance(duration, bool) or not isinstance(duration, int) or duration < 1:
        raise ValueError("transitions.duration_ms must be a positive integer")


def serialize_toml(cfg: dict) -> str:
    """Validate and serialize configuration dictionary to strict TOML format."""
    validate_config(cfg)
    lines = [
        "[server]",
        f'host = "{toml_escape(cfg.get("server", {}).get("host", "127.0.0.1"))}"',
        f"port = {int(cfg.get('server', {}).get('port', 8787))}",
        "",
        "[twitch]",
        f"enabled = {str(cfg.get('twitch', {}).get('enabled', False)).lower()}",
        f'client_id = "{toml_escape(cfg.get("twitch", {}).get("client_id", ""))}"',
        f'client_secret = "{toml_escape(cfg.get("twitch", {}).get("client_secret", ""))}"',
        f"include_follows = {str(cfg.get('twitch', {}).get('include_follows', False)).lower()}",
        f'redirect_url = "{toml_escape(cfg.get("twitch", {}).get("redirect_url", "http://localhost:3000"))}"',
        "",
        "[twitch_chat]",
        f"enabled = {str(cfg.get('twitch_chat', {}).get('enabled', False)).lower()}",
        f'channel = "{toml_escape(cfg.get("twitch_chat", {}).get("channel", ""))}"',
        f'seven_tv_source = "{toml_escape(cfg.get("twitch_chat", {}).get("seven_tv_source", "direct"))}"',
        f'seven_tv_mirror = "{toml_escape(cfg.get("twitch_chat", {}).get("seven_tv_mirror", "https://enhanced.jeetbot.cc"))}"',
        f"fade_seconds = {int(cfg.get('twitch_chat', {}).get('fade_seconds', 45))}",
        "",
        "[donationalerts]",
        f"enabled = {str(cfg.get('donationalerts', {}).get('enabled', False)).lower()}",
        f'client_id = "{toml_escape(cfg.get("donationalerts", {}).get("client_id", ""))}"',
        f'client_secret = "{toml_escape(cfg.get("donationalerts", {}).get("client_secret", ""))}"',
        f'access_token = "{toml_escape(cfg.get("donationalerts", {}).get("access_token", ""))}"',
        "",
        "[donatex]",
        f"enabled = {str(cfg.get('donatex', {}).get('enabled', False)).lower()}",
        f'token = "{toml_escape(cfg.get("donatex", {}).get("token", ""))}"',
        "",
        "[goal]",
        f"enabled = {str(cfg.get('goal', {}).get('enabled', False)).lower()}",
        f'title = "{toml_escape(cfg.get("goal", {}).get("title", "Сбор на цель"))}"',
        f"current = {float(cfg.get('goal', {}).get('current', 0.0)):.1f}",
        f"target = {float(cfg.get('goal', {}).get('target', 10000.0)):.1f}",
        f'currency = "{toml_escape(cfg.get("goal", {}).get("currency", "RUB"))}"',
        "",
        "# 6. TEXT-TO-SPEECH (YANDEX ALICE)",
        "[tts]",
        f'mode = "{toml_escape(cfg.get("tts", {}).get("mode", "off"))}"',
        f'voice = "{toml_escape(cfg.get("tts", {}).get("voice", "shitova.us"))}"',
        f'speed = "{toml_escape(cfg.get("tts", {}).get("speed", "1"))}"',
        f'emotion = "{toml_escape(cfg.get("tts", {}).get("emotion", "neutral"))}"',
        f"volume = {float(cfg.get('tts', {}).get('volume', 0.8)):.2f}",
        f"max_length = {int(cfg.get('tts', {}).get('max_length', 200))}",
        f'reward_name = "{toml_escape(cfg.get("tts", {}).get("reward_name", "TTS"))}"',
        f'auth_token = "{toml_escape(cfg.get("tts", {}).get("auth_token", yandex_tts.DEFAULT_AUTH_TOKEN))}"',
        "",
    ]

    # Serialize random_pool as TOML array
    pool = cfg.get("tts", {}).get("random_pool", yandex_tts.DEFAULT_RANDOM_POOL)
    pool_str = ", ".join(f'"{toml_escape(v)}"' for v in pool)
    lines.insert(-1, f"random_pool = [{pool_str}]")

    # Serialize blacklist as TOML array
    blacklist = cfg.get("tts", {}).get("blacklist", [])
    if blacklist:
        bl_str = ", ".join(f'"{toml_escape(w)}"' for w in blacklist)
        lines.insert(-1, f"blacklist = [{bl_str}]")

    # Serialize vip_voices as [tts.vip_voices] sub-table
    vip = cfg.get("tts", {}).get("vip_voices", {})
    if vip:
        lines.append("[tts.vip_voices]")
        for nick, voice in vip.items():
            lines.append(f'{toml_escape(nick)} = "{toml_escape(voice)}"')
        lines.append("")

    # 7. APPEARANCE & THEME PRESET
    lines.append("[appearance]")
    lines.append(f'theme = "{toml_escape(cfg.get("appearance", {}).get("theme", "mocha-teal"))}"')
    lines.append("")

    # 8. SCENE TRANSITIONS
    if "transitions" in cfg:
        tr = cfg["transitions"]
        lines.append("[transitions]")
        lines.append(f'enabled = {str(tr.get("enabled", True)).lower()}')
        lines.append(f'effect = "{toml_escape(tr.get("effect", "doom-melt"))}"')
        lines.append(f'duration_ms = {int(tr.get("duration_ms", 600))}')
        lines.append("")

    # 9. CROSS-PLATFORM MEDIA PLAYER & LYRICS
    if "media" in cfg:
        med = cfg["media"]
        lines.append("[media]")
        lines.append(f'enabled = {str(med.get("enabled", False)).lower()}')
        lines.append(f'player = "{toml_escape(med.get("player", "auto"))}"')
        lines.append(f'auto_pause = {str(med.get("auto_pause", True)).lower()}')
        lines.append(f'show_lyrics = {str(med.get("show_lyrics", True)).lower()}')
        ign = med.get("ignore", ["firefox"])
        ign_str = ", ".join(f'"{toml_escape(x)}"' for x in ign)
        lines.append(f'ignore = [{ign_str}]')
        lines.append(f'youtube_domain = "{toml_escape(med.get("youtube_domain", "youtube-nocookie.com"))}"')
        lines.append("")

    return "\n".join(lines)
