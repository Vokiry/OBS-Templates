"""External OAuth and authorization callback endpoints."""

import html as html_mod
import logging

from aiohttp import web

log = logging.getLogger("bridge.routes.auth")


def register_auth_routes(app: web.Application, config: dict, enable_settings: bool) -> None:
    """Register DonationAlerts OAuth and Twitch badge endpoints."""

    if enable_settings:

        async def da_auth_url_handler(request: web.Request) -> web.Response:
            da_cfg = config.get("donationalerts", {})
            cid = str(da_cfg.get("client_id", "")).strip()
            redirect_uri = "http://localhost:8787/api/da/callback"
            url = (
                f"https://www.donationalerts.com/oauth/authorize?"
                f"client_id={cid}&redirect_uri={redirect_uri}&response_type=code&"
                f"scope=oauth-user-show%20oauth-donation-subscribe"
            )
            return web.json_response({"url": url}, headers={"Access-Control-Allow-Origin": "*"})

        app.router.add_get("/api/da/auth-url", da_auth_url_handler)

    async def da_callback_handler(request: web.Request) -> web.Response:
        code = request.query.get("code")
        if not code:
            error = (
                request.query.get("error_description")
                or request.query.get("error")
                or "Код авторизации не найден"
            )
            log.error("DonationAlerts OAuth error: %s", error)
            safe_error = html_mod.escape(str(error))
            return web.Response(
                text=f"<h1>[ SYSTEM ]</h1><p style='font-family: monospace;'>Ошибка от DonationAlerts: {safe_error}</p>",
                content_type="text/html",
                status=400,
            )

        da_cfg = config.get("donationalerts", {})
        client_id = str(da_cfg.get("client_id", "")).strip()
        client_secret = str(da_cfg.get("client_secret", "")).strip()
        if not client_secret:
            raw_token = str(da_cfg.get("access_token", "")).strip()
            if len(raw_token) == 40 and not raw_token.startswith("eyJ"):
                client_secret = raw_token

        if not client_id or not client_secret:
            log.error("DonationAlerts missing client_id or client_secret")
            return web.Response(
                text="<h1>[ SYSTEM ]</h1><p style='font-family: monospace;'>Ошибка: укажите client_id и client_secret в bridge/config.toml</p>",
                content_type="text/html",
                status=400,
            )

        from adapters.donationalerts import exchange_da_code

        try:
            redirect_uri = "http://localhost:8787/api/da/callback"
            await exchange_da_code(client_id, client_secret, redirect_uri, code)
            return web.Response(
                text=(
                    "<!DOCTYPE html><html><head><meta charset='utf-8'><title>SYSTEM // DA OK</title></head>"
                    "<body style='background:#0B0F14;color:#63E6BE;font-family:monospace;padding:40px;text-align:center;'>"
                    "<h1>[ SYSTEM // DONATIONALERTS CONNECTED ]</h1>"
                    "<p style='color:#E8EEF2;'>DonationAlerts успешно авторизован! Окно можно закрыть, мост уже подключился.</p>"
                    "</body></html>"
                ),
                content_type="text/html",
            )
        except Exception as e:
            log.error("DonationAlerts auth callback error: %s", e)
            safe_err = html_mod.escape(str(e))
            return web.Response(
                text=(
                    f"<!DOCTYPE html><html><head><meta charset='utf-8'><title>SYSTEM // DA ERROR</title></head>"
                    f"<body style='background:#0B0F14;color:#E5484D;font-family:monospace;padding:40px;'>"
                    f"<h1>[ Ошибка авторизации DonationAlerts ]</h1>"
                    f"<p style='color:#E8EEF2;'>{safe_err}</p>"
                    f"</body></html>"
                ),
                content_type="text/html",
                status=500,
            )

    async def get_twitch_badges_handler(request: web.Request) -> web.Response:
        from adapters.twitch_chat import get_cached_badges

        badges = get_cached_badges()
        return web.json_response(badges, headers={"Access-Control-Allow-Origin": "*"})

    app.router.add_get("/api/da/callback", da_callback_handler)
    app.router.add_get("/api/twitch/badges", get_twitch_badges_handler)
