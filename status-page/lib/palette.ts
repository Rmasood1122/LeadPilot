/**
 * Colour tokens for light and dark mode, emitted as CSS variables by the root
 * layout. Kept in TypeScript so tests/palette.test.ts can prove WCAG AA
 * contrast for every text pairing the page uses (4.5:1 for text, 3:1 for the
 * status icons and bars). Status is never conveyed by colour alone: every
 * status has a text label and a distinct icon shape (components/StatusIcon.tsx).
 */

import type { DisplayStatus } from "./status.ts";

export interface Palette {
  bg: string;
  surface: string;
  text: string;
  muted: string;
  border: string;
  link: string;
  focus: string;
  nodata: string;
  status: Record<DisplayStatus, string>;
}

export const LIGHT: Palette = {
  bg: "#f6f7f9",
  surface: "#ffffff",
  text: "#16191d",
  muted: "#4b5360",
  border: "#cfd5dc",
  link: "#1452a8",
  focus: "#1452a8",
  nodata: "#8a929c",
  status: {
    operational: "#17703a",
    degraded: "#835400",
    partial_outage: "#a8400e",
    major_outage: "#b3261e",
    maintenance: "#1452a8",
    unknown: "#555d69",
  },
};

export const DARK: Palette = {
  bg: "#0e1116",
  surface: "#161b22",
  text: "#e6e9ed",
  muted: "#a3acb8",
  border: "#2f3742",
  link: "#7cb6ff",
  focus: "#7cb6ff",
  nodata: "#6b7480",
  status: {
    operational: "#4cc472",
    degraded: "#e0b13f",
    partial_outage: "#f2914a",
    major_outage: "#ff8078",
    maintenance: "#7cb6ff",
    unknown: "#a3acb8",
  },
};

function channel(c: number): number {
  const s = c / 255;
  return s <= 0.03928 ? s / 12.92 : ((s + 0.055) / 1.055) ** 2.4;
}

export function luminance(hex: string): number {
  const m = /^#([0-9a-f]{6})$/i.exec(hex);
  if (!m) throw new Error(`not a #rrggbb colour: ${hex}`);
  const n = parseInt(m[1]!, 16);
  return 0.2126 * channel((n >> 16) & 255) + 0.7152 * channel((n >> 8) & 255) + 0.0722 * channel(n & 255);
}

export function contrast(a: string, b: string): number {
  const [hi, lo] = [luminance(a), luminance(b)].sort((x, y) => y - x) as [number, number];
  return (hi + 0.05) / (lo + 0.05);
}

function vars(p: Palette): string {
  const entries: [string, string][] = [
    ["bg", p.bg],
    ["surface", p.surface],
    ["text", p.text],
    ["muted", p.muted],
    ["border", p.border],
    ["link", p.link],
    ["focus", p.focus],
    ["nodata", p.nodata],
    ...(Object.entries(p.status) as [string, string][]).map(([k, v]) => [`s-${k}`, v] as [string, string]),
  ];
  return entries.map(([k, v]) => `--${k}:${v};`).join("");
}

export function paletteCss(): string {
  return (
    `:root{color-scheme:light dark;${vars(LIGHT)}}` +
    `@media (prefers-color-scheme: dark){:root{${vars(DARK)}}}`
  );
}
