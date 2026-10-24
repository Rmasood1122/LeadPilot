/**
 * The home page video (src/components/home/HomeVideo.tsx, files made by
 * frontend/video-src/render.mjs): accessible controls and captions, reduced
 * motion respected, and the shipped files real, small and matching the
 * transcript on the page.
 */
import { readFileSync, statSync } from "node:fs";
import React from "react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { act, fireEvent, render, screen } from "@testing-library/react";

import { HomeVideo } from "@/components/home/HomeVideo";
import { VIDEO } from "@/components/home/content";

let playSpy: ReturnType<typeof vi.fn<(this: HTMLMediaElement) => Promise<void>>>;

function stubMotion(reduce: boolean) {
  vi.stubGlobal("matchMedia", (q: string) => ({
    matches: reduce && q === "(prefers-reduced-motion: reduce)",
    addEventListener() {},
    removeEventListener() {},
  }));
}

beforeEach(() => {
  playSpy = vi.fn<(this: HTMLMediaElement) => Promise<void>>(function (this: HTMLMediaElement) {
    Object.defineProperty(this, "paused", { value: false, configurable: true });
    this.dispatchEvent(new Event("play"));
    return Promise.resolve();
  });
  vi.spyOn(HTMLMediaElement.prototype, "play").mockImplementation(playSpy);
  vi.spyOn(HTMLMediaElement.prototype, "pause").mockImplementation(function (this: HTMLMediaElement) {
    Object.defineProperty(this, "paused", { value: true, configurable: true });
    this.dispatchEvent(new Event("pause"));
  });
});

afterEach(() => {
  vi.restoreAllMocks();
  vi.unstubAllGlobals();
});

describe("HomeVideo element", () => {
  it("is muted, looping, inline, poster-first and labelled", () => {
    stubMotion(false);
    render(<HomeVideo />);
    const v = screen.getByTestId("home-video") as HTMLVideoElement;
    expect(v.muted).toBe(true);
    expect(v.loop).toBe(true);
    expect(v.hasAttribute("playsinline")).toBe(true);
    expect(v.getAttribute("preload")).toBe("metadata");
    expect(v.getAttribute("poster")).toBe(VIDEO.poster);
    expect(v.getAttribute("aria-label")).toBe(VIDEO.label);
    const desc = document.getElementById(v.getAttribute("aria-describedby")!);
    expect(desc?.textContent).toBe(VIDEO.description);
    const types = Array.from(v.querySelectorAll("source")).map((s) => s.getAttribute("type"));
    expect(types).toEqual(["video/mp4", "video/webm"]);
  });

  it("has an English captions track on by default and a transcript on the page", () => {
    stubMotion(false);
    render(<HomeVideo />);
    const track = document.querySelector("track")!;
    expect(track.getAttribute("kind")).toBe("captions");
    expect(track.getAttribute("srclang")).toBe("en");
    expect(track.hasAttribute("default")).toBe(true);
    expect(track.getAttribute("src")).toBe(VIDEO.captions);
    const items = screen.getByTestId("home-video-transcript").querySelectorAll("li");
    expect(Array.from(items).map((li) => li.textContent)).toEqual(VIDEO.transcript);
    expect(screen.getByTestId("home-video-captions").getAttribute("aria-pressed")).toBe("true");
  });

  it("replaces the native controls with a visible Pause/Play button once hydrated", () => {
    stubMotion(false);
    render(<HomeVideo />);
    const v = screen.getByTestId("home-video") as HTMLVideoElement;
    expect(v.controls).toBe(false);
    expect(playSpy).toHaveBeenCalledTimes(1);
    const btn = screen.getByTestId("home-video-toggle");
    expect(btn.getAttribute("aria-label")).toBe("Pause video");
    act(() => {
      fireEvent.click(btn);
    });
    expect(v.paused).toBe(true);
    expect(screen.getByTestId("home-video-toggle").getAttribute("aria-label")).toBe("Play video");
  });

  it("never starts by itself for prefers-reduced-motion, but plays when asked", () => {
    stubMotion(true);
    render(<HomeVideo />);
    expect(playSpy).not.toHaveBeenCalled();
    act(() => {
      fireEvent.click(screen.getByTestId("home-video-toggle"));
    });
    expect(playSpy).toHaveBeenCalledTimes(1);
  });

  it("server HTML has no autoplay attribute (so reduced motion is honoured before hydration)", () => {
    const src = readFileSync("src/components/home/HomeVideo.tsx", "utf8");
    expect(src).not.toMatch(/\bautoPlay\b/);
  });
});

describe("the shipped video files", () => {
  const pub = (p: string) => `public${p}`;
  const MAX = 3 * 1024 * 1024;

  it("MP4 (H.264 container) and WebM exist, are real media and at most 3 MB each", () => {
    const mp4 = readFileSync(pub(VIDEO.mp4));
    expect(mp4.subarray(4, 8).toString("latin1")).toBe("ftyp");
    const webm = readFileSync(pub(VIDEO.webm));
    expect(webm.subarray(0, 4).toString("hex")).toBe("1a45dfa3"); // EBML
    for (const f of [VIDEO.mp4, VIDEO.webm, VIDEO.poster]) {
      expect(statSync(pub(f)).size).toBeGreaterThan(10_000);
      expect(statSync(pub(f)).size).toBeLessThanOrEqual(MAX);
    }
  });

  it("the captions file is WebVTT and its cues are the transcript, in order", () => {
    const vtt = readFileSync(pub(VIDEO.captions), "utf8");
    expect(vtt.startsWith("WEBVTT")).toBe(true);
    const cues = vtt
      .split(/\r?\n\r?\n/)
      .filter((block) => block.includes("-->"))
      .map((block) => block.split(/\r?\n/).slice(block.split(/\r?\n/).findIndex((l) => l.includes("-->")) + 1).join(" ").trim());
    expect(cues).toEqual(VIDEO.transcript);
  });

  it("the description states the real length of the video", () => {
    const html = readFileSync("video-src/walkthrough.html", "utf8");
    const duration = Number(/window\.DURATION\s*=\s*([\d.]+)/.exec(html)![1]);
    expect(VIDEO.description).toContain(`${Math.round(duration)}-second`);
    const vtt = readFileSync(pub(VIDEO.captions), "utf8");
    const last = [...vtt.matchAll(/--> (\d\d):(\d\d):(\d\d\.\d+)/g)].pop()!;
    expect(Number(last[1]) * 3600 + Number(last[2]) * 60 + Number(last[3])).toBeCloseTo(duration, 1);
  });

  it("the video is clearly sample data", () => {
    const html = readFileSync("video-src/walkthrough.html", "utf8");
    expect(html).toContain("Product animation with sample data");
    expect(VIDEO.description).toMatch(/sample data/);
  });
});
