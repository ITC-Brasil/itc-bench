"""Bench update (ADR-026, TA-ADR-033): newest published version and its installer.

GET /v1/bench/versao: 200 with the signed manifest of the newest version not revoked, or 204.
GET /v1/bench/versao/arquivo?sha256=...: the installer of that version, only while it is the
one being served. No extension in the path and Cache-Control: no-store, so the Cloudflare edge
never stores it. Range is answered by Starlette's FileResponse (206); a resume (Range from
byte > 0) counts apart from a download from the start, so resumes do not eat the download limit.
"""

import re
from pathlib import Path

from fastapi import APIRouter, Depends, Query, Request, Response
from fastapi.responses import FileResponse, JSONResponse

from app import db
from app.auth import Refusal, exigir_sessao, utcnow

router = APIRouter(prefix="/v1/bench")
SEM_CACHE = {"Cache-Control": "no-store"}
INICIO_RANGE = re.compile(r"bytes=(\d+)-")

COUNT = (
    "INSERT INTO bench_versao_uso (usuario, tipo, janela, contagem) VALUES (?, ?, ?, 1)"
    " ON CONFLICT (usuario, tipo) DO UPDATE SET"
    " contagem = CASE WHEN janela = excluded.janela THEN contagem + 1 ELSE 1 END,"
    " janela = excluded.janela"
    " RETURNING contagem"
)


def limitar(settings, usuario: str, tipo: str, limite: int) -> None:
    agora = utcnow()
    conn = db.connect(settings.database_path)
    try:
        with db.immediate(conn):
            contagem = conn.execute(COUNT, (usuario, tipo, agora.strftime("%Y-%m-%dT%H"))).fetchone()[0]
    finally:
        conn.close()
    if contagem > limite:
        raise Refusal(429, "limite_excedido", {"Retry-After": str(3600 - (agora.minute * 60 + agora.second))})


def atual(settings) -> tuple | None:
    conn = db.connect(settings.database_path)
    try:
        return conn.execute(
            "SELECT versao, minima, sha256, tamanho, notas, manifesto, assinatura FROM bench_versoes"
            " WHERE revogado_em IS NULL ORDER BY ordem DESC LIMIT 1"
        ).fetchone()
    finally:
        conn.close()


@router.get("/versao")
def versao(request: Request, sessao: dict = Depends(exigir_sessao)):
    settings = request.app.state.settings
    limitar(settings, sessao["usuario"], "consulta", settings.bench_versao_consultas_hora)
    linha = atual(settings)
    if linha is None:
        return Response(status_code=204, headers=SEM_CACHE)
    campos = ("versao", "minima", "sha256", "tamanho", "notas", "manifesto", "assinatura")
    return JSONResponse(dict(zip(campos, linha, strict=True)), headers=SEM_CACHE)


@router.get("/versao/arquivo")
def arquivo(
    request: Request,
    sha256: str = Query(pattern=r"^[0-9a-f]{64}$"),
    sessao: dict = Depends(exigir_sessao),
):
    settings = request.app.state.settings
    linha = atual(settings)
    if linha is None or linha[2] != sha256:
        raise Refusal(404, "versao_indisponivel")
    m = INICIO_RANGE.match(request.headers.get("range", ""))
    if m and int(m.group(1)) > 0:
        limitar(settings, sessao["usuario"], "retomada", settings.bench_versao_retomadas_hora)
    else:
        limitar(settings, sessao["usuario"], "download", settings.bench_versao_downloads_hora)
    caminho = Path(settings.bench_versoes_dir) / f"setup-{sha256}.exe"
    if not caminho.is_file():
        raise Refusal(404, "versao_indisponivel")
    return FileResponse(caminho, media_type="application/octet-stream", headers=SEM_CACHE)
