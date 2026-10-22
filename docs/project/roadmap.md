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

## M0.7 — First real generation ✅ (2026-10-21)

- [x] `generate_tests.py`: `retrieve_context` (real async DB read, org-scoped) → `draft_manual_cases` (real Groq call, `qf-balanced` tier, strict structured output into `ManualTestCase`). Exposed via `POST /generate`.
- [x] **Done when, proven for real:** generated a case for NovaPay's transfer rule that genuinely reflects the retrieved requirement — correct ref-number format, atomic debit/credit, transaction-history entries — not a generic hallucinated case.
- [x] Full test matrix, all real (no mocking), in `apps/agents/tests/integration/test_generate_tests.py`:
  - **Positive:** generated case is grounded in the specific requirement text (asserts requirement-specific content appears, not just "a case exists").
  - **Negative:** missing chunk → `ChunkNotFoundError`, not a silent empty result or a crash.
  - **Edge:** empty instruction string still degrades gracefully; malformed request → FastAPI's own 422 (verified manually).
  - **Edge / regression guard:** RLS isolation holds for this *new* read path too (a different org_id with the same `feature_id` must not see another org's chunk) — the same mechanism M0.3 proved, now confirmed for a second consumer of `knowledge_chunks`.

**Bug caught by actually running the test suite, not just the manual curl checks:** `apps/agents/__init__.py` never got the Windows event-loop policy fix from M0.6 — this package didn't touch a database until `generate_tests.py` just now. All four tests failed identically with the same `ProactorEventLoop` error until fixed. Same oversight pattern as M0.6's `apps/knowledge` miss: the fix doesn't travel with the *concept*, it has to be added per-package, and only running real code against a real DB catches the gap.

## M0.8 — The human review gate ✅ (2026-10-21)

- [x] `human_review` node, using LangGraph's `interrupt()`, after `draft_manual_cases`. Graph compiled with a real Postgres-backed checkpointer (`AsyncPostgresSaver` — one-time table setup via `apps/agents/scripts/setup_checkpointer.py`, since those are CREATE TABLE statements LangGraph's own code runs, not something Alembic hand-writes).
- [x] `POST /generate` starts a thread, pauses at the interrupt, returns `thread_id` + the pending case. `POST /review/{thread_id}` resumes with `approve`/`edit`/`reject`, persists a `case_reviews` row (new migration, same RLS pattern as every other table).
- [x] **Done when, proven for the hard way, not assumed:** started a generation (paused at interrupt) → **killed the server process entirely** (confirmed dead — connection refused) → **started a brand-new process** → resumed the exact same `thread_id` → correct final result. This is the actual proof the build plan asks for: the checkpoint lives in Postgres, not in the first process's memory.
- [x] Full test matrix (`apps/agents/tests/integration/test_human_review.py`), all real:
  - **Positive:** generate pauses at the interrupt with the drafted case in the payload; approve resumes correctly.
  - **Negative:** `aget_state` on a thread that was never started returns an empty snapshot (the signal `/review`'s 404 is built on).
  - **Edge:** `reject` short-circuits with no final case; `edit` carries the edited case through, not the original.
  - **Regression:** an automated proxy for the manual kill/restart proof — resumes a thread using a **fully independent** `AsyncPostgresSaver` connection and compiled graph instance from the one that started it, simulating a process boundary without the flakiness of real subprocess management. If checkpointing ever silently degraded to in-memory-only, this is what would catch it.

**Known gap, stated plainly, not hidden:** LangGraph's checkpoint tables (`checkpoints`, `checkpoint_blobs`, `checkpoint_writes`) have no `org_id` column — RLS (ADR-004) doesn't cover them the way it covers every table we own. Mitigated at the application level by namespacing `thread_id` as `{org_id}:{feature_id}:{uuid}`, which is not a database-enforced guarantee. Documented in `setup_checkpointer.py`'s docstring; revisit if/when this matters for real multi-tenant isolation.

## M0.9 — First automated script ✅ (2026-10-21)

- [x] `api_automation_agent.py`: on approve/edit, generates one pytest file (real Groq call, `qf-strong` tier) asserting the business rule against NovaPay's real API, dry-runs it via subprocess (not sandboxed — explicitly not required yet per the build plan). Wired into `/review`'s approve/edit path; results persisted to a new `automated_scripts` table (same RLS pattern as everything else).
- [x] **Done when, proven twice over:**
  1. The generated pytest file genuinely runs and **passes** against NovaPay's real, running API.
  2. **Deliberately broke the assertion** (changed the expected balance delta to a nonsense value) and watched it **fail for the right reason** — a real `AssertionError` comparing real numbers, not a crash or a false pass.
- [x] **Bonus, cashing in M0.5's deferred promise:** a test for the known ownership-check gap (`fromAccountId` never verified against the caller) genuinely fails against the real API — concrete proof that generation finds real gaps, not just happy paths. Kept permanently as `test_novapay_known_gaps.py`, marked `xfail(strict=True)` so it stays informative without making CI permanently red, and **fails loudly** the moment NovaPay's behavior ever changes.
- [x] Full test matrix (`test_api_automation_agent.py`): positive (real account resolution; full generate→run→pass), negative (bad credentials raise), edge (a syntax-error script is reported as failed, not an unhandled crash in our own process), regression (asserts the prompt sent to the LLM always contains the real credentials/account IDs/OpenAPI spec — see below for why).

**Two real bugs, found by actually running the generated code against the real API, not by review:**

1. **First attempt failed at the very first real HTTP call** — the LLM invented a plausible-looking account ID (`"12345678"`) that doesn't exist, 404ing immediately. Fixed by adding `resolve_two_own_accounts()`: the agent itself probes the live API (login, scan account IDs, find two owned by the same user) and hands the LLM *real, verified* IDs — exactly the plan's §7.1 design ("the agent maps steps to the live app... to resolve real locators and endpoints"), not something to leave to the LLM to guess.
2. **Second attempt got the account IDs and field names right** (after also passing the real `fixtures/novapay/openapi.yaml` into the prompt, fixing a parallel guessed-field-name problem: `sourceAccountId`/`reference` instead of the real `fromAccountId`/`refNo`) **but invented login credentials** (`testuser`/`testpass`) — never told what to use. Fixed the same way: real credentials stated explicitly in the prompt, not left to chance.

**CI gap, resolved honestly, not hidden:** these tests need a live NovaPay, which is a separate, unvendored repo (M0.5) that CI has no access to. `tests/integration/conftest.py` adds a `requires_novapay` marker, auto-skipped (not failed) whenever `localhost:4000` isn't reachable — true both locally (if you forget to start it) and in CI (where it's never available). The CI job still runs; these specific tests just skip with a clear reason instead of erroring.

**Where this leaves the Walking Skeleton:** M0.1 through M0.9 are done — ingestion, generation, human review (with real Postgres-backed pause/resume), and automation all work end-to-end against a real external app. **M0.10 (minimal evidence hashing) is the one remaining piece**, not done in this pass — scoped as its own milestone, not folded in here.

## M0.10 — Minimal evidence hashing ✅ (2026-10-21)

- [x] `evidence.py`: on every dry run (approve/edit path), hashes the real generated script and real execution output (SHA-256), uploads both plus a manifest to MinIO (`qualiflow-evidence` bucket, real `boto3` S3 client — this app's first actual use of the object storage set up back in M0.1) under `{org_id}/{feature_id}/{case_review_id}/`. `automated_scripts` gets a new `evidence` JSONB column (migration `4495e4bd985e`) storing the manifest alongside the row it belongs to.
- [x] **Done when, proven at two levels, not just one:**
  1. **Standalone:** called `store_evidence()` directly, confirmed `verify_evidence()` independently re-fetches and re-hashes to `True`, and separately confirmed via a raw `list_objects_v2` call that all three objects genuinely exist in MinIO — not just trusting the round-trip's own math.
  2. **End-to-end through the real HTTP API:** ran the full `/generate` → `/review` (approve) flow against the live `apps/agents` server. The response came back with a populated `evidence_manifest`, and the `automated_scripts` row in Postgres has the matching `evidence` JSONB confirmed via direct `psql` query — the live wiring works, not just the unit-level mechanism.
- [x] **A genuinely useful side effect of not mocking anything:** that same end-to-end run's dry run **failed for real** — the LLM's generated assertion assumed a purely numeric 6-digit reference-number suffix (`TRF-\d{8}-\d{6}`), but NovaPay's actual refNo uses a hex suffix (e.g. `TRF-20261021-639BBE`). Evidence hashing correctly captured this as a real failing run with real hashes, proving the mechanism doesn't launder failures into false passes. Left as-is — a generation-prompt nuance for a future `api_automation_agent.py` pass, not M0.10's scope.
- [x] Full test matrix (`apps/agents/tests/integration/test_evidence.py`), all real (no mocking — every test hits the actual MinIO instance on the Fedora host):
  - **Positive:** store→verify round-trip returns `True`; stored objects are independently confirmed present via a direct bucket listing, not just `verify_evidence`'s own say-so.
  - **Negative:** a tampered manifest hash (doesn't match what's actually stored) is correctly rejected by `verify_evidence`.
  - **Edge:** empty code/output strings still hash and store without crashing; calling `_ensure_bucket()` twice against an already-existing bucket doesn't raise.
  - **Regression:** guards against S3 keys ever picking up Windows backslashes (e.g. if someone later "simplifies" the key-building with `os.path.join`) — this project has been bitten by Windows-specific path bugs enough times (the whole `ProactorEventLoop` saga) to guard against the next one proactively.
- [x] **Stale test file fixed along the way:** `test_generate_tests.py` (written for M0.7) still called a `generate_tests_graph` module-level singleton that M0.8's `interrupt()`/checkpointer work replaced with a `build_graph(checkpointer)` factory — a real collection-time `ImportError` that would have silently blocked the entire `apps/agents` test suite (one bad file aborts collection for all of it) rather than just failing its own tests. Rewritten to use `build_graph` + a real `AsyncPostgresSaver`, reading the drafted case from the interrupt payload instead of a final state key; all four of its original positive/negative/edge checks (grounding, missing-chunk, empty-instruction, RLS isolation) preserved.

**Where this leaves the Walking Skeleton:** M0.1 through M0.10 are all done. Ingestion, generation, human review (real Postgres-backed pause/resume), automation, and now evidence hashing all work end-to-end against a real external app, with real artifacts, real hashes, and real failures captured honestly. The Walking Skeleton phase is complete.

## Post-M0.10 — Generalizing automation past NovaPay ✅ (2026-10-22)

**A real gap, caught by asking "does this actually work against any app yet?", not found by me first:** `api_automation_agent.py` was never generic — it had `NOVAPAY_URL = "http://localhost:4000"` and a fixed path to `fixtures/novapay/openapi.yaml` as module-level constants, `demo`/`Demo@123` as default credentials, and `resolve_two_own_accounts()` was a hand-written function encoding NovaPay's own domain model (bank accounts, `user_id` ownership) directly in source. The plan's own M0.9 wording ("one hand-written pytest pattern," generalization explicitly deferred to Phase 1) said this plainly, but it was built without flagging the hardcoding as a decision needing sign-off first — only surfaced when asked directly whether the "works against any public or private site" philosophy matched the code. Fixed now rather than carried forward:

- [x] **`target_apps` table** (migration `8c1f5b2e4a97`, same RLS pattern as every other table) — base URL + OpenAPI spec per `org_id`/`feature_id`, registered via a new `POST /targets`. Deliberately no credentials column: auth is supplied per `/generate`/`/review` request (`ReviewRequest.target_auth`), never persisted — storing secrets at rest is a real security decision that hasn't been made yet, not something to default into quietly.
- [x] **`resolve_two_own_accounts()` deleted, replaced with a general two-step mechanism:** `generate_resolver_script()` (real LLM call) writes a small Python script that performs whatever real HTTP calls are needed to discover concrete values a *specific* case requires, given only the target's OpenAPI spec + the case itself — no domain knowledge hand-coded here. `run_resolver()` executes that script for real (same no-mocking principle as `dry_run`) and returns the JSON values it printed. NovaPay's "two accounts belonging to the same user" is now just what this mechanism happens to discover for one case, not a special code path.
- [x] **`generate_pytest_script()` is now target-parameterized** (`target: dict`, `auth: dict`) instead of reading fixed constants — the prompt no longer names NovaPay anywhere.
- [x] **Proven for real, including the honest failure modes:**
  - `generate_resolver_script` + `run_resolver` genuinely discover real account values against the live NovaPay API with zero NovaPay-specific code.
  - The full `generate_pytest_script` → `dry_run` pipeline passes against the real API, now routed entirely through a DB-seeded `target_apps` row instead of a hardcoded path.
  - **Real LLM flakiness surfaced and is worth recording honestly:** the resolver-generation call failed twice before succeeding on a third real attempt — once with unparseable JSON, once with literal `\n` escape sequences corrupting the generated Python (a `SyntaxError` on execution). Both are genuine `gpt-oss-120b` sampling issues on longer, more control-flow-heavy generated code, not a logic bug in the mechanism — the same call succeeded cleanly in an isolated run. Not fixed here; a bounded self-correction/retry loop on resolver syntax errors is exactly what Phase 1's "API automation, widened" step already calls for.
- [x] **Full positive/negative/edge/regression test matrix updated** (`test_api_automation_agent.py`): positive (resolver discovers real values generically; full pipeline passes), negative (bad credentials fail resolution honestly, no invented values), edge (`run_resolver` raises on a crashing script or on missing JSON output — mirrors `dry_run`'s syntax-error edge case), regression (prompt still contains real auth/target/spec; **and a new static guard that reads `api_automation_agent.py`'s own source and asserts the string "novapay" never appears in it again** — caught its own docstring referencing NovaPay by name on the first run, fixed immediately).
- [x] **Process fix, not just a code fix:** going forward, any hardcoded app-specific value or mock needs explicit sign-off *before* being written, not documented after the fact in the roadmap. Standing instruction, not scoped to this milestone.

**Bug caught mid-fix, worth remembering:** the migration-apply command was piped through `tail`, which exits 0 regardless of the upstream command's real exit code — a transient Postgres connection timeout during `alembic upgrade head` was silently treated as success, and the next test run failed with `UndefinedTable` before the real cause was found. Don't pipe a migration (or any exit-code-matters) command through `tail`/`head` without checking the *actual* command's exit status separately.

## Onboarding docs — a stranger can now actually run this ✅ (2026-10-22)

Flagged earlier as the real gap behind the question "is this ready for everyone to use": `docs/getting-started/quickstart.md` and `installation.md` were still stub placeholders, there was no committed Keycloak provisioning script, and the only working runbook (`Plan/manual-validation.md`) was gitignored and invisible outside this machine. Closed now, with every command actually run against the live stack rather than written blind:

- [x] **Real `installation.md`:** `.env` setup, `docker compose up -d`, `uv sync --all-packages`, applying the shared schema (`alembic upgrade head`), the LangGraph checkpointer setup script, starting all three app servers.
- [x] **`infra/keycloak/provision-realm.sh`:** codifies the `kcadm.sh` realm/client setup that previously existed only as commands run by hand once. Idempotent — tested twice against the real running Keycloak (confirmed it skips creation on a second run and still correctly re-syncs the client secret; confirmed a token request and `/protected` auth still work afterward).
- [x] **Real `quickstart.md`:** the full ingest → register target → generate → review/approve → evidence flow, every command run for real against the live stack and copied in verbatim (not written from memory of earlier test runs).
- [x] **A real `uv` workspace gotcha found and documented:** `uv sync --project apps/X` (or a plain `uv run --project apps/X ...` without `--no-sync`) silently evicts the *other* workspace members' editable installs from the shared venv — repeatedly broke this session's own server restarts (`ModuleNotFoundError` for whichever app wasn't the most recently synced) before the cause was found. Fixed in the docs: `uv sync --all-packages` once, `--no-sync` on every subsequent `uv run`.
- [x] **Two compiled-package corruptions hit and fixed along the way** (`greenlet`, then `aiohttp` — both `ImportError: cannot import name ... (unknown location)`), caused by earlier interrupted syncs in this same long session leaving partial installs behind. Fixed with `uv pip install --reinstall <package>` once nothing held a file lock on them.
- [x] **A real design gap surfaced by actually running the quickstart, not just writing it:** a `thread_id` from `/generate` can only be reviewed once — `/review` resumes the graph past its interrupt and consumes it, even when something downstream (missing target, flaky LLM call) then fails. No retry-in-place exists yet. Documented plainly in the quickstart rather than discovered the hard way by a reader; a real `/generate`-again-for-a-fresh-thread retry loop is future work, not built here.
- [x] **The full automate+evidence flow was run live, start to finish, against NovaPay** as part of testing the docs — including hitting both of today's other known flakiness modes for real (a `502` from malformed resolver code, then separately a `500`/`TimeoutExpired` from `dry_run`'s 30s budget under load from three servers running at once) before a clean run succeeded with `passed: true` and a verified `evidence` row in Postgres.
