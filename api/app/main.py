from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse

from app import db
from app.auth import Refusal, refusal_handler
from app.body_limit import BodyLimit
from app.config import Settings
from app.routes import relatorio, saude


async def invalid_request(request, exc) -> JSONResponse:
    # FastAPI's default 422 echoes the input back; the session holds hostname and paths.
    return JSONResponse({"erro": "requisicao_invalida"}, 422)


def create_app(settings: Settings | None = None, ia_transport=None) -> FastAPI:
    """ia_transport: httpx transport for the OpenCode Go client; tests pass a mock, production None."""
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
    app.state.ia_transport = ia_transport
    app.add_middleware(BodyLimit, max_bytes=settings.max_body_bytes)
    app.add_exception_handler(Refusal, refusal_handler)
    app.add_exception_handler(RequestValidationError, invalid_request)
    app.include_router(saude.router)
    app.include_router(relatorio.router)
    return app
