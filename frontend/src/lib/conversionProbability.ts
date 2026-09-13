/** Feature A5 — live conversion probability, shaped for the lead page.
 *  Pure; tested in src/tests/conversionProbability.test.ts. */

export interface ConversionFactor {
  factor: string;
  value?: number;
  multiplier?: number;
  count?: number;
  idle_days?: number;
  effect?: string;
}

export interface ConversionEstimate {
  probability: number;
  band: "won" | "hot" | "warm" | "cold" | "cooling";
  kill_signal: string | null;
  unanswered_sends: number;
  factors: ConversionFactor[];
}

export interface ConversionResponse {
  live: ConversionEstimate;
  stored: {
    conversion_probability: number | null;
    engagement_state: "active" | "cooling" | "archived" | "won";
    kill_signal: string | null;
    conversion_probability_at: string | null;
    factors: ConversionFactor[];
  };
}

export function probabilityPercent(p: number | null | undefined): string {
  if (p === null || p === undefined || Number.isNaN(p)) return "—";
  const pct = p * 100;
  return pct < 1 && pct > 0 ? "<1%" : `${Math.round(pct)}%`;
}

export function stateTone(state: string): "success" | "warning" | "destructive" | "primary" | "default" {
  if (state === "won") return "success";
  if (state === "cooling") return "warning";
  if (state === "archived") return "destructive";
  return "primary";
}

const KILL_TEXT: Record<string, string> = {
  bounced: "the email bounced",
  unsubscribed: "they asked to stop",
  not_interested: "they said they're not interested",
  probability_below_archive: "no engagement across many touches",
};

export function killSignalText(signal: string | null | undefined): string {
  if (!signal) return "";
  return KILL_TEXT[signal] ?? signal.replace(/_/g, " ");
}

/** One factor as a short human line, or null for factors not worth showing. */
export function describeFactor(f: ConversionFactor): string | null {
  const x = (m?: number) => (m === undefined ? "" : ` (×${m.toFixed(2)})`);
  if (f.factor === "ai_booking_likelihood") return `Starting point: AI score ${probabilityPercent(f.value)}`;
  if (f.factor === "default_prior") return `Starting point: ${probabilityPercent(f.value)} (no AI score)`;
  if (f.factor.startsWith("unanswered_")) {
    const channel = f.factor.slice("unanswered_".length);
    return `${f.count} unanswered ${channel} ${f.count === 1 ? "touch" : "touches"}${x(f.multiplier)}`;
  }
  if (f.factor.startsWith("reply_")) return `Replied: ${f.factor.slice(6).replace(/_/g, " ")}${x(f.multiplier)}`;
  if (f.factor === "opened") return `Opened recently${x(f.multiplier)}`;
  if (f.factor === "clicked") return `Clicked a link${x(f.multiplier)}`;
  if (f.factor === "inactivity") return `Quiet for ${Math.round(f.idle_days ?? 0)} days${x(f.multiplier)}`;
  if (f.effect === "kill") return killSignalText(f.factor) || f.factor;
  if (f.factor === "meeting_booked") return "Meeting booked";
  return null;
}
