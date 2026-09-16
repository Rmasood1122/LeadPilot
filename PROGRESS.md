# PROGRESS — overnight build (started 2026-09-16)

Branch: `feature/8-new-features`. Never merged to `master`, never force-pushed.

## How to read this
Each feature below moves through: **migration → service → API → frontend → tests → docs → commit**.
"Done" means all seven, with the relevant test suites green.

---

## Scope

**Part 1 — 12 differentiation features**

| # | Feature | Status |
|---|---------|--------|
| 1 | Positive Reply Classifier | **done** (0053) |
| 2 | F-P-T-A Scoring Engine | not started |
| 3 | Sequence Completion Guarantee + metric | not started |
| 4 | Deliverability Health Score (per mailbox) | not started |
| 5 | Human Review Queue for high-risk sends | not started |
| 6 | Unified Cross-Channel Inbox | not started |
| 7 | Re-engagement Memory ("not now" ≠ "never") | not started |
| 8 | Transparent Attribution Ledger | not started |
| 9 | Compliance & Consent Layer | not started |
| 10 | Data Provenance Tags | not started |
| 11 | Founder/Agency Mode (multi-client workspaces) | not started |
| 12 | "Why This Prospect" Explainability Panel | not started |

**Part 2 — Meeting Prep & Training module**

| # | Piece | Status |
|---|-------|--------|
| P2.1 | Auto-generated meeting brief + script | not started |
| P2.2 | Mock interview / roleplay mode + feedback | not started |
| P2.3 | Standalone practice + pre-meeting checklist | not started |

---

## Baseline survey (what already existed on 2026-09-16)

Read before writing anything, so nothing gets rebuilt that is already there:

- **Replies** — `InboundReply` already carries `classification` (routing: unsubscribe /
  bounce / out-of-office), `reply_category` (BUYING_SIGNAL | OBJECTION | NOT_NOW |
  WRONG_PERSON, feature 0034) and `authenticity_kind` (0043). None of these is the
  5-way interested/neutral/objection/not-now/unsubscribe taxonomy feature 1 asks for,
  and no "positive reply rate" metric exists. → new, additive column set.
- **Scoring** — `lead_scoring.py` produces `ai_booking_likelihood` (a single 0-100
  booking-likelihood number). No F-P-T-A decomposition. → new service, new columns.
- **Sequences** — `sequence_engine.py` already hard-stops only on explicit conditions,
  but there is no record of *planned* step count, no completion timestamp, and no
  completion-rate metric. → columns + metric.
- **Deliverability** — `deliverability.py` scores per *domain* per user (SPF/DKIM/DMARC
  + blacklist + bounce rate). Nothing per *mailbox*, no spam-complaint rate, no
  auto-throttle. → new per-mailbox table + scheduled refresh + send-path throttle.
- **Reviews** — `SequenceReview` (0047) reviews sequence *content* before launch. There
  is no per-*message* human approval queue. → new table.
- **Conversation** — `conversation_thread.py` builds one lead's cross-channel thread.
  There is no cross-*prospect* inbox list. → new endpoint + page on top of it.
- **Re-engagement** — `ReengagementAttempt` (0048) exists for post-sequence touches;
  `InboundReply.reschedule_date` exists but nothing auto-schedules from a "not now".
- **Compliance** — `compliance_region.py`, `compliance_audit.py`, `ComplianceAuditLog`
  and `SuppressionEntry` exist. Suppression is email/phone only (no LinkedIn/WhatsApp
  in the same act) and there is no consent-event ledger.
- **Workspaces** — `workspaces.py` has members/roles/branding/domain verification.
  No per-workspace sending-domain pool, reporting scope or billing view.
- **Meeting prep** — `MeetingPrepBrief` (FG7) generates a brief. No script structure,
  no objection list, no roleplay.

---

## Decisions log

(Appended as decisions are made — each entry says *why*, so the choice can be argued
with later.)

- **2026-09-16 — Additive-only migrations.** Every new column is nullable or has a
  server default, and every new table is standalone. Rationale: this branch will be
  merged into a database that already has production rows; a NOT NULL column with no
  default cannot be added to a live table without a rewrite, and the repo's existing
  migrations (0024–0052) all follow this rule.
- **2026-09-16 — New columns instead of overloading existing ones.** Feature 1's
  5-way intent taxonomy gets its own columns rather than widening `reply_category`,
  because `reply_category` already drives the FG1 reply-intelligence UI and drafts;
  changing its value set would silently break that feature's consumers.

---

## Log

- **2026-09-16 — Feature 1 done.** Migration `0053_reply_intent` (5 nullable
  columns on `inbound_replies`), `app/services/reply_intent.py`, wired into
  `reply_tasks.process_inbound_reply`, `reply_quality` on strategy analytics +
  a dedicated `/strategies/{id}/reply-quality`, `intent` block on every CRM
  reply, `ReplyQualityPanel` on the analytics page and an intent badge in the
  reply inbox. Tests: `tests/test_reply_intent.py` (36),
  `tests/test_reply_intent_migration.py` (5),
  `frontend/src/tests/replyIntent.test.ts` (21). `tsc --noEmit` clean.
  Decisions: only `interested` counts as positive (`not_now` is a future
  opportunity, not a win for *this* campaign); a failed model call leaves the
  reply unclassified rather than guessing `neutral`, because a guessed label
  silently moves a headline metric; rates are `null` not `0.0` on an empty
  denominator. Docs: `docs/features/positive-reply-classifier.md`.
- **2026-09-16 (start)** — Surveyed the codebase (models, services, API, frontend,
  test layout, migration chain head = `0052_auth_sessions`). Confirmed backend tests
  run (`pytest tests/test_compliance_rules.py` → 31 passed). Wrote this file.

## Known issues / left for Rehan

(none yet)
