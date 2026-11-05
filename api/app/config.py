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
    # ADR-026: sent as reasoning_effort; "low" keeps the report under the timeout. Empty = not sent.
    opencode_go_reasoning_effort: str = "low"
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
    # Bench login (ADR-013). Every default lets the API start: with GLPI_* or the HMAC key
    # empty, POST /v1/bench/login answers 503 glpi_indisponivel.
    glpi_url: str = ""
    glpi_oauth_client_id: str = ""
    glpi_oauth_client_secret: SecretStr = SecretStr("")
    glpi_perfil_tecnicos_id: int = 0
    glpi_timeout_seconds: float = Field(10.0, gt=0, le=30)
    # Keys the user field in the audit and the rate limit when GLPI did not recognize it:
    # a password typed in the user field must not reach the database (ADR-013).
    bench_login_hmac_key: SecretStr = SecretStr("")
    bench_sessao_horas: int = Field(12, ge=1, le=24)
    bench_login_falhas_usuario: int = Field(5, ge=1)
    bench_login_falhas_ip: int = Field(20, ge=1)
    # Bench cadastros read from NocoDB (ADR-014, TA-ADR-027). Own token: a Viewer user only on
    # the "ITC Bench" base, never the mirror token. Empty: the route answers 503.
    nocodb_cadastros_token: SecretStr = SecretStr("")
    nocodb_tabela_servidores: str = ""
    nocodb_tabela_instaladores: str = ""
    nocodb_tabela_wifi: str = ""
    nocodb_tabela_unidades: str = ""
    nocodb_cadastros_timeout_seconds: float = Field(5.0, gt=0, le=15)
    nocodb_cadastros_ttl_seconds: int = Field(60, ge=1)
    # Keys the ETag: the content holds secrets, so the version must not derive from it alone.
    # Empty: a random key per process (a restart invalidates the 304s).
    bench_cadastros_etag_key: SecretStr = SecretStr("")
    # TA-ADR-028: Bench reports per technician per UTC hour.
    bench_relatorio_limite_hora: int = Field(30, ge=1)

    @field_validator("opencode_go_model")
    @classmethod
    def reject_forbidden_model(cls, value: str) -> str:
        value = value.strip()
        if value.lower().startswith(FORBIDDEN_MODEL_PREFIX):
            raise ValueError("muse-spark-* models are forbidden (ADR-011)")
        return value
