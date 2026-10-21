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

## M0.1 — Infra up ✅ (2026-10-21)

- [x] `docker-compose.yml`: Postgres 16 + pgvector, Redis, MinIO, OTel Collector, Prometheus, Grafana — all 6 containers up and verified (pgvector extension created, MinIO console/Prometheus/Grafana all HTTP 200).
- [x] Observability — **split decision:** OpenTelemetry + Prometheus + Grafana are **in** (free, self-hosted, ~300–500MB — fits this machine's ~3.7GB Docker limit easily, covers request latency/error-rate/volume). Langfuse (LLM-specific tracing — prompts, tokens, cost, replay) is **skipped** — its full self-hosted stack doesn't fit here, and neither kbguard nor graphtrace has an instance to reuse. Revisit Langfuse deliberately once there's bigger infra or a real debugging need for it.

**What actually went wrong getting here (worth remembering):**

- `docker compose` (the v2 CLI plugin) wasn't installed — this machine only has the bare `Docker.DockerCLI` winget package, not full Docker Desktop. Fixed by downloading the official plugin binary to `~/.docker/cli-plugins/docker-compose.exe`.
- `minio/minio` on Docker Hub now requires login; `quay.io/minio/minio` also stopped allowing anonymous pulls (as of Sept 2025/2026, per community reports — no official MinIO statement found). The last free community image tag also carries a known auth-bypass CVE (CVE-2026-40344) per third-party reports, so it wasn't worth pinning anyway. Switched to `cgr.dev/chainguard/minio:latest` — verified to pull anonymously, from a legitimate vendor (not a random Docker Hub mirror account).
- Bind-mount volumes don't work against the remote `fedora-host` Docker context — the daemon resolves paths on *its own* filesystem, not this Windows machine's. Prometheus's config is baked into a custom image via `build:` instead (works over the remote context since the build context gets streamed to wherever the daemon is); the OTel Collector's config is passed as a whole YAML string via its `env:` config provider, avoiding the need for a mount entirely.
- The remote Docker engine is actually **Docker Desktop** running in its own `linuxkit` VM on the Fedora host (`Name: docker-desktop` in `docker info`) — not the native `docker.service` systemd unit. Checking `systemctl is-active docker` was checking the wrong thing entirely; it'll always show `inactive` regardless of whether the real engine is up.

## M0.2 – M0.10 — Walking Skeleton

Not started. See the build plan for the full sequence: API skeleton + auth, tenant isolation (RLS) proven via a leak test, first traced LangGraph node, the demo bank fixture, ingestion, first generation, the human review gate, first automated script, and minimal evidence hashing.
