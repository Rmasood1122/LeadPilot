/** Identity & phone verification — pure helpers (Sections B + C).
 *
 *  Kept free of React and fetch so every rule the verification screen applies
 *  is unit-tested in src/tests/identity.test.ts. The SERVER is authoritative
 *  for every one of these checks (app/services/phone_verification.py and
 *  app/services/identity.py); these exist so the form can say "that number
 *  needs a country code" before a round trip, not instead of the server. */

import type { UserOut } from "./api/types";

export type VerificationStep = "identity" | "phone" | null;

export interface VerificationStatus {
  identity_required: boolean;
  identity_complete: boolean;
  phone_verified: boolean;
  phone_required: boolean;
  next_step: VerificationStep;
  personal_country: string | null;
  account_type: "individual" | "company" | null;
  company_name: string | null;
  company_country: string | null;
  phone_number_masked: string | null;
  under_review: boolean;
}

const E164 = /^\+[1-9]\d{7,14}$/;

/** Same normalisation as the backend: strip spaces, dashes, dots and
 *  parentheses; a leading 00 becomes +. Returns null when not E.164. */
export function normalizePhone(raw: string): string | null {
  let value = (raw ?? "").trim().replace(/[\s\-().]/g, "");
  if (value.startsWith("00")) value = `+${value.slice(2)}`;
  return E164.test(value) ? value : null;
}

/** +923001234567 -> +92*******567 (mirrors app/integrations/sms.py). */
export function maskPhone(phone: string | null | undefined): string {
  const value = phone ?? "";
  if (value.length <= 6) return "*".repeat(value.length);
  return value.slice(0, 3) + "*".repeat(value.length - 6) + value.slice(-3);
}

/** The six-digit code as typed: digits only, at most six. */
export function sanitizeCode(raw: string): string {
  return (raw ?? "").replace(/\D/g, "").slice(0, 6);
}

/** Whole seconds until an ISO timestamp, never negative. */
export function secondsUntil(iso: string | null | undefined, now: Date = new Date()): number {
  if (!iso) return 0;
  const target = Date.parse(iso);
  if (Number.isNaN(target)) return 0;
  return Math.max(0, Math.ceil((target - now.getTime()) / 1000));
}

/** 75 -> "1:15"; 0 -> "" (nothing to wait for). */
export function formatCountdown(seconds: number): string {
  if (seconds <= 0) return "";
  const m = Math.floor(seconds / 60);
  const s = seconds % 60;
  return `${m}:${String(s).padStart(2, "0")}`;
}

/** Which step the screen shows. Identity always comes first. */
export function stepFor(status: Pick<VerificationStatus,
  "identity_complete" | "phone_verified" | "phone_required">): VerificationStep {
  if (!status.identity_complete) return "identity";
  if (status.phone_required && !status.phone_verified) return "phone";
  return null;
}

// The phone step can be put off for the browser session (the gated actions
// still refuse with PHONE_NOT_VERIFIED). The identity step cannot.
export const DEFER_KEY = "leadpilot.verify.phone-deferred";

export function isPhoneDeferred(): boolean {
  try {
    return window.sessionStorage.getItem(DEFER_KEY) === "1";
  } catch {
    return false;
  }
}

export function deferPhone(): void {
  try {
    window.sessionStorage.setItem(DEFER_KEY, "1");
  } catch {
    /* storage blocked: the Shell will simply ask again */
  }
}

/** Should the Shell send this user to /onboarding/verify? Pre-0039 accounts
 *  (identity_required false or absent) never are. */
export function needsVerification(user: Pick<UserOut,
  "identity_required" | "identity_complete" | "phone_verified">, phoneDeferred = false): boolean {
  if (!user.identity_required) return false;
  if (!user.identity_complete) return true;
  return !user.phone_verified && !phoneDeferred;
}

/** The exact detail the backend's phone gate returns. */
export const PHONE_NOT_VERIFIED = "PHONE_NOT_VERIFIED";
