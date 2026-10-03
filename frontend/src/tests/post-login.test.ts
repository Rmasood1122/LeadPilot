import { describe, expect, it } from "vitest";
import { postLoginDestination } from "@/lib/post-login";

const ready = {
  email: "founder@agency.com",
  email_verified: true,
  identity_required: false,
  identity_complete: true,
  phone_verified: true,
  has_active_plan: true,
};
const afterLogin = { afterLogin: true };

describe("postLoginDestination — right after sign-in", () => {
  it("sends an account with a plan to the dashboard", () => {
    expect(postLoginDestination(ready, afterLogin)).toBe("/pipeline");
  });

  it("sends an account that never bought a plan to pricing", () => {
    expect(postLoginDestination({ ...ready, has_active_plan: false }, afterLogin)).toBe("/pricing");
  });

  it("does not gate on a response that predates has_active_plan", () => {
    expect(postLoginDestination({ ...ready, has_active_plan: undefined }, afterLogin)).toBe("/pipeline");
  });

  it("asks for email verification before anything else", () => {
    expect(postLoginDestination({ ...ready, email_verified: false, has_active_plan: false }, afterLogin))
      .toBe("/check-email?email=founder%40agency.com");
  });

  it("finishes identity verification before pricing (checkout needs a verified phone)", () => {
    const user = { ...ready, identity_required: true, identity_complete: false, has_active_plan: false };
    expect(postLoginDestination(user, afterLogin)).toBe("/onboarding/verify");
  });

  it("respects a deferred phone step", () => {
    const user = { ...ready, identity_required: true, phone_verified: false, has_active_plan: false };
    expect(postLoginDestination(user, afterLogin)).toBe("/onboarding/verify");
    expect(postLoginDestination(user, { ...afterLogin, phoneDeferred: true })).toBe("/pricing");
  });
});

describe("postLoginDestination — silent session restore", () => {
  it("never sends a no-plan user to pricing on app load", () => {
    expect(postLoginDestination({ ...ready, has_active_plan: false })).toBe("/pipeline");
  });

  it("still enforces email and identity verification", () => {
    expect(postLoginDestination({ ...ready, email_verified: false }))
      .toBe("/check-email?email=founder%40agency.com");
    expect(postLoginDestination({ ...ready, identity_required: true, identity_complete: false }))
      .toBe("/onboarding/verify");
  });
});
