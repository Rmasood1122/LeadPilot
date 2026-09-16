# F-P-T-A Scoring Engine (Part 1, Feature 2)

**Migration** `0054_fpta_scoring` · **Service** `app/services/fpta_scoring.py` ·
**UI** `frontend/src/lib/fpta.ts`, `components/leads/FptaBadges.tsx`,
`components/leads/WhyThisProspectPanel.tsx` (Feature 12)

## Why four numbers and not one

`ai_booking_likelihood` (FG1) answers "will they book?" in a single 0-100. It
is useful and unchanged. But it erases the difference between the four ways a
prospect can be wrong, and those four want **opposite actions**:

| Dimension | The question | What a low score means you should do |
|-----------|--------------|--------------------------------------|
| **Fit** | Are they the company and person this offer is for? | Don't contact. No amount of timing rescues a wrong fit. |
| **Problem** | Is there evidence they *have* the problem we solve? | The message has no hook. Go find a signal in their own words first. |
| **Timing** | Is something happening now that makes this the moment? | Contact them, but expect a "not now" — and plan the return trip (Feature 7). |
| **Access** | Can we reach this person on a channel they answer? | The other three don't matter yet. Fix the route. |

"82 fit / 20 problem" and "50 across the board" average to the same overall.
They are not the same prospect.

**Overall** = `0.30·fit + 0.30·problem + 0.20·timing + 0.20·access`. Fit and
problem weigh most because they decide whether to contact at all; timing and
access decide when and how.

## Two layers

1. **A deterministic baseline per dimension**, computed from data already held,
   with the evidence recorded as short signal strings. This is what makes the
   score explainable (Feature 12 renders exactly these strings) and what
   survives a model outage.
2. **One Claude call per batch of 10** that writes a human sentence per
   dimension and may move each baseline by **at most ±15 points**. The clamp is
   enforced in `_resolve()`, not merely requested in the prompt.

`fpta_method` records which happened: `model`, `heuristic` (the model was
unavailable or returned nothing usable) or `mixed` (it answered for some
dimensions and not others). The UI says so out loud, so terse fallback wording
is never mistaken for a weak prospect.

### What each baseline reads

- **Fit** — `seniority(title)` and `industry_match()` (both reused from
  `lead_scoring.py`, so one ICP definition drives both engines) plus headcount
  against the ICP's `company_size_ranges`.
- **Problem** — pain language and ICP keywords found in the prospect's own
  LinkedIn posts, company news, and the org description. The signal **quotes
  them**: a hook built on their sentence survives being read back to them; an
  inferred one does not.
- **Timing** — funding inside 18 months, news inside 90 days, a LinkedIn post
  inside 30 days, and change language ("we're hiring", "just joined").
- **Access** — the only dimension that can be *checked* rather than inferred,
  so it is scored from facts alone: a verified email, a LinkedIn connection, a
  phone with recorded consent, a WhatsApp opt-in.

### Nothing is invented

A dimension with no evidence scores its documented low baseline and says so —
`"No visible problem signal"`, `"No recent activity on file"` — rather than
borrowing confidence from a neighbouring dimension. A perfect fit contributes
**nothing** to the problem score; `tests/test_fpta_scoring.py` asserts exactly
that.

## Where it runs

**At enrollment.** `sequence_engine.enroll_leads()` calls
`fpta_scoring.score_for_enrollment()` *after* its commit, so a scoring failure
can never undo an enrollment that already succeeded. It scores only prospects
with `fpta_scored_at IS NULL` — re-enrolling must not silently overwrite a
score a person has already read and acted on.

Also on demand: `POST /leads/{id}/fpta/rescore`, and
`POST /strategies/{id}/leads/fpta/rescore` for a backfill (default
`only_unscored=true`).

## API

| Method | Path | Notes |
|--------|------|-------|
| `GET` | `/leads/{id}/fpta` | The four sub-scores, each with reason, evidence and weight, plus an engagement note |
| `POST` | `/leads/{id}/fpta/rescore` | Rate limited under `RATE_LIMIT_AI_ACTION` (one model call) |
| `POST` | `/strategies/{id}/leads/fpta/rescore` | Backfill; `only_unscored` defaults to true |
| `GET` | `/strategies/{id}/leads?sort=fpta` | Sorts by overall; unscored last, never as zero |
| `GET` | `/crm/leads` | Grid rows carry `fpta_overall` + the four sub-scores; `fpta_overall` is sortable server-side |

Lead list rows (`LeadOut`) and detail (`LeadDetailOut`) carry the columns
directly, so the list can show *why* a prospect ranks where it does.

## UI

- **`FptaBadges`** — the compact strip, used on the lead header, the pipeline
  kanban card and the CRM grid. Each badge carries its dimension's question as
  a tooltip, because "Fit: 82" means nothing on first reading.
- **`WhyThisProspectPanel`** — Feature 12. See
  `docs/features/why-this-prospect.md`.

## Tests

- `tests/test_fpta_scoring.py` — each baseline in isolation, dimension
  independence, the ±15 clamp, the heuristic fallback, the enrollment hook
  (including that a scoring failure does not break enrollment), and the API.
- `tests/test_fpta_scoring_migration.py` — columns match the model, all
  nullable, index present, downgrade round-trips.
- `frontend/src/tests/fpta.test.ts` — bands mirror the server's thresholds,
  "—" not "0" for unscored, headline/advice selection.
