import type { Metadata } from "next";
import Link from "next/link";
import { notFound } from "next/navigation";

import { incidentsDir, loadIncidents } from "../../../lib/incidents.ts";
import { IncidentCard } from "../../../components/IncidentCard.tsx";

// Incidents change only by deploy (a merged PR), so every known incident is
// built ahead. An unknown slug falls through to notFound() (a 404). Not
// `dynamicParams = false`: Next 15.5 then logs a spurious NoFallbackError
// stack for every unknown URL, which would bury real errors in the logs.

export function generateStaticParams(): { slug: string }[] {
  return loadIncidents(incidentsDir()).map((i) => ({ slug: i.slug }));
}

type Props = { params: Promise<{ slug: string }> };

function find(slug: string) {
  return loadIncidents(incidentsDir()).find((i) => i.slug === slug);
}

export async function generateMetadata({ params }: Props): Promise<Metadata> {
  const incident = find((await params).slug);
  return { title: incident ? incident.title : "Incident not found" };
}

export default async function IncidentPage({ params }: Props) {
  const incident = find((await params).slug);
  if (!incident) notFound();
  return (
    <>
      <p>
        <Link href="/history">← Incident history</Link>
      </p>
      <IncidentCard incident={incident} headingLevel={2} link={false} />
      {incident.body.length > 0 && (
        <section className="body-text" aria-label="Details">
          {incident.body.map((p, n) => (
            <p key={n}>{p}</p>
          ))}
        </section>
      )}
    </>
  );
}
