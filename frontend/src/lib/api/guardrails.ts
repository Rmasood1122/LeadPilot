import { api } from "./client";
import type {
  CrmSyncResult,
  Exclusion,
  ExclusionKind,
  ExclusionPage,
  GuardrailsStatus,
  ImportResult,
  LibraryEntry,
  LibraryKind,
} from "../guardrails";

/** F05 Guardrails Studio. `body` is an OBJECT — api() stringifies it itself. */

export const getGuardrailsStatus = () => api<GuardrailsStatus>("/guardrails/status");

export function listExclusions(
  opts: { kind?: ExclusionKind; q?: string; includeRemoved?: boolean; limit?: number } = {},
) {
  const params = new URLSearchParams();
  if (opts.kind) params.set("kind", opts.kind);
  if (opts.q) params.set("q", opts.q);
  if (opts.includeRemoved) params.set("include_removed", "true");
  params.set("limit", String(opts.limit ?? 200));
  return api<ExclusionPage>(`/guardrails/exclusions?${params.toString()}`);
}

export const addExclusion = (input: {
  kind: ExclusionKind; value: string; reason: string; note?: string | null;
}) => api<Exclusion & { status: string }>("/guardrails/exclusions",
  { method: "POST", body: input });

export const removeExclusion = (id: string) =>
  api<Exclusion>(`/guardrails/exclusions/${id}`, { method: "DELETE" });

export const importExclusions = (csv: string, defaultReason: string) =>
  api<ImportResult>("/guardrails/exclusions/import",
    { method: "POST", body: { csv, default_reason: defaultReason } });

export const syncExclusionsFromCrm = () =>
  api<CrmSyncResult>("/guardrails/exclusions/crm-sync", { method: "POST", body: {} });

export const listGuardrailProducts = () =>
  api<{ items: { id: string; name: string }[] }>("/guardrails/products");

export const listLibrary = (productId?: string | null) =>
  api<{ product_id: string | null; items: LibraryEntry[] }>(
    `/guardrails/library${productId ? `?product_id=${productId}` : ""}`);

export const addLibraryEntry = (input: {
  kind: LibraryKind; text: string; product_id?: string | null; source_url?: string | null;
}) => api<LibraryEntry>("/guardrails/library", { method: "POST", body: input });

export const removeLibraryEntry = (id: string) =>
  api<void>(`/guardrails/library/${id}`, { method: "DELETE" });
