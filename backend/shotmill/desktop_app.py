"""Same-origin local application for the fully installed Windows desktop bundle.

The launcher supplies both directories explicitly. Development environment
variables must not redirect the installed application's database or providers.
"""

from pathlib import Path

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from starlette.responses import FileResponse
from starlette.routing import Route

from shotmill.config import Settings


def create_desktop_app(data_root: Path, frontend_root: Path) -> FastAPI:
    data_root = data_root.resolve()
    frontend_root = frontend_root.resolve(strict=True)
    if not (frontend_root / "index.html").is_file():
        raise ValueError("The bundled frontend is missing index.html")
    if data_root == frontend_root or data_root.is_relative_to(frontend_root):
        raise ValueError("Desktop data must not be stored in the served frontend directory")
    from shotmill.app_factory import create_app

    settings = Settings(
        app_name="ShotMill", api_version="0.3", data_root=data_root,
        database_url=f"sqlite+pysqlite:///{(data_root / 'shotmill.db').as_posix()}",
    )
    application = create_app(settings)
    async def frontend_index(request):
        return FileResponse(frontend_root / "index.html")

    application.router.routes.insert(0, Route(
        "/", frontend_index, methods=["GET", "HEAD"], include_in_schema=False,
    ))
    # API and scoped media routes have already been registered. The immutable
    # packaged frontend is served last; runtime data is never mounted here.
    application.mount("/", StaticFiles(directory=frontend_root, html=True), name="desktop-ui")
    return application
