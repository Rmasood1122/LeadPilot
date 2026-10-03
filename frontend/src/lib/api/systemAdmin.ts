/** Admin: system-scope integration credentials + system settings.
 *
 * Uses `api()` directly rather than the `apiClient` compat adapter the older
 * admin modules use: that adapter JSON-encodes the body before `api()` encodes
 * it again, and its callers read `.data` off a response that has none. */

import { api } from "./client";

export interface SystemIntegrationKey {
  key: string;
  is_set: boolean;
}

export interface SystemIntegration {
  provider: string;
  label: string;
  purpose: string;
  scope: "system" | "user" | "both";
  keys: SystemIntegrationKey[];
  configured: boolean;
}

export interface SystemSetting {
  key: string;
  value: boolean | number | string;
  default: boolean | number | string;
  type: "bool" | "int" | "float" | "str";
  description: string;
  is_default: boolean;
  updated_at: string | null;
}

export function listSystemIntegrations(): Promise<SystemIntegration[]> {
  return api("/admin/integrations");
}

/** An empty string for a key clears it. Values are never sent back. */
export function setSystemIntegration(
  provider: string,
  values: Record<string, string>,
): Promise<SystemIntegration> {
  return api(`/admin/integrations/${provider}`, { method: "PUT", body: { values } });
}

export function clearSystemIntegration(provider: string): Promise<{ removed: number }> {
  return api(`/admin/integrations/${provider}`, { method: "DELETE" });
}

export function listSystemSettings(): Promise<SystemSetting[]> {
  return api("/admin/system-settings");
}

// --------------------------------------------------------------------------
// Feature 8 — compliance rules
// --------------------------------------------------------------------------

export interface RuleFields {
  send_start_hour: number | null;
  send_end_hour: number | null;
  skip_weekends: boolean | null;
  daily_cap: number | null;
  consent_required: boolean | null;
  bounce_pause_threshold: number | null;
}

export interface ComplianceRule extends RuleFields {
  id: string;
  scope: string;
  workspace_id: string | null;
  region: string;
  channel: string;
  note: string | null;
  /** Non-empty only for a row written outside the API; the engine fails closed on it. */
  problems: string[];
  updated_at: string | null;
}

export interface EffectiveRule extends RuleFields {
  window_empty: boolean;
  failed_closed: boolean;
  rule_ids: string[];
}

export interface ComplianceRuleList {
  baseline: EffectiveRule;
  baseline_caps: Record<string, number | null>;
  hard_bounds: { hour_min: number; hour_max: number; bounce_max: number };
  regions: string[];
  channels: string[];
  rules: ComplianceRule[];
}

export function listComplianceRules(workspaceId?: string): Promise<ComplianceRuleList> {
  return api(`/admin/compliance-rules${workspaceId ? `?workspace_id=${workspaceId}` : ""}`);
}

export function listRuleWorkspaces(): Promise<{ id: string; name: string; owner_email: string }[]> {
  return api("/admin/compliance-rules/workspaces");
}

export function upsertComplianceRule(
  body: Partial<RuleFields> & {
    workspace_id: string | null;
    region: string;
    channel: string;
    note?: string | null;
  },
): Promise<ComplianceRule> {
  return api("/admin/compliance-rules", { method: "PUT", body });
}

export function deleteComplianceRule(id: string): Promise<void> {
  return api(`/admin/compliance-rules/${id}`, { method: "DELETE" });
}

export function effectiveComplianceRule(
  workspaceId: string | undefined,
  region: string,
  channel: string,
): Promise<EffectiveRule> {
  const q = new URLSearchParams({ region, channel });
  if (workspaceId) q.set("workspace_id", workspaceId);
  return api(`/admin/compliance-rules/effective?${q}`);
}

export function updateSystemSetting(
  key: string,
  value: SystemSetting["value"],
): Promise<{ key: string; value: SystemSetting["value"] }> {
  return api(`/admin/system-settings/${key}`, { method: "PUT", body: { value } });
}
