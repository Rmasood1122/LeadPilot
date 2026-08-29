/**
 * When to tell the backend where the video is up to.
 *
 * Kept as pure functions, deliberately, and separate from the player
 * component. A YouTube player cannot be driven in jsdom, so anything tangled
 * up with the iframe is untestable in the unit suite — but the DECISION of
 * when to write is the part with the real failure modes (a request every
 * animation frame, or a seek that never gets recorded), and it belongs
 * somewhere it can be tested exhaustively without a browser.
 *
 * See src/tests/tutorial-progress.test.ts.
 */

/** Ordinary heartbeat while playing. */
export const REPORT_INTERVAL_MS = 10_000;

/** A position jump larger than this is a seek, not playback. */
export const SEEK_JUMP_SECONDS = 15;

/** Never write more often than this, whatever else is true. */
export const MIN_REPORT_GAP_MS = 3_000;

/** Mirrors COMPLETION_THRESHOLD_PERCENT in app/api/tutorials.py. */
export const COMPLETION_THRESHOLD_PERCENT = 90;

export interface ReportDecisionInput {
  /** Position at the previous report, in seconds. */
  lastPositionSeconds: number;
  /** Position now, in seconds. */
  positionSeconds: number;
  /** Wall-clock of the previous report. 0 = never reported. */
  lastReportAtMs: number;
  nowMs: number;
  /** Total length, if the player knows it yet. */
  durationSeconds: number | null;
  /** Whether the backend already considers this tutorial complete. */
  completedAlready: boolean;
}

/**
 * True when the current position is worth a PUT.
 *
 * Three reasons to write, in order of importance:
 *
 *  1. The user just crossed the completion threshold. This one must not wait
 *     for the next heartbeat: someone who watches to 90% and immediately
 *     closes the tab has genuinely finished the video, and losing that would
 *     silently withhold a badge they earned.
 *  2. They seeked. A jump is a deliberate move and the resume point is now
 *     wrong; waiting up to 10s to record it means a refresh in that window
 *     resumes somewhere they were not.
 *  3. The heartbeat elapsed. Ordinary playback.
 *
 * MIN_REPORT_GAP_MS is checked FIRST and overrides all three, so no
 * combination of events can turn this into a request per frame. Scrubbing
 * along a timeline fires a continuous stream of position changes, and every
 * one of them looks like a seek.
 */
export function shouldReportProgress(input: ReportDecisionInput): boolean {
  const {
    lastPositionSeconds, positionSeconds, lastReportAtMs, nowMs,
    durationSeconds, completedAlready,
  } = input;

  // Never reported before: record immediately so a resume point exists even
  // if the user closes the tab seconds later.
  if (lastReportAtMs === 0) return true;

  const sinceLastReport = nowMs - lastReportAtMs;
  if (sinceLastReport < MIN_REPORT_GAP_MS) return false;

  if (!completedAlready && durationSeconds && durationSeconds > 0) {
    const percent = (positionSeconds / durationSeconds) * 100;
    const previousPercent = (lastPositionSeconds / durationSeconds) * 100;
    if (percent >= COMPLETION_THRESHOLD_PERCENT &&
        previousPercent < COMPLETION_THRESHOLD_PERCENT) {
      return true;
    }
  }

  if (Math.abs(positionSeconds - lastPositionSeconds) >= SEEK_JUMP_SECONDS) {
    return true;
  }

  return sinceLastReport >= REPORT_INTERVAL_MS;
}

/**
 * Percent watched, clamped to 0-100.
 *
 * Returns 0 rather than NaN or Infinity when the duration is unknown or zero —
 * a NaN reaches the DOM as `width: NaN%`, which renders as a full-width bar
 * and reads as "finished".
 */
export function percentWatched(
  positionSeconds: number,
  durationSeconds: number | null,
): number {
  if (!durationSeconds || durationSeconds <= 0) return 0;
  const raw = (positionSeconds / durationSeconds) * 100;
  return Math.max(0, Math.min(100, raw));
}

/** "7:04" / "1:02:03". Returns "—" when the length is unknown. */
export function formatDuration(seconds: number | null | undefined): string {
  if (!seconds || seconds <= 0) return "—";
  const total = Math.floor(seconds);
  const h = Math.floor(total / 3600);
  const m = Math.floor((total % 3600) / 60);
  const s = total % 60;
  const pad = (n: number) => String(n).padStart(2, "0");
  return h > 0 ? `${h}:${pad(m)}:${pad(s)}` : `${m}:${pad(s)}`;
}

/**
 * The embed URL for a YouTube video.
 *
 * youtube-nocookie.com, not youtube.com: it is the privacy-preserving host
 * (no tracking cookie until the user actually plays), which matters because
 * this app ships a privacy policy and is bundled into an Android APK.
 *
 * enablejsapi=1 is what lets the IFrame API read playback position at all —
 * without it the player loads and reports nothing, so progress silently never
 * advances. rel=0 keeps "related videos" to the same channel at the end.
 */
export function youtubeEmbedUrl(
  youtubeId: string,
  opts: { startSeconds?: number; origin?: string } = {},
): string {
  const params = new URLSearchParams({
    enablejsapi: "1",
    rel: "0",
    modestbranding: "1",
    playsinline: "1",
  });
  if (opts.startSeconds && opts.startSeconds > 0) {
    params.set("start", String(Math.floor(opts.startSeconds)));
  }
  // The IFrame API refuses postMessage traffic when the origin does not match,
  // so this is required for progress reporting to work at all in a browser.
  if (opts.origin) params.set("origin", opts.origin);
  return `https://www.youtube-nocookie.com/embed/${encodeURIComponent(youtubeId)}?${params.toString()}`;
}
