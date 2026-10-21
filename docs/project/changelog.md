# Changelog

## Unreleased

- Repo scaffolding: `LICENSE` (Apache-2.0), `.gitignore`, `README.md`, CI skeleton (`.github/workflows/ci.yml`), this documentation site.
- M0.1 infra: `docker-compose.yml` (Postgres 16 + pgvector, Redis, MinIO, OTel Collector, Prometheus, Grafana) against the remote `fedora-host` Docker context. See `project/roadmap.md` for the real-world gotchas hit along the way (missing compose plugin, MinIO image distribution changes, remote-context bind-mount limitation).
- M0.2 API skeleton: `apps/api` (FastAPI), Keycloak container + realm/client, JWT-gated `/protected` endpoint, OTel metrics flowing to Prometheus, first unit tests + CI wired to run them.
- M0.3 tenant isolation: `organizations`/`projects` with Postgres RLS, a restricted non-superuser app role, per-request org scoping, and a leak test verified red-without/green-with the policy. New `integration` CI job with its own Postgres service container.
- M0.4 first LangGraph node: `apps/agents`, a tier-resolved one-node graph calling Groq with strict structured output, logged cost/latency (no tracing backend), exposed via a live `/hello/{name}` endpoint. Test is deliberately real (no mocking) — new `agents` CI job, needs a `GROQ_API_KEY` secret once pushed.
- M0.5 reference fixture: pivoted away from a QualiFlow-owned `demo-apps/` folder to **NovaPay** (separate, pre-existing repo) as the standalone app-under-test. `fixtures/novapay/openapi.yaml` (validated) and `brd-transfer-rule.md` describe it; three real authorization/consistency gaps found in NovaPay's transfer API along the way.
- M0.6 ingestion v0: `apps/knowledge`, real delta-hash skip proven against self-hosted embeddings (switched from BGE-M3 to a smaller multilingual model after repeated OOM kills — see roadmap for the full incident, including a close call with the host itself). Also fixed a real uvicorn/Windows event-loop bug (`uvicorn.run()` hard-codes `ProactorEventLoop`, ignoring any policy set) and a SQLAlchemy `text()` + Postgres `::` cast collision.
