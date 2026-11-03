import re
import sqlite3
from datetime import datetime, timezone

import pytest

from app import auth, tokens

URL = "/teste/protegida"
UNAUTHORIZED = {"erro": "nao_autorizado"}


@pytest.fixture
def settings(settings):
    settings.rate_limit_per_token_per_hour = 3
    settings.max_body_bytes = 64
    return settings


@pytest.fixture
def clock(monkeypatch):
    """Freeze auth.utcnow; set clock.now to move it."""

    class Clock:
        now = datetime(2026, 9, 28, 14, 10, 0, tzinfo=timezone.utc)

    monkeypatch.setattr(auth, "utcnow", lambda: Clock.now)
    return Clock


def bearer(token):
    return {"Authorization": f"Bearer {token}"}


def test_valid_token_passes_and_records_last_use(protected_client, issue, settings):
    token = issue()
    response = protected_client.post(URL, headers=bearer(token))

    assert response.status_code == 200
    assert response.json() == {"carreta": "UM-03"}
    conn = sqlite3.connect(settings.database_path)
    assert conn.execute("SELECT ultimo_uso FROM carretas_tokens").fetchone()[0] is not None
    conn.close()


@pytest.mark.parametrize(
    "headers",
    [
        {},
        {"Authorization": ""},
        {"Authorization": "Bearer"},
        {"Authorization": "Bearer "},
        {"Authorization": "Basic dXNlcjpwYXNz"},
        {"Authorization": "Token itcta_" + "a" * 43},
        {"Authorization": "Bearer itcta_curto"},
        {"Authorization": "Bearer " + "a" * 49},
        {"Authorization": "Bearer itcta_" + "a" * 43 + " extra"},
        {"Authorization": "Bearer itcta_" + "a" * 43},  # well formed, unknown
    ],
)
def test_bad_credentials_get_the_same_401(protected_client, issue, headers):
    issue()
    response = protected_client.post(URL, headers=headers)

    assert response.status_code == 401
    assert response.json() == UNAUTHORIZED
    assert response.headers["www-authenticate"] == "Bearer"


def test_revoked_token_is_refused_on_the_next_request(protected_client, issue, settings):
    token = issue()
    assert protected_client.post(URL, headers=bearer(token)).status_code == 200

    assert tokens.main(["revoke", "--carreta", "UM-03", "--motivo", "perdido", "--operador", "t"], settings) == 0
    response = protected_client.post(URL, headers=bearer(token))

    assert response.status_code == 401
    assert response.json() == UNAUTHORIZED


def test_rotate_swaps_the_accepted_token(protected_client, issue, settings, capsys):
    old = issue()
    tokens.main(["rotate", "--carreta", "UM-03", "--operador", "t"], settings)
    new = re.search(r"itcta_\S{43}", capsys.readouterr().out).group()

    assert protected_client.post(URL, headers=bearer(old)).status_code == 401
    assert protected_client.post(URL, headers=bearer(new)).status_code == 200


def test_hourly_limit_is_per_token(protected_client, issue, clock):
    token, other = issue(), issue("UM-04")
    for _ in range(3):
        assert protected_client.post(URL, headers=bearer(token)).status_code == 200

    clock.now = clock.now.replace(minute=59, second=30)
    response = protected_client.post(URL, headers=bearer(token))

    assert response.status_code == 429
    assert response.json() == {"erro": "limite_excedido"}
    assert response.headers["retry-after"] == "30"
    assert protected_client.post(URL, headers=bearer(other)).status_code == 200


def test_new_hour_opens_a_new_window(protected_client, issue, clock):
    token = issue()
    for _ in range(4):
        protected_client.post(URL, headers=bearer(token))
    assert protected_client.post(URL, headers=bearer(token)).status_code == 429

    clock.now = clock.now.replace(hour=15, minute=0)

    assert protected_client.post(URL, headers=bearer(token)).status_code == 200


def test_order_is_body_then_token_then_limit(protected_client, issue, settings, clock):
    token = issue()
    for _ in range(3):
        protected_client.post(URL, headers=bearer(token))
    big = b"x" * 65

    # Body first: a big body is 413 with no token, or with a token over its limit.
    assert protected_client.post(URL, content=big).status_code == 413
    assert protected_client.post(URL, content=big, headers=bearer(token)).status_code == 413
    # Token before limit: a revoked token over its limit is 401, not 429.
    assert protected_client.post(URL, headers=bearer(token)).status_code == 429
    tokens.main(["revoke", "--carreta", "UM-03", "--motivo", "x", "--operador", "t"], settings)
    assert protected_client.post(URL, headers=bearer(token)).status_code == 401


def test_refused_requests_do_not_count(protected_client, issue, settings):
    token = issue()
    protected_client.post(URL, content=b"x" * 65, headers=bearer(token))
    protected_client.post(URL, headers={"Authorization": "Bearer itcta_" + "b" * 43})

    conn = sqlite3.connect(settings.database_path)
    assert conn.execute("SELECT count(*) FROM tokens_uso").fetchone()[0] == 0
    conn.close()
