# Installation

This gets every piece of QualiFlow's Walking Skeleton running from a fresh clone: infra, database schema, auth, and the three app servers (`apps/api`, `apps/knowledge`, `apps/agents`).

## Prerequisites

- Docker + Docker Compose, pointed at whatever host you want to run infra on (local machine or a remote Docker context).
- [uv](https://docs.astral.sh/uv/) for Python.
- A [Groq](https://console.groq.com/) API key (or any LiteLLM-supported provider — see `apps/agents/src/qualiflow_agents/tiers.py`).

## 1. Configure

```bash
git clone https://github.com/devbyanoop/qualiflow.git
cd qualiflow
cp .env.example .env
```

Edit `.env`:

- Leave the `localhost` defaults as-is if infra runs on the same machine you're developing on. Point `QUALIFLOW_PG_HOST` (and the Keycloak/MinIO/OTel hosts, if you edit those too) at a different host if your Docker daemon is remote.
- Set `GROQ_API_KEY` to a real key.
- Pick real passwords for `QUALIFLOW_PG_PASSWORD`, `QUALIFLOW_PG_APP_PASSWORD`, `QUALIFLOW_MINIO_ROOT_PASSWORD`, `QUALIFLOW_KEYCLOAK_ADMIN_PASSWORD`, `QUALIFLOW_API_CLIENT_SECRET`, `QUALIFLOW_GRAFANA_ADMIN_PASSWORD` — the `changeme` placeholders are not meant to be used as-is.

## 2. Install Python dependencies

```bash
uv sync --all-packages
```

This is a `uv` workspace with three separately-installable apps (`apps/api`, `apps/knowledge`, `apps/agents`) sharing one virtual environment. `uv sync --all-packages` installs all three together. **Important:** running a scoped `uv sync --project apps/X` (or a plain `uv run --project apps/X ...` without `--no-sync`) afterward will silently evict the *other two* apps' editable installs from the shared venv, since uv resolves that command to only what that one project needs. Every command below passes `--no-sync` for this reason — if you ever need to re-sync, use `uv sync --all-packages` again, not a scoped sync.

## 3. Bring up infra

```bash
docker compose up -d
docker compose ps   # all 8 services should show "Up" (postgres also "healthy")
```

This builds `postgres` (creates the restricted `qualiflow_app` role on first boot — see `infra/postgres/`) and `prometheus` from the Dockerfiles in `infra/`, and pulls `redis`, `minio`, the embeddings model (TEI), `keycloak`, `otel-collector`, and `grafana`.

## 4. Provision Keycloak

```bash
set -a; source .env; set +a   # bash; on PowerShell, load .env into your session some other way
bash infra/keycloak/provision-realm.sh
```

Creates the `qualiflow` realm and the `qualiflow-api` confidential client (service-accounts / client-credentials grant), and syncs the client secret to whatever you set `QUALIFLOW_API_CLIENT_SECRET` to. Safe to re-run — it skips creation if the realm/client already exist and just re-syncs the secret.

## 5. Apply the database schema

All migrations for every app live under `apps/api/alembic/` — one shared schema.

```bash
cd apps/api
uv run --no-sync alembic upgrade head
cd ../..
```

Then LangGraph's own checkpoint tables (`apps/agents` uses these for pause/resume on human review — not something Alembic manages, since LangGraph owns that schema):

```bash
uv run --no-sync --project apps/agents python apps/agents/scripts/setup_checkpointer.py
```

Follow the grant statement the script prints at the end — it needs to run once against Postgres as the superuser too (see the script's own docstring for the exact command).

## 6. Start the app servers

Three separate processes, each in its own terminal (or backgrounded):

```bash
uv run --no-sync --project apps/api python -m qualiflow_api.main        # port 8001
uv run --no-sync --project apps/knowledge python -m qualiflow_knowledge.main   # port 8003
uv run --no-sync --project apps/agents python -m qualiflow_agents.main  # port 8002
```

## 7. Verify

```bash
curl http://localhost:8001/healthz   # {"status":"ok"}
curl http://localhost:8003/healthz   # {"status":"ok"}
curl http://localhost:8002/healthz   # {"status":"ok"}
```

All three healthy means you're ready for the [quickstart](quickstart.md).
