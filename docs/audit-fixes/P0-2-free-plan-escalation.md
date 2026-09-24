# P0-2 — Free Plan Escalation: Fix Report

- **Status:** FIXED (production scope)
- **Date:** 2026-09-24
- **Commit:** 4f5fd4c on feature/8-new-features
- **Audit reference:** RED FLAG 2 (RF-2) in audit_findings.md

## The bug — corrected framing
Not a missing check. "Stub mode" is deliberate: with STRIPE_SECRET_KEY
empty, billing_stub_mode (app/config.py) makes start_checkout
(app/services/billing.py) activate any chosen tier locally with
is_stub=True and no payment — documented in BUILD_BLOCKERS.md §4 and
required by existing tests. It exists for development and test. Production
runs with the key empty, so any signed-in user with a verified phone could
take Enterprise for free.

## The fix (Option A — block in production only)
In POST /billing/checkout (app/api/billing.py): when billing_stub_mode is
on AND production_guard.is_production(APP_ENV), return 503 "payments are
not configured; plans cannot be changed right now" before anything is
written. Dev/test stub mode is unchanged; the existing TestStubCheckout
tests are untouched and still green.

## Plan-mutation route inventory
- POST /billing/checkout — now guarded in production.
- POST /billing/cancel — unguarded, deliberately: only moves a user to free.
- POST /webhooks/stripe — already 503 without STRIPE_WEBHOOK_SECRET;
  every event's signature is checked. Unchanged.
- POST /admin/users/{id}/plan — admin-only override, not Stripe-tied.
  Unchanged.

## Verification
- Red: 3 of 5 new tests failed with `assert 200 == 503` — a free stub
  Enterprise (and pay-per-meeting) plan granted in production, no key and
  whitespace-only key.
- Green: 5/5 in tests/test_checkout_requires_stripe.py, asserting
  users.plan stays FREE and no subscription row exists; the 13-module
  billing/plan sweep is green.

## Left open, by design
- No production_guard boot check yet — production runs with the key empty
  today, so a boot check would stop the next deploy. Add it the day the
  real Stripe key is set.
- Existing is_stub=true subscription rows keep their plans. Needs a
  one-time production audit and a revoke/keep decision.
- Stub mode still runs on any non-production APP_ENV — a staging server
  open to real users would still hand out plans.
