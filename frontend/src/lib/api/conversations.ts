import { api } from "./client";
import type { ChannelSuggestion, ThreadItem } from "../conversation";

export interface ThreadResponse {
  lead_id: string;
  items: ThreadItem[];
  summary: {
    channels: { channel: string; outbound: number; inbound: number }[];
    last_outbound_at: string | null;
    last_inbound_at: string | null;
    open_suggestions: number;
  };
}

export const getConversation = (leadId: string) =>
  api<ThreadResponse>(`/leads/${leadId}/conversation`);

export const getLeadSuggestions = (leadId: string) =>
  api<ChannelSuggestion[]>(`/leads/${leadId}/channel-suggestions`);

export const acceptSuggestion = (id: string) =>
  api<{ status: string; switched_message_id: string | null; note: string | null }>(
    `/channel-suggestions/${id}/accept`, { method: "POST" });

export const dismissSuggestion = (id: string) =>
  api<ChannelSuggestion>(`/channel-suggestions/${id}/dismiss`, { method: "POST" });
