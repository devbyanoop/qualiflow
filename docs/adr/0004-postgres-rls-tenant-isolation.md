# 0004 — Postgres RLS + a non-superuser app role for tenant isolation

**Status:** Accepted (2026-10-21, M0.3)

## Context

QualiFlow is multi-tenant from the start. Application-level filtering (a `WHERE org_id = ?` on every query) is one unguarded query away from a real cross-tenant data leak — it depends on every developer, on every query, forever, getting it right.

## Decision

Every tenant-scoped table has Postgres Row-Level Security `ENABLE`d and `FORCE`d, with a policy filtering on `current_setting('app.current_org_id', true)`. That setting is applied per-request via `set_config('app.current_org_id', ..., true)` — the parameterized, injection-safe equivalent of `SET LOCAL`, scoped to the transaction so a pooled connection handed to the next request starts with no org set, not the previous request's.

Critically, the application **never** connects to Postgres as the superuser — only as a restricted `qualiflow_app` role, created via a custom `infra/postgres/` image. Superusers bypass RLS unconditionally, so this isn't optional: RLS without a non-superuser app role provides no real isolation at all.

## Consequences

- Isolation is enforced by the database, not by every query author remembering to filter correctly.
- Proven by an actual leak test, not just a code review: verified **red** with the RLS policy manually disabled (confirmed real cross-org leakage), and **green** with it restored.
- Known gap, not hidden: LangGraph's own checkpoint tables (`checkpoints`, `checkpoint_blobs`, `checkpoint_writes`) have no `org_id` column — this RLS pattern doesn't cover them. Mitigated at the application level only (thread IDs namespaced `{org_id}:{feature_id}:{uuid}`), which is not a database-enforced guarantee. Revisit if/when this matters for real multi-tenant isolation.
- Org identity is currently simplistic — "one Keycloak client = one org," via the `azp` claim — until a real organization/membership model exists where a user can belong to one. A deliberate simplification, revisit when multi-user orgs matter.
