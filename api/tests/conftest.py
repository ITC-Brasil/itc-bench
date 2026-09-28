import pytest
from fastapi import Depends
from fastapi.testclient import TestClient

from app import db, tokens
from app.auth import exigir_token
from app.config import Settings
from app.main import create_app


@pytest.fixture
def settings(tmp_path):
    # Temporary database per test; _env_file=None keeps a local .env out of the tests.
    return Settings(_env_file=None, database_path=str(tmp_path / "tecnico.db"))


@pytest.fixture
def client(settings):
    # The context manager runs the lifespan, which applies the migrations.
    with TestClient(create_app(settings)) as client:
        yield client


@pytest.fixture
def protected_client(settings):
    """App with a test-only protected route; production has none until Module 03."""
    app = create_app(settings)

    @app.post("/teste/protegida")
    def protegida(carreta: str = Depends(exigir_token)):
        return {"carreta": carreta}

    with TestClient(app) as client:
        yield client


@pytest.fixture
def issue(settings):
    """Create an active token for a carreta and return it."""

    def create(carreta="UM-03"):
        db.migrate(settings.database_path)
        conn = db.connect(settings.database_path)
        try:
            with db.immediate(conn):
                token, _ = tokens.insert_token(conn, carreta, "", "teste")
        finally:
            conn.close()
        return token

    return create
