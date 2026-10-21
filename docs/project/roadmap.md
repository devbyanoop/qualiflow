# Roadmap & status

This page is the single source of truth for "is X actually built yet?" — updated the same day any item's status changes. If anything elsewhere in these docs seems to claim more than this page shows as done, trust this page.

**Last updated:** 2026-10-21

Full detail lives in the local `Plan/qualiflow-build-plan.md` (not published — see [Contributing](contributing.md) for why the planning docs stay private). This page tracks only what's actually shipped.

## M0.0 — Repo & CI skeleton

- [x] Git repository, `main` branch
- [x] `LICENSE` (Apache-2.0)
- [x] `.gitignore` (Python, Node, secrets, MkDocs build output; planning docs kept private)
- [x] `README.md` stub
- [x] `.github/workflows/ci.yml` — proven green on an empty pipe
- [x] This documentation site (MkDocs + Material)
- [ ] Pushed to a public GitHub remote (deferred — local-only for now)

## M0.1 — Infra up

- [ ] `docker-compose.yml`: Postgres 16 + pgvector, Redis, MinIO
- [ ] Observability: **decision pending** — self-hosted Langfuse's stack (Postgres+ClickHouse+Redis+MinIO+2 app containers) doesn't fit the ~3.7GB the Docker engine reports as usable here; neither kbguard nor graphtrace already runs an instance to reuse. Leaning Langfuse Cloud free tier for now, self-host later once on bigger infra — confirm before M0.4 needs it.

## M0.2 – M0.10 — Walking Skeleton

Not started. See the build plan for the full sequence: API skeleton + auth, tenant isolation (RLS) proven via a leak test, first traced LangGraph node, the demo bank fixture, ingestion, first generation, the human review gate, first automated script, and minimal evidence hashing.
