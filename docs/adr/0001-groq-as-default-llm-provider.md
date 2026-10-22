# 0001 — Groq as the default LLM provider, not OpenAI

**Status:** Accepted (2026-10-21, M0.4)

## Context

The original plan locked OpenAI as the default LLM provider. In practice, only a Groq API key was available when the Walking Skeleton started, and the tier abstraction (`qf-fast` / `qf-balanced` / `qf-strong`, resolved to a real model string per provider) was already designed to be pluggable — each tenant maps tiers to whichever provider they have a key for, so this was never meant to be a single hardcoded choice.

## Decision

Default the tier presets to Groq's `openai/gpt-oss-20b` (`qf-fast`) and `openai/gpt-oss-120b` (`qf-balanced`/`qf-strong`), resolved through LiteLLM. Model names were confirmed by querying Groq's real `/v1/models` endpoint, not guessed from memory (the first guesses — `llama-3.1-8b-instant`, `llama-3.3-70b-versatile` — weren't actually available on this account).

## Consequences

- Groq's free tier is genuinely free, which matters for a project with no revenue yet — but it comes with a real 8000 TPM rate limit that has caused repeated, documented test flakiness (retried and passed on a second or third attempt every time it's been hit).
- LiteLLM doesn't have `groq/openai/gpt-oss-20b` mapped in its own pricing table (the nested `openai/` confuses its provider-prefix detection) — a manual fallback price table was added rather than silently reporting no cost.
- Because the tier abstraction already existed, swapping providers per deployment is a config change in `tiers.py`, not a rewrite — this decision is a default, not a lock-in.
- Groq has no embeddings endpoint at all, which forced [0005](0005-self-hosted-embeddings.md) sooner than planned.
