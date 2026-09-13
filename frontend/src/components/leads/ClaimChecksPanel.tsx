"use client";

/** Feature A1 — what the claim engine checked in this lead's outreach.
 *  Every factual claim an AI-written message made about the prospect, whether
 *  it was backed by stored data (and by what), and what was removed or
 *  rewritten before sending when it was not. */

import { useQuery } from "@tanstack/react-query";
import { ShieldCheck } from "lucide-react";

import { getLeadClaimChecks } from "@/lib/api/claims";
import {
  categoryLabel,
  describeMissing,
  groupByMessage,
  sourceLabel,
  verdictTone,
} from "@/lib/claims";
import { Badge } from "@/components/ui/badge";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { AsyncState } from "@/components/ui/skeleton";

export function ClaimChecksPanel({ leadId }: { leadId: string }) {
  const query = useQuery({
    queryKey: ["lead", leadId, "claim-checks"],
    queryFn: () => getLeadClaimChecks(leadId),
  });
  const groups = groupByMessage(query.data ?? []);

  return (
    <AsyncState isLoading={query.isLoading} error={query.error}>
      {groups.length === 0 ? (
        <p className="text-sm text-muted-foreground">
          No factual claims about this lead have been checked yet. Every AI-written message is
          checked against stored data before it sends.
        </p>
      ) : (
        <div className="space-y-4">
          {groups.map((group) => (
            <Card key={group.key}>
              <CardHeader className="flex-row items-center justify-between gap-2">
                <CardTitle className="flex items-center gap-2 text-base">
                  <ShieldCheck size={16} aria-hidden="true" />
                  {group.created_at ? new Date(group.created_at).toLocaleString() : "Message"}
                </CardTitle>
                <Badge tone={group.removed ? "warning" : "success"}>
                  {group.removed ? `${group.removed} removed` : "All claims verified"}
                </Badge>
              </CardHeader>
              <CardContent>
                <ul className="space-y-3 text-sm">
                  {group.checks.map((check) => (
                    <li key={check.id} className="space-y-1 border-l-2 border-border pl-3">
                      <div className="flex flex-wrap items-center gap-2">
                        <Badge tone={verdictTone(check.verdict)}>{check.verdict}</Badge>
                        <span className="text-xs text-muted-foreground">
                          {categoryLabel(check.category)} · {check.channel} {check.field}
                          {check.extractor === "model" ? " · found by AI" : ""}
                        </span>
                      </div>
                      <p className={check.verdict === "verified" ? "" : "line-through opacity-70"}>
                        {check.claim_text}
                      </p>
                      {check.verdict === "verified" ? (
                        <p className="text-xs text-muted-foreground">
                          Backed by {sourceLabel(check.evidence_source)}
                          {check.evidence_excerpt ? `: “${check.evidence_excerpt.slice(0, 140)}”` : ""}
                        </p>
                      ) : (
                        <>
                          {check.replacement_text && (
                            <p className="text-xs">Replaced with: “{check.replacement_text}”</p>
                          )}
                          {check.unsupported.length > 0 && (
                            <p className="text-xs text-muted-foreground">
                              Not found in stored data: {check.unsupported.map(describeMissing).join(", ")}
                            </p>
                          )}
                        </>
                      )}
                    </li>
                  ))}
                </ul>
              </CardContent>
            </Card>
          ))}
        </div>
      )}
    </AsyncState>
  );
}
