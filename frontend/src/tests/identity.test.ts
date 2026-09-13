import { afterEach, describe, expect, it } from "vitest";
import {
  DEFER_KEY,
  deferPhone,
  formatCountdown,
  isPhoneDeferred,
  maskPhone,
  needsVerification,
  normalizePhone,
  sanitizeCode,
  secondsUntil,
  stepFor,
} from "@/lib/identity";

describe("normalizePhone (mirrors the backend)", () => {
  it("accepts international formats with separators", () => {
    expect(normalizePhone("+1 (415) 555-0123")).toBe("+14155550123");
    expect(normalizePhone("0092 300 1234567")).toBe("+923001234567");
    expect(normalizePhone("+44.20.7946.0958")).toBe("+442079460958");
  });
  it("rejects numbers without a country code or out of range", () => {
    expect(normalizePhone("4155550123")).toBeNull();
    expect(normalizePhone("+0123456789")).toBeNull();
    expect(normalizePhone("+1415")).toBeNull();
    expect(normalizePhone("")).toBeNull();
  });
});

describe("maskPhone (mirrors app/integrations/sms.py)", () => {
  it("keeps the first three and last three characters", () => {
    expect(maskPhone("+14155550123")).toBe("+14******123");
    expect(maskPhone("12345")).toBe("*****");
    expect(maskPhone(null)).toBe("");
  });
});

describe("code entry", () => {
  it("keeps digits only, at most six", () => {
    expect(sanitizeCode(" 12-34 56 78")).toBe("123456");
    expect(sanitizeCode("abc")).toBe("");
  });
});

describe("resend countdown", () => {
  const now = new Date("2026-09-13T10:00:00Z");
  it("counts whole seconds and never goes negative", () => {
    expect(secondsUntil("2026-09-13T10:01:15Z", now)).toBe(75);
    expect(secondsUntil("2026-09-13T09:59:00Z", now)).toBe(0);
    expect(secondsUntil(null, now)).toBe(0);
    expect(secondsUntil("not a date", now)).toBe(0);
  });
  it("formats m:ss and hides a finished wait", () => {
    expect(formatCountdown(75)).toBe("1:15");
    expect(formatCountdown(9)).toBe("0:09");
    expect(formatCountdown(0)).toBe("");
  });
});

describe("step routing", () => {
  it("always asks identity first", () => {
    expect(stepFor({ identity_complete: false, phone_verified: true, phone_required: true }))
      .toBe("identity");
  });
  it("then the phone, unless the deployment turned the requirement off", () => {
    expect(stepFor({ identity_complete: true, phone_verified: false, phone_required: true }))
      .toBe("phone");
    expect(stepFor({ identity_complete: true, phone_verified: false, phone_required: false }))
      .toBeNull();
  });
});

describe("needsVerification (the Shell's redirect rule)", () => {
  it("never redirects a pre-0039 account", () => {
    expect(needsVerification({ identity_required: false })).toBe(false);
    expect(needsVerification({})).toBe(false);
  });
  it("redirects until identity is complete, even when the phone is deferred", () => {
    expect(needsVerification({ identity_required: true, identity_complete: false }, true))
      .toBe(true);
  });
  it("lets a deferred phone through, but not an undeferred one", () => {
    const user = { identity_required: true, identity_complete: true, phone_verified: false };
    expect(needsVerification(user, false)).toBe(true);
    expect(needsVerification(user, true)).toBe(false);
    expect(needsVerification({ ...user, phone_verified: true }, false)).toBe(false);
  });
});

describe("phone deferral", () => {
  afterEach(() => window.sessionStorage.removeItem(DEFER_KEY));
  it("is remembered for the session", () => {
    expect(isPhoneDeferred()).toBe(false);
    deferPhone();
    expect(isPhoneDeferred()).toBe(true);
  });
});
