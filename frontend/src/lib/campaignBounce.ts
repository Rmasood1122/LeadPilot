/** The campaign bounce auto-pause, as the server applies it
 *  (app/services/sequence_engine.py: pause when rate > threshold; the
 *  threshold is the workspace compliance rule's, never above the 3% baseline). */

const BASELINE_THRESHOLD = 0.03;

interface BounceStats {
  bounce_rate: number;
  bounce_pause_threshold?: number | null;
}

function threshold(stats: BounceStats): number {
  return stats.bounce_pause_threshold ?? BASELINE_THRESHOLD;
}

function percent(value: number): string {
  return `${Number((value * 100).toFixed(1))}%`;
}

export function bounceOverThreshold(stats: BounceStats): boolean {
  return stats.bounce_rate > threshold(stats);
}

export function bouncePauseText(stats: BounceStats): string {
  return `Bounce rate auto-pause: ${percent(stats.bounce_rate)} is above the ` +
    `${percent(threshold(stats))} limit. Fix deliverability issues, then resume.`;
}
