# Meeting Prep & Training (Part 2)

**Migration** `0064_meeting_practice` ·
**Services** `app/services/meeting_practice.py`, `app/services/roleplay.py` ·
**API** `app/api/practice.py` ·
**UI** `frontend/src/lib/practice.ts`, `components/leads/CallScriptPanel.tsx`,
`components/leads/RoleplayPanel.tsx`

Builds on the existing FG7 meeting-prep brief (`MeetingPrepBrief`,
`app/services/meeting_prep.py`), which already generated a brief automatically
when a meeting was booked. This adds the three things it did not have: the
F-P-T-A signals, an **editable** script, and somewhere to **practise**.

---

## 1. The brief now reads the F-P-T-A signals

`collect_context` carries a `fpta` block — the four sub-scores with the
**evidence each was built from** (Part 1 Feature 2) — and the prompt rule for
`pain_points` now says to cite that evidence where it exists.

That is the difference between *"they probably have an inspection backlog"* and
*"they said they were drowning in inspections"*. The prospect was ranked on
those signals; the brief reads the same ones rather than forming a second,
conflicting opinion.

An unscored prospect renders as **"(none on record)"**, not as a zero — "not
scored" and "scored badly" are different facts.

## 2. The call script, which the seller owns

`script_json` holds `{opening, discovery[], objections[], close, notes}`.

**Its own column, not another key in `sections_json`.** That blob is model
output, rewritten whenever "Regenerate" is pressed. The script is the
seller's — and *an edit a regeneration silently overwrites is an edit nobody
makes twice.* `ensure_script()` seeds it **only while it is empty** and never
overwrites; a test asserts that regenerating the brief leaves an edit intact.

Seeding is **not a second model call**: everything the opening, the questions
and the objection lines need was generated for the brief already, and asking
again would produce a script that disagrees with the page above it. The close
is built from the brief's own next step, so it is a sentence someone can
actually say rather than *"ask for the next step"*.

Until a person touches it the UI labels it **Suggested** — generated text must
never be mistaken for something that was approved.

## 3. The pre-meeting checklist

`readiness()` returns four items — brief generated, script reviewed, objections
prepared (≥ 3), practised — each with a detail line, plus a headline that says
how long there is.

**Derived every time, never stored.** Every item is a fact that already exists
somewhere, and a stored checklist goes stale and then lies.

**Practice only blocks when it was asked for.** `practice_required` is per
*meeting*, default off: making every call require a rehearsal is how a checklist
becomes something people click through without reading, and the call worth
rehearsing is the one that matters.

## 4. The roleplay

The AI plays the **prospect** — their company, the pains from the brief, and
**the objections they have actually raised**, which outrank the predicted ones
because a rehearsal against real pushback is worth more than one against a
guess.

Three difficulties (`easy` / `realistic` / `hostile`), each with a documented
behaviour note.

### The prospect never becomes a coach

The single most common failure of a roleplay feature is an AI that breaks
character to be encouraging — *"Great question! As a fire-safety director, I
would say…"*. The system prompt forbids it, and `_clean_reply` strips the
give-aways if it happens anyway. **A prospect who is nicer than the real one
teaches the wrong lesson.**

### A failed turn never loses what the seller said

`reply()` saves the seller's line **before** asking the model. A model outage
returns `status: "failed"` with the line already stored — losing what a person
said because the other side failed to answer is the one thing a practice tool
must not do.

### Bounded

`MAX_TURNS = 40`. A rehearsal is not a novel, and an unbounded roleplay is an
unbounded model bill. The UI warns four turns out so the seller starts closing.

## 5. The feedback

Five scores (overall, discovery, objection handling, tone, close), what went
well, what to improve, tone and pacing notes, **the objections that were not
handled**, and `one_thing` — the single change that would most improve the next
call, which the UI shows **first**. A review that opens with five compliments is
a review nobody acts on.

**A session with fewer than two of the seller's own lines is recorded as
`abandoned` and not scored.** Scoring a conversation that never happened
produces a number that means nothing and then pollutes the improvement chart.

Scores are **columns**, not keys inside `feedback_json`, because "am I getting
better?" is a chart across sessions and extracting a number from JSON is spelled
differently on SQLite and PostgreSQL. The trend is sorted **ascending
explicitly** (with `created_at` as a tiebreak) rather than by reversing the
display order — several sessions in one sitting share a `started_at` to the
second, and an unstable sort would draw the improvement line backwards.

## 6. Standalone *and* pre-meeting

`lead_id` is **optional** on `POST /practice/sessions`. The standalone practice
tool and the pre-meeting step are one code path rather than two that can drift,
and the panel is rendered even when a lead has **no** brief — rehearsing a
prospect you have not booked yet is a legitimate thing to want.

## Schema notes

- **Turns are rows, not a JSON array.** A roleplay is appended to one line at a
  time by a live UI; a JSON array means read-modify-write per turn, which loses
  a line whenever two requests overlap. `UNIQUE(session_id, turn_no)` turns a
  duplicated submit into a conflict rather than a duplicated line.
- **`lead_id` and `brief_id` are `SET NULL`.** A practice history is about the
  *seller*; losing the prospect they practised against must not erase the
  evidence that they improved.

## API

| Method | Path |
|--------|------|
| `GET` `PUT` | `/meeting-prep/{brief_id}/script` |
| `GET` | `/meeting-prep/{brief_id}/readiness` |
| `POST` | `/meeting-prep/{brief_id}/practice-required` |
| `POST` | `/practice/sessions` (`lead_id` optional) |
| `GET` | `/practice/sessions` (history + trend) |
| `GET` | `/practice/sessions/{id}` |
| `POST` | `/practice/sessions/{id}/reply` |
| `POST` | `/practice/sessions/{id}/finish` |

Roleplay calls are rate limited under `RATE_LIMIT_AI_ACTION` — every turn is a
model call billed to the deployment's key.

## Tests

`tests/test_practice.py` (51) — F-P-T-A reaching the prompt, seeding without a
model call, a regeneration not overwriting an edit, the checklist's blocking
rules, real objections outranking predicted ones, coaching being stripped, a
failed turn keeping the seller's line, the turn bound, unscored short sessions,
clamped scores, and the trend's order. `tests/test_practice_migration.py` (10).
`frontend/src/tests/practice.test.ts` (27).
