import json
from typing import Any, Literal

from fastapi import APIRouter, Depends, Path, Request
from pydantic import BaseModel, ConfigDict, Field

from app import db, normalizacao, prompt, tarefas
from app.auth import Refusal, exigir_token
from app.services import opencode_go

router = APIRouter()

# NetBIOS names are at most 15 characters; 63 is the DNS label limit, kept as margin.
HOSTNAME = r"^\s*[A-Za-z0-9][A-Za-z0-9-]{0,62}\s*$"
HISTORICO_PROMPT = 5
HISTORICO_ROTA = 20


class Sessao(BaseModel):
    # Unknown fields are kept: the stored session is the whole normalized document.
    model_config = ConfigDict(extra="allow")

    versaoSchema: Literal[normalizacao.VERSOES]  # type: ignore[valid-type]
    id: str = Field(min_length=1, max_length=120)
    hostname: str = Field(pattern=HOSTNAME)
    projeto: str | None = None
    subPerfil: str | None = None


class Entrada(BaseModel):
    """sessao.json + the module JSONs + correcoes.json of one pendrive session (pendrive/SCHEMA.md)."""

    model_config = ConfigDict(extra="ignore")

    sessao: Sessao
    modulos: dict[str, dict[str, Any] | None] = {}
    correcoes: dict[str, Any] | None = None


def historico(conn, hostname: str, limite: int, bench: bool = False) -> list[dict]:
    """bench: also who sent it, the unit and the report text (GET /v1/bench/historico, ADR-016).
    Never in the prompt: there the GLPI login of the technician stays out (TA-ADR-028)."""
    rows = conn.execute(
        "SELECT d.id, d.recebido_em, d.carreta, d.sessao_id, d.projeto, d.sub_perfil, d.versao_schema,"
        " d.resumo, d.falha, r.maior_confianca, r.chamado_titulo, r.modelo,"
        " d.bench_usuario, d.unidade, r.relatorio_md, r.chamado_descricao"
        " FROM diagnosticos d LEFT JOIN relatorios r ON r.diagnostico_id = d.id"
        " WHERE d.hostname = ? ORDER BY d.id DESC LIMIT ?",
        (hostname, limite),
    ).fetchall()
    itens = [
        {
            "diagnostico_id": row[0],
            "recebido_em": row[1],
            "carreta": row[2],
            "sessao_id": row[3],
            "projeto": row[4],
            "sub_perfil": row[5],
            "versao_schema": row[6],
            "resumo": json.loads(row[7]),
            "falha": row[8],
            "relatorio": None if row[9] is None and row[10] is None else {
                "maior_confianca": row[9], "chamado_titulo": row[10], "modelo": row[11],
            },
        }
        for row in rows
    ]
    if bench:
        for item, row in zip(itens, rows, strict=True):
            item["bench_usuario"], item["unidade"] = row[12], row[13]
            if item["relatorio"] is not None:
                item["relatorio"]["relatorio_md"], item["relatorio"]["chamado_descricao"] = row[14], row[15]
    return itens


def gerar_laudo(request: Request, conn, diagnostico_id: int, normalizada: dict, avisos: list[str], anteriores: list[dict]):
    """Call the AI outside any transaction (it can take up to the timeout, TA-ADR-010) and store
    the report; on failure store the code in diagnosticos.falha and refuse with it."""
    settings = request.app.state.settings
    sessao = normalizada["sessao"]
    try:
        gerado = opencode_go.gerar(
            settings, prompt.montar(normalizada, avisos, anteriores), sessao["id"], request.app.state.transports.get("ia")
        )
    except opencode_go.IAFalha as falha:
        with db.immediate(conn):
            conn.execute(
                "UPDATE diagnosticos SET falha = ?, processando_desde = NULL WHERE id = ?", (falha.code, diagnostico_id)
            )
        tarefas.falha_ia(request.app, falha.code)
        raise Refusal(falha.status, falha.code) from None

    relatorio_md = com_avisos(gerado.relatorio_md, avisos)
    with db.immediate(conn):
        conn.execute(
            "INSERT INTO relatorios (diagnostico_id, modelo, tokens_entrada, tokens_saida, duracao_ms,"
            " maior_confianca, relatorio_md, chamado_titulo, chamado_descricao) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (
                diagnostico_id, gerado.modelo, gerado.tokens_entrada, gerado.tokens_saida, gerado.duracao_ms,
                gerado.maior_confianca, relatorio_md, gerado.chamado_titulo, gerado.chamado_descricao,
            ),
        )
        conn.execute("UPDATE diagnosticos SET falha = NULL, processando_desde = NULL WHERE id = ?", (diagnostico_id,))
    return gerado, relatorio_md


def com_avisos(relatorio_md: str, avisos: list[str]) -> str:
    """Normalization notices always reach the technician, whatever the model wrote."""
    if not avisos:
        return relatorio_md
    return relatorio_md + "\n\n## Avisos da coleta\n\n" + "\n".join(f"- {aviso}" for aviso in avisos)


@router.post("/v1/relatorio")
def relatorio(entrada: Entrada, request: Request, carreta: str = Depends(exigir_token)):
    settings = request.app.state.settings
    normalizada, avisos = normalizacao.normalizar(entrada.model_dump())
    sessao = normalizada["sessao"]
    hostname = sessao["hostname"]

    conn = db.connect(settings.database_path)
    try:
        # History first, so the session being diagnosed is not part of its own history.
        anteriores = historico(conn, hostname, HISTORICO_PROMPT)
        with db.immediate(conn):
            diagnostico_id = conn.execute(
                "INSERT INTO diagnosticos (carreta, token_id, hostname, sessao_id, projeto, sub_perfil,"
                " versao_schema, dados, resumo) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (
                    carreta, request.state.token_id, hostname, sessao["id"], sessao.get("projeto"), sessao.get("subPerfil"),
                    sessao["versaoSchema"], json.dumps(normalizada, ensure_ascii=False),
                    json.dumps(normalizacao.resumir(normalizada), ensure_ascii=False),
                ),
            ).lastrowid

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


@router.get("/v1/historico/{hostname}")
def historico_rota(
    request: Request,
    hostname: str = Path(pattern=HOSTNAME),
    carreta: str = Depends(exigir_token),
):
    conn = db.connect(request.app.state.settings.database_path)
    try:
        itens = historico(conn, hostname.strip().upper(), HISTORICO_ROTA)
    finally:
        conn.close()
    return {"hostname": hostname.strip().upper(), "diagnosticos": itens}
