/** Multi-variate test results (GET /strategies/{id}/mv-results) — what the
 *  panel shows when the request fails. Pure; tested in
 *  src/tests/multiVariate.test.ts.
 *
 *  The plan gate is the SERVER's (app/core/plans.py `multi_variate`, checked
 *  by the endpoint against the account whose data it is — inside a workspace
 *  that is the owner). The panel follows the answer instead of guessing from
 *  the signed-in person's own plan: 402 = the plan does not include it. */
import { ApiError } from "@/lib/api/client";

export type MvFailure = "upgrade" | "not_found" | "error";

export function mvFailure(error: unknown): MvFailure | null {
  if (!error) return null;
  if (error instanceof ApiError && error.status === 402) return "upgrade";
  if (error instanceof ApiError && error.status === 404) return "not_found";
  return "error";
}

export function mvFailureText(failure: MvFailure): string {
  switch (failure) {
    case "upgrade":
      return "Multi-variate test results are included from the Growth plan.";
    case "not_found":
      return "This campaign was not found.";
    default:
      return "Multi-variate results could not be loaded. Refresh to try again.";
  }
}

/** A refusal is an answer, not a blip: 402 / 404 are never retried. */
export function mvShouldRetry(failureCount: number, error: unknown): boolean {
  const failure = mvFailure(error);
  return failure === "error" && failureCount < 2;
}
