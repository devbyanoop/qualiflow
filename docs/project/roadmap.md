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

## M0.2 — API skeleton ✅ (2026-10-21)

- [x] `apps/api`: FastAPI app (`src/qualiflow_api/`), `uv` workspace root at repo root.
- [x] Keycloak container (`quay.io/keycloak/keycloak`, `start-dev`) — realm `qualiflow`, confidential client `qualiflow-api` with service-accounts (client-credentials grant) enabled, provisioned via `kcadm.sh` (not a baked realm-import JSON — same remote-bind-mount reasoning as Prometheus in M0.1).
- [x] `/healthz` (unauthenticated, 200) and `/protected` (JWT-gated via Keycloak JWKS, 401 without/invalid token, 200 with a real one) — all three states verified against a real token from the running Keycloak.
- [x] OpenTelemetry metrics wired (`FastAPIInstrumentor` + `MeterProvider` → OTel Collector → Prometheus) — confirmed real `http_server_duration_milliseconds_count` series showing up in Prometheus, broken down by endpoint and status code.
- [x] First unit tests (`apps/api/tests/test_main.py`, 3 passing) and CI updated to actually run them.

**Bugs hit and fixed (worth remembering):**

- **Clock-skew `ImmatureSignatureError`:** PyJWT rejected a genuinely valid token because Keycloak (on the remote Fedora host) and this machine's clocks differ by ~4 seconds — normal NTP drift, not a real problem. Fixed with `leeway=10` on `jwt.decode()`. If this ever needs much more leeway than that, it's a sign of an actual clock-sync problem, not something to paper over with a bigger number.
- **Port collision via Windows' exact-match socket binding:** `localhost:8000` kept routing to kbguard's already-running MkDocs dev server (bound to exactly `127.0.0.1:8000`) instead of our FastAPI app (bound to `0.0.0.0:8000`) — Windows prefers the more specific bind. Not a bug in our app; just moved the API to port 8001.
- **`Settings()` instantiated at import time with no defaults** meant `apps.qualiflow_api.main` couldn't even be imported without `.env` loaded — which broke the *first* unit test we wrote, and would have broken CI identically (no `.env` there, and these tests never call the real Keycloak anyway). Fixed by giving `keycloak_issuer`/`api_client_id` safe defaults; real runs still override them via uvicorn's `--env-file`.

## M0.3 — Tenant isolation ✅ (2026-10-21)

- [x] `organizations`/`projects` tables (Alembic migration) with Postgres RLS: `ENABLE` + `FORCE ROW LEVEL SECURITY`, a policy filtering on `current_setting('app.current_org_id', true)`.
- [x] A genuinely **non-superuser** `qualiflow_app` Postgres role for the app to connect as — created via `infra/postgres/init-app-role.sh` baked into a custom image (same remote-build pattern as Prometheus). The app never connects as the `qualiflow` superuser; migrations and test setup do.
- [x] `get_org_scoped_db` dependency: sets the tenant context per-request via `set_config('app.current_org_id', ..., true)` (the parameterized, injection-safe equivalent of `SET LOCAL`) — scoped to the transaction, so a pooled connection handed to a different request right after this one commits starts with no org set, not the previous request's org.
- [x] The leak test (`apps/api/tests/integration/test_tenant_isolation.py`) — seeds two orgs' data via the superuser (bypasses RLS entirely, confirms both rows really exist), then proves the restricted role sees only its own org, in both directions, plus the "no org set → sees nothing" failure mode. **Verified red without the policy** (manually disabled RLS, watched it fail on real cross-org leakage) **and green with it** — exactly the build plan's own bar for this test.
- [x] Wired into CI as a separate `integration` job with its own Postgres service container (role creation replicated as an explicit step, since GitHub Actions can't build `infra/postgres/Dockerfile` directly as a service image).

**Simplification, stated explicitly:** org identity is currently just the Keycloak client's `azp` claim — "one Keycloak client = one org" — until a real `Organization`/membership model exists where a user can belong to one. Revisit when multi-user orgs matter, not before.

**Bugs hit and fixed:**

- `sqlalchemy>=2.0` alone doesn't pull in `greenlet`, which its asyncio support needs — fixed by depending on `sqlalchemy[asyncio]` instead.
- Alembic has no equivalent of uvicorn's `--env-file` flag, so `Settings()` silently fell back to its `"changeme"` default password when migrations ran — fixed by loading `.env` directly inside `settings.py` (via `python-dotenv`), so every entry point (alembic, pytest, uvicorn) behaves identically.
- **psycopg's async driver can't use Windows' default `ProactorEventLoop`** — only `SelectorEventLoop`. This would have broken the real running app too (uvicorn on Windows defaults to Proactor), not just this test, so the fix lives in `qualiflow_api/__init__.py` (runs before any submodule, from any entry point) rather than a test-only fixture.

## M0.4 — First LangGraph node ✅ (2026-10-21)

- [x] `apps/agents`: new workspace member (LangGraph + LiteLLM + Pydantic), separate from `apps/api` per ADR's control-plane/agent split.
- [x] `tiers.py` — the tier-alias resolution §15.3 describes (`qf-fast` → a real model string), using a **Groq** preset rather than the plan's default OpenAI one — exactly the pluggability §15.3 anticipates (each tenant maps tiers to whichever provider they have a key for).
- [x] One-node graph (`hello_graph.py`): calls the LLM with OpenAI-style strict JSON-schema structured output, validated into a one-field Pydantic model.
- [x] No tracing backend (§0) — `logging_utils.py` logs tokens/latency/cost as one JSON line per call instead.
- [x] Exposed via `GET /hello/{name}` on a FastAPI app (port 8002) — tested live, real response: `{"greeting": "Hello Anoop, hope you're having a wonderful day!"}`.
- [x] Test is **deliberately not mocked** — it makes a real call to Groq. Wired into CI as its own `agents` job with a `GROQ_API_KEY` secret (not yet addable — no GitHub remote exists yet, per the M0.0 local-only decision; add it once pushed).

**Clarified, not just decided — grounded in the plan's own words:** `apps/agents` calling a real LLM does **not** contradict the plan's determinism promise. §3 principle 1 ("AI authors and maintains; deterministic engines execute") and ADR-002 ("No LLM in the hot path of regression execution") are about **generated test execution** — the downstream artifact an agent produces, which runs with zero LLM calls once it exists (see M0.9's own note on this). `apps/agents` *is* the authoring layer; calling a real LLM is its job, not an exception to the rule.

**Bugs and real-world gaps hit along the way:**

- `apps/agents` had no `.env`-loading mechanism at all (never needed one before) — added the same `load_dotenv()`-in-`__init__.py` pattern as `apps/api`.
- Guessed Groq model names from memory (`llama-3.1-8b-instant`, `llama-3.3-70b-versatile`) — **wrong**, not available on this account. Queried `GET /v1/models` with the real key instead of guessing again; landed on `openai/gpt-oss-20b`/`120b`, which Groq actually serves.
- LiteLLM's `completion_cost()` doesn't have `groq/openai/gpt-oss-20b` mapped (its nested `openai/` confuses LiteLLM's own provider-prefix detection, reporting `custom_llm_provider=openai` instead of `groq`) — added a small, explicitly-cited manual fallback price table (`$0.075`/`$0.30` per 1M input/output tokens, cross-checked against three independent sources) rather than silently report no cost or guess a number.

## M0.5 — The fixture everything else tests against ✅ (2026-10-21)

**Architecture decision made this milestone, not just executed:** the original plan had QualiFlow build and own a `demo-apps/` folder inside its own repo. Rejected — QualiFlow is standalone infrastructure that tests *someone's* app, the same way it would for a real client; bundling a target app inside the tool that tests it blurs that distinction. **NovaPay** (`D:\AutomationTool\novapay`, already built for Qestra/niti) is the reference fixture instead — a separate repo, pointed at over the network, never vendored in. `qualiflow-plan.md` and `qualiflow-build-plan.md` are both updated throughout to reflect this.

- [x] Confirmed NovaPay runs (`node server.js`, port 4000) and exercised its real endpoints with `curl` — login, accounts, customers, transfers — rather than assuming behavior from source alone.
- [x] `fixtures/novapay/openapi.yaml` — written from the verified running app, **validated clean** with `openapi-spec-validator` (caught a real spec bug: `exclusiveMinimum: 0` is OpenAPI 3.1/JSON-Schema-2020-12 syntax, not valid under 3.0.3's dialect, which needs `minimum` + a boolean `exclusiveMinimum`).
- [x] `fixtures/novapay/brd-transfer-rule.md` — the *intended* fund-transfer rule, written as a BRD would state it, not a description of current bugs.

**Real findings, verified against the running app, not guessed from reading code:** NovaPay's `POST /api/transfers` (the JSON API path) diverges from its own `POST /transfer` (HTML form path) in three ways — it doesn't reject `fromAccountId == toAccountId`, doesn't verify the source account belongs to the caller (any logged-in user can empty any account by id), and doesn't write transaction-history rows for either leg. `GET /api/accounts/:id` has the same ownership gap. These are documented in `openapi.yaml`, not fixed — NovaPay isn't QualiFlow's to patch. **Deliberately left in place as a future milestone's payoff:** once case generation (M0.7) and automation (M0.9) exist, a negative test for "can't transfer from an account you don't own" should be generated, run, and genuinely fail against the real API — a concrete demonstration that generation finds real gaps, not just confirms happy paths.

## M0.6 — Ingestion v0 ✅ (2026-10-21)

- [x] `apps/knowledge`: new workspace member. `POST /ingest` — hash → delta-hash skip check → embed (only if new) → store in pgvector with `org_id`/`feature_id`.
- [x] **Done when, proven for real:** first ingest of the NovaPay transfer BRD → `{"embedded": true}`; identical second ingest → `{"embedded": false}`, same `chunk_id` both times. Verified the stored row directly in Postgres: real 384-dim vector, exactly one row despite two calls.
- [x] Automated integration test (`apps/knowledge/tests/integration/test_delta_hash.py`) captures this proof — real DB, real embeddings call, no mocking. Wired into a new `knowledge` CI job.

**Embeddings provider — resolved through a real incident, not a clean decision:**

The locked choice was OpenAI `text-embedding-3-large`; we only have a Groq key, and Groq has no embeddings endpoint at all (confirmed via its `/v1/models` listing). The plan's own fallback — self-hosted **BGE-M3** — became primary, promoted ahead of schedule rather than "later for air-gapped."

BGE-M3 (2.2GB on disk) **OOM-killed repeatedly** (`exit 137`) on this machine's Docker engine, which only had ~3.7GB usable (the same ceiling flagged for Langfuse back in M0.1). What followed, in order:

1. Raised Docker Desktop's VM memory to 8192 MiB via `~/.docker/desktop/settings-store.json` (`MemoryMiB`, confirmed the correct key empirically — the file had no memory key by default). BGE-M3 still OOM'd.
2. Raised further to 11264 MiB. Still OOM'd, identically, despite the other 7 containers combined using only ~1.7GB — strong signal that BGE-M3's actual CPU/ONNX warmup footprint on this runtime is far larger than its disk size suggests, not simply "not enough RAM allocated."
3. **This nearly broke the host.** At 11GB allocated, the Fedora host's own free memory dropped to 189Mi with swap in use — Docker Desktop's GUI stopped responding for the user. Diagnosed by checking `free -h` directly; confirmed by stopping Docker Desktop and watching available memory jump from 2.7Gi to 13Gi instantly.
4. Reverted to 8192 MiB. Learned along the way that `docker desktop restart` does **not** reliably reload `settings-store.json` from disk (a second edit was silently ignored, with the service re-writing its own stale cached value back over it) — a clean **`stop` → edit file → `start`** sequence is required for a settings change to actually take effect.
5. **Abandoned BGE-M3** rather than keep escalating memory with diminishing returns. Switched to `sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2` (~470MB) on the same TEI image — warmed up in seconds, no OOM. 384 dimensions, not BGE-M3's 1024 — the `knowledge_chunks` migration was corrected before applying it, confirmed against the running service rather than assumed.

**The Windows event-loop bug this milestone forced us to actually understand (not just patch again):**

M0.3's `__init__.py` fix (`asyncio.set_event_loop_policy(WindowsSelectorEventLoopPolicy())`) was real but had never been tested through a *live* server touching the database — only through pytest. Running `apps/knowledge`'s server for real exposed why: **uvicorn's own `Server.run()` directly instantiates `asyncio.ProactorEventLoop`** on Windows (`uvicorn/loops/asyncio.py`, whenever `workers==1` and reload is off) — it never consults the event-loop *policy* at all, so no policy-based fix can touch this code path. Confirmed by reading uvicorn's source directly rather than guessing further. The real fix: stop using `uvicorn.run(app, ...)`; build the `Config`/`Server` objects directly and drive `server.serve()` on our own explicitly-constructed `SelectorEventLoop`. Applied to `apps/knowledge/main.py`, and proactively to `apps/api/main.py` too (which has the identical latent bug — no DB-touching endpoint is wired up there yet, so it was never triggered, but it will be).

**One more real bug, caught only by actually running the INSERT:** `:embedding::vector` in a SQLAlchemy `text()` statement silently fails to bind — SQLAlchemy's parameter parser reads `::` as Postgres's cast operator and leaves `:embedding` completely unprocessed (not a compile error; the literal string reaches psycopg, which then fails with a syntax error). Fixed with a space: `:embedding ::vector`.

**CI gap closed along the way:** GitHub Actions' `services:` has no way to pass CLI arguments to a container. Confirmed via the TEI image's own `--help` that every flag has an environment-variable equivalent (`--model-id` → `MODEL_ID`), tested locally before trusting it in CI.

## M0.7 – M0.10 — Walking Skeleton

Not started. See the build plan for the full sequence: first generation, the human review gate, first automated script, and minimal evidence hashing.
