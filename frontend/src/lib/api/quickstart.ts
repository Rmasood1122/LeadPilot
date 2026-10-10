import { api } from "./client";
import type { QuickstartConfig, QuickstartDraft, QuickstartRun } from "../quickstart";

/** F06 Quickstart. Review-only: there is deliberately no approve/send call.
 *
 *  NOTE: `body` is passed as an OBJECT. api() stringifies it itself — see the
 *  fixed-bug note at the bottom of ./client.ts. */

export const getQuickstartConfig = () => api<QuickstartConfig>("/quickstart/config");

export const startQuickstart = (payload: {
  website_url: string; offer: string; product_name?: string;
}) => api<QuickstartRun>("/quickstart", { method: "POST", body: payload });

export const listQuickstarts = () => api<{ items: QuickstartRun[] }>("/quickstart");

export const getQuickstart = (id: string) => api<QuickstartRun>(`/quickstart/${id}`);

export const discardQuickstartDraft = (id: string) =>
  api<QuickstartDraft>(`/quickstart/drafts/${id}/discard`, { method: "POST", body: {} });
