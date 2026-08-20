import type { Theme } from "./types";
import { DEFAULT_THEME } from "./types";

/** The 5 presets from project knowledge section H — theme JSON objects,
 *  not stylesheets. All five pass WCAG AA out of the box (verified in
 *  tests/contrast.test.ts). */
export const PRESETS: Record<string, Theme> = {
  light: { ...DEFAULT_THEME, preset: "light" },
  dark: {
    ...DEFAULT_THEME,
    preset: "dark",
    background_color: "#0b0f17",
    primary_color: "#60a5fa",
    accent_color: "#34d399",
  },
  "enterprise-blue": {
    ...DEFAULT_THEME,
    preset: "enterprise-blue",
    background_color: "#eef4fb",
    primary_color: "#1e40af",
    accent_color: "#0e7490",
    radius_px: 6,
  },
  midnight: {
    ...DEFAULT_THEME,
    preset: "midnight",
    background_color: "#080312",
    primary_color: "#a78bfa",
    accent_color: "#f472b6",
    radius_px: 12,
  },
  sand: {
    ...DEFAULT_THEME,
    preset: "sand",
    background_color: "#f6f1e7",
    primary_color: "#92400e",
    accent_color: "#0f766e",
    font_family: "Lora",
  },
};

export const PRESET_LABELS: Record<string, string> = {
  light: "Light",
  dark: "Dark",
  "enterprise-blue": "Enterprise Blue",
  midnight: "Midnight",
  sand: "Sand",
};
