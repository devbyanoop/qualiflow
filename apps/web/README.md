# QualiFlow web (UI shell)

Next.js + TypeScript + Tailwind + `next-intl`. Phase 0 scope only right now: i18n routing (EN + Arabic/RTL) and a placeholder page proving every string is externalized — no backend integration yet (see [docs/adr/0007](../../docs/adr/0007-environment-classification.md) and the roadmap for what Phase 0 actually covers here).

## Develop

From the repo root (this is a pnpm workspace member, not a standalone project):

```bash
pnpm install
pnpm --filter qualiflow-web dev
```

Visit `http://localhost:3000` — redirects to `/en` or `/ar` based on the browser's `Accept-Language`, or use the language switcher in the top corner.

## Structure

- `src/app/[locale]/` — all routes are locale-prefixed; `src/app/[locale]/layout.tsx` sets `<html lang>` / `dir` per locale.
- `src/i18n/` — `next-intl` routing config, navigation helpers, request config.
- `src/proxy.ts` — locale detection/routing (Next.js 16's `proxy` convention, not the deprecated `middleware`).
- `messages/en.json`, `messages/ar.json` — every UI string, externalized. New strings go here, never inline in a component.

## What's deliberately not here yet

No auth, no API calls, no real dashboard pages — see the Phase 0 scope decision in the project roadmap. The Arabic translations in `messages/ar.json` are AI-assisted, not reviewed by a native speaker (same caveat as `fixtures/i18n-demo-brd.md`).
