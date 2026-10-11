/**
 * The status vocabulary shared by every part of the page.
 *
 * `unknown` exists only here, never in the backend contract: it is what the
 * page shows for a component nothing could check, so the page never claims
 * "Operational" for something it did not verify.
 */

export const PUBLIC_STATUSES = [
  "operational",
  "degraded",
  "partial_outage",
  "major_outage",
  "maintenance",
] as const;

export type PublicStatus = (typeof PUBLIC_STATUSES)[number];
export type DisplayStatus = PublicStatus | "unknown";

export const STATUS_LABELS: Record<DisplayStatus, string> = {
  operational: "Operational",
  degraded: "Degraded performance",
  partial_outage: "Partial outage",
  major_outage: "Major outage",
  maintenance: "Under maintenance",
  unknown: "No data",
};

export function isPublicStatus(value: unknown): value is PublicStatus {
  return typeof value === "string" && (PUBLIC_STATUSES as readonly string[]).includes(value);
}

/** Severity for "worst of" decisions. Maintenance and unknown are handled by callers. */
const SEVERITY: Record<PublicStatus, number> = {
  operational: 0,
  maintenance: 1,
  degraded: 2,
  partial_outage: 3,
  major_outage: 4,
};

export function severity(status: PublicStatus): number {
  return SEVERITY[status];
}

/** The worse of two known statuses. */
export function worse(a: PublicStatus, b: PublicStatus): PublicStatus {
  return SEVERITY[a] >= SEVERITY[b] ? a : b;
}
