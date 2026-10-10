# P0-5 — per-account daily AI spend cap

Branch `claude/p0-5-account-spend-cap`. Finding: `BASELINE.md` §3 row "P0-5 AI
spend cap" — FIXED per strategy, **OPEN per account**. Not downgraded by P0-D.

## Behaviour (defined)

1. Every plan in `app/core/plans.py` has a finite `max_ai_spend_usd_per_day`.
   Values are placeholders until the founders decide (`DECISIONS.md` P0-5-CAPS):
   free 10, starter 25, growth 60, pay_per_meeting 60, scale 150, pro 150,
   enterprise 400 (USD per UTC day).
2. The day is 00:00–24:00 UTC. "Spent today" is the sum of
   `api_usage.cost_micros` for the account since 00:00 UTC, **all purposes**
   (`usage_meter.account_spent_today_micros`, filtered by the account's own id).
3. Inside a `usage_meter` scope whose purpose is `pipeline`, `verification` or
   `lead_scoring` and whose account is known, `check_budget()` refuses a model
   call whose worst-case price would take the account past its cap
   (`AccountBudgetExceededError`, a `BudgetExceededError`). Nothing is spent on
   the refused call. The existing per-strategy budget (F-AI-01) still applies;
   the stricter of the two wins.
4. A refused pipeline/verification stops the same way a strategy budget stop
   does: no retry, strategy → `BUDGET_EXHAUSTED`, error text names the daily
   limit, the plan and the 00:00 UTC reset. The strategy is resumable.
5. `POST /products/{id}/strategies` and `POST /strategies/{id}/resume` answer
   **429** `{"error":"daily_ai_limit_reached", plan, limit_usd,
   spent_today_usd, message}` once the day's cap is used up, and enqueue
   nothing.
6. The frontend shows that `message` (and the existing 402 plan-limit
   `message`) instead of the bare status line (`normalizeError`).

Not stopped mid-flight on purpose: `outreach`, `meeting_prep`,
`call_analysis` scopes. Their spend counts toward the day, but stopping a send
halfway leaves a claimed-but-unsent message, and a booked meeting without its
brief; their spend is small next to a pipeline.

## Residual (reported, not fixed here)

- **P0-5b — calls outside any scope are not metered at all.** `note()` is a
  no-op outside a scope, so support chat, the website builder, reply
  classifiers and other request-path model calls write no `api_usage` row and
  are neither counted nor capped. 34 modules import the Anthropic client; only
  the 6 worker scopes above attribute spend. Needs its own PR: wrap each
  request-path call site in a scope with the caller's `user_id`.
- `BASELINE.md` §12 item 3 proposed a **monthly** cap. This PR uses a **daily**
  cap: it bounds the worst-case burn rate (the audit's $398/day), and a monthly
  ceiling is at most 31 × the daily one. Founders confirm or ask for a monthly
  cap as well (P0-5-CAPS).
- Two scopes for the same account that open at the same moment each read the
  same "spent today" and can together exceed the cap by at most one scope's
  spend. Bounded by the existing 2/hour strategy rate limit.
- Strategy creation is refused only once the cap is fully used; a run started
  with $0.10 left stops at its first expensive call (by design, no spend past
  the cap).

## Tests

- `tests/test_account_spend_cap.py` (new): plans, gate (fits / refused /
  in-scope spend / yesterday excluded / all purposes count / other account
  excluded / outreach-meeting-call not stopped / lead scoring stopped / stricter
  wins / permanent error), pipeline task stops cleanly without passing the cap,
  API 429 on create and resume, create allowed below the cap.
- `tests/test_strategy_budget.py::test_no_budget_means_no_gate`: isolates the
  strategy gate (account cap switched off), then asserts the same call **is**
  refused once the account cap is on. Strengthened, not weakened.
- `frontend/src/tests/api-client.test.ts`: structured detail → its message.

Pre-fix failing state: on `origin/master` (afcccd3) the new backend tests fail
at import/attribute (`plans.PLANS[...]["max_ai_spend_usd_per_day"]` missing,
`usage_meter.AccountBudgetExceededError` missing); the frontend test failed
with `err.detail === "429 "` (run recorded in the PR).
