# 0007 — Environment classification, production blocked by default

**Status:** Accepted (2026-10-22, Phase 0)

## Context

Agents and generated tests make real HTTP calls against whatever system they're pointed at (see [0003](0003-no-hardcoded-target-app.md)). Nothing before this decision distinguished a throwaway dev/QA system from a real production one — a target was just a URL and a spec. The plan's §8.5 names this directly: "Agents and tests can delete data, trigger payments, or send emails if an environment is wired to real services." The guardrail needs to exist *before* there's anything dangerous to guard, not retrofitted after an incident.

## Decision

Every `target_apps` row must be classified as exactly one of `production`, `pre-production`, `uat`, `qa`, `dev` — required at registration (`POST /targets`), with no default. Enforced twice: a Pydantic `Literal` at the API layer, and a Postgres `CHECK` constraint at the database layer (migration `b2a7c419e3d5`), so a caller that bypasses the API some other way still can't land an unclassified or misspelled value.

When `/review` is asked to approve or edit against a target classified `production`, it's blocked outright (`403`) unless the request explicitly sets `"allow_production": true` — the "opt-in" the plan calls for.

## Consequences

- A target can no longer silently be production without anyone having said so.
- **What this decision deliberately does NOT do, stated plainly:** `allow_production: true` only lifts the block. It does not verify the generated script is actually read-only, which is §8.5's separate "Action policies" guardrail (allowed domains, blocked HTTP methods like `DELETE`, sandboxed payment/email side effects, rate limits, a kill switch) — none of that exists yet. Today, an opted-in production run can still perform real writes. This is a known, bounded gap, not an oversight: it's listed in §8.5's own table as a distinct guardrail from environment classification, and building it is separate future work, not silently assumed to be covered by this ADR.
- Full positive/negative/edge/regression test matrix in `test_environment_classification.py`, including a defense-in-depth check that a raw SQL insert bypassing the API still hits the database's own constraint.
