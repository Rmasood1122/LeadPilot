/**
 * Product defect #15: every 429 became "Too many requests...", hiding the
 * server's own explanation when the refusal is the plan's daily AI limit
 * (daily_ai_limit_reached) or the monthly spend cap (monthly_spend_cap_reached)
 * -- on Resume, Re-verify, lead sourcing and launch.
 */
import { describe, expect, it } from "vitest";
import { ApiError, normalizeError } from "@/lib/api/client";
import { resumeStrategyErrorMessage } from "@/lib/api/strategies";
import { launchErrorMessage, sourceErrorMessage } from "@/lib/leadOutreach";

const DAILY = "Your Starter plan's daily AI limit ($10.00) is used up. It resets at 00:00 UTC.";
const MONTHLY = "This run is forecast to cost $3.00, but only $1.00 of your $50.00 monthly spend cap is left.";

function resp(status: number, body: unknown): Response {
  return new Response(JSON.stringify(body), { status, headers: { "Content-Type": "application/json" } });
}

describe("structured 429 refusals keep the server's message", () => {
  it("normalizeError keeps the error code", async () => {
    const err = await normalizeError(resp(429, {
      detail: { error: "daily_ai_limit_reached", plan: "Starter", message: DAILY } }));
    expect(err.code).toBe("daily_ai_limit_reached");
    expect(err.detail).toBe(DAILY);
  });

  it.each([
    ["Resume / Re-verify", resumeStrategyErrorMessage],
    ["sourcing", sourceErrorMessage],
    ["launch", launchErrorMessage],
  ])("%s shows the daily-limit and spend-cap sentences", async (_name, fn) => {
    const daily = await normalizeError(resp(429, {
      detail: { error: "daily_ai_limit_reached", message: DAILY } }));
    const monthly = await normalizeError(resp(429, {
      detail: { error: "monthly_spend_cap_reached", message: MONTHLY } }));
    expect(fn(daily)).toBe(DAILY);
    expect(fn(monthly)).toBe(MONTHLY);
  });

  it.each([resumeStrategyErrorMessage, sourceErrorMessage, launchErrorMessage])(
    "a plain rate-limit 429 still says to wait", (fn) => {
      expect(fn(new ApiError(429, "Rate limit exceeded"))).toMatch(/too many requests/i);
    });
});
