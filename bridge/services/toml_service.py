"""TOML serialization and escaping service."""

from services import yandex_tts


def toml_escape(val) -> str:
    """Escape string values for safe inclusion in TOML."""
    if val is None:
        return ""
    return str(val).replace("\\", "\\\\").replace('"', '\\"').replace("\n", "").replace("\r", "")


def serialize_toml(cfg: dict) -> str:
    """Serialize configuration dictionary to strict TOML format."""
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

    return "\n".join(lines)
