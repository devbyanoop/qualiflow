from pathlib import Path

from dotenv import load_dotenv
from pydantic_settings import BaseSettings, SettingsConfigDict

# Loaded here, not just via uvicorn's --env-file, so every entry point
# (alembic, pytest, uvicorn) behaves the same way. parents[4] from this
# file (src/qualiflow_api/settings.py) is the repo root. If the file
# doesn't exist (e.g. in CI), this is a silent no-op and the field
# defaults below apply instead — never an error.
load_dotenv(Path(__file__).resolve().parents[4] / ".env")


class Settings(BaseSettings):
    # env_prefix means QUALIFLOW_KEYCLOAK_ISSUER -> keycloak_issuer, etc.
    # .env itself is loaded by uvicorn's --env-file flag before this module
    # even imports, so Settings just reads from the process environment.
    model_config = SettingsConfigDict(env_prefix="QUALIFLOW_", extra="ignore")

    # Defaults match .env.example's placeholders — good enough for the
    # module to import cleanly in tests/CI, which never hit a real
    # Keycloak. Real runs override these via uvicorn's --env-file .env.
    keycloak_issuer: str = "http://localhost:8080/realms/qualiflow"
    api_client_id: str = "qualiflow-api"
    otel_exporter_otlp_endpoint: str = "http://192.168.1.14:4318"

    pg_host: str = "localhost"
    pg_port: int = 5433
    pg_db: str = "qualiflow"
    pg_user: str = "qualiflow"
    pg_password: str = "changeme"
    pg_app_password: str = "changeme"

    @property
    def database_url(self) -> str:
        """The APP's own connection — the restricted qualiflow_app role,
        genuinely subject to RLS. This is what the running API uses."""
        return (
            f"postgresql+psycopg://qualiflow_app:{self.pg_app_password}"
            f"@{self.pg_host}:{self.pg_port}/{self.pg_db}"
        )

    @property
    def database_url_admin(self) -> str:
        """The superuser connection — migrations and test setup/bypass
        verification only. The running app must never use this one."""
        return (
            f"postgresql+psycopg://{self.pg_user}:{self.pg_password}"
            f"@{self.pg_host}:{self.pg_port}/{self.pg_db}"
        )


settings = Settings()
