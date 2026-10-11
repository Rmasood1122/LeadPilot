import { describe, expect, it } from "vitest";
import { oauthResultMessage } from "@/lib/api/ecosystem";

describe("oauthResultMessage", () => {
  it("reports a successful connection", () => {
    expect(oauthResultMessage(new URLSearchParams("tab=integrations&hubspot=connected")))
      .toEqual({ text: "HubSpot connected", ok: true });
  });

  it("carries the failure reason", () => {
    expect(oauthResultMessage(new URLSearchParams("slack=error&reason=state%20expired")))
      .toEqual({ text: "Slack connection failed: state expired", ok: false });
  });

  it("ignores unrelated query strings", () => {
    expect(oauthResultMessage(new URLSearchParams("tab=integrations"))).toBeNull();
    expect(oauthResultMessage(new URLSearchParams("zoom=connected"))).toBeNull();
  });

  // Product defect #16: the Gmail callback now redirects here too.
  it("reports the Gmail callback result", () => {
    expect(oauthResultMessage(new URLSearchParams("tab=integrations&gmail=connected")))
      .toEqual({ text: "Gmail connected", ok: true });
    expect(oauthResultMessage(new URLSearchParams("gmail=error&reason=missing%20code")))
      .toEqual({ text: "Gmail connection failed: missing code", ok: false });
  });
});
