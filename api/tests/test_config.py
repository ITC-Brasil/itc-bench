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
