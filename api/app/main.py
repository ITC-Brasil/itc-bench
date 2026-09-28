from contextlib import asynccontextmanager

from fastapi import FastAPI

from app import db
from app.config import Settings


def create_app(settings: Settings | None = None) -> FastAPI:
    # Settings are loaded here, so a forbidden model (ADR-011) stops the container at startup.
    settings = settings or Settings()

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        db.migrate(settings.database_path)
        yield

    docs = settings.app_enable_docs
    app = FastAPI(
        title="Técnico Assistente",
        docs_url="/docs" if docs else None,
        redoc_url="/redoc" if docs else None,
        openapi_url="/openapi.json" if docs else None,
        lifespan=lifespan,
    )
    app.state.settings = settings
    return app
