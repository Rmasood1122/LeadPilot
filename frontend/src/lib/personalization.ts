/** Pure helpers for Feature Group 2's UI (unit-tested in
 *  src/tests/personalization.test.ts). */

export const MAX_SAMPLES = 5;
export const MIN_SAMPLE_CHARS = 40;

/** Mirrors app/services/style_profile.py::clean_samples, so the form can
 *  say what is wrong before a round trip. Returns an error or null. */
export function sampleError(samples: string[]): string | null {
  const filled = samples.map((s) => s.trim()).filter(Boolean);
  if (filled.length === 0) return "Paste at least one sample of your writing.";
  if (filled.length > MAX_SAMPLES) return `At most ${MAX_SAMPLES} samples.`;
  const short = filled.findIndex((s) => s.length < MIN_SAMPLE_CHARS);
  if (short >= 0) {
    return `Sample ${short + 1} is too short to show a style (at least ${MIN_SAMPLE_CHARS} characters).`;
  }
  return null;
}

/** Mirrors loom_video.loom_embed_id. */
export function isLoomShareUrl(url: string): boolean {
  return /loom\.com\/(share|embed)\/[a-f0-9]{32}/i.test(url.trim());
}

/** Mirrors linkedin_posts.public_identifier. */
export function isLinkedInProfileUrl(url: string): boolean {
  return /linkedin\.com\/in\/[^/?#]+/i.test(url.trim());
}

const FORMALITY = ["", "very casual", "casual", "neutral", "formal", "very formal"];

export function formalityLabel(n: number | null | undefined): string {
  return FORMALITY[Math.max(1, Math.min(5, Math.round(n ?? 3)))];
}

/** "3 days ago" style age for a fetched-at timestamp; "never" when null. */
export function fetchedAgo(iso: string | null | undefined, now = new Date()): string {
  if (!iso) return "never";
  const then = new Date(iso);
  if (Number.isNaN(then.getTime())) return "never";
  const minutes = Math.max(0, Math.round((now.getTime() - then.getTime()) / 60_000));
  if (minutes < 60) return minutes <= 1 ? "just now" : `${minutes} minutes ago`;
  const hours = Math.round(minutes / 60);
  if (hours < 24) return `${hours} hour${hours === 1 ? "" : "s"} ago`;
  const days = Math.round(hours / 24);
  return `${days} day${days === 1 ? "" : "s"} ago`;
}
