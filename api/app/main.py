import asyncio
import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse

from app import db, tarefas
from app.auth import Refusal, refusal_handler
from app.body_limit import BodyLimit
from app.config import Settings
from app.routes import bench, bench_relatorio, bench_versao, cadastros, relatorio, saude
from app.services import glpi, nocodb

log = logging.getLogger("tecnico")


async def invalid_request(request, exc) -> JSONResponse:
    # FastAPI's default 422 echoes the input back; the session holds hostname and paths.
    return JSONResponse({"erro": "requisicao_invalida"}, 422)


def create_app(settings: Settings | None = None, transports: dict | None = None, em_segundo_plano=tarefas.em_thread) -> FastAPI:
    """transports: httpx transports by service ("ia", "nocodb", "ntfy", "glpi", "nocodb_cadastros"); tests pass mocks,
    production none. em_segundo_plano: how off-request work runs; tests run it inline."""
    # Settings are loaded here, so a forbidden model (ADR-011) stops the container at startup.
    settings = settings or Settings()

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        db.migrate(settings.database_path)
        if settings.glpi_url and not glpi.url_interna(settings.glpi_url):
            # ADR-013: GLPI 11 has no HTTPS; the password must not cross the internet in clear.
            log.error("GLPI_URL recusada: http:// só para host interno; login do Bench responde 503")
        repetir = asyncio.create_task(repetir_espelho(app)) if nocodb.configurado(settings) else None
        yield
        if repetir:
            repetir.cancel()

    docs = settings.app_enable_docs
    app = FastAPI(
        title="Técnico Assistente",
        docs_url="/docs" if docs else None,
        redoc_url="/redoc" if docs else None,
        openapi_url="/openapi.json" if docs else None,
        lifespan=lifespan,
    )
    app.state.settings = settings
    app.state.transports = transports or {}
    app.state.em_segundo_plano = em_segundo_plano
    app.state.cadastros = cadastros.Copia()
    app.state.chave_versao = cadastros.chave_versao(settings)
    app.add_middleware(BodyLimit, max_bytes=settings.max_body_bytes)
    app.add_exception_handler(Refusal, refusal_handler)
    app.add_exception_handler(RequestValidationError, invalid_request)
    app.include_router(saude.router)
    app.include_router(relatorio.router)
    app.include_router(bench.router)
    app.include_router(cadastros.router)
    app.include_router(bench_relatorio.router)
    app.include_router(bench_versao.router)
    return app


async def repetir_espelho(app: FastAPI) -> None:
    """Resend pending mirrors every NOCODB_RETRY_SECONDS, also when no new report arrives."""
    settings = app.state.settings
    while True:
        await asyncio.sleep(settings.nocodb_retry_seconds)
        try:
            await asyncio.to_thread(nocodb.espelhar_pendentes, settings, app.state.transports.get("nocodb"))
        except Exception:
            log.exception("reenvio do espelho falhou")
