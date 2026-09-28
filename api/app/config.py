from pydantic import Field, SecretStr, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

# ADR-011: these models use customer data for training.
FORBIDDEN_MODEL_PREFIX = "muse-spark"


class Settings(BaseSettings):
    # ponytail: only the variables used so far; each module adds its own.
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    app_enable_docs: bool = False
    database_path: str = "/data/tecnico.db"
    max_body_bytes: int = 512 * 1024
    rate_limit_per_token_per_hour: int = 60
    # SecretStr: repr, str and model_dump show "**********", never the key (§7).
    opencode_go_api_key: SecretStr = SecretStr("")
    opencode_go_model: str = "mimo-v2.6-flash"
    # ADR-010: answer before the 100 s cut of the Cloudflare Tunnel; 90 leaves room for the rest.
    opencode_go_timeout_seconds: float = Field(60.0, gt=0, le=90)
    # Mirror of relatorios in NocoDB (ADR-005): one way, off the request path.
    nocodb_enabled: bool = False
    nocodb_url: str = ""
    nocodb_token: SecretStr = SecretStr("")
    nocodb_table_id: str = ""
    nocodb_retry_seconds: int = Field(300, ge=10)
    # ntfy alerts (§6.7); the same key is sent at most once per ntfy_repeat_minutes.
    ntfy_enabled: bool = False
    ntfy_url: str = ""
    ntfy_topic: str = ""
    ntfy_token: SecretStr = SecretStr("")
    ntfy_repeat_minutes: int = Field(60, ge=1)
    ntfy_failure_threshold_per_hour: int = Field(5, ge=1)

    @field_validator("opencode_go_model")
    @classmethod
    def reject_forbidden_model(cls, value: str) -> str:
        value = value.strip()
        if value.lower().startswith(FORBIDDEN_MODEL_PREFIX):
            raise ValueError("muse-spark-* models are forbidden (ADR-011)")
        return value
