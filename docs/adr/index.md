# Architecture Decision Records

Short records of significant technical decisions: what was decided, why, what else was considered, and what tradeoffs were accepted. Written once, rarely edited — a reversed decision gets a new ADR that supersedes the old one, not a rewrite of history.

| # | Decision | Status |
|---|----------|--------|
| [0001](0001-groq-as-default-llm-provider.md) | Groq as the default LLM provider, not OpenAI | Accepted |
| [0002](0002-novapay-external-fixture.md) | NovaPay is an external reference fixture, never vendored in | Accepted |
| [0003](0003-no-hardcoded-target-app.md) | No app identity is ever hardcoded into the automation agent | Accepted |
| [0004](0004-postgres-rls-tenant-isolation.md) | Postgres RLS + a non-superuser app role for tenant isolation | Accepted |
| [0005](0005-self-hosted-embeddings.md) | Self-hosted embeddings, not a paid API | Accepted |
| [0006](0006-skip-langfuse.md) | Skip Langfuse for now | Accepted |
| [0007](0007-environment-classification.md) | Environment classification, production blocked by default | Accepted |
