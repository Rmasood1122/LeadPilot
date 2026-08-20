# ClientHunter Enterprise — Launch Checklist

Work through this from top to bottom before going live. Every item has a verification step.

---

## 1. Infrastructure

- [ ] PostgreSQL 16 provisioned and accessible (`DATABASE_URL` set)
- [ ] Redis provisioned and accessible (`REDIS_URL` set)
- [ ] All Celery workers running: `celery -A app.workers.celery_app worker`
- [ ] Celery Beat running: `celery -A app.workers.celery_app beat`
- [ ] Verify Beat schedule includes nightly aggregation at `PLAYBOOK_AGGREGATION_UTC_HOUR`

**Verify:** `GET /health` returns `{"status": "ok"}` from all three services.

---

## 2. Migrations

- [ ] `alembic upgrade head` runs clean (all 11 migrations pass)
- [ ] Confirm `subject_line_patterns` table exists
- [ ] Confirm `webhook_targets` and `webhook_deliveries` tables exist
- [ ] Confirm `users.onboarding_state` column exists (JSONB)
- [ ] Confirm `messages.personalization_score` column exists
- [ ] Confirm `strategies.personalization_correlation` column exists
- [ ] Confirm `playbook_scores` has `decay_half_life_days`, `effective_sample_size`, `trend` columns

**Verify:** `alembic current` shows `0011_m8c5 (head)`.

---

## 3. Secrets and environment

- [ ] `SECRET_KEY` is a cryptographically random string (not the default)
- [ ] `ENCRYPTION_KEY` is a valid Fernet key (`python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"`)
- [ ] `ANTHROPIC_API_KEY` set and has credits
- [ ] `GMAIL_CLIENT_ID` + `GMAIL_CLIENT_SECRET` set; redirect URI matches Google Cloud Console
- [ ] `WHATSAPP_PHONE_NUMBER_ID` + `WHATSAPP_ACCESS_TOKEN` + `WHATSAPP_APP_SECRET` set
- [ ] `CALENDLY_WEBHOOK_SECRET` set
- [ ] `APOLLO_API_KEY` + `HUNTER_API_KEY` set
- [ ] `FIREBASE_PROJECT_ID` + `FIREBASE_CREDENTIALS_JSON` set (for FCM push)
- [ ] All RATE_LIMIT_* variables reviewed and acceptable for your user base

**Verify:** `GET /admin/circuit-breakers` shows all providers CLOSED.

---

## 4. Compliance (non-negotiable)

- [ ] Gmail warm-up schedule configured (`GMAIL_WARMUP_START_DAILY=20`, `GMAIL_DAILY_SEND_CAP=500`)
- [ ] Bounce pause threshold set (`GMAIL_BOUNCE_PAUSE_THRESHOLD=0.03`)
- [ ] Suppression list endpoint tested: unsubscribe link leads to instant suppression
- [ ] WhatsApp cold-contact templates approved by Meta before first campaign
- [ ] At least one test lead verified that unsubscribe removes them from all future sends

---

## 5. Integration smoke tests

- [ ] Gmail OAuth flow completes for a test account; `GET /integrations/gmail/status` returns connected
- [ ] Apollo search returns at least one lead for a simple query
- [ ] Hunter verifies a known-good email as `deliverable`
- [ ] Calendly webhook test event received at `POST /webhooks/calendly` and processed
- [ ] WhatsApp test message sent and received in Meta developer console

---

## 6. Learning loop (M8-C1/C2/C3)

- [ ] Run `POST /admin/playbook/recompute` → returns `{"status": "triggered"}`
- [ ] After 60s check: `GET /admin/playbook/scores` returns a result (may be empty on first run — that's OK)
- [ ] Confirm `learning_loop:last_run` Redis key is set after nightly job first fires
- [ ] `GET /playbook/similar-strategies?query=SaaS+lead+generation` returns without error

---

## 7. Advanced learning (M8-C4) ✦ NEW

- [ ] `GET /playbook/send-times?channel=gmail` returns without error (fallback_used=true on first run — expected)
- [ ] `GET /playbook/subject-patterns?channel=gmail` returns without error (empty list on first run — expected)
- [ ] After a strategy with >2 variants exists and outcomes are recorded: `GET /strategies/{id}/mv-results` returns per_variant_stats
- [ ] `GET /strategies/{id}/personalization-stats` returns `health_indicator` without error
- [ ] Confirm `personalization_score` is written to the messages table after a test send

---

## 8. Production launch features (M8-C5) ✦ NEW

- [ ] Rate limits fire correctly: POST more than `RATE_LIMIT_STRATEGIES` strategies in one hour → `429` with `Retry-After` header
- [ ] Free-plan user attempting multi_variate endpoint → `402` with `"error": "plan_limit_exceeded"`
- [ ] Register a test webhook target: `POST /webhooks/targets` with a requestbin URL → `{"status": "created"}`
- [ ] Trigger a `meeting_booked` event → confirm delivery arrives at requestbin within 30s
- [ ] If requestbin is offline: confirm retry is scheduled (check `GET /admin/webhook-deliveries`)
- [ ] `GET /onboarding/state` for a new user → shows 0 steps complete, `product_created` as next
- [ ] After creating a product: `GET /onboarding/state` → shows `product_created` complete
- [ ] Admin: `GET /admin/rate-limits/{user_id}` returns current counters
- [ ] Admin: `POST /admin/users/{id}/plan` with `{"plan": "starter"}` → updates plan + writes audit log

---

## 9. Frontend + Mobile

- [ ] `npm run build` in `frontend/` completes with no TypeScript errors
- [ ] Login → Dashboard: OnboardingChecklist visible for new user
- [ ] Analytics page: SendTimeCard and SubjectLineCard render (even if "No data yet")
- [ ] Settings page: PlanCard shows current plan limits
- [ ] Campaign page: PersonalizationHealth and MultiVariateResults sections visible
- [ ] Android APK installs and loads; push notification received on test device
- [ ] Theme engine: custom color → live preview → save → reload → theme persists

---

## 10. Performance

- [ ] Run `python scripts/benchmark.py` → all rows PASS or WARN (no FAIL)
- [ ] p99 API latency under 1s under 50 concurrent users
- [ ] Nightly aggregation completes in under 30s for 10k outcomes

---

## 11. SDK / PyPI

- [ ] `pip install clienthunter` (TestPyPI) in a fresh venv → `clienthunter --help` works
- [ ] `clienthunter serve` starts the backend (Docker must be available)
- [ ] `clienthunter status` shows connected integrations

---

## Final gate

All boxes checked? You're live.

If any box can't be checked, document the gap and set a deadline. Do not skip compliance items (#4) — they are non-negotiable.
