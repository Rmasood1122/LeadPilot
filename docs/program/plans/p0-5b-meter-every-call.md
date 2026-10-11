# P0-5b — meter every model call to an account

Branch `claude/p0-5b-meter-every-call`, stacked on #55 (P0-5). Residual of
P0-5: `usage_meter.note()` is a no-op outside a scope, and only the six worker
scopes (pipeline, verification, lead scoring at sourcing, meeting prep, call
analysis, `leadpilot.outreach.send`) existed. A read-only inventory found 46
model call sites; everything a user triggers on demand, every inbound reply,
follow-up and re-engagement sends and the nightly sweeps ran unscoped:
neither counted nor capped.

## Behaviour (defined)

| Purpose | Capped? | Where |
|---|---|---|
| `icp` | yes | lead sourcing (`POST /strategies/{id}/leads/source`), post-pipeline ICP binding |
| `intake` | yes (degrades) | `POST /products/{id}/past-clients` — refused extraction stores the null-pattern record with the reason; what the user typed is never lost |
| `lead_scoring` | yes (FPTA degrades to heuristic) | FPTA rescore (lead / strategy), `POST /leads/{id}/rescore`, rescore task |
| `review` | yes | `POST /sequences/{id}/review` |
| `drafting` | yes | style profile, loom script, WhatsApp template drafts, LinkedIn network drafts, follow-up email (re)generation |
| `practice` | yes | roleplay reply / finish |
| `mutation` | yes | `POST /strategies/{id}/mutate`, nightly idle sweep |
| `website` | yes | page generation task (requester id now passed to the task) |
| `meeting_summary` | yes | `generate_summary_impl` (End Meeting task, recall webhook, inline button) |
| `voice_profile` | yes | voice-profile task |
| `displacement` | yes | 12-hourly displacement scan |
| `launch` | counted | enroll / approve (review + enrolment scoring; enrolment is already committed) |
| `outreach` | counted | follow-up and re-engagement sends, AI call script |
| `reply_handling` | counted | Gmail poll, WhatsApp and Unipile webhooks, reply tasks, CRM reclassify — never starved: it drives STOP / bounce / unsubscribe |
| `support_chat` | counted | in-app help must stay reachable |

Request side (`app/api/metering.py::metered`): for a capped purpose, 429
`daily_ai_limit_reached` before any work once the day is used up; 429 when the
gateway refuses mid-request, including handlers that map model failures to
502; `refuse_after=False` where the degraded result is the designed outcome.
Queued work (voice profile, website pages, strategy rescore) is pre-checked at
the route and metered in the worker.

Also fixed:
- **Strategy budget armed for every purpose** (`owner_scope`): a strategy
  whose pipeline finished near its budget had every send render, brief and
  scoring call refused (sends retried to failure). Now pipeline and
  verification only, as `BUDGETED_PURPOSES` always said.
- **Consensus OpenAI call lost its scope** in the worker thread
  (`ThreadPoolExecutor` without `copy_context()`): GPT-4o spend was never
  recorded. And `OpenAIClient.complete` had no `check_budget`.
- Gateways log a warning for any model call outside a scope (regression
  signal in production logs).

## Not covered (reported)

- Dev-only debug routes (`/debug/*`, never mounted in production).
- Concurrent requests for one account can each pass the gate with the same
  "spent today" and overshoot by at most one call each.
- Degrade paths that commit before the 429 (sequence review stores its INFO
  finding; roleplay stores the user's line): by design, nothing the user did
  is lost.

## Tests

`tests/test_metering_coverage.py` (17): routes / impls write `api_usage` rows
with the account and purpose; 429 before work; 429 instead of 502 mid-request;
intake degrades with the reason; counted-only purposes work past the limit;
strategy budget binds pipeline + verification only; consensus OpenAI spend
lands in the pipeline scope. Pre-fix (app/ at #55): 15 failed, 2 passed.
`tests/conftest.py`: the site-generation enqueue stub accepts the new
`user_id` argument (records the same thing).
