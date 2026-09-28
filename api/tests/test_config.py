import pytest
from pydantic import ValidationError

from app.config import Settings
from app.main import create_app


def test_default_model_is_allowed():
    assert Settings(_env_file=None).opencode_go_model == "mimo-v2.6-flash"


def test_allowed_model_is_trimmed():
    assert Settings(_env_file=None, opencode_go_model=" glm-5.3-flash ").opencode_go_model == "glm-5.3-flash"


@pytest.mark.parametrize("model", ["muse-spark-x", " Muse-Spark-x ", "MUSE-SPARK-1"])
def test_forbidden_model_is_rejected(model):
    with pytest.raises(ValidationError, match="ADR-011"):
        Settings(_env_file=None, opencode_go_model=model)


def test_forbidden_model_in_environment_stops_startup(monkeypatch):
    monkeypatch.setenv("OPENCODE_GO_MODEL", " Muse-Spark-x ")
    with pytest.raises(ValidationError, match="ADR-011"):
        create_app()


def test_api_key_is_secret_and_timeout_defaults_to_60(monkeypatch):
    monkeypatch.setenv("OPENCODE_GO_API_KEY", "sk-real-key")
    settings = Settings(_env_file=None)

    assert settings.opencode_go_api_key.get_secret_value() == "sk-real-key"
    assert "sk-real-key" not in repr(settings) + str(settings.model_dump())
    assert settings.opencode_go_timeout_seconds == 60.0


@pytest.mark.parametrize("seconds", ["0", "91"])
def test_timeout_outside_the_tunnel_budget_is_rejected(seconds):
    with pytest.raises(ValidationError):
        Settings(_env_file=None, opencode_go_timeout_seconds=seconds)
