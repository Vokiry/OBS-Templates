"""Adapter process supervisor with hot-reloading support."""

import asyncio
import logging

log = logging.getLogger("bridge.adapter_manager")


async def watch(name: str, coro) -> None:
    """Supervise an adapter coroutine, catching errors and preventing crashes."""
    try:
        await coro
    except asyncio.CancelledError:
        pass
    except Exception:
        log.exception("adapter %r failed", name)


class AdapterManager:
    """Manages adapter lifecycles with hot-reloading support."""

    def __init__(self, broadcast):
        self.broadcast = broadcast
        self.tasks: dict[str, asyncio.Task] = {}
        self.configs: dict[str, dict] = {}
        self.states: dict[str, bool] = {
            "twitch": False,
            "twitch_chat": False,
            "donationalerts": False,
            "donatex": False,
        }

    def _prepare_sections(self, full_config: dict) -> dict[str, tuple[str, dict]]:
        tc_cfg = dict(full_config.get("twitch_chat", {}))
        tw_cfg = full_config.get("twitch", {})
        if tw_cfg.get("client_id") and not tc_cfg.get("client_id"):
            tc_cfg["client_id"] = tw_cfg["client_id"]
            tc_cfg["client_secret"] = tw_cfg.get("client_secret", "")

        return {
            "twitch": ("adapters.twitch", dict(full_config.get("twitch", {}))),
            "twitch_chat": ("adapters.twitch_chat", tc_cfg),
            "donationalerts": ("adapters.donationalerts", dict(full_config.get("donationalerts", {}))),
            "donatex": ("adapters.donatex", dict(full_config.get("donatex", {}))),
        }

    async def start_all(self, full_config: dict) -> None:
        """Start all enabled adapters as supervised background tasks."""
        sections = self._prepare_sections(full_config)
        for name, (module_path, section) in sections.items():
            self.configs[name] = dict(section)
            enabled = bool(section.get("enabled"))
            self.states[name] = enabled
            if not enabled:
                continue
            log.info("starting adapter: %s", name)
            module = __import__(module_path, fromlist=["run"])
            self.tasks[name] = asyncio.create_task(watch(name, module.run(section, self.broadcast)))

    async def restart_adapter(self, name: str, module_path: str, section: dict) -> None:
        """Cancel an existing adapter task and start a new instance with updated config."""
        if name in self.tasks:
            t = self.tasks.pop(name)
            t.cancel()
            try:
                await asyncio.wait_for(t, timeout=2.0)
            except (asyncio.CancelledError, asyncio.TimeoutError, Exception):
                pass

        self.configs[name] = dict(section)
        enabled = bool(section.get("enabled"))
        self.states[name] = enabled
        if enabled:
            log.info("hot-reloading adapter: %s", name)
            module = __import__(module_path, fromlist=["run"])
            self.tasks[name] = asyncio.create_task(watch(name, module.run(section, self.broadcast)))
        else:
            log.info("adapter %s disabled", name)

    async def reload_if_changed(self, full_config: dict) -> None:
        """Compare config with active adapters and hot-reload any sections that changed."""
        sections = self._prepare_sections(full_config)
        for name, (module_path, section) in sections.items():
            if section != self.configs.get(name):
                await self.restart_adapter(name, module_path, section)

    async def stop_all(self) -> None:
        """Gracefully cancel and stop all running adapter tasks."""
        for t in self.tasks.values():
            t.cancel()
        if self.tasks:
            try:
                await asyncio.wait_for(
                    asyncio.gather(*self.tasks.values(), return_exceptions=True),
                    timeout=2.0,
                )
            except (asyncio.TimeoutError, Exception):
                pass
        self.tasks.clear()
