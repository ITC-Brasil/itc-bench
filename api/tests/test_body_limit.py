import pytest
from fastapi import Request
from fastapi.testclient import TestClient

from app.config import Settings
from app.main import create_app

LIMIT = 16


@pytest.fixture
def client(tmp_path):
    settings = Settings(_env_file=None, database_path=str(tmp_path / "tecnico.db"), max_body_bytes=LIMIT)
    app = create_app(settings)

    # Test-only route: production has no body route until Module 03.
    @app.post("/teste/eco")
    async def eco(request: Request):
        return {"bytes": len(await request.body())}

    with TestClient(app) as client:
        yield client


def chunks(total, size=5):
    # A generator body makes httpx send Transfer-Encoding: chunked, without Content-Length.
    sent = 0
    while sent < total:
        piece = min(size, total - sent)
        sent += piece
        yield b"x" * piece


def test_default_limit_is_512_kb():
    assert Settings(_env_file=None).max_body_bytes == 524288


def test_body_at_the_limit_passes(client):
    response = client.post("/teste/eco", content=b"x" * LIMIT)

    assert response.status_code == 200
    assert response.json() == {"bytes": LIMIT}


def test_content_length_over_the_limit_is_refused(client):
    response = client.post("/teste/eco", content=b"x" * (LIMIT + 1))

    assert response.status_code == 413
    assert response.json() == {"erro": "corpo_grande"}


def test_chunked_body_over_the_limit_is_refused(client):
    response = client.post("/teste/eco", content=chunks(LIMIT + 1))

    assert "content-length" not in response.request.headers
    assert response.status_code == 413
    assert response.json() == {"erro": "corpo_grande"}


def test_chunked_body_under_the_limit_reaches_the_route_whole(client):
    response = client.post("/teste/eco", content=chunks(LIMIT))

    assert response.status_code == 200
    assert response.json() == {"bytes": LIMIT}


@pytest.mark.parametrize("value", ["abc", "-1", "+1", "1.5", ""])
def test_malformed_content_length_is_refused(client, value):
    response = client.post("/teste/eco", content=b"x", headers={"content-length": value})

    assert response.status_code == 400
    assert response.json() == {"erro": "requisicao_invalida"}


def test_limit_applies_to_every_route(client):
    # /v1/saude has no POST: the size check still answers first.
    assert client.post("/v1/saude", content=b"x" * (LIMIT + 1)).status_code == 413
    assert client.get("/v1/saude").status_code == 200
