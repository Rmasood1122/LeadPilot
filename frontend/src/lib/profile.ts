/** Pure rules for the Profile page. The server re-checks everything. */
import { ApiError } from "@/lib/api/client";

export const MIN_PASSWORD = 8;
export const MAX_NAME = 120;

export function validateName(raw: string): string | null {
  const v = raw.trim();
  if (v.length > MAX_NAME) return `Name must be ${MAX_NAME} characters or fewer.`;
  // eslint-disable-next-line no-control-regex
  if (/[\x00-\x1f\x7f]/.test(v)) return "Name contains invalid characters.";
  return null;
}

export function validatePasswordChange(
  current: string, next: string, confirm: string,
): string | null {
  if (!current) return "Enter your current password.";
  if (next.length < MIN_PASSWORD) return `New password must be at least ${MIN_PASSWORD} characters.`;
  if (next === current) return "New password must be different from the current one.";
  if (next !== confirm) return "The two new passwords do not match.";
  return null;
}

export function passwordErrorMessage(err: unknown): string {
  if (err instanceof ApiError) {
    if (err.status === 429) return "Too many attempts. Wait a while and try again.";
    if (err.status === 400 || err.status === 422) return err.message;
  }
  return "Could not change the password. Try again.";
}

const LABELS: Record<string, string> = {
  free: "Free", starter: "Starter", growth: "Growth", scale: "Scale", pro: "Pro",
  enterprise: "Enterprise", pay_per_meeting: "Pay per meeting",
};
export const planLabel = (plan: string): string => LABELS[plan] ?? plan;
/** Enterprise is the top tier: there is nothing to upgrade to. */
export const canUpgrade = (plan: string): boolean => plan !== "enterprise";

/** File name for the account export, e.g. leadpilot-account-export-2026-10-10.json */
export function accountExportFilename(now: Date = new Date()): string {
  return `leadpilot-account-export-${now.toISOString().slice(0, 10)}.json`;
}

export function exportErrorMessage(err: unknown): string {
  if (err instanceof ApiError) {
    if (err.status === 403 && err.detail === "INVALID_PASSWORD") return "That password is not right.";
    if (err.status === 429) return "Too many attempts. Wait a while and try again.";
  }
  return "Could not prepare your data. Try again.";
}
