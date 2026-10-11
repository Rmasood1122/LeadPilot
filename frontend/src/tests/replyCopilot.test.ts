import { describe, expect, it } from "vitest";

import {
  approveLabel,
  answersEarlierReplies,
  autoSendBlockedReason,
  deliveryLabel,
  formatDuration,
  formatShare,
  intentLabel,
  intentTone,
  isCopyOnly,
  isDisabledError,
  isEdited,
  type ReplyDraft,
} from "@/lib/replyCopilot";

function draft(overrides: Partial<ReplyDraft> = {}): ReplyDraft {
  return {
    id: "d1", reply_id: "r1", lead_id: "l1",
    lead: { full_name: "Sara Khan", company: "Acme Fire" },
    channel: "email", intent: "positive", meeting_time_request: false,
    status: "pending", draft_subject: "Re: Quick question",
    draft_body: "Thanks Sara - happy to walk you through it.",
    final_subject: null, final_body: null, edited: false, auto_sent: false,
    claim_flags: [], grounding: {}, reply_preview: "How does it work?",
    reply_received_at: "2026-10-10T10:00:00Z", decided_at: null,
    created_at: "2026-10-10T10:01:00Z", delivery: null, send_result: null,
    ...overrides,
  };
}

describe("labels", () => {
  it("names each intent", () => {
    expect(intentLabel("positive")).toBe("Interested");
    expect(intentLabel("objection")).toBe("Objection");
    expect(intentLabel("question")).toBe("Question");
    expect(intentTone("positive")).toBe("success");
    expect(intentTone("objection")).toBe("warning");
  });

  it("LinkedIn is copy-only, email sends", () => {
    expect(isCopyOnly(draft({ channel: "linkedin" }))).toBe(true);
    expect(isCopyOnly(draft())).toBe(false);
    expect(approveLabel(draft(), draft().draft_body)).toBe("Approve & send");
    expect(approveLabel(draft(), "Different words")).toBe("Send edited");
    expect(approveLabel(draft({ channel: "linkedin" }), draft().draft_body)).toBe("Copy");
  });
});

describe("edit detection mirrors the backend", () => {
  it("ignores whitespace-only changes", () => {
    const d = draft();
    expect(isEdited(d, `  ${d.draft_body.replace(/ /g, "  ")}\n`)).toBe(false);
    expect(isEdited(d, `${d.draft_body} Thursday?`)).toBe(true);
  });
});

describe("delivery", () => {
  it("says what happened to a decision", () => {
    expect(deliveryLabel(draft())).toBe("Waiting for you");
    expect(deliveryLabel(draft({ status: "discarded" }))).toBe("Discarded");
    expect(deliveryLabel(draft({ status: "copied" }))).toMatch(/LinkedIn/);
    expect(deliveryLabel(draft({ status: "superseded" }))).toMatch(/newer reply/);
    expect(deliveryLabel(draft({ status: "approved" }))).toBe("queued");
    expect(deliveryLabel(draft({
      status: "approved",
      delivery: { state: "sent", status: "sent", error: null, sent_at: null },
    }))).toBe("sent");
    expect(deliveryLabel(draft({
      status: "approved", auto_sent: true,
      delivery: { state: "queued", status: "scheduled", error: null, sent_at: null },
    }))).toMatch(/^Auto-sent: queued/);
    expect(deliveryLabel(draft({
      status: "approved",
      delivery: { state: "blocked", status: "cancelled", error: "suppressed at send time",
                  sent_at: null },
    }))).toBe("not sent — suppressed at send time");
    expect(deliveryLabel(draft({
      status: "approved",
      delivery: { state: "held_for_review", status: "awaiting_review", error: null,
                  sent_at: null },
    }))).toMatch(/review/);
  });
});

describe("metric formatting", () => {
  it("never shows 0 for nothing measured", () => {
    expect(formatDuration(null)).toBe("—");
    expect(formatShare(null)).toBe("—");
    expect(formatShare(0)).toBe("0%");
  });

  it("formats durations", () => {
    expect(formatDuration(42)).toBe("42s");
    expect(formatDuration(600)).toBe("10 min");
    expect(formatDuration(7200)).toBe("2.0 h");
    expect(formatDuration(3 * 86400)).toBe("3.0 days");
    expect(formatShare(0.756)).toBe("76%");
  });
});

describe("flag and settings", () => {
  it("treats 404 as the feature being off", () => {
    expect(isDisabledError({ status: 404 })).toBe(true);
    expect(isDisabledError({ status: 500 })).toBe(false);
    expect(isDisabledError(null)).toBe(false);
  });

  it("explains why auto-send cannot be turned on", () => {
    expect(autoSendBlockedReason(undefined)).toBe("Loading…");
    expect(autoSendBlockedReason({ auto_send_meeting_time: false, auto_send_allowed: false,
                                   enabled: true })).toMatch(/administrator/);
    expect(autoSendBlockedReason({ auto_send_meeting_time: false, auto_send_allowed: true,
                                   enabled: true })).toBeNull();
    // Already on: turning it OFF must stay possible even if the admin switch moved.
    expect(autoSendBlockedReason({ auto_send_meeting_time: true, auto_send_allowed: false,
                                   enabled: true })).toBeNull();
  });
});

describe("answer earlier replies (per-account setting)", () => {
  it("defaults to on, including for an older API without the field", () => {
    expect(answersEarlierReplies(undefined)).toBe(true);
    expect(answersEarlierReplies({ auto_send_meeting_time: false, auto_send_allowed: false,
                                   enabled: true })).toBe(true);
    expect(answersEarlierReplies({ auto_send_meeting_time: false, auto_send_allowed: false,
                                   answer_earlier_replies: false, enabled: true })).toBe(false);
  });
});
