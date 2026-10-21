from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="QUALIFLOW_", extra="ignore")

    pg_host: str = "localhost"
    pg_port: int = 5433
    pg_db: str = "qualiflow"
    pg_user: str = "qualiflow"
    pg_password: str = "changeme"
    pg_app_password: str = "changeme"

    minio_api_port: int = 9000
    minio_root_user: str = "qualiflow"
    minio_root_password: str = "changeme"

    @property
    def minio_endpoint_url(self) -> str:
        return f"http://{self.pg_host}:{self.minio_api_port}"

    @property
    def database_url(self) -> str:
        # Same restricted qualiflow_app role as apps/api and
        # apps/knowledge — read-only use here, but still never the
        # superuser.
        return (
            f"postgresql+psycopg://qualiflow_app:{self.pg_app_password}"
            f"@{self.pg_host}:{self.pg_port}/{self.pg_db}"
        )

    @property
    def database_url_admin(self) -> str:
        # Superuser — test seeding/cleanup only, same as apps/api and
        # apps/knowledge. The running service never uses this.
        return (
            f"postgresql+psycopg://{self.pg_user}:{self.pg_password}"
            f"@{self.pg_host}:{self.pg_port}/{self.pg_db}"
        )


settings = Settings()
