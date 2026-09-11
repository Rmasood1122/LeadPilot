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
    expect(oauthResultMessage(new URLSearchParams("gmail=connected"))).toBeNull();
  });
});
