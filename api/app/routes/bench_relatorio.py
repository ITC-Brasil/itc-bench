"""Bench diagnostics with the technician session (ADR-016, TA-ADR-028).

POST /v1/bench/relatorio: same normalization, prompt and AI call as /v1/relatorio, with a limit
per technician and idempotency per envio_id: the tunnel cuts at ~100 s and the Bench resends
the same envio_id, which returns the stored report, retries the AI on the same row, or gets
409 while another request is still waiting for the AI. GET /v1/bench/historico/{hostname}: any
technician with a session reads any hostname, as a carreta does (risk accepted in ADR-016).
"""

import json
import logging
from datetime import datetime, timedelta
from uuid import UUID

from fastapi import APIRouter, Depends, Path, Request
from pydantic import Field, field_validator

from app import db, normalizacao, tarefas
from app.auth import Refusal, exigir_sessao, iso, utcnow
from app.routes import cadastros
from app.routes.relatorio import HISTORICO_PROMPT, HISTORICO_ROTA, HOSTNAME, Entrada, gerar_laudo, historico

log = logging.getLogger("tecnico.bench")
router = APIRouter(prefix="/v1/bench")
CARRETA = "BANCADA"
PROCESSANDO_SEGUNDOS = 120

COUNT = (
    "INSERT INTO bench_relatorio_uso (usuario, janela, contagem) VALUES (?, ?, 1)"
    " ON CONFLICT (usuario) DO UPDATE SET"
    " contagem = CASE WHEN janela = excluded.janela THEN contagem + 1 ELSE 1 END,"
    " janela = excluded.janela"
    " RETURNING contagem"
)


class EntradaBench(Entrada):
    envio_id: str
    unidade: str | None = Field(None, max_length=32)

    @field_validator("envio_id")
    @classmethod
    def uuid(cls, valor: str) -> str:
        return str(UUID(valor))  # ValueError -> 422; canonical form for the UNIQUE column


def limitar(settings, usuario: str) -> None:
    agora = utcnow()
    conn = db.connect(settings.database_path)
    try:
        with db.immediate(conn):
            contagem = conn.execute(COUNT, (usuario, agora.strftime("%Y-%m-%dT%H"))).fetchone()[0]
    finally:
        conn.close()
    if contagem > settings.bench_relatorio_limite_hora:
        raise Refusal(429, "limite_excedido", {"Retry-After": str(3600 - (agora.minute * 60 + agora.second))})


def unidade_valida(request: Request, codigo: str | None) -> str | None:
    """Never trust the code the machine sent: only an active Unidade, else NULL with a log line."""
    if not codigo:
        return None
    try:
        dados, _, _ = cadastros.obter(request)
    except Refusal:
        log.warning("unidade do diagnostico nao conferida: cadastros indisponiveis")
        return None
    if codigo.strip() in {u["codigo"] for u in dados["unidades"]}:
        return codigo.strip()
    log.warning("unidade do diagnostico fora das Unidades ativas; gravada nula")
    return None


def gravado(conn, diagnostico_id: int) -> dict | None:
    row = conn.execute(
        "SELECT relatorio_md, chamado_titulo, chamado_descricao, maior_confianca, modelo, tokens_entrada, tokens_saida"
        " FROM relatorios WHERE diagnostico_id = ?",
        (diagnostico_id,),
    ).fetchone()
    if row is None:
        return None
    return dict(
        zip(
            ("relatorio_md", "chamado_titulo", "chamado_descricao", "maior_confianca", "modelo", "tokens_entrada", "tokens_saida"),
            row,
            strict=True,
        )
    ) | {"diagnostico_id": diagnostico_id}


@router.post("/relatorio")
def relatorio(entrada: EntradaBench, request: Request, sessao: dict = Depends(exigir_sessao)):
    settings = request.app.state.settings
    limitar(settings, sessao["usuario"])
    normalizada, avisos = normalizacao.normalizar(entrada.model_dump(exclude={"envio_id", "unidade"}))
    sessao_diag = normalizada["sessao"]
    hostname = sessao_diag["hostname"]
    unidade = unidade_valida(request, entrada.unidade)
    agora = utcnow()
    envio = entrada.envio_id[:8]

    conn = db.connect(settings.database_path)
    try:
        anteriores = historico(conn, hostname, HISTORICO_PROMPT)
        with db.immediate(conn):
            row = conn.execute(
                "SELECT id, processando_desde FROM diagnosticos WHERE envio_id = ?", (entrada.envio_id,)
            ).fetchone()
            pronto = gravado(conn, row[0]) if row else None
            if row is None:
                diagnostico_id = conn.execute(
                    "INSERT INTO diagnosticos (carreta, hostname, sessao_id, projeto, sub_perfil, versao_schema, dados,"
                    " resumo, bench_usuario, bench_sessao_id, unidade, envio_id, processando_desde)"
                    " VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                    (
                        CARRETA, hostname, sessao_diag["id"], sessao_diag.get("projeto"), sessao_diag.get("subPerfil"),
                        sessao_diag["versaoSchema"], json.dumps(normalizada, ensure_ascii=False),
                        json.dumps(normalizacao.resumir(normalizada), ensure_ascii=False),
                        sessao["usuario"], sessao["id"], unidade, entrada.envio_id, iso(agora),
                    ),
                ).lastrowid
            elif pronto is None:
                diagnostico_id = row[0]
                inicio = row[1] and datetime.strptime(row[1], "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=agora.tzinfo)
                if inicio and agora - inicio < timedelta(seconds=PROCESSANDO_SEGUNDOS):
                    log.info("diagnostico %s ainda em processamento (id %d)", envio, diagnostico_id)
                    raise Refusal(409, "em_processamento")
                # Earlier attempt failed (or presumed failed): retry the AI on the same row.
                conn.execute(
                    "UPDATE diagnosticos SET processando_desde = ? WHERE id = ?", (iso(agora), diagnostico_id)
                )
                anteriores = [item for item in anteriores if item["diagnostico_id"] != diagnostico_id]
        if pronto is not None:
            log.info("diagnostico %s ja tinha laudo (id %d); devolvido o gravado", envio, row[0])
            return pronto
        log.info("diagnostico %s recebido de %s (id %d)", envio, sessao["usuario"], diagnostico_id)
        gerado, relatorio_md = gerar_laudo(request, conn, diagnostico_id, normalizada, avisos, anteriores)
    finally:
        conn.close()

    tarefas.espelhar(request.app)
    return {
        "relatorio_md": relatorio_md,
        "chamado_titulo": gerado.chamado_titulo,
        "chamado_descricao": gerado.chamado_descricao,
        "maior_confianca": gerado.maior_confianca,
        "modelo": gerado.modelo,
        "tokens_entrada": gerado.tokens_entrada,
        "tokens_saida": gerado.tokens_saida,
        "diagnostico_id": diagnostico_id,
    }


@router.get("/historico/{hostname}")
def historico_rota(
    request: Request,
    hostname: str = Path(pattern=HOSTNAME),
    sessao: dict = Depends(exigir_sessao),
):
    nome = hostname.strip().upper()
    conn = db.connect(request.app.state.settings.database_path)
    try:
        itens = historico(conn, nome, HISTORICO_ROTA, bench=True)
    finally:
        conn.close()
    return {"hostname": nome, "diagnosticos": itens}
