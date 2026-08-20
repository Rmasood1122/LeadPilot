import { api } from "./client";
import type { AnalyticsOut, StrategyOut } from "./types";

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
