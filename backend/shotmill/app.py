"""Development/server ASGI entry point; desktop builds use the explicit factory."""

from shotmill.app_factory import create_app

__all__ = ["app", "create_app"]

app = create_app()
