import { describe, expect, it } from "vitest";
import {
  OUTCOME_OPTIONS,
  draftStatusInfo,
  isBriefInFlight,
  meetingWhen,
  outcomeLabel,
  parseDealValue,
  profileRows,
} from "@/lib/meeting-prep";

describe("draftStatusInfo", () => {
  it("only a saved draft can be sent", () => {
    const sendable = (
      ["pending", "draft_saved", "sent", "not_connected", "reauth_required",
       "suppressed", "no_address", "generation_failed", "failed"] as const
    ).filter((s) => draftStatusInfo(s).canSend);
    expect(sendable).toEqual(["draft_saved"]);
  });

  it("a suppressed contact can be neither edited nor sent", () => {
    const info = draftStatusInfo("suppressed");
    expect(info.canSend).toBe(false);
    expect(info.canEdit).toBe(false);
    expect(info.tone).toBe("destructive");
  });

  it("surfaces the Gmail error text", () => {
    expect(draftStatusInfo("failed", "HTTP 500").message).toContain("HTTP 500");
  });
});

describe("isBriefInFlight", () => {
  it("polls only while pending or generating", () => {
    expect(isBriefInFlight({ status: "pending" })).toBe(true);
    expect(isBriefInFlight({ status: "generating" })).toBe(true);
    expect(isBriefInFlight({ status: "ready" })).toBe(false);
    expect(isBriefInFlight({ status: "failed" })).toBe(false);
    expect(isBriefInFlight(null)).toBe(false);
  });
});

describe("profileRows", () => {
  it("drops empty fields and links LinkedIn and bare domains", () => {
    const rows = profileRows({
      name: "Sara Khan", title: null, company: "Acme", email: "s@acme.test",
      phone: "", linkedin_url: "https://linkedin.com/in/sara", location: null,
      industry: "fire", company_size: 30, company_website: "acme.test",
      founded_year: null, funding: null, status: "replied",
    });
    expect(rows.map((r) => r.label)).toEqual([
      "Name", "Company", "Email", "LinkedIn", "Industry", "Company size", "Website",
    ]);
    expect(rows.find((r) => r.label === "Website")?.href).toBe("https://acme.test");
    expect(rows.find((r) => r.label === "LinkedIn")?.href).toBe("https://linkedin.com/in/sara");
    expect(rows.find((r) => r.label === "Company size")?.value).toBe("30");
  });

  it("handles a missing profile", () => {
    expect(profileRows(null)).toEqual([]);
  });
});

describe("meetingWhen", () => {
  const now = new Date(2026, 8, 11, 10, 0);
  it("labels today and tomorrow", () => {
    expect(meetingWhen(new Date(2026, 8, 11, 15, 0).toISOString(), now)).toMatch(/^Today /);
    expect(meetingWhen(new Date(2026, 8, 12, 9, 30).toISOString(), now)).toMatch(/^Tomorrow /);
  });
  it("never throws on missing or bad input", () => {
    expect(meetingWhen(null)).toBe("Time not on record");
    expect(meetingWhen("not a date")).toBe("Time not on record");
  });
});

describe("parseDealValue", () => {
  it("accepts currency formatting", () => {
    expect(parseDealValue("$4,500.50")).toBe(4500.5);
    expect(parseDealValue("1200")).toBe(1200);
  });
  it("rejects garbage", () => {
    expect(parseDealValue("")).toBeNull();
    expect(parseDealValue("1.2.3")).toBeNull();
    expect(parseDealValue("abc")).toBeNull();
  });
});

describe("outcome options", () => {
  it("covers all five backend outcomes exactly once", () => {
    expect(OUTCOME_OPTIONS.map((o) => o.value).sort()).toEqual(
      ["closed_lost", "closed_won", "interested", "needs_follow_up", "not_a_fit"],
    );
    expect(outcomeLabel("closed_won")).toBe("Closed won");
  });
});
