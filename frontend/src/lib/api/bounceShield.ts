import { api } from "./client";
import type { EmailVerdict } from "../bounce-shield";

/** F01 — the email waterfall's verdict, the per-lead override, re-verify. */

export const getEmailVerdict = (leadId: string) =>
  api<EmailVerdict>(`/leads/${leadId}/email-verdict`);

/** Re-verify the current address. May spend one paid verification. */
export const refreshEmailVerdict = (leadId: string) =>
  api<EmailVerdict>(`/leads/${leadId}/email-verdict/refresh`, { method: "POST", body: {} });

/** Allow sending to an address that is not verified-valid. `body` is an
 *  OBJECT — api() stringifies it itself. */
export const setEmailOverride = (leadId: string, reason: string) =>
  api<EmailVerdict>(`/leads/${leadId}/email-override`, { method: "POST", body: { reason } });

export const clearEmailOverride = (leadId: string) =>
  api<EmailVerdict>(`/leads/${leadId}/email-override`, { method: "DELETE" });
