from pydantic import field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

# ADR-011: these models use customer data for training.
FORBIDDEN_MODEL_PREFIX = "muse-spark"


class Settings(BaseSettings):
    # ponytail: only the variables used so far; each module adds its own.
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    app_enable_docs: bool = False
    database_path: str = "/data/tecnico.db"
    max_body_bytes: int = 512 * 1024
    opencode_go_model: str = "mimo-v2.6-flash"

    @field_validator("opencode_go_model")
    @classmethod
    def reject_forbidden_model(cls, value: str) -> str:
        value = value.strip()
        if value.lower().startswith(FORBIDDEN_MODEL_PREFIX):
            raise ValueError("muse-spark-* models are forbidden (ADR-011)")
        return value
