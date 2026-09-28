import hmac
import re
from datetime import datetime, timezone

from fastapi import Request
from fastapi.responses import JSONResponse

from app import db
from app.tokens import PREFIX, hash_token

# PREFIX + secrets.token_urlsafe(32): 43 URL-safe characters.
TOKEN_FORMAT = re.compile(re.escape(PREFIX) + r"[A-Za-z0-9_-]{43}")

# ADR-021: fixed one-hour UTC window, one row per token in tokens_uso.
COUNT_USE = (
    "INSERT INTO tokens_uso (token_id, janela, contagem) VALUES (?, ?, 1)"
    " ON CONFLICT (token_id) DO UPDATE SET"
    " contagem = CASE WHEN janela = excluded.janela THEN contagem + 1 ELSE 1 END,"
    " janela = excluded.janela"
    " RETURNING contagem"
)


class Refusal(Exception):
    """Short answer with a stable code and no internal detail."""

    def __init__(self, status: int, code: str, headers: dict | None = None):
        self.status, self.code, self.headers = status, code, headers


async def refusal_handler(request: Request, exc: Refusal) -> JSONResponse:
    return JSONResponse({"erro": exc.code}, exc.status, headers=exc.headers)


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


def unauthorized() -> Refusal:
    return Refusal(401, "nao_autorizado", {"WWW-Authenticate": "Bearer"})


def exigir_token(request: Request) -> str:
    """Dependency: Authorization: Bearer itcta_... of an active token, within the hourly limit.

    Missing header, other scheme, malformed, unknown and revoked tokens get the same 401.
    Returns the carreta.
    """
    scheme, _, token = request.headers.get("authorization", "").partition(" ")
    if scheme.lower() != "bearer" or not TOKEN_FORMAT.fullmatch(token):
        raise unauthorized()

    settings = request.app.state.settings
    digest = hash_token(token)
    now = utcnow()
    conn = db.connect(settings.database_path)
    try:
        with db.immediate(conn):
            # The index compares the SHA-256 of the input, not the token (ADR-007); see
            # docs/modules/02-tokens-auth.md. compare_digest makes the check explicit.
            row = conn.execute(
                "SELECT id, carreta, token_hash FROM carretas_tokens WHERE token_hash = ? AND ativo = 1",
                (digest,),
            ).fetchone()
            if row is None or not hmac.compare_digest(row[2], digest):
                raise unauthorized()
            token_id, carreta, _ = row
            count = conn.execute(COUNT_USE, (token_id, now.strftime("%Y-%m-%dT%H"))).fetchone()[0]
            conn.execute("UPDATE carretas_tokens SET ultimo_uso = CURRENT_TIMESTAMP WHERE id = ?", (token_id,))
    finally:
        conn.close()

    if count > settings.rate_limit_per_token_per_hour:
        retry_after = 3600 - (now.minute * 60 + now.second)
        raise Refusal(429, "limite_excedido", {"Retry-After": str(retry_after)})
    return carreta
