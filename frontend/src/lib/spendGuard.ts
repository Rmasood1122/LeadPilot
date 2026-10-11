/** F07 — pure helpers for Spend Guard (usage page, monthly cap, forecasts).
 *  No React, no fetching; tested in tests/spendGuard.test.ts. Types are
 *  structural so this file does not import the API module (which imports it). */

export const DISABLED_STATUS = 409;
export const THRESHOLDS = [50, 80, 100] as const;
export const MIN_CAP_USD = 1;
export const MAX_CAP_USD = 1_000_000;

/** True when the API said the feature is switched off (not an error to show). */
export function isDisabledError(error: unknown): boolean {
  return typeof error === "object" && error !== null
    && (error as { status?: number }).status === DISABLED_STATUS;
}

export function formatUsd(value: number | null | undefined, digits = 2): string {
  if (value === null || value === undefined || Number.isNaN(value)) return "—";
  return new Intl.NumberFormat("en-US", {
    style: "currency", currency: "USD", minimumFractionDigits: digits, maximumFractionDigits: digits,
  }).format(value);
}

/** Share of the cap used, 0..∞ (can exceed 100 when spend lands past the cap
 *  outside a guarded run, e.g. sends). null when there is no cap. */
export function percentUsed(spentUsd: number, capUsd: number | null | undefined): number | null {
  if (!capUsd || capUsd <= 0) return null;
  return Math.round((spentUsd / capUsd) * 1000) / 10;
}

/** Highest threshold reached (50/80/100), or null below 50% / without a cap. */
export function thresholdReached(percent: number | null): 50 | 80 | 100 | null {
  if (percent === null) return null;
  for (const t of [...THRESHOLDS].reverse()) if (percent >= t) return t;
  return null;
}

export type Tone = "default" | "warning" | "danger";

export function capTone(percent: number | null): Tone {
  const t = thresholdReached(percent);
  if (t === 100) return "danger";
  if (t === 80 || t === 50) return "warning";
  return "default";
}

/** The progress bar's width: clamped to 0..100. */
export function barWidth(percent: number | null): number {
  if (percent === null) return 0;
  return Math.max(0, Math.min(100, percent));
}

export function alertBanner(threshold: number | null): string | null {
  if (threshold === null) return null;
  if (threshold >= 100) {
    return "Your monthly spend cap is reached. New strategy, lead-sourcing and Quickstart runs are "
      + "refused and running ones stop before their next paid call. Scheduled sends continue.";
  }
  return `${threshold}% of your monthly spend cap is used.`;
}

export type CapInput = { ok: true; value: number | null } | { ok: false; error: string };

/** The cap form's text → the API value. Empty = no cap. */
export function parseCapInput(text: string): CapInput {
  const raw = text.trim().replace(/^\$/, "").replace(/,/g, "");
  if (raw === "") return { ok: true, value: null };
  const value = Number(raw);
  if (!Number.isFinite(value)) return { ok: false, error: "Enter an amount in US dollars." };
  if (value < MIN_CAP_USD || value > MAX_CAP_USD) {
    return { ok: false, error: `The cap must be between $${MIN_CAP_USD} and $${MAX_CAP_USD.toLocaleString("en-US")}.` };
  }
  return { ok: true, value: Math.round(value * 100) / 100 };
}

/** "+12.5% over" / "-8.0% under" / "—" for a reconciliation error ratio. */
export function errorLabel(errorPct: number | null | undefined): string {
  if (errorPct === null || errorPct === undefined) return "—";
  const pct = Math.round(errorPct * 1000) / 10;
  if (pct === 0) return "exact";
  return `${pct > 0 ? "+" : ""}${pct.toFixed(1)}% ${pct > 0 ? "over" : "under"}`;
}

interface ReconLike {
  reconcilable: boolean;
  complete?: boolean;
  error_pct?: number | null;
  within_tolerance?: boolean | null;
}

/** One forecast row's verdict on the ±25% metric. */
export function accuracyVerdict(rec: ReconLike): { text: string; tone: Tone } {
  if (!rec.reconcilable) return { text: "Refused — never ran", tone: "default" };
  if (!rec.complete) return { text: "Running — not measured yet", tone: "default" };
  if (rec.error_pct === null || rec.error_pct === undefined) {
    return { text: "No recorded spend", tone: "default" };
  }
  return rec.within_tolerance
    ? { text: `Within ±25% (${errorLabel(rec.error_pct)})`, tone: "default" }
    : { text: `Outside ±25% (${errorLabel(rec.error_pct)})`, tone: "warning" };
}

export function accuracySummary(acc: { measured_runs: number; within_tolerance: number }): string {
  if (acc.measured_runs === 0) return "No finished runs measured yet.";
  return `${acc.within_tolerance} of ${acc.measured_runs} finished runs forecast within ±25%.`;
}

/** "1,200 Apollo · 300 Hunter" for {provider: credits}. */
export function creditsLabel(credits: Record<string, number> | null | undefined): string {
  const parts = Object.entries(credits ?? {})
    .filter(([, n]) => n > 0)
    .map(([p, n]) => `${n.toLocaleString("en-US")} ${p.charAt(0).toUpperCase()}${p.slice(1)}`);
  return parts.length ? parts.join(" · ") : "none";
}
