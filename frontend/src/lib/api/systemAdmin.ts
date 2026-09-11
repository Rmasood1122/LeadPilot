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

export function updateSystemSetting(
  key: string,
  value: SystemSetting["value"],
): Promise<{ key: string; value: SystemSetting["value"] }> {
  return api(`/admin/system-settings/${key}`, { method: "PUT", body: { value } });
}
