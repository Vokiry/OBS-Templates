"""System Doctor diagnostic service."""

from pathlib import Path


def collect_doctor_diagnostics(
    config: dict,
    broadcaster,
    project_root: Path,
    src_dir: Path,
    adapter_mgr=None,
    adapter_states=None,
) -> dict:
    """Collect runtime diagnostic health report for all system modules."""
    server_cfg = config.get("server", {})
    tc_cfg = config.get("twitch_chat", {})
    tw_cfg = config.get("twitch", {})
    da_cfg = config.get("donationalerts", {})
    dx_cfg = config.get("donatex", {})
    tts_cfg = config.get("tts", {})
    goal_cfg = config.get("goal", {})

    from adapters.twitch_chat import get_cached_badges

    cached_badges = get_cached_badges()
    has_twitch_token = (project_root / "bridge" / ".twitch_token.json").exists()
    has_da_token = (project_root / "bridge" / ".da_token.json").exists()

    sounds_dir = src_dir / "sounds"
    sounds_count = (
        len(list(sounds_dir.glob("*.wav"))) + len(list(sounds_dir.glob("*.mp3")))
        if sounds_dir.exists()
        else 0
    )
    states = adapter_mgr.states if adapter_mgr else (adapter_states or {})

    return {
        "status": "ok",
        "server": {
            "host": server_cfg.get("host", "127.0.0.1"),
            "port": int(server_cfg.get("port", 8787)),
        },
        "overlays": {"count": len(broadcaster.clients)},
        "twitch_chat": {
            "enabled": bool(tc_cfg.get("enabled")),
            "channel": tc_cfg.get("channel", "").strip(),
            "connected": states.get("twitch_chat", False),
            "badges_count": len(cached_badges) if cached_badges else 0,
            "emotes_count": len(broadcaster.last_7tv_emotes.get("emotes", []))
            if broadcaster.last_7tv_emotes
            else 0,
            "fade_seconds": int(tc_cfg.get("fade_seconds", 45)),
        },
        "twitch": {
            "enabled": bool(tw_cfg.get("enabled")),
            "configured": bool(tw_cfg.get("client_id") and tw_cfg.get("client_secret")),
            "authenticated": has_twitch_token,
        },
        "donationalerts": {
            "enabled": bool(da_cfg.get("enabled")),
            "configured": bool(da_cfg.get("client_id")),
            "authenticated": has_da_token or bool(da_cfg.get("access_token")),
        },
        "donatex": {
            "enabled": bool(dx_cfg.get("enabled")),
            "configured": bool(dx_cfg.get("token")),
            "connected": states.get("donatex", False),
        },
        "sounds": {
            "count": sounds_count,
            "master_volume": broadcaster.last_sounds_config.get("masterVolume", 0.7)
            if broadcaster.last_sounds_config
            else 0.7,
        },
        "tts": {
            "mode": tts_cfg.get("mode", "off"),
            "voice": tts_cfg.get("voice", "shitova.us"),
            "volume": float(tts_cfg.get("volume", 0.8)),
        },
        "goal": {
            "enabled": bool(goal_cfg.get("enabled")),
            "title": goal_cfg.get("title", ""),
            "current": float(goal_cfg.get("current", 0)),
            "target": float(goal_cfg.get("target", 10000)),
        },
        "stream_stats": broadcaster.last_stream_stats,
    }
