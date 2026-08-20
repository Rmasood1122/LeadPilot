import type { Theme } from "./types";
import { hexToRgb, readableTextOn, relativeLuminance } from "./contrast";

/** Turn a Theme into the CSS variables every component consumes.
 *  Pure + exported so tests can assert the exact variable output. */
export function themeToCssVars(theme: Theme): Record<string, string> {
  const rgb = (hex: string) => hexToRgb(hex).join(" ");
  const dark = relativeLuminance(theme.background_color) < 0.35;
  const card = dark ? lighten(theme.background_color, 0.08) : "#ffffff";
  return {
    "--background": rgb(theme.background_color),
    "--foreground": rgb(readableTextOn(theme.background_color)),
    "--card": rgb(card),
    "--card-foreground": rgb(readableTextOn(card)),
    "--primary": rgb(theme.primary_color),
    "--primary-foreground": rgb(readableTextOn(theme.primary_color)),
    "--accent": rgb(theme.accent_color),
    "--accent-foreground": rgb(readableTextOn(theme.accent_color)),
    "--muted": rgb(dark ? lighten(theme.background_color, 0.14) : "#e2e8f0"),
    "--muted-foreground": rgb(dark ? "#94a3b8" : "#64748b"),
    "--border": rgb(dark ? lighten(theme.background_color, 0.2) : "#cbd5e1"),
    "--destructive": rgb("#dc2626"),
    "--success": rgb("#16a34a"),
    "--warning": rgb("#d97706"),
    "--radius": `${theme.radius_px}px`,
    "--font-family": `"${theme.font_family}"`,
    "--density-gutter": theme.density === "compact" ? "0.5rem" : "1rem",
    "--bg-image": theme.background_image_url
      ? `url("${theme.background_image_url}")`
      : "none",
    "--bg-overlay": String(theme.background_overlay),
  };
}

function lighten(hex: string, amount: number): string {
  const [r, g, b] = hexToRgb(hex);
  const up = (c: number) => Math.min(255, Math.round(c + (255 - c) * amount));
  return `#${[up(r), up(g), up(b)]
    .map((c) => c.toString(16).padStart(2, "0"))
    .join("")}`;
}

export function applyTheme(theme: Theme, el?: HTMLElement) {
  const target = el ?? document.documentElement;
  const vars = themeToCssVars(theme);
  for (const [k, v] of Object.entries(vars)) target.style.setProperty(k, v);
  target.style.fontSize = `calc(16px * ${theme.font_size_scale})`;
  loadGoogleFont(theme.font_family);
}

export function loadGoogleFont(family: string) {
  if (typeof document === "undefined") return;
  const id = `gf-${family.replace(/\s+/g, "-")}`;
  if (document.getElementById(id)) return;
  const link = document.createElement("link");
  link.id = id;
  link.rel = "stylesheet";
  link.href = `https://fonts.googleapis.com/css2?family=${encodeURIComponent(
    family,
  )}:wght@400;500;600;700&display=swap`;
  document.head.appendChild(link);
}

/** Inline <script> for the FIRST paint: reads the cached theme from
 *  localStorage and sets variables before hydration — no flash. */
export const NO_FLASH_SCRIPT = `
(function(){try{
var raw=localStorage.getItem("leadpilot.theme");if(!raw)return;
var t=JSON.parse(raw);
function rgb(h){h=h.replace("#","");var n=parseInt(h,16);return ((n>>16)&255)+" "+((n>>8)&255)+" "+(n&255);}
var s=document.documentElement.style;
s.setProperty("--background",rgb(t.background_color||"#f8fafc"));
s.setProperty("--primary",rgb(t.primary_color||"#1d4ed8"));
s.setProperty("--accent",rgb(t.accent_color||"#0891b2"));
s.setProperty("--radius",(t.radius_px||8)+"px");
s.setProperty("--font-family",'"'+(t.font_family||"Inter")+'"');
document.documentElement.style.fontSize="calc(16px * "+(t.font_size_scale||1)+")";
}catch(e){}})();`;
