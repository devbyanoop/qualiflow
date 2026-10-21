from fastapi import Depends, FastAPI
from opentelemetry.instrumentation.fastapi import FastAPIInstrumentor

from .auth import verify_token
from .settings import settings
from .telemetry import configure_telemetry

configure_telemetry(service_name="qualiflow-api", otlp_endpoint=settings.otel_exporter_otlp_endpoint)

app = FastAPI(title="QualiFlow API")

# Wraps the app in OTel's ASGI middleware — this is what actually emits
# the http.server.* metrics per request, using the MeterProvider we just
# set globally above. No manual per-endpoint instrumentation needed.
FastAPIInstrumentor.instrument_app(app)


@app.get("/healthz")
def healthz() -> dict:
    return {"status": "ok"}


@app.get("/protected")
def protected(claims: dict = Depends(verify_token)) -> dict:
    return {"sub": claims["sub"], "azp": claims.get("azp")}
