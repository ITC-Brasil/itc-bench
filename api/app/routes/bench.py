"""Bench routes (ADR-013): login against GLPI, 12-hour session, logout.

/v1/bench/ is the only prefix the Cloudflare Access lets through without the service token, so
the rate limit here (SQLite, fixed 15-minute window) is the main defense against brute force.
"""

import hashlib
import hmac
import ipaddress
import logging
import secrets
from datetime import timedelta

from fastapi import APIRouter, Depends, Request, Response
from pydantic import BaseModel, ConfigDict, Field, SecretStr

from app import db
from app.auth import SESSAO_PREFIX, Refusal, exigir_sessao, iso, utcnow
from app.routes import saude as saude_rota
from app.routes.relatorio import HOSTNAME
from app.services import glpi, ntfy
from app.tokens import hash_token

log = logging.getLogger("tecnico.bench")
router = APIRouter(prefix="/v1/bench")
JANELA_MINUTOS = 15
RETENCAO = "-90 days"

COUNT = (
    "INSERT INTO bench_login_tentativas (chave, janela, contagem) VALUES (?, ?, 1)"
    " ON CONFLICT (chave) DO UPDATE SET"
    " contagem = CASE WHEN janela = excluded.janela THEN contagem + 1 ELSE 1 END,"
    " janela = excluded.janela"
)

router.get("/saude")(saude_rota.saude)


class Login(BaseModel):
    model_config = ConfigDict(extra="forbid")

    usuario: str = Field(min_length=1, max_length=255)
    senha: SecretStr = Field(min_length=1, max_length=1024)
    maquina: str = Field(pattern=HOSTNAME)


def ip_do_cliente(request: Request) -> str:
    """CF-Connecting-IP, trusted because the port listens on 127.0.0.1 only (TA-ADR-009) and
    the tunnel is the only way in; without it (or malformed), the connection address."""
    cabecalho = request.headers.get("cf-connecting-ip", "").strip()
    try:
        return str(ipaddress.ip_address(cabecalho))
    except ValueError:
        return request.client.host if request.client else "-"


def referencia(settings, usuario: str) -> str:
    """HMAC of the typed user: what GLPI did not recognize may be a password (ADR-013)."""
    chave = settings.bench_login_hmac_key.get_secret_value().encode()
    return "h:" + hmac.new(chave, usuario.encode(), hashlib.sha256).hexdigest()[:16]


def janela(agora) -> tuple[str, int]:
    """Current 15-minute window and the seconds left in it."""
    inicio = agora.replace(minute=agora.minute - agora.minute % JANELA_MINUTOS, second=0, microsecond=0)
    fim = inicio + timedelta(minutes=JANELA_MINUTOS)
    return inicio.strftime("%Y-%m-%dT%H:%M"), max(1, int((fim - agora).total_seconds()))


def gravar(settings, *comandos) -> None:
    """Each item: (sql, params). One BEGIN IMMEDIATE for all."""
    conn = db.connect(settings.database_path)
    try:
        with db.immediate(conn):
            for sql, params in comandos:
                conn.execute(sql, params)
    finally:
        conn.close()


def auditoria(quando, usuario, maquina, ip, resultado):
    return (
        "INSERT INTO bench_login_auditoria (quando, usuario, maquina, ip, resultado) VALUES (?, ?, ?, ?, ?)",
        (quando, usuario, maquina, ip, resultado),
    )


@router.post("/login")
def login(entrada: Login, request: Request):
    settings = request.app.state.settings
    agora = utcnow()
    quando = iso(agora)
    usuario = entrada.usuario.strip().lower()
    ip = ip_do_cliente(request)

    if not glpi.configurado(settings):
        gravar(settings, auditoria(quando, None, entrada.maquina, ip, "glpi_indisponivel"))
        raise Refusal(503, "glpi_indisponivel")

    ref = referencia(settings, usuario)
    chave_usuario, chave_ip = f"u:{ref}", f"ip:{ip}"
    janela_atual, restante = janela(agora)

    # Checked before GLPI: a locked user never reaches it. Check and reserve in one BEGIN
    # IMMEDIATE (Module 14): parallel attempts cannot pass the limit. The lock is not held
    # during the GLPI call; the reserved attempt is given back when GLPI accepts or is down.
    conn = db.connect(settings.database_path)
    try:
        with db.immediate(conn):
            contagens = dict(
                conn.execute(
                    "SELECT chave, contagem FROM bench_login_tentativas WHERE janela = ? AND chave IN (?, ?)",
                    (janela_atual, chave_usuario, chave_ip),
                ).fetchall()
            )
            bloqueado = (
                contagens.get(chave_usuario, 0) >= settings.bench_login_falhas_usuario
                or contagens.get(chave_ip, 0) >= settings.bench_login_falhas_ip
            )
            if not bloqueado:
                conn.execute(COUNT, (chave_usuario, janela_atual))
                conn.execute(COUNT, (chave_ip, janela_atual))
    finally:
        conn.close()
    if bloqueado:
        gravar(settings, auditoria(quando, ref, entrada.maquina, ip, "limite_excedido"))
        limite_atingido(request.app, ref, ip)
        raise Refusal(429, "limite_excedido", {"Retry-After": str(restante)})

    def devolver(*chaves):
        sql = "UPDATE bench_login_tentativas SET contagem = contagem - 1 WHERE chave = ? AND janela = ?"
        return [*((sql, (c, janela_atual)) for c in chaves), ("DELETE FROM bench_login_tentativas WHERE contagem <= 0", ())]

    try:
        tecnico = glpi.autenticar(settings, usuario, entrada.senha, request.app.state.transports.get("glpi"))
    except glpi.CredenciaisInvalidas:
        gravar(settings, auditoria(quando, ref, entrada.maquina, ip, "credenciais_invalidas"))
        raise Refusal(401, "credenciais_invalidas") from None
    except glpi.GlpiIndisponivel as erro:
        gravar(
            settings,
            *devolver(chave_usuario, chave_ip),
            auditoria(quando, ref, entrada.maquina, ip, "glpi_indisponivel"),
        )
        log.warning("login sem GLPI (%s)", erro.code)
        raise Refusal(503, "glpi_indisponivel") from None

    if not tecnico.tem_perfil:
        gravar(settings, auditoria(quando, tecnico.login, entrada.maquina, ip, "fora_do_perfil"))
        raise Refusal(403, "fora_do_perfil")

    sessao = SESSAO_PREFIX + secrets.token_urlsafe(32)
    expira = iso(agora + timedelta(hours=settings.bench_sessao_horas))
    gravar(
        settings,
        (
            "INSERT INTO bench_sessoes (token_hash, usuario, nome, glpi_id, maquina, ip, criada_em, expira_em)"
            " VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
            (hash_token(sessao), tecnico.login, tecnico.nome, tecnico.glpi_id, entrada.maquina, ip, quando, expira),
        ),
        ("DELETE FROM bench_login_tentativas WHERE chave = ?", (chave_usuario,)),
        *devolver(chave_ip),
        auditoria(quando, tecnico.login, entrada.maquina, ip, "ok"),
        # Retention: old audit rows and sessions expired long ago.
        ("DELETE FROM bench_login_auditoria WHERE quando < strftime('%Y-%m-%dT%H:%M:%SZ', 'now', ?)", (RETENCAO,)),
        ("DELETE FROM bench_sessoes WHERE expira_em < strftime('%Y-%m-%dT%H:%M:%SZ', 'now', ?)", (RETENCAO,)),
    )
    return {"sessao": sessao, "expira_em": expira, "tecnico": {"login": tecnico.login, "nome": tecnico.nome}}


@router.post("/logout", status_code=204)
def logout(request: Request):
    """Always 204: revokes the session when it is valid, says nothing otherwise."""
    try:
        sessao = exigir_sessao(request)
    except Refusal:
        return Response(status_code=204)
    quando = iso(utcnow())
    gravar(
        request.app.state.settings,
        ("UPDATE bench_sessoes SET revogada_em = ? WHERE id = ?", (quando, sessao["id"])),
        auditoria(quando, sessao["usuario"], None, ip_do_cliente(request), "logout"),
    )
    return Response(status_code=204)


@router.get("/sessao")
def sessao(dados: dict = Depends(exigir_sessao)):
    return {"tecnico": {"login": dados["usuario"], "nome": dados["nome"]}, "expira_em": dados["expira_em"]}


def limite_atingido(app, ref: str, ip: str) -> None:
    settings = app.state.settings
    app.state.em_segundo_plano(
        lambda: ntfy.alertar(
            settings,
            f"bench_login_limite:{ref}",
            "Login do Bench: limite de tentativas",
            f"Usuário {ref} (HMAC) ou IP {ip} passou do limite de senhas erradas em 15 min. "
            "Se não foi um técnico errando a senha, é tentativa de força bruta.",
            app.state.transports.get("ntfy"),
        )
    )

