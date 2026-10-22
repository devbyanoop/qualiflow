import { defineRouting } from "next-intl/routing";

export const routing = defineRouting({
  // RTL proof-of-mechanism for Phase 0 (build plan, ADR-014): Arabic
  // alongside English from day one, not retrofitted later. Adding a
  // third locale later only touches this list and messages/<locale>.json
  // -- no component needs to know the locale set.
  locales: ["en", "ar"],
  defaultLocale: "en",
});
