import { api } from "./client";

/** Private LinkedIn network (Growth plan and up). Every call is scoped to the
 *  signed-in account on the server; nothing here can read anyone else's data. */
export interface NetworkStatus {
  eligible: boolean;
  plan: string;
  upgrade_to: string | null;
  connection_count: number;
  last_import_at: string | null;
  last_analyzed_at: string | null;
  needs_new_export: boolean;
  max_bytes: number;
  max_rows: number;
}

export interface NetworkMatch {
  connection_id: string;
  full_name: string;
  position: string | null;
  company: string | null;
  profile_url: string | null;
  connected_on: string | null;
  score: number;
  segment: string;
  reasons: string[] | null;
}

export interface NetworkProduct {
  product_id: string;
  product_name: string;
  total_matches: number;
  segments: { segment: string; count: number }[];
  matches: NetworkMatch[];
}

export interface ImportResult {
  added: number;
  skipped: number;
  total: number;
  matched: number;
}

export const getNetworkStatus = () => api<NetworkStatus>("/linkedin-network/status");
export const getRecommendations = () =>
  api<{ products: NetworkProduct[] }>("/linkedin-network/recommendations");
export const importConnections = (csvText: string) =>
  api<ImportResult>("/linkedin-network/import", { body: { csv_text: csvText } });
export const eraseNetwork = () =>
  api<Record<string, number>>("/linkedin-network", { method: "DELETE" });

export interface NetworkMessage {
  id: string;
  connection_id: string;
  product_id: string;
  text: string;
  status: "draft" | "approved" | "queued" | "sent" | "failed";
  channel: "copy" | "unipile" | "bulk" | null;
  error: string | null;
  sent_at: string | null;
}

export const listMessages = () =>
  api<{ messages: NetworkMessage[] }>("/linkedin-network/messages");
export const draftMessage = (connectionId: string, productId: string) =>
  api<NetworkMessage>("/linkedin-network/messages/draft", {
    body: { connection_id: connectionId, product_id: productId },
  });
export const saveMessage = (id: string, text: string) =>
  api<NetworkMessage>(`/linkedin-network/messages/${id}`, { method: "PUT", body: { text } });
export const markMessageSent = (id: string) =>
  api<NetworkMessage>(`/linkedin-network/messages/${id}/mark-sent`, { body: {} });
export const sendMessageNow = (id: string) =>
  api<NetworkMessage>(`/linkedin-network/messages/${id}/send`, { body: {} });
export const bulkSend = (ids: string[]) =>
  api<{ queued: number; spacing_seconds: number }>("/linkedin-network/messages/bulk-send", {
    body: { ids },
  });
