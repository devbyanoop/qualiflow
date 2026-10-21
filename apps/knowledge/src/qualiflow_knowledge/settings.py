from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="QUALIFLOW_", extra="ignore")

    pg_host: str = "localhost"
    pg_port: int = 5433
    pg_db: str = "qualiflow"
    pg_user: str = "qualiflow"
    pg_password: str = "changeme"
    pg_app_password: str = "changeme"
    embeddings_port: int = 8085

    @property
    def database_url(self) -> str:
        # Same restricted qualiflow_app role as apps/api — this service
        # never connects as the superuser either.
        return (
            f"postgresql+psycopg://qualiflow_app:{self.pg_app_password}"
            f"@{self.pg_host}:{self.pg_port}/{self.pg_db}"
        )

    @property
    def database_url_admin(self) -> str:
        # Superuser connection — test setup/teardown only, same as
        # apps/api's settings.py. The running service never uses this.
        return (
            f"postgresql+psycopg://{self.pg_user}:{self.pg_password}"
            f"@{self.pg_host}:{self.pg_port}/{self.pg_db}"
        )

    @property
    def embeddings_url(self) -> str:
        # TEI lives on the same remote host as Postgres (pg_host) — not
        # a separate setting, just reusing it.
        return f"http://{self.pg_host}:{self.embeddings_port}"


settings = Settings()
