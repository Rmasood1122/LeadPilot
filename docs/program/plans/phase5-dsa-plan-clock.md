# Gate change: sealed daily-approval tests broke when the wall clock passed 2026-10-12

Date: 2026-10-12. Branch `claude/gate-dsa-plan-clock`. One sealed test file
changes: `tests/test_daily_send_approval.py`. The change is in its LinkedIn
helper only, and no assertion is changed.

## What happened

The eval-gate went red on every master push of 2026-10-12, including master
`3650313` after #87–#92 were merged. The same trees had passed as PRs on
2026-10-11 (UTC). Two sealed tests failed:

```
tests/test_daily_send_approval.py::TestSendPath::test_email_only_approval_keeps_linkedin_deferred
  AssertionError: assert 'held_plan_limit' == 'deferred_channel_not_approved'
tests/test_daily_send_approval.py::TestSendPath::test_a_later_linkedin_approval_releases_only_linkedin
  assert 0 == 1   (released)
```

It reproduces locally on `3650313`: compliance 0.9655, suite 0.99965,
promote BLOCK.

## Root cause

`app/services/plan_holds.py` grandfathers enrollments created before
`PLAN_HOLD_EFFECTIVE_AT = 2026-10-12 00:00 UTC` (#85). The test fixtures
enroll leads with the real clock, the test user is on the **free** plan
(email only), and these two tests turn a step into a **LinkedIn** step. Until
2026-10-12 the enrollment was grandfathered, so only daily approval
decided. From 2026-10-12 the plan hold, which is correct product behaviour
(free has no LinkedIn), fires first. The tests never meant to involve the
plan.

## The change

`_as_linkedin` now also puts the strategy's owner on the Growth plan, which
includes LinkedIn (`app/core/plans.py`). This makes the test's hidden
assumption ("this account may send LinkedIn") explicit and independent of the
date. The code is not changed, and no test is weakened:

- every assertion stays the same;
- the plan-hold behaviour keeps its own tests (`tests/test_plan_downgrade_holds.py`, unchanged, passing).

`dataset_hash` covers `evals/compliance_testset.yaml` and
`evals/run_evals.py` only, so the baseline is not changed.

The only hard-coded date constant in `app/` is `PLAN_HOLD_EFFECTIVE_AT`
(`grep -rn "datetime(202[67]," app`), so no other time bomb of this kind
exists in the code.

## Evidence

| Command | Exit | Result |
|---|---|---|
| master `3650313`: `python3 evals/run_evals.py` + `promote.py` (pre-fix) | 0 / 1 | 5,637 tests; compliance 0.9655 (`test_daily_send_approval.py`: 2 of 48 failing); **BLOCK** |
| `pytest tests/test_daily_send_approval.py tests/test_daily_send_approval_e2e.py tests/test_daily_send_approval_network.py tests/test_plan_downgrade_holds.py` | 0 | 103 passed |
| this branch: `python3 evals/tools/registry_lint.py evals/registry.yaml` | 0 | OK |
| this branch: `python3 evals/run_evals.py` | 0 | 5,637 tests, pass 1.000, compliance 1.000, 929.3 s |
| this branch: `python3 evals/tools/promote.py` | 0 | **PROMOTE**, with 1 soft warning: runtime 929 s vs the 900 s ceiling, measured on a loaded 2-CPU sandbox; the baseline mean is 840 s. A soft warning does not block. |
| this branch: `python3 evals/fixtures/verify_block_fixtures.py` | 0 | all 3 hard gates fire |
