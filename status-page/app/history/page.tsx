import type { Metadata } from "next";

import { formatMonth } from "../../lib/format.ts";
import { incidentsDir, loadIncidents, type Incident } from "../../lib/incidents.ts";
import { IncidentCard } from "../../components/IncidentCard.tsx";

export const metadata: Metadata = { title: "Incident history" };

export default function History() {
  const incidents = loadIncidents(incidentsDir());
  const byMonth = new Map<string, Incident[]>();
  for (const i of incidents) {
    const key = formatMonth(i.startedAt);
    byMonth.set(key, [...(byMonth.get(key) ?? []), i]);
  }
  return (
    <>
      <h1>Incident history</h1>
      <p>
        Every incident and maintenance window posted on this page, newest first. Also available as{" "}
        <a href="/history.rss">RSS</a> and <a href="/history.atom">Atom</a>.
      </p>
      {incidents.length === 0 ? (
        <p className="empty">No incidents have been reported.</p>
      ) : (
        [...byMonth.entries()].map(([month, list]) => (
          <section key={month} aria-labelledby={`m-${month.replace(/\s/g, "-")}`}>
            <h2 id={`m-${month.replace(/\s/g, "-")}`}>{month}</h2>
            {list.map((i) => (
              <IncidentCard key={i.slug} incident={i} showAllUpdates={false} />
            ))}
          </section>
        ))
      )}
    </>
  );
}
