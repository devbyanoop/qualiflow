# Changelog

## Unreleased

- Repo scaffolding: `LICENSE` (Apache-2.0), `.gitignore`, `README.md`, CI skeleton (`.github/workflows/ci.yml`), this documentation site.
- M0.1 infra: `docker-compose.yml` (Postgres 16 + pgvector, Redis, MinIO, OTel Collector, Prometheus, Grafana) against the remote `fedora-host` Docker context. See `project/roadmap.md` for the real-world gotchas hit along the way (missing compose plugin, MinIO image distribution changes, remote-context bind-mount limitation).
- M0.2 API skeleton: `apps/api` (FastAPI), Keycloak container + realm/client, JWT-gated `/protected` endpoint, OTel metrics flowing to Prometheus, first unit tests + CI wired to run them.
- M0.3 tenant isolation: `organizations`/`projects` with Postgres RLS, a restricted non-superuser app role, per-request org scoping, and a leak test verified red-without/green-with the policy. New `integration` CI job with its own Postgres service container.
