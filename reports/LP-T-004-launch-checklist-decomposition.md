# LP-T-004: LAUNCH_CHECKLIST Decomposition Report

**Produced by:** Claude Code
**Date:** 2026-09-30
**Repo HEAD:** f73c930c910ec4f11626216a88738a4f0244a9e6 (master)
**Scope:** LAUNCH_CHECKLIST.md (62 items, 12 sections) + docs/ checklists (PLAY_STORE_CHECKLIST.md, STORE_ASSETS.md, DEPLOY.md, README_M7_CHUNKS_2_3.md, backup/backup-procedure.md; FIREBASE_SETUP_CHECKLIST.md and compliance.md characterized; PRODUCTION_READINESS.md cross-referenced only — already GAP-007)
**Read-only task:** no source, test, or checklist file modified. This report is the only artifact.

Mapping vocabulary: `EXISTING → GAP-xxx` | `NEW → GAP-1xx` (definition in Part C) | `DUP of <ref>`.
Severity and evidence requirement for every NEW mapping are defined once per proposed gap in Part C and apply to each item mapped to it; item-specific evidence deltas are noted inline.

---

## PART A — LAUNCH_CHECKLIST.md (62 items)

### Section 1 — Infrastructure (5 items)
| # | Verbatim item | Mapping | Rationale / notes |
|---|---|---|---|
| 1.1 | PostgreSQL 16 provisioned and accessible (`DATABASE_URL` set) | NEW → GAP-105 | Runtime environment provisioning; no environment has been stood up or verified by this project. |
| 1.2 | Redis provisioned and accessible (`REDIS_URL` set) | NEW → GAP-105 | Same class as 1.1. |
| 1.3 | All Celery workers running: `celery -A app.workers.celery_app worker` | NEW → GAP-105 | Worker runtime verification; depends on 1.1/1.2. |
| 1.4 | Celery Beat running: `celery -A app.workers.celery_app beat` | NEW → GAP-105 | Note: `celerybeat-schedule.*` state files are committed at repo root — hygiene sub-item recorded under GAP-106 staleness sweep. |
| 1.5 | Verify Beat schedule includes nightly aggregation at `PLAYBOOK_AGGREGATION_UTC_HOUR` | NEW → GAP-105 | Config-level verification once Beat runs. |
| — | Section verify step: `GET /health` returns ok from all three services | NEW → GAP-105 | The section's acceptance evidence; counted with the section, not as a 63rd item. |

### Section 2 — Migrations (7 items)
| # | Verbatim item | Mapping | Rationale / notes |
|---|---|---|---|
| 2.1 | `alembic upgrade head` runs clean (all 11 migrations pass) | EXISTING → GAP-103 | Exactly REQ-103's migration step. **Item text is stale:** repo has 49 migration files (0001…0047), not 11 → GAP-106. Executing "as written" would mis-verify. |
| 2.2 | Confirm `subject_line_patterns` table exists | EXISTING → GAP-103 | Post-migration schema assertion; fold into REQ-103 evidence as explicit checks. |
| 2.3 | Confirm `webhook_targets` and `webhook_deliveries` tables exist | EXISTING → GAP-103 | Same. |
| 2.4 | Confirm `users.onboarding_state` column exists (JSONB) | EXISTING → GAP-103 | Same. |
| 2.5 | Confirm `messages.personalization_score` column exists | EXISTING → GAP-103 | Same. |
| 2.6 | Confirm `strategies.personalization_correlation` column exists | EXISTING → GAP-103 | Same. |
| 2.7 | Confirm `playbook_scores` has `decay_half_life_days`, `effective_sample_size`, `trend` columns | EXISTING → GAP-103 | Same. |
| — | Section verify step: `alembic current` shows `0011_m8c5 (head)` | — | **STALE** (head is now in the 0047 range) → GAP-106. Must be corrected before the section is executable. |

### Section 3 — Secrets and environment (9 items)
| # | Verbatim item | Mapping | Rationale / notes |
|---|---|---|---|
| 3.1 | `SECRET_KEY` is a cryptographically random string (not the default) | EXISTING → GAP-102 | Secrets-conformance operational check; add to REQ-102 evidence (deployed-env check, value never recorded). |
| 3.2 | `ENCRYPTION_KEY` is a valid Fernet key (generation command given) | EXISTING → GAP-102 | Same. |
| 3.3 | `ANTHROPIC_API_KEY` set and has credits | EXISTING → GAP-007 | Identical dependency already registered from docs/PRODUCTION_READINESS.md (BLOCKED external). |
| 3.4 | `GMAIL_CLIENT_ID` + `GMAIL_CLIENT_SECRET` set; redirect URI matches Google Cloud Console | NEW → GAP-107 | Provider commissioning beyond GAP-004's set. BLOCKED external (founder Google Cloud config). |
| 3.5 | `WHATSAPP_PHONE_NUMBER_ID` + `WHATSAPP_ACCESS_TOKEN` + `WHATSAPP_APP_SECRET` set | NEW → GAP-107 | BLOCKED external (Meta app). |
| 3.6 | `CALENDLY_WEBHOOK_SECRET` set | NEW → GAP-107 | BLOCKED external (Calendly account). |
| 3.7 | `APOLLO_API_KEY` + `HUNTER_API_KEY` set | NEW → GAP-107 | BLOCKED external (paid data providers). |
| 3.8 | `FIREBASE_PROJECT_ID` + `FIREBASE_CREDENTIALS_JSON` set (for FCM push) | NEW → GAP-107 | BLOCKED external; setup procedure exists: docs/FIREBASE_SETUP_CHECKLIST.md (24 console steps, characterized in Part B, not itemized — pure external console procedure backing this key). |
| 3.9 | All RATE_LIMIT_* variables reviewed and acceptable for your user base | NEW → GAP-108 | Config review/decision, not a credential; founder judgment with recorded values. |
| — | Section verify step: `GET /admin/circuit-breakers` shows all providers CLOSED | NEW → GAP-107 | Aggregate acceptance evidence once keys exist + environment runs (dep: GAP-105). |

### Section 4 — Compliance (non-negotiable) (5 items) — ALL CRITICAL
| # | Verbatim item | Mapping | Rationale / notes |
|---|---|---|---|
| 4.1 | Gmail warm-up schedule configured (`GMAIL_WARMUP_START_DAILY=20`, `GMAIL_DAILY_SEND_CAP=500`) | NEW → GAP-109 | Live configuration of a legal-adjacent control. Enforcement code is offline-tested (sealed set, GAP-001); the *live configuration and behavior* have never been verified. |
| 4.2 | Bounce pause threshold set (`GMAIL_BOUNCE_PAUSE_THRESHOLD=0.03`) | NEW → GAP-109 | Same class. |
| 4.3 | Suppression list endpoint tested: unsubscribe link leads to instant suppression | NEW → GAP-109 | Live E2E of the exact surface the sealed tests guard offline; the STATUS doc's guarantee is offline-only. |
| 4.4 | WhatsApp cold-contact templates approved by Meta before first campaign | NEW → GAP-109 | BLOCKED external (Meta review). Legal prerequisite to any WhatsApp campaign. |
| 4.5 | At least one test lead verified that unsubscribe removes them from all future sends | NEW → GAP-109 | Live E2E across channels; cross-ref docs/compliance.md (enforcement architecture reference — characterized in Part B, no items). |

### Section 5 — Integration smoke tests (5 items)
| # | Verbatim item | Mapping | Rationale / notes |
|---|---|---|---|
| 5.1 | Gmail OAuth flow completes for a test account; `GET /integrations/gmail/status` returns connected | NEW → GAP-107 | The smoke half of 3.4. |
| 5.2 | Apollo search returns at least one lead for a simple query | NEW → GAP-107 | Smoke half of 3.7. |
| 5.3 | Hunter verifies a known-good email as `deliverable` | NEW → GAP-107 | Smoke half of 3.7. |
| 5.4 | Calendly webhook test event received at `POST /webhooks/calendly` and processed | NEW → GAP-107 | Smoke half of 3.6; also exercises webhook HMAC path (cross-ref GAP-102 audit scope). |
| 5.5 | WhatsApp test message sent and received in Meta developer console | NEW → GAP-107 | Smoke half of 3.5; sequencing dep on 4.4 for real campaigns. |

### Section 6 — Learning loop (M8-C1/C2/C3) (4 items)
| # | Verbatim item | Mapping | Rationale / notes |
|---|---|---|---|
| 6.1 | Run `POST /admin/playbook/recompute` → returns `{"status": "triggered"}` | NEW → GAP-110 | Feature runtime verification; dep GAP-105. |
| 6.2 | After 60s check: `GET /admin/playbook/scores` returns a result (may be empty on first run) | NEW → GAP-110 | Same. |
| 6.3 | Confirm `learning_loop:last_run` Redis key is set after nightly job first fires | NEW → GAP-110 | Same; also exercises Beat schedule (dep 1.4/1.5). |
| 6.4 | `GET /playbook/similar-strategies?query=SaaS+lead+generation` returns without error | NEW → GAP-110 | Same. |

### Section 7 — Advanced learning (M8-C4) (5 items)
| # | Verbatim item | Mapping | Rationale / notes |
|---|---|---|---|
| 7.1 | `GET /playbook/send-times?channel=gmail` returns without error (fallback_used=true on first run — expected) | NEW → GAP-110 | Same verification class as §6; grouped. |
| 7.2 | `GET /playbook/subject-patterns?channel=gmail` returns without error (empty list on first run — expected) | NEW → GAP-110 | Same. |
| 7.3 | After a strategy with >2 variants exists and outcomes are recorded: `GET /strategies/{id}/mv-results` returns per_variant_stats | NEW → GAP-110 | Requires seeded live data; note sequencing after §5/§8 basics. |
| 7.4 | `GET /strategies/{id}/personalization-stats` returns `health_indicator` without error | NEW → GAP-110 | Same. |
| 7.5 | Confirm `personalization_score` is written to the messages table after a test send | NEW → GAP-110 | Requires a real test send (dep GAP-107 Gmail). |

### Section 8 — Production launch features (M8-C5) (9 items)
| # | Verbatim item | Mapping | Rationale / notes |
|---|---|---|---|
| 8.1 | Rate limits fire correctly: POST more than `RATE_LIMIT_STRATEGIES` strategies in one hour → `429` with `Retry-After` header | NEW → GAP-111 | Abuse-control runtime verification. |
| 8.2 | Free-plan user attempting multi_variate endpoint → `402` with `"error": "plan_limit_exceeded"` | NEW → GAP-111 | **Financial surface** (plan gating) — drives the gap's MAJOR floor. |
| 8.3 | Register a test webhook target: `POST /webhooks/targets` with a requestbin URL → `{"status": "created"}` | NEW → GAP-111 | Outbound webhook feature verification. |
| 8.4 | Trigger a `meeting_booked` event → confirm delivery arrives at requestbin within 30s | NEW → GAP-111 | Same. |
| 8.5 | If requestbin is offline: confirm retry is scheduled (check `GET /admin/webhook-deliveries`) | NEW → GAP-111 | Reliability path. |
| 8.6 | `GET /onboarding/state` for a new user → shows 0 steps complete, `product_created` as next | NEW → GAP-111 | Onboarding runtime verification. |
| 8.7 | After creating a product: `GET /onboarding/state` → shows `product_created` complete | NEW → GAP-111 | Same. |
| 8.8 | Admin: `GET /admin/rate-limits/{user_id}` returns current counters | NEW → GAP-111 | Admin surface; cross-ref GAP-101 audit (admin authz). |
| 8.9 | Admin: `POST /admin/users/{id}/plan` with `{"plan": "starter"}` → updates plan + writes audit log | NEW → GAP-111 | Financial + audit-trail surface; cross-ref GAP-101/102. |

### Section 9 — Frontend + Mobile (7 items)
| # | Verbatim item | Mapping | Rationale / notes |
|---|---|---|---|
| 9.1 | `npm run build` in `frontend/` completes with no TypeScript errors | NEW → GAP-112 | **Executable now by Claude Code without credentials** — flagged as the cheapest next verification in this group. |
| 9.2 | Login → Dashboard: OnboardingChecklist visible for new user | NEW → GAP-112 | UI QA; dep GAP-105 backend. |
| 9.3 | Analytics page: SendTimeCard and SubjectLineCard render (even if "No data yet") | NEW → GAP-112 | UI QA. |
| 9.4 | Settings page: PlanCard shows current plan limits | NEW → GAP-112 | UI QA. |
| 9.5 | Campaign page: PersonalizationHealth and MultiVariateResults sections visible | NEW → GAP-112 | UI QA. |
| 9.6 | Android APK installs and loads; push notification received on test device | NEW → GAP-112 | **Conditional applicability** — depends on founder decision that Android is in v1 scope (see UNCERTAIN flags); overlaps mobile-release track GAP-114 (Part B). |
| 9.7 | Theme engine: custom color → live preview → save → reload → theme persists | NEW → GAP-112 | UI QA. |

### Section 10 — Performance (3 items)
| # | Verbatim item | Mapping | Rationale / notes |
|---|---|---|---|
| 10.1 | Run `python scripts/benchmark.py` → all rows PASS or WARN (no FAIL) | NEW → GAP-113 | Script exists at `scripts/benchmark.py` (verified); needs running environment. |
| 10.2 | p99 API latency under 1s under 50 concurrent users | NEW → GAP-113 | Load verification; dep GAP-105. |
| 10.3 | Nightly aggregation completes in under 30s for 10k outcomes | NEW → GAP-113 | Dep §6 loop + seeded data. |

### Section 11 — SDK / PyPI (3 items)
| # | Verbatim item | Mapping | Rationale / notes |
|---|---|---|---|
| 11.1 | `pip install clienthunter` (TestPyPI) in a fresh venv → `clienthunter --help` works | NEW → GAP-115 | **Conditional applicability** — SDK-in-v1 is a scope decision (UNCERTAIN flags). pypi-release workflow exists at HEAD. |
| 11.2 | `clienthunter serve` starts the backend (Docker must be available) | NEW → GAP-115 | Same; dep GAP-103 docker build. |
| 11.3 | `clienthunter status` shows connected integrations | NEW → GAP-115 | Same; dep GAP-107. |

### Final gate section
No checkbox items. Its rule "Do not skip compliance items (#4) — they are non-negotiable" is honored: all §4 items map to GAP-109 at CRITICAL.

---

## PART B — docs/ checklists supplement (50 items net of already-ingested)

**Characterized, no items to map:** `docs/PRODUCTION_READINESS.md` (= GAP-007, cross-ref only). `docs/compliance.md` (prose reference describing compliance enforcement architecture — no checkboxes; used as rationale source for §4/GAP-109). `docs/FIREBASE_SETUP_CHECKLIST.md` (24 numbered console steps, all external user actions, no checkboxes — the setup procedure behind item 3.8/GAP-107; contains two "TODO: verify against current console/AGP" staleness notes → GAP-106 sweep).

### docs/PLAY_STORE_CHECKLIST.md (19 items)
| Line | Verbatim item | Mapping |
|---|---|---|
| 11 | Signed AAB built and downloaded from GitHub Actions artifact | NEW → GAP-114 |
| 12 | Privacy policy live at `https://app.clienthunter.com/privacy` | NEW → GAP-114 (legal-adjacent: privacy policy must be live — also required by stores) |
| 13 | `assetlinks.json` deployed with correct SHA-256 fingerprint (see SIGNING.md Step 6) | NEW → GAP-114 |
| 14 | All store assets prepared (see STORE_ASSETS.md) | NEW → GAP-114 |
| 15 | Google Play Developer account ($25 one-time fee) | NEW → GAP-114 (BLOCKED external: account) |
| 35 | App name: `ClientHunter Enterprise` | NEW → GAP-114 |
| 36 | Short description (≤80 chars, see STORE_ASSETS.md) | NEW → GAP-114 |
| 37 | Full description (≤4000 chars) | NEW → GAP-114 |
| 38 | App icon: upload 512×512 PNG | NEW → GAP-114 |
| 39 | Feature graphic: upload 1024×500 JPG/PNG | NEW → GAP-114 |
| 40 | Phone screenshots: upload at least 2 | NEW → GAP-114 |
| 41 | Category: **Business** | NEW → GAP-114 |
| 42 | Tags (optional) | NEW → GAP-114 (INFORMATIONAL sub-item) |
| 43 | Contact details: email, website, privacy policy URL | NEW → GAP-114 |
| 132 | App installs from Play Store internal testing link | NEW → GAP-114 |
| 133 | Login works against the production backend | NEW → GAP-114 (dep GAP-105) |
| 134 | Deep links work (`clienthunter:///strategies/1` opens the app) | NEW → GAP-114 |
| 135 | Push notification received (trigger one from the backend) | NEW → GAP-114 (dep GAP-107 Firebase) |
| 136 | Back button behaviour correct | NEW → GAP-114 |

### docs/STORE_ASSETS.md (10 items) — all DUP of PLAY_STORE block 35–43 + line 12
| Lines 123–132 | icon / feature graphic / ≥2 screenshots / title / short desc / full desc / privacy URL / content rating / contact email / category | DUP of PLAY_STORE 38 / 39 / 40 / 35 / 36 / 37 / 12 / **content rating = the one non-dup** → NEW → GAP-114 / 43 / 41 |

(Net: 9 duplicates, 1 new item — "Content rating questionnaire completed" → GAP-114.)

### docs/DEPLOY.md (7 items, lines 191–197)
| Verbatim item | Mapping |
|---|---|
| App installs from Play Store | DUP of PLAY_STORE 132 |
| Login works against production backend | DUP of PLAY_STORE 133 |
| Strategy pipeline starts when initiated | NEW → GAP-110 (live pipeline start — core-product E2E, grouped with feature runtime verification) |
| Push notification received when strategy completes | DUP of PLAY_STORE 135 |
| Deep link in notification opens correct in-app view | DUP of PLAY_STORE 134 |
| Meeting booking via Calendly works and updates lead status | NEW → GAP-107 (Calendly live E2E — extends 5.4 to full booking flow) |
| `/privacy` page accessible | DUP of PLAY_STORE 12 |

### docs/README_M7_CHUNKS_2_3.md (8 items, lines 34–41) — mobile QA
| Verbatim item | Mapping |
|---|---|
| Splash screen shows, then fades out | NEW → GAP-114 |
| Status bar color matches app primary blue | NEW → GAP-114 (INFORMATIONAL sub-item) |
| Pull-down on leads kanban → spinner → haptic on device | NEW → GAP-114 |
| Back button at dashboard root → exit dialog | DUP of PLAY_STORE 136 |
| Back button inside strategy detail → navigates back | DUP of PLAY_STORE 136 |
| WiFi off → "No connection" banner appears non-blocking | NEW → GAP-114 |
| WiFi on → banner disappears within 30s | NEW → GAP-114 |
| Deep link via adb opens strategies/1 | DUP of PLAY_STORE 134 |

### docs/backup/backup-procedure.md (6 items, lines 226–231) — per-change ops runbook, not launch items
| Verbatim item | Mapping |
|---|---|
| Backup 1 — file copies to `C:\tmp\leadpilot-backups\<TS>_<label>\` | NEW → GAP-116 (note: Windows dev-machine path — runbook is machine-specific → GAP-106 staleness sweep) |
| Backup 1 restoration test — every file diffs IDENTICAL | NEW → GAP-116 |
| Backup 2 — git anchor commit, hash recorded | NEW → GAP-116 |
| If change includes a migration: verified `pg_dump` taken | NEW → GAP-116 |
| Current alembic revision recorded | NEW → GAP-116 |
| Rollback procedure written down **before** the change | NEW → GAP-116 |

---

## PART C — Proposed new gaps (for Claude Project normalization into 03)

| ID | Title | Proposed severity (reason) | Status at creation | Evidence requirement (VERIFIED FIXED unless noted) |
|---|---|---|---|---|
| GAP-105 | Runtime infrastructure never stood up/verified (PG16, Redis, Celery worker+Beat, /health) | MAJOR (product cannot run without it; not CRITICAL — no data/legal exposure until it runs) | OPEN (dep: founder platform choice — Railway/Render/compose) | Recorded provisioning + `GET /health` ok from api/worker/beat + Beat schedule dump showing nightly aggregation hour |
| GAP-106 | LAUNCH_CHECKLIST and related docs are stale vs codebase (says 11 migrations/head `0011_m8c5`; repo has 49 files `0001…0047`; Firebase TODOs; Windows-path runbook; committed celerybeat state files) | MAJOR (the launch instrument itself gives wrong verification targets — following it as written would mis-verify) | OPEN | Reviewed commit updating checklist/docs to current chain + removal of stale verify targets; VERIFIED NOT APPLICABLE not available (staleness is demonstrated above) |
| GAP-107 | Remaining provider commissioning + live smoke (Gmail OAuth, WhatsApp, Calendly incl. booking E2E, Apollo, Hunter, Firebase; circuit-breakers all CLOSED) | MAJOR (revenue-path providers; same class as GAP-004/007) | BLOCKED (external accounts/keys) | Per-provider smoke output recorded (5.1–5.5 + DEPLOY Calendly E2E) + `GET /admin/circuit-breakers` all CLOSED |
| GAP-108 | RATE_LIMIT_* values unreviewed for target user base | MODERATE (config judgment; abuse controls exist in code) | OPEN — founder decision | Recorded value set + one-line rationale (D-entry or config commit) |
| GAP-109 | Live compliance verification never executed (warm-up + bounce config, unsubscribe→instant suppression E2E, cross-send suppression E2E, Meta template approval) | **CRITICAL** (legal-compliance surface; 00/06 default; offline sealed tests ≠ live verification; checklist itself marks §4 non-negotiable) | OPEN; 4.4 BLOCKED (Meta review) | Recorded live E2E outputs for 4.1–4.3, 4.5; Meta approval record for 4.4; no send campaigns before this is green |
| GAP-110 | Core-product + learning-loop runtime verification (pipeline start E2E; §6 + §7 endpoints; personalization_score written on real send) | MAJOR (includes "strategy pipeline starts" — the core product path — plus M8 feature surface) | OPEN (deps: 105, 107) | Recorded endpoint outputs per item incl. pipeline-start E2E and messages-table check |
| GAP-111 | Launch-feature runtime verification (429 rate limit, **402 plan gating**, webhook targets/delivery/retry, onboarding state, admin counters + plan change w/ audit log) | MAJOR (financial gating + audit trail + reliability) | OPEN (deps: 105) | Recorded responses incl. 429 w/ Retry-After, 402 body, requestbin delivery <30s, retry scheduling, audit-log row |
| GAP-112 | Frontend build + UI/mobile QA unverified (npm build; 5 UI checks; Android APK+push; theme persistence) | MODERATE (9.1 is a hard build gate — runnable now; UI items are QA) | OPEN; 9.6 conditional on mobile-in-v1 decision | `npm run build` clean output (immediately executable); recorded UI QA per item; device evidence for 9.6 |
| GAP-113 | Performance unverified (benchmark.py PASS/WARN; p99 <1s @50 users; nightly agg <30s @10k) | MODERATE (MAJOR if launch traffic is imminent) | OPEN (deps: 105, seeded data) | Benchmark output + load-test record + timed aggregation run |
| GAP-114 | Mobile/store release track unexecuted (signed AAB, privacy page live, assetlinks, store listing/assets incl. content rating, internal-testing QA, mobile UX QA) | MODERATE, **conditional** (whole track hinges on mobile-in-v1 scope decision; if descoped → VERIFIED NOT APPLICABLE via D-entry) | OPEN — founder scope decision first; account items BLOCKED external | If in scope: per-item recorded evidence incl. live privacy URL; if descoped: D-entry |
| GAP-115 | SDK/PyPI distribution unverified (TestPyPI install, `clienthunter serve`, `status`) | MODERATE, **conditional** (distribution channel; scope decision) | OPEN — founder scope decision | Fresh-venv install + serve + status outputs, or descope D-entry |
| GAP-116 | Backup/rollback runbook not adopted as practiced procedure (6 per-change steps; machine-specific path) | MINOR (ops hygiene; becomes MODERATE once production data exists) | OPEN | One recorded execution of the runbook on a real change + path fixed (ties to GAP-106) |

Dependency spine: GAP-105 → {110, 111, 112(UI), 113}; GAP-107 → {109(4.4 partly), 110(7.5), 114(push), 115(status)}; GAP-103 (existing) → {2.x, 115.2}.

---

## RECONCILIATION

| Count | Value |
|---|---|
| LAUNCH_CHECKLIST items processed | **62** (5+7+9+5+5+4+5+9+7+3+3) ✓ |
| — MAPS TO EXISTING | 10 (§2.1–2.7 → GAP-103; §3.1–3.2 → GAP-102; §3.3 → GAP-007) |
| — NEW GAP REQUIRED | 52 (→ GAP-105/107/108/109/110/111/112/113/115 per Part A) |
| — DUPLICATE within LAUNCH | 0 |
| — UNCERTAIN (unmappable) | 0 · Conditional-applicability flags: 4 (9.6, 11.1–11.3) pending founder scope decisions on mobile + SDK |
| docs/ items processed (net of PRODUCTION_READINESS) | **50** (PLAY_STORE 19 + STORE_ASSETS 10 + DEPLOY 7 + README_M7 8 + backup 6) |
| — NEW | 33 (GAP-114: 25; GAP-116: 6; GAP-110: 1; GAP-107: 1) |
| — DUP | 17 (STORE_ASSETS 9; DEPLOY 5; README_M7 3) |
| Proposed new gaps by severity | CRITICAL 1 (GAP-109) · MAJOR 5 (105, 106, 107, 110, 111) · MODERATE 5 (108, 112, 113, 114, 115) · MINOR 1 (116) |
| Section verify-steps (non-checkbox) mapped | 4 (§1→105, §2→106-stale, §3→107; Final-gate rule honored via GAP-109 CRITICAL) |

## OUT-OF-SCOPE DISCOVERIES (reported, not fixed)
1. **Checklist staleness is systemic, not cosmetic** — migration count 11 vs 49 means ~36 migrations of product surface post-date the launch checklist; the 62 items are a *lower bound* on launch verification (GAP-106 covers correcting the instrument; a delta review of what migrations 0012–0047 added that the checklist never covers should be part of its remediation).
2. `celerybeat-schedule.{bak,dat,dir}` runtime state files committed at repo root (hygiene; folded into GAP-106 sweep).
3. `scripts/verify_debug_router_guard.py` exists — direct input for the GAP-102 audit (debug-router production exposure); noted for LP-T-002/REQ-102 scoping.
4. `docs/PLAY_STORE_CHECKLIST.md` line 12 and DEPLOY reference `app.clienthunter.com/privacy` while docs/PRODUCTION_READINESS.md references `calendarharvest.com` — reinforces the GAP-007 staleness/naming inconsistency.

## LIMITATIONS
- Severities are **proposed**; Claude Project assigns final values per 00's canonical definitions.
- Item texts were read from the repo at HEAD f73c930; none paraphrased in the mapping columns beyond trivial truncation of command syntax already quoted in full in the source files.
- `03_GAP_REGISTER.md` / `00_PROJECT_CHARTER.md` are project-knowledge files, not repo files (task §11 listed them as repo `cat` targets — deviation noted); the authoritative session copies were used.
