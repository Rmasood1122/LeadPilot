/** Part 1 Feature 2 — the four sub-scores as a compact strip.
 *
 *  Used wherever a prospect is LISTED (CRM grid, kanban card, lead header).
 *  Four numbers rather than one, because "82 fit / 20 problem" and
 *  "50 across the board" average to the same overall and want opposite
 *  actions. Each carries its question as a tooltip — "Fit: 82" means nothing
 *  to someone reading it for the first time. */

import { Badge } from "@/components/ui/badge";
import {
  band,
  bandLabel,
  bandTone,
  dimensionName,
  dimensionQuestion,
  scoreText,
  summaryDimensions,
  type FptaSummary,
} from "@/lib/fpta";

export function FptaBadges({ lead, compact = false }: {
  lead: FptaSummary;
  compact?: boolean;
}) {
  if (lead.fpta_overall === null || lead.fpta_overall === undefined) {
    return compact ? null : <Badge tone="default">F-P-T-A not scored</Badge>;
  }
  const overall = band(lead.fpta_overall);

  return (
    <span className="inline-flex flex-wrap items-center gap-1"
          aria-label={`F-P-T-A ${lead.fpta_overall} out of 100 (${bandLabel(overall)})`}>
      <Badge tone={bandTone(overall)} className="tabular-nums"
             title={`Fit / Problem / Timing / Access — overall ${lead.fpta_overall}/100`}>
        {compact ? lead.fpta_overall : `F-P-T-A ${lead.fpta_overall}`}
      </Badge>
      {summaryDimensions(lead).map(({ key, score }) => (
        <Badge key={key} tone={bandTone(band(score))} className="tabular-nums"
               title={`${dimensionName(key)} ${scoreText(score)}/100 — ${dimensionQuestion(key)}`}>
          {dimensionName(key)[0]}
          <span className="ml-0.5">{scoreText(score)}</span>
        </Badge>
      ))}
    </span>
  );
}
