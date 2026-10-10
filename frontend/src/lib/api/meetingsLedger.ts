/** F08 — the meetings-per-dollar ledger. Money is integer cents, exactly as
 *  the API returns it; format at the edge (lib/revenue.ts formatMoney). */

import { getAccessTokenSync } from "../auth-session";
import { WORKSPACE_HEADER, getActiveWorkspace } from "../workspace";
import type { LedgerExportFormat, LedgerExportView, LedgerQuery } from "../meetingsLedger";
import { ledgerExportPath, ledgerQueryString } from "../meetingsLedger";
import { api, BASE, normalizeError } from "./client";

export type LedgerMethod =
  | "direct_reply" | "thread_match" | "last_touch" | "none" | "pending";

export type LedgerEventKind = "qualified_conversation" | "meeting_booked" | "meeting_held";

export interface LedgerFigures {
  sends: number;
  qualified_conversations: number;
  meetings_booked: number;
  meetings_held: number;
  booked_by_method: Record<LedgerMethod, number>;
  booked_mean_confidence: number | null;
  booked_certain: number;
  booked_attributed: number;
  ai_cost_cents: number;
  data_cost_cents: number;
  other_recorded_cost_cents: number;
  shared_cost_cents: number;
  platform_fee_cents: number;
  infrastructure_cost_cents: number;
  total_cost_cents: number;
  cost_per_qualified_conversation_cents: number | null;
  cost_per_meeting_booked_cents: number | null;
  cost_per_meeting_held_cents: number | null;
  meetings_booked_per_1k_spend: number | null;
  revenue_cents: number;
  deals_won: number;
  /** As of now — a stock, not bounded by the period. */
  open_pipeline_cents: number;
}

export interface LedgerCampaign extends LedgerFigures {
  strategy_id: string;
  name: string;
  campaign_state: string | null;
}

export interface LedgerEvent {
  kind: LedgerEventKind;
  strategy_id: string;
  campaign: string;
  lead_id: string;
  company: string | null;
  at: string;
  source: string;
  outcome_id: string | null;
  method: LedgerMethod;
  method_label: string;
  confidence: number | null;
  is_certain: boolean;
  attribution_id: string | null;
}

export interface LedgerReconciliation {
  raw_cost_cents: number;
  ledger_cost_cents: number;
  difference_cents: number;
  rounding_tolerance_cents: number;
  balanced: boolean;
  decomposition_balanced: boolean;
  booked_outcome_leads: number;
  ledger_meetings_booked: number;
  attributed: number;
  pending: number;
}

export interface MeetingsLedger {
  version: string;
  generated_at: string;
  currency: string;
  date_from: string;
  date_to: string;
  strategy_ids: string[] | null;
  infrastructure: {
    cents_per_1k_sends: number;
    included: boolean;
    excluded_non_usd_cents: number;
    note: string;
  };
  campaigns: LedgerCampaign[];
  totals: LedgerFigures & { unallocated_cost_cents: number };
  events: LedgerEvent[];
  reconciliation: LedgerReconciliation;
  method_labels: Record<LedgerMethod, string>;
  definitions: Record<string, string>;
}

export function getMeetingsLedger(query: LedgerQuery): Promise<MeetingsLedger> {
  return api(`/analytics/meetings-ledger?${ledgerQueryString(query)}`);
}

/** The export as a Blob. Not through api(): CSV and PDF are not JSON. Same
 *  auth + workspace headers as api() (see lib/api/audit.ts). */
export async function downloadMeetingsLedger(
  query: LedgerQuery,
  format: LedgerExportFormat,
  view: LedgerExportView = "campaigns",
): Promise<Blob> {
  const headers: Record<string, string> = {};
  const token = getAccessTokenSync();
  if (token) headers.Authorization = `Bearer ${token}`;
  const workspace = getActiveWorkspace();
  if (workspace) headers[WORKSPACE_HEADER] = workspace;
  const resp = await fetch(`${BASE}${ledgerExportPath(query, format, view)}`, { headers });
  if (!resp.ok) throw await normalizeError(resp);
  return resp.blob();
}
