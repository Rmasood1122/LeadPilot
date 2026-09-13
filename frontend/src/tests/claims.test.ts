import { describe, expect, it } from "vitest";
import {
  categoryLabel,
  describeMissing,
  groupByMessage,
  sourceLabel,
  verdictTone,
  type ClaimCheck,
} from "@/lib/claims";

function check(overrides: Partial<ClaimCheck>): ClaimCheck {
  return {
    id: Math.random().toString(36).slice(2), lead_id: "l1", message_id: "m1",
    channel: "email", field: "body", category: "funding", claim_text: "Congrats on the round.",
    verdict: "verified", extractor: "rules", evidence_source: null, evidence_excerpt: null,
    unsupported: [], replacement_text: null, created_at: "2026-09-13T10:00:00Z", ...overrides,
  };
}

describe("labels", () => {
  it("maps verdicts to tones", () => {
    expect(verdictTone("verified")).toBe("success");
    expect(verdictTone("rewritten")).toBe("warning");
    expect(verdictTone("stripped")).toBe("destructive");
  });
  it("names categories and falls back readably", () => {
    expect(categoryLabel("their_content")).toBe("Their post");
    expect(categoryLabel("brand_new_kind")).toBe("brand new kind");
  });
  it("describes where evidence came from", () => {
    expect(sourceLabel("apollo:enrichment.person.organization.estimated_num_employees"))
      .toBe("Apollo · estimated num employees");
    expect(sourceLabel("newsapi:https://news.example/a:b")).toBe("NewsAPI");
    expect(sourceLabel("linkedin_post:https://linkedin.com/p/1")).toBe("LinkedIn post");
    expect(sourceLabel(null)).toBe("No stored source");
  });
  it("explains what could not be found", () => {
    expect(describeMissing("number:2.5e+07")).toBe("the number 25,000,000");
    expect(describeMissing("series:c")).toBe("Series C");
    expect(describeMissing("name:Salesforce")).toBe("“Salesforce”");
    expect(describeMissing("no funding evidence on record")).toBe("no funding evidence on record");
  });
});

describe("groupByMessage", () => {
  it("groups per message, newest first, counting removals", () => {
    const groups = groupByMessage([
      check({ message_id: "old", created_at: "2026-09-01T00:00:00Z" }),
      check({ message_id: "new", verdict: "stripped", created_at: "2026-09-10T00:00:00Z" }),
      check({ message_id: "new", verdict: "rewritten", created_at: "2026-09-10T00:00:01Z" }),
    ]);
    expect(groups.map((g) => g.message_id)).toEqual(["new", "old"]);
    expect(groups[0].removed).toBe(2);
    expect(groups[1].removed).toBe(0);
  });
  it("keeps checks made outside a send apart", () => {
    const groups = groupByMessage([check({ message_id: null, id: "a" }),
                                   check({ message_id: null, id: "b", created_at: "x" })]);
    expect(groups).toHaveLength(2);
  });
});
