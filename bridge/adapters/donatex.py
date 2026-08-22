import asyncio
import logging

log = logging.getLogger("bridge.donatex")


async def run(config: dict, broadcast) -> None:
    log.warning(
        "donatex adapter is a stub: realtime transport is SignalR, "
        "endpoint details must be verified against donatex.gg/api-docs"
    )
    while True:
        await asyncio.sleep(3600)
