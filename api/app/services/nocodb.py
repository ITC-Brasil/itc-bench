"""One-way mirror of relatorios in NocoDB (ADR-005). Never on the request path.

A report is born 'pendente' and turns 'ok' once NocoDB accepts it; any failure keeps it
'pendente' for the next pass (after a report, and every NOCODB_RETRY_SECONDS).
"""

import threading

import httpx

from app import db

TIMEOUT_SECONDS = 10.0
LOTE = 20
# ponytail: per-process lock, so the post-report pass and the retry loop never send the
# same row twice. Enough with the single uvicorn worker (ADR-021); a second worker would
# need a claim column instead.
_lock = threading.Lock()

PENDENTES = (
    "SELECT r.id, r.diagnostico_id, d.recebido_em, d.carreta, d.hostname, d.projeto, d.sub_perfil,"
    " r.modelo, r.maior_confianca, r.chamado_titulo, r.relatorio_md"
    " FROM relatorios r JOIN diagnosticos d ON d.id = r.diagnostico_id"
    " WHERE r.espelho_status = 'pendente' ORDER BY r.id LIMIT ?"
)


def registro(row) -> dict:
    """Fields of docs/NOCODB.md, in the NocoDB column names."""
    _, diagnostico_id, recebido_em, carreta, hostname, projeto, sub_perfil, modelo, confianca, titulo, relatorio = row
    return {
        "DiagnosticoId": diagnostico_id,
        "Data": f"{recebido_em}+00:00",
        "Carreta": carreta,
        "Hostname": hostname,
        "Projeto": projeto,
        "SubPerfil": sub_perfil,
        "Modelo": modelo,
        "MaiorConfianca": confianca,
        "ChamadoTitulo": titulo,
        "Relatorio": relatorio,
    }


def configurado(settings) -> bool:
    token = settings.nocodb_token.get_secret_value().strip()
    return bool(settings.nocodb_enabled and settings.nocodb_url and settings.nocodb_table_id and token not in ("", "changeme"))


def espelhar_pendentes(settings, transport: httpx.BaseTransport | None = None) -> int:
    """Send up to LOTE pending reports; return how many NocoDB accepted."""
    if not configurado(settings):
        return 0
    with _lock:
        conn = db.connect(settings.database_path)
        try:
            rows = conn.execute(PENDENTES, (LOTE,)).fetchall()
            if not rows:
                return 0
            url = f"{settings.nocodb_url.rstrip('/')}/api/v2/tables/{settings.nocodb_table_id}/records"
            headers = {"xc-token": settings.nocodb_token.get_secret_value().strip()}
            enviados = 0
            with httpx.Client(timeout=TIMEOUT_SECONDS, transport=transport) as client:
                for row in rows:
                    erro = enviar(client, url, headers, registro(row))
                    with db.immediate(conn):
                        if erro is None:
                            conn.execute(
                                "UPDATE relatorios SET espelho_status = 'ok', espelho_em = CURRENT_TIMESTAMP,"
                                " espelho_erro = NULL, espelho_tentativas = espelho_tentativas + 1 WHERE id = ?",
                                (row[0],),
                            )
                            enviados += 1
                        else:
                            conn.execute(
                                "UPDATE relatorios SET espelho_erro = ?, espelho_tentativas = espelho_tentativas + 1"
                                " WHERE id = ?",
                                (erro, row[0]),
                            )
                    if erro in ("timeout", "indisponivel"):
                        # NocoDB is down: the rest waits for the next pass instead of
                        # holding the lock for LOTE timeouts.
                        break
            return enviados
        finally:
            conn.close()


def enviar(client: httpx.Client, url: str, headers: dict, campos: dict) -> str | None:
    """None on success, else a short code without the NocoDB text."""
    try:
        resposta = client.post(url, json=[campos], headers=headers)
    except httpx.TimeoutException:
        return "timeout"
    except httpx.HTTPError:
        return "indisponivel"
    return None if resposta.status_code == 200 else f"http_{resposta.status_code}"
