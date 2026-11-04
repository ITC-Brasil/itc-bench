"""GET /v1/bench/cadastros (ADR-014): the four NocoDB cadastros for a signed-in technician.

In-memory copy with a TTL; one NocoDB read at a time (the others get the copy, and wait only
when there is none). NocoDB down: the last copy goes out with defasado=true for up to 24 h.
Nothing of the cadastros is written to SQLite; the audit keeps who, when and 12 characters of
the version. The version is an HMAC with a server key: the content holds secrets.
"""

import hashlib
import hmac
import json
import logging
import secrets
import threading
import time

from fastapi import APIRouter, Depends, Query, Request, Response
from pydantic import SecretStr

from app.auth import Refusal, exigir_sessao, iso, utcnow
from app.routes.bench import RETENCAO, gravar
from app.services import nocodb_cadastros

log = logging.getLogger("tecnico.cadastros")
router = APIRouter(prefix="/v1/bench")
DEFASAGEM_MAXIMA = 24 * 3600
VERSAO_LOG = 12


class Copia:
    """Last good read of NocoDB, per app. tentado: when the last read started (monotonic)."""

    def __init__(self):
        self.lock = threading.Lock()
        self.dados = None
        self.lido_mono = 0.0
        self.lido_em = ""
        self.tentado = None
        self.falhou = False


def chave_versao(settings) -> bytes:
    chave = settings.bench_cadastros_etag_key.get_secret_value().strip()
    return chave.encode() if chave else secrets.token_bytes(32)


def obter(request: Request) -> tuple[dict, str, bool]:
    """(cadastros, lido_em, defasado) or 503 cadastros_indisponivel."""
    app = request.app
    settings, copia = app.state.settings, app.state.cadastros
    if not nocodb_cadastros.configurado(settings):
        raise Refusal(503, "cadastros_indisponivel")
    ttl = settings.nocodb_cadastros_ttl_seconds
    if copia.dados is None or time.monotonic() - copia.tentado >= ttl:
        # Without a copy, wait for whoever is reading; with one, take it and let them read.
        # After the wait, a read that just failed is not repeated within the TTL.
        if copia.lock.acquire(blocking=copia.dados is None):
            try:
                if copia.tentado is None or time.monotonic() - copia.tentado >= ttl:
                    renovar(app, copia)
            finally:
                copia.lock.release()
    if copia.dados is None or time.monotonic() - copia.lido_mono > DEFASAGEM_MAXIMA:
        raise Refusal(503, "cadastros_indisponivel")
    return copia.dados, copia.lido_em, copia.falhou


def renovar(app, copia: Copia) -> None:
    copia.tentado = time.monotonic()
    try:
        dados = nocodb_cadastros.ler(app.state.settings, app.state.transports.get("nocodb_cadastros"))
    except nocodb_cadastros.NocodbIndisponivel as erro:
        copia.falhou = True
        log.warning("leitura dos cadastros no NocoDB falhou (%s); copia em memoria: %s", erro.code, copia.dados is not None)
        return
    copia.dados, copia.lido_mono, copia.lido_em, copia.falhou = dados, copia.tentado, iso(utcnow()), False
    log.info(
        "cadastros lidos do NocoDB: %s",
        ", ".join(f"{nome} {len(dados[nome])}" for nome in ("servidores", "instaladores", "wifi", "unidades")),
    )


def revelar(valor):
    if isinstance(valor, SecretStr):
        return valor.get_secret_value()
    if isinstance(valor, list):
        return [revelar(item) for item in valor]
    if isinstance(valor, dict):
        return {chave: revelar(item) for chave, item in valor.items()}
    return valor


def etags(cabecalho: str) -> set[str]:
    """If-None-Match: one or more quoted tags, weak or not."""
    return {parte.strip().removeprefix("W/").strip('"') for parte in cabecalho.split(",") if parte.strip()}


@router.get("/cadastros")
def cadastros(
    request: Request,
    unidade: str | None = Query(None, min_length=1, max_length=32),
    sessao: dict = Depends(exigir_sessao),
):
    dados, lido_em, defasado = obter(request)
    codigos = {u["codigo"] for u in dados["unidades"]}
    if unidade is not None and unidade.strip() not in codigos:
        raise Refusal(422, "unidade_invalida")
    unidade = unidade.strip() if unidade else None
    wifi = [rede for rede in dados["wifi"] if unidade is None or rede["unidade"] == unidade]
    conteudo = revelar(
        {
            "unidade": unidade,
            "servidores": dados["servidores"],
            "instaladores": dados["instaladores"],
            "wifi": wifi,
            "unidades": dados["unidades"],
        }
    )
    canonico = json.dumps(conteudo, sort_keys=True, ensure_ascii=False, separators=(",", ":")).encode()
    versao = hmac.new(request.app.state.chave_versao, canonico, hashlib.sha256).hexdigest()
    cabecalhos = {"ETag": f'"{versao}"', "Cache-Control": "no-store"}
    if versao in etags(request.headers.get("if-none-match", "")):
        return Response(status_code=304, headers=cabecalhos)

    quando = iso(utcnow())
    gravar(
        request.app.state.settings,
        (
            "INSERT INTO bench_cadastros_entregas (sessao_id, usuario, unidade, quando, versao) VALUES (?, ?, ?, ?, ?)",
            (sessao["id"], sessao["usuario"], unidade, quando, versao[:VERSAO_LOG]),
        ),
        ("DELETE FROM bench_cadastros_entregas WHERE quando < strftime('%Y-%m-%dT%H:%M:%SZ', 'now', ?)", (RETENCAO,)),
    )
    log.info("cadastros entregues a %s (unidade %s, versao %s, defasado %s)", sessao["usuario"], unidade or "-", versao[:VERSAO_LOG], defasado)
    corpo = {
        "versao": versao,
        "lido_em": lido_em,
        "defasado": defasado,
        **conteudo,
        "descartados": dados["descartados"],
    }
    return Response(
        json.dumps(corpo, ensure_ascii=False), media_type="application/json", headers=cabecalhos
    )
