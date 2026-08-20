import { api } from "./client";

export interface IntegrationStatus {
  gmail: { connected: boolean; email: string | null; healthy: boolean | null };
  whatsapp: {
    configured: boolean;
    phone_number_id: string | null;
    webhook_ok: boolean | null;
  };
  apollo: { key_set: boolean; masked: string | null };
  hunter: { key_set: boolean; masked: string | null };
  calendly: { token_set: boolean };
}

export function getIntegrations(): Promise<IntegrationStatus> {
  return api("/integrations/status");
}

export function gmailAuthUrl(): Promise<{ url: string }> {
  return api("/integrations/gmail/auth-url");
}

export function testConnection(
  provider: string,
): Promise<{ healthy: boolean }> {
  return api(`/integrations/${provider}/test`, { method: "POST" });
}

export function listSuppression(): Promise<{
  entries: { email: string | null; phone: string | null; reason: string; ts: string }[];
}> {
  return api("/suppression");
}

export function addSuppression(input: {
  email?: string;
  phone?: string;
  reason: string;
}) {
  return api("/suppression", { body: input });
}
