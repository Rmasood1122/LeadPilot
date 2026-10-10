# Plan enforcement — max_sequence_steps, channels, max_leads_per_strategy

Branch `claude/plan-enforcement`. Finding: `BASELINE.md` §3 "Plan enforcement"
(HIGH, revenue, not downgraded by P0-D): three advertised limits were declared
in `app/core/plans.py` and checked nowhere.

## Behaviour (defined)

Every refusal is the existing **402** `plan_limit_exceeded` body
(`limit`, `current_plan`, `upgrade_to`, `message`). The plan is the data
owner's (`get_current_user`; in a workspace, the owner whose plan pays).

| Limit | Where | Rule |
|---|---|---|
| `max_sequence_steps` | `POST /strategies/{id}/sequences`; `POST /sequences/{id}/enroll`; `POST /sequences/{id}/approve` | steps in the sequence ≤ limit (-1 = unlimited) |
| `channels` | same three, for every channel a step sends on (`step.channel or sequence.channel`); `POST /leads/{id}/call` needs `phone` | email = plan channel `gmail` (`PLAN_CHANNEL_NAME`) |
| `max_leads_per_strategy` | `POST /strategies/{id}/leads/source` | 402 when the strategy is full; otherwise `requested_leads` = min(asked, `LEADS_MAX_PER_RUN`, room left) |
| `max_leads_per_strategy` | sourcing worker `source_leads_impl` | stops inserting at the limit, counts the rest as `plan_limit` (covers two batches at once and a downgrade between request and run) |

- Leads that count: every lead of the strategy except `DROPPED` (suppressed,
  GDPR-erased, rejected).
- Shape errors (422) are reported before the plan (402) on sequence creation.
- Re-checking at launch means a sequence built on a higher plan cannot be
  launched after a downgrade.

## Changed on purpose

- **Legacy `pro` gets all four channels** (was `gmail`, `whatsapp`). Channels
  were never enforced, so every Pro account could use all four; Pro is ranked
  above Growth (`_LINKEDIN_NETWORK_PLANS`) and "keeps exactly what it has".
  Enforcing the old list would have removed LinkedIn and phone from paying
  accounts on deploy. **Founder decision PLAN-PRO**: confirm, or pick the
  narrower list knowingly.
- `source_leads_impl` returns a 4th count, `plan_limit`.

## Existing tests updated (each to isolate what it tests, none weakened)

- `test_lead_tasks.py` (3) and `test_leads_api.py::test_deleted_lead_is_never_resourced`:
  the exact counts dict now includes `"plan_limit": 0` (still exact equality).
- `test_leads_api.py::test_max_leads_capped_by_settings`: account set to Scale
  so the 200 `LEADS_MAX_PER_RUN` cap is what is measured (Free would cap at 100).
- `test_calendly.py` (LinkedIn half of one test), `test_linkedin_channel.py`
  (1): account set to Growth before creating a LinkedIn sequence.
- `test_phone_calls.py::test_call_now`: account set to Scale.

## Residual (reported, not fixed here)

- **Sends already scheduled keep going after a downgrade.** Enforcement is at
  create and launch; the outreach worker does not re-check the plan per
  message. Stopping live campaigns on downgrade is a billing-policy decision.
- Inbox replies on WhatsApp/LinkedIn (answering a lead who wrote in) are not
  channel-gated: they are replies, not outreach.
- The web app shows the 402 `message` once #55 (`normalizeError`) is merged;
  before that it shows "402 ".
