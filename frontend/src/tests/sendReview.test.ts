import { describe, expect, it } from "vitest";

import {
  MIN_REJECT_NOTE,
  canDecide,
  hasEdits,
  isStale,
  rejectNoteError,
  reviewHeadline,
  sortTriggers,
  triggerTone,
  waitingFor,
  type SendReviewItem,
} from "@/lib/sendReview";

const NOW = new Date("2026-09-16T12:00:00Z");

function item(overrides: Partial<SendReviewItem> = {}): SendReviewItem {
  return {
    id: "r1", message_id: "m1", status: "pending",
    triggers: [{ code: "vip_title", label: "Executive / VIP contact",
                 detail: "Sara Khan is CEO at Blaze Safety." }],
    subject: "Quick question", body: "Who owns inspections?", edited: false,
    channel: "email", step_no: 2, message_status: "awaiting_review",
    lead: { id: "l1", full_name: "Sara Khan", title: "CEO",
            company: "Blaze Safety", email: "sara@blaze.test" },
    decision_note: null, decided_at: null, decided_by_user_id: null,
    created_at: "2026-09-16T10:00:00Z",
    ...overrides,
  };
}

describe("sortTriggers", () => {
  it("puts the relationship-ending reason first", () => {
    const sorted = sortTriggers([
      { code: "tone_flag", label: "Tone", detail: "" },
      { code: "prior_objection", label: "Objected", detail: "" },
      { code: "vip_title", label: "VIP", detail: "" },
    ]);
    expect(sorted.map((t) => t.code)).toEqual(["prior_objection", "vip_title", "tone_flag"]);
  });

  it("does not mutate its input", () => {
    const triggers = [{ code: "tone_flag" as const, label: "Tone", detail: "" },
                      { code: "prior_objection" as const, label: "Objected", detail: "" }];
    sortTriggers(triggers);
    expect(triggers[0].code).toBe("tone_flag");
  });
});

describe("triggerTone", () => {
  it("treats a prior objection as the serious one", () => {
    expect(triggerTone("prior_objection")).toBe("destructive");
    expect(triggerTone("vip_title")).toBe("warning");
    expect(triggerTone("tone_flag")).toBe("default");
  });
});

describe("reviewHeadline", () => {
  it("leads with the most serious reason and the person", () => {
    expect(reviewHeadline(item())).toBe("Executive / VIP contact — Sara Khan");
  });

  it("falls back to the email when there is no name", () => {
    expect(reviewHeadline(item({
      lead: { id: "l1", full_name: null, title: null, company: null,
              email: "x@y.test" },
    }))).toContain("x@y.test");
  });

  it("still says something when the triggers list is empty", () => {
    expect(reviewHeadline(item({ triggers: [] }))).toBe("Step 2 to Sara Khan");
  });
});

describe("waitingFor", () => {
  it("counts hours then days", () => {
    expect(waitingFor(item(), NOW)).toBe("waiting 2 hours");
    expect(waitingFor(item({ created_at: "2026-09-13T12:00:00Z" }), NOW))
      .toBe("waiting 3 days");
  });

  it("uses the singular for one", () => {
    expect(waitingFor(item({ created_at: "2026-09-16T11:00:00Z" }), NOW))
      .toBe("waiting 1 hour");
    expect(waitingFor(item({ created_at: "2026-09-15T12:00:00Z" }), NOW))
      .toBe("waiting 1 day");
  });

  it("says less than an hour rather than 0 hours", () => {
    expect(waitingFor(item({ created_at: "2026-09-16T11:40:00Z" }), NOW))
      .toBe("waiting less than an hour");
  });

  it("is empty without a timestamp, and never negative", () => {
    expect(waitingFor(item({ created_at: null }), NOW)).toBe("");
    expect(waitingFor(item({ created_at: "2026-09-17T12:00:00Z" }), NOW)).toBe("");
  });
});

describe("isStale", () => {
  it("flags a message held for more than three days", () => {
    expect(isStale(item({ created_at: "2026-09-12T11:00:00Z" }), NOW)).toBe(true);
    expect(isStale(item({ created_at: "2026-09-14T12:00:00Z" }), NOW)).toBe(false);
  });

  it("never flags a decided review — it is not waiting for anyone", () => {
    expect(isStale(item({ created_at: "2026-09-01T12:00:00Z", status: "approved" }), NOW))
      .toBe(false);
  });
});

describe("canDecide", () => {
  it("is true only while pending", () => {
    expect(canDecide(item())).toBe(true);
    expect(canDecide(item({ status: "approved" }))).toBe(false);
    expect(canDecide(item({ status: "rejected" }))).toBe(false);
  });
});

describe("rejectNoteError", () => {
  it("refuses a shrug", () => {
    expect(rejectNoteError("no")).toContain(String(MIN_REJECT_NOTE));
    expect(rejectNoteError("   ")).not.toBeNull();
  });

  it("accepts a real reason", () => {
    expect(rejectNoteError("Wrong moment for this account")).toBeNull();
  });
});

describe("hasEdits", () => {
  it("is false when nothing changed", () => {
    expect(hasEdits(item(), "Quick question", "Who owns inspections?")).toBe(false);
  });

  it("is true for a changed body or subject", () => {
    expect(hasEdits(item(), "Quick question", "Different")).toBe(true);
    expect(hasEdits(item(), "Different", "Who owns inspections?")).toBe(true);
  });

  it("treats a null original as an empty string, not as a difference", () => {
    expect(hasEdits(item({ subject: null, body: null }), "", "")).toBe(false);
  });
});
