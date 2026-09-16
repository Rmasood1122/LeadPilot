/** Where a signed-in user belongs — pure, so every rule is unit-tested in
 *  src/tests/post-login.test.ts.
 *
 *  The plan check (no purchased plan -> /pricing) runs ONLY straight after an
 *  explicit sign-in (`afterLogin: true`). A silent session restore on app load
 *  routes to the dashboard regardless of plan, and nothing redirects a no-plan
 *  user back to /pricing later in the session — they go there themselves.
 *  The SERVER decides the facts (email_verified, has_active_plan); this only
 *  turns them into a route. */

import type { UserOut } from "./api/types";
import { needsVerification } from "./identity";

export const DASHBOARD_PATH = "/pipeline";
export const PRICING_PATH = "/pricing";

type RoutingUser = Pick<UserOut,
  "email" | "email_verified" | "identity_required" | "identity_complete" |
  "phone_verified" | "has_active_plan">;

export function postLoginDestination(
  user: RoutingUser,
  opts: { phoneDeferred?: boolean; afterLogin?: boolean } = {},
): string {
  if (user.email_verified === false) {
    return `/check-email?email=${encodeURIComponent(user.email)}`;
  }
  if (needsVerification(user, opts.phoneDeferred ?? false)) return "/onboarding/verify";
  // Only an explicit `false` gates: a response without the field is from a
  // backend that predates it, and must not send anyone to pricing.
  if (opts.afterLogin && user.has_active_plan === false) return PRICING_PATH;
  return DASHBOARD_PATH;
}
