# 0006 — Skip Langfuse for now

**Status:** Accepted (2026-10-21, M0.1)

## Context

The plan calls for LLM-specific tracing: prompts, token counts, cost, and replay, per call. OpenTelemetry + Prometheus + Grafana were already planned for general infra metrics (request latency, error rate, volume) and are free and self-hosted.

## Decision

Ship OTel + Prometheus + Grafana; skip Langfuse. Its full self-hosted stack doesn't fit this machine's real Docker memory ceiling — the same ~3.7GB ceiling that nearly took the host down during [0005](0005-self-hosted-embeddings.md)'s BGE-M3 incident — and neither of this project's sibling repos has an existing instance to reuse. Every LLM call is instead logged as one structured JSON line (tier, model, latency, tokens, cost) via `logging_utils.log_llm_call`.

## Consequences

- No prompt/response replay, no cost dashboard, no per-call trace UI yet — the structured logs are greppable but not browsable the way Langfuse's UI would be.
- Avoided repeating the exact memory incident that already happened once this project.
- Revisit deliberately once there's meaningfully bigger infra available, or a real debugging need that structured logs genuinely can't satisfy — not as a default "add it eventually."
