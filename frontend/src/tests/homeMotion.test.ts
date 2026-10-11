import { describe, expect, it } from "vitest";

import { nextTabIndex, revealMode, shouldPlay } from "@/lib/homeMotion";

describe("home video: reduced motion and the visitor's own choice", () => {
  it("plays by itself only without reduced motion, and only on screen", () => {
    expect(shouldPlay({ reducedMotion: false, choice: null, inView: true })).toBe(true);
    expect(shouldPlay({ reducedMotion: true, choice: null, inView: true })).toBe(false);
    expect(shouldPlay({ reducedMotion: false, choice: null, inView: false })).toBe(false);
  });

  it("Pause wins, even after scrolling away and back", () => {
    expect(shouldPlay({ reducedMotion: false, choice: "pause", inView: true })).toBe(false);
  });

  it("Play wins over reduced motion (the visitor asked for it)", () => {
    expect(shouldPlay({ reducedMotion: true, choice: "play", inView: true })).toBe(true);
    expect(shouldPlay({ reducedMotion: true, choice: "play", inView: false })).toBe(false);
  });
});

describe("scroll reveals", () => {
  it("are off for reduced motion or without IntersectionObserver", () => {
    expect(revealMode({ reducedMotion: false, hasObserver: true })).toBe("animate");
    expect(revealMode({ reducedMotion: true, hasObserver: true })).toBe("static");
    expect(revealMode({ reducedMotion: false, hasObserver: false })).toBe("static");
  });
});

describe("stage tabs keyboard (WAI-ARIA tabs)", () => {
  it("arrows wrap, Home/End jump, other keys are ignored", () => {
    expect(nextTabIndex("ArrowRight", 0, 6)).toBe(1);
    expect(nextTabIndex("ArrowDown", 5, 6)).toBe(0);
    expect(nextTabIndex("ArrowLeft", 0, 6)).toBe(5);
    expect(nextTabIndex("ArrowUp", 3, 6)).toBe(2);
    expect(nextTabIndex("Home", 4, 6)).toBe(0);
    expect(nextTabIndex("End", 1, 6)).toBe(5);
    expect(nextTabIndex("Enter", 1, 6)).toBeNull();
  });
});
