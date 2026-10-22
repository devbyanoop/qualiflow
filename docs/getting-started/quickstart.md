# Quickstart

The full Walking Skeleton flow: ingest a requirement, register a target app, generate a manual test case, review it, and automate it with real evidence hashing. Assumes you've completed [installation](installation.md) and all three servers are healthy.

NovaPay (the reference fixture this project was validated against) isn't published yet — step 1 works standalone against anything you ingest; steps 3+ need a real running app to point QualiFlow at.

**One thing to know before you start:** a `thread_id` from `/generate` can only be reviewed once — `/review` resumes the LangGraph execution past its pause point, consuming it, even if something downstream (a missing target, a flaky LLM call) then fails. There's no retry-in-place; call `/generate` again for a fresh `thread_id` instead.

## 1. Ingest a requirement

```bash
curl -s -X POST http://localhost:8003/ingest -H "Content-Type: application/json" \
  -d '{
    "org_id": "my-org",
    "feature_id": "my-feature",
    "content": "Describe the business rule here — whatever a BRD or user story would say."
  }'
```

Returns `{"chunk_id": ..., "doc_hash": ..., "embedded": true}`. Re-posting identical content returns `"embedded": false` — the delta-hash skip, no re-embedding.

## 2. Register a target app (for automation)

If you just want a manual test case with no automation, skip to step 3 and pass `{"action": "approve"}` with no `target_auth` — you'll get `422`, and that's fine if all you wanted was the manual case from step 3's response body before that point. To also get a real generated + dry-run pytest script, register the system under test first:

```bash
curl -s -X POST http://localhost:8002/targets -H "Content-Type: application/json" \
  -d '{
    "org_id": "my-org",
    "feature_id": "my-feature",
    "base_url": "http://localhost:4000",
    "openapi_spec": "<the target app'\''s real OpenAPI 3.0.3 spec, as text>"
  }'
```

Returns `{"target_id": ...}`. No credentials here — those go in step 4's `/review` call instead, per request, never persisted.

## 3. Generate a manual test case

```bash
curl -s -X POST http://localhost:8002/generate -H "Content-Type: application/json" \
  -d '{
    "org_id": "my-org",
    "feature_id": "my-feature",
    "instruction": "Generate a test case for this rule."
  }' | python -m json.tool
```

Returns a `thread_id` and the drafted case under `pending_review`. The graph is now paused — it won't do anything further until you review it (next step).

## 4. Review and approve

```bash
curl -s -X POST "http://localhost:8002/review/<THREAD_ID>" -H "Content-Type: application/json" \
  -d '{
    "action": "approve",
    "target_auth": {"username": "...", "password": "..."}
  }' --max-time 90 | python -m json.tool
```

`action` is `"approve"`, `"reject"`, or `"edit"` (the latter needs an `"edited_case"` body matching the case schema). Omit `target_auth` and you get `422`; include it with no target registered (step 2) and you get `404`.

With a registered target and valid `target_auth`, QualiFlow writes a small resolver script, runs it for real against your target to discover whatever concrete values the case needs (no invented IDs), writes a pytest file automating the case, and dry-runs it. The response's `automation` block has `passed`, `script_path`, and an `evidence_manifest` (SHA-256 hashes of the real script and output, stored in MinIO).

Two real, occasional failure modes worth knowing about rather than being surprised by — both mean "call `/generate` again for a fresh thread and retry," not "something is broken":

- **`502`** — the resolver or test-generation LLM call occasionally produces malformed code (escaping corruption on longer generated scripts); the response names the real failure instead of returning a broken script.
- **`500` with a `subprocess.TimeoutExpired`** — the dry-run itself has a 30s budget; on a machine already running all three servers plus infra, that can occasionally be tight.

## 5. Verify the evidence

```bash
docker compose exec postgres psql -U qualiflow -d qualiflow \
  -c "SELECT id, passed, evidence FROM automated_scripts ORDER BY created_at DESC LIMIT 1;"
```

The `evidence` column's hashes should match what `/review`'s response returned — anyone with the MinIO credentials can independently re-fetch and re-hash the stored script/output to confirm, without touching QualiFlow's code at all.
