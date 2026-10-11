/**
 * Incidents shown on the public status page (/status, src/app/status/page.tsx).
 *
 * The page is part of the static export, so incidents are data compiled into
 * the bundle: posting, updating or resolving one is a pull request that edits
 * INCIDENTS below, and the next Vercel deploy publishes it. Steps and writing
 * rules: docs/program/STATUS_PAGE.md, "Posting an incident".
 *
 * Same format and rules as status-page/incidents/README.md (the optional
 * subdomain app), expressed as TypeScript so a typo fails `tsc`/`next build`
 * and src/tests/statusIncidents.test.ts checks every entry with
 * validateIncident():
 *   - id: "YYYY-MM-DD-<slug>", date = UTC date of the FIRST update; never
 *     change a published id.
 *   - updates oldest first; times are UTC ending in "Z", not in the future;
 *     at most one "resolved", and only as the latest.
 *   - components: ids from INCIDENT_COMPONENTS.
 *   - Facts only: what customers saw, when (UTC), what we did. No internal
 *     hostnames, error messages, queue names, customer names or counts.
 *
 * While an incident is not resolved, every listed component is shown at least
 * as bad as its impact (statusBoard.applyIncidents); it can never make a
 * component look better than the live checks.
 *
 * There are deliberately no example entries: an entry here is published as a
 * real event.
 */

export const INCIDENT_IMPACTS = ["none", "minor", "major", "critical", "maintenance"] as const;
export type IncidentImpact = (typeof INCIDENT_IMPACTS)[number];

export const INCIDENT_UPDATE_STATUSES = ["investigating", "identified", "monitoring", "resolved"] as const;
export type IncidentUpdateStatus = (typeof INCIDENT_UPDATE_STATUSES)[number];

/** "website" is the static site itself; the rest are /status/public ids. */
export const INCIDENT_COMPONENTS = [
  "website",
  "api",
  "background-processing",
  "ai-features",
  "booking-pages",
] as const;

export const INCIDENT_UPDATE_LABELS: Record<IncidentUpdateStatus, string> = {
  investigating: "Investigating",
  identified: "Identified",
  monitoring: "Monitoring",
  resolved: "Resolved",
};

export interface IncidentUpdate {
  status: IncidentUpdateStatus;
  /** UTC, e.g. "2026-10-11T14:05:00Z". */
  at: string;
  text: string;
}

export interface Incident {
  id: string;
  title: string;
  impact: IncidentImpact;
  components: string[];
  /** Oldest first. */
  updates: IncidentUpdate[];
}

export const INCIDENTS: readonly Incident[] = [
  // Newest first is not required; the page sorts. Example shape (do not
  // uncomment — it would publish a fake incident):
  // {
  //   id: "2026-10-11-scheduled-sends-delayed",
  //   title: "Scheduled sends delayed",
  //   impact: "major",
  //   components: ["background-processing"],
  //   updates: [
  //     { status: "investigating", at: "2026-10-11T14:05:00Z", text: "Scheduled emails are not going out. We are investigating." },
  //     { status: "resolved", at: "2026-10-11T14:40:00Z", text: "Sends resumed at 14:35 UTC." },
  //   ],
  // },
];

const ID_RE = /^(\d{4}-\d{2}-\d{2})-[a-z0-9]+(?:-[a-z0-9]+)*$/;
const UTC_RE = /^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z$/;
const MAX_TITLE = 120;

export function isResolved(incident: Incident): boolean {
  const last = incident.updates[incident.updates.length - 1];
  return last?.status === "resolved";
}

/** Human-readable problems with one incident; [] means it may be published. */
export function validateIncident(incident: Incident, now: Date = new Date()): string[] {
  const errors: string[] = [];
  const idMatch = ID_RE.exec(incident.id);
  if (!idMatch) errors.push(`id "${incident.id}" must be YYYY-MM-DD-<lowercase-slug>`);

  const title = incident.title.trim();
  if (!title || title.length > MAX_TITLE) errors.push(`title must be 1-${MAX_TITLE} characters`);

  if (!(INCIDENT_IMPACTS as readonly string[]).includes(incident.impact)) {
    errors.push(`impact "${incident.impact}" is not one of ${INCIDENT_IMPACTS.join(", ")}`);
  }

  if (incident.components.length === 0) errors.push("list at least one component");
  for (const c of incident.components) {
    if (!(INCIDENT_COMPONENTS as readonly string[]).includes(c)) {
      errors.push(`component "${c}" is not one of ${INCIDENT_COMPONENTS.join(", ")}`);
    }
  }

  if (incident.updates.length === 0) {
    errors.push("add at least one update");
    return errors;
  }

  let previous = -Infinity;
  incident.updates.forEach((u, i) => {
    if (!(INCIDENT_UPDATE_STATUSES as readonly string[]).includes(u.status)) {
      errors.push(`update ${i + 1}: status "${u.status}" is not valid`);
    }
    if (!u.text.trim()) errors.push(`update ${i + 1}: text is empty`);
    if (!UTC_RE.test(u.at)) {
      errors.push(`update ${i + 1}: time "${u.at}" must be UTC like 2026-10-11T14:05:00Z`);
      return;
    }
    const t = Date.parse(u.at);
    if (Number.isNaN(t)) {
      errors.push(`update ${i + 1}: time "${u.at}" is not a real date`);
      return;
    }
    if (t > now.getTime()) errors.push(`update ${i + 1}: time "${u.at}" is in the future`);
    if (t < previous) errors.push(`update ${i + 1}: updates must be in time order, oldest first`);
    previous = t;
    if (u.status === "resolved" && i !== incident.updates.length - 1) {
      errors.push(`update ${i + 1}: "resolved" must be the latest update (at most one)`);
    }
  });

  if (idMatch && UTC_RE.test(incident.updates[0].at) && idMatch[1] !== incident.updates[0].at.slice(0, 10)) {
    errors.push(`id date ${idMatch[1]} must equal the first update's UTC date ${incident.updates[0].at.slice(0, 10)}`);
  }
  return errors;
}

function latestAt(incident: Incident): number {
  const last = incident.updates[incident.updates.length - 1];
  return last ? Date.parse(last.at) : 0;
}

/** Open incidents first, then newest first by latest update. */
export function sortIncidents(list: readonly Incident[]): Incident[] {
  return [...list].sort((a, b) => {
    const openA = isResolved(a) ? 1 : 0;
    const openB = isResolved(b) ? 1 : 0;
    if (openA !== openB) return openA - openB;
    return latestAt(b) - latestAt(a);
  });
}
