"""Static files and redirection routes."""

from pathlib import Path

from aiohttp import web


def redirect_with_query(request: web.Request, target: str):
    query = request.query_string
    raise web.HTTPFound(f"{target}?{query}" if query else target)


async def root_redirect(request: web.Request):
    redirect_with_query(request, "/dock")


async def dock_redirect(request: web.Request):
    redirect_with_query(request, "/src/dock/index.html")


async def settings_redirect(request: web.Request):
    redirect_with_query(request, "/src/settings/index.html")


async def panels_redirect(request: web.Request):
    redirect_with_query(request, "/src/panels/index.html")


def register_static_routes(app: web.Application, src_dir: Path, enable_settings: bool) -> None:
    """Register top-level browser redirects and static directory mount."""
    app.router.add_get("/", root_redirect)
    app.router.add_get("/dock", dock_redirect)
    app.router.add_get("/panels", panels_redirect)
    if enable_settings:
        app.router.add_get("/settings", settings_redirect)

    if src_dir.exists():
        app.router.add_static("/src", path=str(src_dir))
