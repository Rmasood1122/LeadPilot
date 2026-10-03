import { ApiError, api } from "./client";
import type { AnalyticsOut, StrategyOut } from "./types";

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
): Promise<{ id: string }> {
  return api(`/products/${productId}/strategies`, {
    body: { flow_type: hasPastClients ? "with_clients" : "no_clients" },
  });
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
