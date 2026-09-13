/** Feature A6 — the shareable ROI dashboard. Pure helpers; tested in
 *  src/tests/shareLinks.test.ts. */

export interface ShareLink {
  id: string;
  label: string;
  token_prefix: string;
  strategy_id: string | null;
  scope: "account" | "campaign";
  status: "active" | "expired" | "revoked";
  expires_at: string;
  revoked_at: string | null;
  last_viewed_at: string | null;
  view_count: number;
  created_at: string | null;
}

export interface PublicDashboard {
  title: string;
  brand: { name: string; logo_url: string | null; primary_color: string | null } | null;
  scope: { type: "account" | "campaign"; campaign_name: string | null; campaigns: number };
  period: { date_from: string; date_to: string; days: number };
  currency: string;
  totals: {
    meetings_booked: number;
    messages_sent: number;
    leads_contacted: number;
    reply_rate: number;
    pipeline_value: string;
    revenue_attributed: string;
    time_saved_hours: number;
  };
  pipeline: { key: string; label: string; count: number }[];
  trend: { date: string; meetings_booked: number; pipeline_value: string; revenue_attributed: string }[];
  generated_at: string;
  expires_at: string;
}

/** "4000.00" -> "$4,000"; keeps cents only when there are some. */
export function formatAmount(value: string | number, currency = "USD"): string {
  const amount = typeof value === "number" ? value : Number.parseFloat(value || "0");
  const whole = Number.isInteger(amount);
  try {
    return new Intl.NumberFormat("en-US", {
      style: "currency", currency, minimumFractionDigits: whole ? 0 : 2, maximumFractionDigits: 2,
    }).format(amount);
  } catch {
    return `${amount.toFixed(whole ? 0 : 2)} ${currency}`;
  }
}

/** "in 3 days" / "in 5 hours" / "expired". */
export function expiresInText(expiresAt: string, now: Date = new Date()): string {
  const ms = Date.parse(expiresAt) - now.getTime();
  if (Number.isNaN(ms) || ms <= 0) return "expired";
  const hours = Math.round(ms / 3_600_000);
  if (hours < 48) return `in ${Math.max(hours, 1)} hour${hours === 1 ? "" : "s"}`;
  const days = Math.round(hours / 24);
  return `in ${days} days`;
}

/** Daily points summed into Monday-start weeks, oldest first. */
export function weeklyMeetings(trend: PublicDashboard["trend"]): { week: string; meetings: number }[] {
  const weeks = new Map<string, number>();
  for (const point of trend) {
    const day = new Date(`${point.date}T00:00:00Z`);
    if (Number.isNaN(day.getTime())) continue;
    const offset = (day.getUTCDay() + 6) % 7; // Monday = 0
    day.setUTCDate(day.getUTCDate() - offset);
    const key = day.toISOString().slice(0, 10);
    weeks.set(key, (weeks.get(key) ?? 0) + point.meetings_booked);
  }
  return [...weeks.entries()].sort(([a], [b]) => a.localeCompare(b))
    .map(([week, meetings]) => ({ week, meetings }));
}

/** The widest stage count, for proportional bars (never 0, so no NaN widths). */
export function stageScale(pipeline: PublicDashboard["pipeline"]): number {
  return Math.max(1, ...pipeline.map((s) => s.count));
}

export function readToken(search: string): string | null {
  const token = new URLSearchParams(search).get("token");
  return token && token.length >= 16 ? token : null;
}
