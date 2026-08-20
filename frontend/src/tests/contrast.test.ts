/**
 * Theme engine tests (Chunk 7) — pure functions only; no DOM or network.
 *
 * Contrast math: verified against known WCAG reference pairs.
 * Preset coverage: all five presets must pass WCAG AA for their core
 *   text-on-background combination out of the box.
 * themeToCssVars: asserts the exact variable names and value format the
 *   Tailwind config and CSS `var()` calls depend on.
 */

import { describe, it, expect } from "vitest";
import {
  contrastRatio,
  passesAA,
  relativeLuminance,
  readableTextOn,
  suggestPassingColor,
  themeContrastWarnings,
  AA_NORMAL,
} from "@/lib/theme/contrast";
import { themeToCssVars } from "@/lib/theme/apply";
import { PRESETS } from "@/lib/theme/presets";
import { DEFAULT_THEME } from "@/lib/theme/types";

// -------------------------------------------------------  Contrast math

describe("relativeLuminance", () => {
  it("white is 1.0", () => expect(relativeLuminance("#ffffff")).toBeCloseTo(1));
  it("black is 0.0", () => expect(relativeLuminance("#000000")).toBeCloseTo(0));
  it("#0d0d0d is near-black", () =>
    expect(relativeLuminance("#0d0d0d")).toBeLessThan(0.01));
});

describe("contrastRatio — known WCAG pairs", () => {
  it("white on black = 21:1", () =>
    expect(contrastRatio("#ffffff", "#000000")).toBeCloseTo(21, 0));

  it("white on white = 1:1", () =>
    expect(contrastRatio("#ffffff", "#ffffff")).toBeCloseTo(1, 0));

  /** W3C reference: #595959 on #fff ≈ 7:1 (passes AA large AND normal). */
  it("#595959 on white > 7:1", () =>
    expect(contrastRatio("#595959", "#ffffff")).toBeGreaterThan(7));

  /** W3C reference: #777777 on #fff ≈ 4.48:1 (just under AA normal). */
  it("#777777 on white is just under 4.5:1", () => {
    const ratio = contrastRatio("#777777", "#ffffff");
    expect(ratio).toBeGreaterThan(4.0);
    expect(ratio).toBeLessThan(4.5);
  });

  it("is commutative", () =>
    expect(contrastRatio("#1d4ed8", "#ffffff")).toBeCloseTo(
      contrastRatio("#ffffff", "#1d4ed8"),
      5,
    ));
});

describe("passesAA", () => {
  it("white on black passes", () => expect(passesAA("#ffffff", "#000000")).toBe(true));
  it("white on white fails", () => expect(passesAA("#ffffff", "#ffffff")).toBe(false));
  it("#777777 on white fails AA normal", () =>
    expect(passesAA("#777777", "#ffffff")).toBe(false));
});

describe("readableTextOn", () => {
  it("dark backgrounds get white text", () =>
    expect(readableTextOn("#000000")).toBe("#ffffff"));
  it("light backgrounds get dark text", () =>
    expect(readableTextOn("#ffffff")).toBe("#111827"));
});

describe("suggestPassingColor", () => {
  it("already passing color returned unchanged", () => {
    expect(suggestPassingColor("#000000", "#ffffff")).toBe("#000000");
  });
  it("produces a color that passes AA", () => {
    const suggestion = suggestPassingColor("#aaaaaa", "#ffffff");
    expect(passesAA(suggestion, "#ffffff")).toBe(true);
  });
  it("keeps working toward extreme colors when needed", () => {
    const suggestion = suggestPassingColor("#cccccc", "#ffffff");
    expect(passesAA(suggestion, "#ffffff")).toBe(true);
  });
});

// -----------------------------------------------  All 5 presets pass AA

describe("Preset AA compliance", () => {
  Object.entries(PRESETS).forEach(([name, preset]) => {
    it(`${name}: text on background passes AA`, () => {
      const text = readableTextOn(preset.background_color);
      const ratio = contrastRatio(text, preset.background_color);
      expect(ratio).toBeGreaterThanOrEqual(AA_NORMAL);
    });

    it(`${name}: primary text on primary bg passes AA`, () => {
      const text = readableTextOn(preset.primary_color);
      const ratio = contrastRatio(text, preset.primary_color);
      expect(ratio).toBeGreaterThanOrEqual(AA_NORMAL);
    });

    it(`${name}: accent text on accent bg passes AA`, () => {
      const text = readableTextOn(preset.accent_color);
      const ratio = contrastRatio(text, preset.accent_color);
      expect(ratio).toBeGreaterThanOrEqual(AA_NORMAL);
    });
  });
});

describe("themeContrastWarnings", () => {
  it("no warnings for Light preset", () =>
    expect(themeContrastWarnings(PRESETS["light"])).toHaveLength(0));
  it("no warnings for Dark preset", () =>
    expect(themeContrastWarnings(PRESETS["dark"])).toHaveLength(0));
  it("emits a warning for a bad combo", () => {
    const warnings = themeContrastWarnings({
      background_color: "#ffffff",
      primary_color: "#eeeeee", // near-white on white
      accent_color: "#0891b2",
    });
    expect(warnings.length).toBeGreaterThan(0);
    expect(warnings.some((w) => w.includes("fails WCAG AA"))).toBe(true);
  });
});

// -------------------------------------------------  themeToCssVars output

describe("themeToCssVars", () => {
  const vars = themeToCssVars(DEFAULT_THEME);

  it("emits --background as space-separated rgb triplet", () => {
    expect(vars["--background"]).toMatch(/^\d+ \d+ \d+$/);
  });

  it("emits --radius with px unit", () => {
    expect(vars["--radius"]).toBe(`${DEFAULT_THEME.radius_px}px`);
  });

  it("emits --font-family as quoted string", () => {
    expect(vars["--font-family"]).toBe(`"${DEFAULT_THEME.font_family}"`);
  });

  it("comfortable density sets --density-gutter to 1rem", () => {
    expect(vars["--density-gutter"]).toBe("1rem");
  });

  it("compact density sets --density-gutter to 0.5rem", () => {
    const compact = themeToCssVars({ ...DEFAULT_THEME, density: "compact" });
    expect(compact["--density-gutter"]).toBe("0.5rem");
  });

  it("all required variable names are present", () => {
    const required = [
      "--background", "--foreground", "--card", "--card-foreground",
      "--primary", "--primary-foreground", "--accent", "--accent-foreground",
      "--muted", "--muted-foreground", "--border",
      "--destructive", "--success", "--warning",
      "--radius", "--font-family", "--density-gutter",
      "--bg-image", "--bg-overlay",
    ];
    for (const name of required) {
      expect(vars).toHaveProperty(name);
    }
  });

  it("no background image when url is null", () => {
    expect(vars["--bg-image"]).toBe("none");
  });

  it("background image url is wrapped in url()", () => {
    const withBg = themeToCssVars({
      ...DEFAULT_THEME,
      background_image_url: "https://example.com/bg.jpg",
    });
    expect(withBg["--bg-image"]).toBe(`url("https://example.com/bg.jpg")`);
  });
});
