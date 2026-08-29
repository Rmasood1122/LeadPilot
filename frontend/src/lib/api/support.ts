import { api } from "./client";
import type {
  ChatReply, ChatSession, SupportFaq, SupportTicket,
} from "./types";

/**
 * AI support chat + ticket fallback (Feature 3).
 *
 * Every call is user-scoped by the bearer token — there is no endpoint here
 * that takes a user id, so one user's conversation is unreachable from
 * another's session by construction rather than by a check.
 */

export function getSupportFaq(): Promise<SupportFaq> {
  return api<SupportFaq>("/support/faq");
}

/** Ask a question. Omit sessionId to continue the most recent conversation. */
export function sendChatMessage(
  message: string,
  sessionId?: string,
): Promise<ChatReply> {
  return api<ChatReply>("/support/chat", {
    method: "POST",
    body: sessionId ? { message, session_id: sessionId } : { message },
  });
}

export function listChatSessions(): Promise<{
  sessions: ChatSession[];
  retention_days: number;
}> {
  return api("/support/chat/sessions");
}

export function getChatSession(sessionId: string): Promise<ChatSession> {
  return api<ChatSession>(`/support/chat/sessions/${encodeURIComponent(sessionId)}`);
}

export function startChatSession(): Promise<ChatSession> {
  return api<ChatSession>("/support/chat/sessions", { method: "POST" });
}

export function deleteChatSession(sessionId: string): Promise<{ deleted: string }> {
  return api(`/support/chat/sessions/${encodeURIComponent(sessionId)}`, {
    method: "DELETE",
  });
}

/**
 * Escalate to a human.
 *
 * Deliberately NOT blocked when the daily chat budget is exhausted — someone
 * who has run out of messages is exactly the person who most needs a human.
 */
export function createSupportTicket(input: {
  subject: string;
  body: string;
  chatSessionId?: string;
}): Promise<SupportTicket> {
  return api<SupportTicket>("/support/tickets", {
    method: "POST",
    body: {
      subject: input.subject,
      body: input.body,
      ...(input.chatSessionId ? { chat_session_id: input.chatSessionId } : {}),
    },
  });
}

export function listSupportTickets(): Promise<{ tickets: SupportTicket[] }> {
  return api("/support/tickets");
}
