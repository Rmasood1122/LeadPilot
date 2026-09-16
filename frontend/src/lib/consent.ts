/** Part 1 Feature 9 — the compliance and consent layer, shaped for the UI.
 *  Pure; tested in src/tests/consent.test.ts. */

export type ConsentChannel = "email" | "phone" | "linkedin" | "whatsapp";
export type ConsentKind = "granted" | "withdrawn" | "suppressed" | "erased";

export interface ChannelRequirements {
  unsubscribe_required: boolean;
  sender_identity: boolean;
  prior_consent: boolean;
  tracking_allowed: boolean;
  notes: string[];
}

export interface ChannelConsent {
  contactable: boolean;
  reason: string | null;
  identifier: string | null;
  requirements: ChannelRequirements;
}

export interface LeadConsent {
  lead_id: string;
  region: string | null;
  regime: string;
  legal_basis: string;
  channels: Record<ConsentChannel, ChannelConsent>;
  history: ConsentEvent[];
}

export interface ConsentEvent {
  id: string;
  lead_id: string | null;
  kind: ConsentKind;
  channel: string;
  identifier: string | null;
  region: string | null;
  regime: string | null;
  basis: string | null;
  source: string;
  detail: string | null;
  meta: Record<string, unknown> | null;
  actor_user_id: string | null;
  ts: string | null;
}

export const CHANNEL_ORDER: ConsentChannel[] = ["email", "linkedin", "phone", "whatsapp"];

const CHANNEL_LABELS: Record<ConsentChannel, string> = {
  email: "Email", phone: "Phone", linkedin: "LinkedIn", whatsapp: "WhatsApp",
};

export function channelLabel(channel: string): string {
  return CHANNEL_LABELS[channel as ConsentChannel] ?? channel;
}

const KIND_LABELS: Record<ConsentKind, string> = {
  granted: "Consent given",
  withdrawn: "Asked us to stop",
  suppressed: "Suppressed",
  erased: "Data erased",
};

export function kindLabel(kind: ConsentKind): string {
  return KIND_LABELS[kind] ?? kind;
}

export function kindTone(kind: ConsentKind): "success" | "warning" | "destructive" | "default" {
  if (kind === "granted") return "success";
  if (kind === "withdrawn") return "destructive";
  if (kind === "erased") return "warning";
  return "default";
}

/** "Contactable" or the reason not — never a bare boolean, because "no
 *  address on file" and "they asked us to stop" are very different states. */
export function channelStatusText(entry: ChannelConsent): string {
  if (entry.contactable) return "Contactable";
  return entry.reason ?? "Not contactable";
}

export function channelTone(entry: ChannelConsent): "success" | "warning" | "destructive" {
  if (entry.contactable) return "success";
  if (entry.reason === "suppressed") return "destructive";
  return "warning";
}

/** Channels ordered for display, with the ones that ARE open first — the
 *  question a person has open is "how can I reach them", not "how can't I". */
export function orderedChannels(consent: LeadConsent | null | undefined):
  { channel: ConsentChannel; entry: ChannelConsent }[] {
  if (!consent) return [];
  return CHANNEL_ORDER
    .filter((channel) => consent.channels[channel])
    .map((channel) => ({ channel, entry: consent.channels[channel] }))
    .sort((a, b) => Number(b.entry.contactable) - Number(a.entry.contactable));
}

/** True when this person cannot be reached at all. The panel leads with this
 *  rather than making someone read four rows to work it out. */
export function isFullySuppressed(consent: LeadConsent | null | undefined): boolean {
  const rows = orderedChannels(consent);
  return rows.length > 0 && rows.every((row) => !row.entry.contactable);
}

/** The one-line summary above the channel list. */
export function consentHeadline(consent: LeadConsent | null | undefined): string {
  if (!consent) return "";
  if (isFullySuppressed(consent)) {
    return `No contactable channel — ${consent.regime} applies.`;
  }
  const open = orderedChannels(consent).filter((r) => r.entry.contactable);
  return `${open.map((r) => channelLabel(r.channel)).join(", ")} open · ${consent.regime}.`;
}

/** Every requirement that applies to a contactable channel, de-duplicated —
 *  the same note often applies to email and LinkedIn. */
export function activeNotes(consent: LeadConsent | null | undefined): string[] {
  const notes = new Set<string>();
  for (const { entry } of orderedChannels(consent)) {
    if (!entry.contactable) continue;
    for (const note of entry.requirements.notes) notes.add(note);
  }
  return [...notes];
}
