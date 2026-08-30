/**
 * Pre-filled subject for a ticket escalated from the chat (Task 4).
 *
 * WHY THIS IS DERIVED IN THE UI AND NOT RETURNED BY THE API
 * The subject is a starting point in an editable input, not a stored value.
 * Deriving it here means it also works for a conversation reloaded from
 * history, where the API response that produced the answer is long gone --
 * the question is still sitting in the transcript directly above it. Sending
 * it from the server would have covered only the live reply and left every
 * reloaded message with an empty box.
 */

/** Prefix required by the product owner. Kept exact. */
export const TICKET_SUBJECT_PREFIX = "Question not in FAQ: ";

/** The API caps subject at 200 characters (TicketIn.subject, max_length=200). */
export const TICKET_SUBJECT_MAX = 200;

/**
 * Build the subject for `question`.
 *
 * The API rejects anything over 200 characters, and the chat accepts messages
 * up to 2000, so a long question MUST be truncated here -- otherwise clicking
 * "Submit a ticket" pre-fills a subject the server will refuse with a 422 the
 * user cannot understand or fix without deleting text by hand.
 *
 * Returns "" for a blank question so the caller renders an empty input rather
 * than a subject that is nothing but the prefix.
 */
export function ticketSubjectFor(question: string | null | undefined): string {
  const trimmed = (question ?? "").trim().replace(/\s+/g, " ");
  if (!trimmed) return "";

  const subject = TICKET_SUBJECT_PREFIX + trimmed;
  if (subject.length <= TICKET_SUBJECT_MAX) return subject;

  // Reserve one character for the ellipsis so the result is exactly at the
  // limit, never one over it.
  const room = TICKET_SUBJECT_MAX - TICKET_SUBJECT_PREFIX.length - 1;
  return TICKET_SUBJECT_PREFIX + trimmed.slice(0, room) + "…";
}
