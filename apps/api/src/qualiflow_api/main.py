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


if __name__ == "__main__":
    # NOT uvicorn.run(app, ...) -- same reasoning as
    # apps/knowledge/main.py's identical block: uvicorn.Server.run()
    # directly instantiates asyncio.ProactorEventLoop on Windows
    # (uvicorn/loops/asyncio.py), bypassing any event-loop POLICY we
    # set. This app has no DB-touching endpoint wired up yet (db.py's
    # get_org_scoped_db from M0.3 isn't used by any route here), so
    # this was never actually triggered through the live server --
    # only through pytest, which creates its loop after imports and
    # never hits this uvicorn-specific code path. Fixed proactively
    # before the first DB endpoint gets added, not after it breaks.
    import asyncio
    import sys

    import uvicorn

    config = uvicorn.Config(app, host="0.0.0.0", port=8001)
    server = uvicorn.Server(config)

    if sys.platform == "win32":
        loop = asyncio.SelectorEventLoop()
        asyncio.set_event_loop(loop)
        loop.run_until_complete(server.serve())
    else:
        asyncio.run(server.serve())
