import pytest
from fastapi.testclient import TestClient

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
