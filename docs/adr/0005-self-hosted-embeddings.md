# 0005 — Self-hosted embeddings, not a paid API

**Status:** Accepted (2026-10-21, M0.6)

## Context

The plan's locked default was OpenAI's `text-embedding-3-large`. Only a Groq key was available (see [0001](0001-groq-as-default-llm-provider.md)), and Groq has no embeddings endpoint at all — confirmed via its own `/v1/models` listing, not assumed.

## Decision

Self-host embeddings via HuggingFace's Text Embeddings Inference (TEI) server, promoted from "later, for air-gapped deployments" to the primary path ahead of schedule. The first model tried, **BAAI/bge-m3** (1024 dimensions), OOM-killed repeatedly even after raising the Docker VM's memory ceiling to 11GB — at which point the Fedora host's own free memory dropped to 189Mi and its GUI stopped responding, a real incident, not a close call avoided in advance. Reverted the memory ceiling and switched instead to **`sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2`** (384 dimensions), which warmed up in seconds with no OOM.

## Consequences

- Free and self-hosted, fitting this machine's actual memory budget (~3.7GB usable) rather than chasing a bigger host to fit a heavier model.
- A real quality tradeoff was accepted, not just a cost one: 384 dimensions and a general multilingual model, not BGE-M3's larger, retrieval-tuned 1024-dimension embeddings. `knowledge_chunks`' vector column is sized to match (confirmed against the running service, not assumed).
- Revisit once retrieval quality is a real, measured problem (not hypothetical) or once bigger infra is available — not on a fixed schedule.
