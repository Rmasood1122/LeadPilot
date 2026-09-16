"use client";

/** Part 1 Feature 10 — where each enriched field came from.
 *
 *  Every field on a prospect arrives from somewhere, and those somewheres are
 *  not equally trustworthy. A title typed by a person is not a title Apollo
 *  guessed from a job posting; an email a verifier confirmed is not one built
 *  from a first name and a domain. Today they render identically, and someone
 *  about to write "I saw you're hiring three more inspectors" has no way to
 *  know which they are looking at.
 *
 *  Source and AGE are shown separately, on purpose: a weak source needs a
 *  better source, an old fact needs a refresh, and one blended score would
 *  hide which. */

import { useQuery } from "@tanstack/react-query";
import { Info } from "lucide-react";

import { getLeadProvenance } from "@/lib/api/provenance";
import {
  ageLabel,
  confidenceTone,
  flagged,
  hoverText,
  needsChecking,
  provenanceHeadline,
  stalenessTone,
  type ProvenanceItem,
} from "@/lib/provenance";
import { Badge } from "@/components/ui/badge";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { AsyncState } from "@/components/ui/skeleton";

export function ProvenancePanel({ leadId }: { leadId: string }) {
  const { data, isLoading, error } = useQuery({
    queryKey: ["lead-provenance", leadId],
    queryFn: () => getLeadProvenance(leadId),
  });
  const check = flagged(data);

  return (
    <Card aria-label="Where this data came from">
      <CardHeader className="gap-1">
        <CardTitle className="flex items-center gap-2 text-sm">
          <Info size={16} aria-hidden="true" /> Where this data came from
        </CardTitle>
        <p className="text-xs text-muted-foreground">{provenanceHeadline(data)}</p>
      </CardHeader>
      <CardContent className="space-y-3 text-sm">
        <AsyncState isLoading={isLoading} error={error}
                    empty={!!data && !data.tracked} emptyLabel="">
          {data?.tracked && (
            <>
              {check.length > 0 && (
                <p className="text-sm">
                  Check before quoting back to them:{" "}
                  {check.map((item) => item.label).join(", ")}.
                </p>
              )}
              <ul className="space-y-1">
                {data.items.map((item) => <FieldRow key={item.field} item={item} />)}
              </ul>
            </>
          )}
        </AsyncState>
      </CardContent>
    </Card>
  );
}

/** One row — and the `title` attribute is the hover this feature is really
 *  about: the whole story in one string, wherever the field is rendered. */
function FieldRow({ item }: { item: ProvenanceItem }) {
  return (
    <li className="flex flex-wrap items-center gap-2" title={hoverText(item)}>
      <span className="w-32 shrink-0 text-muted-foreground">{item.label}</span>
      {item.value && <span className="truncate">{item.value}</span>}
      <Badge tone={confidenceTone(item.confidence)}>
        {item.source_label}
        {item.confidence !== null && ` · ${Math.round(item.confidence * 100)}%`}
      </Badge>
      <Badge tone={stalenessTone(item.staleness.band)}>{ageLabel(item)}</Badge>
      {needsChecking(item) && <Badge tone="warning">Check this</Badge>}
    </li>
  );
}

/** The inline hover used wherever a single enriched field is rendered outside
 *  this panel — the lead header, the CRM grid. Renders nothing when the field
 *  has no tag, rather than an empty marker that invites a click. */
export function ProvenanceTag({ item }: { item: ProvenanceItem | null | undefined }) {
  if (!item) return null;
  return (
    <Badge tone={confidenceTone(item.confidence)} title={hoverText(item)}>
      {item.source_label}
    </Badge>
  );
}
