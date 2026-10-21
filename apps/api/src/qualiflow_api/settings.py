from pydantic_settings import BaseSettings, SettingsConfigDict


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


settings = Settings()
