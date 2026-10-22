# 0003 — No app identity is ever hardcoded into the automation agent

**Status:** Accepted (2026-10-22, post-M0.10)

## Context

M0.9's first version of `api_automation_agent.py` was built as a narrow proof against NovaPay specifically: a `NOVAPAY_URL` constant, a fixed path to `fixtures/novapay/openapi.yaml`, default `demo`/`Demo@123` credentials, and a hand-written `resolve_two_own_accounts()` function that encoded NovaPay's own domain model (bank accounts, `user_id` ownership) directly in source. This matched the plan's own stated scope for that milestone ("one hand-written pytest pattern," generalization explicitly deferred to Phase 1) — but it directly contradicted the project's stated goal of generating and automating tests against *any* publicly or privately hosted site, and the hardcoding was never flagged as a decision needing sign-off before being built that way. It was caught only when asked directly whether the code matched that philosophy.

## Decision

`api_automation_agent.py` never references a named application. Target apps (base URL + OpenAPI spec) are registered per `org_id`/`feature_id` via a `target_apps` table and `POST /targets`. Credentials are supplied per `/generate`/`/review` request (`target_auth`), never persisted — storing secrets at rest is a real decision that hasn't been made yet, not something to default into quietly. `resolve_two_own_accounts()` is deleted; a generic two-step mechanism replaces it: an LLM writes a small resolver script from just the target's OpenAPI spec and the case at hand, and that script is executed for real against the real target to discover whatever concrete values the case needs.

A static regression test (`test_regression_no_app_name_is_hardcoded_in_source`) reads `api_automation_agent.py`'s own source and fails if the string "novapay" ever appears in it again.

## Consequences

- The automation layer is now genuinely generic — NovaPay is just the first registered target, proven through the same path any other app would use.
- Real cost: an extra LLM call per automation attempt (the resolver step), and real LLM flakiness on longer generated scripts (malformed JSON or escaping corruption) has been observed and documented rather than hidden — surfaces as a `502`, safe to retry.
- No bounded self-correction/retry loop exists yet for a failed resolver script; Phase 1's "API automation, widened" already names this as planned work.
- **Process consequence, not just a code one:** going forward, any hardcoded app-specific value or mock requires explicit sign-off *before* being written, across all work, not just this project — this was the direct trigger for that standing rule.
