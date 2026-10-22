import { createNavigation } from "next-intl/navigation";
import { routing } from "./routing";

// Locale-aware Link/useRouter/usePathname -- every navigation call
// goes through these instead of next/navigation directly, so a link
// never accidentally drops the current locale.
export const { Link, redirect, usePathname, useRouter, getPathname } =
  createNavigation(routing);
