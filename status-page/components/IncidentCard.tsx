import Link from "next/link";

import { IMPACT_LABELS, UPDATE_STATUS_LABELS, type Incident } from "../lib/incidents.ts";
import { COMPONENTS } from "../lib/config.ts";
import { LocalTime } from "./LocalTime.tsx";

const NAMES = Object.fromEntries(COMPONENTS.map((c) => [c.id, c.name]));

/** One incident: title, impact, affected components and its updates (newest first). */
export function IncidentCard({
  incident,
  headingLevel = 3,
  showAllUpdates = true,
  link = true,
}: {
  incident: Incident;
  headingLevel?: 2 | 3;
  showAllUpdates?: boolean;
  link?: boolean;
}) {
  const Heading = headingLevel === 2 ? "h2" : "h3";
  const updates = showAllUpdates ? incident.updates : incident.updates.slice(0, 1);
  return (
    <article className={`incident impact-${incident.impact}`}>
      <Heading className="incident-title">
        {link ? <Link href={`/incidents/${incident.slug}`}>{incident.title}</Link> : incident.title}
      </Heading>
      <p className="meta">
        <span className="tag">{incident.resolved ? "Resolved" : UPDATE_STATUS_LABELS[incident.updates[0]!.status]}</span>
        <span>Impact: {IMPACT_LABELS[incident.impact]}</span>
        <span>Affects: {incident.components.map((c) => NAMES[c]).join(", ")}</span>
      </p>
      <ol className="updates">
        {updates.map((u) => (
          <li key={`${u.at}-${u.status}`}>
            <strong>{UPDATE_STATUS_LABELS[u.status]}</strong> — {u.text}
            <br />
            <small>
              <LocalTime iso={u.at} />
            </small>
          </li>
        ))}
      </ol>
    </article>
  );
}
