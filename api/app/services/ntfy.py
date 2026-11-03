"""ntfy alerts (§6.7) with repeat limiting: one message per key per NTFY_REPEAT_MINUTES.

The suppression is decided and recorded in SQLite before sending, so a storm of the same
failure sends one message, and the next one says how many were suppressed.
"""

from datetime import datetime, timedelta, timezone

import httpx

from app import db

TIMEOUT_SECONDS = 5.0
FORMATO = "%Y-%m-%dT%H:%M:%S"


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


def configurado(settings) -> bool:
    token = settings.ntfy_token.get_secret_value().strip()
    return bool(settings.ntfy_enabled and settings.ntfy_url and settings.ntfy_topic and token not in ("", "changeme"))


def reservar(settings, chave: str) -> int | None:
    """Record a send for chave and return how many were suppressed before it, or None to suppress."""
    agora = utcnow()
    conn = db.connect(settings.database_path)
    try:
        with db.immediate(conn):
            row = conn.execute("SELECT ultimo_envio, suprimidos FROM alertas WHERE chave = ?", (chave,)).fetchone()
            if row is not None:
                ultimo = datetime.strptime(row[0], FORMATO).replace(tzinfo=timezone.utc)
                if agora - ultimo < timedelta(minutes=settings.ntfy_repeat_minutes):
                    conn.execute("UPDATE alertas SET suprimidos = suprimidos + 1 WHERE chave = ?", (chave,))
                    return None
            conn.execute(
                "INSERT INTO alertas (chave, ultimo_envio, suprimidos) VALUES (?, ?, 0)"
                " ON CONFLICT (chave) DO UPDATE SET ultimo_envio = excluded.ultimo_envio, suprimidos = 0",
                (chave, agora.strftime(FORMATO)),
            )
            return row[1] if row else 0
    finally:
        conn.close()


def alertar(settings, chave: str, titulo: str, mensagem: str, transport: httpx.BaseTransport | None = None) -> bool:
    """Send one alert unless the same key was sent recently. Never raises."""
    if not configurado(settings):
        return False
    suprimidos = reservar(settings, chave)
    if suprimidos is None:
        return False
    if suprimidos:
        mensagem += f"\n\n({suprimidos} alertas iguais suprimidos desde o último envio.)"
    headers = {"Authorization": f"Bearer {settings.ntfy_token.get_secret_value().strip()}"}
    # JSON publishing (POST to the root URL): title and message in UTF-8 without header encoding.
    corpo = {
        "topic": settings.ntfy_topic,
        "title": titulo,
        "message": mensagem,
        "priority": 4,
        "tags": ["warning", "tecnico-assistente"],
    }
    try:
        with httpx.Client(timeout=TIMEOUT_SECONDS, transport=transport) as client:
            return client.post(settings.ntfy_url.rstrip("/"), json=corpo, headers=headers).status_code == 200
    except httpx.HTTPError:
        # ponytail: the send is already recorded, so an ntfy outage loses this alert for
        # one repeat window. Acceptable for an alert channel; queue it if that matters.
        return False
