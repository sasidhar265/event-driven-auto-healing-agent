from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI
from fastapi.responses import RedirectResponse
from fastapi.staticfiles import StaticFiles
from sqlalchemy import text
from sqlalchemy.engine import make_url
from sqlalchemy.exc import SQLAlchemyError

from app.api import integration_router, internal_router, operations_router
from app.art_api import router as art_router
from app.config import get_settings
from app.db import engine
from app.runtime_config import get_runtime_rules


@asynccontextmanager
async def lifespan(_: FastAPI):
    """Release the shared PostgreSQL connection pool when FastAPI stops."""
    yield
    await engine.dispose()


def create_application(api_profile: str | None = None) -> FastAPI:
    """Build an application exposing only the routes needed by its deployment."""

    get_runtime_rules()
    profile = api_profile or get_settings().api_profile
    application = FastAPI(
        title="Auto-Healing Suggestion Agent Runtime",
        version=get_settings().app_version,
        lifespan=lifespan,
    )
    application.include_router(operations_router)
    if profile in {"integration", "full"}:
        application.include_router(integration_router)
    if profile in {"admin", "full"}:
        application.include_router(internal_router)
        application.include_router(art_router)
    application.mount(
        "/ui",
        StaticFiles(directory=Path(__file__).parent / "static", html=True),
        name="ui",
    )

    @application.get("/", include_in_schema=False)
    async def root() -> RedirectResponse:
        """Redirect the service root to the bundled operations console."""
        return RedirectResponse("/ui/")

    @application.get("/health/live")
    async def live() -> dict[str, object]:
        """Report service configuration and verify PostgreSQL with a lightweight query."""
        settings = get_settings()
        database_url = make_url(settings.database_url)
        database_status = "connected"
        try:
            async with engine.connect() as connection:
                await connection.execute(text("SELECT 1"))
        except SQLAlchemyError:
            database_status = "unavailable"
        return {
            "status": "ok",
            "service": settings.service_name,
            "api_profile": profile,
            "database": {
                "status": database_status,
                "engine": database_url.get_backend_name(),
                "host": database_url.host or "local socket",
                "port": database_url.port,
                "name": database_url.database,
                "username": database_url.username,
            },
        }

    return application


app = create_application()
