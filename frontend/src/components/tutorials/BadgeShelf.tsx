import { Award, Lock } from "lucide-react";
import { Badge } from "@/components/ui/badge";
import { ProgressBar } from "./ProgressBar";
import type { TutorialBadge } from "@/lib/api/types";

/**
 * Completion badges.
 *
 * Unearned badges are SHOWN, greyed, with their remaining count — not hidden.
 * A badge you cannot see is not a goal; showing "2 of 3" is what makes the
 * third video worth watching. It also means the shelf does not reflow as
 * badges are earned.
 *
 * Earned state is derived server-side from progress and is never stored, so
 * resetting a video correctly revokes its badge.
 */
export function BadgeShelf({ badges }: { badges: TutorialBadge[] }) {
  if (!badges.length) return null;
  const earnedCount = badges.filter((b) => b.earned).length;

  return (
    <section aria-labelledby="badges-heading" className="space-y-3">
      <div className="flex items-baseline justify-between">
        <h2 id="badges-heading" className="text-sm font-semibold">
          Badges
        </h2>
        <span className="text-xs text-muted-foreground">
          {earnedCount} of {badges.length} earned
        </span>
      </div>
      <ul className="grid gap-3 sm:grid-cols-2 lg:grid-cols-4">
        {badges.map((badge) => {
          const pct = badge.required_total
            ? (badge.required_completed / badge.required_total) * 100
            : 0;
          return (
            <li
              key={badge.slug}
              data-testid={`badge-${badge.slug}`}
              data-earned={badge.earned ? "true" : "false"}
              className={
                "rounded border p-3 " +
                (badge.earned
                  ? "border-success/40 bg-success/5"
                  : "border-border bg-card opacity-70")
              }
            >
              <div className="flex items-center gap-2">
                {badge.earned ? (
                  <Award size={18} className="text-success" aria-hidden="true" />
                ) : (
                  <Lock size={18} className="text-muted-foreground" aria-hidden="true" />
                )}
                <span className="text-sm font-medium">{badge.label}</span>
              </div>
              <p className="mt-1 text-xs text-muted-foreground">
                {badge.description}
              </p>
              {badge.earned ? (
                <Badge tone="success" className="mt-2">
                  Earned
                </Badge>
              ) : (
                <div className="mt-2 space-y-1">
                  <ProgressBar
                    percent={pct}
                    label={`${badge.label} progress`}
                  />
                  <p className="text-xs text-muted-foreground">
                    {badge.required_completed} of {badge.required_total} complete
                  </p>
                </div>
              )}
            </li>
          );
        })}
      </ul>
    </section>
  );
}
