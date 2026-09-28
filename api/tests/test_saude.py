import os

import pytest
from fastapi.testclient import TestClient

from app.main import create_app


def test_saude_ok_without_internal_details(client):
    response = client.get("/v1/saude")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_saude_missing_database_returns_503_and_creates_nothing(settings):
    # Without the context manager the lifespan does not run, so nothing is migrated.
    client = TestClient(create_app(settings))

    response = client.get("/v1/saude")

    assert response.status_code == 503
    assert response.json() == {"status": "erro"}
    assert not os.path.exists(settings.database_path)


@pytest.mark.parametrize("path", ["/docs", "/redoc", "/openapi.json"])
def test_docs_disabled_by_default(client, path):
    assert client.get(path).status_code == 404


@pytest.mark.parametrize("path", ["/docs", "/redoc", "/openapi.json"])
def test_docs_enabled_by_flag(settings, path):
    settings.app_enable_docs = True
    with TestClient(create_app(settings)) as client:
        assert client.get(path).status_code == 200
