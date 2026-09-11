/** ai_booking_likelihood as a compact badge (kanban card, CRM grid, lead page). */

import { Badge } from "@/components/ui/badge";
import { scoreBand } from "@/lib/lead-score";

export function ScoreBadge({
  score,
  reason,
  compact = false,
}: {
  score: number | null | undefined;
  reason?: string | null;
  compact?: boolean;
}) {
  const band = scoreBand(score);
  if (score === null || score === undefined) {
    return compact ? null : <Badge tone="default">Not scored</Badge>;
  }
  return (
    <Badge
      tone={band.tone}
      title={reason ? `AI booking likelihood ${score}/100 — ${reason}` : `AI booking likelihood ${score}/100`}
      aria-label={`AI booking likelihood ${score} out of 100 (${band.label})`}
      className="tabular-nums"
    >
      {compact ? score : `${score} · ${band.label}`}
    </Badge>
  );
}
