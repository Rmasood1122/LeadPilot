/** M9 CRM domain module — built on the SAME api() client as every other
 *  module in this directory. No second HTTP client, no direct fetch. */

import { api } from "./client";
import type {
  CrmActivityKind,
  CrmActivityPage,
  CrmCampaignsDashboard,
  CrmColumnState,
  CrmCustomField,
  CrmFieldType,
  CrmFilter,
  CrmGridPage,
  CrmLeadsDashboard,
  CrmNote,
  CrmPipelineDashboard,
  CrmSavedView,
  CrmSort,
  CrmTag,
  LeadStatus,
} from "./types";

// --------------------------------------------------------------------------
// Dashboards
// --------------------------------------------------------------------------

function scope(strategyId?: string | null, extra?: Record<string, string>) {
  const q = new URLSearchParams(extra);
  if (strategyId) q.set("strategy_id", strategyId);
  const qs = q.toString();
  return qs ? `?${qs}` : "";
}

export function getPipelineDashboard(
  strategyId?: string | null,
): Promise<CrmPipelineDashboard> {
  return api(`/crm/dashboard/pipeline${scope(strategyId)}`);
}

export function getLeadsDashboard(
  strategyId?: string | null,
  stuckAfterDays = 7,
): Promise<CrmLeadsDashboard> {
  return api(
    `/crm/dashboard/leads${scope(strategyId, {
      stuck_after_days: String(stuckAfterDays),
    })}`,
  );
}

export function getCampaignsDashboard(
  strategyId?: string | null,
): Promise<CrmCampaignsDashboard> {
  return api(`/crm/dashboard/campaigns${scope(strategyId)}`);
}

export function getActivityFeed(params: {
  strategyId?: string | null;
  leadId?: string | null;
  kinds?: CrmActivityKind[];
  limit?: number;
  /** Opaque cursor from a previous page's next_before. */
  before?: string | null;
} = {}): Promise<CrmActivityPage> {
  const q = new URLSearchParams();
  if (params.strategyId) q.set("strategy_id", params.strategyId);
  if (params.leadId) q.set("lead_id", params.leadId);
  if (params.limit) q.set("limit", String(params.limit));
  if (params.before) q.set("before", params.before);
  // Repeated key, not a comma list — FastAPI reads list[str] query params
  // that way, and a company name with a comma in it would otherwise split.
  for (const kind of params.kinds ?? []) q.append("kind", kind);
  const qs = q.toString();
  return api(`/crm/dashboard/activity${qs ? `?${qs}` : ""}`);
}

// --------------------------------------------------------------------------
// Grid
// --------------------------------------------------------------------------

export interface GridQuery {
  strategy_id?: string | null;
  filters?: Record<string, CrmFilter>;
  sort?: CrmSort[];
  search?: string | null;
  tag_ids?: string[];
  limit?: number;
  offset?: number;
}

/** POST, not GET.
 *
 *  A saved view's filter set is nested ({company: {op, value}}), and encoding
 *  that into a query string means inventing a serialisation, risking URL
 *  length limits on a wide filter set, and writing every filter value into
 *  the access log. It is still a read — no rate limit, no mutation. */
export function queryGrid(body: GridQuery = {}): Promise<CrmGridPage> {
  return api("/crm/grid", { method: "POST", body });
}

export interface LeadPatch {
  status?: LeadStatus;
  owner_user_id?: string | null;
  priority?: string | null;
  next_action_at?: string | null;
  custom?: Record<string, unknown>;
}

export function patchLead(
  leadId: string,
  patch: LeadPatch,
): Promise<{ id: string; status: LeadStatus; changed: string[] }> {
  return api(`/crm/leads/${leadId}`, { method: "PATCH", body: patch });
}

export interface BulkResult {
  updated: string[];
  updated_count: number;
  /** Rows whose current status made the requested move illegal. Partial
   *  success is the contract — see the backend handler. */
  skipped: { lead_id: string; reason: string }[];
  skipped_count: number;
}

export function bulkPatchLeads(body: {
  lead_ids: string[];
  status?: LeadStatus;
  add_tag_ids?: string[];
  remove_tag_ids?: string[];
}): Promise<BulkResult> {
  return api("/crm/leads/bulk", { method: "POST", body });
}

// --------------------------------------------------------------------------
// Notes / tags / activity
// --------------------------------------------------------------------------

export function listNotes(leadId: string): Promise<{ items: CrmNote[] }> {
  return api(`/crm/leads/${leadId}/notes`);
}

export function createNote(leadId: string, body: string): Promise<CrmNote> {
  return api(`/crm/leads/${leadId}/notes`, { method: "POST", body: { body } });
}

export function deleteNote(noteId: string): Promise<void> {
  return api(`/crm/notes/${noteId}`, { method: "DELETE" });
}

export function listTags(): Promise<{ items: CrmTag[] }> {
  return api("/crm/tags");
}

export function createTag(
  name: string,
  colorToken = "muted",
): Promise<CrmTag & { created: boolean }> {
  return api("/crm/tags", { method: "POST", body: { name, color_token: colorToken } });
}

export function deleteTag(tagId: string): Promise<void> {
  return api(`/crm/tags/${tagId}`, { method: "DELETE" });
}

export function addTagToLead(leadId: string, tagId: string): Promise<unknown> {
  return api(`/crm/leads/${leadId}/tags/${tagId}`, { method: "POST" });
}

export function removeTagFromLead(leadId: string, tagId: string): Promise<void> {
  return api(`/crm/leads/${leadId}/tags/${tagId}`, { method: "DELETE" });
}

export function getLeadActivity(
  leadId: string,
  before?: string | null,
): Promise<CrmActivityPage> {
  const qs = before ? `?before=${encodeURIComponent(before)}` : "";
  return api(`/crm/leads/${leadId}/activity${qs}`);
}

// --------------------------------------------------------------------------
// Saved views
// --------------------------------------------------------------------------

export function listViews(
  viewType?: "grid" | "dashboard",
): Promise<{ items: CrmSavedView[] }> {
  return api(`/crm/views${viewType ? `?view_type=${viewType}` : ""}`);
}

export interface SavedViewInput {
  name: string;
  view_type: "grid" | "dashboard";
  filters_json: Record<string, CrmFilter>;
  sort_json: CrmSort[];
  columns_json: CrmColumnState[];
  is_default: boolean;
}

export function createView(body: SavedViewInput): Promise<CrmSavedView> {
  return api("/crm/views", { method: "POST", body });
}

export function updateView(
  viewId: string,
  body: SavedViewInput,
): Promise<CrmSavedView> {
  return api(`/crm/views/${viewId}`, { method: "PUT", body });
}

export function deleteView(viewId: string): Promise<void> {
  return api(`/crm/views/${viewId}`, { method: "DELETE" });
}

// --------------------------------------------------------------------------
// Custom fields
// --------------------------------------------------------------------------

export function listFields(): Promise<{ items: CrmCustomField[] }> {
  return api("/crm/fields");
}

export function createField(body: {
  key: string;
  label: string;
  field_type: CrmFieldType;
  options_json?: string[] | null;
  sort_order?: number;
}): Promise<CrmCustomField> {
  return api("/crm/fields", { method: "POST", body });
}

export function deleteField(fieldId: string): Promise<void> {
  return api(`/crm/fields/${fieldId}`, { method: "DELETE" });
}

// --------------------------------------------------------------------------
// Real-time
// --------------------------------------------------------------------------

/** Mint a single-use, 60-second ticket for the SSE stream.
 *
 *  EventSource cannot set an Authorization header, so the credential has to
 *  travel in the URL. This is what travels — not the access token, which
 *  would put an hour-valid JWT into the server log and the browser history. */
export function createStreamTicket(): Promise<{
  ticket: string;
  expires_in: number;
}> {
  return api("/crm/stream/ticket", { method: "POST" });
}
