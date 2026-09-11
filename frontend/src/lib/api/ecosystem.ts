/** Feature Group 4 — Slack, HubSpot / Salesforce, outbound webhooks and
 *  personal API keys. */

import { api } from "./client";

// ---- Slack ---------------------------------------------------------------

export interface SlackStatus {
  configured: boolean;
  connected: boolean;
  team_name?: string | null;
  channel_id?: string | null;
  channel_name?: string | null;
}

export interface SlackChannel {
  id: string;
  name: string | null;
  is_private: boolean;
}

export const getSlack = (): Promise<SlackStatus> => api("/integrations/slack");
export const slackAuthUrl = (): Promise<{ auth_url: string }> =>
  api("/integrations/slack/auth-url");
export const listSlackChannels = (): Promise<SlackChannel[]> =>
  api("/integrations/slack/channels");
export const setSlackChannel = (channelId: string): Promise<SlackStatus> =>
  api("/integrations/slack/channel", { method: "PUT", body: { channel_id: channelId } });
export const testSlack = (): Promise<{ ok: boolean }> =>
  api("/integrations/slack/send-test", { method: "POST" });
export const disconnectSlack = (): Promise<void> =>
  api("/integrations/slack", { method: "DELETE" });

// ---- HubSpot / Salesforce ------------------------------------------------

export type CrmProvider = "hubspot" | "salesforce";

export interface CrmStatus {
  provider: CrmProvider;
  configured: boolean;
  connected: boolean;
  status?: "connected" | "error" | "revoked";
  account_id?: string | null;
  account_name?: string | null;
  last_push_at?: string | null;
  last_pull_at?: string | null;
  last_error?: string | null;
  linked_leads?: number;
  linked_deals?: number;
  settings?: { sync_new_leads: boolean; [key: string]: unknown };
}

export const getCrm = (): Promise<CrmStatus[]> => api("/integrations/crm");
export const crmAuthUrl = (p: CrmProvider): Promise<{ auth_url: string }> =>
  api(`/integrations/${p}/auth-url`);
export const syncCrm = (p: CrmProvider): Promise<{ queued: boolean }> =>
  api(`/integrations/${p}/sync`, { method: "POST" });
export const updateCrmSettings = (
  p: CrmProvider,
  body: { sync_new_leads?: boolean },
): Promise<CrmStatus> => api(`/integrations/${p}/settings`, { method: "PUT", body });
export const disconnectCrm = (p: CrmProvider): Promise<void> =>
  api(`/integrations/${p}`, { method: "DELETE" });

// ---- Outbound webhooks -----------------------------------------------------

export interface WebhookTarget {
  id: string;
  url: string;
  events: string[];
  active: boolean;
  description: string | null;
  source: string;
  disabled_reason: string | null;
  created_at: string | null;
  secret?: string;
}

export interface WebhookEvent {
  event: string;
  description: string;
  sample: Record<string, unknown>;
  zapier: boolean;
}

export interface WebhookDeliveryRow {
  id: string;
  target_id: string;
  event: string;
  status: "pending" | "delivered" | "exhausted" | "failed" | "cancelled" | string;
  attempts: number;
  last_status_code: number | null;
  last_error: string | null;
  created_at: string | null;
  target_url?: string;
}

export const listWebhooks = (): Promise<WebhookTarget[]> => api("/webhooks/outbound");
export const listWebhookEvents = (): Promise<WebhookEvent[]> => api("/webhooks/outbound/events");
export const listWebhookDeliveries = (): Promise<WebhookDeliveryRow[]> =>
  api("/webhooks/outbound/deliveries?limit=20");
export const registerWebhook = (body: {
  url: string;
  events: string[];
  description?: string;
}): Promise<WebhookTarget> => api("/webhooks/outbound/register", { method: "POST", body });
export const testWebhook = (id: string): Promise<{ delivery_id: string; event: string }> =>
  api(`/webhooks/outbound/${id}/test`, { method: "POST" });
export const deleteWebhook = (id: string): Promise<void> =>
  api(`/webhooks/outbound/${id}`, { method: "DELETE" });

// ---- API keys ----------------------------------------------------------------

export interface ApiKeyRow {
  id: string;
  name: string;
  prefix: string;
  created_at: string | null;
  last_used_at: string | null;
  revoked: boolean;
  key?: string;
}

export const listApiKeys = (): Promise<ApiKeyRow[]> => api("/me/api-keys");
export const createApiKey = (name: string): Promise<ApiKeyRow> =>
  api("/me/api-keys", { method: "POST", body: { name } });
export const revokeApiKey = (id: string): Promise<void> =>
  api(`/me/api-keys/${id}`, { method: "DELETE" });

/** A settings-page query string like `?tab=integrations&hubspot=connected`
 *  turned into a user-facing toast, or null. */
export function oauthResultMessage(params: URLSearchParams): { text: string; ok: boolean } | null {
  const names: Record<string, string> = { slack: "Slack", hubspot: "HubSpot", salesforce: "Salesforce" };
  for (const [key, label] of Object.entries(names)) {
    const value = params.get(key);
    if (value === "connected") return { text: `${label} connected`, ok: true };
    if (value === "error") {
      const reason = params.get("reason");
      return { text: `${label} connection failed${reason ? `: ${reason}` : ""}`, ok: false };
    }
  }
  return null;
}
