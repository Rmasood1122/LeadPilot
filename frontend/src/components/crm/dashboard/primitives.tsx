"use client";

/** Shared dashboard primitives: stat tiles, sparklines, section headers,
 *  and the theme bridge every chart on these four pages reads colour from.
 *
 * COLOUR RULE: nothing in this directory contains a hex value. The theme
 * engine (src/lib/theme/) writes --primary/--accent/--muted-foreground etc.
 * as CSS variables and five presets plus a custom mode change them live; a
 * hardcoded #1d4ed8 would be the one element on the page that ignores the
 * user's choice. Recharts needs real colour strings rather than CSS
 * variables, so `chartColor()` resolves them at render time — the same
 * approach the existing analytics page already uses.
 */

import { useEffect, useState } from "react";
import { cn } from "@/lib/utils";
import { Card, CardContent } from "@/components/ui/card";

/** Resolve a theme CSS variable to an rgb() string Recharts can use.
 *
 *  Returns a neutral during SSR/static export, where there is no computed
 *  style to read — the client re-resolves on mount, so the only cost is that
 *  the very first painted frame of a chart is grey. */
export function chartColor(name: string): string {
  if (typeof window === "undefined") return "rgb(148 163 184)";
  const value = getComputedStyle(document.documentElement)
    .getPropertyValue(name)
    .trim();
  return value ? `rgb(${value})` : "rgb(148 163 184)";
}

/** Re-resolve theme colours after mount and whenever the theme changes.
 *
 *  Charts capture their colours at render time, so switching preset would
 *  otherwise leave every chart on the page in the old palette until
 *  something else caused a re-render. */
export function useChartPalette() {
  const [palette, setPalette] = useState(() => ({
    primary: chartColor("--primary"),
    accent: chartColor("--accent"),
    muted: chartColor("--muted-foreground"),
    success: chartColor("--success"),
    warning: chartColor("--warning"),
    destructive: chartColor("--destructive"),
    border: chartColor("--border"),
  }));

  useEffect(() => {
    const read = () => ({
      primary: chartColor("--primary"),
      accent: chartColor("--accent"),
      muted: chartColor("--muted-foreground"),
      success: chartColor("--success"),
      warning: chartColor("--warning"),
      destructive: chartColor("--destructive"),
      border: chartColor("--border"),
    });
    setPalette(read());

    // The theme engine sets variables via element.style on <html>, so a
    // style-attribute mutation is the signal that the preset changed.
    const observer = new MutationObserver(() => setPalette(read()));
    observer.observe(document.documentElement, {
      attributes: true,
      attributeFilter: ["style"],
    });
    return () => observer.disconnect();
  }, []);

  return palette;
}

export function SectionHeading({
  title,
  hint,
  right,
}: {
  title: string;
  hint?: string;
  right?: React.ReactNode;
}) {
  return (
    <div className="flex items-end justify-between gap-4">
      <div>
        <h2 className="text-sm font-semibold">{title}</h2>
        {hint && <p className="text-xs text-muted-foreground">{hint}</p>}
      </div>
      {right}
    </div>
  );
}

export function StatTile({
  label,
  value,
  sub,
  tone = "default",
  title,
}: {
  label: string;
  value: string | number;
  sub?: string;
  tone?: "default" | "positive" | "warning" | "danger";
  title?: string;
}) {
  const toneClass = {
    default: "text-foreground",
    positive: "text-[rgb(var(--success))]",
    warning: "text-[rgb(var(--warning))]",
    danger: "text-[rgb(var(--destructive))]",
  }[tone];

  return (
    <Card>
      <CardContent className="p-gutter">
        <p className="text-xs font-medium uppercase tracking-wide text-muted-foreground">
          {label}
        </p>
        <p
          className={cn("mt-1 text-2xl font-semibold tabular-nums", toneClass)}
          title={title}
        >
          {value}
        </p>
        {sub && <p className="mt-0.5 text-xs text-muted-foreground">{sub}</p>}
      </CardContent>
    </Card>
  );
}

/** A tiny inline trend line, drawn as SVG rather than pulled from Recharts.
 *
 *  A sparkline has no axes, no tooltip, no legend and no responsiveness
 *  requirement beyond its container width — a full chart component for it is
 *  an eight-element polyline wrapped in three hundred lines of layout code. */
export function Sparkline({
  points,
  height = 32,
  label,
}: {
  points: number[];
  height?: number;
  label: string;
}) {
  const palette = useChartPalette();
  if (points.length === 0) {
    return (
      <div
        className="flex items-center text-xs text-muted-foreground"
        style={{ height }}
      >
        No data yet
      </div>
    );
  }

  const max = Math.max(...points, 1);
  const width = 100; // viewBox units; the SVG scales to its container
  const step = points.length > 1 ? width / (points.length - 1) : width;
  const path = points
    .map((value, index) => {
      const x = index * step;
      const y = height - (value / max) * height;
      return `${index === 0 ? "M" : "L"}${x.toFixed(2)},${y.toFixed(2)}`;
    })
    .join(" ");

  return (
    <svg
      viewBox={`0 0 ${width} ${height}`}
      preserveAspectRatio="none"
      className="w-full"
      style={{ height }}
      role="img"
      aria-label={label}
    >
      <path
        d={path}
        fill="none"
        stroke={palette.primary}
        strokeWidth={1.5}
        vectorEffect="non-scaling-stroke"
      />
    </svg>
  );
}

/** Formats a 0..1 rate as a percentage — or an em dash when it is null.
 *
 *  null and 0 mean different things and must never render the same: null is
 *  "nothing has been sent yet", 0 is "everything was sent and none of it
 *  worked". Showing 0% for the first is a lie the reader has no way to
 *  detect. */
export function formatRate(rate: number | null | undefined, digits = 1): string {
  if (rate === null || rate === undefined) return "—";
  return `${(rate * 100).toFixed(digits)}%`;
}

export function formatCount(value: number | null | undefined): string {
  if (value === null || value === undefined) return "—";
  return value.toLocaleString();
}

/** Human label for a LeadStatus. */
export function stageLabel(stage: string): string {
  return stage.replace(/_/g, " ").replace(/\b\w/g, (c) => c.toUpperCase());
}
