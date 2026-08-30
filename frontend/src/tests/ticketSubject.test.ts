import { describe, expect, it } from "vitest";

import {
  TICKET_SUBJECT_MAX,
  TICKET_SUBJECT_PREFIX,
  ticketSubjectFor,
} from "@/lib/support/ticketSubject";

describe("ticketSubjectFor", () => {
  it("uses the exact prefix the product owner specified", () => {
    expect(TICKET_SUBJECT_PREFIX).toBe("Question not in FAQ: ");
    expect(ticketSubjectFor("what is the weather")).toBe(
      "Question not in FAQ: what is the weather",
    );
  });

  it("returns an empty string for a blank question", () => {
    // Otherwise the box would be pre-filled with a prefix and nothing else,
    // which is worse than an empty box.
    for (const blank of ["", "   ", "\n\t", null, undefined]) {
      expect(ticketSubjectFor(blank)).toBe("");
    }
  });

  it("trims and collapses whitespace", () => {
    expect(ticketSubjectFor("  how   do  I \n start?  ")).toBe(
      "Question not in FAQ: how do I start?",
    );
  });

  it("NEVER exceeds the 200 characters the API accepts", () => {
    // The chat accepts 2000 characters but TicketIn.subject caps at 200. An
    // untruncated subject would pre-fill a value the server rejects with a
    // 422 the user cannot understand or fix without deleting text by hand.
    const long = "a".repeat(2000);
    const subject = ticketSubjectFor(long);
    expect(subject.length).toBe(TICKET_SUBJECT_MAX);
    expect(subject.startsWith(TICKET_SUBJECT_PREFIX)).toBe(true);
    expect(subject.endsWith("…")).toBe(true);
  });

  it("leaves a question that exactly fits untouched", () => {
    const exact = "b".repeat(TICKET_SUBJECT_MAX - TICKET_SUBJECT_PREFIX.length);
    const subject = ticketSubjectFor(exact);
    expect(subject.length).toBe(TICKET_SUBJECT_MAX);
    expect(subject.endsWith("…")).toBe(false);
    expect(subject).toBe(TICKET_SUBJECT_PREFIX + exact);
  });

  it("truncates a question that is one character too long", () => {
    const oneOver = "c".repeat(
      TICKET_SUBJECT_MAX - TICKET_SUBJECT_PREFIX.length + 1,
    );
    const subject = ticketSubjectFor(oneOver);
    expect(subject.length).toBe(TICKET_SUBJECT_MAX);
    expect(subject.endsWith("…")).toBe(true);
  });
});
