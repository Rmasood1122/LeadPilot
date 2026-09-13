import { getAccessTokenSync } from "../auth-session";
import { WORKSPACE_HEADER, getActiveWorkspace } from "../workspace";
import type { ChainVerification } from "../audit";
import { api, BASE, normalizeError } from "./client";

export const verifyAuditTrail = () => api<ChainVerification>("/audit/trail/verify");

/** The signed export as a Blob. Not through api(): the PDF is binary, and the
 *  JSON is kept byte-for-byte as the server signed it (re-serialising a parsed
 *  object could reorder nothing today, but a signed artefact should not depend
 *  on that). Same auth + workspace headers as api(). */
export async function downloadAuditExport(format: "json" | "pdf"): Promise<Blob> {
  const headers: Record<string, string> = {};
  const token = getAccessTokenSync();
  if (token) headers.Authorization = `Bearer ${token}`;
  const workspace = getActiveWorkspace();
  if (workspace) headers[WORKSPACE_HEADER] = workspace;
  const resp = await fetch(`${BASE}/audit/trail/export?format=${format}`, { headers });
  if (!resp.ok) throw await normalizeError(resp);
  return resp.blob();
}
