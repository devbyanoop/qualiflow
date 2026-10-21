# QualiFlow — Build Plan

**Companion to `qualiflow-plan.md` · how to actually build it, one step at a time**

This document turns the product/engineering plan into an ordered sequence of small, checkable build steps. The plan says *what* and *why*; this says *what to type, in what order, and how to know it worked*. Every step names the plan section it implements, so you can always go back to "why does this exist?"

**How to use this:**

- Work top to bottom. Don't start a step until the previous one's "done when" is true.
- Each milestone ends with a **Concepts to own** list — if you can't explain those in your own words, re-do the step before moving on. This is the point: understanding the mechanism, not just getting it green.
- Resist adding anything from Phase 2+ of the main plan while you're in Phase 0/1 here. Scope creep is the #1 risk on the plan's own risk register (§28) — this document is the guardrail.
- Open-source from commit zero (Apache-2.0, locked in §22.1). You are not "building in private, then open-sourcing" — every commit from Day 0 is public-repo quality.

---

## 0a. Tech stack at a glance

Full rationale lives in `qualiflow-plan.md` §15.2 — this is that table, reproduced here so you don't have to flip files while building.

| Layer | Choice |
|---|---|
| Agent orchestration | **LangGraph** (Python) |
| Tool access | **MCP** — Microsoft's Playwright MCP (web); custom MCP servers for Appium / API spec / test repo / DB schema |
| LLM gateway | **LiteLLM** (proxy) — multi-provider, BYOK, budgets, tier aliases |
| Backend API | **FastAPI** + Pydantic v2 |
| Background jobs | **Redis + Celery** to start → **Temporal** at scale |
| Database | **PostgreSQL 16 + pgvector** |
| Search | Postgres full-text + pgvector (hybrid) + **bge-reranker-v2-m3** reranker |
| Embeddings | **OpenAI `text-embedding-3-large`** now; self-hosted **BGE-M3** for air-gapped later |
| Document parsing | **Docling** (pure OSS, local); Unstructured as a format-gap fallback; openpyxl/pandas for spreadsheets |
| LangGraph checkpoints | `langgraph-checkpoint-postgres` |
| Object storage | **S3** (MinIO locally); Object Lock for WORM later |
| Frontend | **Next.js + TypeScript + shadcn/ui**, next-intl (i18n) |
| Auth | **Keycloak**, self-hosted |
| Runners | Docker images on **Kubernetes Jobs** |
| Mobile devices | Emulators → device farms (BrowserStack / Sauce Labs / AWS Device Farm) — Phase 3+ |
| Reports & email | HTML → PDF (headless Chromium), SES/SendGrid/Postmark — Phase 2+ |
| Observability | **OpenTelemetry**, Grafana/Prometheus, **Langfuse** (self-hosted) |
| Infra as code | **Terraform** + Helm |
| CI/CD | GitHub Actions |
| Billing | Stripe — Phase 2+ |
| Python tooling | **uv** workspaces |
| JS tooling | **pnpm** workspaces |
| License | **Apache-2.0** |

Not every row is needed on Day 1 — Keycloak, Postgres, Redis, MinIO, Langfuse, FastAPI, and LangGraph are the Walking Skeleton's entire footprint (§1 below). Billing, device farms, Temporal, Terraform/Helm, and WORM storage are explicitly later-phase rows; don't stand them up early.

## 0. Decisions locked before you write code

These were ambiguous ("X or Y") or missing in the plan. They're now resolved directly in `qualiflow-plan.md` — this is just the one-screen summary so you don't re-litigate them mid-build.

| Area | Locked choice | Where in the plan |
|---|---|---|
| License | Apache-2.0 | §22.1 |
| Auth | Keycloak, self-hosted | §15.2 |
| Observability | Langfuse, self-hosted | §15.2 |
| Embeddings | `text-embedding-3-large` (OpenAI) now; BGE-M3 self-hosted later for air-gapped | §15.2 |
| Reranker | `bge-reranker-v2-m3`, self-hosted | §5.2 |
| Tenant isolation | Postgres RLS via `app.current_org_id` session var, set by gateway middleware per request | §15.6 ADR-004 |
| Secrets (Phase 0–1 only) | `.env` + dotenv — fine until a real client's DB credentials show up (Phase 2 → Vault) | §18 |
| Python tooling | `uv` workspaces | §21 |
| JS tooling | `pnpm` workspaces | §21 |
| MCP for web | Microsoft's official Playwright MCP server (external dep, not vendored) | §21 |
| Default export schema | title / preconditions / steps / test data / expected result / priority / tags | §13.2 |

If you hit a point where one of these feels wrong once you're in the code, change it — but change it deliberately and update both documents, don't let it drift silently.

---

## 0b. Testing strategy for QualiFlow's own code

The plan's §20 defines *eval suites* — they measure AI output quality, not whether the software works. Underneath them you still need the ordinary test pyramid, and it needs to exist from M0.0 onward, not get bolted on later. Four layers, each a different cost and cadence:

| Layer | Tool | Runs | Calls a real LLM? |
|---|---|---|---|
| Unit | pytest (Python apps/packages); Vitest (`apps/web`) | every push, in CI, seconds | No — LLM calls are mocked |
| Integration | pytest against a real Postgres (a service container in CI, same image as `docker-compose.yml`) | every push, in CI, ~1 min | No — tests RLS, migrations, API contracts against a real DB, not AI quality |
| Eval suites (§20) | Langfuse-traced runs against golden datasets | only when a prompt, graph, or model preset changes (path-filtered CI job) | Yes — the one layer that spends real tokens, deliberately kept off the default path |
| Exploratory / manual | you, using the product the way a QA lead would | ad hoc, every milestone | N/A |

- M0.0's CI workflow starts with two jobs: `unit` and `integration`. Add the `eval` job around M0.7, once there's a real `generate_tests` graph to evaluate — path-filter it to `apps/agents/**` and `packages/model-presets/**` so a frontend CSS change doesn't trigger token spend.
- Exploratory testing is where 16 years of manual-testing instinct is the most direct asset on this project: every milestone's "done when" in §1 below is something to actively try to break (wrong input, killed process mid-run, two concurrent requests) before trusting a green checkmark.

## 0c. Testing the tool against a real website (Phase 2+, not now)

This becomes possible once the `ui_automation_agent` and Playwright MCP integration exist — that's Phase 2 (§26 of the main plan), not the Walking Skeleton or the API-only MVP. Two decisions to make when you actually get there:

- **Target choice:** point it at a site *built to be automated against* — e.g. `the-internet.herokuapp.com`, `saucedemo.com`, `parabank.parasoft.com`, `demoqa.com`, `automationexercise.com` — never an arbitrary live production site you don't have explicit permission to test. Generated automation hitting a real company's site risks violating its terms of service, tripping rate limits or bot defenses, or — if any generated step happens to be a write action — mutating data you don't control. The plan's production-safety principle (§8.5, §3 principle 9: "safe by default") is written for *client* environments, but the same caution applies to any third-party site.
- **Treat it as a named milestone, not an afterthought:** "first external target" — point the web agent at one of the practice sites above and confirm locator-resolution and self-healing hold up against real-world markup you didn't write (the demo bank's HTML is nothing like it) before claiming the web executor actually works.

## 1. The Walking Skeleton (before "Phase 0" officially starts)

The plan's Phase 0 exit criterion is "`docker compose up` gives a working authenticated API." That's necessary but not sufficient for *understanding the architecture to the core* — it doesn't touch LangGraph, RAG, or the review gate. Before the official phases, build one ugly, minimal, end-to-end slice through **every architectural layer** in the stack diagram (§15.1). This is the single most valuable week you'll spend: it's where the abstractions in the plan stop being prose and become code you've typed.

Target: one BRD paragraph → one generated test case → one human approval → one generated pytest script → one pass/fail result → one hashed evidence file. No UI polish, no multi-tenancy edge cases, no second language. Just prove the pipe connects.

### M0.0 — Repo & CI skeleton

M0.3 below says the tenant-isolation leak test "lives in CI" — that's only true if CI exists *before* M0.3. Build the pipe for proof, before you have anything that needs proving.

- Create the GitHub repo (public, since OSS-from-commit-zero is the call made in §22.1). Apache-2.0 `LICENSE` file, `.gitignore` (Python + Node), a one-paragraph `README.md` stub.
- `.github/workflows/ci.yml`: on push/PR — checkout, set up `uv` and `pnpm`, run lint, run tests. It's fine (expected, even) that this passes trivially with zero tests in it right now.
- **Done when:** a trivial commit pushed to GitHub triggers the Actions run and shows green — before a single line of product code exists.
- **Concepts to own:** why you want "CI is broken" and "my test is broken" to never be two unknowns you're debugging at the same time. Standing up the empty pipe first means every later red run has exactly one possible cause.

### M0.1 — Infra up
- `docker-compose.yml`: Postgres 16 (+pgvector extension), Redis, MinIO, Langfuse (self-hosted stack).
- **Done when:** `docker compose up` succeeds; you can `psql` in and `CREATE EXTENSION vector;`; you can open the MinIO console and the Langfuse UI in a browser.
- **Concepts to own:** why pgvector lives *inside* Postgres instead of a separate vector DB (ADR consequence: one database, one backup story, relational + vector joins for free).

### M0.2 — API skeleton
- `apps/api`: FastAPI app, `/healthz`, Pydantic v2 settings from env.
- Keycloak container added to compose; one realm, one client, OIDC discovery endpoint reachable. Wire a single protected endpoint that rejects without a valid token.
- **Done when:** unauthenticated request to the protected endpoint → 401; authenticated (via a token you pull manually from Keycloak's token endpoint) → 200.
- **Concepts to own:** the OIDC token flow end to end (what's actually inside a JWT; how the API validates it without calling Keycloak on every request — JWKS caching).

### M0.3 — Tenant isolation, proven before anything else is built on top
- Alembic migration: `organizations`, `projects` tables. RLS policy on both, filtering on `current_setting('app.current_org_id')`.
- Gateway middleware: reads org from the authenticated token, runs `SET app.current_org_id = ...` at the start of each request's DB session.
- **Write the leak test now, not later:** seed two orgs, two projects; as org A's session, assert org B's project is invisible — not filtered-in-application-code invisible, *RLS-invisible* (query with RLS bypassed should still see it; query through the normal path should not).
- **Done when:** that test is red without the policy, green with it, and lives in CI.
- **Concepts to own:** the difference between "the API happens to add a WHERE clause" and "the database physically cannot return another tenant's row no matter which code path queries it." This is the one mechanism the whole multi-tenancy security story (§18) rests on — get it solid here, cheaply, before 40 tables depend on the pattern.

### M0.4 — First LangGraph node, traced
- `apps/agents`: a trivial one-node graph — takes a string, calls an LLM via LiteLLM (OpenAI preset, `fast` tier), returns structured output (a Pydantic model with one field). Exposed behind one FastAPI endpoint.
- Langfuse tracing wired so the call shows up with tokens, latency, and cost in the Langfuse UI.
- **Done when:** you can hit the endpoint, see a real LLM response, and see the matching trace in Langfuse with cost in dollars.
- **Concepts to own:** what LiteLLM's tier alias (`qf-fast`) actually resolves to underneath (§15.3) — trace it yourself from alias → preset → real model string. Structured output via Pydantic — see what happens when the model returns something that fails validation (force it with a weird prompt) so the failure mode isn't a surprise later.

### M0.5 — The fixture everything else tests against
- `demo-apps/bank`: the smallest possible API (e.g. 2 endpoints: create a loan application, get EMI for a loan) with an OpenAPI spec. One BRD paragraph in English describing the EMI rule in prose (e.g. "EMI = reducing-balance formula, rounded to nearest rupee").
- **Done when:** the demo API runs in its own container, `curl` against it works, the OpenAPI spec validates.
- **Concepts to own:** nothing new here — but notice this is the thing §4.2's "feature context pack" and §7.5's "business rule spec" will both eventually point at. Keep it tiny on purpose; you'll extend it, not replace it, through every later phase.

### M0.6 — Ingestion v0 (no RAG yet, just the pipe)
- `apps/knowledge`: endpoint to upload the BRD paragraph → chunk (even a single chunk is fine at this size) → hash → embed (`text-embedding-3-large`) → store in pgvector with `org_id`, `feature_id` columns.
- **Done when:** the row exists in Postgres with a real embedding vector, and re-uploading the identical text produces **zero** new embedding calls (prove the document-hash skip from §5.1 works, not just that it's described in the plan).
- **Concepts to own:** why delta hashing matters economically (§5.1) — calculate by hand what re-embedding a 200-page BRD on every edit would cost vs. hashing.

### M0.7 — First real generation
- Extend the M0.4 graph into the real `generate_tests` shape (§16.2), but collapsed: `retrieve_context` (pull the one chunk) → `draft_manual_cases` (LLM, `balanced` tier, structured output = `ManualTestCase` Pydantic model) → stop (no review node yet).
- **Done when:** calling the endpoint with "generate a case for the EMI calculation" returns one structured, schema-valid test case object, traced in Langfuse, and you can see the retrieved chunk's text was actually used (not hallucinated from nothing — check the prompt that was sent).
- **Concepts to own:** the full `GenerateState` TypedDict (§16.2) — type every field yourself even though you're only using three of them right now; the rest exist because of gates you'll add next.

### M0.8 — The human gate
- One LangGraph `interrupt()` after `draft_manual_cases`. A bare endpoint (or even a CLI script) to list pending cases and POST an approve/edit/reject decision. Persist a `CaseReview` row with the decision and (if edited) the diff.
- **Done when:** the graph actually pauses — you can kill and restart the API process mid-review and the pending case is still there waiting (this is the checkpoint-postgres behavior from §15.2 — prove it, don't assume it).
- **Concepts to own:** why `interrupt()` + Postgres checkpointing is categorically different from "save to a table and poll" — the graph's *entire execution state* resumes, not just a flag you check.

### M0.9 — First automated script, from an approval
- On approve, route to a minimal `api_automation_agent`: generate one pytest file (using `httpx` against the demo bank API) asserting the EMI value matches, using the validation-kit's calculation-checker pattern from §7.5 even if the validation kit package itself is just a stub function right now.
- Dry-run it in a subprocess (not a sandboxed container yet — that's a Phase 0/1 hardening step, not a Walking Skeleton requirement).
- **Done when:** the generated pytest file actually runs and passes against the real demo bank API, and you can deliberately break the demo API's EMI rounding to watch it fail for the right reason.
- **Concepts to own:** §3 principle 1 ("AI authors and maintains; deterministic engines execute") — notice concretely that once this file exists, running it again needs zero LLM calls.

### M0.10 — Evidence, minimally
- SHA-256 hash the test run's output + the script version; write a `manifest.json` next to it in MinIO.
- **Done when:** you can show someone the manifest and the artifact and they could, in principle, verify the hash without touching QualiFlow at all.
- **Concepts to own:** this is a toy version of §12.1 — notice everything missing from the real thing (WORM, hash-chaining, e-signatures) so Phase 4's compliance pack isn't a surprise, it's "the things we deliberately skipped in week one."

**Walking Skeleton exit:** you have, end to end, in your own repo, with nothing stubbed out at the architecture level: ingestion → RAG retrieval → generation → human review (with real pause/resume) → automation → execution → evidence. Everything from here on is *widening* this pipe (more sources, more languages, more executors, more roles) — not building new pipes. That's the single biggest thing to internalize before Phase 0 proper.

---

## 2. Phase 0 proper — Discovery & Foundation (§26, Months 0–1.5)

You've already done the *technical* half of Phase 0's exit criterion via the Walking Skeleton. What's left is the parts that aren't code:

1. **Customer discovery (§24.1).** 15–20 interviews, run in parallel with the build, not after it — you want real pains shaping Phase 1, not your own assumptions. Write up each one same-day while it's fresh; a pattern across 15 scattered memories is useless, a pattern across 15 structured notes is your roadmap.
2. **Legal basics.** Company/IP/trademark search for the name (flagged as a working name in the plan's header) — do this before the GitHub org name and domain are public, reversing it later is expensive.
3. **ADR-001 through ADR-016**, written as actual files in `docs/adr/`, one per decision, dated, with the "why" — not copy-pasted from the plan, but written in your own words as you hit each decision for real. The two you already have hard evidence for from the Walking Skeleton: ADR-004 (RLS) and ADR-008 (tiers, not models) — write those first since you can cite your own test output.
4. **Harden the skeleton into the real Phase 0 deliverables (§26):** i18n scaffolding in the Next.js shell (even English-only, externalize every string now — §15.6 ADR-014, retrofitting is the expensive path the plan explicitly warns about), environment classification + production-block middleware (§8.5 — this is a guardrail, build it before there's anything dangerous to guard), the bilingual (EN+AR) version of the demo BRD.

**Phase 0 exit (per plan, now concrete):** `docker compose up` → authenticated, RLS-proven, i18n-scaffolded API; Walking Skeleton still green in CI; 10+ interviews written up; ADRs 1–16 drafted.

---

## 3. Phase 1 — MVP build order (§26, Months 1.5–5)

The plan lists Phase 1's scope as a flat bullet list. Here it's sequenced by dependency — what has to exist before the next thing is buildable — not by the plan's section order.

1. **Knowledge base, widened.** Take M0.6 from "one paragraph" to real documents: PDF/DOCX/XLSX parsing (Docling/Unstructured), structure-aware chunking by heading, hybrid search (pgvector + Postgres full-text), the `bge-reranker-v2-m3` reranker. Re-run the delta-hash proof from M0.6 against a *revised* document — confirm only changed chunks re-embed.
2. **`generate_tests`, widened to the real graph (§16.2).** Add the `mode` branch (`new` vs `convert` — CSV/Excel import using the locked default schema from §13.2), few-shot retrieval of prior approved cases once there are any, and the full review-decision set (approve / edit / reject / manual-only) from §6.2, each persisting a `CaseReview` row that becomes training signal data even before §6.3's learning job exists to consume it.
3. **API automation, widened.** From one hand-written pytest pattern to the real `api_automation_agent` node (§16.2): resolve real endpoints from the OpenAPI spec, use page-object-equivalent structure for API clients, run the dry-run loop with bounded self-correction (§16.3 — cap attempts, log every retry so you can see the escalation behavior from §15.3 actually trigger).
4. **Validation kit v0 (§7.4).** Pull the EMI-checking logic out of the one-off pytest file from M0.9 into a real installable package (`packages/validation-kit`) with a read-only DB connector and a UI/API ↔ DB field-compare helper. This is the first thing that should feel reusable rather than bespoke — if it doesn't, the abstraction is wrong, fix it now while there's only one caller.
5. **Runner image + real evidence (§12.1, §19).** Move dry-run execution from an in-process subprocess (M0.9's shortcut) into an actual ephemeral container run via a runner image. Widen the M0.10 manifest into the real evidence package shape: context, step evidence, integrity hashes — still no WORM/signatures (that's Phase 4), but the *shape* should already match so Phase 4 extends it instead of replacing it.
6. **Cost tracking (§22.3).** Every LLM call from here on logs tokens and computed cost against the actions table in §22.3 — you already have the Langfuse traces from M0.4 onward; this step is building the aggregation/dashboard on top, not new instrumentation.
7. **Reports v0 (§11.1).** Two views only: QA engineer (review queue + failures) and QA lead (coverage + approval rates). Resist adding the other seven roles from §11.1's table — they're not in Phase 1 scope and the plan is explicit about that.
8. **Open-source the validation kit and MCP servers (§22.1).** By this point they've been exercised by real use inside the monorepo for weeks — publish them as their own installable packages with the Apache-2.0 license, a README, and the eval cases that already exist from step 2 onward as proof they work, not as a separate documentation exercise.

**Phase 1 exit (per plan, §26):** 2–3 design partners using it on a real project; ≥ 60% first-pass approval of generated cases measured on partner data (not your own demo bank — the demo bank proves the pipe works, partner data proves the product works); cost per case measured; first public demo video.

---

## 4. Beyond Phase 1

Phases 2–5 are already well-ordered in `qualiflow-plan.md` §26 (web automation + healing + TMS sync → mobile + release intelligence + migration + Arabic → compliance + regulated enterprise → scale/ecosystem). Don't pre-build this document's level of granularity for them yet — write the next phase's step-by-step the same way you wrote this one, **after** Phase 1 exits, using what you learned from design partners to correct the plan's assumptions (§24.1's point exactly: expect "Must" items to move to "Later"). Re-planning Phase 2 before Phase 1 ships is itself a form of scope creep.

One thing worth deciding now, cheaply, because it's a one-line note rather than a build step: when you get to Phase 3's mobile work, resolve the demo-mobile-app sourcing question flagged inline in §26 of the main plan before you're mid-sprint and blocked on it.

---

## 5. Anti-scope-creep checklist

Re-read before starting each new milestone above. If the answer to any of these is "yes," stop and cut:

- Am I adding a second language, a second executor, or a second domain pack before the first one works end-to-end on the demo bank?
- Am I building UI polish for a flow that has zero real users yet?
- Am I reaching for Vault, WORM storage, or e-signatures before Phase 2/4 respectively?
- Am I generalizing the validation kit for a use case I don't have yet, instead of the one in front of me?
- Could a design-partner interview answer this better than guessing?

---

*Companion document — update it the same cadence as `qualiflow-plan.md`: after every phase exit and every design-partner conversation.*
