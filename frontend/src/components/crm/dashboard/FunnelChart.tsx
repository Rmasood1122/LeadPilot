"use client";

/** The pipeline funnel.
 *
 * Drawn as proportional horizontal bars rather than the classic tapering
 * trapezoid. A trapezoid encodes each stage's size as an AREA, and people
 * read areas badly — two stages differing by 40% look nearly identical. Bar
 * length is a position-along-a-common-scale encoding, which is the most
 * accurately read of them all, and it leaves room on the right for the
 * conversion figure that is the actual point of the chart.
 *
 * Each row shows `reached` (leads that got to this stage or past it) as the
 * bar, `current` (leads sitting here now) as a secondary number, and the
 * conversion from the previous stage. See the backend docstring for why
 * `reached` is cumulative — the short version is that status is a single
 * value, so dividing the raw columns reports conversions above 100%.
 */

import type { CrmFunnelStage } from "@/lib/api/types";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { formatCount, formatRate, stageLabel, useChartPalette } from "./primitives";

export function FunnelChart({ stages }: { stages: CrmFunnelStage[] }) {
  const palette = useChartPalette();
  const top = stages.length > 0 ? Math.max(...stages.map((s) => s.reached), 1) : 1;

  return (
    <Card>
      <CardHeader>
        <CardTitle className="text-sm">Pipeline funnel</CardTitle>
        <p className="text-xs text-muted-foreground">
          Bar length is leads that reached each stage or moved past it.
          Conversion is against the stage above.
        </p>
      </CardHeader>
      <CardContent className="space-y-2">
        {stages.map((stage) => {
          const share = top > 0 ? stage.reached / top : 0;
          // A drop-off worth flagging: fewer than half carried through.
          const weak =
            stage.conversion_from_previous !== null &&
            stage.conversion_from_previous < 0.5;
          return (
            <div key={stage.stage} className="grid grid-cols-[9rem_1fr_5rem] items-center gap-3">
              <span className="truncate text-xs font-medium">
                {stageLabel(stage.stage)}
              </span>
              <div
                className="relative h-6 rounded bg-muted"
                role="img"
                aria-label={`${stageLabel(stage.stage)}: ${stage.reached} reached, ${stage.current} currently here`}
              >
                <div
                  className="h-full rounded transition-[width] duration-300"
                  style={{
                    width: `${Math.max(share * 100, stage.reached > 0 ? 2 : 0)}%`,
                    backgroundColor: palette.primary,
                  }}
                />
                <span className="absolute inset-y-0 left-2 flex items-center text-xs font-medium text-primary-foreground mix-blend-difference tabular-nums">
                  {formatCount(stage.reached)}
                </span>
                {stage.current > 0 && (
                  <span
                    className="absolute inset-y-0 right-2 flex items-center text-[11px] text-muted-foreground tabular-nums"
                    title={`${stage.current} lead(s) are sitting at this stage right now`}
                  >
                    {formatCount(stage.current)} here
                  </span>
                )}
              </div>
              <span
                className={`text-right text-xs tabular-nums ${
                  weak ? "text-[rgb(var(--warning))]" : "text-muted-foreground"
                }`}
                title={
                  stage.conversion_from_previous === null
                    ? "First stage — nothing to convert from"
                    : "Share of the previous stage that reached this one"
                }
              >
                {stage.conversion_from_previous === null
                  ? "—"
                  : formatRate(stage.conversion_from_previous, 0)}
              </span>
            </div>
          );
        })}
      </CardContent>
    </Card>
  );
}
