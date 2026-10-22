import createMiddleware from "next-intl/middleware";
import { routing } from "./i18n/routing";

export default createMiddleware(routing);

export const config = {
  // Skip API routes, Next internals, and anything with a file extension
  // (static assets) -- only page navigations get locale-prefixed.
  matcher: ["/((?!api|_next|_vercel|.*\\..*).*)"],
};
