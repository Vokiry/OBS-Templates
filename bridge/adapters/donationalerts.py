import asyncio
import json
import logging
from pathlib import Path
import aiohttp
import websockets

log = logging.getLogger("bridge.donationalerts")

USER_API = "https://www.donationalerts.com/api/v1/user/oauth"
SUBSCRIBE_API = "https://www.donationalerts.com/api/v1/centrifuge/subscribe"
TOKEN_API = "https://www.donationalerts.com/oauth/token"
WS_URL = "wss://centrifugo.donationalerts.com/connection/websocket"

TOKEN_FILE = Path(__file__).parent.parent / ".da_token.json"


def normalize_donation(data: dict) -> dict:
    username = data.get("username") or data.get("name") or "anonymous"
    amount = data.get("amount") or data.get("amount_formatted") or ""
    currency = data.get("currency", "")
    message = (data.get("message") or "").strip()
    amount_str = f"{amount} {currency}".strip()
    body = f"{username} · {amount_str}".strip(" ·")
    return {
        "kind": "donate",
        "user": username,
        "amount": amount_str,
        "message": message,
        "body": body,
    }


async def exchange_da_code(client_id: str, client_secret: str, redirect_uri: str, code: str) -> dict:
    async with aiohttp.ClientSession() as session:
        data = {
            "grant_type": "authorization_code",
            "client_id": client_id,
            "client_secret": client_secret,
            "redirect_uri": redirect_uri,
            "code": code,
        }
        async with session.post(TOKEN_API, data=data) as resp:
            text = await resp.text()
            if resp.status != 200:
                log.error("DonationAlerts token exchange failed (HTTP %s): %s", resp.status, text)
                raise ValueError(f"DonationAlerts error ({resp.status}): {text}")
            tokens = json.loads(text)
            with open(TOKEN_FILE, "w", encoding="utf-8") as f:
                json.dump(tokens, f)
            log.info("donationalerts tokens saved to %s", TOKEN_FILE)
            return tokens


async def refresh_da_token(client_id: str, client_secret: str, refresh_token: str) -> dict:
    async with aiohttp.ClientSession() as session:
        data = {
            "grant_type": "refresh_token",
            "client_id": client_id,
            "client_secret": client_secret,
            "refresh_token": refresh_token,
            "scope": "oauth-user-show oauth-donation-subscribe",
        }
        async with session.post(TOKEN_API, data=data) as resp:
            resp.raise_for_status()
            tokens = await resp.json()
            with open(TOKEN_FILE, "w", encoding="utf-8") as f:
                json.dump(tokens, f)
            log.info("donationalerts tokens refreshed and saved")
            return tokens


class DonationAlertsAdapter:
    def __init__(self, token: str, broadcast):
        self.token = token.strip()
        self.broadcast = broadcast
        self.channel = None

    async def get_user_info(self) -> tuple[int, str]:
        headers = {"Authorization": f"Bearer {self.token}"}
        async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=10)) as session:
            async with session.get(USER_API, headers=headers) as resp:
                if resp.status == 401:
                    raise ValueError("DonationAlerts access token is invalid or expired (HTTP 401)")
                resp.raise_for_status()
                data = await resp.json()
        
        user_data = data.get("data", {})
        user_id = user_data.get("id")
        socket_token = user_data.get("socket_connection_token") or self.token
        if not user_id:
            raise ValueError(f"Could not get user ID from DonationAlerts API: {data}")
        return user_id, socket_token

    async def run(self) -> None:
        user_id, socket_token = await self.get_user_info()
        self.channel = f"$alerts:donation_{user_id}"
        log.info("donationalerts authenticated (user_id: %s, channel: %s)", user_id, self.channel)

        async with websockets.connect(WS_URL) as ws:
            # 1. Connect to Centrifugo with socket_connection_token
            await ws.send(json.dumps({
                "params": {"token": socket_token},
                "id": 1,
            }))

            client = None
            for _ in range(5):
                raw = await ws.recv()
                reply = json.loads(raw)
                result = reply.get("result") or reply.get("data")
                if isinstance(result, dict) and "client" in result:
                    client = result["client"]
                    break

            if not client:
                raise ValueError("Could not get Centrifugo client ID from handshake response")

            log.info("donationalerts centrifugo connected (client: %s)", client)

            # 2. Subscribe to user channel via REST API
            await self._subscribe_channel(ws, client)

            # 3. Listen to incoming events
            async for raw in ws:
                try:
                    msg = json.loads(raw)
                    await self._handle(msg)
                except Exception as e:
                    log.warning("error parsing donationalerts message: %s", e)

    async def _subscribe_channel(self, ws, client: str) -> None:
        async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=10)) as session:
            async with session.post(
                SUBSCRIBE_API,
                headers={"Authorization": f"Bearer {self.token}"},
                json={"client": client, "channels": [self.channel]},
            ) as resp:
                resp.raise_for_status()
                payload = await resp.json()

        channels = payload.get("channels", [])
        for ch in channels:
            await ws.send(json.dumps({
                "params": {
                    "channel": ch["channel"],
                    "token": ch["token"],
                },
                "method": 1,
                "id": 2,
            }))
            log.info("donationalerts subscribed to %s", ch["channel"])

    async def _handle(self, message: dict) -> None:
        data_container = (
            (message.get("result") or {}).get("data")
            or (message.get("push") or {}).get("data")
            or message.get("data")
        )
        if not data_container:
            return

        if isinstance(data_container, str):
            try:
                data_container = json.loads(data_container)
            except Exception:
                pass

        if not isinstance(data_container, dict):
            return

        donation = data_container.get("data") or data_container
        if isinstance(donation, str):
            try:
                donation = json.loads(donation)
            except Exception:
                pass

        if not isinstance(donation, dict) or not (donation.get("amount") or donation.get("username") or donation.get("name")):
            return

        log.info("donationalerts donation received from %s", donation.get("username") or donation.get("name"))
        await self.broadcast(normalize_donation(donation))


async def run(config: dict, broadcast) -> None:
    token = config.get("access_token", "").strip()
    client_id = str(config.get("client_id", "")).strip()
    client_secret = str(config.get("client_secret", "")).strip()

    # Detect if user pasted 40-char client_secret into access_token field:
    if not client_secret and len(token) == 40 and not token.startswith("eyJ"):
        client_secret = token
        token = ""

    while True:
        try:
            current_token = token
            if not current_token and TOKEN_FILE.exists():
                try:
                    with open(TOKEN_FILE, "r", encoding="utf-8") as f:
                        cached = json.load(f)
                        current_token = cached.get("access_token", "")
                except Exception:
                    pass

            if not current_token:
                if client_id and client_secret:
                    redirect_uri = "http://localhost:8787/api/da/callback"
                    auth_url = (
                        f"https://www.donationalerts.com/oauth/authorize?"
                        f"client_id={client_id}&redirect_uri={redirect_uri}&response_type=code&"
                        f"scope=oauth-user-show%20oauth-donation-subscribe"
                    )
                    log.warning(
                        "\n========================================================================\n"
                        "[!] DonationAlerts требует подтверждения авторизации!\n"
                        "    Открой эту ссылку в браузере:\n"
                        "    %s\n"
                        "========================================================================",
                        auth_url
                    )
                    try:
                        import subprocess, shutil
                        if shutil.which("xdg-open"):
                            subprocess.Popen(["xdg-open", auth_url], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
                        else:
                            import webbrowser
                            webbrowser.open(auth_url)
                    except Exception:
                        pass
                else:
                    log.warning(
                        "donationalerts: укажите client_id и client_secret (или access_token) в config.toml"
                    )
                await asyncio.sleep(15)
                continue

            adapter = DonationAlertsAdapter(current_token, broadcast)
            await adapter.run()

        except asyncio.CancelledError:
            raise
        except Exception as exc:
            # Handle token expiry by attempting refresh
            if "401" in str(exc) and client_id and client_secret and TOKEN_FILE.exists():
                try:
                    with open(TOKEN_FILE, "r", encoding="utf-8") as f:
                        cached = json.load(f)
                    ref = cached.get("refresh_token")
                    if ref:
                        log.info("donationalerts: refreshing expired access token...")
                        await refresh_da_token(client_id, client_secret, ref)
                        continue
                except Exception as ref_err:
                    log.warning("donationalerts: could not refresh token: %s", ref_err)
                    TOKEN_FILE.unlink(missing_ok=True)

            log.warning("donationalerts connection error (%s), retrying in 10s...", exc)
            await asyncio.sleep(10)
