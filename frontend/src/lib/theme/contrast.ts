/** WCAG 2.1 contrast math (section H: warn on AA failures).
 *  Ratio = (L1 + 0.05) / (L2 + 0.05); AA normal text needs >= 4.5:1. */

export function hexToRgb(hex: string): [number, number, number] {
  const h = hex.replace("#", "");
  const full = h.length === 3 ? h.split("").map((c) => c + c).join("") : h;
  const n = parseInt(full, 16);
  return [(n >> 16) & 255, (n >> 8) & 255, n & 255];
}

function channel(c: number): number {
  const s = c / 255;
  return s <= 0.03928 ? s / 12.92 : Math.pow((s + 0.055) / 1.055, 2.4);
}

export function relativeLuminance(hex: string): number {
  const [r, g, b] = hexToRgb(hex);
  return 0.2126 * channel(r) + 0.7152 * channel(g) + 0.0722 * channel(b);
}

export function contrastRatio(a: string, b: string): number {
  const la = relativeLuminance(a);
  const lb = relativeLuminance(b);
  const hi = Math.max(la, lb);
  const lo = Math.min(la, lb);
  return (hi + 0.05) / (lo + 0.05);
}

export const AA_NORMAL = 4.5;

export function passesAA(a: string, b: string): boolean {
  return contrastRatio(a, b) >= AA_NORMAL;
}

/** Best-readable text color (white or near-black) for a solid background. */
export function readableTextOn(bg: string): string {
  return contrastRatio(bg, "#ffffff") >= contrastRatio(bg, "#111827")
    ? "#ffffff"
    : "#111827";
}

/** Nearest passing color: walk lightness toward white or black (whichever
 *  direction can pass) until AA passes — keeps the user's hue. */
export function suggestPassingColor(color: string, against: string): string {
  if (passesAA(color, against)) return color;
  const towardWhite = relativeLuminance(against) < 0.5;
  let [r, g, b] = hexToRgb(color);
  for (let i = 0; i < 40; i++) {
    if (towardWhite) {
      r = Math.min(255, Math.round(r + (255 - r) * 0.12));
      g = Math.min(255, Math.round(g + (255 - g) * 0.12));
      b = Math.min(255, Math.round(b + (255 - b) * 0.12));
    } else {
      r = Math.round(r * 0.88);
      g = Math.round(g * 0.88);
      b = Math.round(b * 0.88);
    }
    const hex = `#${[r, g, b]
      .map((c) => c.toString(16).padStart(2, "0"))
      .join("")}`;
    if (passesAA(hex, against)) return hex;
  }
  return towardWhite ? "#ffffff" : "#000000";
}

/** All warnings for a theme — shown inline AND persisted with the theme
 *  (contrast_warnings) so the user was demonstrably informed. */
export function themeContrastWarnings(theme: {
  background_color: string;
  primary_color: string;
  accent_color: string;
}): string[] {
  const warnings: string[] = [];
  const check = (label: string, fg: string, bg: string) => {
    const ratio = contrastRatio(fg, bg);
    if (ratio < AA_NORMAL) {
      warnings.push(
        `${label} fails WCAG AA — ${ratio.toFixed(1)}:1, needs ${AA_NORMAL}:1`,
      );
    }
  };
  check("Text on background", readableTextOn(theme.background_color), theme.background_color);
  check("Text on primary", readableTextOn(theme.primary_color), theme.primary_color);
  check("Text on accent", readableTextOn(theme.accent_color), theme.accent_color);
  check("Primary on background", theme.primary_color, theme.background_color);
  return warnings;
}
