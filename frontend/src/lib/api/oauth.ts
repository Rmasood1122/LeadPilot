import { api } from "./client";

/** Connector consent (app/api/oauth.py). */

export interface ConsentScope {
  scope: string;
  description: string;
}

export interface ConsentRequest {
  request_id: string;
  client_name: string | null;
  redirect_uri: string;
  redirect_host: string | null;
  scopes: ConsentScope[];
  expires_at: string;
}

export const getConsentRequest = (requestId: string) =>
  api<ConsentRequest>(`/oauth/requests/${encodeURIComponent(requestId)}`);

/** NOTE: `body` is passed as an OBJECT. api() stringifies it itself. */
export const decideConsent = (requestId: string, approve: boolean) =>
  api<{ redirect_to: string }>(`/oauth/requests/${encodeURIComponent(requestId)}/decision`, {
    method: "POST", body: { approve },
  });
