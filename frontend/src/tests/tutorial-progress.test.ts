/**
 * Unit tests for the tutorial progress-reporting decision (Feature 2).
 *
 * A YouTube player cannot be driven in jsdom, so this covers the part that
 * actually decides when to write — the part whose failure modes are a request
 * per animation frame, or a seek that is never recorded.
 */

import { describe, expect, it } from "vitest";
import {
  COMPLETION_THRESHOLD_PERCENT,
  MIN_REPORT_GAP_MS,
  REPORT_INTERVAL_MS,
  SEEK_JUMP_SECONDS,
  formatDuration,
  percentWatched,
  shouldReportProgress,
  youtubeEmbedUrl,
} from "@/lib/tutorial-progress";

const base = {
  lastPositionSeconds: 0,
  positionSeconds: 0,
  lastReportAtMs: 1_000_000,
  nowMs: 1_000_000,
  durationSeconds: 600 as number | null,
  completedAlready: false,
};

describe("shouldReportProgress", () => {
  it("always reports the very first position", () => {
    // A resume point must exist even if the tab closes seconds later.
    expect(shouldReportProgress({ ...base, lastReportAtMs: 0 })).toBe(true);
  });

  it("does not report again inside the minimum gap", () => {
    expect(
      shouldReportProgress({
        ...base,
        nowMs: base.lastReportAtMs + MIN_REPORT_GAP_MS - 1,
        positionSeconds: 300,
      }),
    ).toBe(false);
  });

  it("the minimum gap beats a seek", () => {
    // Scrubbing along a timeline fires a continuous stream of position
    // changes, every one of which looks like a seek. Without this the player
    // would hammer the API for the whole drag.
    expect(
      shouldReportProgress({
        ...base,
        nowMs: base.lastReportAtMs + 100,
        lastPositionSeconds: 0,
        positionSeconds: 500,
      }),
    ).toBe(false);
  });

  it("reports on the heartbeat during ordinary playback", () => {
    expect(
      shouldReportProgress({
        ...base,
        nowMs: base.lastReportAtMs + REPORT_INTERVAL_MS,
        lastPositionSeconds: 10,
        positionSeconds: 20,
      }),
    ).toBe(true);
  });

  it("stays quiet between heartbeats", () => {
    expect(
      shouldReportProgress({
        ...base,
        nowMs: base.lastReportAtMs + REPORT_INTERVAL_MS - 1,
        lastPositionSeconds: 10,
        positionSeconds: 15,
      }),
    ).toBe(false);
  });

  it("reports a seek without waiting for the heartbeat", () => {
    // The resume point is wrong the moment they jump; waiting up to 10s means
    // a refresh in that window resumes somewhere they never were.
    expect(
      shouldReportProgress({
        ...base,
        nowMs: base.lastReportAtMs + MIN_REPORT_GAP_MS,
        lastPositionSeconds: 10,
        positionSeconds: 10 + SEEK_JUMP_SECONDS,
      }),
    ).toBe(true);
  });

  it("treats a backwards seek as a seek too", () => {
    expect(
      shouldReportProgress({
        ...base,
        nowMs: base.lastReportAtMs + MIN_REPORT_GAP_MS,
        lastPositionSeconds: 400,
        positionSeconds: 10,
      }),
    ).toBe(true);
  });

  it("reports immediately on crossing the completion threshold", () => {
    // Someone who watches to 90% and closes the tab has finished the video.
    // Losing that silently withholds a badge they earned.
    const duration = 100;
    expect(
      shouldReportProgress({
        ...base,
        nowMs: base.lastReportAtMs + MIN_REPORT_GAP_MS,
        durationSeconds: duration,
        lastPositionSeconds: 89,
        positionSeconds: 90,
      }),
    ).toBe(true);
  });

  it("does not re-trigger on the threshold once already complete", () => {
    expect(
      shouldReportProgress({
        ...base,
        nowMs: base.lastReportAtMs + MIN_REPORT_GAP_MS,
        durationSeconds: 100,
        lastPositionSeconds: 89,
        positionSeconds: 90,
        completedAlready: true,
      }),
    ).toBe(false);
  });

  it("does not fire the threshold rule twice for one crossing", () => {
    expect(
      shouldReportProgress({
        ...base,
        nowMs: base.lastReportAtMs + MIN_REPORT_GAP_MS,
        durationSeconds: 100,
        lastPositionSeconds: 91, // already past it
        positionSeconds: 92,
      }),
    ).toBe(false);
  });

  it("copes with an unknown duration", () => {
    expect(() =>
      shouldReportProgress({
        ...base,
        durationSeconds: null,
        nowMs: base.lastReportAtMs + REPORT_INTERVAL_MS,
      }),
    ).not.toThrow();
  });

  it("mirrors the backend threshold", () => {
    // Drift here means the UI and the database disagree about "complete".
    expect(COMPLETION_THRESHOLD_PERCENT).toBe(90);
  });
});

describe("percentWatched", () => {
  it("computes a percentage", () => {
    expect(percentWatched(30, 120)).toBe(25);
  });

  it("clamps above 100", () => {
    // Players can report a position a shade past their own duration.
    expect(percentWatched(130, 120)).toBe(100);
  });

  it("returns 0 for an unknown or zero duration, never NaN", () => {
    // NaN reaches the DOM as `width: NaN%`, which renders full-width and reads
    // as "finished" for a video nobody has started.
    expect(percentWatched(30, null)).toBe(0);
    expect(percentWatched(30, 0)).toBe(0);
    expect(Number.isNaN(percentWatched(30, null))).toBe(false);
  });

  it("never goes negative", () => {
    expect(percentWatched(-5, 120)).toBe(0);
  });
});

describe("formatDuration", () => {
  it.each([
    [null, "—"],
    [0, "—"],
    [undefined, "—"],
    [59, "0:59"],
    [60, "1:00"],
    [424, "7:04"],
    [3723, "1:02:03"],
  ])("formats %s as %s", (input, expected) => {
    expect(formatDuration(input as number | null)).toBe(expected);
  });
});

describe("youtubeEmbedUrl", () => {
  it("uses the no-cookie host", () => {
    // The app ships a privacy policy and is bundled into an Android APK.
    expect(youtubeEmbedUrl("abc123")).toContain(
      "https://www.youtube-nocookie.com/embed/abc123",
    );
  });

  it("enables the JS API", () => {
    // Without enablejsapi the player loads and reports nothing, so progress
    // silently never advances.
    expect(youtubeEmbedUrl("abc123")).toContain("enablejsapi=1");
  });

  it("passes a resume point", () => {
    expect(youtubeEmbedUrl("abc123", { startSeconds: 42 })).toContain("start=42");
  });

  it("omits start at position zero", () => {
    expect(youtubeEmbedUrl("abc123", { startSeconds: 0 })).not.toContain("start=");
  });

  it("floors a fractional resume point", () => {
    expect(youtubeEmbedUrl("abc123", { startSeconds: 42.9 })).toContain("start=42");
  });

  it("escapes the video id", () => {
    expect(youtubeEmbedUrl("a/b?c")).toContain("embed/a%2Fb%3Fc");
  });
});
