import { ApiError, api, tooManyRequestsMessage } from "./client";
import type { AutopilotOptIn } from "../autopilot";
import type { AnalyticsOut, StrategyOut } from "./types";
import type { BusinessType, ServiceAreaIn } from "@/lib/localBusiness";

/** Mirrors INVALID_PASSWORD in app/api/strategies.py. */
export const INVALID_PASSWORD = "INVALID_PASSWORD";

/** Permanently delete a strategy. The account password is re-checked by the
 *  server; nothing is deleted unless it matches. */
export function deleteStrategy(
  id: string,
  password: string,
): Promise<{ deleted: boolean; id: string; deleted_at: string }> {
  return api(`/strategies/${id}`, { method: "DELETE", body: { password } });
}

/** The sentence the confirmation dialog shows for a failed delete. */
export function deleteStrategyErrorMessage(err: unknown): string {
  if (!(err instanceof ApiError)) {
    return "Could not delete the strategy. Check your connection and try again.";
  }
  if (err.status === 403 && err.detail === INVALID_PASSWORD) {
    return "That password is incorrect. Nothing was deleted.";
  }
  if (err.status === 429) return "Too many attempts. Wait a few minutes and try again.";
  if (err.status === 404) return "This strategy no longer exists.";
  return err.detail || "Could not delete the strategy.";
}

export interface PastClientIn {
  details: string;
  acquisition_story: string;
}

export async function createProduct(input: {
  name: string;
  description: string;
  type: "product" | "skill";
  /** Local business mode; omit (or null) for a non-local business. */
  business_type?: BusinessType | null;
}): Promise<{ id: string }> {
  return api("/products", { body: input });
}

export async function addPastClients(
  productId: string,
  clients: PastClientIn[],
): Promise<unknown> {
  return api(`/products/${productId}/past-clients`, { body: { clients } });
}

export async function createStrategy(
  productId: string,
  hasPastClients: boolean,
  autopilot?: AutopilotOptIn,
  local: { service_area?: ServiceAreaIn; local_offer?: string } = {},
): Promise<{ id: string }> {
  return api(`/products/${productId}/strategies`, {
    body: {
      flow_type: hasPastClients ? "with_clients" : "no_clients",
      // Autopilot launch: sent only when turned on WITH the confirmation.
      ...(autopilot?.enabled ? { autopilot } : {}),
      // Local business mode: service area / offer (only for a local business).
      ...local,
    },
  });
}

/** Re-enqueue a strategy's pipeline. The engine continues from the first step
 *  with no saved output, so nothing already done is repeated or re-billed.
 *  Pass `maxBudgetUsd` to raise the cap of a run that stopped on its budget. */
export function resumeStrategy(
  id: string,
  maxBudgetUsd?: number,
): Promise<StrategyOut> {
  return api(`/strategies/${id}/resume`, {
    body: maxBudgetUsd === undefined ? {} : { max_budget_usd: maxBudgetUsd },
  });
}

/** Run the 10 verification passes again on a strategy waiting for human review.
 *  Reuses the finished research; only verification is paid for again. */
export function reverifyStrategy(
  id: string,
  opts: { maxBudgetUsd?: number; maxAttempts?: number } = {},
): Promise<StrategyOut> {
  const body: Record<string, number> = {};
  if (opts.maxBudgetUsd !== undefined) body.max_budget_usd = opts.maxBudgetUsd;
  if (opts.maxAttempts !== undefined) body.max_attempts = opts.maxAttempts;
  return api(`/strategies/${id}/reverify`, { body });
}

/** Human sign-off on 1-3 failed verification passes (needs_human_review). */
export function overrideFailedPasses(
  id: string,
  passNos: number[],
  reason: string,
): Promise<StrategyOut> {
  return api(`/strategies/${id}/override-passes`, {
    body: { pass_nos: passNos, reason, acknowledge: true },
  });
}

/** The sentence shown when a resume request is refused. */
export function resumeStrategyErrorMessage(err: unknown): string {
  if (!(err instanceof ApiError)) {
    return "Could not resume. Check your connection and try again.";
  }
  if (err.status === 409) return err.detail || "This strategy cannot be resumed right now.";
  if (err.status === 422) return err.detail || "That budget is not valid.";
  if (err.status === 429) {
    return tooManyRequestsMessage(err, "Too many requests. Wait a few minutes and try again.");
  }
  if (err.status === 404) return "This strategy no longer exists.";
  return err.detail || "Could not resume the strategy.";
}

export function getStrategy(id: string): Promise<StrategyOut> {
  return api(`/strategies/${id}`);
}

export function listStrategies(): Promise<StrategyOut[]> {
  return api("/strategies");
}

export function getStrategyDocument(
  id: string,
): Promise<{ strategy_document: string | null; gtm_document: string | null }> {
  return api(`/strategies/${id}/document`);
}

export function getAnalytics(
  id: string,
  granularity = "day",
): Promise<AnalyticsOut> {
  return api(`/strategies/${id}/analytics?granularity=${granularity}`);
}
