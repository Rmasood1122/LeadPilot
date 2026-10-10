/** F09 — 30-Day Pilot Mode. There is deliberately no call that edits a
 *  pilot's criteria: they are locked on day 1. The full account export is
 *  the existing POST /me/data-export (lib/api/profile.ts exportMyData). */

import { getAccessTokenSync } from "../auth-session";
import { WORKSPACE_HEADER, getActiveWorkspace } from "../workspace";
import type {
  Pilot,
  PilotExportFormat,
  PilotExportView,
  PilotStartBody,
  PilotTemplate,
} from "../pilot";
import { pilotExportPath } from "../pilot";
import { api, BASE, normalizeError } from "./client";

export const getPilotTemplate = (): Promise<PilotTemplate> => api("/pilots/template");

export const getCurrentPilot = (): Promise<{ pilot: Pilot | null }> => api("/pilots/current");

export const listPilots = (): Promise<{ items: Pilot[] }> => api("/pilots");

export const getPilot = (id: string): Promise<Pilot> =>
  api(`/pilots/${encodeURIComponent(id)}`);

export const startPilot = (body: PilotStartBody): Promise<Pilot> =>
  api("/pilots", { method: "POST", body });

export const setScorecardEmails = (id: string, enabled: boolean): Promise<Pilot> =>
  api(`/pilots/${encodeURIComponent(id)}`, { method: "PATCH", body: { scorecard_emails: enabled } });

export const endPilot = (id: string): Promise<Pilot> =>
  api(`/pilots/${encodeURIComponent(id)}/end`, { method: "POST" });

/** The verdict export as a Blob (PDF/CSV are not JSON). Same auth +
 *  workspace headers as api() — the lib/api/meetingsLedger.ts pattern. */
export async function downloadPilotExport(
  id: string,
  format: PilotExportFormat,
  view: PilotExportView = "verdict",
): Promise<Blob> {
  const headers: Record<string, string> = {};
  const token = getAccessTokenSync();
  if (token) headers.Authorization = `Bearer ${token}`;
  const workspace = getActiveWorkspace();
  if (workspace) headers[WORKSPACE_HEADER] = workspace;
  const resp = await fetch(`${BASE}${pilotExportPath(id, format, view)}`, { headers });
  if (!resp.ok) throw await normalizeError(resp);
  return resp.blob();
}
