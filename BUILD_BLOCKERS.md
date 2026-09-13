# BUILD_BLOCKERS.md

Things the overnight build could not finish for real because they need an
external credential, account or decision. Per rule #3 of the brief, each
dependency is stubbed/mocked behind configuration so the rest of the app works,
and each entry says exactly what unblocks it.

---

## 1. SMS delivery (phone verification) — needs Twilio credentials
- **State:** fully implemented against the Twilio Messages API; ships with
  `SMS_PROVIDER=console` (logs a masked notice, delivers nothing).
- **Effect until unblocked:** in any real environment users cannot receive
  codes, so post-0039 accounts cannot start outreach, buy a plan or mint share
  links. Set `REQUIRE_PHONE_VERIFICATION=false` to open the gate meanwhile.
- **To unblock:**
  1. Twilio account → a sending number (or Messaging Service) enabled for the
     countries you onboard from (US/CA/UK/AU/NZ/IE/SG first per the ICP).
  2. Set `SMS_PROVIDER=twilio`, `TWILIO_ACCOUNT_SID`, `TWILIO_AUTH_TOKEN`,
     `TWILIO_FROM_NUMBER` (E.164, or the `MG…` Messaging Service SID).
  3. UK/AU/SG sender registration rules may apply to alphanumeric/long-code
     senders — check Twilio's country guidelines before launch.
- **Never exercised against the real API** — the adapter is covered by a
  transport-level test only.

## 2. VPN / proxy detection — needs a provider key for production volume
- **State:** implemented for proxycheck.io (default) and IPQualityScore.
- **Effect until unblocked:** proxycheck works without a key up to ~1,000
  lookups/day; past that it returns "denied" and the guard fails open (logged).
- **To unblock:** create a proxycheck.io account and set
  `VPN_DETECTION_API_KEY` (or switch `VPN_DETECTION_PROVIDER=ipqualityscore`
  with that provider's key). Verify the provider's current `type` values —
  marked `TODO: verify` in `app/integrations/ip_intelligence.py`.

## 3. IP geolocation — optional key
- **State:** ipapi.co (no key) by default; ipinfo.io supported.
- **To unblock at scale:** ipapi.co's free tier is ~1k/day. For more, set
  `GEOLOCATION_PROVIDER=ipinfo` and `GEOLOCATION_API_KEY=<ipinfo token>`.

## 4. Stripe — live payments need keys (`# TODO: connect live Stripe keys`)
- **State:** both billing models are implemented end to end against Stripe's
  REST API (Checkout in subscription and setup mode, per-meeting invoices,
  cancellation, signed webhooks). With no key the app runs in **stub mode**:
  plans activate locally and meetings are marked charged, all with
  `is_stub=true`, and every stub path logs `TODO: connect live Stripe keys`.
- **Effect until unblocked:** nobody is actually charged. Stub rows are
  flagged so they can never be mistaken for revenue.
- **To unblock:**
  1. Stripe account → Developers → API keys → set `STRIPE_SECRET_KEY`
     (`sk_live_…`; use `sk_test_…` first).
  2. Developers → Webhooks → add endpoint `https://<api>/webhooks/stripe`
     with events `checkout.session.completed`,
     `customer.subscription.created`, `customer.subscription.updated`,
     `customer.subscription.deleted`, `invoice.paid`,
     `invoice.payment_failed` → set `STRIPE_WEBHOOK_SECRET` (`whsec_…`).
  3. Optional: create recurring Prices for the four tiers and set
     `STRIPE_PRICE_STARTER/GROWTH/SCALE/ENTERPRISE` (otherwise checkout sends
     inline prices from `app/core/billing_catalog.py`).
  4. Test with `stripe listen --forward-to localhost:8000/webhooks/stripe`.
- **Existing stub rows:** before going live, decide whether to cancel or
  convert any `billing_subscriptions.is_stub = true` rows.
- **Never exercised against the real API** — covered by transport-level
  recorders and real signature verification only.
