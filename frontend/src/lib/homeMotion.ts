/** Motion rules for the home page, pure so they are unit-tested in
 *  src/tests/homeMotion.test.ts.
 *
 *  - prefers-reduced-motion: reduce => the video never starts by itself and
 *    nothing reveals on scroll (content is simply there).
 *  - A person's own choice always wins: pressing Pause keeps it paused while
 *    scrolling; pressing Play plays it even with reduced motion on.
 *  - The video pauses while it is off screen (saves battery) and resumes
 *    when it comes back, unless the person paused it. */

export const REDUCED_MOTION_QUERY = "(prefers-reduced-motion: reduce)";

export function prefersReducedMotion(): boolean {
  try {
    return typeof window !== "undefined" && !!window.matchMedia?.(REDUCED_MOTION_QUERY).matches;
  } catch {
    return false;
  }
}

export type PlayChoice = "play" | "pause" | null;

export function shouldPlay(s: { reducedMotion: boolean; choice: PlayChoice; inView: boolean }): boolean {
  if (!s.inView) return false;
  if (s.choice === "pause") return false;
  if (s.choice === "play") return true;
  return !s.reducedMotion;
}

/** "animate": hide below-the-fold sections until they scroll in.
 *  "static": show everything now (reduced motion, no IntersectionObserver,
 *  or no JavaScript at all, since the server HTML never hides anything). */
export function revealMode(s: { reducedMotion: boolean; hasObserver: boolean }): "animate" | "static" {
  return !s.reducedMotion && s.hasObserver ? "animate" : "static";
}

/** Roving focus for the stage tabs (WAI-ARIA tabs pattern, horizontal and
 *  vertical arrows both work, Home/End jump to the ends). Returns the new
 *  index, or null for a key the tab list does not handle. */
export function nextTabIndex(key: string, current: number, count: number): number | null {
  switch (key) {
    case "ArrowRight":
    case "ArrowDown":
      return (current + 1) % count;
    case "ArrowLeft":
    case "ArrowUp":
      return (current - 1 + count) % count;
    case "Home":
      return 0;
    case "End":
      return count - 1;
    default:
      return null;
  }
}
