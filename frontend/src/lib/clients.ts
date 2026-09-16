/** Part 1 Feature 11 — per-client agency workspaces, shaped for the UI.
 *  Pure; tested in src/tests/clients.test.ts. */

export type ClientStatus = "active" | "paused" | "archived";

export interface ClientWorkspace {
  id: string;
  name: string;
  slug: string;
  status: ClientStatus;
  contact_name: string | null;
  contact_email: string | null;
  billing_email: string | null;
  billing_reference: string | null;
  monthly_fee_cents: number;
  per_meeting_fee_cents: number;
  currency: string;
  notes: string | null;
  sending_domains: string[];
  strategy_count: number;
  archived_at: string | null;
  created_at: string | null;
}

export interface ClientReport {
  client_id: string;
  name: string;
  strategies: number;
  leads: number;
  sent: number;
  replies: number;
  meetings: number;
  won: number;
  /** null, never 0, when nothing has been sent. */
  reply_rate: number | null;
  meeting_rate: number | null;
  revenue_cents: number;
  currency: string;
}

export interface BillingLine {
  label: string;
  amount_cents: number;
}

export interface ClientBilling {
  client_id: string;
  name: string;
  currency: string;
  period_start: string;
  retainer_cents: number;
  per_meeting_fee_cents: number;
  meetings_this_period: number;
  variable_cents: number;
  total_cents: number;
  billing_email: string | null;
  billing_reference: string | null;
  lines: BillingLine[];
}

export interface ClientOverview {
  clients: (ClientWorkspace & ClientReport)[];
  unassigned_strategies: number;
  note: string;
}

/** 200000 -> "£2,000.00". Money is integer cents everywhere in this schema,
 *  so the only place it becomes a decimal is here. */
export function money(cents: number | null | undefined, currency = "USD"): string {
  const value = (cents ?? 0) / 100;
  try {
    return new Intl.NumberFormat(undefined, { style: "currency", currency })
      .format(value);
  } catch {
    // An unknown currency code must not blank the invoice.
    return `${value.toFixed(2)} ${currency}`;
  }
}

/** 0.145 -> "15%". "—" for a rate that does not exist yet, because 0% reads
 *  as failure in a report someone is about to forward to that client. */
export function rate(value: number | null | undefined): string {
  return value === null || value === undefined ? "—" : `${Math.round(value * 100)}%`;
}

export function statusTone(status: ClientStatus):
  "success" | "warning" | "default" {
  if (status === "active") return "success";
  if (status === "paused") return "warning";
  return "default";
}

/** The one line under a client's name on the overview. */
export function clientSubtitle(client: ClientWorkspace & Partial<ClientReport>): string {
  const parts = [
    `${client.strategy_count} campaign${client.strategy_count === 1 ? "" : "s"}`,
  ];
  if (client.meetings !== undefined) {
    parts.push(`${client.meetings} meeting${client.meetings === 1 ? "" : "s"}`);
  }
  if (client.sending_domains.length) {
    parts.push(client.sending_domains.join(", "));
  } else {
    parts.push("no sending domain reserved");
  }
  return parts.join(" · ");
}

/** The warning about a client whose sending is not isolated yet. An empty
 *  pool is permissive by design, so the UI has to say so rather than let
 *  someone assume isolation they do not have. */
export function poolWarning(client: ClientWorkspace): string | null {
  if (client.sending_domains.length) return null;
  return "No sending domain reserved — this client's campaigns can send from any "
    + "connected mailbox. Add a domain to isolate them.";
}

/** The banner on the overview: work nobody is billing for. */
export function unassignedWarning(overview: ClientOverview | null | undefined):
  string | null {
  if (!overview?.unassigned_strategies) return null;
  const n = overview.unassigned_strategies;
  return `${n} campaign${n === 1 ? "" : "s"} ${n === 1 ? "is" : "are"} not filed `
    + "under a client. That work is not on any invoice.";
}

/** Clients ordered the way an agency reads them: active first, then by the
 *  most recent activity proxy we have (meetings), then by name. */
export function sortClients<T extends ClientWorkspace & Partial<ClientReport>>(
  clients: T[],
): T[] {
  const rank: Record<ClientStatus, number> = { active: 0, paused: 1, archived: 2 };
  return [...clients].sort((a, b) =>
    rank[a.status] - rank[b.status]
    || (b.meetings ?? 0) - (a.meetings ?? 0)
    || a.name.localeCompare(b.name));
}

/** The invoice total, checked against its own lines. Returns null when they
 *  agree — the UI only shows this when the arithmetic does not, which should
 *  never happen and is worth seeing if it does. */
export function billingMismatch(billing: ClientBilling | null | undefined):
  string | null {
  if (!billing) return null;
  const summed = billing.lines.reduce((total, line) => total + line.amount_cents, 0);
  if (summed === billing.total_cents) return null;
  return `The lines add up to ${money(summed, billing.currency)} but the total says `
    + `${money(billing.total_cents, billing.currency)}.`;
}
