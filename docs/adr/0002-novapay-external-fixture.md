# 0002 — NovaPay is an external reference fixture, never vendored in

**Status:** Accepted (2026-10-21, M0.5)

## Context

The original plan had QualiFlow build and own a `demo-apps/` folder inside its own repository, to have something to generate and run tests against during development.

## Decision

Rejected. QualiFlow is standalone testing infrastructure — the same way it would test a real client's app — and bundling a target application inside the tool that tests it blurs that distinction. **NovaPay** (a separate Express/EJS/SQLite banking app, already built for other work) is used as the reference fixture instead: a separate repository, reached over the network by registering its base URL and OpenAPI spec (see [0003](0003-no-hardcoded-target-app.md)), never copied into this repo.

## Consequences

- QualiFlow's repo stays focused on the product; it has no "app under test" of its own to maintain, version, or keep realistic.
- NovaPay has real, undocumented-by-design bugs (no ownership check on `/api/transfers`, no distinct-account check, no transaction-history write on the API path) that QualiFlow's generated tests are expected to catch — a deliberate, useful property of testing something QualiFlow doesn't own or get to fix.
- Real cost: NovaPay isn't published yet, so a stranger cloning QualiFlow has nothing to point it at out of the box. Tracked as an open gap, not hidden — see `docs/getting-started/quickstart.md`'s note on this.
- This decision is also what forced [0003](0003-no-hardcoded-target-app.md): once NovaPay was accepted as "just an app QualiFlow talks to," hardcoding its specifics into the automation agent was a direct contradiction that got caught and fixed.
