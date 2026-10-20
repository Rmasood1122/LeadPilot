# Brand rename inventory — LeadPilot / ClientHunter / Vectorae → Victorae

Phase 0, step 3 of `docs/program/STAR_VICTORAE.md`. Read-only sweep of git-tracked files at
program start SHA `7872f9c6d4cda7796d43ed3fe486799a197ed74d` (2026-10-20). Eight parallel
subagents, one per area; their full tables are reproduced below as Parts 1–8, unedited except for
the part headings. Nothing in the repository was changed by the sweep.

## 0. Read this first

1. **The product already has a third name in the code: "Vectorae".** PR #113 (commit `6ada8b0`,
   2026-10-18) renamed the display brand LeadPilot → **Vectorae**. "Vectorae" appears 2,896 times
   in 479 tracked files. **"Victorae" appears 0 times.** The program prompt says the new name is
   "Victorae". Either it is a new name (a fourth brand), or it is a misspelling of Vectorae.
   Phase 1 cannot start until the founders say which (recon Q-a). This inventory therefore
   counts **Vectorae as an old variant to be replaced**, alongside LeadPilot and ClientHunter.
2. **The earlier rebrands were partial.** Visible old names that survive on master include:
   - the OpenAPI title and the `GET /` response name "ClientHunter Enterprise API" (`app/main.py:173,402`);
   - the Android launcher label "ClientHunter" (`frontend/android/app/src/main/res/values/strings.xml`
     `app_name`, `title_activity_main`), although `capacitor.config.ts` says `appName: 'Vectorae'`;
   - the login-page logo `frontend/public/brand/logo-full.png`, which shows a "LEADPILOT" wordmark,
     while `Logo.tsx:61` gives it `alt="Vectorae"`;
   - the homepage walkthrough video, its poster and the social-share image, which show "LeadPilot"
     on every frame (the `.vtt` captions say Vectorae);
   - the pilot scorecard email "LeadPilot account" (`app/services/pilot_mode.py:598`) and the
     meetings-ledger PDF title (`app/services/meetings_ledger.py:672`). Both are asserted by the
     **sealed** `tests/test_pilot_mode.py:806,1020`;
   - the Python SDK (`sdk/`), which is ClientHunter throughout;
   - root docs README, SECURITY, BACKUP, DEPLOY, LAUNCH_CHECKLIST, SYSTEM_HANDOFF (titled
     "ClientHunter Enterprise"), and the store-listing docs.
3. **Not every "LeadPilot" is us.** 99 occurrences refer to other companies: LeadPilot AB (a
   Swedish company that owns `leadpilot.com`), Twenty Over Ten's "Lead Pilot", LeadPilot AI and
   others. Most are in the "not affiliated with LeadPilot AB" sentence on the comparison pages,
   FAQ and JSON-LD (`frontend/src/content/geo/shared.ts:53`, `geo/faq.ts:28`, asserted by
   `frontend/src/tests/geoPages.test.ts:96`). A find-and-replace would corrupt them. They are class
   **EXCL** below and must be allowlisted by `brand_lint`.
4. **Our deploy docs point at a third party's domain.** `CLAUDE_CODE_HANDOFF.md:1727,1897-1902`,
   `DEPLOY_RAILWAY.md:102,146,167`, `.env.production.example:110` and the frontend build error at
   `frontend/next.config.js:109` use `leadpilot.com` / `api.leadpilot.com`, which belongs to LeadPilot AB.
   The sitemap and website builder use `https://leadpilot.io` (`app/services/sitemap.py:26`,
   `app/services/website_builder.py:39`). These are not branding decisions: they are wrong
   addresses. Reported, not fixed.

## 1. Counts

Units differ by area, because the agents counted either matching lines or occurrences (marked).
The help-center articles are counted twice: once in `docs/help-center/` and once in the synced
copy at `frontend/src/content/help-center/`, which `frontend/scripts/help/sync_help_center.mjs`
regenerates.

| Area | Unit | A display | B identifier | C human | DEFECT | EXCL (not us) | Part |
|---|---|---:|---:|---:|---:|---:|---|
| Backend `app/` | occurrences | 289 (139 + 150 comments) | 147 | 15 | 5 | — | 1 |
| Frontend web (excl. Android) | lines | 786 | 134 | 36 | 3 | in A/B rows* | 2 |
| Android, Capacitor, `native/`, `sdk/` | lines | 245 | 209 | 1 | 0 | — | 3 |
| Product docs (help center, features, connectors, api, store, privacy) | occurrences | 708 (650 + 58 heading-slugs) | 131 | 29 | 0 | — | 4 |
| Program docs, root `*.md`, `status-page/`, `reports/` | occurrences | 951 (465 current, 474 historical, 12 test/comment) | 438 | 198 (155 = "Calendarharvest" as company name) | 0 | 99 | 5 |
| Tests and evals | lines | 199 | 280 | 2 | 0 | — | 6 |
| Config, CI, infra, `alembic/`, scripts, plugins | occurrences | 99 (73 + 26 comments) | 110 | 8 | 1 | — | 7 |
| Binary and visual assets | items | 16 | 22 | 9 | 0 | — | 8 |
| **Total (mixed units, approximate)** | | **≈ 3,290** | **≈ 1,470** | **≈ 300** | **9** | **≥ 99** | |

\* The frontend agent recorded the LeadPilot AB lines inside its table with a "not us" reason
rather than as a separate class.

By variant, across all areas (approximate): Vectorae ≈ 2,900; leadpilot/LeadPilot/LEADPILOT/Lead
Pilot ≈ 1,150; clienthunter/ClientHunter/CLIENTHUNTER ≈ 760; `lpk_` ≈ 32; Victorae 0.

## 2. Class B keep-list (summary; every row is in the Parts)

These must not be renamed in this program. Each goes into `.brand-allowlist` in Phase 1 with this reason.

| Identifier | Where (examples) | Why it stays |
|---|---|---|
| Android `applicationId`/namespace `com.clienthunter.app`; keystore alias `clienthunter` | `frontend/android/app/build.gradle:27,31`, `capacitor.config.ts:8`, proguard, `assetlinks.json`, `local.properties.example`, `.github/workflows/android-release.yml` | A new id is a different app; installed users never get the update; the alias must match the existing signing key |
| Deep-link scheme `clienthunter://`, App Links host `app.clienthunter.com` | `AndroidManifest.xml:103`, `app/services/notifications.py`, `frontend/src/lib/deeplinks.ts` | Links already in notifications and emails |
| Celery task names `leadpilot.*` (≈58 lines) and the tracked beat file `celerybeat-schedule.*` | `app/workers/*`, sealed `tests/test_champion_tracker.py` | In-flight and scheduled tasks would be orphaned |
| OAuth scopes `leadpilot:read` / `leadpilot:write`; MCP server name `leadpilot`; plugin/marketplace id `leadpilot`; skill `leadpilot-outbound` | `app/mcp/`, `app/services/oauth_server.py`, `.claude-plugin/marketplace.json`, `plugins/` | Existing grants, installs and tool allowlists |
| Webhook headers `X-LeadPilot-*`, legacy `X-ClientHunter-Signature` | `app/api/calls.py`, `app/api/crm_integrations.py`, `app/api/linkedin.py`, `app/api/meetings.py`, docs | Customers' signature-verification code |
| API key prefix `lpk_` | `app/services/api_keys.py`, `app/mcp/auth.py` | Existing keys stop validating |
| Audit-trail key-derivation salt `b"leadpilot-audit-trail"` | `app/services/audit_trail.py:311` | Changing it breaks verification of every signed trail |
| Stored values: `leadpilot_calendar` enum/payload value, tutorial slug `getting-started-with-leadpilot`, badge `leadpilot-certified`, export format id `leadpilot-account-export` (sealed test), help-center chunk ids, `LeadSource="Vectorae"` written to customers' Salesforce | `app/`, `tests/` | Rows in our DB and in customers' CRMs |
| DNS TXT record `_leadpilot-verify.<domain>` | `app/services/workspaces.py:33`, `docs/features/workspaces.md:59` | Customers already published it |
| Cookie `lp_refresh`; browser keys `ch_access_token`, `ch_refresh_token`, `ch_user_email`, `ch_user_id`, `ch_theme`, `ch_push_*`, `leadpilot.theme`, `leadpilot.workspace`, `leadpilot.verify.phone-deferred`, `lp_oauth_consent_request` | `app/config.py:181`, `frontend/src/lib/auth-session.ts`, `frontend/src/lib/api/auth.ts`, `frontend/src/lib/theme/ThemeProvider.tsx`, `frontend/src/lib/theme/apply.ts` | Users are logged out or lose settings. Note `ch_*` and `lp_*` do not match the brand regex; `brand_lint` must not be relied on to protect them |
| Public URLs `/what-is-leadpilot/`, `/help/what-is-leadpilot/`, `/compare/leadpilot-vs-*/` and seven geo content file names | `frontend/src/content/geo/`, `site-pages.json`, `sitemap-lastmod.json`, `llms.txt` | Indexed URLs; renaming needs 301s (`vercel.json` has none) |
| Env var names `LEADPILOT_*`, `CLIENTHUNTER_API_*`, `VECTORAE_*` | `.env*.example`, `render.yaml`, `sdk/` | Set on Render/Vercel and in customers' shells |
| Render services `leadpilot-api`, `leadpilot-worker`; Vercel project `lead-pilot`; repo `Rmasood1122/LeadPilot` | `render.yaml`, docs | Dashboards and URLs |
| Postgres DB/user `clienthunter` (compose); gate stamp dir `leadpilot-gate` | `docker-compose*.yml`, `scripts/gate/` | Existing volumes; a partial rename blocks every push |
| SDK package/import/CLI `clienthunter`; native modules `vectorae_native_rs`, `vectorae_native_cpp` | `sdk/`, `native/`, `app/agents/native.py`, `.github/workflows/verify.yml:230` | Not published on PyPI (checked 2026-10-20: all names 404), so a rename is cheap **if** the founders want it — but it is still an identifier rename, so it is a plan item, not Phase 1 |
| UptimeRobot monitor names "Vectorae - …" | `status-page/lib/config.ts:65-70` | Matched by exact string against the external account |
| Media file names `frontend/public/media/leadpilot-walkthrough.*` | `frontend/src/app/page.tsx` | Referenced URLs; harmless to keep |
| Every shipped Alembic migration (7 hits in 6 files, all docstrings) | `alembic/versions/` | Never edit a shipped migration |
| Test-only domain `leadpilot.dev` (141 lines, 11 sealed files) | `tests/` | Fixture data; recommend keep |

## 3. Class C — needs a founder decision (summary)

| Item | Location | Who acts |
|---|---|---|
| Legal entity and trading name. Terms/Privacy say "Vectorae Enterprise" operated by "Calendarharvest"; the Terms page comment says Calendarharvest has no legal entity yet; `docs/PRIVACY_POLICY.md` says "ClientHunter Enterprise, also sold as Vectorae" | `frontend/src/app/terms/page.tsx`, `privacy/page.tsx`, `docs/PRIVACY_POLICY.md` | Founders + counsel |
| Brand formula "Vectorae by Calendarharvest" checked in code (page titles must contain it) | `frontend/src/content/product-facts.json`, brand constants, `docs/program/ai-visibility/REPORT.md:165` | Founders: does "by Calendarharvest" stay? |
| CAN-SPAM postal identity `SENDER_IDENTITY` default "Vectorae User, 123 Main St…" | `app/config.py:106`, `.env.production.example:114` | Founders (real postal address); production guard already blocks the placeholder |
| Resend sender name `EMAIL_FROM_NAME=Vectorae` | `render.yaml` (2×), `.env*.example` | Founders, Render dashboard |
| Voice-clone consent text and LinkedIn risk warning (versioned: wording change bumps the version and re-asks consent); ElevenLabs voice name "Vectorae - <name>"; meeting bot "Vectorae Notetaker" seen by prospects | `app/services/voice_twin.py`, `app/integrations/recall.py:154`, `app/services/linkedin*` | Founders + counsel |
| Google OAuth consent-screen app name (SECURITY.md:92 says "ClientHunter") | Google Cloud console | Founder with GCP access |
| Play Store listing "ClientHunter Enterprise" | `docs/STORE_ASSETS.md`, `docs/PLAY_STORE_CHECKLIST.md` | Founder, Play Console |
| Social/listing handles: LinkedIn `leadpilot-app`, G2 `leadpilot-2026-10-14`, Crunchbase `organization/leadpilot`, YouTube `@LeadPilotEnterprise` (also in JSON-LD `sameAs`) | `frontend/src/content/geo/`, `docs/program/ai-visibility/` | Founders |
| Stripe product name; HubSpot/Salesforce app listings; WhatsApp Business display name; Vapi assistant names | dashboards | Founders |
| Logo wordmark PNG (shows "LEADPILOT"), walkthrough video + poster (show "LeadPilot") | `frontend/public/brand/logo-full.png`, `frontend/public/media/leadpilot-walkthrough.*` | Founders supply artwork; the video can be re-rendered from `frontend/video-src/render.mjs` (its source already says Vectorae) once the name is fixed |
| Claude Project name "LeadPilot Production Readiness" | `CLAUDE.md:5` | Founders (claude.ai) |
| `scripts/generate_placeholder_icons.py` would overwrite the real icons with a "CH" square | `scripts/` | Do not run; founders decide whether to delete |

## 4. Defects found (customer-voice and others)

| # | Defect | Evidence | Severity |
|---|---|---|---|
| BR-D1 | Website builder prompt hard-codes "Vectorae Enterprise", "Also known as: Calendarharvest" and the founder's name, so a **customer's** generated pages carry our brand and founder | `app/services/website_builder.py:57,75,76,88` | HIGH (customer-voice) |
| BR-D2 | WhatsApp template placeholder "Hi {{1}}, Sam from Vectorae. Reply STOP to opt out." — customers may copy it into their own messages | `frontend/src/components/campaigns/TemplateEditor.tsx:70`; asserted by `frontend/src/tests/templateEditor.test.tsx:27,81` | MEDIUM |
| BR-D3 | Booking page "Scheduling by Vectorae" and ROI share page "Powered by Vectorae" are shown to the customer's prospects; not verified whether white-label hides them | `frontend/src/app/book/page.tsx:312`, `frontend/src/app/share/roi/page.tsx:132` | LOW–MEDIUM, needs founder call |
| BR-D4 | Default sender identity "Vectorae User, 123 Main St…" is the CAN-SPAM footer of outbound customer email if not configured; blocked in production by `production_guard` | `app/config.py:106`, `app/services/sequence_engine.py:630` | LOW (guarded) |
| BR-D5 | `displacement_monitor.FORBIDDEN_MENTIONS` lists leadpilot and vectorae but not victorae, so a DM naming the new brand would pass | `app/services/displacement_monitor.py:74` | MEDIUM — fix with the rename |
| BR-D6 | `scripts/phase_c_pipeline.py:172` puts `calendly.example/leadpilot/15min` into a rendered outreach message | manual script, placeholder domain | LOW |
| BR-D7 | Hidden coupling: FakeClaude only answers support chat if the prompt contains "Vectorae in-app support assistant" | `tests/conftest.py:304` ↔ `app/services/support_chat.py:98` | Must change together |
| BR-D8 | Help-center brand-specific search logic (`is_vectorae`, `is_leadpilot`) | `app/services/help_center.py:564-567,753` | Must learn the new name |

## 5. Generated, synced or ignored files

- `frontend/src/content/help-center/` — copy of `docs/help-center/`, regenerated by
  `frontend/scripts/help/sync_help_center.mjs`; a test fails on drift. Edit the docs originals.
- Help-center index — regenerated by `python -m scripts.help_center.build_index`. Renaming a heading
  changes its chunk id, which is stored on support-chat rows (`faq_ids`) and in the alias map at
  `app/services/help_center.py:182-190`. A heading rename needs an alias entry.
- `celerybeat-schedule.{bak,dat,dir}` — Celery beat runtime state, tracked by mistake (not in
  `.gitignore`); rewritten whenever beat runs. Should be untracked, never edited.
- Walkthrough video and poster — rendered by `frontend/video-src/render.mjs` from `walkthrough.html`.
- `__pycache__/` — git-ignored, not inventoried.

## 6. Problems found that are not about the brand (reported, not fixed)

- Android package mismatch: `app/core/config.py:438` and `.env.production.example` say
  `io.clienthunter.app`; the real applicationId is `com.clienthunter.app`.
- SDK default API URL `api.clienthunter.ai` (`sdk/.../config.py:33`, with a TODO); live domain is calendarharvest.com.
- Android manifest references `@mipmap/ic_launcher`, which is not in git; the committed Android project
  is also missing root/settings Gradle files, the wrapper, MainActivity and `google-services.json`,
  so it cannot build from the repo alone.
- The skill is stored twice (`.claude/skills/leadpilot-outbound` and the plugin); copies currently identical.

## 7. Phase 1 tooling notes

- Android build toolchain in this container: Java 21 and Gradle 8.14 present; no Android SDK
  (`ANDROID_HOME` unset). Combined with the missing project files, **no Android build can run here.**
- `brand_lint` must cover the `ch_`/`lp_` storage keys only by allowlist awareness, not by regex;
  it must allowlist EXCL third-party names by line content, not by file, so new occurrences in those
  files are still caught.
- This inventory file itself and `STAR_VICTORAE.md` will need allowlist entries.

---

# Part 1 — Brand inventory: backend package `app/`

_Source: subagent sweep, file `brand-app.md`._

Scope: every git-tracked file under `app/` (367 files). Command: `git grep -nIiE 'lead[ _.-]?pilot|client[ _.-]?hunter|vectorae|victorae|lpk_' -- app/` (440 matching lines, 455 occurrences) plus `git grep -nIi calendarharvest -- app/` (product-name use only). Verified per file with `git grep -c`. Read-only sweep: no repo file was changed.

## 1. Summary

- Occurrences: **456** in **153** files (455 regex occurrences + 1 `Calendarharvest` product-name row).
- By class: A 139, A-comment 150, B 147, C 15, DEFECT 5  (A-comment = code comments/docstrings, a subset of class A).
- By variant: `Vectorae` 270, `leadpilot` 119, `ClientHunter` 33, `LeadPilot` 18, `clienthunter` 11, `lpk_` 3, `lead pilot` 1, `Calendarharvest` 1
- `Victorae` (the new name): 0 hits in app/. `Lead Pilot`/`lead-pilot`/`lead_pilot` with separator: only `lead pilot` (1, in a guard list) and `leadpilot_calendar`/`leadpilot-*` strings counted under `leadpilot`.

| variant | A | A-comment | B | C | DEFECT |
|---|---|---|---|---|---|
| Vectorae | 129 | 107 | 15 | 15 | 4 |
| leadpilot | 6 | 20 | 93 | 0 | 0 |
| ClientHunter | 2 | 6 | 25 | 0 | 0 |
| LeadPilot | 2 | 8 | 8 | 0 | 0 |
| clienthunter | 0 | 7 | 4 | 0 | 0 |
| lpk_ | 0 | 2 | 1 | 0 | 0 |
| lead pilot | 0 | 0 | 1 | 0 | 0 |
| Calendarharvest | 0 | 0 | 0 | 0 | 1 |

Redis key prefixes: **none branded** (keys are `gmail:*`, `whatsapp:*`, `calls:usage:*`, `send_time:learned:*`). Cookie: the refresh cookie is `lp_refresh` (`app/config.py:181`) -- an abbreviation of LeadPilot that the regex does not catch (B, see section 5).

## 2. Occurrences

| path:line | variant | class | reason | risk |
|---|---|---|---|---|
| app/agents/__init__.py:1 | Vectorae | A-comment | code comment/docstring | low |
| app/agents/__init__.py:2 | Vectorae | A-comment | code comment/docstring | low |
| app/agents/base.py:1 | Vectorae | A-comment | code comment/docstring | low |
| app/agents/native.py:3 | Vectorae | A-comment | code comment/docstring | low |
| app/agents/native.py:5 | Vectorae | A-comment | code comment/docstring | low |
| app/agents/native.py:11 | Vectorae | A-comment | code comment/docstring | low |
| app/agents/native.py:26 | Vectorae | B | env var name VECTORAE_REQUIRE_NATIVE (Dockerfile + CI set it) | high |
| app/agents/native.py:41 | Vectorae | B | compiled native extension module name (native/rust, native/cpp build output) | high |
| app/agents/native.py:42 | Vectorae | B | compiled native extension module name (native/rust, native/cpp build output) | high |
| app/agents/reference.py:10 | Vectorae | A-comment | code comment/docstring | low |
| app/api/account_data.py:106 | leadpilot | A | download filename shown to the user (stale LeadPilot) | low |
| app/api/agents.py:1 | Vectorae | A-comment | code comment/docstring | low |
| app/api/agents.py:12 | Vectorae | A-comment | docstring (route-handler docstrings render in /docs) | low |
| app/api/audit.py:71 | leadpilot | A | download filename shown to the user (stale LeadPilot) | low |
| app/api/audit.py:74 | leadpilot | A | download filename shown to the user (stale LeadPilot) | low |
| app/api/auth.py:224 | Vectorae | A | user-facing message/string | low |
| app/api/auth.py:226 | Vectorae | A | user-facing message/string | low |
| app/api/auth.py:573 | Vectorae | A | user-facing message/string | low |
| app/api/calls.py:17 | LeadPilot | A-comment | docstring documenting a B header name | low |
| app/api/calls.py:297 | LeadPilot | B | inbound webhook signature/timestamp header name that callers send | high |
| app/api/crm_integrations.py:11 | LeadPilot | A-comment | docstring documenting a B header name | low |
| app/api/crm_integrations.py:207 | Vectorae | A | user-facing message/string | low |
| app/api/crm_integrations.py:266 | LeadPilot | A-comment | docstring documenting a B header name | low |
| app/api/crm_integrations.py:266 | LeadPilot | A-comment | docstring documenting a B header name | low |
| app/api/crm_integrations.py:286 | LeadPilot | B | inbound webhook signature/timestamp header name that callers send | high |
| app/api/crm_integrations.py:287 | LeadPilot | B | inbound webhook signature/timestamp header name that callers send | high |
| app/api/devices.py:2 | ClientHunter | A-comment | docstring (route-handler docstrings render in /docs) | low |
| app/api/health.py:57 | clienthunter | A-comment | comment naming the clienthunter CLI/SDK (B elsewhere) | low |
| app/api/leads.py:202 | clienthunter | A-comment | comment naming the clienthunter CLI/SDK (B elsewhere) | low |
| app/api/linkedin.py:19 | LeadPilot | A-comment | docstring documenting a B header name | low |
| app/api/linkedin.py:264 | LeadPilot | B | inbound webhook signature/timestamp header name that callers send | high |
| app/api/meeting_prep.py:209 | Vectorae | A-comment | docstring (route-handler docstrings render in /docs) | low |
| app/api/meetings.py:69 | LeadPilot | B | inbound webhook signature/timestamp header name that callers send | high |
| app/api/meetings_ledger.py:83 | leadpilot | A | download filename shown to the user (stale LeadPilot) | low |
| app/api/pilots.py:159 | leadpilot | A | download filename shown to the user (stale LeadPilot) | low |
| app/api/reply_copilot.py:127 | Vectorae | A-comment | docstring (route-handler docstrings render in /docs) | low |
| app/api/revenue_analytics.py:380 | leadpilot | A | download filename shown to the user (stale LeadPilot) | low |
| app/api/slack_integration.py:136 | Vectorae | A | user-facing message/string | low |
| app/api/strategies.py:665 | clienthunter | A-comment | comment naming the clienthunter CLI/SDK (B elsewhere) | low |
| app/api/tutorials.py:1 | Vectorae | A-comment | code comment/docstring | low |
| app/api/tutorials.py:212 | Vectorae | A-comment | code comment/docstring | low |
| app/api/unsubscribe.py:79 | Vectorae | A-comment | code comment/docstring | low |
| app/api/voice_twin.py:233 | Vectorae | A | user-facing message/string | low |
| app/api/voice_twin.py:323 | Vectorae | A | user-facing message/string | low |
| app/api/voice_twin.py:329 | Vectorae | A | user-facing message/string | low |
| app/api/website_builder.py:22 | leadpilot | A-comment | comment naming a stale leadpilot domain | low |
| app/api/website_builder.py:187 | leadpilot | A-comment | comment naming a stale leadpilot domain | low |
| app/cli/create_admin.py:7 | clienthunter | A-comment | comment naming the clienthunter CLI/SDK (B elsewhere) | low |
| app/cli/create_admin.py:8 | clienthunter | A-comment | comment naming the clienthunter CLI/SDK (B elsewhere) | low |
| app/config.py:24 | Vectorae | A | APP_NAME default; used in email-verification and password-reset emails (email_verification.py:142, password_reset.py:195) | med |
| app/config.py:37 | leadpilot | B | default DATABASE_URL user/password/db name leadpilot (local dev + docker defaults) | med |
| app/config.py:37 | leadpilot | B | default DATABASE_URL user/password/db name leadpilot (local dev + docker defaults) | med |
| app/config.py:37 | leadpilot | B | default DATABASE_URL user/password/db name leadpilot (local dev + docker defaults) | med |
| app/config.py:106 | Vectorae | DEFECT | default SENDER_IDENTITY placeholder goes into the CAN-SPAM footer of customer outreach email (sequence_engine.py:630); blocked in prod by production_guard/adversarial_review (they key on "123 main st", not the brand) | med |
| app/config.py:145 | clienthunter | A-comment | comment naming the clienthunter CLI/SDK (B elsewhere) | low |
| app/config.py:179 | leadpilot | A-comment | comment naming a Celery task (B) | low |
| app/config.py:179 | leadpilot | A-comment | comment naming a Celery task (B) | low |
| app/config.py:246 | Vectorae | C | EMAIL_FROM_NAME default: Resend sender display name on transactional mail | med |
| app/core/billing_catalog.py:117 | Vectorae | A | public pricing tagline | low |
| app/core/config.py:55 | clienthunter | B | default DATABASE_URL db name clienthunter | low |
| app/core/config.py:265 | Vectorae | A-comment | code comment/docstring | low |
| app/core/config.py:438 | clienthunter | B | Android applicationId io.clienthunter.app (FCM / App Links) | high |
| app/core/errors.py:116 | ClientHunter | A-comment | code comment/docstring | low |
| app/core/errors.py:126 | ClientHunter | B | internal Python symbol ClientHunterError (imports in app + tests; no external dependency) | low |
| app/core/errors.py:129 | ClientHunter | B | internal Python symbol ClientHunterError (imports in app + tests; no external dependency) | low |
| app/core/exceptions.py:10 | ClientHunter | B | internal Python symbol ClientHunterError (imports in app + tests; no external dependency) | low |
| app/core/exceptions.py:23 | ClientHunter | B | internal Python symbol ClientHunterError (imports in app + tests; no external dependency) | low |
| app/core/exceptions.py:37 | ClientHunter | B | internal Python symbol ClientHunterError (imports in app + tests; no external dependency) | low |
| app/core/exceptions.py:45 | ClientHunter | B | internal Python symbol ClientHunterError (imports in app + tests; no external dependency) | low |
| app/core/logging.py:2 | ClientHunter | A-comment | code comment/docstring | low |
| app/core/production_guard.py:227 | Vectorae | A-comment | code comment/docstring | low |
| app/core/production_guard.py:234 | Vectorae | A | operator-facing startup error quoting the placeholder text (must track config.py:106) | low |
| app/db/models.py:1 | Vectorae | A-comment | code comment/docstring | low |
| app/db/models.py:211 | Vectorae | A-comment | code comment/docstring | low |
| app/db/models.py:313 | Vectorae | A-comment | code comment/docstring | low |
| app/db/models.py:1796 | Vectorae | A-comment | code comment/docstring | low |
| app/db/models.py:1875 | Vectorae | A-comment | code comment/docstring | low |
| app/db/models.py:2871 | leadpilot | A-comment | comment listing the leadpilot_calendar enum value (B) | low |
| app/db/models.py:3195 | Vectorae | A-comment | code comment/docstring | low |
| app/db/models.py:3510 | Vectorae | A-comment | code comment/docstring | low |
| app/db/models.py:3837 | Vectorae | A-comment | code comment/docstring | low |
| app/db/models.py:3931 | leadpilot | A-comment | comment naming a stale leadpilot domain | low |
| app/db/models.py:4270 | leadpilot | A-comment | comment listing the leadpilot_calendar enum value (B) | low |
| app/db/models.py:6071 | Vectorae | A-comment | code comment/docstring | low |
| app/db/models.py:6196 | Vectorae | A-comment | code comment/docstring | low |
| app/integrations/aegisaudit.py:66 | Vectorae | A | report title sent to third-party AEGISAUDIT | low |
| app/integrations/apollo.py:25 | Vectorae | A-comment | code comment/docstring | low |
| app/integrations/geolocation.py:74 | Vectorae | B | User-Agent string third-party sites see (judge: rename is low-impact but visible) | low |
| app/integrations/google_meet.py:51 | ClientHunter | B | internal Python symbol ClientHunterError (imports in app + tests; no external dependency) | low |
| app/integrations/google_meet.py:65 | ClientHunter | B | internal Python symbol ClientHunterError (imports in app + tests; no external dependency) | low |
| app/integrations/hunter.py:3 | Vectorae | A-comment | code comment/docstring | low |
| app/integrations/mailreach.py:3 | Vectorae | A-comment | code comment/docstring | low |
| app/integrations/plumbing.py:26 | leadpilot | B | logger name leadpilot.external (log filters/alerts may key on it) | low |
| app/integrations/postiq.py:39 | leadpilot | B | CLIENT_NAME sent to the POSTIQ integration | med |
| app/integrations/recall.py:154 | Vectorae | C | Recall.ai bot display name "Vectorae Notetaker" -- shown to PROSPECTS in the customer's meeting (recording disclosure); no caller overrides it (meeting_recording.py:107) | high |
| app/integrations/salesforce.py:9 | Vectorae | A-comment | code comment/docstring | low |
| app/integrations/signalforge.py:20 | Vectorae | A-comment | code comment/docstring | low |
| app/integrations/signalforge.py:22 | Vectorae | A-comment | code comment/docstring | low |
| app/integrations/signalforge.py:24 | Vectorae | A-comment | code comment/docstring | low |
| app/integrations/slack.py:165 | Vectorae | A | Slack button label | low |
| app/integrations/sms.py:25 | ClientHunter | B | internal Python symbol ClientHunterError (imports in app + tests; no external dependency) | low |
| app/integrations/sms.py:32 | ClientHunter | B | internal Python symbol ClientHunterError (imports in app + tests; no external dependency) | low |
| app/integrations/stripe_billing.py:29 | ClientHunter | B | internal Python symbol ClientHunterError (imports in app + tests; no external dependency) | low |
| app/integrations/stripe_billing.py:34 | ClientHunter | B | internal Python symbol ClientHunterError (imports in app + tests; no external dependency) | low |
| app/integrations/stripe_billing.py:141 | Vectorae | C | Stripe product name created at checkout (shown on customer invoices/Stripe dashboard) | med |
| app/integrations/unipile_linkedin.py:114 | Vectorae | A-comment | code comment/docstring | low |
| app/integrations/unipile_linkedin.py:127 | Vectorae | A-comment | code comment/docstring | low |
| app/integrations/zoom.py:7 | Vectorae | A-comment | code comment/docstring | low |
| app/integrations/zoom.py:12 | Vectorae | A-comment | code comment/docstring | low |
| app/integrations/zoom.py:46 | ClientHunter | B | internal Python symbol ClientHunterError (imports in app + tests; no external dependency) | low |
| app/integrations/zoom.py:60 | ClientHunter | B | internal Python symbol ClientHunterError (imports in app + tests; no external dependency) | low |
| app/main.py:2 | ClientHunter | A-comment | code comment/docstring | low |
| app/main.py:107 | Vectorae | A-comment | code comment/docstring | low |
| app/main.py:173 | ClientHunter | A | OpenAPI title "ClientHunter Enterprise API" (/docs, /openapi.json; SDK generators may read it) | med |
| app/main.py:217 | ClientHunter | B | internal Python symbol ClientHunterError (imports in app + tests; no external dependency) | low |
| app/main.py:224 | ClientHunter | B | internal Python symbol ClientHunterError (imports in app + tests; no external dependency) | low |
| app/main.py:366 | Vectorae | A-comment | code comment/docstring | low |
| app/main.py:402 | ClientHunter | A | root GET / JSON name field (uptime probes may match it) | low |
| app/mcp/__init__.py:1 | Vectorae | A-comment | code comment/docstring | low |
| app/mcp/__init__.py:10 | Vectorae | A-comment | code comment/docstring | low |
| app/mcp/auth.py:5 | lpk_ | A-comment | docstring documenting the lpk_ key prefix (B) | low |
| app/mcp/context.py:64 | Vectorae | A | user-facing message/string | low |
| app/mcp/context.py:64 | Vectorae | A | user-facing message/string | low |
| app/mcp/context.py:68 | Vectorae | A | user-facing message/string | low |
| app/mcp/context.py:74 | Vectorae | A | user-facing message/string | low |
| app/mcp/scopes.py:3 | leadpilot | B | OAuth/MCP scope string granted in issued tokens and connector configs | high |
| app/mcp/scopes.py:4 | leadpilot | B | OAuth/MCP scope string granted in issued tokens and connector configs | high |
| app/mcp/server.py:48 | leadpilot | B | MCP server name (connector identity in Claude/ChatGPT) | high |
| app/mcp/server.py:67 | Vectorae | A | MCP connector resource name/title/description shown in Claude/ChatGPT (C if listed in a connector directory) | med |
| app/mcp/server.py:74 | Vectorae | A | MCP connector resource name/title/description shown in Claude/ChatGPT (C if listed in a connector directory) | med |
| app/mcp/server.py:75 | Vectorae | A | MCP connector resource name/title/description shown in Claude/ChatGPT (C if listed in a connector directory) | med |
| app/mcp/server.py:144 | leadpilot | A-comment | docstring naming the OAuth scope (B) | low |
| app/mcp/stepup.py:4 | leadpilot | A-comment | docstring naming the OAuth scope (B) | low |
| app/mcp/stepup.py:4 | leadpilot | A-comment | docstring naming the OAuth scope (B) | low |
| app/mcp/stepup.py:13 | leadpilot | A-comment | docstring naming the OAuth scope (B) | low |
| app/mcp/tools/__init__.py:50 | Vectorae | A-comment | code comment/docstring | low |
| app/mcp/tools/__init__.py:57 | Vectorae | A | user-facing message/string | low |
| app/mcp/tools/campaigns.py:6 | leadpilot | A-comment | docstring naming the OAuth scope (B) | low |
| app/mcp/tools/campaigns.py:80 | Vectorae | A | user-facing message/string | low |
| app/mcp/tools/chatgpt.py:37 | Vectorae | A | user-facing message/string | low |
| app/mcp/tools/chatgpt.py:39 | Vectorae | A | user-facing message/string | low |
| app/mcp/tools/chatgpt.py:42 | Vectorae | A | user-facing message/string | low |
| app/mcp/tools/chatgpt.py:61 | Vectorae | A | user-facing message/string | low |
| app/mcp/tools/chatgpt.py:65 | Vectorae | A | user-facing message/string | low |
| app/mcp/tools/leads.py:139 | Vectorae | A | user-facing message/string | low |
| app/mcp/tools/leads.py:199 | Vectorae | A | user-facing message/string | low |
| app/mcp/tools/strategies.py:54 | Vectorae | A | user-facing message/string | low |
| app/pipeline/registry.py:1 | Vectorae | A-comment | code comment/docstring | low |
| app/pipeline/registry.py:26 | Vectorae | A | LLM system prompt role framing (model-facing; not copied into outreach) | low |
| app/pipeline/registry.py:47 | Vectorae | A | LLM system prompt role framing (model-facing; not copied into outreach) | low |
| app/services/account_erasure.py:166 | Vectorae | A-comment | code comment/docstring | low |
| app/services/account_erasure.py:325 | Vectorae | A-comment | code comment/docstring | low |
| app/services/account_export.py:317 | leadpilot | B | account-export format id leadpilot-account-export (GDPR export consumers) | med |
| app/services/adversarial_review.py:81 | Vectorae | A | LLM system prompt role framing (model-facing; not copied into outreach) | low |
| app/services/anthropic_client.py:1 | Vectorae | A-comment | code comment/docstring | low |
| app/services/anthropic_client.py:22 | ClientHunter | B | internal Python symbol ClientHunterError (imports in app + tests; no external dependency) | low |
| app/services/anthropic_client.py:155 | ClientHunter | B | internal Python symbol ClientHunterError (imports in app + tests; no external dependency) | low |
| app/services/api_keys.py:3 | lpk_ | A-comment | docstring documenting the lpk_ key prefix (B) | low |
| app/services/api_keys.py:21 | lpk_ | B | API key prefix lpk_ (every issued key starts with it; auth parses it) | high |
| app/services/audit_trail.py:54 | leadpilot | B | audit report format/version id leadpilot.activity-audit.v1 (verifiers key on it) | high |
| app/services/audit_trail.py:311 | leadpilot | B | HKDF salt for audit-trail signing key -- changing it breaks verification of every existing signed audit trail | critical |
| app/services/audit_trail.py:426 | Vectorae | A | audit-trail PDF title | low |
| app/services/autopilot.py:96 | Vectorae | A | user-facing message/string | low |
| app/services/autopilot.py:217 | Vectorae | A | user-facing message/string | low |
| app/services/autopilot.py:387 | Vectorae | A | user-facing message/string | low |
| app/services/autopilot.py:388 | Vectorae | A | user-facing message/string | low |
| app/services/autopilot.py:549 | Vectorae | A | LLM system prompt role framing (model-facing; not copied into outreach) | low |
| app/services/autopilot.py:686 | Vectorae | A | user-facing message/string | low |
| app/services/benchmarks.py:1 | Vectorae | A-comment | code comment/docstring | low |
| app/services/benchmarks.py:6 | Vectorae | A-comment | code comment/docstring | low |
| app/services/benchmarks.py:292 | Vectorae | A | user-facing message/string | low |
| app/services/billing.py:779 | Vectorae | A | Stripe invoice line description shown to customer | low |
| app/services/billing.py:930 | Vectorae | A | billing email/plan name shown to the customer | low |
| app/services/billing.py:952 | Vectorae | A | billing email/plan name shown to the customer | low |
| app/services/billing.py:964 | Vectorae | C | required subscription/auto-renewal notice text | med |
| app/services/claim_verification.py:211 | Vectorae | B | functional token list: sender vocabulary excluded from claim extraction -- must add the new name in lockstep | med |
| app/services/claim_verification.py:396 | Vectorae | A | LLM system prompt role framing (model-facing; not copied into outreach) | low |
| app/services/compliance_audit.py:9 | Vectorae | A-comment | code comment/docstring | low |
| app/services/compliance_audit.py:14 | Vectorae | A-comment | code comment/docstring | low |
| app/services/compliance_audit.py:22 | Vectorae | A-comment | code comment/docstring | low |
| app/services/compliance_rules.py:34 | Vectorae | A-comment | code comment/docstring | low |
| app/services/compliance_rules.py:285 | Vectorae | A-comment | code comment/docstring | low |
| app/services/consensus.py:58 | Vectorae | A | LLM system prompt role framing (model-facing; not copied into outreach) | low |
| app/services/consent.py:135 | Vectorae | C | regulatory disclaimer (DNC/TCPA/PDPA) | low |
| app/services/credentials.py:35 | ClientHunter | B | internal Python symbol ClientHunterError (imports in app + tests; no external dependency) | low |
| app/services/credentials.py:39 | ClientHunter | B | internal Python symbol ClientHunterError (imports in app + tests; no external dependency) | low |
| app/services/crm_events.py:366 | leadpilot | B | channel/source enum value leadpilot_calendar (stored in DB rows and sent in webhook payloads) | high |
| app/services/crm_sync.py:4 | Vectorae | A-comment | code comment/docstring | low |
| app/services/crm_sync.py:8 | Vectorae | A-comment | code comment/docstring | low |
| app/services/crm_sync.py:8 | Vectorae | A-comment | code comment/docstring | low |
| app/services/crm_sync.py:13 | Vectorae | A-comment | code comment/docstring | low |
| app/services/crm_sync.py:28 | Vectorae | A-comment | code comment/docstring | low |
| app/services/crm_sync.py:335 | Vectorae | A-comment | code comment/docstring | low |
| app/services/crm_sync.py:414 | Vectorae | B | LeadSource value written into the customer's Salesforce (their reports filter on it) | high |
| app/services/crm_sync.py:460 | Vectorae | A | deal name/description written into customer CRM records | low |
| app/services/crm_sync.py:466 | Vectorae | A | deal name/description written into customer CRM records | low |
| app/services/crm_sync.py:560 | Vectorae | A-comment | code comment/docstring | low |
| app/services/crm_sync.py:738 | Vectorae | A-comment | code comment/docstring | low |
| app/services/crm_sync.py:739 | Vectorae | A-comment | code comment/docstring | low |
| app/services/daily_send_approval.py:3 | Vectorae | A-comment | code comment/docstring | low |
| app/services/daily_send_approval.py:95 | Vectorae | C | versioned LinkedIn risk disclosure (LINKEDIN_WARNING_VERSION must bump if text changes) | high |
| app/services/daily_send_approval.py:689 | Vectorae | A | user-facing message/string | low |
| app/services/daily_send_approval.py:694 | Vectorae | A | user-facing message/string | low |
| app/services/daily_send_approval.py:701 | Vectorae | A | user-facing message/string | low |
| app/services/daily_send_approval.py:704 | Vectorae | A | user-facing message/string | low |
| app/services/displacement_monitor.py:74 | Vectorae | B | FORBIDDEN_MENTIONS guard list for prospect DMs -- must ADD the new name (victorae) or the guard stops catching it | high |
| app/services/displacement_monitor.py:74 | leadpilot | B | FORBIDDEN_MENTIONS guard list for prospect DMs -- must ADD the new name (victorae) or the guard stops catching it | high |
| app/services/displacement_monitor.py:74 | lead pilot | B | FORBIDDEN_MENTIONS guard list for prospect DMs -- must ADD the new name (victorae) or the guard stops catching it | high |
| app/services/displacement_monitor.py:77 | Vectorae | A | LLM system prompt role framing (model-facing; not copied into outreach) | low |
| app/services/email_network_gmail.py:90 | Vectorae | A-comment | code comment/docstring | low |
| app/services/email_sender.py:1 | Vectorae | A-comment | code comment/docstring | low |
| app/services/email_sender.py:7 | Vectorae | A-comment | code comment/docstring | low |
| app/services/email_sender.py:44 | ClientHunter | B | internal Python symbol ClientHunterError (imports in app + tests; no external dependency) | low |
| app/services/email_sender.py:56 | ClientHunter | B | internal Python symbol ClientHunterError (imports in app + tests; no external dependency) | low |
| app/services/fpta_scoring.py:79 | Vectorae | A | LLM system prompt role framing (model-facing; not copied into outreach) | low |
| app/services/guardrails.py:688 | Vectorae | A-comment | code comment/docstring | low |
| app/services/help_center.py:34 | Vectorae | A-comment | code comment/docstring | low |
| app/services/help_center.py:34 | Vectorae | A-comment | code comment/docstring | low |
| app/services/help_center.py:156 | Vectorae | A-comment | code comment/docstring | low |
| app/services/help_center.py:176 | Vectorae | A-comment | code comment/docstring | low |
| app/services/help_center.py:182 | leadpilot | B | help-center chunk-id alias (stored citation ids; derived from doc headings) | med |
| app/services/help_center.py:182 | leadpilot | B | help-center chunk-id alias (stored citation ids; derived from doc headings) | med |
| app/services/help_center.py:182 | Vectorae | B | help-center chunk-id alias (stored citation ids; derived from doc headings) | med |
| app/services/help_center.py:183 | leadpilot | B | help-center chunk-id alias (stored citation ids; derived from doc headings) | med |
| app/services/help_center.py:183 | Vectorae | B | help-center chunk-id alias (stored citation ids; derived from doc headings) | med |
| app/services/help_center.py:184 | Vectorae | B | help-center chunk-id alias (stored citation ids; derived from doc headings) | med |
| app/services/help_center.py:185 | leadpilot | B | help-center chunk-id alias (stored citation ids; derived from doc headings) | med |
| app/services/help_center.py:186 | Vectorae | B | help-center chunk-id alias (stored citation ids; derived from doc headings) | med |
| app/services/help_center.py:190 | Vectorae | B | help-center chunk-id alias (stored citation ids; derived from doc headings) | med |
| app/services/help_center.py:564 | Vectorae | A-comment | code comment/docstring | low |
| app/services/help_center.py:565 | Vectorae | A-comment | code comment/docstring | low |
| app/services/help_center.py:566 | Vectorae | A-comment | code comment/docstring | low |
| app/services/help_center.py:567 | Vectorae | A-comment | code comment/docstring | low |
| app/services/help_center.py:753 | leadpilot | A-comment | code comment/docstring | low |
| app/services/icp_extraction.py:47 | Vectorae | A | LLM system prompt role framing (model-facing; not copied into outreach) | low |
| app/services/icp_extraction.py:68 | Vectorae | A | LLM system prompt role framing (model-facing; not copied into outreach) | low |
| app/services/lead_scoring.py:53 | Vectorae | A | LLM system prompt role framing (model-facing; not copied into outreach) | low |
| app/services/linkedin_outreach.py:50 | Vectorae | A | LLM system prompt role framing (model-facing; not copied into outreach) | low |
| app/services/local_business.py:11 | Vectorae | A-comment | code comment/docstring | low |
| app/services/local_business.py:494 | Vectorae | C | HIPAA/health-data compliance statement | med |
| app/services/local_business.py:505 | Vectorae | C | HIPAA/health-data compliance statement | med |
| app/services/local_business.py:510 | Vectorae | C | HIPAA/health-data compliance statement | med |
| app/services/local_business.py:542 | Vectorae | A | user-facing message/string | low |
| app/services/local_business.py:544 | Vectorae | A | user-facing message/string | low |
| app/services/loom_video.py:15 | Vectorae | A-comment | code comment/docstring | low |
| app/services/loom_video.py:45 | Vectorae | A | LLM system prompt role framing (model-facing; not copied into outreach) | low |
| app/services/mailbox_health.py:21 | Vectorae | A-comment | code comment/docstring | low |
| app/services/mailbox_health.py:577 | Vectorae | A | user-facing message/string | low |
| app/services/market_intel.py:83 | Vectorae | B | User-Agent string third-party sites see (judge: rename is low-impact but visible) | low |
| app/services/meeting_ai.py:51 | Vectorae | A | LLM system prompt role framing (model-facing; not copied into outreach) | low |
| app/services/meeting_followup.py:7 | Vectorae | A-comment | code comment/docstring | low |
| app/services/meeting_followup.py:115 | Vectorae | A | LLM system prompt role framing (model-facing; not copied into outreach) | low |
| app/services/meeting_prep.py:5 | Vectorae | A-comment | code comment/docstring | low |
| app/services/meeting_prep.py:68 | leadpilot | B | channel/source enum value leadpilot_calendar (stored in DB rows and sent in webhook payloads) | high |
| app/services/meeting_prep.py:72 | Vectorae | A | LLM system prompt role framing (model-facing; not copied into outreach) | low |
| app/services/meetings_ledger.py:75 | Vectorae | A | user-facing message/string | low |
| app/services/meetings_ledger.py:511 | leadpilot | B | export/report format version id (consumers key on it) | med |
| app/services/meetings_ledger.py:672 | LeadPilot | A | PDF title still says "LeadPilot" (missed by PR #113) | low |
| app/services/message_personalization.py:19 | Vectorae | A | LLM system prompt role framing (model-facing; not copied into outreach) | low |
| app/services/message_personalization.py:195 | Vectorae | A | LLM system prompt role framing (model-facing; not copied into outreach) | low |
| app/services/message_personalization.py:323 | Vectorae | A | LLM system prompt role framing (model-facing; not copied into outreach) | low |
| app/services/message_personalization.py:446 | Vectorae | A | LLM system prompt role framing (model-facing; not copied into outreach) | low |
| app/services/notifications.py:2 | ClientHunter | A-comment | code comment/docstring | low |
| app/services/notifications.py:123 | clienthunter | B | mobile deep-link URL scheme clienthunter:// (Android manifest intent filter) | high |
| app/services/notifications.py:124 | clienthunter | B | App Links host app.clienthunter.com (assetlinks; TODO says unconfirmed) | high |
| app/services/notifications.py:130 | clienthunter | A-comment | code comment/docstring | low |
| app/services/oauth_server.py:51 | leadpilot | B | OAuth/MCP scope string granted in issued tokens and connector configs | high |
| app/services/oauth_server.py:52 | leadpilot | B | OAuth/MCP scope string granted in issued tokens and connector configs | high |
| app/services/open_tracking.py:48 | leadpilot | B | dev-only HMAC fallback secret for open-tracking tokens | low |
| app/services/phone_calls.py:76 | Vectorae | A | LLM system prompt role framing (model-facing; not copied into outreach) | low |
| app/services/phone_calls.py:92 | Vectorae | A | LLM system prompt role framing (model-facing; not copied into outreach) | low |
| app/services/phone_verification.py:152 | Vectorae | A | SMS verification text sent to the user | low |
| app/services/pilot_mode.py:36 | Vectorae | A-comment | code comment/docstring | low |
| app/services/pilot_mode.py:77 | leadpilot | B | export/report format version id (consumers key on it) | med |
| app/services/pilot_mode.py:86 | Vectorae | A-comment | code comment/docstring | low |
| app/services/pilot_mode.py:582 | Vectorae | A | user-facing message/string | low |
| app/services/pilot_mode.py:598 | LeadPilot | A | weekly scorecard email body still says "LeadPilot account" (missed by PR #113) | low |
| app/services/pilot_mode.py:702 | Vectorae | A | user-facing message/string | low |
| app/services/pilot_mode.py:858 | Vectorae | A | user-facing message/string | low |
| app/services/provenance.py:54 | Vectorae | A | user-facing message/string | low |
| app/services/reply_classification.py:12 | Vectorae | A-comment | code comment/docstring | low |
| app/services/reply_classification.py:35 | Vectorae | A | LLM system prompt role framing (model-facing; not copied into outreach) | low |
| app/services/reply_copilot.py:420 | Vectorae | A-comment | code comment/docstring | low |
| app/services/reply_copilot.py:492 | Vectorae | A | LLM system prompt role framing (model-facing; not copied into outreach) | low |
| app/services/reply_copilot.py:1050 | Vectorae | A-comment | code comment/docstring | low |
| app/services/reply_fraud.py:51 | Vectorae | A | LLM system prompt role framing (model-facing; not copied into outreach) | low |
| app/services/reply_intelligence.py:103 | Vectorae | A | LLM system prompt role framing (model-facing; not copied into outreach) | low |
| app/services/reply_intent.py:75 | Vectorae | A | LLM system prompt role framing (model-facing; not copied into outreach) | low |
| app/services/revenue_analytics.py:13 | Vectorae | A-comment | code comment/docstring | low |
| app/services/roi_calculator.py:3 | Vectorae | A-comment | code comment/docstring | low |
| app/services/roi_calculator.py:56 | Vectorae | A-comment | code comment/docstring | low |
| app/services/roi_card.py:228 | Vectorae | A | ROI proof card (designed to be forwarded by the user; "Powered by" attribution) | low |
| app/services/safe_fetch.py:58 | Vectorae | B | User-Agent string third-party sites see (judge: rename is low-impact but visible) | low |
| app/services/send_diagnostics.py:167 | Vectorae | A | user-facing message/string | low |
| app/services/send_time.py:91 | leadpilot | A-comment | comment naming a Celery task (B) | low |
| app/services/send_time.py:343 | Vectorae | A | LLM system prompt role framing (model-facing; not copied into outreach) | low |
| app/services/sequence_engine.py:73 | Vectorae | A-comment | code comment/docstring | low |
| app/services/sequence_engine.py:172 | Vectorae | A-comment | code comment/docstring | low |
| app/services/sequence_engine.py:829 | Vectorae | A-comment | code comment/docstring | low |
| app/services/sequence_engine.py:834 | Vectorae | A-comment | code comment/docstring | low |
| app/services/signal_radar.py:4 | Vectorae | A-comment | code comment/docstring | low |
| app/services/sitemap.py:1 | Vectorae | A-comment | code comment/docstring | low |
| app/services/sitemap.py:26 | leadpilot | B | SITE_ORIGIN https://leadpilot.io (canonical URLs/sitemap; differs from live calendarharvest.com) | med |
| app/services/spend_guard.py:848 | Vectorae | A | user-facing message/string | low |
| app/services/spend_guard.py:951 | Vectorae | A-comment | code comment/docstring | low |
| app/services/spend_guard.py:984 | Vectorae | A | user-facing message/string | low |
| app/services/strategy_mutation.py:56 | Vectorae | A | LLM system prompt role framing (model-facing; not copied into outreach) | low |
| app/services/style_profile.py:32 | Vectorae | A | LLM system prompt role framing (model-facing; not copied into outreach) | low |
| app/services/support_chat.py:39 | Vectorae | A-comment | code comment/docstring | low |
| app/services/support_chat.py:98 | Vectorae | A | Help AI (support chat) system prompt naming the product | low |
| app/services/support_chat.py:103 | Vectorae | A | Help AI (support chat) system prompt naming the product | low |
| app/services/support_chat.py:108 | Vectorae | A | Help AI (support chat) system prompt naming the product | low |
| app/services/support_chat.py:115 | Vectorae | A | Help AI (support chat) system prompt naming the product | low |
| app/services/support_chat.py:266 | Vectorae | A-comment | code comment/docstring | low |
| app/services/support_chat.py:266 | Vectorae | A-comment | code comment/docstring | low |
| app/services/support_kb.py:26 | Vectorae | A-comment | code comment/docstring | low |
| app/services/support_kb.py:76 | leadpilot | B | FAQ entry id (help_center LEGACY_FAQ_ALIASES + stored citations) | med |
| app/services/support_kb.py:77 | Vectorae | A | Help AI knowledge-base Q/A text shown to users | low |
| app/services/support_kb.py:79 | Vectorae | A | Help AI knowledge-base Q/A text shown to users | low |
| app/services/support_kb.py:90 | Vectorae | A | Help AI knowledge-base Q/A text shown to users | low |
| app/services/support_kb.py:100 | Vectorae | A | Help AI knowledge-base Q/A text shown to users | low |
| app/services/support_kb.py:114 | Vectorae | A | Help AI knowledge-base Q/A text shown to users | low |
| app/services/support_kb.py:142 | Vectorae | A | Help AI knowledge-base Q/A text shown to users | low |
| app/services/support_kb.py:195 | Vectorae | A | Help AI knowledge-base Q/A text shown to users | low |
| app/services/system_settings.py:92 | Vectorae | C | regulatory disclaimer (DNC/TCPA/PDPA) | low |
| app/services/system_settings.py:141 | Vectorae | A-comment | code comment/docstring | low |
| app/services/tutorials.py:97 | leadpilot | B | tutorial slug stored in tutorial_progress.tutorial_slug (DB) and URLs | high |
| app/services/tutorials.py:98 | Vectorae | A | user-facing message/string | low |
| app/services/tutorials.py:100 | Vectorae | A | user-facing message/string | low |
| app/services/tutorials.py:120 | Vectorae | A | user-facing message/string | low |
| app/services/tutorials.py:148 | leadpilot | B | tutorial slug stored in tutorial_progress.tutorial_slug (DB) and URLs | high |
| app/services/tutorials.py:149 | Vectorae | A | user-facing message/string | low |
| app/services/tutorials.py:216 | leadpilot | B | badge id leadpilot-certified (persisted badge key) | high |
| app/services/tutorials.py:216 | Vectorae | A | user-facing message/string | low |
| app/services/usage_meter.py:38 | ClientHunter | B | internal Python symbol ClientHunterError (imports in app + tests; no external dependency) | low |
| app/services/usage_meter.py:96 | ClientHunter | B | internal Python symbol ClientHunterError (imports in app + tests; no external dependency) | low |
| app/services/voice_profiler.py:3 | Vectorae | A-comment | code comment/docstring | low |
| app/services/voice_profiler.py:63 | Vectorae | A | LLM system prompt role framing (model-facing; not copied into outreach) | low |
| app/services/voice_twin.py:78 | Vectorae | C | voice-clone written consent text (CONSENT_VERSION must bump; returned as template by api/voice_twin.py:106) | high |
| app/services/voice_twin.py:79 | Vectorae | C | voice-clone written consent text (CONSENT_VERSION must bump; returned as template by api/voice_twin.py:106) | high |
| app/services/voice_twin.py:85 | Vectorae | C | voice-clone written consent text (CONSENT_VERSION must bump; returned as template by api/voice_twin.py:106) | high |
| app/services/voice_twin.py:445 | Vectorae | A | user-facing message/string | low |
| app/services/voice_twin.py:709 | Vectorae | A | user-facing message/string | low |
| app/services/voice_twin.py:774 | Vectorae | A | user-facing message/string | low |
| app/services/voice_twin.py:794 | Vectorae | A | user-facing message/string | low |
| app/services/voice_twin.py:814 | Vectorae | A | user-facing message/string | low |
| app/services/voice_twin.py:836 | Vectorae | C | voice name/description created at ElevenLabs (third-party; existing voices keep old name) | med |
| app/services/voice_twin.py:839 | Vectorae | C | voice name/description created at ElevenLabs (third-party; existing voices keep old name) | med |
| app/services/voice_twin.py:860 | Vectorae | A | user-facing message/string | low |
| app/services/voice_twin.py:883 | Vectorae | A | user instruction naming the ElevenLabs voice "Vectorae - <name>" (must match :836) | med |
| app/services/voice_twin.py:884 | Vectorae | A | user instruction naming the ElevenLabs voice "Vectorae - <name>" (must match :836) | med |
| app/services/voice_twin.py:1069 | Vectorae | A | user-facing message/string | low |
| app/services/voice_twin.py:1556 | Vectorae | A | user-facing message/string | low |
| app/services/webhook_delivery.py:19 | LeadPilot | A-comment | docstring documenting a B header name | low |
| app/services/webhook_delivery.py:20 | LeadPilot | A-comment | docstring documenting a B header name | low |
| app/services/webhook_delivery.py:21 | LeadPilot | A-comment | docstring documenting a B header name | low |
| app/services/webhook_delivery.py:22 | ClientHunter | A-comment | docstring documenting a B header name | low |
| app/services/webhook_delivery.py:64 | Vectorae | A | webhook event description shown in UI/API | low |
| app/services/webhook_delivery.py:371 | Vectorae | B | User-Agent on outbound webhooks (customers may allowlist/filter it) | med |
| app/services/webhook_delivery.py:372 | LeadPilot | B | outbound webhook header name customers verify against | high |
| app/services/webhook_delivery.py:373 | LeadPilot | B | outbound webhook header name customers verify against | high |
| app/services/webhook_delivery.py:374 | LeadPilot | B | outbound webhook header name customers verify against | high |
| app/services/webhook_delivery.py:375 | ClientHunter | B | legacy outbound signature header X-ClientHunter-Signature (customers may still verify it) | high |
| app/services/website_builder.py:39 | leadpilot | B | SITE_ORIGIN https://leadpilot.io (canonical URLs/sitemap; differs from live calendarharvest.com) | med |
| app/services/website_builder.py:57 | Vectorae | DEFECT | page-generation prompt hard-codes "Vectorae Enterprise" brand + founder name; also used for CUSTOMER workspace pages (api/website_builder.py scopes pages by workspace_id) -> customer sites branded as us | high |
| app/services/website_builder.py:75 | Vectorae | DEFECT | page-generation prompt hard-codes "Vectorae Enterprise" brand + founder name; also used for CUSTOMER workspace pages (api/website_builder.py scopes pages by workspace_id) -> customer sites branded as us | high |
| app/services/website_builder.py:76 | Calendarharvest | DEFECT | "Also known as: Calendarharvest" product alias in the page-generation prompt (same issue as :75) | high |
| app/services/website_builder.py:88 | Vectorae | DEFECT | page-generation prompt hard-codes "Vectorae Enterprise" brand + founder name; also used for CUSTOMER workspace pages (api/website_builder.py scopes pages by workspace_id) -> customer sites branded as us | high |
| app/services/whatsapp_optin.py:149 | Vectorae | A | user-facing message/string | low |
| app/services/whatsapp_templates.py:84 | Vectorae | A | user-facing message/string | low |
| app/services/whatsapp_templates.py:382 | Vectorae | A | LLM system prompt role framing (model-facing; not copied into outreach) | low |
| app/services/workspaces.py:33 | leadpilot | B | DNS TXT verification record name _leadpilot-verify.<domain> customers have already published | high |
| app/services/workspaces.py:231 | Vectorae | A | default brand_name for non-white-label workspaces (invite email subject, branding API) | med |
| app/services/workspaces.py:293 | Vectorae | A | default brand_name for non-white-label workspaces (invite email subject, branding API) | med |
| app/services/workspaces.py:300 | Vectorae | A | default brand_name for non-white-label workspaces (invite email subject, branding API) | med |
| app/services/workspaces.py:371 | leadpilot | A-comment | code comment/docstring | low |
| app/templates/roi_card.html:5 | Vectorae | A | ROI proof card (designed to be forwarded by the user; "Powered by" attribution) | low |
| app/templates/roi_card.html:148 | Vectorae | A | ROI proof card (designed to be forwarded by the user; "Powered by" attribution) | low |
| app/verification/passes.py:16 | Vectorae | A | LLM system prompt role framing (model-facing; not copied into outreach) | low |
| app/verification/passes.py:77 | Vectorae | A | LLM system prompt role framing (model-facing; not copied into outreach) | low |
| app/worker_health.py:38 | Vectorae | A | worker health OpenAPI title | low |
| app/worker_health.py:156 | leadpilot | B | service id leadpilot-worker (health probes) | low |
| app/workers/autopilot_tasks.py:3 | leadpilot | A-comment | comment naming a Celery task (B) | low |
| app/workers/autopilot_tasks.py:9 | leadpilot | A-comment | comment naming a Celery task (B) | low |
| app/workers/autopilot_tasks.py:15 | leadpilot | A-comment | comment naming a Celery task (B) | low |
| app/workers/autopilot_tasks.py:40 | leadpilot | B | Celery task name / queue route (in-flight messages + beat schedule + monitoring key on it) | high |
| app/workers/autopilot_tasks.py:51 | leadpilot | B | Celery task name / queue route (in-flight messages + beat schedule + monitoring key on it) | high |
| app/workers/autopilot_tasks.py:62 | leadpilot | B | Celery task name / queue route (in-flight messages + beat schedule + monitoring key on it) | high |
| app/workers/autopilot_tasks.py:75 | leadpilot | B | Celery task name / queue route (in-flight messages + beat schedule + monitoring key on it) | high |
| app/workers/calendar_tasks.py:47 | leadpilot | B | channel/source enum value leadpilot_calendar (stored in DB rows and sent in webhook payloads) | high |
| app/workers/calendar_tasks.py:230 | Vectorae | A-comment | code comment/docstring | low |
| app/workers/calendar_tasks.py:250 | Vectorae | A | user-facing message/string | low |
| app/workers/calendar_tasks.py:252 | leadpilot | B | channel/source enum value leadpilot_calendar (stored in DB rows and sent in webhook payloads) | high |
| app/workers/calendar_tasks.py:268 | Vectorae | A-comment | code comment/docstring | low |
| app/workers/celery_app.py:17 | leadpilot | B | Celery app main name | med |
| app/workers/celery_app.py:110 | leadpilot | B | Celery task name / queue route (in-flight messages + beat schedule + monitoring key on it) | high |
| app/workers/celery_app.py:111 | leadpilot | B | Celery task name / queue route (in-flight messages + beat schedule + monitoring key on it) | high |
| app/workers/celery_app.py:112 | leadpilot | B | Celery task name / queue route (in-flight messages + beat schedule + monitoring key on it) | high |
| app/workers/celery_app.py:114 | leadpilot | B | Celery task name / queue route (in-flight messages + beat schedule + monitoring key on it) | high |
| app/workers/celery_app.py:125 | leadpilot | A-comment | comment naming a Celery task (B) | low |
| app/workers/celery_app.py:128 | leadpilot | B | Celery task name / queue route (in-flight messages + beat schedule + monitoring key on it) | high |
| app/workers/celery_app.py:131 | leadpilot | B | Celery task name / queue route (in-flight messages + beat schedule + monitoring key on it) | high |
| app/workers/celery_app.py:163 | leadpilot | A-comment | comment naming a Celery task (B) | low |
| app/workers/celery_app.py:199 | leadpilot | B | Celery task name / queue route (in-flight messages + beat schedule + monitoring key on it) | high |
| app/workers/celery_app.py:205 | leadpilot | B | Celery task name / queue route (in-flight messages + beat schedule + monitoring key on it) | high |
| app/workers/celery_app.py:207 | leadpilot | B | Celery task name / queue route (in-flight messages + beat schedule + monitoring key on it) | high |
| app/workers/celery_app.py:210 | leadpilot | B | Celery task name / queue route (in-flight messages + beat schedule + monitoring key on it) | high |
| app/workers/celery_app.py:262 | leadpilot | B | Celery task name / queue route (in-flight messages + beat schedule + monitoring key on it) | high |
| app/workers/celery_app.py:267 | leadpilot | B | Celery task name / queue route (in-flight messages + beat schedule + monitoring key on it) | high |
| app/workers/celery_app.py:271 | leadpilot | B | Celery task name / queue route (in-flight messages + beat schedule + monitoring key on it) | high |
| app/workers/celery_app.py:275 | leadpilot | B | Celery task name / queue route (in-flight messages + beat schedule + monitoring key on it) | high |
| app/workers/celery_app.py:304 | leadpilot | B | Celery task name / queue route (in-flight messages + beat schedule + monitoring key on it) | high |
| app/workers/celery_app.py:311 | leadpilot | B | Celery task name / queue route (in-flight messages + beat schedule + monitoring key on it) | high |
| app/workers/celery_app.py:367 | Vectorae | A-comment | code comment/docstring | low |
| app/workers/celery_app.py:482 | leadpilot | B | Celery task name / queue route (in-flight messages + beat schedule + monitoring key on it) | high |
| app/workers/celery_app.py:486 | leadpilot | B | Celery task name / queue route (in-flight messages + beat schedule + monitoring key on it) | high |
| app/workers/celery_app.py:493 | leadpilot | B | Celery task name / queue route (in-flight messages + beat schedule + monitoring key on it) | high |
| app/workers/celery_app.py:501 | leadpilot | B | Celery task name / queue route (in-flight messages + beat schedule + monitoring key on it) | high |
| app/workers/celery_app.py:507 | leadpilot | B | Celery task name / queue route (in-flight messages + beat schedule + monitoring key on it) | high |
| app/workers/champion_tasks.py:43 | leadpilot | B | Celery task name / queue route (in-flight messages + beat schedule + monitoring key on it) | high |
| app/workers/champion_tasks.py:56 | leadpilot | B | Celery task name / queue route (in-flight messages + beat schedule + monitoring key on it) | high |
| app/workers/lead_tasks.py:691 | leadpilot | B | Celery task name / queue route (in-flight messages + beat schedule + monitoring key on it) | high |
| app/workers/lead_tasks.py:696 | leadpilot | B | Celery task name / queue route (in-flight messages + beat schedule + monitoring key on it) | high |
| app/workers/lead_tasks.py:701 | leadpilot | B | Celery task name / queue route (in-flight messages + beat schedule + monitoring key on it) | high |
| app/workers/lead_tasks.py:706 | leadpilot | B | Celery task name / queue route (in-flight messages + beat schedule + monitoring key on it) | high |
| app/workers/lead_tasks.py:711 | leadpilot | B | Celery task name / queue route (in-flight messages + beat schedule + monitoring key on it) | high |
| app/workers/monitoring.py:32 | leadpilot | B | Celery task name / queue route (in-flight messages + beat schedule + monitoring key on it) | high |
| app/workers/monitoring.py:33 | leadpilot | B | Celery task name / queue route (in-flight messages + beat schedule + monitoring key on it) | high |
| app/workers/monitoring.py:35 | leadpilot | B | Celery task name / queue route (in-flight messages + beat schedule + monitoring key on it) | high |
| app/workers/monitoring.py:36 | leadpilot | B | Celery task name / queue route (in-flight messages + beat schedule + monitoring key on it) | high |
| app/workers/monitoring.py:37 | leadpilot | B | Celery task name / queue route (in-flight messages + beat schedule + monitoring key on it) | high |
| app/workers/monitoring.py:38 | leadpilot | B | Celery task name / queue route (in-flight messages + beat schedule + monitoring key on it) | high |
| app/workers/monitoring.py:39 | leadpilot | B | Celery task name / queue route (in-flight messages + beat schedule + monitoring key on it) | high |
| app/workers/monitoring.py:41 | leadpilot | B | Celery task name / queue route (in-flight messages + beat schedule + monitoring key on it) | high |
| app/workers/monitoring.py:42 | leadpilot | B | Celery task name / queue route (in-flight messages + beat schedule + monitoring key on it) | high |
| app/workers/network_tasks.py:21 | leadpilot | B | Celery task name / queue route (in-flight messages + beat schedule + monitoring key on it) | high |
| app/workers/network_tasks.py:32 | leadpilot | B | Celery task name / queue route (in-flight messages + beat schedule + monitoring key on it) | high |
| app/workers/network_tasks.py:119 | leadpilot | B | Celery task name / queue route (in-flight messages + beat schedule + monitoring key on it) | high |
| app/workers/network_tasks.py:132 | leadpilot | B | Celery task name / queue route (in-flight messages + beat schedule + monitoring key on it) | high |
| app/workers/outreach_tasks.py:1960 | leadpilot | B | Celery task name / queue route (in-flight messages + beat schedule + monitoring key on it) | high |
| app/workers/outreach_tasks.py:1969 | leadpilot | B | Celery task name / queue route (in-flight messages + beat schedule + monitoring key on it) | high |
| app/workers/outreach_tasks.py:1999 | leadpilot | B | Celery task name / queue route (in-flight messages + beat schedule + monitoring key on it) | high |
| app/workers/outreach_tasks.py:2350 | leadpilot | B | Celery task name / queue route (in-flight messages + beat schedule + monitoring key on it) | high |
| app/workers/outreach_tasks.py:2369 | leadpilot | B | Celery task name / queue route (in-flight messages + beat schedule + monitoring key on it) | high |
| app/workers/outreach_tasks.py:2470 | leadpilot | B | Celery task name / queue route (in-flight messages + beat schedule + monitoring key on it) | high |
| app/workers/outreach_tasks.py:2479 | leadpilot | B | Celery task name / queue route (in-flight messages + beat schedule + monitoring key on it) | high |
| app/workers/pilot_tasks.py:7 | Vectorae | A-comment | code comment/docstring | low |
| app/workers/plan_hold_tasks.py:24 | leadpilot | B | Celery task name / queue route (in-flight messages + beat schedule + monitoring key on it) | high |
| app/workers/quickstart_tasks.py:72 | leadpilot | B | Celery task name / queue route (in-flight messages + beat schedule + monitoring key on it) | high |
| app/workers/quickstart_tasks.py:93 | leadpilot | B | Celery task name / queue route (in-flight messages + beat schedule + monitoring key on it) | high |
| app/workers/site_tasks.py:34 | leadpilot | B | default export dir path | low |
| app/workers/tasks.py:89 | leadpilot | B | Celery task name / queue route (in-flight messages + beat schedule + monitoring key on it) | high |
| app/workers/tasks.py:95 | leadpilot | B | Celery task name / queue route (in-flight messages + beat schedule + monitoring key on it) | high |
| app/workers/tasks.py:209 | leadpilot | B | Celery task name / queue route (in-flight messages + beat schedule + monitoring key on it) | high |
| app/workers/tool_integration_tasks.py:11 | Vectorae | A-comment | code comment/docstring | low |
| app/workers/tool_integration_tasks.py:79 | Vectorae | A-comment | code comment/docstring | low |

## 3. File/dir names containing a variant

None under `app/` (`git ls-files app | grep -iE 'lead[ _.-]?pilot|client[ _.-]?hunter|vectorae'` is empty). Native modules `vectorae_native_rs` / `vectorae_native_cpp` are imported here but built from `native/` (outside this area).

## 4. Generated or git-ignored files

Only `app/**/__pycache__/` (bytecode, git-ignored) -- regenerated by any Python import; not inventoried. No generated templates or assets in `app/`.

## 5. Surprising findings

**DEFECTs (product name reaching prospects / customer-owned content)**
1. `app/services/website_builder.py:57,75,76,88` -- the page-generation prompt hard-codes `Product: Vectorae Enterprise`, `Also known as: Calendarharvest`, `Founder: Rehan Masood` and `title tag: ... | Vectorae Enterprise`. `app/api/website_builder.py` scopes pages by `workspace_id`, so a CUSTOMER workspace's generated pages are written as our marketing pages (our brand, our founder) on their site.
2. `app/config.py:106` -- default `SENDER_IDENTITY = "Vectorae User, 123 Main St, City, Country"` is appended as the CAN-SPAM footer of customer outreach (`app/services/sequence_engine.py:630`). Latent only: `production_guard.py` and `adversarial_review.py` block it in production, but they detect it by `"123 main st"`/`"city, country"`, not by the brand, so a rename does not weaken them.
- Borderline (classed C): `app/integrations/recall.py:154` -- the Recall.ai meeting bot joins the customer's sales calls as **"Vectorae Notetaker"**, visible to the prospect; the only caller (`app/services/meeting_recording.py:107`) never overrides `bot_name`.
- NOT defects (checked): every outreach writer prompt (`message_personalization`, `linkedin_outreach`, `meeting_followup`, `reply_copilot`, `loom_video`, `phone_calls`, `whatsapp_templates`, `autopilot`, `strategy_mutation`) uses "You are Vectorae's X writer" as role framing only; none asks the model to name the product. Only `displacement_monitor.py:74` has an output guard (`FORBIDDEN_MENTIONS = ("vectorae","leadpilot","lead pilot")`) -- it must gain `victorae` on rename, and the other writers have no such guard at all.

**Identifiers that must not be renamed casually (B, high/critical)**
- `app/services/audit_trail.py:311` HKDF salt `b"leadpilot-audit-trail"`: changing it breaks verification of every existing signed audit trail (critical).
- Webhook headers: outbound `X-LeadPilot-Event/-Delivery/-Signature` + legacy `X-ClientHunter-Signature` (`webhook_delivery.py:372-375`); inbound `X-LeadPilot-Signature`/`-Timestamp` (`api/calls.py:297`, `api/crm_integrations.py:286-287`, `api/linkedin.py:264`, `api/meetings.py:69`). The User-Agent is already `Vectorae-Webhooks/1.0` while the headers say LeadPilot.
- API key prefix `lpk_` (`services/api_keys.py:21`); OAuth/MCP scopes `leadpilot:read`/`leadpilot:write` (`mcp/scopes.py`, `services/oauth_server.py`); MCP `SERVER_NAME = "leadpilot"`.
- ~60 Celery task names `leadpilot.*` + Celery app name (`workers/*`, `celery_app.py`, `monitoring.py`): renaming orphans queued messages and beat entries.
- Persisted values: `leadpilot_calendar` channel/source (DB + webhook payloads), tutorial slugs `getting-started-with-leadpilot`/`using-the-leadpilot-dashboard` (DB `tutorial_progress.tutorial_slug`), badge `leadpilot-certified`, FAQ id `what-is-leadpilot` + help-center citation aliases, `LeadSource: "Vectorae"` written into customers' Salesforce, DNS TXT `_leadpilot-verify.<domain>` customers already published, export/report format ids (`leadpilot.activity-audit.v1`, `leadpilot.meetings-ledger.v1`, `leadpilot.pilot-verdict.v1`, `leadpilot-account-export`).
- Mobile: `ANDROID_PACKAGE_NAME = "io.clienthunter.app"`, deep-link scheme `clienthunter://`, App Links host `app.clienthunter.com` (marked "TODO: confirm production domain").
- Cookie `lp_refresh` (`config.py:181`, not matched by the regex): renaming logs every browser session out.
- Env var `VECTORAE_REQUIRE_NATIVE` and module names `vectorae_native_*` -- these are Vectorae-era identifiers; a move to Victorae would add new B items.

**Leftovers from the earlier rebrand (PR #113) -- display text still old**
- OpenAPI `title="ClientHunter Enterprise API"` (`main.py:173`) and root `GET /` name (`main.py:402`); module docstrings "ClientHunter Enterprise" (`main.py:2`, `core/logging.py:2`, `api/devices.py:2`, `services/notifications.py:2`). The OpenAPI description has no brand name.
- User-visible "LeadPilot": weekly pilot scorecard email (`pilot_mode.py:598`), meetings-ledger PDF title (`meetings_ledger.py:672`), download filenames `leadpilot-*.json/pdf/png` (6 places).
- `SITE_ORIGIN = "https://leadpilot.io"` (`sitemap.py:26`, `website_builder.py:39`) while the live domain is calendarharvest.com.

**Legal / third-party (C) needing a human**: voice-clone consent text (`voice_twin.py:78-85`, bump `CONSENT_VERSION`), LinkedIn risk disclosure (`daily_send_approval.py:95`, bump `LINKEDIN_WARNING_VERSION`), ElevenLabs voice name `Vectorae - <name>` (`voice_twin.py:836-839`; `:883-884` tells users to look for that name), Stripe product name (`stripe_billing.py:141`), Resend sender name `EMAIL_FROM_NAME` (`config.py:246`), Recall bot name, required trial-renewal notice (`billing.py:964`), HIPAA/DNC/TCPA disclaimers.

**Coupled strings**: `claim_verification.py:211` treats "Vectorae" as sender vocabulary and `help_center.py:182-190` alias targets are derived from doc headings containing "vectorae" -- both must change in lockstep with the brand/docs or tests (`tests/help_center/test_corpus.py`) fail. `ClientHunterError` (24 refs) is an internal base class: rename is a safe refactor but touches tests.

# Part 2 — Brand inventory: `frontend/` (excluding `frontend/android/` and `frontend/capacitor.config.ts`)

_Source: subagent sweep, file `brand-frontend.md`._

Read-only sweep of git-tracked files. Command: `git grep -nIiE 'lead[ _.-]?pilot|client[ _.-]?hunter|vectorae|lpk_|calendarharvest' -- frontend ':!frontend/android' ':!frontend/capacitor.config.ts'` (987 matching lines, 183 files), plus `git ls-files frontend | grep -iE ...` for names. No repo file was modified.

## 1. Summary

**Lines in table (excluding Calendarharvest-only lines): 959, in 176 files.** One row per matching line (a line with two hits is one row); homogeneous A rows collapsed where a file had more than 15 of the same reason. Every B, C and DEFECT row is on its own.

| Class | Lines |
|---|---|
| A (display, incl. A-comment and test-asserted copy) | 786 |
| B (identifier) | 134 |
| C (needs human) | 36 |
| DEFECT (customer-voice) | 3 |

Occurrences per variant (`git grep -o`, all of area):

| Variant | Occurrences | Note |
|---|---|---|
| Vectorae (incl. 2x `VECTORAE`) | 919 | current brand; mostly A copy |
| leadpilot / LeadPilot | 140 | almost all B: URL slugs, storage keys, media file names, header names, export filenames |
| clienthunter / ClientHunter | 59 | deep-link scheme (B), npm name (B), "ClientHunter Enterprise" file-header comments (A) |
| lpk_ | 5 | API key prefix (B) |
| Lead Pilot | 2 | refers to OTHER companies (disambiguation), C |
| Calendarharvest / calendarharvest | 97 | company/trading name + domain. Per the brief, not inventoried line-by-line (not used as a product name); see §6 |

Per-line variant x class (lines): Vectorae A 744 / B 33 (copy lines that also carry a slug) / C 28 / DEFECT 3; LeadPilot A 20 / B 95 / C 10; ClientHunter A 22 / B 37; lpk_ B 4; Lead Pilot C 2.

## 2. Occurrence table

| path:line | variant | class | reason | risk |
|---|---|---|---|---|
| `e2e/support-chat.spec.ts:26` | Vectorae | A | test asserts/uses display string (update with copy) | med |
| `e2e/support-chat.spec.ts:35` | LeadPilot, Vectorae | B | copy line that also links to public URL path/slug (/what-is-leadpilot/, /compare/leadpilot-vs-*/, help id); indexed by search engines/LLMs, sitemap; rename needs 301 redirects (test) | high |
| `e2e/support-chat.spec.ts:36` | Vectorae | A | test asserts/uses display string (update with copy) | med |
| `e2e/support-chat.spec.ts:37` | Vectorae | A | test asserts/uses display string (update with copy) | med |
| `e2e/support-chat.spec.ts:73` | Vectorae | A | test asserts/uses display string (update with copy) | med |
| `e2e/support-chat.spec.ts:183` | Vectorae | A | test asserts/uses display string (update with copy) | med |
| `e2e/support-chat.spec.ts:190` | Vectorae | A | test asserts/uses display string (update with copy) | med |
| `e2e/support-chat.spec.ts:191` | Vectorae | A | test asserts/uses display string (update with copy) | med |
| `e2e/support-chat.spec.ts:202` | Vectorae | A | test asserts/uses display string (update with copy) | med |
| `e2e/support-chat.spec.ts:205` | Vectorae | A | test asserts/uses display string (update with copy) | med |
| `e2e/support-chat.spec.ts:226` | Vectorae | A | test asserts/uses display string (update with copy) | med |
| `e2e/tutorials.spec.ts:2` | Vectorae | A | A-comment (code comment/docstring) | low |
| `e2e/tutorials.spec.ts:39` | LeadPilot, Vectorae | B | tutorial slug / badge id served by backend (app/services/tutorials.py, DB progress rows) (test fixture) | med |
| `e2e/tutorials.spec.ts:54` | LeadPilot, Vectorae | B | tutorial slug / badge id served by backend (app/services/tutorials.py, DB progress rows) (test fixture) | med |
| `e2e/tutorials.spec.ts:137` | LeadPilot, Vectorae | B | tutorial slug / badge id served by backend (app/services/tutorials.py, DB progress rows) (test fixture) | med |
| `e2e/tutorials.spec.ts:206` | Vectorae | A | test asserts/uses display string (update with copy) | med |
| `e2e/tutorials.spec.ts:232` | Vectorae | A | test asserts/uses display string (update with copy) | med |
| `e2e/tutorials.spec.ts:377` | LeadPilot | B | tutorial slug / badge id served by backend (app/services/tutorials.py, DB progress rows) (test fixture) | med |
| `e2e/tutorials.spec.ts:387` | LeadPilot | B | tutorial slug / badge id served by backend (app/services/tutorials.py, DB progress rows) (test fixture) | med |
| `e2e/tutorials.spec.ts:435` | LeadPilot | B | tutorial slug / badge id served by backend (app/services/tutorials.py, DB progress rows) (test fixture) | med |
| `e2e/tutorials.spec.ts:458` | LeadPilot | B | tutorial slug / badge id served by backend (app/services/tutorials.py, DB progress rows) (test fixture) | med |
| `next.config.js:22` | ClientHunter | A | A-comment (code comment/docstring) | low |
| `next.config.js:109` | LeadPilot | A | example API origin in developer-facing build-error text; api.leadpilot.com is LeadPilot AB's domain (not ours) | med |
| `package-lock.json:2` | ClientHunter | B | npm package name (package.json/package-lock) | low |
| `package-lock.json:8` | ClientHunter | B | npm package name (package.json/package-lock) | low |
| `package.json:2` | ClientHunter | B | npm package name (package.json/package-lock) | low |
| `public/.well-known/assetlinks.json:6` | ClientHunter | B | Android package_name in Digital Asset Links / docs; must match Play Store applicationId | high |
| `public/manifest.json:2` | Vectorae | A | PWA manifest name/short_name (installed-app label) | med |
| `public/manifest.json:3` | Vectorae | A | PWA manifest name/short_name (installed-app label) | med |
| `public/media/leadpilot-walkthrough.en.vtt:4` | LeadPilot | B | media file name /media/leadpilot-walkthrough.* (file path; og:image URL is public) | med |
| `public/media/leadpilot-walkthrough.en.vtt:14` | Vectorae | A | UI / public page display text | low |
| `public/media/leadpilot-walkthrough.en.vtt:34` | Vectorae | A | UI / public page display text | low |
| `scripts/generate-assets.cmd:2` | ClientHunter | A | A-comment (code comment/docstring) | low |
| `scripts/generate-assets.sh:2` | ClientHunter | A | A-comment (code comment/docstring) | low |
| `scripts/seo/snapshot_plans.mjs:26` | LeadPilot | B | API host / Render service name (leadpilot-api) | med |
| `scripts/static-server.js:5` | ClientHunter | A | A-comment (code comment/docstring) | low |
| `src/app/(admin)/admin/compliance-rules/page.tsx:211` | Vectorae | A | UI / public page display text | low |
| `src/app/(app)/analytics/page.tsx:185` | Vectorae | A | A-comment (code comment/docstring) | low |
| `src/app/(app)/analytics/revenue/page.tsx:116` | Vectorae | A | UI / public page display text | low |
| `src/app/(app)/learn/page.tsx:4` | Vectorae | A | A-comment (code comment/docstring) | low |
| `src/app/(app)/learn/page.tsx:106` | Vectorae | A | UI / public page display text | low |
| `src/app/(app)/pilot/page.tsx:204` | Vectorae | A | UI / public page display text | low |
| `src/app/(app)/pipeline/page.tsx:46` | LeadPilot | B | A-comment naming old localStorage key (mentions removed/legacy key) | low |
| `src/app/(app)/profile/page.tsx:195` | Vectorae | A | UI / public page display text | low |
| `src/app/(app)/send-approval/page.tsx:6` | Vectorae | A | A-comment (code comment/docstring) | low |
| `src/app/(app)/send-approval/page.tsx:109` | Vectorae | A | UI / public page display text | low |
| `src/app/(app)/send-approval/page.tsx:110` | Vectorae | A | UI / public page display text | low |
| `src/app/(app)/strategies/new/page.tsx:123` | Vectorae | A | UI / public page display text | low |
| `src/app/(app)/team/page.tsx:386` | Vectorae | A | UI / public page display text | low |
| `src/app/(auth)/signup/page.tsx:49` | Vectorae | A | UI / public page display text | low |
| `src/app/about/page.tsx:18` | Vectorae | A | page <title>/meta | med |
| `src/app/about/page.tsx:27` | Vectorae | A | UI / public page display text | low |
| `src/app/about/page.tsx:35` | Vectorae | A | UI / public page display text | low |
| `src/app/about/page.tsx:86` | Vectorae | A | UI / public page display text | low |
| `src/app/about/page.tsx:130` | Vectorae | A | UI / public page display text | low |
| `src/app/about/page.tsx:166` | Vectorae | A | UI / public page display text | low |
| `src/app/book/page.tsx:312` | Vectorae | A | prospect/third-party-facing "by Vectorae" attribution (seen by customers' prospects; white-label consideration) | med |
| `src/app/compare/[slug]/page.tsx:2` | LeadPilot | A | A-comment mentioning URL slug/path (the slug itself is B elsewhere) | low |
| `src/app/compare/[slug]/page.tsx:17` | LeadPilot | B | public URL path/slug (/what-is-leadpilot/, /compare/leadpilot-vs-*/, help id); indexed by search engines/LLMs, sitemap; rename needs 301 redirects | high |
| `src/app/compare/[slug]/page.tsx:37` | Vectorae | A | JSON-LD breadcrumb name | med |
| `src/app/compare/[slug]/page.tsx:46` | Vectorae | A | UI / public page display text | low |
| `src/app/compare/[slug]/page.tsx:48` | Vectorae | A | UI / public page display text | low |
| `src/app/compare/page.tsx:15` | Vectorae | A | page <title>/meta | med |
| `src/app/compare/page.tsx:17` | Vectorae | A | page meta description | low |
| `src/app/compare/page.tsx:27` | Vectorae | A | UI / public page display text | low |
| `src/app/compare/page.tsx:29` | Vectorae | A | UI / public page display text | low |
| `src/app/compare/page.tsx:41` | Vectorae | A | UI / public page display text | low |
| `src/app/compare/page.tsx:42` | Vectorae | A | UI / public page display text | low |
| `src/app/compare/page.tsx:49` | LeadPilot, Vectorae | B | copy line that also links to public URL path/slug (/what-is-leadpilot/, /compare/leadpilot-vs-*/, help id); indexed by search engines/LLMs, sitemap; rename needs 301 redirects | high |
| `src/app/compare/page.tsx:50` | Vectorae | A | UI / public page display text | low |
| `src/app/contact/page.tsx:18` | Vectorae | A | page <title>/meta | med |
| `src/app/contact/page.tsx:26` | LeadPilot | C | third-party listing URL (LinkedIn/G2/Crunchbase/YouTube) in JSON-LD sameAs / contact page; owner must rename listing, URL is B | high |
| `src/app/contact/page.tsx:35` | Vectorae | A | UI / public page display text | low |
| `src/app/contact/page.tsx:45` | Vectorae | A | UI / public page display text | low |
| `src/app/contact/page.tsx:62` | Vectorae | A | UI / public page display text | low |
| `src/app/contact/page.tsx:104` | Vectorae | A | UI / public page display text | low |
| `src/app/contact/page.tsx:136` | Vectorae | A | UI / public page display text | low |
| `src/app/contact/page.tsx:212` | Vectorae | A | UI / public page display text | low |
| `src/app/faq/page.tsx:17` | Vectorae | A | page <title>/meta | med |
| `src/app/faq/page.tsx:36` | LeadPilot, Vectorae | B | copy line that also links to public URL path/slug (/what-is-leadpilot/, /compare/leadpilot-vs-*/, help id); indexed by search engines/LLMs, sitemap; rename needs 301 redirects | high |
| `src/app/faq/page.tsx:38` | Vectorae | A | UI / public page display text | low |
| `src/app/help/[slug]/page.tsx:30` | Vectorae | A | page <title>/meta | med |
| `src/app/help/[slug]/page.tsx:48` | Vectorae | A | UI / public page display text | low |
| `src/app/help/page.tsx:16` | Vectorae | A | page <title>/meta | med |
| `src/app/how-it-works/page.tsx:17` | Vectorae | A | page <title>/meta | med |
| `src/app/how-it-works/page.tsx:27` | Vectorae | A | UI / public page display text | low |
| `src/app/how-it-works/page.tsx:37` | Vectorae | A | UI / public page display text | low |
| `src/app/how-it-works/page.tsx:85` | Vectorae | A | UI / public page display text | low |
| `src/app/how-it-works/page.tsx:116` | Vectorae | A | UI / public page display text | low |
| `src/app/layout.tsx:2` | ClientHunter | A | A-comment (code comment/docstring) | low |
| `src/app/layout.tsx:32` | Vectorae | A | page <title>/meta | med |
| `src/app/oauth/consent/page.tsx:3` | Vectorae | A | A-comment | low |
| `src/app/oauth/consent/page.tsx:61` | Vectorae | C | OAuth connector consent screen text | high |
| `src/app/oauth/consent/page.tsx:80` | Vectorae | C | OAuth connector consent screen text | high |
| `src/app/outbound-statistics/page.tsx:15` | Vectorae | A | page <title>/meta | med |
| `src/app/outbound-statistics/page.tsx:31` | Vectorae | A | UI / public page display text | low |
| `src/app/outbound-statistics/page.tsx:32` | LeadPilot, Vectorae | B | copy line that also links to public URL path/slug (/what-is-leadpilot/, /compare/leadpilot-vs-*/, help id); indexed by search engines/LLMs, sitemap; rename needs 301 redirects | high |
| `src/app/page.tsx:25` | Vectorae | A | page <title>/meta | med |
| `src/app/page.tsx:30` | LeadPilot | B | media file name /media/leadpilot-walkthrough.* (file path; og:image URL is public) | med |
| `src/app/pricing/PricingClient.tsx:162` | Vectorae | A | UI / public page display text | low |
| `src/app/pricing/PricingClient.tsx:178` | Vectorae | A | UI / public page display text | low |
| `src/app/pricing/page.tsx:24` | Vectorae | A | page <title>/meta | med |
| `src/app/privacy/page.tsx:32` | Vectorae | C | legal text (Terms/Privacy) names the product/"Vectorae Enterprise"; legal review needed | high |
| `src/app/privacy/page.tsx:57` | Vectorae | C | legal text (Terms/Privacy) names the product/"Vectorae Enterprise"; legal review needed | high |
| `src/app/privacy/page.tsx:60` | Vectorae | C | legal text (Terms/Privacy) names the product/"Vectorae Enterprise"; legal review needed | high |
| `src/app/privacy/page.tsx:97` | Vectorae | C | legal text (Terms/Privacy) names the product/"Vectorae Enterprise"; legal review needed | high |
| `src/app/privacy/page.tsx:218` | Vectorae | C | legal text (Terms/Privacy) names the product/"Vectorae Enterprise"; legal review needed | high |
| `src/app/privacy/page.tsx:219` | Vectorae | C | legal text (Terms/Privacy) names the product/"Vectorae Enterprise"; legal review needed | high |
| `src/app/privacy/page.tsx:265` | Vectorae | C | legal text (Terms/Privacy) names the product/"Vectorae Enterprise"; legal review needed | high |
| `src/app/share/roi/page.tsx:132` | Vectorae | A | prospect/third-party-facing "by Vectorae" attribution (seen by customers' prospects; white-label consideration) | med |
| `src/app/status/page.tsx:10` | Vectorae | A | A-comment (code comment/docstring) | low |
| `src/app/status/page.tsx:21` | Vectorae | A | page <title>/meta | med |
| `src/app/status/page.tsx:23` | Vectorae | A | UI / public page display text | low |
| `src/app/status/page.tsx:34` | Vectorae | A | UI / public page display text | low |
| `src/app/status/page.tsx:36` | Vectorae | A | UI / public page display text | low |
| `src/app/status/page.tsx:37` | Vectorae | A | UI / public page display text | low |
| `src/app/status/page.tsx:65` | Vectorae | A | UI / public page display text | low |
| `src/app/terms/page.tsx:17` | Vectorae | C | legal text (Terms/Privacy) names the product/"Vectorae Enterprise"; legal review needed | high |
| `src/app/terms/page.tsx:44` | Vectorae | C | legal text (Terms/Privacy) names the product/"Vectorae Enterprise"; legal review needed | high |
| `src/app/terms/page.tsx:46` | Vectorae | C | legal text (Terms/Privacy) names the product/"Vectorae Enterprise"; legal review needed | high |
| `src/app/terms/page.tsx:56` | Vectorae | C | legal text (Terms/Privacy) names the product/"Vectorae Enterprise"; legal review needed | high |
| `src/app/terms/page.tsx:69` | Vectorae | C | legal text (Terms/Privacy) names the product/"Vectorae Enterprise"; legal review needed | high |
| `src/app/terms/page.tsx:71` | Vectorae | C | legal text (Terms/Privacy) names the product/"Vectorae Enterprise"; legal review needed | high |
| `src/app/terms/page.tsx:85` | Vectorae | C | legal text (Terms/Privacy) names the product/"Vectorae Enterprise"; legal review needed | high |
| `src/app/terms/page.tsx:107` | Vectorae | C | legal text (Terms/Privacy) names the product/"Vectorae Enterprise"; legal review needed | high |
| `src/app/terms/page.tsx:130` | Vectorae | C | legal text (Terms/Privacy) names the product/"Vectorae Enterprise"; legal review needed | high |
| `src/app/terms/page.tsx:175` | Vectorae | C | legal text (Terms/Privacy) names the product/"Vectorae Enterprise"; legal review needed | high |
| `src/app/terms/page.tsx:212` | Vectorae | C | legal text (Terms/Privacy) names the product/"Vectorae Enterprise"; legal review needed | high |
| `src/app/what-is-leadpilot/page.tsx:2` | LeadPilot | A | A-comment mentioning URL slug/path (the slug itself is B elsewhere) | low |
| `src/app/what-is-leadpilot/page.tsx:16` | Vectorae | A | page <title>/meta | med |
| `src/app/what-is-leadpilot/page.tsx:18` | LeadPilot | B | public URL path/slug (/what-is-leadpilot/, /compare/leadpilot-vs-*/, help id); indexed by search engines/LLMs, sitemap; rename needs 301 redirects | high |
| `src/app/what-is-leadpilot/page.tsx:21` | Vectorae | A | UI / public page display text | low |
| `src/app/what-is-leadpilot/page.tsx:24` | LeadPilot, Vectorae | B | copy line that also links to public URL path/slug (/what-is-leadpilot/, /compare/leadpilot-vs-*/, help id); indexed by search engines/LLMs, sitemap; rename needs 301 redirects | high |
| `src/app/what-is-leadpilot/page.tsx:31` | Vectorae | A | UI / public page display text | low |
| `src/app/what-is-leadpilot/page.tsx:32` | Vectorae | A | UI / public page display text | low |
| `src/components/Footer.tsx:37` | LeadPilot | B | public URL path/slug (/what-is-leadpilot/, /compare/leadpilot-vs-*/, help id); indexed by search engines/LLMs, sitemap; rename needs 301 redirects | high |
| `src/components/Footer.tsx:38` | LeadPilot | B | public URL path/slug (/what-is-leadpilot/, /compare/leadpilot-vs-*/, help id); indexed by search engines/LLMs, sitemap; rename needs 301 redirects | high |
| `src/components/Footer.tsx:39` | LeadPilot | B | public URL path/slug (/what-is-leadpilot/, /compare/leadpilot-vs-*/, help id); indexed by search engines/LLMs, sitemap; rename needs 301 redirects | high |
| `src/components/Footer.tsx:40` | LeadPilot | B | public URL path/slug (/what-is-leadpilot/, /compare/leadpilot-vs-*/, help id); indexed by search engines/LLMs, sitemap; rename needs 301 redirects | high |
| `src/components/Footer.tsx:41` | LeadPilot | B | public URL path/slug (/what-is-leadpilot/, /compare/leadpilot-vs-*/, help id); indexed by search engines/LLMs, sitemap; rename needs 301 redirects | high |
| `src/components/Footer.tsx:48` | LeadPilot, Vectorae | B | copy line that also links to public URL path/slug (/what-is-leadpilot/, /compare/leadpilot-vs-*/, help id); indexed by search engines/LLMs, sitemap; rename needs 301 redirects | high |
| `src/components/analytics/BenchmarkPanel.tsx:3` | Vectorae | A | A-comment (code comment/docstring) | low |
| `src/components/calls/CallHistory.tsx:199` | Vectorae | A | UI / public page display text | low |
| `src/components/campaigns/TemplateEditor.tsx:70` | Vectorae | DEFECT | WhatsApp template example in product name: customer-voice placeholder "Sam from Vectorae" a customer may copy into messages they send | high |
| `src/components/content/ContentPage.tsx:180` | Vectorae | A | UI / public page display text | low |
| `src/components/home/HomeHeader.tsx:45` | Vectorae | A | UI / public page display text | low |
| `src/components/home/HomePage.tsx:97` | Vectorae | A | UI / public page display text | low |
| `src/components/home/HomeVideo.tsx:4` | LeadPilot | B | media file name /media/leadpilot-walkthrough.* (file path; og:image URL is public) | med |
| `src/components/home/StageStepper.tsx:35` | Vectorae | A | UI / public page display text | low |
| `src/components/home/content.ts:21` | Vectorae | A | page <title>/meta | med |
| `src/components/home/content.ts:23` | Vectorae | A | UI / public page display text | low |
| `src/components/home/content.ts:42` | Vectorae | A | UI / public page display text | low |
| `src/components/home/content.ts:54` | LeadPilot | B | media file name /media/leadpilot-walkthrough.* (file path; og:image URL is public) | med |
| `src/components/home/content.ts:55` | LeadPilot | B | media file name /media/leadpilot-walkthrough.* (file path; og:image URL is public) | med |
| `src/components/home/content.ts:56` | LeadPilot | B | media file name /media/leadpilot-walkthrough.* (file path; og:image URL is public) | med |
| `src/components/home/content.ts:57` | LeadPilot | B | media file name /media/leadpilot-walkthrough.* (file path; og:image URL is public) | med |
| `src/components/home/content.ts:58` | Vectorae | A | UI / public page display text | low |
| `src/components/home/content.ts:60` | LeadPilot | B | media file name /media/leadpilot-walkthrough.* (file path; og:image URL is public) | med |
| `src/components/home/content.ts:63` | Vectorae | A | UI / public page display text | low |
| `src/components/home/content.ts:68` | Vectorae | A | UI / public page display text | low |
| `src/components/home/content.ts:79` | Vectorae | A | A-comment (code comment/docstring) | low |
| `src/components/home/content.ts:90` | Vectorae | A | UI / public page display text | low |
| `src/components/home/content.ts:102` | Vectorae | A | UI / public page display text | low |
| `src/components/home/content.ts:114` | Vectorae | A | UI / public page display text | low |
| `src/components/home/content.ts:137` | Vectorae | A | UI / public page display text | low |
| `src/components/home/content.ts:147` | Vectorae | A | UI / public page display text | low |
| `src/components/home/content.ts:349` | Vectorae | A | UI / public page display text | low |
| `src/components/home/content.ts:354` | Vectorae | A | UI / public page display text | low |
| `src/components/home/content.ts:362` | Vectorae | A | UI / public page display text | low |
| `src/components/inbox/ReplyCopilotPanel.tsx:9` | Vectorae | A | A-comment (code comment/docstring) | low |
| `src/components/leads/ChampionPanel.tsx:7` | Vectorae | A | A-comment (code comment/docstring) | low |
| `src/components/leads/MeetingPrepPanel.tsx:33` | LeadPilot, Vectorae | B | meeting source enum value from backend API (DB/webhook payload value) | high |
| `src/components/meetings/PlatformLauncher.tsx:5` | Vectorae | A | A-comment (code comment/docstring) | low |
| `src/components/meetings/PlatformLauncher.tsx:95` | Vectorae | A | UI / public page display text | low |
| `src/components/providers/NativeProvider.tsx:4` | ClientHunter | A | A-comment (code comment/docstring) | low |
| `src/components/settings/GuardrailsCard.tsx:178` | Vectorae | A | UI / public page display text | low |
| `src/components/settings/LinkedInAccountsCard.tsx:7` | Vectorae | A | A-comment (code comment/docstring) | low |
| `src/components/settings/SlackCard.tsx:3` | Vectorae | A | A-comment (code comment/docstring) | low |
| `src/components/settings/SlackCard.tsx:102` | Vectorae | A | UI / public page display text | low |
| `src/components/settings/VoiceTwinCard.tsx:150` | Vectorae | C | voice-twin data handling / disclosure statement in consent flow | high |
| `src/components/settings/VoiceTwinCard.tsx:202` | Vectorae | A | UI / public page display text | low |
| `src/components/settings/VoiceTwinCard.tsx:233` | Vectorae | C | voice-twin data handling / disclosure statement in consent flow | high |
| `src/components/settings/VoiceTwinCard.tsx:312` | Vectorae | C | voice-twin data handling / disclosure statement in consent flow | high |
| `src/components/settings/VoiceTwinCard.tsx:380` | Vectorae | A | UI / public page display text | low |
| `src/components/settings/WebhooksCard.tsx:146` | LeadPilot | B | webhook header name customers verify (X-LeadPilot-*/X-ClientHunter-*) shown in UI/docs | high |
| `src/components/settings/WebhooksCard.tsx:240` | lpk_ | B | API key prefix lpk_ (customer integrations/secret scanners depend on it) | high |
| `src/components/status/StatusBoard.tsx:210` | Vectorae | A | UI / public page display text | low |
| `src/components/status/StatusBoard.tsx:226` | Vectorae | A | UI / public page display text | low |
| `src/components/strategy/OutreachPanel.tsx:176` | Vectorae | A | UI / public page display text | low |
| `src/components/support/ChatWidget.tsx:213` | Vectorae | A | UI / public page display text | low |
| `src/components/support/ChatWidget.tsx:219` | Vectorae | A | UI / public page display text | low |
| `src/components/support/ChatWidget.tsx:282` | Vectorae | A | UI / public page display text | low |
| `src/components/ui/Logo.tsx:5` | Vectorae | C | logo/wordmark (alt text; artwork public/brand/logo-full.png contains "VECTORAE") | high |
| `src/components/ui/Logo.tsx:39` | Vectorae | C | logo/wordmark (alt text; artwork public/brand/logo-full.png contains "VECTORAE") | high |
| `src/components/ui/Logo.tsx:61` | Vectorae | C | logo/wordmark (alt text; artwork public/brand/logo-full.png contains "VECTORAE") | high |
| `src/components/ui/OfflineBanner.tsx:4` | ClientHunter | A | A-comment (code comment/docstring) | low |
| `src/components/ui/OfflineBanner.tsx:16` | Vectorae | A | A-comment (code comment/docstring) | low |
| `src/components/ui/OfflineBanner.tsx:42` | Vectorae | A | UI / public page display text | low |
| `src/components/ui/OfflineBanner.tsx:48` | Vectorae | A | UI / public page display text | low |
| `src/content/geo/compare.ts:2` | LeadPilot | A | A-comment mentioning URL slug/path (the slug itself is B elsewhere) | low |
| `src/content/geo/compare.ts:L29-469` (49 occurrences) | Vectorae | A | public GEO page copy | low |
| `src/content/geo/compare.ts:61` | Vectorae | A | page <title>/meta | med |
| `src/content/geo/compare.ts:147` | Vectorae | A | page <title>/meta | med |
| `src/content/geo/compare.ts:232` | Vectorae | A | page <title>/meta | med |
| `src/content/geo/compare.ts:313` | Vectorae | A | page <title>/meta | med |
| `src/content/geo/compare.ts:393` | Vectorae | A | page <title>/meta | med |
| `src/content/geo/compare.ts:494` | LeadPilot | B | public URL path/slug (/what-is-leadpilot/, /compare/leadpilot-vs-*/, help id); indexed by search engines/LLMs, sitemap; rename needs 301 redirects | high |
| `src/content/geo/faq.ts:L24-68` (23 occurrences) | Vectorae | A | public GEO page copy | low |
| `src/content/geo/faq.ts:27` | LeadPilot, Vectorae | B | copy line that also links to public URL path/slug (/what-is-leadpilot/, /compare/leadpilot-vs-*/, help id); indexed by search engines/LLMs, sitemap; rename needs 301 redirects | high |
| `src/content/geo/faq.ts:28` | Lead Pilot, LeadPilot, Vectorae | C | refers to a DIFFERENT company (LeadPilot AB, leadpilot.com) in disambiguation text; must NOT be renamed blindly | high |
| `src/content/geo/faq.ts:50` | LeadPilot, Vectorae | B | copy line that also links to public URL path/slug (/what-is-leadpilot/, /compare/leadpilot-vs-*/, help id); indexed by search engines/LLMs, sitemap; rename needs 301 redirects | high |
| `src/content/geo/faq.ts:52` | LeadPilot, Vectorae | B | copy line that also links to public URL path/slug (/what-is-leadpilot/, /compare/leadpilot-vs-*/, help id); indexed by search engines/LLMs, sitemap; rename needs 301 redirects | high |
| `src/content/geo/faq.ts:53` | LeadPilot, Vectorae | B | copy line that also links to public URL path/slug (/what-is-leadpilot/, /compare/leadpilot-vs-*/, help id); indexed by search engines/LLMs, sitemap; rename needs 301 redirects | high |
| `src/content/geo/forPages.ts:4` | LeadPilot | A | A-comment pointing at docs/ source file path (path dependency) | low |
| `src/content/geo/forPages.ts:L32-228` (32 occurrences) | Vectorae | A | public GEO page copy | low |
| `src/content/geo/forPages.ts:56` | Vectorae | A | page <title>/meta | med |
| `src/content/geo/forPages.ts:87` | LeadPilot, Vectorae | B | copy line that also links to public URL path/slug (/what-is-leadpilot/, /compare/leadpilot-vs-*/, help id); indexed by search engines/LLMs, sitemap; rename needs 301 redirects | high |
| `src/content/geo/forPages.ts:93` | LeadPilot, Vectorae | B | copy line that also links to public URL path/slug (/what-is-leadpilot/, /compare/leadpilot-vs-*/, help id); indexed by search engines/LLMs, sitemap; rename needs 301 redirects | high |
| `src/content/geo/forPages.ts:101` | LeadPilot, Vectorae | B | copy line that also links to public URL path/slug (/what-is-leadpilot/, /compare/leadpilot-vs-*/, help id); indexed by search engines/LLMs, sitemap; rename needs 301 redirects | high |
| `src/content/geo/forPages.ts:102` | LeadPilot, Vectorae | B | copy line that also links to public URL path/slug (/what-is-leadpilot/, /compare/leadpilot-vs-*/, help id); indexed by search engines/LLMs, sitemap; rename needs 301 redirects | high |
| `src/content/geo/forPages.ts:103` | LeadPilot, Vectorae | B | copy line that also links to public URL path/slug (/what-is-leadpilot/, /compare/leadpilot-vs-*/, help id); indexed by search engines/LLMs, sitemap; rename needs 301 redirects | high |
| `src/content/geo/forPages.ts:110` | Vectorae | A | page <title>/meta | med |
| `src/content/geo/forPages.ts:148` | LeadPilot, Vectorae | B | copy line that also links to public URL path/slug (/what-is-leadpilot/, /compare/leadpilot-vs-*/, help id); indexed by search engines/LLMs, sitemap; rename needs 301 redirects | high |
| `src/content/geo/forPages.ts:154` | LeadPilot, Vectorae | B | copy line that also links to public URL path/slug (/what-is-leadpilot/, /compare/leadpilot-vs-*/, help id); indexed by search engines/LLMs, sitemap; rename needs 301 redirects | high |
| `src/content/geo/forPages.ts:162` | LeadPilot, Vectorae | B | copy line that also links to public URL path/slug (/what-is-leadpilot/, /compare/leadpilot-vs-*/, help id); indexed by search engines/LLMs, sitemap; rename needs 301 redirects | high |
| `src/content/geo/forPages.ts:163` | LeadPilot, Vectorae | B | copy line that also links to public URL path/slug (/what-is-leadpilot/, /compare/leadpilot-vs-*/, help id); indexed by search engines/LLMs, sitemap; rename needs 301 redirects | high |
| `src/content/geo/forPages.ts:171` | Vectorae | A | page <title>/meta | med |
| `src/content/geo/forPages.ts:226` | LeadPilot, Vectorae | B | copy line that also links to public URL path/slug (/what-is-leadpilot/, /compare/leadpilot-vs-*/, help id); indexed by search engines/LLMs, sitemap; rename needs 301 redirects | high |
| `src/content/geo/shared.ts:46` | Vectorae | A | public GEO page copy | low |
| `src/content/geo/shared.ts:52` | LeadPilot, Vectorae | C | refers to a DIFFERENT company (LeadPilot AB, leadpilot.com) in disambiguation text; must NOT be renamed blindly | high |
| `src/content/geo/shared.ts:53` | Lead Pilot, LeadPilot | C | refers to a DIFFERENT company (LeadPilot AB, leadpilot.com) in disambiguation text; must NOT be renamed blindly | high |
| `src/content/geo/shared.ts:80` | Vectorae | A | public GEO page copy | low |
| `src/content/geo/statistics.ts:4` | Vectorae | A | A-comment (code comment/docstring) | low |
| `src/content/geo/statistics.ts:13` | Vectorae | A | public GEO page copy | low |
| `src/content/geo/statistics.ts:38` | Vectorae | A | public GEO page copy | low |
| `src/content/geo/statistics.ts:99` | Vectorae | A | public GEO page copy | low |
| `src/content/geo/statistics.ts:108` | Vectorae | A | public GEO page copy | low |
| `src/content/geo/whatIs.ts:2` | LeadPilot | A | A-comment pointing at docs/ source file path (path dependency) | low |
| `src/content/geo/whatIs.ts:11` | Vectorae | A | public GEO page copy | low |
| `src/content/geo/whatIs.ts:15` | Vectorae | A | public GEO page copy | low |
| `src/content/geo/whatIs.ts:20` | Vectorae | A | public GEO page copy | low |
| `src/content/geo/whatIs.ts:28` | Vectorae | A | public GEO page copy | low |
| `src/content/geo/whatIs.ts:31` | Vectorae | A | public GEO page copy | low |
| `src/content/geo/whatIs.ts:37` | Vectorae | A | public GEO page copy | low |
| `src/content/geo/whatIs.ts:39` | Vectorae | A | public GEO page copy | low |
| `src/content/geo/whatIs.ts:44` | Vectorae | A | public GEO page copy | low |
| `src/content/geo/whatIs.ts:48` | Vectorae | A | public GEO page copy | low |
| `src/content/geo/whatIs.ts:57` | LeadPilot | B | public URL path/slug (/what-is-leadpilot/, /compare/leadpilot-vs-*/, help id); indexed by search engines/LLMs, sitemap; rename needs 301 redirects | high |
| `src/content/geo/whatIs.ts:69` | Vectorae | A | public GEO page copy | low |
| `src/content/geo/whatIs.ts:70` | Vectorae | A | public GEO page copy | low |
| `src/content/geo/whatIs.ts:74` | Vectorae | A | public GEO page copy | low |
| `src/content/help-center/01-what-is-leadpilot.md:2` | LeadPilot | B | public URL path/slug (/what-is-leadpilot/, /compare/leadpilot-vs-*/, help id); indexed by search engines/LLMs, sitemap; rename needs 301 redirects | high |
| `src/content/help-center/01-what-is-leadpilot.md:3` | Vectorae | A | page <title>/meta | med |
| `src/content/help-center/01-what-is-leadpilot.md:L39-89` (16 occurrences) | Vectorae | A | help-center article copy (also served via backend support KB) | low |
| `src/content/help-center/02-who-its-for-and-not-for.md:3` | Vectorae | A | page <title>/meta | med |
| `src/content/help-center/02-who-its-for-and-not-for.md:L37-112` (23 occurrences) | Vectorae | A | help-center article copy (also served via backend support KB) | low |
| `src/content/help-center/02-who-its-for-and-not-for.md:115` | LeadPilot, Vectorae | B | link/ref to help-center filename 01-what-is-leadpilot.md (file rename breaks link; backend help_center/support_kb also read these files) | med |
| `src/content/help-center/03-getting-started.md:3` | Vectorae | A | page <title>/meta | med |
| `src/content/help-center/03-getting-started.md:51` | Vectorae | A | help-center article copy (also served via backend support KB) | low |
| `src/content/help-center/03-getting-started.md:61` | Vectorae | A | help-center article copy (also served via backend support KB) | low |
| `src/content/help-center/03-getting-started.md:62` | Vectorae | A | help-center article copy (also served via backend support KB) | low |
| `src/content/help-center/03-getting-started.md:68` | Vectorae | A | help-center article copy (also served via backend support KB) | low |
| `src/content/help-center/03-getting-started.md:78` | Vectorae | A | help-center article copy (also served via backend support KB) | low |
| `src/content/help-center/03-getting-started.md:80` | Vectorae | A | help-center article copy (also served via backend support KB) | low |
| `src/content/help-center/03-getting-started.md:84` | Vectorae | A | A-comment (code comment/docstring) | low |
| `src/content/help-center/03-getting-started.md:86` | Vectorae | A | A-comment (code comment/docstring) | low |
| `src/content/help-center/03-getting-started.md:94` | Vectorae | A | help-center article copy (also served via backend support KB) | low |
| `src/content/help-center/03-getting-started.md:98` | Vectorae | A | help-center article copy (also served via backend support KB) | low |
| `src/content/help-center/03-getting-started.md:113` | Vectorae | A | help-center article copy (also served via backend support KB) | low |
| `src/content/help-center/03-getting-started.md:117` | Vectorae | A | help-center article copy (also served via backend support KB) | low |
| `src/content/help-center/03-getting-started.md:131` | Vectorae | A | help-center article copy (also served via backend support KB) | low |
| `src/content/help-center/04-research-pipeline.md:32` | Vectorae | A | help-center article copy (also served via backend support KB) | low |
| `src/content/help-center/04-research-pipeline.md:40` | Vectorae | A | help-center article copy (also served via backend support KB) | low |
| `src/content/help-center/04-research-pipeline.md:57` | Vectorae | A | help-center article copy (also served via backend support KB) | low |
| `src/content/help-center/04-research-pipeline.md:59` | Vectorae | A | help-center article copy (also served via backend support KB) | low |
| `src/content/help-center/04-research-pipeline.md:76` | Vectorae | A | help-center article copy (also served via backend support KB) | low |
| `src/content/help-center/04-research-pipeline.md:79` | Vectorae | A | help-center article copy (also served via backend support KB) | low |
| `src/content/help-center/04-research-pipeline.md:80` | Vectorae | A | help-center article copy (also served via backend support KB) | low |
| `src/content/help-center/05-strategy-verification.md:26` | Vectorae | A | help-center article copy (also served via backend support KB) | low |
| `src/content/help-center/05-strategy-verification.md:30` | Vectorae | A | help-center article copy (also served via backend support KB) | low |
| `src/content/help-center/05-strategy-verification.md:33` | Vectorae | A | help-center article copy (also served via backend support KB) | low |
| `src/content/help-center/05-strategy-verification.md:37` | Vectorae | A | help-center article copy (also served via backend support KB) | low |
| `src/content/help-center/05-strategy-verification.md:62` | Vectorae | A | help-center article copy (also served via backend support KB) | low |
| `src/content/help-center/05-strategy-verification.md:63` | Vectorae | A | help-center article copy (also served via backend support KB) | low |
| `src/content/help-center/05-strategy-verification.md:86` | Vectorae | A | help-center article copy (also served via backend support KB) | low |
| `src/content/help-center/05-strategy-verification.md:105` | Vectorae | A | help-center article copy (also served via backend support KB) | low |
| `src/content/help-center/06-lead-sourcing-and-email-verification.md:49` | Vectorae | A | help-center article copy (also served via backend support KB) | low |
| `src/content/help-center/06-lead-sourcing-and-email-verification.md:53` | Vectorae | A | help-center article copy (also served via backend support KB) | low |
| `src/content/help-center/06-lead-sourcing-and-email-verification.md:57` | Vectorae | A | help-center article copy (also served via backend support KB) | low |
| `src/content/help-center/06-lead-sourcing-and-email-verification.md:65` | Vectorae | A | help-center article copy (also served via backend support KB) | low |
| `src/content/help-center/06-lead-sourcing-and-email-verification.md:101` | Vectorae | A | help-center article copy (also served via backend support KB) | low |
| `src/content/help-center/06-lead-sourcing-and-email-verification.md:111` | Vectorae | A | help-center article copy (also served via backend support KB) | low |
| `src/content/help-center/06-lead-sourcing-and-email-verification.md:126` | Vectorae | A | help-center article copy (also served via backend support KB) | low |
| `src/content/help-center/07-personalization-and-claim-verification.md:34` | Vectorae | A | help-center article copy (also served via backend support KB) | low |
| `src/content/help-center/07-personalization-and-claim-verification.md:38` | Vectorae | A | help-center article copy (also served via backend support KB) | low |
| `src/content/help-center/07-personalization-and-claim-verification.md:47` | Vectorae | A | help-center article copy (also served via backend support KB) | low |
| `src/content/help-center/07-personalization-and-claim-verification.md:49` | Vectorae | A | help-center article copy (also served via backend support KB) | low |
| `src/content/help-center/07-personalization-and-claim-verification.md:52` | Vectorae | A | help-center article copy (also served via backend support KB) | low |
| `src/content/help-center/07-personalization-and-claim-verification.md:54` | Vectorae | A | help-center article copy (also served via backend support KB) | low |
| `src/content/help-center/07-personalization-and-claim-verification.md:56` | Vectorae | A | help-center article copy (also served via backend support KB) | low |
| `src/content/help-center/07-personalization-and-claim-verification.md:60` | Vectorae | A | help-center article copy (also served via backend support KB) | low |
| `src/content/help-center/07-personalization-and-claim-verification.md:62` | Vectorae | A | help-center article copy (also served via backend support KB) | low |
| `src/content/help-center/07-personalization-and-claim-verification.md:71` | Vectorae | A | help-center article copy (also served via backend support KB) | low |
| `src/content/help-center/07-personalization-and-claim-verification.md:80` | Vectorae | A | help-center article copy (also served via backend support KB) | low |
| `src/content/help-center/08-sequences-and-follow-ups.md:44` | Vectorae | A | help-center article copy (also served via backend support KB) | low |
| `src/content/help-center/08-sequences-and-follow-ups.md:50` | Vectorae | A | help-center article copy (also served via backend support KB) | low |
| `src/content/help-center/08-sequences-and-follow-ups.md:62` | Vectorae | A | help-center article copy (also served via backend support KB) | low |
| `src/content/help-center/08-sequences-and-follow-ups.md:65` | Vectorae | A | help-center article copy (also served via backend support KB) | low |
| `src/content/help-center/08-sequences-and-follow-ups.md:80` | Vectorae | A | help-center article copy (also served via backend support KB) | low |
| `src/content/help-center/08-sequences-and-follow-ups.md:93` | Vectorae | A | help-center article copy (also served via backend support KB) | low |
| `src/content/help-center/08-sequences-and-follow-ups.md:99` | Vectorae | A | help-center article copy (also served via backend support KB) | low |
| `src/content/help-center/08-sequences-and-follow-ups.md:100` | Vectorae | A | help-center article copy (also served via backend support KB) | low |
| `src/content/help-center/08-sequences-and-follow-ups.md:104` | Vectorae | A | help-center article copy (also served via backend support KB) | low |
| `src/content/help-center/08-sequences-and-follow-ups.md:129` | Vectorae | A | help-center article copy (also served via backend support KB) | low |
| `src/content/help-center/08-sequences-and-follow-ups.md:138` | Vectorae | A | help-center article copy (also served via backend support KB) | low |
| `src/content/help-center/08-sequences-and-follow-ups.md:146` | Vectorae | A | help-center article copy (also served via backend support KB) | low |
| `src/content/help-center/08-sequences-and-follow-ups.md:152` | Vectorae | A | help-center article copy (also served via backend support KB) | low |
| `src/content/help-center/08-sequences-and-follow-ups.md:154` | Vectorae | A | help-center article copy (also served via backend support KB) | low |
| `src/content/help-center/09-email-sending-gmail.md:38` | Vectorae | A | help-center article copy (also served via backend support KB) | low |
| `src/content/help-center/09-email-sending-gmail.md:44` | Vectorae | A | help-center article copy (also served via backend support KB) | low |
| `src/content/help-center/09-email-sending-gmail.md:45` | Vectorae | A | help-center article copy (also served via backend support KB) | low |
| `src/content/help-center/09-email-sending-gmail.md:47` | Vectorae | A | help-center article copy (also served via backend support KB) | low |
| `src/content/help-center/09-email-sending-gmail.md:49` | Vectorae | A | help-center article copy (also served via backend support KB) | low |
| `src/content/help-center/09-email-sending-gmail.md:55` | Vectorae | A | help-center article copy (also served via backend support KB) | low |
| `src/content/help-center/09-email-sending-gmail.md:57` | Vectorae | A | help-center article copy (also served via backend support KB) | low |
| `src/content/help-center/09-email-sending-gmail.md:61` | Vectorae | A | help-center article copy (also served via backend support KB) | low |
| `src/content/help-center/09-email-sending-gmail.md:84` | Vectorae | A | help-center article copy (also served via backend support KB) | low |
| `src/content/help-center/09-email-sending-gmail.md:86` | Vectorae | A | help-center article copy (also served via backend support KB) | low |
| `src/content/help-center/09-email-sending-gmail.md:97` | Vectorae | A | help-center article copy (also served via backend support KB) | low |
| `src/content/help-center/09-email-sending-gmail.md:99` | Vectorae | A | help-center article copy (also served via backend support KB) | low |
| `src/content/help-center/09-email-sending-gmail.md:112` | Vectorae | A | help-center article copy (also served via backend support KB) | low |
| `src/content/help-center/10-whatsapp-outreach.md:45` | Vectorae | A | help-center article copy (also served via backend support KB) | low |
| `src/content/help-center/10-whatsapp-outreach.md:56` | Vectorae | A | help-center article copy (also served via backend support KB) | low |
| `src/content/help-center/10-whatsapp-outreach.md:68` | Vectorae | A | help-center article copy (also served via backend support KB) | low |
| `src/content/help-center/10-whatsapp-outreach.md:71` | Vectorae | A | help-center article copy (also served via backend support KB) | low |
| `src/content/help-center/10-whatsapp-outreach.md:89` | Vectorae | A | help-center article copy (also served via backend support KB) | low |
| `src/content/help-center/10-whatsapp-outreach.md:91` | Vectorae | A | help-center article copy (also served via backend support KB) | low |
| `src/content/help-center/10-whatsapp-outreach.md:98` | Vectorae | A | help-center article copy (also served via backend support KB) | low |
| `src/content/help-center/10-whatsapp-outreach.md:106` | Vectorae | A | help-center article copy (also served via backend support KB) | low |
| `src/content/help-center/10-whatsapp-outreach.md:108` | Vectorae | A | help-center article copy (also served via backend support KB) | low |
| `src/content/help-center/10-whatsapp-outreach.md:120` | Vectorae | A | help-center article copy (also served via backend support KB) | low |
| `src/content/help-center/10-whatsapp-outreach.md:126` | Vectorae | A | help-center article copy (also served via backend support KB) | low |
| `src/content/help-center/10-whatsapp-outreach.md:130` | Vectorae | A | help-center article copy (also served via backend support KB) | low |
| `src/content/help-center/11-linkedin.md:L42-164` (19 occurrences) | Vectorae | A | help-center article copy (also served via backend support KB) | low |
| `src/content/help-center/11-linkedin.md:105` | Vectorae | A | A-comment (code comment/docstring) | low |
| `src/content/help-center/12-send-review-queue.md:32` | Vectorae | A | help-center article copy (also served via backend support KB) | low |
| `src/content/help-center/12-send-review-queue.md:39` | Vectorae | A | help-center article copy (also served via backend support KB) | low |
| `src/content/help-center/12-send-review-queue.md:41` | Vectorae | A | help-center article copy (also served via backend support KB) | low |
| `src/content/help-center/12-send-review-queue.md:47` | Vectorae | A | help-center article copy (also served via backend support KB) | low |
| `src/content/help-center/12-send-review-queue.md:49` | Vectorae | A | help-center article copy (also served via backend support KB) | low |
| `src/content/help-center/12-send-review-queue.md:51` | Vectorae | A | help-center article copy (also served via backend support KB) | low |
| `src/content/help-center/12-send-review-queue.md:57` | Vectorae | A | help-center article copy (also served via backend support KB) | low |
| `src/content/help-center/12-send-review-queue.md:61` | Vectorae | A | help-center article copy (also served via backend support KB) | low |
| `src/content/help-center/12-send-review-queue.md:75` | Vectorae | A | help-center article copy (also served via backend support KB) | low |
| `src/content/help-center/12-send-review-queue.md:85` | Vectorae | A | help-center article copy (also served via backend support KB) | low |
| `src/content/help-center/12-send-review-queue.md:93` | Vectorae | A | help-center article copy (also served via backend support KB) | low |
| `src/content/help-center/12-send-review-queue.md:112` | Vectorae | A | help-center article copy (also served via backend support KB) | low |
| `src/content/help-center/13-replies-and-unified-inbox.md:34` | Vectorae | A | help-center article copy (also served via backend support KB) | low |
| `src/content/help-center/13-replies-and-unified-inbox.md:36` | Vectorae | A | help-center article copy (also served via backend support KB) | low |
| `src/content/help-center/13-replies-and-unified-inbox.md:38` | Vectorae | A | help-center article copy (also served via backend support KB) | low |
| `src/content/help-center/13-replies-and-unified-inbox.md:57` | Vectorae | A | help-center article copy (also served via backend support KB) | low |
| `src/content/help-center/13-replies-and-unified-inbox.md:68` | Vectorae | A | help-center article copy (also served via backend support KB) | low |
| `src/content/help-center/13-replies-and-unified-inbox.md:80` | Vectorae | A | help-center article copy (also served via backend support KB) | low |
| `src/content/help-center/14-booking-and-calendar.md:31` | Vectorae | A | help-center article copy (also served via backend support KB) | low |
| `src/content/help-center/14-booking-and-calendar.md:33` | Vectorae | A | help-center article copy (also served via backend support KB) | low |
| `src/content/help-center/14-booking-and-calendar.md:35` | Vectorae | A | help-center article copy (also served via backend support KB) | low |
| `src/content/help-center/14-booking-and-calendar.md:36` | Vectorae | A | help-center article copy (also served via backend support KB) | low |
| `src/content/help-center/14-booking-and-calendar.md:38` | Vectorae | A | help-center article copy (also served via backend support KB) | low |
| `src/content/help-center/14-booking-and-calendar.md:56` | Vectorae | A | help-center article copy (also served via backend support KB) | low |
| `src/content/help-center/14-booking-and-calendar.md:66` | Vectorae | A | help-center article copy (also served via backend support KB) | low |
| `src/content/help-center/14-booking-and-calendar.md:72` | Vectorae | A | help-center article copy (also served via backend support KB) | low |
| `src/content/help-center/14-booking-and-calendar.md:82` | Vectorae | A | help-center article copy (also served via backend support KB) | low |
| `src/content/help-center/14-booking-and-calendar.md:92` | Vectorae | A | help-center article copy (also served via backend support KB) | low |
| `src/content/help-center/14-booking-and-calendar.md:96` | Vectorae | A | help-center article copy (also served via backend support KB) | low |
| `src/content/help-center/15-meetings-prep-room-transcripts.md:33` | Vectorae | A | help-center article copy (also served via backend support KB) | low |
| `src/content/help-center/15-meetings-prep-room-transcripts.md:37` | Vectorae | A | help-center article copy (also served via backend support KB) | low |
| `src/content/help-center/15-meetings-prep-room-transcripts.md:44` | Vectorae | A | help-center article copy (also served via backend support KB) | low |
| `src/content/help-center/15-meetings-prep-room-transcripts.md:48` | Vectorae | A | help-center article copy (also served via backend support KB) | low |
| `src/content/help-center/15-meetings-prep-room-transcripts.md:52` | Vectorae | A | help-center article copy (also served via backend support KB) | low |
| `src/content/help-center/15-meetings-prep-room-transcripts.md:70` | Vectorae | A | help-center article copy (also served via backend support KB) | low |
| `src/content/help-center/15-meetings-prep-room-transcripts.md:76` | Vectorae | A | help-center article copy (also served via backend support KB) | low |
| `src/content/help-center/15-meetings-prep-room-transcripts.md:80` | Vectorae | A | help-center article copy (also served via backend support KB) | low |
| `src/content/help-center/15-meetings-prep-room-transcripts.md:84` | Vectorae | A | help-center article copy (also served via backend support KB) | low |
| `src/content/help-center/15-meetings-prep-room-transcripts.md:88` | Vectorae | A | help-center article copy (also served via backend support KB) | low |
| `src/content/help-center/15-meetings-prep-room-transcripts.md:92` | Vectorae | A | help-center article copy (also served via backend support KB) | low |
| `src/content/help-center/15-meetings-prep-room-transcripts.md:96` | Vectorae | A | help-center article copy (also served via backend support KB) | low |
| `src/content/help-center/15-meetings-prep-room-transcripts.md:98` | Vectorae | A | help-center article copy (also served via backend support KB) | low |
| `src/content/help-center/16-crm-and-integrations.md:30` | Vectorae | A | help-center article copy (also served via backend support KB) | low |
| `src/content/help-center/16-crm-and-integrations.md:32` | Vectorae | A | help-center article copy (also served via backend support KB) | low |
| `src/content/help-center/16-crm-and-integrations.md:45` | Vectorae | A | help-center article copy (also served via backend support KB) | low |
| `src/content/help-center/16-crm-and-integrations.md:47` | Vectorae | A | help-center article copy (also served via backend support KB) | low |
| `src/content/help-center/16-crm-and-integrations.md:55` | Vectorae | A | A-comment (code comment/docstring) | low |
| `src/content/help-center/16-crm-and-integrations.md:63` | Vectorae | A | A-comment (code comment/docstring) | low |
| `src/content/help-center/16-crm-and-integrations.md:68` | Vectorae | A | help-center article copy (also served via backend support KB) | low |
| `src/content/help-center/16-crm-and-integrations.md:74` | Vectorae | A | help-center article copy (also served via backend support KB) | low |
| `src/content/help-center/16-crm-and-integrations.md:82` | LeadPilot, Vectorae | B | webhook header name customers verify (X-LeadPilot-*/X-ClientHunter-*) shown in UI/docs | high |
| `src/content/help-center/16-crm-and-integrations.md:95` | Vectorae, lpk_ | B | API key prefix lpk_ (customer integrations/secret scanners depend on it) | high |
| `src/content/help-center/17-learning-loop-and-ab-tests.md:34` | Vectorae | A | help-center article copy (also served via backend support KB) | low |
| `src/content/help-center/17-learning-loop-and-ab-tests.md:36` | Vectorae | A | help-center article copy (also served via backend support KB) | low |
| `src/content/help-center/17-learning-loop-and-ab-tests.md:38` | Vectorae | A | help-center article copy (also served via backend support KB) | low |
| `src/content/help-center/17-learning-loop-and-ab-tests.md:40` | Vectorae | A | help-center article copy (also served via backend support KB) | low |
| `src/content/help-center/17-learning-loop-and-ab-tests.md:50` | Vectorae | A | help-center article copy (also served via backend support KB) | low |
| `src/content/help-center/17-learning-loop-and-ab-tests.md:75` | Vectorae | A | help-center article copy (also served via backend support KB) | low |
| `src/content/help-center/17-learning-loop-and-ab-tests.md:81` | Vectorae | A | A-comment (code comment/docstring) | low |
| `src/content/help-center/17-learning-loop-and-ab-tests.md:87` | Vectorae | A | help-center article copy (also served via backend support KB) | low |
| `src/content/help-center/18-analytics-health-score-roi.md:34` | Vectorae | A | help-center article copy (also served via backend support KB) | low |
| `src/content/help-center/18-analytics-health-score-roi.md:54` | Vectorae | A | help-center article copy (also served via backend support KB) | low |
| `src/content/help-center/18-analytics-health-score-roi.md:64` | Vectorae | A | help-center article copy (also served via backend support KB) | low |
| `src/content/help-center/18-analytics-health-score-roi.md:75` | Vectorae | A | A-comment (code comment/docstring) | low |
| `src/content/help-center/19-deliverability-and-mailbox-health.md:25` | Vectorae | A | help-center article copy (also served via backend support KB) | low |
| `src/content/help-center/19-deliverability-and-mailbox-health.md:35` | Vectorae | A | help-center article copy (also served via backend support KB) | low |
| `src/content/help-center/19-deliverability-and-mailbox-health.md:55` | Vectorae | A | help-center article copy (also served via backend support KB) | low |
| `src/content/help-center/19-deliverability-and-mailbox-health.md:61` | Vectorae | A | help-center article copy (also served via backend support KB) | low |
| `src/content/help-center/19-deliverability-and-mailbox-health.md:74` | Vectorae | A | help-center article copy (also served via backend support KB) | low |
| `src/content/help-center/20-compliance.md:38` | Vectorae | A | help-center article copy (also served via backend support KB) | low |
| `src/content/help-center/20-compliance.md:42` | Vectorae | A | help-center article copy (also served via backend support KB) | low |
| `src/content/help-center/20-compliance.md:56` | Vectorae | A | help-center article copy (also served via backend support KB) | low |
| `src/content/help-center/20-compliance.md:66` | Vectorae | A | help-center article copy (also served via backend support KB) | low |
| `src/content/help-center/20-compliance.md:74` | Vectorae | A | help-center article copy (also served via backend support KB) | low |
| `src/content/help-center/20-compliance.md:78` | Vectorae | A | help-center article copy (also served via backend support KB) | low |
| `src/content/help-center/20-compliance.md:81` | Vectorae | A | help-center article copy (also served via backend support KB) | low |
| `src/content/help-center/20-compliance.md:87` | Vectorae | A | help-center article copy (also served via backend support KB) | low |
| `src/content/help-center/20-compliance.md:100` | Vectorae | A | help-center article copy (also served via backend support KB) | low |
| `src/content/help-center/20-compliance.md:104` | Vectorae | A | help-center article copy (also served via backend support KB) | low |
| `src/content/help-center/20-compliance.md:106` | Vectorae | A | help-center article copy (also served via backend support KB) | low |
| `src/content/help-center/20-compliance.md:121` | Vectorae | A | help-center article copy (also served via backend support KB) | low |
| `src/content/help-center/21-privacy-data-retention-deletion.md:42` | Vectorae | A | help-center article copy (also served via backend support KB) | low |
| `src/content/help-center/21-privacy-data-retention-deletion.md:44` | Vectorae | A | help-center article copy (also served via backend support KB) | low |
| `src/content/help-center/21-privacy-data-retention-deletion.md:46` | Vectorae | A | help-center article copy (also served via backend support KB) | low |
| `src/content/help-center/21-privacy-data-retention-deletion.md:55` | Vectorae | A | help-center article copy (also served via backend support KB) | low |
| `src/content/help-center/21-privacy-data-retention-deletion.md:57` | Vectorae | A | help-center article copy (also served via backend support KB) | low |
| `src/content/help-center/21-privacy-data-retention-deletion.md:59` | Vectorae | A | help-center article copy (also served via backend support KB) | low |
| `src/content/help-center/21-privacy-data-retention-deletion.md:63` | Vectorae | A | help-center article copy (also served via backend support KB) | low |
| `src/content/help-center/21-privacy-data-retention-deletion.md:67` | Vectorae | A | help-center article copy (also served via backend support KB) | low |
| `src/content/help-center/21-privacy-data-retention-deletion.md:81` | LeadPilot | A | download/export filename shown to user; judge: customer scripts may match it | low |
| `src/content/help-center/21-privacy-data-retention-deletion.md:96` | Vectorae | A | help-center article copy (also served via backend support KB) | low |
| `src/content/help-center/21-privacy-data-retention-deletion.md:130` | Vectorae | A | help-center article copy (also served via backend support KB) | low |
| `src/content/help-center/21-privacy-data-retention-deletion.md:140` | Vectorae | A | help-center article copy (also served via backend support KB) | low |
| `src/content/help-center/21-privacy-data-retention-deletion.md:144` | Vectorae | A | help-center article copy (also served via backend support KB) | low |
| `src/content/help-center/21-privacy-data-retention-deletion.md:156` | Vectorae | A | help-center article copy (also served via backend support KB) | low |
| `src/content/help-center/21-privacy-data-retention-deletion.md:161` | Vectorae | A | help-center article copy (also served via backend support KB) | low |
| `src/content/help-center/22-plans-limits-billing.md:42` | Vectorae | A | help-center article copy (also served via backend support KB) | low |
| `src/content/help-center/22-plans-limits-billing.md:92` | Vectorae | A | A-comment (code comment/docstring) | low |
| `src/content/help-center/22-plans-limits-billing.md:98` | Vectorae | A | help-center article copy (also served via backend support KB) | low |
| `src/content/help-center/22-plans-limits-billing.md:104` | Vectorae | A | help-center article copy (also served via backend support KB) | low |
| `src/content/help-center/22-plans-limits-billing.md:117` | Vectorae | A | help-center article copy (also served via backend support KB) | low |
| `src/content/help-center/22-plans-limits-billing.md:119` | Vectorae | A | help-center article copy (also served via backend support KB) | low |
| `src/content/help-center/22-plans-limits-billing.md:121` | Vectorae | A | help-center article copy (also served via backend support KB) | low |
| `src/content/help-center/22-plans-limits-billing.md:130` | Vectorae | A | help-center article copy (also served via backend support KB) | low |
| `src/content/help-center/22-plans-limits-billing.md:157` | Vectorae | A | help-center article copy (also served via backend support KB) | low |
| `src/content/help-center/22-plans-limits-billing.md:167` | Vectorae | A | help-center article copy (also served via backend support KB) | low |
| `src/content/help-center/23-account-security.md:37` | Vectorae | A | help-center article copy (also served via backend support KB) | low |
| `src/content/help-center/23-account-security.md:39` | Vectorae | A | help-center article copy (also served via backend support KB) | low |
| `src/content/help-center/23-account-security.md:54` | Vectorae | A | help-center article copy (also served via backend support KB) | low |
| `src/content/help-center/23-account-security.md:82` | Vectorae | A | help-center article copy (also served via backend support KB) | low |
| `src/content/help-center/23-account-security.md:94` | Vectorae | A | help-center article copy (also served via backend support KB) | low |
| `src/content/help-center/23-account-security.md:95` | Vectorae | A | help-center article copy (also served via backend support KB) | low |
| `src/content/help-center/23-account-security.md:101` | Vectorae | A | help-center article copy (also served via backend support KB) | low |
| `src/content/help-center/23-account-security.md:109` | Vectorae, lpk_ | B | API key prefix lpk_ (customer integrations/secret scanners depend on it) | high |
| `src/content/help-center/24-workspaces-and-agency-mode.md:35` | Vectorae | A | help-center article copy (also served via backend support KB) | low |
| `src/content/help-center/24-workspaces-and-agency-mode.md:92` | Vectorae | A | help-center article copy (also served via backend support KB) | low |
| `src/content/help-center/24-workspaces-and-agency-mode.md:106` | Vectorae | A | help-center article copy (also served via backend support KB) | low |
| `src/content/help-center/24-workspaces-and-agency-mode.md:110` | Vectorae | A | help-center article copy (also served via backend support KB) | low |
| `src/content/help-center/24-workspaces-and-agency-mode.md:114` | Vectorae | A | help-center article copy (also served via backend support KB) | low |
| `src/content/help-center/24-workspaces-and-agency-mode.md:118` | Vectorae | A | help-center article copy (also served via backend support KB) | low |
| `src/content/help-center/25-pause-stop-kill-switch.md:36` | Vectorae | A | help-center article copy (also served via backend support KB) | low |
| `src/content/help-center/25-pause-stop-kill-switch.md:52` | Vectorae | A | help-center article copy (also served via backend support KB) | low |
| `src/content/help-center/25-pause-stop-kill-switch.md:66` | Vectorae | A | help-center article copy (also served via backend support KB) | low |
| `src/content/help-center/25-pause-stop-kill-switch.md:68` | Vectorae | A | help-center article copy (also served via backend support KB) | low |
| `src/content/help-center/25-pause-stop-kill-switch.md:79` | Vectorae | A | help-center article copy (also served via backend support KB) | low |
| `src/content/help-center/25-pause-stop-kill-switch.md:93` | Vectorae | A | help-center article copy (also served via backend support KB) | low |
| `src/content/help-center/26-mobile-app.md:35` | Vectorae | A | help-center article copy (also served via backend support KB) | low |
| `src/content/help-center/26-mobile-app.md:39` | ClientHunter, Vectorae | B | Android package_name in Digital Asset Links / docs; must match Play Store applicationId | high |
| `src/content/help-center/26-mobile-app.md:47` | Vectorae | A | help-center article copy (also served via backend support KB) | low |
| `src/content/help-center/26-mobile-app.md:56` | Vectorae | A | help-center article copy (also served via backend support KB) | low |
| `src/content/help-center/26-mobile-app.md:57` | Vectorae | A | help-center article copy (also served via backend support KB) | low |
| `src/content/help-center/26-mobile-app.md:65` | Vectorae | A | help-center article copy (also served via backend support KB) | low |
| `src/content/help-center/26-mobile-app.md:79` | Vectorae | A | help-center article copy (also served via backend support KB) | low |
| `src/content/help-center/26-mobile-app.md:81` | Vectorae | A | help-center article copy (also served via backend support KB) | low |
| `src/content/help-center/26-mobile-app.md:89` | Vectorae | A | help-center article copy (also served via backend support KB) | low |
| `src/content/help-center/26-mobile-app.md:95` | Vectorae | A | help-center article copy (also served via backend support KB) | low |
| `src/content/help-center/26-mobile-app.md:98` | LeadPilot, Vectorae | B | link/ref to help-center filename 01-what-is-leadpilot.md (file rename breaks link; backend help_center/support_kb also read these files) | med |
| `src/content/help-center/27-troubleshooting.md:87` | Vectorae | A | help-center article copy (also served via backend support KB) | low |
| `src/content/help-center/28-glossary.md:3` | Vectorae | A | page <title>/meta | med |
| `src/content/help-center/28-glossary.md:40` | Vectorae | A | help-center article copy (also served via backend support KB) | low |
| `src/content/help-center/28-glossary.md:42` | Vectorae | A | help-center article copy (also served via backend support KB) | low |
| `src/content/help-center/28-glossary.md:47` | Vectorae | A | help-center article copy (also served via backend support KB) | low |
| `src/content/help-center/28-glossary.md:49` | Vectorae | A | help-center article copy (also served via backend support KB) | low |
| `src/content/help-center/28-glossary.md:56` | Vectorae | A | help-center article copy (also served via backend support KB) | low |
| `src/content/help-center/28-glossary.md:69` | Vectorae | A | help-center article copy (also served via backend support KB) | low |
| `src/content/help-center/28-glossary.md:90` | Vectorae | A | help-center article copy (also served via backend support KB) | low |
| `src/content/help-center/28-glossary.md:94` | Vectorae | A | help-center article copy (also served via backend support KB) | low |
| `src/content/help-center/28-glossary.md:96` | Vectorae | A | help-center article copy (also served via backend support KB) | low |
| `src/content/help-center/28-glossary.md:101` | Vectorae | A | help-center article copy (also served via backend support KB) | low |
| `src/content/help-center/28-glossary.md:108` | Vectorae | A | help-center article copy (also served via backend support KB) | low |
| `src/content/help-center/28-glossary.md:115` | lpk_ | B | API key prefix lpk_ (customer integrations/secret scanners depend on it) | high |
| `src/content/help-center/28-glossary.md:116` | Vectorae | A | help-center article copy (also served via backend support KB) | low |
| `src/content/help-center/28-glossary.md:119` | LeadPilot, Vectorae | B | link/ref to help-center filename 01-what-is-leadpilot.md (file rename breaks link; backend help_center/support_kb also read these files) | med |
| `src/content/help-center/29-known-limitations.md:51` | Vectorae | A | help-center article copy (also served via backend support KB) | low |
| `src/content/help-center/29-known-limitations.md:56` | Vectorae | A | help-center article copy (also served via backend support KB) | low |
| `src/content/help-center/29-known-limitations.md:60` | Vectorae | A | help-center article copy (also served via backend support KB) | low |
| `src/content/help-center/29-known-limitations.md:64` | Vectorae | A | help-center article copy (also served via backend support KB) | low |
| `src/content/help-center/29-known-limitations.md:72` | Vectorae | A | help-center article copy (also served via backend support KB) | low |
| `src/content/help-center/29-known-limitations.md:92` | Vectorae | A | help-center article copy (also served via backend support KB) | low |
| `src/content/help-center/29-known-limitations.md:106` | Vectorae | A | help-center article copy (also served via backend support KB) | low |
| `src/content/help-center/30-contact-support-and-status.md:40` | Vectorae | A | help-center article copy (also served via backend support KB) | low |
| `src/content/help-center/30-contact-support-and-status.md:44` | Vectorae | A | help-center article copy (also served via backend support KB) | low |
| `src/content/help-center/30-contact-support-and-status.md:55` | Vectorae | A | help-center article copy (also served via backend support KB) | low |
| `src/content/help-center/30-contact-support-and-status.md:57` | Vectorae | A | help-center article copy (also served via backend support KB) | low |
| `src/content/help-center/30-contact-support-and-status.md:65` | Vectorae | A | help-center article copy (also served via backend support KB) | low |
| `src/content/help-center/30-contact-support-and-status.md:82` | Vectorae | A | help-center article copy (also served via backend support KB) | low |
| `src/content/help-center/30-contact-support-and-status.md:94` | Vectorae | A | help-center article copy (also served via backend support KB) | low |
| `src/content/help-center/30-contact-support-and-status.md:96` | Vectorae | A | help-center article copy (also served via backend support KB) | low |
| `src/content/help-center/30-contact-support-and-status.md:100` | Vectorae | A | help-center article copy (also served via backend support KB) | low |
| `src/content/help-center/30-contact-support-and-status.md:104` | Vectorae | A | help-center article copy (also served via backend support KB) | low |
| `src/content/help-center/30-contact-support-and-status.md:109` | Vectorae | A | help-center article copy (also served via backend support KB) | low |
| `src/content/help-center/30-contact-support-and-status.md:117` | Vectorae | A | help-center article copy (also served via backend support KB) | low |
| `src/content/help-center/30-contact-support-and-status.md:119` | Vectorae | A | help-center article copy (also served via backend support KB) | low |
| `src/content/help-center/31-guide-solo-founder.md:3` | Vectorae | A | page <title>/meta | med |
| `src/content/help-center/31-guide-solo-founder.md:43` | Vectorae | A | help-center article copy (also served via backend support KB) | low |
| `src/content/help-center/31-guide-solo-founder.md:45` | Vectorae | A | help-center article copy (also served via backend support KB) | low |
| `src/content/help-center/31-guide-solo-founder.md:47` | Vectorae | A | help-center article copy (also served via backend support KB) | low |
| `src/content/help-center/31-guide-solo-founder.md:49` | Vectorae | A | help-center article copy (also served via backend support KB) | low |
| `src/content/help-center/31-guide-solo-founder.md:63` | Vectorae | A | help-center article copy (also served via backend support KB) | low |
| `src/content/help-center/31-guide-solo-founder.md:67` | Vectorae | A | help-center article copy (also served via backend support KB) | low |
| `src/content/help-center/31-guide-solo-founder.md:71` | Vectorae | A | help-center article copy (also served via backend support KB) | low |
| `src/content/help-center/31-guide-solo-founder.md:73` | Vectorae | A | help-center article copy (also served via backend support KB) | low |
| `src/content/help-center/31-guide-solo-founder.md:81` | Vectorae | A | help-center article copy (also served via backend support KB) | low |
| `src/content/help-center/31-guide-solo-founder.md:86` | Vectorae | A | help-center article copy (also served via backend support KB) | low |
| `src/content/help-center/32-guide-sdr-team-member.md:40` | Vectorae | A | help-center article copy (also served via backend support KB) | low |
| `src/content/help-center/33-product-profile-and-icp.md:36` | Vectorae | A | help-center article copy (also served via backend support KB) | low |
| `src/content/help-center/33-product-profile-and-icp.md:49` | Vectorae | A | help-center article copy (also served via backend support KB) | low |
| `src/content/help-center/33-product-profile-and-icp.md:55` | Vectorae | A | A-comment (code comment/docstring) | low |
| `src/content/help-center/33-product-profile-and-icp.md:57` | Vectorae | A | A-comment (code comment/docstring) | low |
| `src/content/help-center/33-product-profile-and-icp.md:70` | Vectorae | A | help-center article copy (also served via backend support KB) | low |
| `src/content/help-center/33-product-profile-and-icp.md:74` | Vectorae | A | help-center article copy (also served via backend support KB) | low |
| `src/content/help-center/33-product-profile-and-icp.md:88` | Vectorae | A | help-center article copy (also served via backend support KB) | low |
| `src/content/help-center/33-product-profile-and-icp.md:103` | Vectorae | A | help-center article copy (also served via backend support KB) | low |
| `src/content/help-center/33-product-profile-and-icp.md:111` | Vectorae | A | help-center article copy (also served via backend support KB) | low |
| `src/content/help-center/34-strategy-patterns-and-playbooks.md:39` | Vectorae | A | help-center article copy (also served via backend support KB) | low |
| `src/content/help-center/34-strategy-patterns-and-playbooks.md:71` | Vectorae | A | help-center article copy (also served via backend support KB) | low |
| `src/content/help-center/34-strategy-patterns-and-playbooks.md:80` | Vectorae | A | help-center article copy (also served via backend support KB) | low |
| `src/content/help-center/34-strategy-patterns-and-playbooks.md:82` | Vectorae | A | help-center article copy (also served via backend support KB) | low |
| `src/content/help-center/34-strategy-patterns-and-playbooks.md:89` | Vectorae | A | help-center article copy (also served via backend support KB) | low |
| `src/content/help-center/35-google-workspace-dns-setup.md:26` | Vectorae | A | help-center article copy (also served via backend support KB) | low |
| `src/content/help-center/35-google-workspace-dns-setup.md:28` | Vectorae | A | help-center article copy (also served via backend support KB) | low |
| `src/content/help-center/35-google-workspace-dns-setup.md:30` | Vectorae | A | help-center article copy (also served via backend support KB) | low |
| `src/content/help-center/35-google-workspace-dns-setup.md:32` | Vectorae | A | help-center article copy (also served via backend support KB) | low |
| `src/content/help-center/35-google-workspace-dns-setup.md:38` | Vectorae | A | help-center article copy (also served via backend support KB) | low |
| `src/content/help-center/35-google-workspace-dns-setup.md:42` | Vectorae | A | help-center article copy (also served via backend support KB) | low |
| `src/content/help-center/35-google-workspace-dns-setup.md:50` | Vectorae | A | help-center article copy (also served via backend support KB) | low |
| `src/content/help-center/35-google-workspace-dns-setup.md:57` | Vectorae | A | help-center article copy (also served via backend support KB) | low |
| `src/content/help-center/35-google-workspace-dns-setup.md:81` | Vectorae | A | help-center article copy (also served via backend support KB) | low |
| `src/content/help-center/35-google-workspace-dns-setup.md:83` | Vectorae | A | help-center article copy (also served via backend support KB) | low |
| `src/content/help-center/35-google-workspace-dns-setup.md:85` | Vectorae | A | help-center article copy (also served via backend support KB) | low |
| `src/content/help-center/35-google-workspace-dns-setup.md:89` | Vectorae | A | help-center article copy (also served via backend support KB) | low |
| `src/content/help-center/36-crm-sync-field-mapping.md:L23-120` (24 occurrences) | Vectorae | A | help-center article copy (also served via backend support KB) | low |
| `src/content/help-center/37-webhooks-and-slack-events.md:36` | Vectorae | A | help-center article copy (also served via backend support KB) | low |
| `src/content/help-center/37-webhooks-and-slack-events.md:44` | Vectorae | A | help-center article copy (also served via backend support KB) | low |
| `src/content/help-center/37-webhooks-and-slack-events.md:71` | ClientHunter, LeadPilot | B | webhook header name customers verify (X-LeadPilot-*/X-ClientHunter-*) shown in UI/docs | high |
| `src/content/help-center/37-webhooks-and-slack-events.md:75` | LeadPilot | B | meeting source enum value from backend API (DB/webhook payload value) | high |
| `src/content/help-center/37-webhooks-and-slack-events.md:92` | Vectorae | A | help-center article copy (also served via backend support KB) | low |
| `src/content/help-center/37-webhooks-and-slack-events.md:96` | LeadPilot | B | webhook header name customers verify (X-LeadPilot-*/X-ClientHunter-*) shown in UI/docs | high |
| `src/content/help-center/37-webhooks-and-slack-events.md:109` | LeadPilot | A | sample code function name in help article (customer may copy; harmless) | low |
| `src/content/help-center/37-webhooks-and-slack-events.md:118` | ClientHunter, LeadPilot | B | webhook header name customers verify (X-LeadPilot-*/X-ClientHunter-*) shown in UI/docs | high |
| `src/content/help-center/37-webhooks-and-slack-events.md:122` | Vectorae | A | help-center article copy (also served via backend support KB) | low |
| `src/content/help-center/37-webhooks-and-slack-events.md:145` | Vectorae | A | help-center article copy (also served via backend support KB) | low |
| `src/content/help-center/37-webhooks-and-slack-events.md:157` | Vectorae | A | help-center article copy (also served via backend support KB) | low |
| `src/content/help-center/38-reply-copilot-and-classification.md:28` | Vectorae | A | help-center article copy (also served via backend support KB) | low |
| `src/content/help-center/38-reply-copilot-and-classification.md:30` | Vectorae | A | help-center article copy (also served via backend support KB) | low |
| `src/content/help-center/38-reply-copilot-and-classification.md:69` | Vectorae | A | help-center article copy (also served via backend support KB) | low |
| `src/content/help-center/38-reply-copilot-and-classification.md:76` | Vectorae | A | help-center article copy (also served via backend support KB) | low |
| `src/content/help-center/38-reply-copilot-and-classification.md:80` | Vectorae | A | help-center article copy (also served via backend support KB) | low |
| `src/content/help-center/39-daily-send-approval-and-notifications.md:27` | Vectorae | A | help-center article copy (also served via backend support KB) | low |
| `src/content/help-center/39-daily-send-approval-and-notifications.md:29` | Vectorae | A | help-center article copy (also served via backend support KB) | low |
| `src/content/help-center/39-daily-send-approval-and-notifications.md:31` | Vectorae | A | help-center article copy (also served via backend support KB) | low |
| `src/content/help-center/39-daily-send-approval-and-notifications.md:33` | Vectorae | A | help-center article copy (also served via backend support KB) | low |
| `src/content/help-center/39-daily-send-approval-and-notifications.md:46` | Vectorae | A | help-center article copy (also served via backend support KB) | low |
| `src/content/help-center/39-daily-send-approval-and-notifications.md:60` | Vectorae | A | help-center article copy (also served via backend support KB) | low |
| `src/content/help-center/39-daily-send-approval-and-notifications.md:70` | Vectorae | A | help-center article copy (also served via backend support KB) | low |
| `src/content/help-center/39-daily-send-approval-and-notifications.md:72` | Vectorae | A | help-center article copy (also served via backend support KB) | low |
| `src/content/help-center/39-daily-send-approval-and-notifications.md:81` | Vectorae | A | help-center article copy (also served via backend support KB) | low |
| `src/content/help-center/39-daily-send-approval-and-notifications.md:83` | Vectorae | A | help-center article copy (also served via backend support KB) | low |
| `src/content/help-center/39-daily-send-approval-and-notifications.md:84` | Vectorae | A | help-center article copy (also served via backend support KB) | low |
| `src/content/help-center/39-daily-send-approval-and-notifications.md:94` | Vectorae | A | help-center article copy (also served via backend support KB) | low |
| `src/content/help-center/40-annual-billing-and-plan-changes.md:29` | Vectorae | A | help-center article copy (also served via backend support KB) | low |
| `src/content/help-center/40-annual-billing-and-plan-changes.md:44` | Vectorae | A | help-center article copy (also served via backend support KB) | low |
| `src/content/help-center/40-annual-billing-and-plan-changes.md:50` | Vectorae | A | help-center article copy (also served via backend support KB) | low |
| `src/content/help-center/40-annual-billing-and-plan-changes.md:68` | Vectorae | A | help-center article copy (also served via backend support KB) | low |
| `src/content/help-center/41-benchmarks-what-good-looks-like.md:32` | Vectorae | A | help-center article copy (also served via backend support KB) | low |
| `src/content/help-center/41-benchmarks-what-good-looks-like.md:34` | Vectorae | A | help-center article copy (also served via backend support KB) | low |
| `src/content/help-center/41-benchmarks-what-good-looks-like.md:36` | Vectorae | A | help-center article copy (also served via backend support KB) | low |
| `src/content/help-center/41-benchmarks-what-good-looks-like.md:38` | Vectorae | A | help-center article copy (also served via backend support KB) | low |
| `src/content/help-center/41-benchmarks-what-good-looks-like.md:44` | Vectorae | A | help-center article copy (also served via backend support KB) | low |
| `src/content/help-center/41-benchmarks-what-good-looks-like.md:55` | Vectorae | A | help-center article copy (also served via backend support KB) | low |
| `src/content/help-center/41-benchmarks-what-good-looks-like.md:59` | Vectorae | A | help-center article copy (also served via backend support KB) | low |
| `src/content/help-center/41-benchmarks-what-good-looks-like.md:67` | Vectorae | A | help-center article copy (also served via backend support KB) | low |
| `src/content/help-center/41-benchmarks-what-good-looks-like.md:71` | Vectorae | A | help-center article copy (also served via backend support KB) | low |
| `src/content/help-center/41-benchmarks-what-good-looks-like.md:73` | Vectorae | A | help-center article copy (also served via backend support KB) | low |
| `src/content/help-center/41-benchmarks-what-good-looks-like.md:80` | Vectorae | A | help-center article copy (also served via backend support KB) | low |
| `src/content/help-center/41-benchmarks-what-good-looks-like.md:82` | Vectorae | A | help-center article copy (also served via backend support KB) | low |
| `src/content/help-center/41-benchmarks-what-good-looks-like.md:88` | Vectorae | A | help-center article copy (also served via backend support KB) | low |
| `src/content/help-center/42-security-faq-for-buyers.md:32` | Vectorae | A | help-center article copy (also served via backend support KB) | low |
| `src/content/help-center/42-security-faq-for-buyers.md:34` | Vectorae | A | help-center article copy (also served via backend support KB) | low |
| `src/content/help-center/42-security-faq-for-buyers.md:36` | Vectorae | A | help-center article copy (also served via backend support KB) | low |
| `src/content/help-center/42-security-faq-for-buyers.md:42` | Vectorae | A | A-comment (code comment/docstring) | low |
| `src/content/help-center/42-security-faq-for-buyers.md:50` | Vectorae | A | help-center article copy (also served via backend support KB) | low |
| `src/content/help-center/42-security-faq-for-buyers.md:54` | LeadPilot | B | webhook header name customers verify (X-LeadPilot-*/X-ClientHunter-*) shown in UI/docs | high |
| `src/content/help-center/42-security-faq-for-buyers.md:55` | LeadPilot | B | webhook header name customers verify (X-LeadPilot-*/X-ClientHunter-*) shown in UI/docs | high |
| `src/content/help-center/42-security-faq-for-buyers.md:56` | LeadPilot | B | webhook header name customers verify (X-LeadPilot-*/X-ClientHunter-*) shown in UI/docs | high |
| `src/content/help-center/42-security-faq-for-buyers.md:58` | ClientHunter | B | webhook header name customers verify (X-LeadPilot-*/X-ClientHunter-*) shown in UI/docs | high |
| `src/content/help-center/42-security-faq-for-buyers.md:62` | Vectorae | A | help-center article copy (also served via backend support KB) | low |
| `src/content/help-center/42-security-faq-for-buyers.md:64` | Vectorae | A | help-center article copy (also served via backend support KB) | low |
| `src/content/help-center/42-security-faq-for-buyers.md:77` | Vectorae | A | help-center article copy (also served via backend support KB) | low |
| `src/content/help-center/42-security-faq-for-buyers.md:89` | Vectorae | A | help-center article copy (also served via backend support KB) | low |
| `src/content/help-center/42-security-faq-for-buyers.md:95` | Vectorae | A | help-center article copy (also served via backend support KB) | low |
| `src/content/help-center/42-security-faq-for-buyers.md:99` | Vectorae | A | help-center article copy (also served via backend support KB) | low |
| `src/content/help-center/43-data-processing-and-subprocessors.md:51` | Vectorae | A | help-center article copy (also served via backend support KB) | low |
| `src/content/help-center/43-data-processing-and-subprocessors.md:55` | Vectorae | A | help-center article copy (also served via backend support KB) | low |
| `src/content/help-center/43-data-processing-and-subprocessors.md:59` | Vectorae | A | help-center article copy (also served via backend support KB) | low |
| `src/content/help-center/43-data-processing-and-subprocessors.md:74` | Vectorae | A | help-center article copy (also served via backend support KB) | low |
| `src/content/help-center/43-data-processing-and-subprocessors.md:114` | Vectorae | A | help-center article copy (also served via backend support KB) | low |
| `src/content/help-center/43-data-processing-and-subprocessors.md:120` | Vectorae | A | help-center article copy (also served via backend support KB) | low |
| `src/content/help-center/43-data-processing-and-subprocessors.md:124` | Vectorae | A | help-center article copy (also served via backend support KB) | low |
| `src/content/help-center/43-data-processing-and-subprocessors.md:126` | Vectorae | A | help-center article copy (also served via backend support KB) | low |
| `src/content/help-center/43-data-processing-and-subprocessors.md:134` | Vectorae | A | help-center article copy (also served via backend support KB) | low |
| `src/content/help-center/44-learn-tab-and-tutorials.md:26` | Vectorae | A | help-center article copy (also served via backend support KB) | low |
| `src/content/help-center/44-learn-tab-and-tutorials.md:30` | Vectorae | A | help-center article copy (also served via backend support KB) | low |
| `src/content/help-center/44-learn-tab-and-tutorials.md:34` | Vectorae | A | help-center article copy (also served via backend support KB) | low |
| `src/content/help-center/44-learn-tab-and-tutorials.md:42` | Vectorae | A | help-center article copy (also served via backend support KB) | low |
| `src/content/help-center/44-learn-tab-and-tutorials.md:48` | Vectorae | A | help-center article copy (also served via backend support KB) | low |
| `src/content/help-center/44-learn-tab-and-tutorials.md:57` | Vectorae | A | help-center article copy (also served via backend support KB) | low |
| `src/content/help-center/44-learn-tab-and-tutorials.md:63` | Vectorae | A | help-center article copy (also served via backend support KB) | low |
| `src/content/help-center/44-learn-tab-and-tutorials.md:66` | Vectorae | A | help-center article copy (also served via backend support KB) | low |
| `src/content/plans-snapshot.json:120` | Vectorae | A | UI / public page display text | low |
| `src/content/product-facts.json:3` | Vectorae | A | product-facts source of truth (feeds JSON-LD, llms.txt, page copy) | med |
| `src/content/product-facts.json:12` | LeadPilot | C | third-party listing URL (LinkedIn/G2/Crunchbase/YouTube) in JSON-LD sameAs / contact page; owner must rename listing, URL is B | high |
| `src/content/product-facts.json:13` | LeadPilot | C | third-party listing URL (LinkedIn/G2/Crunchbase/YouTube) in JSON-LD sameAs / contact page; owner must rename listing, URL is B | high |
| `src/content/product-facts.json:14` | LeadPilot | C | third-party listing URL (LinkedIn/G2/Crunchbase/YouTube) in JSON-LD sameAs / contact page; owner must rename listing, URL is B | high |
| `src/content/product-facts.json:15` | LeadPilot | C | third-party listing URL (LinkedIn/G2/Crunchbase/YouTube) in JSON-LD sameAs / contact page; owner must rename listing, URL is B | high |
| `src/content/product-facts.json:23` | LeadPilot | C | third-party listing URL (LinkedIn/G2/Crunchbase/YouTube) in JSON-LD sameAs / contact page; owner must rename listing, URL is B | high |
| `src/content/product-facts.json:30` | Vectorae | A | product-facts source of truth (feeds JSON-LD, llms.txt, page copy) | med |
| `src/content/product-facts.json:47` | Vectorae | A | product-facts source of truth (feeds JSON-LD, llms.txt, page copy) | med |
| `src/content/product-facts.json:48` | Vectorae | A | product-facts source of truth (feeds JSON-LD, llms.txt, page copy) | med |
| `src/content/product-facts.json:87` | Vectorae | A | product-facts source of truth (feeds JSON-LD, llms.txt, page copy) | med |
| `src/content/site-pages.json:76` | LeadPilot | B | public URL path/slug (/what-is-leadpilot/, /compare/leadpilot-vs-*/, help id); indexed by search engines/LLMs, sitemap; rename needs 301 redirects | high |
| `src/content/site-pages.json:80` | LeadPilot | B | public URL path/slug (/what-is-leadpilot/, /compare/leadpilot-vs-*/, help id); indexed by search engines/LLMs, sitemap; rename needs 301 redirects | high |
| `src/content/site-pages.json:128` | LeadPilot | B | public URL path/slug (/what-is-leadpilot/, /compare/leadpilot-vs-*/, help id); indexed by search engines/LLMs, sitemap; rename needs 301 redirects | high |
| `src/content/site-pages.json:141` | LeadPilot | B | public URL path/slug (/what-is-leadpilot/, /compare/leadpilot-vs-*/, help id); indexed by search engines/LLMs, sitemap; rename needs 301 redirects | high |
| `src/content/site-pages.json:154` | LeadPilot | B | public URL path/slug (/what-is-leadpilot/, /compare/leadpilot-vs-*/, help id); indexed by search engines/LLMs, sitemap; rename needs 301 redirects | high |
| `src/content/site-pages.json:167` | LeadPilot | B | public URL path/slug (/what-is-leadpilot/, /compare/leadpilot-vs-*/, help id); indexed by search engines/LLMs, sitemap; rename needs 301 redirects | high |
| `src/content/site-pages.json:180` | LeadPilot | B | public URL path/slug (/what-is-leadpilot/, /compare/leadpilot-vs-*/, help id); indexed by search engines/LLMs, sitemap; rename needs 301 redirects | high |
| `src/content/site-pages.json:237` | LeadPilot | B | link/ref to help-center filename 01-what-is-leadpilot.md (file rename breaks link; backend help_center/support_kb also read these files) | med |
| `src/content/site-pages.json:288` | LeadPilot | B | public URL path/slug (/what-is-leadpilot/, /compare/leadpilot-vs-*/, help id); indexed by search engines/LLMs, sitemap; rename needs 301 redirects | high |
| `src/content/site-pages.json:293` | LeadPilot | B | link/ref to help-center filename 01-what-is-leadpilot.md (file rename breaks link; backend help_center/support_kb also read these files) | med |
| `src/content/sitemap-lastmod.json:9` | LeadPilot | B | public URL path/slug (/what-is-leadpilot/, /compare/leadpilot-vs-*/, help id); indexed by search engines/LLMs, sitemap; rename needs 301 redirects | high |
| `src/content/sitemap-lastmod.json:13` | LeadPilot | B | public URL path/slug (/what-is-leadpilot/, /compare/leadpilot-vs-*/, help id); indexed by search engines/LLMs, sitemap; rename needs 301 redirects | high |
| `src/content/sitemap-lastmod.json:14` | LeadPilot | B | public URL path/slug (/what-is-leadpilot/, /compare/leadpilot-vs-*/, help id); indexed by search engines/LLMs, sitemap; rename needs 301 redirects | high |
| `src/content/sitemap-lastmod.json:15` | LeadPilot | B | public URL path/slug (/what-is-leadpilot/, /compare/leadpilot-vs-*/, help id); indexed by search engines/LLMs, sitemap; rename needs 301 redirects | high |
| `src/content/sitemap-lastmod.json:16` | LeadPilot | B | public URL path/slug (/what-is-leadpilot/, /compare/leadpilot-vs-*/, help id); indexed by search engines/LLMs, sitemap; rename needs 301 redirects | high |
| `src/content/sitemap-lastmod.json:17` | LeadPilot | B | public URL path/slug (/what-is-leadpilot/, /compare/leadpilot-vs-*/, help id); indexed by search engines/LLMs, sitemap; rename needs 301 redirects | high |
| `src/content/sitemap-lastmod.json:22` | LeadPilot | B | public URL path/slug (/what-is-leadpilot/, /compare/leadpilot-vs-*/, help id); indexed by search engines/LLMs, sitemap; rename needs 301 redirects | high |
| `src/contexts/NetworkContext.tsx:4` | ClientHunter | A | A-comment (code comment/docstring) | low |
| `src/hooks/useBackButton.ts:4` | ClientHunter | A | A-comment (code comment/docstring) | low |
| `src/hooks/useBackButton.ts:11` | Vectorae | A | A-comment (code comment/docstring) | low |
| `src/hooks/useBackButton.ts:48` | Vectorae | A | UI / public page display text | low |
| `src/hooks/useNetwork.ts:4` | ClientHunter | A | A-comment (code comment/docstring) | low |
| `src/hooks/usePushNotifications.ts:4` | ClientHunter | A | A-comment (code comment/docstring) | low |
| `src/hooks/useStatusBar.ts:4` | ClientHunter | A | A-comment (code comment/docstring) | low |
| `src/lib/api/auth.ts:105` | LeadPilot | B | browser storage key (localStorage/sessionStorage); renaming drops users' saved theme/workspace/defer state unless migrated | high |
| `src/lib/api/client.ts:7` | LeadPilot | B | A-comment naming old localStorage key (mentions removed/legacy key) | low |
| `src/lib/api/client.ts:14` | LeadPilot | B | A-comment naming old localStorage key (mentions removed/legacy key) | low |
| `src/lib/api/meetingPrep.ts:54` | LeadPilot | B | meeting source enum value from backend API (DB/webhook payload value) | high |
| `src/lib/api/trust.ts:90` | Vectorae | A | A-comment (code comment/docstring) | low |
| `src/lib/api/tutorials.ts:5` | Vectorae | A | A-comment (code comment/docstring) | low |
| `src/lib/api/types.ts:49` | Vectorae | A | A-comment (code comment/docstring) | low |
| `src/lib/audit.ts:56` | LeadPilot | A | download/export filename shown to user; judge: customer scripts may match it | low |
| `src/lib/auth-session.ts:2` | ClientHunter | A | A-comment (code comment/docstring) | low |
| `src/lib/branding.ts:24` | Vectorae | A | default white-label brand_name | med |
| `src/lib/content/types.ts:2` | LeadPilot | A | A-comment mentioning URL slug/path (the slug itself is B elsewhere) | low |
| `src/lib/deeplinks.ts:2` | ClientHunter | A | A-comment (code comment/docstring) | low |
| `src/lib/deeplinks.ts:7` | ClientHunter | B | deep-link URL scheme clienthunter:// / App Links host (Android intent filter, push payloads depend) | high |
| `src/lib/deeplinks.ts:8` | ClientHunter | B | deep-link URL scheme clienthunter:// / App Links host (Android intent filter, push payloads depend) | high |
| `src/lib/deeplinks.ts:15` | ClientHunter | B | deep-link URL scheme clienthunter:// / App Links host (Android intent filter, push payloads depend) | high |
| `src/lib/deeplinks.ts:25` | ClientHunter | B | deep-link URL scheme clienthunter:// / App Links host (Android intent filter, push payloads depend) | high |
| `src/lib/deeplinks.ts:34` | ClientHunter | B | deep-link URL scheme clienthunter:// / App Links host (Android intent filter, push payloads depend) | high |
| `src/lib/deeplinks.ts:63` | ClientHunter | B | deep-link URL scheme clienthunter:// / App Links host (Android intent filter, push payloads depend) | high |
| `src/lib/deeplinks.ts:184` | ClientHunter | B | deep-link URL scheme clienthunter:// / App Links host (Android intent filter, push payloads depend) | high |
| `src/lib/deeplinks.ts:187` | ClientHunter | B | deep-link URL scheme clienthunter:// / App Links host (Android intent filter, push payloads depend) | high |
| `src/lib/guardrails.ts:82` | Vectorae | A | UI / public page display text | low |
| `src/lib/guardrails.ts:112` | Vectorae | A | UI / public page display text | low |
| `src/lib/identity.ts:75` | LeadPilot | B | browser storage key (localStorage/sessionStorage); renaming drops users' saved theme/workspace/defer state unless migrated | high |
| `src/lib/meetingsLedger.ts:39` | LeadPilot | A | download/export filename shown to user; judge: customer scripts may match it | low |
| `src/lib/oauthConsent.ts:52` | Vectorae | A | A-comment (code comment/docstring) | low |
| `src/lib/passwordReset.ts:12` | Vectorae | A | UI / public page display text | low |
| `src/lib/pilot.ts:252` | LeadPilot | A | download/export filename shown to user; judge: customer scripts may match it | low |
| `src/lib/platform.ts:2` | ClientHunter | A | A-comment (code comment/docstring) | low |
| `src/lib/productFacts.ts:22` | Vectorae | A | A-comment (code comment/docstring) | low |
| `src/lib/profile.ts:41` | LeadPilot | A | download/export filename shown to user; judge: customer scripts may match it | low |
| `src/lib/profile.ts:43` | LeadPilot | A | download/export filename shown to user; judge: customer scripts may match it | low |
| `src/lib/profile.ts:79` | Vectorae | A | UI / public page display text | low |
| `src/lib/replyCopilot.ts:97` | Vectorae | A | A-comment (code comment/docstring) | low |
| `src/lib/seo/llmsTxt.ts:27` | Vectorae | A | UI / public page display text | low |
| `src/lib/seo/llmsTxt.ts:32` | Vectorae | A | UI / public page display text | low |
| `src/lib/seo/llmsTxt.ts:33` | LeadPilot, Vectorae | B | copy line that also links to public URL path/slug (/what-is-leadpilot/, /compare/leadpilot-vs-*/, help id); indexed by search engines/LLMs, sitemap; rename needs 301 redirects | high |
| `src/lib/seo/llmsTxt.ts:38` | Vectorae | A | UI / public page display text | low |
| `src/lib/seo/structuredData.ts:75` | Vectorae | A | A-comment (code comment/docstring) | low |
| `src/lib/statusBoard.ts:15` | Vectorae | A | A-comment (code comment/docstring) | low |
| `src/lib/statusBoard.ts:66` | Vectorae | A | UI / public page display text | low |
| `src/lib/statusBoard.ts:74` | Vectorae | A | UI / public page display text | low |
| `src/lib/statusBoard.ts:75` | Vectorae | A | UI / public page display text | low |
| `src/lib/statusBoard.ts:76` | Vectorae | A | UI / public page display text | low |
| `src/lib/statusBoard.ts:77` | Vectorae | A | UI / public page display text | low |
| `src/lib/storage.ts:2` | ClientHunter | A | A-comment (code comment/docstring) | low |
| `src/lib/theme/ThemeProvider.tsx:36` | LeadPilot | B | A-comment naming old localStorage key (mentions removed/legacy key) | low |
| `src/lib/theme/apply.ts:68` | LeadPilot | B | browser storage key (localStorage/sessionStorage); renaming drops users' saved theme/workspace/defer state unless migrated | high |
| `src/lib/workspace.ts:8` | LeadPilot | B | browser storage key (localStorage/sessionStorage); renaming drops users' saved theme/workspace/defer state unless migrated | high |
| `src/tests/OfflineBanner.test.tsx:2` | ClientHunter | A | A-comment (code comment/docstring) | low |
| `src/tests/audit.test.ts:41` | LeadPilot | A | download/export filename shown to user (test asserts it); judge: customer scripts may match it | med |
| `src/tests/deeplinks.test.ts:2` | ClientHunter | A | A-comment (code comment/docstring) | low |
| `src/tests/deeplinks.test.ts:21` | ClientHunter | B | deep-link URL scheme clienthunter:// / App Links host (Android intent filter, push payloads depend) (test) | med |
| `src/tests/deeplinks.test.ts:23` | ClientHunter | B | deep-link URL scheme clienthunter:// / App Links host (Android intent filter, push payloads depend) (test) | med |
| `src/tests/deeplinks.test.ts:28` | ClientHunter | B | deep-link URL scheme clienthunter:// / App Links host (Android intent filter, push payloads depend) (test) | med |
| `src/tests/deeplinks.test.ts:33` | ClientHunter | B | deep-link URL scheme clienthunter:// / App Links host (Android intent filter, push payloads depend) (test) | med |
| `src/tests/deeplinks.test.ts:38` | ClientHunter | B | deep-link URL scheme clienthunter:// / App Links host (Android intent filter, push payloads depend) (test) | med |
| `src/tests/deeplinks.test.ts:43` | ClientHunter | B | deep-link URL scheme clienthunter:// / App Links host (Android intent filter, push payloads depend) (test) | med |
| `src/tests/deeplinks.test.ts:48` | ClientHunter | B | deep-link URL scheme clienthunter:// / App Links host (Android intent filter, push payloads depend) (test) | med |
| `src/tests/deeplinks.test.ts:53` | ClientHunter | B | deep-link URL scheme clienthunter:// / App Links host (Android intent filter, push payloads depend) (test) | med |
| `src/tests/deeplinks.test.ts:58` | ClientHunter | B | deep-link URL scheme clienthunter:// / App Links host (Android intent filter, push payloads depend) (test) | med |
| `src/tests/deeplinks.test.ts:63` | ClientHunter | B | deep-link URL scheme clienthunter:// / App Links host (Android intent filter, push payloads depend) (test) | med |
| `src/tests/deeplinks.test.ts:93` | ClientHunter | B | deep-link URL scheme clienthunter:// / App Links host (Android intent filter, push payloads depend) (test) | med |
| `src/tests/deeplinks.test.ts:109` | ClientHunter | B | deep-link URL scheme clienthunter:// / App Links host (Android intent filter, push payloads depend) (test) | med |
| `src/tests/deeplinks.test.ts:134` | ClientHunter | B | deep-link URL scheme clienthunter:// / App Links host (Android intent filter, push payloads depend) (test) | med |
| `src/tests/deeplinks.test.ts:137` | ClientHunter | B | deep-link URL scheme clienthunter:// / App Links host (Android intent filter, push payloads depend) (test) | med |
| `src/tests/deeplinks.test.ts:148` | ClientHunter | B | deep-link URL scheme clienthunter:// / App Links host (Android intent filter, push payloads depend) (test) | med |
| `src/tests/deeplinks.test.ts:154` | ClientHunter | B | deep-link URL scheme clienthunter:// / App Links host (Android intent filter, push payloads depend) (test) | med |
| `src/tests/deeplinks.test.ts:155` | ClientHunter | B | deep-link URL scheme clienthunter:// / App Links host (Android intent filter, push payloads depend) (test) | med |
| `src/tests/deeplinks.test.ts:165` | ClientHunter | B | deep-link URL scheme clienthunter:// / App Links host (Android intent filter, push payloads depend) (test) | med |
| `src/tests/geoPages.test.ts:27` | Vectorae | A | test asserts/uses display string (update with copy) | med |
| `src/tests/geoPages.test.ts:28` | Vectorae | A | test asserts/uses display string (update with copy) | med |
| `src/tests/geoPages.test.ts:33` | Vectorae | A | test asserts/uses display string (update with copy) | med |
| `src/tests/geoPages.test.ts:66` | LeadPilot | B | public URL path/slug (/what-is-leadpilot/, /compare/leadpilot-vs-*/, help id); indexed by search engines/LLMs, sitemap; rename needs 301 redirects (test) | high |
| `src/tests/geoPages.test.ts:96` | LeadPilot | C | refers to a DIFFERENT company (LeadPilot AB, leadpilot.com) in disambiguation text; must NOT be renamed blindly (test asserts it) | high |
| `src/tests/guardrails.test.ts:32` | Vectorae | A | test asserts/uses display string (update with copy) | med |
| `src/tests/guardrails.test.ts:60` | Vectorae | A | test asserts/uses display string (update with copy) | med |
| `src/tests/homeClaims.test.ts:8` | Vectorae | A | A-comment (code comment/docstring) | low |
| `src/tests/homeClaims.test.ts:32` | LeadPilot | B | media file name /media/leadpilot-walkthrough.* (file path; og:image URL is public) | med |
| `src/tests/homeClaims.test.ts:40` | Vectorae | A | test asserts/uses display string (update with copy) | med |
| `src/tests/meetingsLedger.test.ts:33` | LeadPilot | A | download/export filename shown to user (test asserts it); judge: customer scripts may match it | med |
| `src/tests/meetingsLedger.test.ts:35` | LeadPilot | A | download/export filename shown to user (test asserts it); judge: customer scripts may match it | med |
| `src/tests/oauthConsent.test.ts:46` | Vectorae | A | test asserts/uses display string (update with copy) | med |
| `src/tests/pilot.test.ts:159` | LeadPilot | A | download/export filename shown to user (test asserts it); judge: customer scripts may match it | med |
| `src/tests/pilot.test.ts:161` | LeadPilot | A | download/export filename shown to user (test asserts it); judge: customer scripts may match it | med |
| `src/tests/profile.test.ts:47` | LeadPilot | A | download/export filename shown to user (test asserts it); judge: customer scripts may match it | med |
| `src/tests/pushNotifications.test.ts:2` | ClientHunter | A | A-comment (code comment/docstring) | low |
| `src/tests/sendApproval.test.ts:143` | ClientHunter | B | deep-link URL scheme clienthunter:// / App Links host (Android intent filter, push payloads depend) (test) | med |
| `src/tests/sendApproval.test.ts:144` | ClientHunter | B | deep-link URL scheme clienthunter:// / App Links host (Android intent filter, push payloads depend) (test) | med |
| `src/tests/statusBoard.test.ts:263` | Vectorae | A | test asserts/uses display string (update with copy) | med |
| `src/tests/statusBoardPage.test.tsx:56` | LeadPilot | B | API host / Render service name (leadpilot-api) (test fixture) | low |
| `src/tests/statusBoardPage.test.tsx:60` | Vectorae | A | test asserts/uses display string (update with copy) | med |
| `src/tests/storage.test.ts:2` | ClientHunter | A | A-comment (code comment/docstring) | low |
| `src/tests/supportSources.test.tsx:45` | Vectorae | A | test asserts/uses display string (update with copy) | med |
| `src/tests/supportSources.test.tsx:59` | Vectorae | A | test asserts/uses display string (update with copy) | med |
| `src/tests/supportSources.test.tsx:82` | Vectorae | A | test asserts/uses display string (update with copy) | med |
| `src/tests/templateEditor.test.tsx:27` | Vectorae | DEFECT | WhatsApp template example in product name: customer-voice placeholder "Sam from Vectorae" a customer may copy into messages they send (test asserts it) | high |
| `src/tests/templateEditor.test.tsx:81` | Vectorae | DEFECT | WhatsApp template example in product name: customer-voice placeholder "Sam from Vectorae" a customer may copy into messages they send (test asserts it) | high |
| `src/tests/useBackButton.test.ts:2` | ClientHunter | A | A-comment (code comment/docstring) | low |
| `src/tests/useBackButton.test.ts:82` | Vectorae | A | test asserts/uses display string (update with copy) | med |
| `tests/e2e/mobile.spec.ts:36` | ClientHunter | A | A-comment (code comment/docstring) | low |
| `tests/e2e/mobile.spec.ts:160` | ClientHunter | B | deep-link URL scheme clienthunter:// / App Links host (Android intent filter, push payloads depend) (test) | med |
| `video-src/render.mjs:8` | LeadPilot | B | media file name /media/leadpilot-walkthrough.* (file path; og:image URL is public) | med |
| `video-src/render.mjs:9` | LeadPilot | B | media file name /media/leadpilot-walkthrough.* (file path; og:image URL is public) | med |
| `video-src/render.mjs:10` | LeadPilot | B | media file name /media/leadpilot-walkthrough.* (file path; og:image URL is public) | med |
| `video-src/render.mjs:12` | LeadPilot | B | media file name /media/leadpilot-walkthrough.* (file path; og:image URL is public) | med |
| `video-src/render.mjs:34` | LeadPilot | B | media file name /media/leadpilot-walkthrough.* (file path; og:image URL is public) | med |
| `video-src/walkthrough.html:3` | LeadPilot, Vectorae | B | media file name /media/leadpilot-walkthrough.* (file path; og:image URL is public) | med |
| `video-src/walkthrough.html:18` | Vectorae | A | page <title>/meta | med |
| `video-src/walkthrough.html:152` | Vectorae | A | UI / public page display text | low |
| `video-src/walkthrough.html:213` | Vectorae | A | UI / public page display text | low |
| `video-src/walkthrough.html:255` | Vectorae | A | UI / public page display text | low |

(Paths are relative to `frontend/`.)

## 3. File / directory NAMES containing a variant

| path | variant | class | reason | risk |
|---|---|---|---|---|
| `frontend/src/app/what-is-leadpilot/page.tsx` (dir `what-is-leadpilot/`) | LeadPilot | B | Next.js route dir = public URL `/what-is-leadpilot/` (sitemap, llms.txt, site-pages.json, internal links, search/LLM index). Rename needs a redirect | high |
| `frontend/src/content/help-center/01-what-is-leadpilot.md` | LeadPilot | B | copy of `docs/help-center/01-what-is-leadpilot.md` (synced); article id `what-is-leadpilot` = URL `/help/what-is-leadpilot/`; linked by filename from 02, 26, 28 and site-pages.json; backend support KB reads the docs/ original | high |
| `frontend/public/media/leadpilot-walkthrough.mp4` | LeadPilot | B | public media URL; referenced by home content.ts, page.tsx og:image, homeClaims.test.ts, render.mjs `NAME` | med |
| `frontend/public/media/leadpilot-walkthrough.webm` | LeadPilot | B | same | med |
| `frontend/public/media/leadpilot-walkthrough-poster.jpg` | LeadPilot | B | same; is the home page og:image / twitter image URL (shared links cache it) | med |
| `frontend/public/media/leadpilot-walkthrough.en.vtt` | LeadPilot | B | captions; cues must match `src/components/home/content.ts` (test-enforced) | med |
| Compare routes `/compare/leadpilot-vs-{apollo,instantly,smartlead,clay,artisan}/` (generated from `src/app/compare/[slug]/page.tsx` + `PREFIX = "leadpilot-vs-"`, no file on disk) | LeadPilot | B | public URLs, in sitemap + llms.txt | high |

## 4. Generated or git-ignored files

- `frontend/src/content/help-center/*.md` (44 files, 464 hit lines across 44 of them): **generated copy** of `docs/help-center/NN-*.md` by `node scripts/help/sync_help_center.mjs` (run from `frontend/`). All 44 are byte-identical today; `src/tests/helpCenterCopy.test.ts` fails on drift. Change `docs/help-center/` (another agent's area) and re-sync; never edit the copy.
- `/llms.txt`: not a file; built at build time by `src/app/llms.txt/route.ts` from `src/lib/seo/llmsTxt.ts` + `product-facts.json`.
- `sitemap.xml`: built by `src/app/sitemap.ts` from `src/content/site-pages.json` + `src/content/sitemap-lastmod.json`. `sitemap-lastmod.json` is regenerated by `node scripts/seo/lastmod.mjs` (git dates); it holds the `leadpilot` slugs as keys.
- `package-lock.json` name `clienthunter-web`: regenerates from `package.json` on `npm install`.
- `public/media/leadpilot-walkthrough.{mp4,webm,-poster.jpg,.en.vtt}`: rendered by `video-src/render.mjs` from `video-src/walkthrough.html` (`const NAME = "leadpilot-walkthrough"`). The video frames and poster burn in the "Vectorae" brand (walkthrough.html:152, 213, 255) — re-render needed, not a text edit.
- Ignored and not inventoried: `.next/`, `out/` (static export; contains copies of everything above), `node_modules/`, `playwright-report/`, `test-results/`, `coverage/`, `next-env.d.ts`.
- No service worker / Workbox / cache-name file exists in `frontend/` (checked `git ls-files` for sw/service-worker/workbox). `frontend/vercel.json` and `frontend/.env.example` have zero hits.

## 5. Surprises and things a find-and-replace would break

1. **DEFECT (customer voice)**: `src/components/campaigns/TemplateEditor.tsx:70` WhatsApp template placeholder `"Hi {{1}}, Sam from Vectorae. Reply STOP to opt out."`. This is the example body for a template the CUSTOMER submits to Meta and sends to their prospects. It models putting our product name in the customer's message. `src/tests/templateEditor.test.tsx:27,81` assert it. Report, not a rename item: the example should not name any product.
2. **"LeadPilot" that must NOT be renamed**: `src/content/geo/shared.ts:53` (`DISAMBIGUATION`), `src/content/geo/faq.ts:28`, asserted by `src/tests/geoPages.test.ts:96` ("not affiliated with LeadPilot AB"). They name a different Swedish company (LeadPilot AB, leadpilot.com). After a rebrand away from Vectorae this sentence may no longer be needed, but blind replacement would make it nonsense. `next.config.js:109` uses `https://api.leadpilot.com` as the example API origin in a build-error message — that domain belongs to LeadPilot AB.
3. **Brand-derived storage keys that the regex does not catch** (B, risk high, rename = users lose session/theme on upgrade unless migrated): `ch_access_token`, `ch_refresh_token`, `ch_user_email`, `ch_user_id` (`src/lib/auth-session.ts:28-31`; also Capacitor Preferences on Android), `ch_theme` (`src/lib/theme/ThemeProvider.tsx:41`, `src/app/layout.tsx:63`), `ch_push_permission_denied`, `ch_push_reshow_prompted` (`src/hooks/usePushNotifications.ts:40-41`), `lp_oauth_consent_request` (`src/lib/oauthConsent.ts:10`). Asserted in `src/tests/session-restore.test.ts`, `storage.test.ts`, `pushNotifications.test.ts`, and e2e specs (`e2e/email-verification.spec.ts:141`, `support-chat.spec.ts:43`, `tutorials.spec.ts:197`). The regex-matched keys are `leadpilot.theme` (`src/lib/theme/apply.ts:68` reads it; `src/lib/api/auth.ts:105` removes it), `leadpilot.workspace` (`src/lib/workspace.ts:8`), `leadpilot.verify.phone-deferred` (`src/lib/identity.ts:75`). Note that two theme keys coexist (`leadpilot.theme` in localStorage via apply.ts NO_FLASH_SCRIPT, `ch_theme` in sessionStorage via layout.tsx). ThemeProvider.tsx:33-41 says that mismatch was an earlier bug. Out of scope, reported only.
4. CSS class prefix `lp-` (`lp-home`, `lp-btn`, `lp-wordmark`, `lp-grid`, `lp-auth`...) in home/signup pages: internal, nothing external depends on it, not inventoried. Optional cleanup.
5. **Deep-link scheme `clienthunter://` and host `app.clienthunter.com`** (`src/lib/deeplinks.ts:25,34`) are still the OLD-OLD brand and are B. The Android intent filter (other agent) and server push payloads (`clienthunter:///send-approval`, `src/tests/sendApproval.test.ts:143`) must change together. `app.clienthunter.com` is marked `TODO: confirm production domain` — probably not a live domain.
6. `public/.well-known/assetlinks.json:6` `com.clienthunter.app` must equal the Play Store applicationId. Changing it is effectively a new app listing. Help article `26-mobile-app.md:39` states it to users.
7. Webhook headers `X-LeadPilot-Event/-Delivery/-Signature` plus legacy `X-ClientHunter-Signature` are documented to customers (WebhooksCard.tsx:146, help 37 and 42). API key prefix `lpk_` too (WebhooksCard.tsx:240, help 16, 23 and 28). Customer integrations depend on these. Keep them and add aliases. Do not rename.
8. `leadpilot_calendar` (MeetingPrepPanel.tsx:33, api/meetingPrep.ts:54, help 37:75) is a backend enum stored in DB (`app/db/models.py:2871`, `app/services/meeting_prep.py:68`) and sent in webhook payloads. Tutorial slugs `getting-started-with-leadpilot`, `using-the-leadpilot-dashboard` and badge `leadpilot-certified` (e2e/tutorials.spec.ts) come from `app/services/tutorials.py:97` and user-progress rows.
9. **Legal / C items**: Terms (`src/app/terms/page.tsx`) and Privacy (`src/app/privacy/page.tsx`) name "Vectorae Enterprise" operated by "Calendarharvest". terms/page.tsx:26 (comment) says "No legal entity yet: 'Calendarharvest' is a trading name". Footer `© 2026 Calendarharvest` (Footer.tsx:112); `product-facts.json:4,7` company_name/Organization. OAuth consent screen "<app> wants to connect to Vectorae" (`src/app/oauth/consent/page.tsx:80`). Voice-twin data statements (`VoiceTwinCard.tsx:150,233,312`). Third-party listings in JSON-LD `sameAs`: `linkedin.com/company/leadpilot-app`, `g2.com/products/leadpilot-2026-10-14`, `crunchbase.com/organization/leadpilot`, `youtube.com/@LeadPilotEnterprise`, and founder `linkedin.com/in/rehan-rana-leadpilot` (product-facts.json:12-15,23; contact/page.tsx:26). These URLs belong to accounts the founders must rename or recreate. Logo: `public/brand/logo-full.png` artwork contains the "VECTORAE" wordmark (Logo.tsx:5); `public/icons/*.png` should be checked visually.
10. **Prospect-facing attribution** (A, but seen by the customer's prospects, not the customer): `src/app/book/page.tsx:312` "Scheduling by Vectorae" on public booking pages, and `src/app/share/roi/page.tsx:132` "Powered by Vectorae". Not customer-voice text, but it is platform branding inside the customer's funnel. White-label (`src/lib/branding.ts:24` default `brand_name: "Vectorae"`) does not appear to cover these two hard-coded strings. ASSUMPTION, not verified.
11. Public URL slugs carry `leadpilot` while page copy says Vectorae: `/what-is-leadpilot/`, `/help/what-is-leadpilot/`, `/compare/leadpilot-vs-*/`. They appear in site-pages.json, sitemap-lastmod.json, Footer.tsx, llmsTxt.ts, geo content links and geoPages.test.ts:66. A rename needs Vercel 301 redirects (static export; `vercel.json` has none today for these).
12. Export filenames `leadpilot-audit-*`, `leadpilot-meetings-ledger-*`, `leadpilot-pilot-verdict-*`, `leadpilot-account-export-*` (lib/audit.ts, meetingsLedger.ts, pilot.ts, profile.ts) are pinned by unit tests and quoted in help article 21. Classed A (filename the user sees). A customer's scripts could match them.
13. `scripts/seo/snapshot_plans.mjs:26` defaults to `https://leadpilot-api-ph3t.onrender.com`, the Render service name (B, other agent's render.yaml). npm package `clienthunter-web` (package.json:2) is private, so nothing external depends on it.

### Frontend tests that assert brand strings (must change in the same commit as the copy)
- Display (A): `e2e/support-chat.spec.ts` (refusal text "I can only help with questions about Vectorae", suggestion "What is Vectorae?"), `e2e/tutorials.spec.ts` ("Learn Vectorae", tutorial titles), `src/tests/useBackButton.test.ts:82` ("Exit Vectorae?"), `statusBoard.test.ts:263` and `statusBoardPage.test.tsx:60` ("Vectorae API unreachable — major outage"), `guardrails.test.ts:32,60` ("Vectorae CRM"), `supportSources.test.tsx:45,59,82`, `geoPages.test.ts:27,28,33` ("Written by Vectorae's founders", "When to choose Vectorae", title contains "Vectorae by Calendarharvest"), `homeClaims.test.ts:116` and `websiteClaims.test.ts:66-69` (every title ends "| Calendarharvest", Footer contains "Calendarharvest"), `templateEditor.test.tsx:27,81` (DEFECT example), and the export-filename tests (audit, meetingsLedger, pilot, profile).
- Identifier (B): `deeplinks.test.ts` (18 lines, `clienthunter:///`), `sendApproval.test.ts:143-144`, `tests/e2e/mobile.spec.ts:160`, `homeClaims.test.ts:32` (vtt path), `geoPages.test.ts:66` (slug), `e2e/tutorials.spec.ts` slugs and badge, and `session-restore`/`storage`/`pushNotifications` tests (`ch_*` keys, §5.3).
- Guard (C): `geoPages.test.ts:96` (LeadPilot AB disambiguation).
- `helpCenterCopy.test.ts` forces the frontend help-center copy to equal `docs/help-center`.

## 6. Calendarharvest (company/trading name + domain): not table rows

97 occurrences on 28 lines without another variant, plus most `title:` lines (`"... Vectorae by Calendarharvest ... | Calendarharvest"`). It is the company and domain, not the product name, so it is excluded from the table per the brief. Relevant points:
- Domain uses (B, live production, keep): robots.txt:79, scripts/seo/check_static_seo.mjs:23, indexnow.json:3, indexnow_submit.mjs:8, site-pages.json:2, product-facts.json:8-9, contact/privacy/terms `ahmadshahid@calendarharvest.com`, help 03:78 `noreply@calendarharvest.com`, help 29:107 and 30:100 status URL.
- Company-name uses (C, legal entity question): terms/page.tsx:26,44,129; privacy/page.tsx:57; Footer.tsx:112; product-facts.json:4,7; geo/whatIs.ts:76; geo/faq.ts:28. `PRODUCT_FULL_NAME` "Vectorae by Calendarharvest" is built in `src/lib/productFacts.ts:22` from product-facts.json, so most titles and JSON-LD change through product-facts.json and not per page.

# Part 3 — Brand inventory: Android, Capacitor, native cores, Python SDK

_Source: subagent sweep, file `brand-android-native-sdk.md`._

Area: `frontend/android/`, `frontend/capacitor.config.ts`, `native/`, `sdk/` (git-tracked files only, repo HEAD `7872f9c6`). Read-only sweep; no repo file modified.
Regex: `git grep -nIiE 'lead[ _.-]?pilot|client[ _.-]?hunter|vectorae|victorae'` (also checked `lpk_`, `calendarharvest`: **0 hits** in this area; `LeadPilot`/`Victorae`: **0 hits** in this area).

## 1. Summary

Matching lines: **455** in **49 files** (android 27 lines/7 files, capacitor.config.ts 2/1, native 49/14, sdk 377/27). Raw occurrences (`git grep -o`): 495.

| Class | Lines |
|---|---|
| A (display, incl. A-comment 108, A-test 2) | 245 (A 135 + A-comment 108 + A-test 2) |
| B (identifier, incl. B-test 70) | 209 (B 139 + B-test 70) |
| C (needs human) | 1 in-area line (pyproject author/mailbox) + out-of-area Play listing docs (see §5) |
| DEFECT (customer-voice) | 0 |

| Variant (occurrences) | Count | Where |
|---|---|---|
| `clienthunter` | 308 | SDK package/CLI/imports, Android ids |
| `ClientHunter` | 121 | SDK class + prose, Android comments/strings |
| `CLIENTHUNTER` | 15 | SDK env vars `CLIENTHUNTER_API_URL` / `CLIENTHUNTER_API_KEY` |
| `vectorae` | 44 | native crate/module/namespace names |
| `Vectorae` | 7 | `capacitor.config.ts` appName, native descriptions/comments |
| LeadPilot / Lead Pilot / Victorae / lpk_ / calendarharvest | 0 | — |

Per-area counts by class (lines):

| Area | A | A-comment | A-test | B | B-test | C |
|---|---|---|---|---|---|---|
| frontend/android + capacitor.config.ts | 3 | 16 | 0 | 10 | 0 | 0 |
| native/ | 7 | 5 | 1 | 33 | 3 | 0 |
| sdk/ | 125 (incl. 90 in README/docs) | 87 | 1 | 96 | 67 | 1 |

Key answers to the brief's questions:

- **Android appId / applicationId / namespace (B):** `com.clienthunter.app` everywhere (`capacitor.config.ts:8`, `build.gradle:27,31`, `strings.xml:5,6`, `proguard-rules.pro:16`). Dev flavor = `com.clienthunter.app.dev`. **No Java/Kotlin package dirs are committed** (no `app/src/main/java/`), so no directory rename exists. Same id is outside the area in `frontend/public/.well-known/assetlinks.json:6`, `.env.example:278 ANDROID_PACKAGE_NAME`, `docs/FIREBASE_SETUP_CHECKLIST.md:24`, `docs/DEPLOY.md:105`, help-center 26-mobile-app.md. The capacitor.config.ts comment says appId "CANNOT be changed after the first Play Store publish". Whether it has been published is not shown in the repo (assetlinks still holds `REPLACE_WITH_REAL_SHA256_FINGERPRINT_IN_CHUNK_4`, `versionCode 1`). ASSUMPTION: it has not been published, so renaming is still possible but is a founder decision (classed B).
- **Deep-link scheme (B):** `clienthunter://` (Manifest:103), emitted by `app/services/notifications.py:130` and parsed by `frontend/src/lib/deeplinks.ts` + `frontend/src/tests/deeplinks.test.ts` (outside the area). App Links host is `app.clienthunter.com` (Manifest:133).
- **appName (A):** `capacitor.config.ts:9 appName: 'Vectorae'`. But **`strings.xml:3 app_name` = `ClientHunter`** and `title_activity_main` = `ClientHunter`. The launcher label comes from strings.xml (`android:label="@string/app_name"`), and `cap sync` does not rewrite it, so **the installed app would show "ClientHunter" today**, not "Vectorae".
- **Google Play listing text (C):** not in this area. It lives in `docs/STORE_ASSETS.md` (9 lines: title `ClientHunter Enterprise`, short/full description) and `docs/PLAY_STORE_CHECKLIST.md` (9 lines). Both need a human because the founder types them into Play Console. Privacy URL there is `https://app.clienthunter.com/privacy`.
- **google-services.json / Firebase (B):** **not committed and not present on disk.** `build.gradle:170` applies `com.google.gms.google-services` and needs it. The Firebase project id is unknown from the repo. The Firebase Android app is registered against package `com.clienthunter.app` (docs/FIREBASE_SETUP_CHECKLIST.md:24), so any applicationId change needs a new Firebase Android app and a new google-services.json.
- **Icons / splash / wordmark (C):** no `res/mipmap*` or `res/drawable*` is committed in `frontend/android`. `capacitor.config.ts` names `androidSplashResourceName: 'splash'`, which does not exist in git. Nothing to inventory, and the logo is a human task anyway.
- **SDK (B):** PyPI dist name `clienthunter` (`sdk/pyproject.toml:6`), import name `clienthunter` (`sdk/src/clienthunter/`), CLI command `clienthunter` (console_scripts `pyproject.toml:56`), public classes `ClientHunter` and `ClientHunterError` (+ 6 subclasses), env vars `CLIENTHUNTER_API_URL` and `CLIENTHUNTER_API_KEY` (`config.py:145,149,189`), config dir `~/.clienthunter/config.toml` (`config.py:34`), default API `https://api.clienthunter.ai` (`config.py:33`, `cli/_init.py:15`), and self-host DB name `clienthunter` (`cli/_serve.py:115,120,146`). **PyPI check (2026-10-20):** `clienthunter`, `vectorae`, `victorae`, `leadpilot`, `vectorae-native-rs` and `vectorae-native-cpp` all return **404** (unclaimed). The control (`requests`) returned 200. Nothing has been published, so the PyPI name can still change at no cost. **User-Agent:** the SDK sets none (`client.py` builds only auth headers), so other sites see the httpx default `python-httpx/<ver>`. There is no brand in the UA.
- **SDK README / docstrings (A):** `sdk/README.md` (31), `sdk/docs/cli.md` (43), `sdk/docs/sdk.md` (13), `sdk/RELEASING.md` (3). These are prose plus code samples quoting the B identifiers above, so they change only when the B identifiers change.
- **Crate / library names (B):** Rust crate and lib `vectorae_native_rs` (`Cargo.toml:2,9`), maturin `module-name` (`rust/pyproject.toml:13`), `#[pymodule] fn vectorae_native_rs` (`lib.rs:70`), dist `vectorae-native-rs`. C++: pybind11 module `vectorae_native_cpp` (`CMakeLists.txt:18`, `bindings.cpp:12`), dist `vectorae-native-cpp`, static lib `vectorae_core`, `namespace vectorae`, include dir `include/vectorae/`. These module names are imported outside the area by `app/agents/native.py`, `tests/test_agents_native_parity.py` and `.github/workflows/verify.yml:230`. The C++ namespace, include dir and `vectorae_core` are internal only and can be renamed in one commit.
- **Android build toolchain in this container:** `java` present = OpenJDK **21.0.12** (`/usr/bin/java`). `gradle` present = **Gradle 8.14.3** (`/opt/gradle/bin/gradle`). **`ANDROID_HOME` and `ANDROID_SDK_ROOT` are unset, and there is no `sdkmanager` and no Android SDK.** The committed Android project is also incomplete: there is no root `build.gradle`, `settings.gradle`, `variables.gradle`, `capacitor.build.gradle`, gradle wrapper, MainActivity or google-services.json. **An Android build cannot be run here**, so any Android rename can only be checked statically (grep or a Gradle/XML parse), not by assembling an APK.

## 2. Occurrence table

Every line in the area is listed. B and C rows are one row each. SDK README/docs rows (all class A) are grouped per file and reason, with line lists. Risk: HIGH = an external system, existing users or a published artifact depends on it.

| path:line | variant | class | reason | risk |
|---|---|---|---|---|
| frontend/android/app/build.gradle:1 | ClientHunter | A-comment | file header comment | low |
| frontend/android/app/build.gradle:27 | clienthunter | B | Gradle `namespace "com.clienthunter.app"` (R/BuildConfig package; must match proguard keep + any future Java sources) | med: renaming breaks generated R class refs; does not change store identity |
| frontend/android/app/build.gradle:31 | clienthunter | B | `applicationId "com.clienthunter.app"` (Play Store identity; dev flavor adds `.dev`) | HIGH: permanent after first Play publish; also bound to FCM google-services.json, assetlinks.json, ANDROID_PACKAGE_NAME env |
| frontend/android/app/proguard-rules.pro:1 | ClientHunter | A-comment | file header comment | low |
| frontend/android/app/proguard-rules.pro:16 | clienthunter | B | `-keep class com.clienthunter.app.**` (must track namespace) | med: if namespace changes and this is not, R8 may strip app classes in release |
| frontend/android/app/src/main/AndroidManifest.xml:3 | ClientHunter | A-comment | file header comment | low |
| frontend/android/app/src/main/AndroidManifest.xml:90 | clienthunter | A-comment | comment documenting `clienthunter://` scheme (B) | low; update only with scheme |
| frontend/android/app/src/main/AndroidManifest.xml:94 | clienthunter | A-comment | comment example deep link (scheme B) | low |
| frontend/android/app/src/main/AndroidManifest.xml:95 | clienthunter | A-comment | comment example deep link (scheme B) | low |
| frontend/android/app/src/main/AndroidManifest.xml:96 | clienthunter | A-comment | comment example deep link (scheme B) | low |
| frontend/android/app/src/main/AndroidManifest.xml:97 | clienthunter | A-comment | comment example deep link (scheme B) | low |
| frontend/android/app/src/main/AndroidManifest.xml:103 | clienthunter | B | `<data android:scheme="clienthunter" />` custom URL scheme; backend push payloads (app/services/notifications.py:130) and frontend/src/lib/deeplinks.ts emit/parse `clienthunter:///...` | HIGH: must change in lockstep with backend notifications + deeplinks.ts + tests; old links in sent pushes/emails break |
| frontend/android/app/src/main/AndroidManifest.xml:107 | clienthunter | A-comment | comment naming App Links host app.clienthunter.com (B) | low |
| frontend/android/app/src/main/AndroidManifest.xml:109 | clienthunter | A-comment | comment naming App Links host (B) | low |
| frontend/android/app/src/main/AndroidManifest.xml:112 | clienthunter | A-comment | comment naming assetlinks URL (B) | low |
| frontend/android/app/src/main/AndroidManifest.xml:115 | clienthunter | A-comment | comment naming keystore file `clienthunter-release.keystore` (B) | low |
| frontend/android/app/src/main/AndroidManifest.xml:120 | clienthunter | A-comment | comment naming App Links host (B) | low |
| frontend/android/app/src/main/AndroidManifest.xml:133 | clienthunter | B | `android:host="app.clienthunter.com"` App Links (autoVerify) host | HIGH/stale: production domain is calendarharvest.com per CLAUDE.md; app.clienthunter.com ownership unproven, so verification likely fails today regardless of rebrand |
| frontend/android/app/src/main/res/values/strings.xml:3 | ClientHunter | A | `app_name` = launcher label (Manifest `android:label="@string/app_name"`) | med: user-visible; disagrees with capacitor.config.ts appName 'Vectorae' (cap sync does not rewrite strings.xml) |
| frontend/android/app/src/main/res/values/strings.xml:4 | ClientHunter | A | `title_activity_main` (activity label) | low-med: user-visible in recents/task switcher |
| frontend/android/app/src/main/res/values/strings.xml:5 | clienthunter | B | `package_name` string = com.clienthunter.app (mirrors applicationId) | med: must equal applicationId |
| frontend/android/app/src/main/res/values/strings.xml:6 | clienthunter | B | `custom_url_scheme` = com.clienthunter.app (Capacitor-generated scheme string) | med |
| frontend/android/app/src/main/res/xml/file_paths.xml:3 | ClientHunter | A-comment | file header comment | low |
| frontend/android/app/src/main/res/xml/network_security_config.xml:3 | ClientHunter | A-comment | file header comment | low |
| frontend/android/app/src/main/res/xml/network_security_config.xml:10 | clienthunter | A-comment | comment naming `https://api.clienthunter.app` (stale domain, not referenced in config) | low |
| frontend/android/local.properties.example:33 | clienthunter | B | example `KEYSTORE_PATH=...clienthunter-release.keystore` (keystore filename) | low: example only; real keystore filename is whatever founder created |
| frontend/android/local.properties.example:35 | clienthunter | B | example `KEY_ALIAS=clienthunter` (signing key alias) | HIGH if copied: alias must match the existing upload keystore; never rename an existing key alias |
| frontend/capacitor.config.ts:8 | clienthunter | B | Capacitor `appId: 'com.clienthunter.app'` (comment line 4: "CANNOT be changed after the first Play Store publish") | HIGH: same identity as applicationId |
| frontend/capacitor.config.ts:9 | Vectorae | A | Capacitor `appName: 'Vectorae'` (only applied on `cap add`; not synced into strings.xml) | low-med: the one place already on Vectorae; Android launcher still shows ClientHunter |
| native/README.md:3 | vectorae | A | README names Rust module `vectorae_native_rs` (B) | low; update only with module |
| native/README.md:6 | vectorae | A | README names C++ module `vectorae_native_cpp` (B) | low |
| native/README.md:9 | vectorae | A | README links docs/features/vectorae-agents.md (file name) | low |
| native/cpp/CMakeLists.txt:2 | vectorae | B | CMake `project(vectorae_native_cpp)` | med: build target name |
| native/cpp/CMakeLists.txt:8 | vectorae | B | static lib target `vectorae_core` | low (internal) |
| native/cpp/CMakeLists.txt:9 | vectorae | B | target `vectorae_core` | low (internal) |
| native/cpp/CMakeLists.txt:11 | vectorae | B | target `vectorae_core` | low (internal) |
| native/cpp/CMakeLists.txt:18 | vectorae | B | `pybind11_add_module(vectorae_native_cpp ...)` = Python import name | HIGH: imported by app/agents/native.py, tests/test_agents_native_parity.py, .github/workflows/verify.yml:230 |
| native/cpp/CMakeLists.txt:19 | vectorae | B | link `vectorae_native_cpp` -> `vectorae_core` | med |
| native/cpp/CMakeLists.txt:20 | vectorae | B | install target `vectorae_native_cpp` | med |
| native/cpp/CMakeLists.txt:25 | vectorae | B | test_core links `vectorae_core` | low |
| native/cpp/include/vectorae/agents.hpp:1 | Vectorae | A-comment | header comment "Vectorae agents, C++ core" | low |
| native/cpp/include/vectorae/agents.hpp:3 | vectorae | A-comment | comment naming module `vectorae_native_cpp` | low |
| native/cpp/include/vectorae/agents.hpp:10 | vectorae | B | C++ `namespace vectorae {` (internal; renamable in one commit, no ABI consumer outside repo) | low |
| native/cpp/include/vectorae/agents.hpp:80 | vectorae | B | namespace close comment | low |
| native/cpp/include/vectorae/text.hpp:13 | vectorae | B | C++ namespace | low |
| native/cpp/include/vectorae/text.hpp:69 | vectorae | B | namespace close comment | low |
| native/cpp/pyproject.toml:6 | vectorae | B | Python dist name `vectorae-native-cpp` (not on PyPI; built in-repo) | med |
| native/cpp/pyproject.toml:8 | Vectorae | A | package description | low |
| native/cpp/src/bindings.cpp:1 | vectorae | A-comment | comment naming module | low |
| native/cpp/src/bindings.cpp:7 | vectorae | B | `#include "vectorae/agents.hpp"` (include dir name) | low (internal) |
| native/cpp/src/bindings.cpp:10 | vectorae | B | `using namespace vectorae;` | low |
| native/cpp/src/bindings.cpp:12 | vectorae | B | `PYBIND11_MODULE(vectorae_native_cpp, m)` = Python import name | HIGH: must match CMake target + all importers |
| native/cpp/src/bindings.cpp:13 | Vectorae | A | module docstring `m.doc()` (visible via help()) | low |
| native/cpp/src/claims.cpp:8 | vectorae | B | include path | low |
| native/cpp/src/claims.cpp:9 | vectorae | B | include path | low |
| native/cpp/src/claims.cpp:11 | vectorae | B | namespace | low |
| native/cpp/src/claims.cpp:100 | vectorae | B | namespace close comment | low |
| native/cpp/src/deliverability.cpp:10 | vectorae | B | include path | low |
| native/cpp/src/deliverability.cpp:12 | vectorae | B | namespace | low |
| native/cpp/src/deliverability.cpp:80 | vectorae | B | namespace close comment | low |
| native/cpp/src/triage.cpp:11 | vectorae | B | include path | low |
| native/cpp/src/triage.cpp:12 | vectorae | B | include path | low |
| native/cpp/src/triage.cpp:14 | vectorae | B | namespace | low |
| native/cpp/src/triage.cpp:100 | vectorae | B | namespace close comment | low |
| native/cpp/tests/test_core.cpp:7 | vectorae | B (test) | include path | low |
| native/cpp/tests/test_core.cpp:8 | vectorae | B (test) | include path | low |
| native/cpp/tests/test_core.cpp:10 | vectorae | B (test) | using namespace | low |
| native/cpp/tests/test_core.cpp:67 | vectorae | A (test) | test stdout "vectorae_native_cpp core: all tests passed" | low |
| native/rust/Cargo.lock:169 | vectorae | B | lockfile package name (generated from Cargo.toml; regenerate with `cargo generate-lockfile`/any cargo build) | low |
| native/rust/Cargo.toml:2 | vectorae | B | crate `[package] name = "vectorae_native_rs"` | med |
| native/rust/Cargo.toml:5 | Vectorae | A | crate description | low |
| native/rust/Cargo.toml:9 | vectorae | B | `[lib] name = "vectorae_native_rs"` (cdylib file name) | HIGH: must match PyO3 #[pymodule] fn name + maturin module-name |
| native/rust/pyproject.toml:6 | vectorae | B | Python dist name `vectorae-native-rs` (not on PyPI) | med |
| native/rust/pyproject.toml:8 | Vectorae | A | package description | low |
| native/rust/pyproject.toml:13 | vectorae | B | maturin `module-name = "vectorae_native_rs"` = Python import name | HIGH: imported by app/agents/native.py, verify.yml:230, parity tests |
| native/rust/src/lib.rs:1 | Vectorae | A-comment | crate doc comment | low |
| native/rust/src/lib.rs:2 | vectorae | A-comment | crate doc comment naming module | low |
| native/rust/src/lib.rs:70 | vectorae | B | `fn vectorae_native_rs` #[pymodule] = Python import name (PyInit_ symbol) | HIGH: must match lib name/module-name |
| sdk/backend_additions/strategies_list.py:7 | clienthunter | A-comment | docstring/comment | low |
| sdk/backend_additions/strategies_list.py:44 | clienthunter | A-comment | docstring/comment | low |
| sdk/pyproject.toml:6 | clienthunter | B | PyPI distribution name — `name = "clienthunter"` | HIGH: `pip install clienthunter` name; name is UNCLAIMED on PyPI today (pypi.org/pypi/clienthunter/json -> 404, 2026-10-20), so renaming before first publish is free |
| sdk/pyproject.toml:8 | ClientHunter | A | PyPI summary (shown on pypi.org) | low-med: user-visible CLI text |
| sdk/pyproject.toml:12 | ClientHunter/clienthunter | C | PyPI author/contact: name + hello@clienthunter.ai mailbox | needs human: author name + mailbox hello@clienthunter.ai shown on PyPI |
| sdk/pyproject.toml:38 | clienthunter | A-comment | toml comment | low |
| sdk/pyproject.toml:42 | clienthunter | A-comment | toml comment | low |
| sdk/pyproject.toml:43 | clienthunter | A-comment | toml comment | low |
| sdk/pyproject.toml:56 | clienthunter | B | console_scripts entry point (CLI command name + module path) — `clienthunter = "clienthunter.cli:app"` | HIGH: CLI command users type; rename breaks scripts/docs |
| sdk/pyproject.toml:59 | clienthunter | B | project URL (domain / GitHub org) — `Homepage = "https://clienthunter.ai"` | med: clienthunter.ai / github.com/clienthunter org - ownership unverified; real repo is not this |
| sdk/pyproject.toml:60 | clienthunter | B | project URL (domain / GitHub org) — `Documentation = "https://docs.clienthunter.ai"` | med: clienthunter.ai / github.com/clienthunter org - ownership unverified; real repo is not this |
| sdk/pyproject.toml:61 | clienthunter | B | project URL (domain / GitHub org) — `Repository = "https://github.com/clienthunter/clienthunter"` | med: clienthunter.ai / github.com/clienthunter org - ownership unverified; real repo is not this |
| sdk/pyproject.toml:62 | clienthunter | B | project URL (domain / GitHub org) — `"Bug Tracker" = "https://github.com/clienthunter/clienthunte` | med: clienthunter.ai / github.com/clienthunter org - ownership unverified; real repo is not this |
| sdk/pyproject.toml:63 | clienthunter | B | project URL (domain / GitHub org) — `Changelog = "https://github.com/clienthunter/clienthunter/bl` | med: clienthunter.ai / github.com/clienthunter org - ownership unverified; real repo is not this |
| sdk/pyproject.toml:70 | clienthunter | B | build config: import package path | med: must track package dir |
| sdk/pyproject.toml:78 | clienthunter | B | build config: import package path | med: must track package dir |
| sdk/src/clienthunter/__init__.py:1 | ClientHunter | A-comment | docstring/comment | low |
| sdk/src/clienthunter/__init__.py:5 | ClientHunter/clienthunter | A-comment | docstring usage example (quotes import/class B) | low |
| sdk/src/clienthunter/__init__.py:7 | ClientHunter/clienthunter | A-comment | docstring/comment | low |
| sdk/src/clienthunter/__init__.py:8 | clienthunter | A-comment | docstring/comment | low |
| sdk/src/clienthunter/__init__.py:20 | clienthunter | A-comment | docstring/comment | low |
| sdk/src/clienthunter/__init__.py:23 | clienthunter | B | Python import name / module path | HIGH: public import name `clienthunter` |
| sdk/src/clienthunter/__init__.py:24 | ClientHunter/clienthunter | B | Python import name / module path | HIGH: public import name `clienthunter` |
| sdk/src/clienthunter/__init__.py:25 | clienthunter | B | Python import name / module path | HIGH: public import name `clienthunter` |
| sdk/src/clienthunter/__init__.py:28 | ClientHunter | B | public exception class name (SDK API) — `ClientHunterError,` | HIGH: public API (users `except ClientHunterError` / `ClientHunter()`); rename needs alias |
| sdk/src/clienthunter/__init__.py:37 | ClientHunter | B | public class name ClientHunter (SDK API) — `"ClientHunter",` | HIGH: public API (users `except ClientHunterError` / `ClientHunter()`); rename needs alias |
| sdk/src/clienthunter/__init__.py:39 | ClientHunter | B | public exception class name (SDK API) — `"ClientHunterError",` | HIGH: public API (users `except ClientHunterError` / `ClientHunter()`); rename needs alias |
| sdk/src/clienthunter/_version.py:5 | clienthunter | A-comment | docstring quoting pyproject attr path | low |
| sdk/src/clienthunter/cli/__init__.py:1 | ClientHunter | A-comment | docstring/comment | low |
| sdk/src/clienthunter/cli/__init__.py:5 | clienthunter | A-comment | docstring/comment | low |
| sdk/src/clienthunter/cli/__init__.py:6 | clienthunter | A-comment | docstring/comment | low |
| sdk/src/clienthunter/cli/__init__.py:7 | clienthunter | A-comment | docstring/comment | low |
| sdk/src/clienthunter/cli/__init__.py:8 | clienthunter | A-comment | docstring/comment | low |
| sdk/src/clienthunter/cli/__init__.py:9 | clienthunter | A-comment | docstring/comment | low |
| sdk/src/clienthunter/cli/__init__.py:10 | clienthunter | A-comment | docstring/comment | low |
| sdk/src/clienthunter/cli/__init__.py:11 | clienthunter | A-comment | docstring/comment | low |
| sdk/src/clienthunter/cli/__init__.py:16 | clienthunter | A-comment | docstring/comment | low |
| sdk/src/clienthunter/cli/__init__.py:22 | clienthunter | B | Python import name / module path | HIGH: public import name `clienthunter` |
| sdk/src/clienthunter/cli/__init__.py:23 | clienthunter | B | Python import name / module path | HIGH: public import name `clienthunter` |
| sdk/src/clienthunter/cli/__init__.py:24 | clienthunter | B | Python import name / module path | HIGH: public import name `clienthunter` |
| sdk/src/clienthunter/cli/__init__.py:25 | clienthunter | B | Python import name / module path | HIGH: public import name `clienthunter` |
| sdk/src/clienthunter/cli/__init__.py:26 | clienthunter | B | Python import name / module path | HIGH: public import name `clienthunter` |
| sdk/src/clienthunter/cli/__init__.py:27 | clienthunter | B | Python import name / module path | HIGH: public import name `clienthunter` |
| sdk/src/clienthunter/cli/__init__.py:28 | clienthunter | B | Python import name / module path | HIGH: public import name `clienthunter` |
| sdk/src/clienthunter/cli/__init__.py:29 | clienthunter | B | Python import name / module path | HIGH: public import name `clienthunter` |
| sdk/src/clienthunter/cli/__init__.py:36 | clienthunter | B | Typer app/CLI program name — `name="clienthunter",` | low-med: program name shown in --help |
| sdk/src/clienthunter/cli/__init__.py:38 | ClientHunter | A | user-visible CLI output/help text | low-med: user-visible CLI text |
| sdk/src/clienthunter/cli/__init__.py:39 | clienthunter | A | user-visible CLI output/help text | low-med: user-visible CLI text |
| sdk/src/clienthunter/cli/__init__.py:40 | clienthunter | A | user-visible CLI output/help text | low-med: user-visible CLI text |
| sdk/src/clienthunter/cli/__init__.py:41 | clienthunter | A | user-visible CLI output/help text | low-med: user-visible CLI text |
| sdk/src/clienthunter/cli/__init__.py:76 | clienthunter | B | Python import name / module path | HIGH: public import name `clienthunter` |
| sdk/src/clienthunter/cli/__init__.py:79 | clienthunter | A | user-visible CLI output/help text | low-med: user-visible CLI text |
| sdk/src/clienthunter/cli/_campaign.py:1 | clienthunter | A-comment | docstring/comment | low |
| sdk/src/clienthunter/cli/_campaign.py:3 | clienthunter | A-comment | docstring/comment | low |
| sdk/src/clienthunter/cli/_campaign.py:4 | clienthunter | A-comment | docstring/comment | low |
| sdk/src/clienthunter/cli/_campaign.py:18 | clienthunter | B | Python import name / module path | HIGH: public import name `clienthunter` |
| sdk/src/clienthunter/cli/_campaign.py:19 | ClientHunter/clienthunter | B | Python import name / module path | HIGH: public import name `clienthunter` |
| sdk/src/clienthunter/cli/_campaign.py:42 | ClientHunter | B | public exception class name (SDK API) — `except ClientHunterError as exc:` | HIGH: public API (users `except ClientHunterError` / `ClientHunter()`); rename needs alias |
| sdk/src/clienthunter/cli/_campaign.py:46 | clienthunter | B | Python import name / module path | HIGH: public import name `clienthunter` |
| sdk/src/clienthunter/cli/_campaign.py:53 | clienthunter | A | user-visible CLI output/help text | low-med: user-visible CLI text |
| sdk/src/clienthunter/cli/_campaign.py:78 | ClientHunter | B | public exception class name (SDK API) — `except ClientHunterError as exc:` | HIGH: public API (users `except ClientHunterError` / `ClientHunter()`); rename needs alias |
| sdk/src/clienthunter/cli/_campaign.py:82 | clienthunter | B | Python import name / module path | HIGH: public import name `clienthunter` |
| sdk/src/clienthunter/cli/_console.py:4 | clienthunter | A-comment | docstring/comment | low |
| sdk/src/clienthunter/cli/_console.py:18 | clienthunter | B | Python import name / module path | HIGH: public import name `clienthunter` |
| sdk/src/clienthunter/cli/_console.py:21 | ClientHunter | B | public exception class name (SDK API) — `ClientHunterError,` | HIGH: public API (users `except ClientHunterError` / `ClientHunter()`); rename needs alias |
| sdk/src/clienthunter/cli/_console.py:54 | ClientHunter | A-comment | docstring/comment | low |
| sdk/src/clienthunter/cli/_console.py:55 | ClientHunter | A-comment | docstring/comment | low |
| sdk/src/clienthunter/cli/_console.py:58 | clienthunter | A-comment | docstring/comment | low |
| sdk/src/clienthunter/cli/_console.py:60 | ClientHunter/clienthunter | B | Python import name / module path | HIGH: public import name `clienthunter` |
| sdk/src/clienthunter/cli/_console.py:62 | ClientHunter | B | public class name ClientHunter (SDK API) — `return ClientHunter(**kwargs)` | HIGH: public API (users `except ClientHunterError` / `ClientHunter()`); rename needs alias |
| sdk/src/clienthunter/cli/_console.py:70 | ClientHunter | B | public exception class name (SDK API) — `def handle_error(exc: ClientHunterError \\| Exception, *, jso` | HIGH: public API (users `except ClientHunterError` / `ClientHunter()`); rename needs alias |
| sdk/src/clienthunter/cli/_console.py:75 | clienthunter | A-comment | docstring/comment | low |
| sdk/src/clienthunter/cli/_console.py:84 | ClientHunter | B | public exception class name (SDK API) — `elif isinstance(exc, ClientHunterError):` | HIGH: public API (users `except ClientHunterError` / `ClientHunter()`); rename needs alias |
| sdk/src/clienthunter/cli/_console.py:105 | clienthunter | A | user-visible CLI output/help text | low-med: user-visible CLI text |
| sdk/src/clienthunter/cli/_console.py:119 | clienthunter | A | user-visible CLI output/help text | low-med: user-visible CLI text |
| sdk/src/clienthunter/cli/_init.py:1 | clienthunter | A-comment | docstring/comment | low |
| sdk/src/clienthunter/cli/_init.py:4 | clienthunter | A-comment | docstring/comment | low |
| sdk/src/clienthunter/cli/_init.py:11 | clienthunter | B | Python import name / module path | HIGH: public import name `clienthunter` |
| sdk/src/clienthunter/cli/_init.py:12 | clienthunter | B | Python import name / module path | HIGH: public import name `clienthunter` |
| sdk/src/clienthunter/cli/_init.py:13 | ClientHunter/clienthunter | B | Python import name / module path | HIGH: public import name `clienthunter` |
| sdk/src/clienthunter/cli/_init.py:15 | clienthunter | B | default API URL domain api.clienthunter.ai — `_DEFAULT_CLOUD_URL = "https://api.clienthunter.ai"` | HIGH/stale: api.clienthunter.ai is not the production API (calendarharvest.com); default is wrong independent of rebrand |
| sdk/src/clienthunter/cli/_init.py:21 | ClientHunter | A | user-visible CLI output/help text | low-med: user-visible CLI text |
| sdk/src/clienthunter/cli/_init.py:26 | clienthunter | A | user-visible CLI output/help text | low-med: user-visible CLI text |
| sdk/src/clienthunter/cli/_init.py:38 | clienthunter | A | user-visible CLI output/help text | low-med: user-visible CLI text |
| sdk/src/clienthunter/cli/_init.py:39 | clienthunter | A | user-visible CLI output/help text | low-med: user-visible CLI text |
| sdk/src/clienthunter/cli/_init.py:71 | ClientHunter | B | public exception class name (SDK API) — `except ClientHunterError as exc:` | HIGH: public API (users `except ClientHunterError` / `ClientHunter()`); rename needs alias |
| sdk/src/clienthunter/cli/_init.py:89 | clienthunter | A | user-visible CLI output/help text | low-med: user-visible CLI text |
| sdk/src/clienthunter/cli/_init.py:92 | clienthunter | A | user-visible CLI output/help text | low-med: user-visible CLI text |
| sdk/src/clienthunter/cli/_init.py:93 | clienthunter | A | user-visible CLI output/help text | low-med: user-visible CLI text |
| sdk/src/clienthunter/cli/_init.py:94 | clienthunter | A | user-visible CLI output/help text | low-med: user-visible CLI text |
| sdk/src/clienthunter/cli/_leads.py:1 | clienthunter | A-comment | docstring/comment | low |
| sdk/src/clienthunter/cli/_leads.py:3 | clienthunter | A-comment | docstring/comment | low |
| sdk/src/clienthunter/cli/_leads.py:4 | clienthunter | A-comment | docstring/comment | low |
| sdk/src/clienthunter/cli/_leads.py:16 | clienthunter | B | Python import name / module path | HIGH: public import name `clienthunter` |
| sdk/src/clienthunter/cli/_leads.py:17 | ClientHunter/clienthunter | B | Python import name / module path | HIGH: public import name `clienthunter` |
| sdk/src/clienthunter/cli/_leads.py:52 | ClientHunter | B | public exception class name (SDK API) — `except ClientHunterError as exc:` | HIGH: public API (users `except ClientHunterError` / `ClientHunter()`); rename needs alias |
| sdk/src/clienthunter/cli/_leads.py:115 | ClientHunter | B | public exception class name (SDK API) — `except ClientHunterError as exc:` | HIGH: public API (users `except ClientHunterError` / `ClientHunter()`); rename needs alias |
| sdk/src/clienthunter/cli/_run.py:1 | clienthunter | A-comment | docstring/comment | low |
| sdk/src/clienthunter/cli/_run.py:35 | clienthunter | B | Python import name / module path | HIGH: public import name `clienthunter` |
| sdk/src/clienthunter/cli/_run.py:36 | ClientHunter/clienthunter | B | Python import name / module path | HIGH: public import name `clienthunter` |
| sdk/src/clienthunter/cli/_run.py:37 | clienthunter | B | Python import name / module path | HIGH: public import name `clienthunter` |
| sdk/src/clienthunter/cli/_run.py:128 | ClientHunter | A | user-visible CLI output/help text | low-med: user-visible CLI text |
| sdk/src/clienthunter/cli/_run.py:206 | ClientHunter | B | public exception class name (SDK API) — `except ClientHunterError as exc:` | HIGH: public API (users `except ClientHunterError` / `ClientHunter()`); rename needs alias |
| sdk/src/clienthunter/cli/_run.py:215 | ClientHunter | B | public exception class name (SDK API) — `except ClientHunterError as exc:` | HIGH: public API (users `except ClientHunterError` / `ClientHunter()`); rename needs alias |
| sdk/src/clienthunter/cli/_run.py:220 | ClientHunter | A | user-visible CLI output/help text | low-med: user-visible CLI text |
| sdk/src/clienthunter/cli/_run.py:235 | ClientHunter | B | public exception class name (SDK API) — `except ClientHunterError as exc:` | HIGH: public API (users `except ClientHunterError` / `ClientHunter()`); rename needs alias |
| sdk/src/clienthunter/cli/_run.py:265 | ClientHunter | B | public exception class name (SDK API) — `except ClientHunterError as exc:` | HIGH: public API (users `except ClientHunterError` / `ClientHunter()`); rename needs alias |
| sdk/src/clienthunter/cli/_run.py:272 | ClientHunter | B | public exception class name (SDK API) — `except ClientHunterError as exc:` | HIGH: public API (users `except ClientHunterError` / `ClientHunter()`); rename needs alias |
| sdk/src/clienthunter/cli/_run.py:284 | clienthunter | A | user-visible CLI output/help text | low-med: user-visible CLI text |
| sdk/src/clienthunter/cli/_run.py:285 | clienthunter | A | user-visible CLI output/help text | low-med: user-visible CLI text |
| sdk/src/clienthunter/cli/_run.py:296 | ClientHunter | B | public exception class name (SDK API) — `except ClientHunterError as exc:` | HIGH: public API (users `except ClientHunterError` / `ClientHunter()`); rename needs alias |
| sdk/src/clienthunter/cli/_run.py:314 | clienthunter | A | user-visible CLI output/help text | low-med: user-visible CLI text |
| sdk/src/clienthunter/cli/_serve.py:1 | clienthunter | A-comment | docstring/comment | low |
| sdk/src/clienthunter/cli/_serve.py:3 | clienthunter | A-comment | docstring/comment | low |
| sdk/src/clienthunter/cli/_serve.py:4 | clienthunter | A-comment | docstring/comment | low |
| sdk/src/clienthunter/cli/_serve.py:5 | clienthunter | A-comment | docstring/comment | low |
| sdk/src/clienthunter/cli/_serve.py:9 | clienthunter | A-comment | docstring/comment | low |
| sdk/src/clienthunter/cli/_serve.py:20 | clienthunter | A-comment | docstring/comment | low |
| sdk/src/clienthunter/cli/_serve.py:39 | clienthunter | B | Python import name / module path | HIGH: public import name `clienthunter` |
| sdk/src/clienthunter/cli/_serve.py:40 | clienthunter | B | Python import name / module path | HIGH: public import name `clienthunter` |
| sdk/src/clienthunter/cli/_serve.py:62 | ClientHunter | A-comment | code comment | low |
| sdk/src/clienthunter/cli/_serve.py:63 | clienthunter | A-comment | code comment | low |
| sdk/src/clienthunter/cli/_serve.py:65 | clienthunter | A-comment | code comment | low |
| sdk/src/clienthunter/cli/_serve.py:115 | clienthunter | B | self-host DB name in generated compose/.env — `POSTGRES_DB: clienthunter` | med: renaming changes DB name for existing self-host volumes |
| sdk/src/clienthunter/cli/_serve.py:120 | clienthunter | B | self-host DB name in generated compose/.env — `test: ["CMD-SHELL", "pg_isready -U ch -d clienthunter"]` | med: renaming changes DB name for existing self-host volumes |
| sdk/src/clienthunter/cli/_serve.py:143 | ClientHunter/clienthunter | A-comment | code comment | low |
| sdk/src/clienthunter/cli/_serve.py:146 | clienthunter | B | self-host DB name in generated compose/.env — `DATABASE_URL=postgresql://ch:{POSTGRES_PASSWORD}@db:5432/cli` | med: renaming changes DB name for existing self-host volumes |
| sdk/src/clienthunter/cli/_serve.py:222 | clienthunter | A-comment | docstring/comment | low |
| sdk/src/clienthunter/cli/_serve.py:315 | ClientHunter | A-comment | docstring/comment | low |
| sdk/src/clienthunter/cli/_serve.py:320 | clienthunter | A-comment | docstring/comment | low |
| sdk/src/clienthunter/cli/_serve.py:325 | ClientHunter | A | user-visible CLI output/help text | low-med: user-visible CLI text |
| sdk/src/clienthunter/cli/_serve.py:337 | clienthunter | A | user-visible CLI output/help text | low-med: user-visible CLI text |
| sdk/src/clienthunter/cli/_serve.py:391 | clienthunter | A | user-visible CLI output/help text | low-med: user-visible CLI text |
| sdk/src/clienthunter/cli/_serve.py:398 | ClientHunter | A-comment | docstring/comment | low |
| sdk/src/clienthunter/cli/_serve.py:401 | clienthunter | A | user-visible CLI output/help text | low-med: user-visible CLI text |
| sdk/src/clienthunter/cli/_serve.py:437 | clienthunter | A | user-visible CLI output/help text | low-med: user-visible CLI text |
| sdk/src/clienthunter/cli/_serve.py:438 | clienthunter | A | user-visible CLI output/help text | low-med: user-visible CLI text |
| sdk/src/clienthunter/cli/_serve.py:442 | clienthunter | A | user-visible CLI output/help text | low-med: user-visible CLI text |
| sdk/src/clienthunter/cli/_status.py:1 | clienthunter | A-comment | docstring/comment | low |
| sdk/src/clienthunter/cli/_status.py:3 | clienthunter | A-comment | docstring/comment | low |
| sdk/src/clienthunter/cli/_status.py:4 | clienthunter | A-comment | docstring/comment | low |
| sdk/src/clienthunter/cli/_status.py:5 | clienthunter | A-comment | docstring/comment | low |
| sdk/src/clienthunter/cli/_status.py:6 | clienthunter | A-comment | docstring/comment | low |
| sdk/src/clienthunter/cli/_status.py:24 | clienthunter | B | Python import name / module path | HIGH: public import name `clienthunter` |
| sdk/src/clienthunter/cli/_status.py:25 | ClientHunter/clienthunter | B | Python import name / module path | HIGH: public import name `clienthunter` |
| sdk/src/clienthunter/cli/_status.py:26 | clienthunter | B | Python import name / module path | HIGH: public import name `clienthunter` |
| sdk/src/clienthunter/cli/_status.py:196 | clienthunter | A | user-visible CLI output/help text | low-med: user-visible CLI text |
| sdk/src/clienthunter/cli/_status.py:207 | ClientHunter | B | public exception class name (SDK API) — `except ClientHunterError as exc:` | HIGH: public API (users `except ClientHunterError` / `ClientHunter()`); rename needs alias |
| sdk/src/clienthunter/cli/_status.py:217 | ClientHunter | B | public exception class name (SDK API) — `except ClientHunterError as exc:` | HIGH: public API (users `except ClientHunterError` / `ClientHunter()`); rename needs alias |
| sdk/src/clienthunter/cli/_status.py:225 | clienthunter | A | user-visible CLI output/help text | low-med: user-visible CLI text |
| sdk/src/clienthunter/cli/_status.py:236 | ClientHunter | B | public exception class name (SDK API) — `except ClientHunterError:` | HIGH: public API (users `except ClientHunterError` / `ClientHunter()`); rename needs alias |
| sdk/src/clienthunter/cli/_status.py:246 | ClientHunter | B | public exception class name (SDK API) — `except ClientHunterError as exc:` | HIGH: public API (users `except ClientHunterError` / `ClientHunter()`); rename needs alias |
| sdk/src/clienthunter/cli/_status.py:256 | ClientHunter | B | public exception class name (SDK API) — `except ClientHunterError as exc:` | HIGH: public API (users `except ClientHunterError` / `ClientHunter()`); rename needs alias |
| sdk/src/clienthunter/cli/serve.py:2 | ClientHunter/clienthunter | A-comment | docstring/comment | low |
| sdk/src/clienthunter/cli/serve.py:140 | ClientHunter | A-comment | docstring/comment | low |
| sdk/src/clienthunter/cli/serve.py:143 | clienthunter | A-comment | docstring/comment | low |
| sdk/src/clienthunter/cli/serve.py:151 | clienthunter | A | user-visible CLI output/help text | low-med: user-visible CLI text |
| sdk/src/clienthunter/cli/serve.py:160 | clienthunter | A | user-visible CLI output/help text | low-med: user-visible CLI text |
| sdk/src/clienthunter/client.py:1 | ClientHunter | A-comment | docstring/comment | low |
| sdk/src/clienthunter/client.py:4 | ClientHunter | A-comment | docstring/comment | low |
| sdk/src/clienthunter/client.py:9 | ClientHunter | A-comment | docstring/comment | low |
| sdk/src/clienthunter/client.py:44 | clienthunter | B | Python import name / module path | HIGH: public import name `clienthunter` |
| sdk/src/clienthunter/client.py:45 | clienthunter | B | Python import name / module path | HIGH: public import name `clienthunter` |
| sdk/src/clienthunter/client.py:46 | clienthunter | B | Python import name / module path | HIGH: public import name `clienthunter` |
| sdk/src/clienthunter/client.py:49 | ClientHunter | B | public exception class name (SDK API) — `ClientHunterError,` | HIGH: public API (users `except ClientHunterError` / `ClientHunter()`); rename needs alias |
| sdk/src/clienthunter/client.py:55 | clienthunter | B | Python import name / module path | HIGH: public import name `clienthunter` |
| sdk/src/clienthunter/client.py:155 | ClientHunter | B | public class name ClientHunter (SDK API) — `def __init__(self, client: "ClientHunter") -> None:` | HIGH: public API (users `except ClientHunterError` / `ClientHunter()`); rename needs alias |
| sdk/src/clienthunter/client.py:233 | ClientHunter | B | public class name ClientHunter (SDK API) — `def __init__(self, client: "ClientHunter") -> None:` | HIGH: public API (users `except ClientHunterError` / `ClientHunter()`); rename needs alias |
| sdk/src/clienthunter/client.py:316 | ClientHunter | B | public class name ClientHunter (SDK API) — `def __init__(self, client: "ClientHunter") -> None:` | HIGH: public API (users `except ClientHunterError` / `ClientHunter()`); rename needs alias |
| sdk/src/clienthunter/client.py:374 | clienthunter | A-comment | docstring/comment | low |
| sdk/src/clienthunter/client.py:405 | ClientHunter | B | public class name ClientHunter (SDK API) — `def __init__(self, client: "ClientHunter") -> None:` | HIGH: public API (users `except ClientHunterError` / `ClientHunter()`); rename needs alias |
| sdk/src/clienthunter/client.py:488 | ClientHunter | B | public class name ClientHunter (SDK API) — `def __init__(self, client: "ClientHunter") -> None:` | HIGH: public API (users `except ClientHunterError` / `ClientHunter()`); rename needs alias |
| sdk/src/clienthunter/client.py:564 | ClientHunter | B | public class name ClientHunter (SDK API) — `def __init__(self, client: "ClientHunter") -> None:` | HIGH: public API (users `except ClientHunterError` / `ClientHunter()`); rename needs alias |
| sdk/src/clienthunter/client.py:644 | ClientHunter | B | public class name ClientHunter (SDK API) — `def __init__(self, client: "ClientHunter") -> None:` | HIGH: public API (users `except ClientHunterError` / `ClientHunter()`); rename needs alias |
| sdk/src/clienthunter/client.py:664 | ClientHunter | A-comment | docstring/comment | low |
| sdk/src/clienthunter/client.py:684 | ClientHunter | B | public class name ClientHunter (SDK API) — `class ClientHunter:` | HIGH: public API (users `except ClientHunterError` / `ClientHunter()`); rename needs alias |
| sdk/src/clienthunter/client.py:685 | ClientHunter | A-comment | docstring/comment | low |
| sdk/src/clienthunter/client.py:689 | ClientHunter | A-comment | docstring/comment | low |
| sdk/src/clienthunter/client.py:695 | ClientHunter | A-comment | docstring/comment | low |
| sdk/src/clienthunter/client.py:699 | CLIENTHUNTER | A-comment | code comment | low |
| sdk/src/clienthunter/client.py:700 | ClientHunter | A-comment | docstring/comment | low |
| sdk/src/clienthunter/client.py:702 | ClientHunter | A-comment | docstring/comment | low |
| sdk/src/clienthunter/client.py:720 | CLIENTHUNTER | A-comment | docstring/comment | low |
| sdk/src/clienthunter/client.py:722 | CLIENTHUNTER | A-comment | docstring/comment | low |
| sdk/src/clienthunter/client.py:757 | ClientHunter | B | public class name ClientHunter (SDK API) — `def __enter__(self) -> "ClientHunter":` | HIGH: public API (users `except ClientHunterError` / `ClientHunter()`); rename needs alias |
| sdk/src/clienthunter/client.py:826 | ClientHunter | B | public exception class name (SDK API) — `last_exc: ClientHunterError \\| None = None` | HIGH: public API (users `except ClientHunterError` / `ClientHunter()`); rename needs alias |
| sdk/src/clienthunter/client.py:879 | ClientHunter | B | public exception class name (SDK API) — `except ClientHunterError:` | HIGH: public API (users `except ClientHunterError` / `ClientHunter()`); rename needs alias |
| sdk/src/clienthunter/client.py:944 | clienthunter | A-comment | docstring/comment | low |
| sdk/src/clienthunter/config.py:1 | ClientHunter | A-comment | docstring/comment | low |
| sdk/src/clienthunter/config.py:4 | CLIENTHUNTER | A-comment | docstring/comment | low |
| sdk/src/clienthunter/config.py:5 | clienthunter | A-comment | docstring/comment | low |
| sdk/src/clienthunter/config.py:8 | clienthunter | A-comment | docstring/comment | low |
| sdk/src/clienthunter/config.py:9 | clienthunter | A-comment | docstring/comment | low |
| sdk/src/clienthunter/config.py:33 | clienthunter | B | default API URL domain api.clienthunter.ai — `_DEFAULT_API_URL = "https://api.clienthunter.ai"  # TODO: re` | HIGH/stale: api.clienthunter.ai is not the production API (calendarharvest.com); default is wrong independent of rebrand |
| sdk/src/clienthunter/config.py:34 | clienthunter | B | config dir ~/.clienthunter (on-disk path in users' homes) — `_CONFIG_DIR = Path.home() / ".clienthunter"` | HIGH (non-test): existing users' tokens live in ~/.clienthunter; rename needs migration/fallback |
| sdk/src/clienthunter/config.py:69 | ClientHunter | A-comment | docstring/comment | low |
| sdk/src/clienthunter/config.py:110 | ClientHunter | A-comment | docstring/comment | low |
| sdk/src/clienthunter/config.py:145 | CLIENTHUNTER | B | env var name — `env_url = os.environ.get("CLIENTHUNTER_API_URL")` | HIGH: users' shells/CI set CLIENTHUNTER_API_URL/KEY; rename needs fallback alias |
| sdk/src/clienthunter/config.py:149 | CLIENTHUNTER | B | env var name — `env_key = os.environ.get("CLIENTHUNTER_API_KEY")` | HIGH: users' shells/CI set CLIENTHUNTER_API_URL/KEY; rename needs fallback alias |
| sdk/src/clienthunter/config.py:170 | clienthunter | A-comment | docstring/comment | low |
| sdk/src/clienthunter/config.py:189 | CLIENTHUNTER | B | env var name — `env_key = os.environ.get("CLIENTHUNTER_API_KEY")` | HIGH: users' shells/CI set CLIENTHUNTER_API_URL/KEY; rename needs fallback alias |
| sdk/src/clienthunter/config.py:226 | clienthunter | A | user-visible CLI output/help text | low-med: user-visible CLI text |
| sdk/src/clienthunter/exceptions.py:1 | ClientHunter | A-comment | docstring/comment | low |
| sdk/src/clienthunter/exceptions.py:21 | ClientHunter | B | public exception class name (SDK API) — `class ClientHunterError(Exception):` | HIGH: public API (users `except ClientHunterError` / `ClientHunter()`); rename needs alias |
| sdk/src/clienthunter/exceptions.py:25 | ClientHunter | B | public exception class name (SDK API) — `class AuthError(ClientHunterError):` | HIGH: public API (users `except ClientHunterError` / `ClientHunter()`); rename needs alias |
| sdk/src/clienthunter/exceptions.py:39 | ClientHunter | B | public exception class name (SDK API) — `class NotFoundError(ClientHunterError):` | HIGH: public API (users `except ClientHunterError` / `ClientHunter()`); rename needs alias |
| sdk/src/clienthunter/exceptions.py:48 | ClientHunter | B | public exception class name (SDK API) — `class ValidationError(ClientHunterError):` | HIGH: public API (users `except ClientHunterError` / `ClientHunter()`); rename needs alias |
| sdk/src/clienthunter/exceptions.py:67 | ClientHunter | B | public exception class name (SDK API) — `class ComplianceError(ClientHunterError):` | HIGH: public API (users `except ClientHunterError` / `ClientHunter()`); rename needs alias |
| sdk/src/clienthunter/exceptions.py:90 | clienthunter | A | user-visible CLI output/help text | low-med: user-visible CLI text |
| sdk/src/clienthunter/exceptions.py:117 | ClientHunter | B | public exception class name (SDK API) — `class RateLimitError(ClientHunterError):` | HIGH: public API (users `except ClientHunterError` / `ClientHunter()`); rename needs alias |
| sdk/src/clienthunter/exceptions.py:134 | ClientHunter | B | public exception class name (SDK API) — `class APIError(ClientHunterError):` | HIGH: public API (users `except ClientHunterError` / `ClientHunter()`); rename needs alias |
| sdk/src/clienthunter/models.py:1 | ClientHunter | A-comment | docstring/comment | low |
| sdk/tests/conftest.py:1 | ClientHunter | A-comment | docstring/comment | low |
| sdk/tests/conftest.py:11 | ClientHunter/clienthunter | B (test) | Python import name / module path | low: test follows import name |
| sdk/tests/conftest.py:12 | clienthunter | B (test) | Python import name / module path | low: test follows import name |
| sdk/tests/conftest.py:136 | ClientHunter | B (test) | public class name ClientHunter (SDK API) — `def ch(client_config: Config) -> ClientHunter:` | low: test follows class name |
| sdk/tests/conftest.py:137 | ClientHunter | A-comment | docstring/comment | low |
| sdk/tests/conftest.py:138 | ClientHunter | B (test) | public class name ClientHunter (SDK API) — `return ClientHunter(_config=client_config)` | low: test follows class name |
| sdk/tests/conftest.py:148 | ClientHunter | A-comment | docstring/comment | low |
| sdk/tests/conftest.py:152 | clienthunter | B (test) | Python import name / module path | low: test follows import name |
| sdk/tests/test_cli.py:22 | clienthunter | B (test) | Python import name / module path | low: test follows import name |
| sdk/tests/test_cli.py:23 | clienthunter | B (test) | Python import name / module path | low: test follows import name |
| sdk/tests/test_cli.py:24 | clienthunter | B (test) | Python import name / module path | low: test follows import name |
| sdk/tests/test_cli.py:44 | clienthunter | A-comment | docstring | low |
| sdk/tests/test_cli.py:49 | clienthunter | B (test) | Python import name / module path | low: test follows import name |
| sdk/tests/test_cli.py:50 | clienthunter | B (test) | Python import name / module path | low: test follows import name |
| sdk/tests/test_cli.py:51 | clienthunter | B (test) | Python import name / module path | low: test follows import name |
| sdk/tests/test_cli.py:52 | clienthunter | B (test) | Python import name / module path | low: test follows import name |
| sdk/tests/test_cli.py:53 | clienthunter | B (test) | Python import name / module path | low: test follows import name |
| sdk/tests/test_cli.py:88 | clienthunter | B (test) | config dir ~/.clienthunter (on-disk path in users' homes) — `config_dir = tmp_path / ".clienthunter"` | low: test mirror of config dir |
| sdk/tests/test_cli.py:92 | clienthunter | B (test) | Python import name / module path | low: test follows import name |
| sdk/tests/test_cli.py:93 | clienthunter | B (test) | Python import name / module path | low: test follows import name |
| sdk/tests/test_cli.py:165 | clienthunter | B (test) | Python import name / module path | low: test follows import name |
| sdk/tests/test_cli.py:321 | clienthunter | B (test) | Python import name / module path | low: test follows import name |
| sdk/tests/test_config.py:20 | clienthunter | B (test) | Python import name / module path | low: test follows import name |
| sdk/tests/test_config.py:32 | clienthunter | B (test) | config dir ~/.clienthunter (on-disk path in users' homes) — `config_dir = tmp_path / ".clienthunter"` | low: test mirror of config dir |
| sdk/tests/test_config.py:35 | clienthunter | B (test) | Python import name / module path | low: test follows import name |
| sdk/tests/test_config.py:36 | clienthunter | B (test) | Python import name / module path | low: test follows import name |
| sdk/tests/test_config.py:48 | clienthunter | B (test) | config dir ~/.clienthunter (on-disk path in users' homes) — `config_dir = tmp_path / ".clienthunter"` | low: test mirror of config dir |
| sdk/tests/test_config.py:51 | clienthunter | B (test) | Python import name / module path | low: test follows import name |
| sdk/tests/test_config.py:52 | clienthunter | B (test) | Python import name / module path | low: test follows import name |
| sdk/tests/test_config.py:68 | clienthunter | B (test) | config dir ~/.clienthunter (on-disk path in users' homes) — `config_dir = tmp_path / ".clienthunter"` | low: test mirror of config dir |
| sdk/tests/test_config.py:71 | clienthunter | B (test) | Python import name / module path | low: test follows import name |
| sdk/tests/test_config.py:72 | clienthunter | B (test) | Python import name / module path | low: test follows import name |
| sdk/tests/test_config.py:88 | clienthunter | B (test) | config dir ~/.clienthunter (on-disk path in users' homes) — `config_dir = tmp_path / ".clienthunter"` | low: test mirror of config dir |
| sdk/tests/test_config.py:91 | clienthunter | B (test) | Python import name / module path | low: test follows import name |
| sdk/tests/test_config.py:92 | clienthunter | B (test) | Python import name / module path | low: test follows import name |
| sdk/tests/test_config.py:96 | CLIENTHUNTER | B (test) | env var name CLIENTHUNTER_API_URL — `monkeypatch.setenv("CLIENTHUNTER_API_URL", "http://from-env:` | HIGH: users' shells/CI set CLIENTHUNTER_API_URL/KEY; rename needs fallback alias |
| sdk/tests/test_config.py:103 | clienthunter | B (test) | config dir ~/.clienthunter (on-disk path in users' homes) — `config_dir = tmp_path / ".clienthunter"` | low: test mirror of config dir |
| sdk/tests/test_config.py:106 | clienthunter | B (test) | Python import name / module path | low: test follows import name |
| sdk/tests/test_config.py:107 | clienthunter | B (test) | Python import name / module path | low: test follows import name |
| sdk/tests/test_config.py:112 | CLIENTHUNTER | B (test) | env var name CLIENTHUNTER_API_KEY — `monkeypatch.setenv("CLIENTHUNTER_API_KEY", "sk-override-key"` | HIGH: users' shells/CI set CLIENTHUNTER_API_URL/KEY; rename needs fallback alias |
| sdk/tests/test_config.py:125 | clienthunter | B (test) | Python import name / module path | low: test follows import name |
| sdk/tests/test_config.py:126 | clienthunter | B (test) | Python import name / module path | low: test follows import name |
| sdk/tests/test_config.py:129 | clienthunter | B (test) | asserts default API domain clienthunter.ai — `assert "clienthunter.ai" in loaded.api_url` | HIGH/stale: api.clienthunter.ai is not the production API (calendarharvest.com); default is wrong independent of rebrand |
| sdk/tests/test_config.py:162 | clienthunter | B (test) | config dir ~/.clienthunter (on-disk path in users' homes) — `config_dir = tmp_path / ".clienthunter"` | low: test mirror of config dir |
| sdk/tests/test_config.py:168 | clienthunter | B (test) | Python import name / module path | low: test follows import name |
| sdk/tests/test_config.py:169 | clienthunter | B (test) | Python import name / module path | low: test follows import name |
| sdk/tests/test_sdk.py:16 | ClientHunter/clienthunter | B (test) | Python import name / module path | low: test follows import name |
| sdk/tests/test_sdk.py:17 | clienthunter | B (test) | Python import name / module path | low: test follows import name |
| sdk/tests/test_sdk.py:18 | clienthunter | B (test) | Python import name / module path | low: test follows import name |
| sdk/tests/test_sdk.py:30 | ClientHunter | B (test) | public class name ClientHunter (SDK API) — `def _ch(access_token: str = "test_tok", refresh_token: str =` | low: test follows class name |
| sdk/tests/test_sdk.py:31 | ClientHunter | A-comment | docstring/comment | low |
| sdk/tests/test_sdk.py:33 | ClientHunter | B (test) | public class name ClientHunter (SDK API) — `return ClientHunter(_config=cfg, max_retries=2)` | low: test follows class name |
| sdk/tests/test_sdk.py:53 | ClientHunter | B (test) | public class name ClientHunter (SDK API) — `ch = ClientHunter(_config=cfg)` | low: test follows class name |
| sdk/tests/test_sdk.py:206 | clienthunter | B (test) | Python import name / module path | low: test follows import name |
| sdk/tests/test_sdk.py:207 | clienthunter | B (test) | Python import name / module path | low: test follows import name |
| sdk/tests/test_sdk.py:208 | clienthunter | B (test) | config dir ~/.clienthunter (on-disk path in users' homes) — `tmp_path / ".clienthunter" / "config.toml")` | low: test mirror of config dir |
| sdk/tests/test_sdk.py:235 | clienthunter | B (test) | Python import name / module path | low: test follows import name |
| sdk/tests/test_sdk.py:236 | clienthunter | B (test) | Python import name / module path | low: test follows import name |
| sdk/tests/test_sdk.py:237 | clienthunter | B (test) | config dir ~/.clienthunter (on-disk path in users' homes) — `tmp_path / ".clienthunter" / "config.toml")` | low: test mirror of config dir |
| sdk/tests/test_sdk.py:262 | clienthunter | B (test) | Python import name / module path | low: test follows import name |
| sdk/tests/test_sdk.py:263 | clienthunter | B (test) | Python import name / module path | low: test follows import name |
| sdk/tests/test_sdk.py:264 | clienthunter | B (test) | config dir ~/.clienthunter (on-disk path in users' homes) — `tmp_path / ".clienthunter" / "config.toml")` | low: test mirror of config dir |
| sdk/tests/test_sdk.py:284 | clienthunter | B (test) | Python import name / module path | low: test follows import name |
| sdk/tests/test_sdk.py:303 | clienthunter | B (test) | Python import name / module path | low: test follows import name |
| sdk/tests/test_sdk.py:314 | clienthunter | B (test) | Python import name / module path | low: test follows import name |
| sdk/tests/test_sdk.py:377 | clienthunter | B (test) | Python import name / module path | low: test follows import name |
| sdk/tests/test_serve_check_env.py:2 | clienthunter | A-comment | docstring/comment | low |
| sdk/tests/test_serve_check_env.py:9 | clienthunter | B (test) | Python import name / module path | low: test follows import name |
| sdk/tests/test_version.py:3 | clienthunter | A-comment | docstring/comment | low |
| sdk/tests/test_version.py:14 | clienthunter | B (test) | Python import name / module path | low: test follows import name |
| sdk/tests/test_version.py:15 | clienthunter | B (test) | Python import name / module path | low: test follows import name |
| sdk/tests/test_version.py:20 | clienthunter | B (test) | Python import name / module path | low: test follows import name |
| sdk/tests/test_version.py:23 | clienthunter | A (test) | assertion failure message | low-med: user-visible CLI text |
| sdk/tests/test_version.py:30 | clienthunter | B (test) | Python import name / module path | low: test follows import name |
| sdk/tests/test_version.py:31 | clienthunter | B (test) | Python import name / module path | low: test follows import name |
| sdk/README.md: L1,3,16,21,156,177 (6 occ) | ClientHunter/clienthunter | A | doc prose / product name | low-med: user docs |
| sdk/README.md: L6,62,72,132,135 (5 occ) | ClientHunter/clienthunter | A | doc: code sample quoting import name/class (B) | low: test follows import name |
| sdk/README.md: L7,8,19,47,120,121,122,123,147 (9 occ) | clienthunter | A | doc: quotes CLI command `clienthunter` (B) | low-med: user docs |
| sdk/README.md: L27,28,64 (3 occ) | ClientHunter/clienthunter/clienthunter | A | doc: quotes clienthunter.ai domain (B) | low-med: user docs |
| sdk/README.md: L35,155,168 (3 occ) | clienthunter | A | doc: quotes PyPI name / repo URL (B) | low-med: user docs |
| sdk/README.md:L50 | clienthunter | A | doc: quotes ~/.clienthunter config dir (B) | HIGH (non-test): existing users' tokens live in ~/.clienthunter; rename needs migration/fallback |
| sdk/README.md: L55,56 (2 occ) | CLIENTHUNTER/CLIENTHUNTER/clienthunter | A | doc: quotes env var CLIENTHUNTER_* (B) | HIGH: users' shells/CI set CLIENTHUNTER_API_URL/KEY; rename needs fallback alias |
| sdk/README.md: L74,137 (2 occ) | ClientHunter | A | doc: quotes public class ClientHunter/ClientHunterError (B) | low-med: user docs |
| sdk/RELEASING.md: L1,11 (2 occ) | clienthunter | A | doc prose / product name | low-med: user docs |
| sdk/RELEASING.md:L34 | clienthunter | A | doc: quotes CLI command `clienthunter` (B) | low-med: user docs |
| sdk/docs/cli.md: L1,26,67,87 (4 occ) | ClientHunter | A | doc prose / product name | low-med: user docs |
| sdk/docs/cli.md:L3 | clienthunter | A | doc: quotes PyPI name / repo URL (B) | low-med: user docs |
| sdk/docs/cli.md: L8,13,20,40,41,46,52,114,119,148,153,158,159,160,168,175,176,177,178,179,180,185,188,189,198,203,206,207,217,220,224,225,227 (33 occ) | clienthunter | A | doc: quotes CLI command `clienthunter` (B) | low-med: user docs |
| sdk/docs/cli.md: L16,37 (2 occ) | clienthunter | A | doc: quotes ~/.clienthunter config dir (B) | HIGH (non-test): existing users' tokens live in ~/.clienthunter; rename needs migration/fallback |
| sdk/docs/cli.md: L27,29,165 (3 occ) | clienthunter | A | doc: quotes clienthunter.ai domain (B) | low-med: user docs |
| sdk/docs/sdk.md:L1 | ClientHunter | A | doc prose / product name | low-med: user docs |
| sdk/docs/sdk.md:L4 | clienthunter | A | doc: quotes PyPI name / repo URL (B) | low-med: user docs |
| sdk/docs/sdk.md: L5,165 (2 occ) | ClientHunter/clienthunter/clienthunter | A | doc: code sample quoting import name/class (B) | low: test follows import name |
| sdk/docs/sdk.md: L10,13,150 (3 occ) | ClientHunter | A | doc: quotes public class ClientHunter/ClientHunterError (B) | low-med: user docs |
| sdk/docs/sdk.md: L14,15 (2 occ) | CLIENTHUNTER/CLIENTHUNTER/clienthunter | A | doc: quotes env var CLIENTHUNTER_* (B) | HIGH: users' shells/CI set CLIENTHUNTER_API_URL/KEY; rename needs fallback alias |
| sdk/docs/sdk.md: L23,30 (2 occ) | clienthunter | A | doc: quotes ~/.clienthunter config dir (B) | HIGH (non-test): existing users' tokens live in ~/.clienthunter; rename needs migration/fallback |
| sdk/docs/sdk.md: L151,173 (2 occ) | clienthunter | A | doc: quotes CLI command `clienthunter` (B) | low-med: user docs |

## 3. File and directory names containing a variant

| Path | Variant | Class | Notes |
|---|---|---|---|
| `sdk/src/clienthunter/` (dir, 15 files: `__init__.py`, `_version.py`, `client.py`, `config.py`, `exceptions.py`, `models.py`, `cli/{__init__,_campaign,_console,_init,_leads,_run,_serve,_status,serve}.py`) | clienthunter | B | Python import package. Its name is the public import path; `pyproject.toml:70,78` and every test import depend on it |
| `native/cpp/include/vectorae/` (dir: `agents.hpp`, `text.hpp`) | vectorae | B (internal) | C++ include dir, used only by `native/cpp/src/*.cpp` and `tests/test_core.cpp` |
| (none under `frontend/android/`) | — | — | No `java/com/clienthunter/app/` source dirs are committed |

Outside the area but tied to it: `docs/features/vectorae-agents.md` (linked from `native/README.md:9`).

## 4. Generated or git-ignored files (not inventoried line by line)

- `native/rust/Cargo.lock`: committed but generated. Line 169 follows `Cargo.toml`, and any `cargo build` or `cargo generate-lockfile` after a crate rename regenerates it.
- `frontend/android/local.properties`: git-ignored (`frontend/android/.gitignore:6`). Machine-local SDK path and signing values. The committed template is `local.properties.example` (inventoried).
- `frontend/android/app/src/main/assets/public/`: git-ignored, regenerated by `npm run mobile:build` → `npx cap sync` from the Next.js export. It carries whatever the web app says.
- `frontend/android/.gradle`, `/build`, `/app/build`, `app/release`, `*.keystore`, `*.jks`: git-ignored build or signing outputs. The **release keystore and its alias** (example alias `clienthunter`) are founder-held secrets. A key alias is never renamed.
- `google-services.json`: not in git and not on disk. It is downloaded from the Firebase console for package `com.clienthunter.app` (see docs/FIREBASE_SETUP_CHECKLIST.md).
- Capacitor-generated Android scaffolding (`capacitor.build.gradle`, `capacitor-cordova-android-plugins/`, `variables.gradle`, `settings.gradle`): referenced by `build.gradle` but not committed. `npx cap add android` or `npx cap sync android` regenerates it. `cap add` would also write `appName` (currently `Vectorae`) into a fresh strings.xml.
- SDK build output (`dist/`, `*.egg-info`): none committed. `python -m build` regenerates it from pyproject.

## 5. Surprises / things to flag

1. **Android launcher name disagrees with the Capacitor config.** `capacitor.config.ts` says `Vectorae`, but `strings.xml` (what Android actually shows) says `ClientHunter`. The PR #113 rebrand reached only the Capacitor config, so a Victorae rename must edit `strings.xml:3,4` directly.
2. **Three different "brand" domains in this area, none of them the live one.** The SDK uses `clienthunter.ai` / `api.clienthunter.ai` / `docs.clienthunter.ai` / `hello@clienthunter.ai`. Android uses `app.clienthunter.com` (App Links host and assetlinks) and `api.clienthunter.app` (comment). CLAUDE.md says the live production domain is `calendarharvest.com`. So the SDK's **default API URL is wrong regardless of the rebrand** (`config.py:33` even carries `# TODO: replace with production URL`), and Android App Links verification against `app.clienthunter.com` very likely fails today. Classed B; it needs a founder decision on which domain is real.
3. **SDK is ClientHunter-branded end to end and was never moved to Vectorae.** The public API names (`ClientHunter`, `ClientHunterError`, `CLIENTHUNTER_*`, `~/.clienthunter`) are B. **Nothing is published on PyPI** (404), so renaming them now costs only in-repo changes plus `.github/workflows/pypi-release.yml` (lines 101-142 hard-code `clienthunter`). If any user already has a git install, a compat shim (old import name, env var fallback, config-dir fallback) is advisable.
4. **Pre-launch state may make the "permanent" appId still changeable.** assetlinks has a placeholder fingerprint and `versionCode 1`. If the app was never uploaded to Play, `com.clienthunter.app` could still change. The founder must confirm in Play Console, which is a C-type check.
5. **pyproject `authors` and URLs point to a GitHub org `github.com/clienthunter/clienthunter` and the mailbox `hello@clienthunter.ai`.** They would appear on PyPI. Ownership of both is unverified (C).
6. **No customer-voice text in this area** (DEFECT = 0). The SDK `ComplianceError` message (`exceptions.py:90`) is shown to the operator, not sent to leads.
7. **The `native/` Python module names are pinned by CI** (`verify.yml:230` imports `vectorae_native_rs, vectorae_native_cpp`) and by `app/agents/native.py`. A rename must update both, the parity test and `docs/features/vectorae-agents.md` in one change.
8. `android-release.yml` (outside the area) names the artifact `clienthunter-prod-release-<sha>` and the example `KEY_ALIAS "clienthunter"`. The artifact name is A or low-risk B; the key alias must not change.

# Part 4 — Brand inventory — product docs area

_Source: subagent sweep, file `brand-docs-product.md`._

Scope: `docs/help-center/`, `docs/features/`, `docs/connectors/`, `docs/api/`, `docs/api-reference.md`, `docs/setup/`, `docs/backup/`, `docs/PRIVACY_POLICY.md`, `docs/PLAY_STORE_CHECKLIST.md`, `docs/STORE_ASSETS.md`, `docs/SIGNING.md`, `docs/FIREBASE_SETUP_CHECKLIST.md`, `docs/ICP.md`, `docs/DEPLOY.md`.
Repo HEAD `7872f9c`. Read-only sweep; git-tracked files only (109 tracked files in scope, **96 contain a hit**).
Command: `git grep -nIiE 'lead[ _.-]?pilot|client[ _.-]?hunter|vectorae|victorae|lpk_|calendarharvest' -- <paths>` → 785 matching lines; each match then split per occurrence and classified (classification script kept in the Phase 0 session scratchpad, not committed).
Excluded per brief: 31 `calendarharvest.com` occurrences used as a domain (URLs, From addresses, status page). Only the 2 standalone uses of "Calendarharvest" as an operator/entity name (privacy policy) are counted.

## 1. Summary

**868 occurrences** (per match, not per line) in 96 files.

| Class | Count | Meaning here |
|---|---|---|
| A | 650 | docs prose, titles, documented UI/email copy, example data |
| A-slug | 58 | help-center **headings** containing "Vectorae": display text, but the heading slug is a chunk id that is persisted (see §5.1). Counted separately; treat as A with a migration step |
| B | 131 | identifiers shown in docs (headers, scopes, `lpk_`, Celery task names, app id, keystore alias, slugs, file names, repo/plugin names) |
| C | 29 | privacy policy, Play Store / Firebase listing values, connector data-handling disclosures and directory submission |
| DEFECT | 0 | no customer-voice text in this area injects a product name |

| Variant | A | A-slug | B | C | Total |
|---|---|---|---|---|---|
| Vectorae | 641 | 58 | 7 | 12 | 718 |
| LeadPilot (all spellings found were `LeadPilot`/`leadpilot`; no `Lead Pilot`, `lead_pilot` prose) | 1 | 0 | 76 | 0 | 77 |
| ClientHunter (incl. `clienthunter`, `ClientHunter Enterprise`) | 8 | 0 | 40 | 15 | 63 |
| lpk_ | 0 | 0 | 8 | 0 | 8 |
| Calendarharvest (entity name) | 0 | 0 | 0 | 2 | 2 |
| Victorae | 0 | 0 | 0 | 0 | 0 |

Per-file line counts verified with `git grep -c` (e.g. `docs/connectors/README.md:35`, `docs/help-center/00-index.md:42`, `docs/ICP.md:18`); row counts are per occurrence so they can exceed line counts.

## 2. Occurrences

Rows are one per occurrence. Where one file has >15 homogeneous A "docs prose" hits of the same variant, they are collapsed into one row; every B, C and A-slug occurrence keeps its own row. Two rows with the same `path:line` = two occurrences on that line.

| path:line | variant | class | reason | risk |
|---|---|---|---|---|
| docs/DEPLOY.md:1 | ClientHunter | A | doc title | LOW |
| docs/DEPLOY.md:25 | ClientHunter | B | repo checkout directory name (example) | LOW |
| docs/DEPLOY.md:56 | ClientHunter | B | deploy URL example (Railway service name) | LOW |
| docs/DEPLOY.md:62 | ClientHunter | B | repo checkout directory name (example) | LOW |
| docs/DEPLOY.md:105 | ClientHunter | B | Android applicationId | HIGH |
| docs/DEPLOY.md:135 | ClientHunter | B | release keystore file name | MED |
| docs/DEPLOY.md:135 | ClientHunter | B | keystore key alias (baked into existing release keystore) | HIGH |
| docs/DEPLOY.md:139 | ClientHunter | B | release keystore file name | MED |
| docs/DEPLOY.md:152 | ClientHunter | B | keystore key alias (baked into existing release keystore) | HIGH |
| docs/DEPLOY.md:169 | ClientHunter | B | CI build artifact name | MED |
| docs/DEPLOY.md:197 | ClientHunter | B | URL/domain (stale; not the live domain) | MED |
| docs/FIREBASE_SETUP_CHECKLIST.md:1 | ClientHunter | A | doc title | LOW |
| docs/FIREBASE_SETUP_CHECKLIST.md:15 | ClientHunter | B | Firebase project name/id (project id immutable once created; existing project keeps it) | MED |
| docs/FIREBASE_SETUP_CHECKLIST.md:24 | ClientHunter | B | Android applicationId | HIGH |
| docs/FIREBASE_SETUP_CHECKLIST.md:26 | ClientHunter | C | Firebase console app nickname (third-party console) | MED |
| docs/FIREBASE_SETUP_CHECKLIST.md:54 | ClientHunter | B | service-account key file name | LOW |
| docs/FIREBASE_SETUP_CHECKLIST.md:58 | ClientHunter | B | service-account key file name | LOW |
| docs/ICP.md:1 | Vectorae | A | doc title | LOW |
| docs/ICP.md:L5-L317 (17 occurrences on 17 lines) | Vectorae | A | docs prose (homogeneous; collapsed) | LOW |
| docs/PLAY_STORE_CHECKLIST.md:1 | ClientHunter | A | doc title | LOW |
| docs/PLAY_STORE_CHECKLIST.md:12 | ClientHunter | B | URL/domain (stale; not the live domain) | MED |
| docs/PLAY_STORE_CHECKLIST.md:22 | ClientHunter | C | Play Console app name to enter | MED |
| docs/PLAY_STORE_CHECKLIST.md:35 | ClientHunter | C | Play Console app name (store listing) | MED |
| docs/PLAY_STORE_CHECKLIST.md:126 | ClientHunter | C | Play Console release notes (public) | MED |
| docs/PLAY_STORE_CHECKLIST.md:134 | ClientHunter | B | Android deep-link URL scheme | HIGH |
| docs/PLAY_STORE_CHECKLIST.md:159 | ClientHunter | A | docs prose | LOW |
| docs/PLAY_STORE_CHECKLIST.md:162 | ClientHunter | B | URL/domain (stale; not the live domain) | MED |
| docs/PLAY_STORE_CHECKLIST.md:165 | ClientHunter | B | URL/domain (stale; not the live domain) | MED |
| docs/PLAY_STORE_CHECKLIST.md:165 | ClientHunter | B | Android applicationId | HIGH |
| docs/PRIVACY_POLICY.md:1 | ClientHunter | C | privacy policy (legal text) | HIGH |
| docs/PRIVACY_POLICY.md:1 | Vectorae | C | privacy policy (legal text) | HIGH |
| docs/PRIVACY_POLICY.md:13 | ClientHunter | C | privacy policy (legal text) | HIGH |
| docs/PRIVACY_POLICY.md:13 | Vectorae | C | privacy policy (legal text) | HIGH |
| docs/PRIVACY_POLICY.md:15 | Calendarharvest | C | privacy policy (legal text) - operator/legal entity name | HIGH |
| docs/PRIVACY_POLICY.md:23 | ClientHunter | C | privacy policy (legal text) | HIGH |
| docs/PRIVACY_POLICY.md:58 | ClientHunter | C | privacy policy (legal text) | HIGH |
| docs/PRIVACY_POLICY.md:139 | Vectorae | C | privacy policy (legal text) | HIGH |
| docs/PRIVACY_POLICY.md:144 | Vectorae | C | privacy policy (legal text) | HIGH |
| docs/PRIVACY_POLICY.md:155 | Vectorae | C | privacy policy (legal text) | HIGH |
| docs/PRIVACY_POLICY.md:155 | Vectorae | C | privacy policy (legal text) | HIGH |
| docs/PRIVACY_POLICY.md:171 | ClientHunter | C | privacy policy (legal text) | HIGH |
| docs/PRIVACY_POLICY.md:185 | Calendarharvest | C | privacy policy (legal text) - operator/legal entity name | HIGH |
| docs/SIGNING.md:1 | ClientHunter | A | doc title | LOW |
| docs/SIGNING.md:21 | ClientHunter | B | release keystore file name | MED |
| docs/SIGNING.md:22 | ClientHunter | B | keystore key alias (baked into existing release keystore) | HIGH |
| docs/SIGNING.md:30 | ClientHunter | B | release keystore file name | MED |
| docs/SIGNING.md:30 | ClientHunter | B | keystore key alias (baked into existing release keystore) | HIGH |
| docs/SIGNING.md:55 | ClientHunter | A | docs prose | LOW |
| docs/SIGNING.md:72 | ClientHunter | B | release keystore file name | MED |
| docs/SIGNING.md:74 | ClientHunter | B | keystore key alias (baked into existing release keystore) | HIGH |
| docs/SIGNING.md:81 | ClientHunter | B | release keystore file name | MED |
| docs/SIGNING.md:83 | ClientHunter | B | keystore key alias (baked into existing release keystore) | HIGH |
| docs/SIGNING.md:97 | ClientHunter | B | release keystore file name | MED |
| docs/SIGNING.md:100 | ClientHunter | B | release keystore file name | MED |
| docs/SIGNING.md:111 | ClientHunter | B | keystore key alias (baked into existing release keystore) | HIGH |
| docs/SIGNING.md:113 | ClientHunter | B | URL/domain (stale; not the live domain) | MED |
| docs/SIGNING.md:140 | ClientHunter | B | release keystore file name | MED |
| docs/SIGNING.md:140 | ClientHunter | B | keystore key alias (baked into existing release keystore) | HIGH |
| docs/STORE_ASSETS.md:1 | ClientHunter | A | doc title | LOW |
| docs/STORE_ASSETS.md:23 | ClientHunter | C | Play Store listing copy (feature graphic headline) | MED |
| docs/STORE_ASSETS.md:51 | ClientHunter | C | Play Store app-name field value | MED |
| docs/STORE_ASSETS.md:66 | ClientHunter | C | Play Store full description | MED |
| docs/STORE_ASSETS.md:68 | ClientHunter | C | Play Store full description | MED |
| docs/STORE_ASSETS.md:83 | ClientHunter | C | Play Store full description | MED |
| docs/STORE_ASSETS.md:96 | ClientHunter | C | Play Store full description | MED |
| docs/STORE_ASSETS.md:115 | ClientHunter | B | URL/domain (stale; not the live domain) | MED |
| docs/STORE_ASSETS.md:117 | ClientHunter | B | URL/domain (stale; not the live domain) | MED |
| docs/api-reference.md:1 | ClientHunter | A | doc title | LOW |
| docs/api-reference.md:42 | Vectorae | A | docs prose | LOW |
| docs/api-reference.md:164 | Vectorae | A | docs prose | LOW |
| docs/api-reference.md:176 | LeadPilot | B | webhook payload enum value (`source`) | HIGH |
| docs/api-reference.md:457 | LeadPilot | B | webhook signature header name (customer verifiers depend on it) | HIGH |
| docs/api-reference.md:493 | LeadPilot | B | webhook signature header name (customer verifiers depend on it) | HIGH |
| docs/api-reference.md:563 | lpk_ | B | API key prefix (issued keys carry it) | HIGH |
| docs/api-reference.md:586 | LeadPilot | B | webhook header name | HIGH |
| docs/api-reference.md:587 | LeadPilot | B | webhook header name | HIGH |
| docs/api-reference.md:587 | LeadPilot | B | webhook signature header name (customer verifiers depend on it) | HIGH |
| docs/api-reference.md:604 | Vectorae | A | docs prose | LOW |
| docs/api-reference.md:613 | LeadPilot | B | webhook timestamp header name | HIGH |
| docs/api-reference.md:613 | LeadPilot | B | webhook signature header name (customer verifiers depend on it) | HIGH |
| docs/api-reference.md:673 | Vectorae | A | docs prose | LOW |
| docs/api-reference.md:677 | Vectorae | B | doc link target (breaks if file renamed) | LOW |
| docs/api-reference.md:677 | Vectorae | B | doc link target (breaks if file renamed) | LOW |
| docs/api/endpoints.md:181 | Vectorae | A | docs prose | LOW |
| docs/api/endpoints.md:325 | Vectorae | A | docs prose | LOW |
| docs/backup/backup-procedure.md:7 | LeadPilot | B | operator backup path (existing backups stored there) | LOW |
| docs/backup/backup-procedure.md:24 | LeadPilot | B | operator backup path (existing backups stored there) | LOW |
| docs/backup/backup-procedure.md:36 | LeadPilot | B | operator backup path (existing backups stored there) | LOW |
| docs/backup/backup-procedure.md:67 | LeadPilot | B | operator backup path (existing backups stored there) | LOW |
| docs/backup/backup-procedure.md:89 | LeadPilot | B | operator backup path (existing backups stored there) | LOW |
| docs/backup/backup-procedure.md:92 | LeadPilot | B | operator backup path (existing backups stored there) | LOW |
| docs/backup/backup-procedure.md:130 | LeadPilot | B | pg_dump file name convention | LOW |
| docs/backup/backup-procedure.md:133 | LeadPilot | B | pg_dump file name convention | LOW |
| docs/backup/backup-procedure.md:134 | LeadPilot | B | pg_dump file name convention | LOW |
| docs/backup/backup-procedure.md:148 | LeadPilot | B | pg_dump file name convention | LOW |
| docs/backup/backup-procedure.md:226 | LeadPilot | B | operator backup path (existing backups stored there) | LOW |
| docs/connectors/README.md:1 | Vectorae | A | doc title | LOW |
| docs/connectors/README.md:3 | Vectorae | A | docs prose | LOW |
| docs/connectors/README.md:10 | Vectorae | A | docs prose | LOW |
| docs/connectors/README.md:16 | Vectorae | A | docs prose | LOW |
| docs/connectors/README.md:18 | LeadPilot | B | Claude skill directory/name | MED |
| docs/connectors/README.md:19 | Vectorae | A | docs prose | LOW |
| docs/connectors/README.md:38 | Vectorae | C | connector name users type into Claude custom-connector UI (third-party listing surface) | MED |
| docs/connectors/README.md:40 | Vectorae | A | docs prose | LOW |
| docs/connectors/README.md:42 | Vectorae | A | docs prose | LOW |
| docs/connectors/README.md:49 | LeadPilot | B | Claude skill directory/name | MED |
| docs/connectors/README.md:54 | Vectorae | A | docs prose | LOW |
| docs/connectors/README.md:55 | Vectorae | A | docs prose | LOW |
| docs/connectors/README.md:56 | Vectorae | A | docs prose | LOW |
| docs/connectors/README.md:56 | Vectorae | A | docs prose | LOW |
| docs/connectors/README.md:58 | Vectorae | A | docs prose | LOW |
| docs/connectors/README.md:65 | LeadPilot | B | GitHub repo / plugin marketplace name | HIGH |
| docs/connectors/README.md:66 | LeadPilot | B | Claude Code plugin@marketplace name | HIGH |
| docs/connectors/README.md:66 | LeadPilot | B | Claude Code plugin@marketplace name | HIGH |
| docs/connectors/README.md:70 | LeadPilot | B | plugin directory path | MED |
| docs/connectors/README.md:74 | LeadPilot | B | local MCP server name in claude mcp add command | LOW |
| docs/connectors/README.md:77 | LeadPilot | B | local MCP server name in claude mcp add command | LOW |
| docs/connectors/README.md:78 | Vectorae | A | docs prose | LOW |
| docs/connectors/README.md:88 | Vectorae | A | docs prose | LOW |
| docs/connectors/README.md:99 | LeadPilot | B | OAuth scope string (issued tokens/consent depend on it) | HIGH |
| docs/connectors/README.md:100 | LeadPilot | B | OAuth scope string (issued tokens/consent depend on it) | HIGH |
| docs/connectors/README.md:110 | Vectorae | C | connector privacy/data-handling disclosure | MED |
| docs/connectors/README.md:112 | Vectorae | C | connector privacy/data-handling disclosure | MED |
| docs/connectors/README.md:120 | Vectorae | C | connector privacy/data-handling disclosure | MED |
| docs/connectors/README.md:130 | Vectorae | C | connector prompt-injection/data-handling disclosure | MED |
| docs/connectors/README.md:159 | Vectorae | C | Anthropic/OpenAI connector directory submission (reviewer test account) | MED |
| docs/features/ai-calling.md:8 | Vectorae | A | docs prose | LOW |
| docs/features/ai-support-chat.md:12 | Vectorae | A | docs prose | LOW |
| docs/features/ai-support-chat.md:29 | Vectorae | A | docs prose | LOW |
| docs/features/ai-support-chat.md:49 | Vectorae | A | docs prose | LOW |
| docs/features/ai-support-chat.md:314 | LeadPilot | B | operator backup path (existing backups stored there) | LOW |
| docs/features/annual-billing.md:16 | Vectorae | A | docs prose | LOW |
| docs/features/annual-billing.md:22 | Vectorae | A | docs prose | LOW |
| docs/features/annual-billing.md:336 | Vectorae | A | docs prose | LOW |
| docs/features/annual-billing.md:352 | Vectorae | A | docs prose | LOW |
| docs/features/annual-billing.md:426 | Vectorae | A | docs prose | LOW |
| docs/features/autopilot-launch.md:239 | LeadPilot | B | Celery task name (queued/beat messages reference it) | HIGH |
| docs/features/autopilot-launch.md:317 | LeadPilot | B | Celery task name (queued/beat messages reference it) | HIGH |
| docs/features/autopilot-launch.md:377 | LeadPilot | B | Celery task name (queued/beat messages reference it) | HIGH |
| docs/features/benchmarks.md:6 | Vectorae | A | docs prose | LOW |
| docs/features/compliance-rules.md:45 | Vectorae | A | docs prose | LOW |
| docs/features/consent-layer.md:73 | Vectorae | A | docs prose | LOW |
| docs/features/crm-ecosystem.md:5 | Vectorae | A | docs prose | LOW |
| docs/features/crm-ecosystem.md:9 | Vectorae | A | docs prose | LOW |
| docs/features/crm-ecosystem.md:26 | Vectorae | A | docs prose | LOW |
| docs/features/crm-ecosystem.md:33 | Vectorae | A | docs prose | LOW |
| docs/features/crm-ecosystem.md:33 | Vectorae | A | docs prose | LOW |
| docs/features/crm-ecosystem.md:35 | Vectorae | A | docs prose | LOW |
| docs/features/crm-ecosystem.md:44 | Vectorae | A | docs prose | LOW |
| docs/features/crm-ecosystem.md:47 | Vectorae | A | docs prose | LOW |
| docs/features/crm-ecosystem.md:61 | LeadPilot | B | webhook timestamp header name | HIGH |
| docs/features/crm-ecosystem.md:62 | LeadPilot | B | webhook signature header name (customer verifiers depend on it) | HIGH |
| docs/features/crm-ecosystem.md:73 | LeadPilot | B | webhook signature header name (customer verifiers depend on it) | HIGH |
| docs/features/crm-ecosystem.md:75 | Vectorae | A | docs prose | LOW |
| docs/features/crm-ecosystem.md:79 | lpk_ | B | API key prefix (issued keys carry it) | HIGH |
| docs/features/crm-ecosystem.md:79 | lpk_ | B | API key prefix (issued keys carry it) | HIGH |
| docs/features/daily-send-approval.md:9 | Vectorae | A | docs prose | LOW |
| docs/features/daily-send-approval.md:10 | Vectorae | A | docs prose | LOW |
| docs/features/daily-send-approval.md:14 | Vectorae | A | docs prose | LOW |
| docs/features/daily-send-approval.md:22 | Vectorae | A | docs prose | LOW |
| docs/features/daily-send-approval.md:99 | Vectorae | A | docs prose | LOW |
| docs/features/daily-send-approval.md:202 | Vectorae | A | docs prose | LOW |
| docs/features/daily-send-approval.md:223 | Vectorae | A | docs prose | LOW |
| docs/features/daily-send-approval.md:285 | ClientHunter | B | Android deep-link URL scheme | HIGH |
| docs/features/email-network.md:8 | Vectorae | A | docs prose | LOW |
| docs/features/email-network.md:61 | LeadPilot | B | Celery task name (queued/beat messages reference it) | HIGH |
| docs/features/email-network.md:72 | Vectorae | A | docs prose | LOW |
| docs/features/email-network.md:206 | Vectorae | A | docs prose | LOW |
| docs/features/email-verification.md:11 | Vectorae | A | docs prose | LOW |
| docs/features/email-verification.md:84 | Vectorae | A | documented default of EMAIL_FROM_NAME (From display name of platform mail); config value lives in app/config.py | MED |
| docs/features/email-verification.md:240 | LeadPilot | B | operator backup path (existing backups stored there) | LOW |
| docs/features/email-verification.md:289 | LeadPilot | B | pg_dump file name convention | LOW |
| docs/features/email-verification.md:290 | LeadPilot | B | pg_dump file name convention | LOW |
| docs/features/engagement-hub.md:345 | Vectorae | A | docs prose | LOW |
| docs/features/f01-waterfall-enrichment.md:20 | Vectorae | A | docs prose | LOW |
| docs/features/f02-signal-radar.md:17 | Vectorae | A | docs prose | LOW |
| docs/features/f03-deliverability-autopilot.md:80 | Vectorae | A | docs prose | LOW |
| docs/features/f03-deliverability-autopilot.md:80 | Vectorae | A | docs prose | LOW |
| docs/features/f03-deliverability-autopilot.md:122 | Vectorae | A | docs prose | LOW |
| docs/features/f03-deliverability-autopilot.md:241 | Vectorae | A | docs prose | LOW |
| docs/features/f04-reply-copilot.md:24 | Vectorae | A | docs prose | LOW |
| docs/features/f04-reply-copilot.md:175 | Vectorae | A | docs prose | LOW |
| docs/features/f04-reply-copilot.md:253 | LeadPilot | B | Celery task name (queued/beat messages reference it) | HIGH |
| docs/features/f04-reply-copilot.md:536 | Vectorae | A | docs prose | LOW |
| docs/features/f04-reply-copilot.md:538 | Vectorae | A | docs prose | LOW |
| docs/features/f05-guardrails-studio.md:18 | Vectorae | A | docs prose | LOW |
| docs/features/f05-guardrails-studio.md:24 | Vectorae | A | docs prose | LOW |
| docs/features/f05-guardrails-studio.md:24 | Vectorae | A | docs prose | LOW |
| docs/features/f06-quickstart.md:19 | Vectorae | A | docs prose | LOW |
| docs/features/f06-quickstart.md:50 | LeadPilot | B | Celery task name (queued/beat messages reference it) | HIGH |
| docs/features/f06-quickstart.md:55 | LeadPilot | B | Celery task name (queued/beat messages reference it) | HIGH |
| docs/features/f06-quickstart.md:199 | Vectorae | B | User-Agent string other sites see (judge) | LOW |
| docs/features/f07-spend-guard.md:26 | Vectorae | A | docs prose | LOW |
| docs/features/f07-spend-guard.md:36 | Vectorae | A | docs prose | LOW |
| docs/features/f07-spend-guard.md:205 | Vectorae | A | docs prose | LOW |
| docs/features/f07-spend-guard.md:212 | Vectorae | A | docs prose | LOW |
| docs/features/f07-spend-guard.md:411 | Vectorae | A | docs prose | LOW |
| docs/features/f08-meetings-per-dollar.md:247 | Vectorae | A | docs prose | LOW |
| docs/features/f08-meetings-per-dollar.md:252 | Vectorae | A | docs prose | LOW |
| docs/features/f09-pilot-mode.md:28 | Vectorae | A | docs prose | LOW |
| docs/features/f09-pilot-mode.md:64 | Vectorae | A | docs prose | LOW |
| docs/features/f09-pilot-mode.md:127 | Vectorae | A | docs prose | LOW |
| docs/features/f09-pilot-mode.md:337 | Vectorae | A | docs prose | LOW |
| docs/features/f09-pilot-mode.md:347 | Vectorae | A | docs prose | LOW |
| docs/features/f09-pilot-mode.md:453 | Vectorae | A | docs prose | LOW |
| docs/features/f10-champion-tracker.md:26 | Vectorae | A | docs prose | LOW |
| docs/features/f10-champion-tracker.md:250 | LeadPilot | B | Celery task name (queued/beat messages reference it) | HIGH |
| docs/features/f10-champion-tracker.md:260 | LeadPilot | B | Celery task name (queued/beat messages reference it) | HIGH |
| docs/features/gdpr-erasure.md:178 | Vectorae | A | docs prose | LOW |
| docs/features/linkedin-channel.md:11 | Vectorae | A | docs prose | LOW |
| docs/features/linkedin-channel.md:48 | LeadPilot | B | webhook signature header name (customer verifiers depend on it) | HIGH |
| docs/features/local-business-mode.md:12 | Vectorae | A | docs prose | LOW |
| docs/features/local-business-mode.md:17 | Vectorae | A | docs prose | LOW |
| docs/features/local-business-mode.md:21 | Vectorae | A | docs prose | LOW |
| docs/features/local-business-mode.md:117 | Vectorae | A | docs prose | LOW |
| docs/features/local-business-mode.md:221 | Vectorae | A | docs prose | LOW |
| docs/features/local-business-mode.md:237 | Vectorae | A | docs prose | LOW |
| docs/features/local-business-mode.md:270 | Vectorae | A | docs prose | LOW |
| docs/features/local-business-mode.md:476 | Vectorae | A | docs prose | LOW |
| docs/features/local-business-mode.md:565 | Vectorae | A | docs prose | LOW |
| docs/features/mailbox-health.md:37 | Vectorae | A | docs prose | LOW |
| docs/features/mcp-connector.md:1 | Vectorae | A | doc title | LOW |
| docs/features/mcp-connector.md:11 | Vectorae | A | docs prose | LOW |
| docs/features/mcp-connector.md:15 | LeadPilot | B | Claude skill directory/name | MED |
| docs/features/mcp-connector.md:26 | LeadPilot | B | OAuth scope string (issued tokens/consent depend on it) | HIGH |
| docs/features/mcp-connector.md:26 | LeadPilot | B | OAuth scope string (issued tokens/consent depend on it) | HIGH |
| docs/features/mcp-connector.md:27 | LeadPilot | B | OAuth scope string (issued tokens/consent depend on it) | HIGH |
| docs/features/mcp-connector.md:27 | lpk_ | B | API key prefix (issued keys carry it) | HIGH |
| docs/features/mcp-connector.md:69 | LeadPilot | B | OAuth scope string (issued tokens/consent depend on it) | HIGH |
| docs/features/mcp-connector.md:69 | LeadPilot | B | OAuth scope string (issued tokens/consent depend on it) | HIGH |
| docs/features/mcp-connector.md:109 | LeadPilot | B | OAuth scope string (issued tokens/consent depend on it) | HIGH |
| docs/features/mcp-connector.md:111 | LeadPilot | B | OAuth scope string (issued tokens/consent depend on it) | HIGH |
| docs/features/mcp-connector.md:111 | LeadPilot | B | OAuth scope string (issued tokens/consent depend on it) | HIGH |
| docs/features/mcp-connector.md:132 | LeadPilot | B | Render service name | HIGH |
| docs/features/meeting-prep.md:6 | Vectorae | A | docs prose | LOW |
| docs/features/meeting-prep.md:28 | Vectorae | A | docs prose | LOW |
| docs/features/meeting-transcripts.md:5 | Vectorae | A | docs prose | LOW |
| docs/features/meeting-transcripts.md:36 | Vectorae | A | docs prose | LOW |
| docs/features/meeting-transcripts.md:73 | Vectorae | A | docs prose | LOW |
| docs/features/password-reset.md:34 | Vectorae | A | docs prose | LOW |
| docs/features/password-reset.md:62 | Vectorae | A | docs prose | LOW |
| docs/features/positive-reply-classifier.md:10 | Vectorae | A | docs prose | LOW |
| docs/features/reengagement.md:4 | Vectorae | A | docs prose | LOW |
| docs/features/send-review-queue.md:34 | Vectorae | A | docs prose | LOW |
| docs/features/sequence-completion.md:39 | Vectorae | A | docs prose | LOW |
| docs/features/trust-deliverability.md:66 | Vectorae | A | docs prose | LOW |
| docs/features/tutorial-section.md:1 | Vectorae | A | doc title | LOW |
| docs/features/tutorial-section.md:20 | Vectorae | A | docs prose | LOW |
| docs/features/tutorial-section.md:110 | LeadPilot | B | tutorial slug marked DO NOT CHANGE (progress rows key on it) | HIGH |
| docs/features/tutorial-section.md:111 | Vectorae | A | docs prose | LOW |
| docs/features/tutorial-section.md:215 | LeadPilot | B | operator backup path (existing backups stored there) | LOW |
| docs/features/unified-inbox.md:37 | Vectorae | A | docs prose | LOW |
| docs/features/vectorae-agents.md:1 | Vectorae | A | doc title | LOW |
| docs/features/vectorae-agents.md:69 | Vectorae | B | Python native extension module names | MED |
| docs/features/vectorae-agents.md:69 | Vectorae | B | Python native extension module names | MED |
| docs/features/vectorae-agents.md:73 | Vectorae | B | env var name | MED |
| docs/features/vectorae-agents.md:91 | Vectorae | B | env var name | MED |
| docs/features/workspaces.md:59 | LeadPilot | B | DNS TXT record name customers publish for domain verification | HIGH |
| docs/help-center/00-index.md:13 | LeadPilot | B | help-center article id/file name (chunk ids persisted in chat_messages.faq_ids; app/services/help_center.py:182 alias map; support_kb.py:76) | HIGH |
| docs/help-center/00-index.md:13 | LeadPilot | B | help-center article id/file name (chunk ids persisted in chat_messages.faq_ids; app/services/help_center.py:182 alias map; support_kb.py:76) | HIGH |
| docs/help-center/00-index.md:L13-L56 (48 occurrences on 42 lines) | Vectorae | A | docs prose (homogeneous; collapsed) | LOW |
| docs/help-center/01-what-is-leadpilot.md:2 | LeadPilot | B | help-center article id/file name (chunk ids persisted in chat_messages.faq_ids; app/services/help_center.py:182 alias map; support_kb.py:76) | HIGH |
| docs/help-center/01-what-is-leadpilot.md:3 | Vectorae | A | help-center article title (shown as Help AI "Sources:") | LOW |
| docs/help-center/01-what-is-leadpilot.md:39 | Vectorae | A-slug | help-center heading: display text, but slugify(heading) forms the chunk id persisted in chat_messages.faq_ids and LEGACY_FAQ_ALIASES | HIGH |
| docs/help-center/01-what-is-leadpilot.md:41 | Vectorae | A | docs prose | LOW |
| docs/help-center/01-what-is-leadpilot.md:41 | Vectorae | A | docs prose | LOW |
| docs/help-center/01-what-is-leadpilot.md:43 | Vectorae | A-slug | help-center heading: display text, but slugify(heading) forms the chunk id persisted in chat_messages.faq_ids and LEGACY_FAQ_ALIASES | HIGH |
| docs/help-center/01-what-is-leadpilot.md:47 | Vectorae | A | docs prose | LOW |
| docs/help-center/01-what-is-leadpilot.md:48 | Vectorae | A | docs prose | LOW |
| docs/help-center/01-what-is-leadpilot.md:50 | Vectorae | A | docs prose | LOW |
| docs/help-center/01-what-is-leadpilot.md:53 | Vectorae | A | docs prose | LOW |
| docs/help-center/01-what-is-leadpilot.md:58 | Vectorae | A | docs prose | LOW |
| docs/help-center/01-what-is-leadpilot.md:58 | Vectorae | A | docs prose | LOW |
| docs/help-center/01-what-is-leadpilot.md:62 | Vectorae | A | docs prose | LOW |
| docs/help-center/01-what-is-leadpilot.md:64 | Vectorae | A-slug | help-center heading: display text, but slugify(heading) forms the chunk id persisted in chat_messages.faq_ids and LEGACY_FAQ_ALIASES | HIGH |
| docs/help-center/01-what-is-leadpilot.md:69 | Vectorae | A | docs prose | LOW |
| docs/help-center/01-what-is-leadpilot.md:74 | Vectorae | A | docs prose | LOW |
| docs/help-center/01-what-is-leadpilot.md:80 | Vectorae | A-slug | help-center heading: display text, but slugify(heading) forms the chunk id persisted in chat_messages.faq_ids and LEGACY_FAQ_ALIASES | HIGH |
| docs/help-center/01-what-is-leadpilot.md:82 | Vectorae | A | docs prose | LOW |
| docs/help-center/01-what-is-leadpilot.md:86 | Vectorae | A | docs prose | LOW |
| docs/help-center/01-what-is-leadpilot.md:89 | Vectorae | A | docs prose | LOW |
| docs/help-center/02-who-its-for-and-not-for.md:3 | Vectorae | A | help-center article title (shown as Help AI "Sources:") | LOW |
| docs/help-center/02-who-its-for-and-not-for.md:37 | Vectorae | A-slug | help-center heading: display text, but slugify(heading) forms the chunk id persisted in chat_messages.faq_ids and LEGACY_FAQ_ALIASES | HIGH |
| docs/help-center/02-who-its-for-and-not-for.md:41 | Vectorae | A-slug | help-center heading: display text, but slugify(heading) forms the chunk id persisted in chat_messages.faq_ids and LEGACY_FAQ_ALIASES | HIGH |
| docs/help-center/02-who-its-for-and-not-for.md:55 | Vectorae | A-slug | help-center heading: display text, but slugify(heading) forms the chunk id persisted in chat_messages.faq_ids and LEGACY_FAQ_ALIASES | HIGH |
| docs/help-center/02-who-its-for-and-not-for.md:76 | Vectorae | A-slug | help-center heading: display text, but slugify(heading) forms the chunk id persisted in chat_messages.faq_ids and LEGACY_FAQ_ALIASES | HIGH |
| docs/help-center/02-who-its-for-and-not-for.md:98 | Vectorae | A-slug | help-center heading: display text, but slugify(heading) forms the chunk id persisted in chat_messages.faq_ids and LEGACY_FAQ_ALIASES | HIGH |
| docs/help-center/02-who-its-for-and-not-for.md:102 | Vectorae | A-slug | help-center heading: display text, but slugify(heading) forms the chunk id persisted in chat_messages.faq_ids and LEGACY_FAQ_ALIASES | HIGH |
| docs/help-center/02-who-its-for-and-not-for.md:115 | LeadPilot | B | help-center article id/file name (chunk ids persisted in chat_messages.faq_ids; app/services/help_center.py:182 alias map; support_kb.py:76) | HIGH |
| docs/help-center/02-who-its-for-and-not-for.md:L39-L115 (23 occurrences on 18 lines) | Vectorae | A | docs prose (homogeneous; collapsed) | LOW |
| docs/help-center/03-getting-started.md:3 | Vectorae | A | help-center article title (shown as Help AI "Sources:") | LOW |
| docs/help-center/03-getting-started.md:51 | Vectorae | A-slug | help-center heading: display text, but slugify(heading) forms the chunk id persisted in chat_messages.faq_ids and LEGACY_FAQ_ALIASES | HIGH |
| docs/help-center/03-getting-started.md:61 | Vectorae | A | docs prose | LOW |
| docs/help-center/03-getting-started.md:61 | Vectorae | A | docs prose | LOW |
| docs/help-center/03-getting-started.md:62 | Vectorae | A | docs prose | LOW |
| docs/help-center/03-getting-started.md:68 | Vectorae | A | docs prose | LOW |
| docs/help-center/03-getting-started.md:78 | Vectorae | A | docs prose | LOW |
| docs/help-center/03-getting-started.md:80 | Vectorae | A-slug | help-center heading: display text, but slugify(heading) forms the chunk id persisted in chat_messages.faq_ids and LEGACY_FAQ_ALIASES | HIGH |
| docs/help-center/03-getting-started.md:84 | Vectorae | A | docs prose | LOW |
| docs/help-center/03-getting-started.md:86 | Vectorae | A | docs prose | LOW |
| docs/help-center/03-getting-started.md:94 | Vectorae | A | docs prose | LOW |
| docs/help-center/03-getting-started.md:98 | Vectorae | A | docs prose | LOW |
| docs/help-center/03-getting-started.md:98 | Vectorae | A | docs prose | LOW |
| docs/help-center/03-getting-started.md:113 | Vectorae | A | docs prose | LOW |
| docs/help-center/03-getting-started.md:113 | Vectorae | A | docs prose | LOW |
| docs/help-center/03-getting-started.md:117 | Vectorae | A | docs prose | LOW |
| docs/help-center/03-getting-started.md:131 | Vectorae | A | docs prose | LOW |
| docs/help-center/04-research-pipeline.md:32 | Vectorae | A | docs prose | LOW |
| docs/help-center/04-research-pipeline.md:40 | Vectorae | A | docs prose | LOW |
| docs/help-center/04-research-pipeline.md:57 | Vectorae | A | docs prose | LOW |
| docs/help-center/04-research-pipeline.md:57 | Vectorae | A | docs prose | LOW |
| docs/help-center/04-research-pipeline.md:59 | Vectorae | A | docs prose | LOW |
| docs/help-center/04-research-pipeline.md:76 | Vectorae | A | docs prose | LOW |
| docs/help-center/04-research-pipeline.md:79 | Vectorae | A | docs prose | LOW |
| docs/help-center/04-research-pipeline.md:80 | Vectorae | A | docs prose | LOW |
| docs/help-center/05-strategy-verification.md:26 | Vectorae | A | docs prose | LOW |
| docs/help-center/05-strategy-verification.md:30 | Vectorae | A | docs prose | LOW |
| docs/help-center/05-strategy-verification.md:33 | Vectorae | A | docs prose | LOW |
| docs/help-center/05-strategy-verification.md:37 | Vectorae | A | docs prose | LOW |
| docs/help-center/05-strategy-verification.md:62 | Vectorae | A | docs prose | LOW |
| docs/help-center/05-strategy-verification.md:63 | Vectorae | A | docs prose | LOW |
| docs/help-center/05-strategy-verification.md:86 | Vectorae | A | docs prose | LOW |
| docs/help-center/05-strategy-verification.md:105 | Vectorae | A | docs prose | LOW |
| docs/help-center/06-lead-sourcing-and-email-verification.md:49 | Vectorae | A | docs prose | LOW |
| docs/help-center/06-lead-sourcing-and-email-verification.md:53 | Vectorae | A | docs prose | LOW |
| docs/help-center/06-lead-sourcing-and-email-verification.md:57 | Vectorae | A | docs prose | LOW |
| docs/help-center/06-lead-sourcing-and-email-verification.md:65 | Vectorae | A | docs prose | LOW |
| docs/help-center/06-lead-sourcing-and-email-verification.md:101 | Vectorae | A | docs prose | LOW |
| docs/help-center/06-lead-sourcing-and-email-verification.md:111 | Vectorae | A | docs prose | LOW |
| docs/help-center/06-lead-sourcing-and-email-verification.md:111 | Vectorae | A | docs prose | LOW |
| docs/help-center/06-lead-sourcing-and-email-verification.md:126 | Vectorae | A | docs prose | LOW |
| docs/help-center/07-personalization-and-claim-verification.md:34 | Vectorae | A | docs prose | LOW |
| docs/help-center/07-personalization-and-claim-verification.md:34 | Vectorae | A | docs prose | LOW |
| docs/help-center/07-personalization-and-claim-verification.md:38 | Vectorae | A | docs prose | LOW |
| docs/help-center/07-personalization-and-claim-verification.md:47 | Vectorae | A | docs prose | LOW |
| docs/help-center/07-personalization-and-claim-verification.md:49 | Vectorae | A-slug | help-center heading: display text, but slugify(heading) forms the chunk id persisted in chat_messages.faq_ids and LEGACY_FAQ_ALIASES | HIGH |
| docs/help-center/07-personalization-and-claim-verification.md:52 | Vectorae | A | docs prose | LOW |
| docs/help-center/07-personalization-and-claim-verification.md:54 | Vectorae | A | docs prose | LOW |
| docs/help-center/07-personalization-and-claim-verification.md:56 | Vectorae | A | docs prose | LOW |
| docs/help-center/07-personalization-and-claim-verification.md:60 | Vectorae | A | docs prose | LOW |
| docs/help-center/07-personalization-and-claim-verification.md:62 | Vectorae | A-slug | help-center heading: display text, but slugify(heading) forms the chunk id persisted in chat_messages.faq_ids and LEGACY_FAQ_ALIASES | HIGH |
| docs/help-center/07-personalization-and-claim-verification.md:71 | Vectorae | A | docs prose | LOW |
| docs/help-center/07-personalization-and-claim-verification.md:80 | Vectorae | A | docs prose | LOW |
| docs/help-center/08-sequences-and-follow-ups.md:44 | Vectorae | A | docs prose | LOW |
| docs/help-center/08-sequences-and-follow-ups.md:50 | Vectorae | A | docs prose | LOW |
| docs/help-center/08-sequences-and-follow-ups.md:62 | Vectorae | A | docs prose | LOW |
| docs/help-center/08-sequences-and-follow-ups.md:65 | Vectorae | A | docs prose | LOW |
| docs/help-center/08-sequences-and-follow-ups.md:80 | Vectorae | A-slug | help-center heading: display text, but slugify(heading) forms the chunk id persisted in chat_messages.faq_ids and LEGACY_FAQ_ALIASES | HIGH |
| docs/help-center/08-sequences-and-follow-ups.md:93 | Vectorae | A | docs prose | LOW |
| docs/help-center/08-sequences-and-follow-ups.md:99 | Vectorae | A | docs prose | LOW |
| docs/help-center/08-sequences-and-follow-ups.md:100 | Vectorae | A | docs prose | LOW |
| docs/help-center/08-sequences-and-follow-ups.md:104 | Vectorae | A-slug | help-center heading: display text, but slugify(heading) forms the chunk id persisted in chat_messages.faq_ids and LEGACY_FAQ_ALIASES | HIGH |
| docs/help-center/08-sequences-and-follow-ups.md:129 | Vectorae | A | docs prose | LOW |
| docs/help-center/08-sequences-and-follow-ups.md:138 | Vectorae | A | docs prose | LOW |
| docs/help-center/08-sequences-and-follow-ups.md:146 | Vectorae | A | docs prose | LOW |
| docs/help-center/08-sequences-and-follow-ups.md:146 | Vectorae | A | docs prose | LOW |
| docs/help-center/08-sequences-and-follow-ups.md:152 | Vectorae | A | docs prose | LOW |
| docs/help-center/08-sequences-and-follow-ups.md:154 | Vectorae | A | docs prose | LOW |
| docs/help-center/09-email-sending-gmail.md:38 | Vectorae | A | docs prose | LOW |
| docs/help-center/09-email-sending-gmail.md:44 | Vectorae | A | docs prose | LOW |
| docs/help-center/09-email-sending-gmail.md:45 | Vectorae | A | docs prose | LOW |
| docs/help-center/09-email-sending-gmail.md:47 | Vectorae | A | docs prose | LOW |
| docs/help-center/09-email-sending-gmail.md:49 | Vectorae | A | docs prose | LOW |
| docs/help-center/09-email-sending-gmail.md:55 | Vectorae | A | docs prose | LOW |
| docs/help-center/09-email-sending-gmail.md:57 | Vectorae | A | docs prose | LOW |
| docs/help-center/09-email-sending-gmail.md:61 | Vectorae | A-slug | help-center heading: display text, but slugify(heading) forms the chunk id persisted in chat_messages.faq_ids and LEGACY_FAQ_ALIASES | HIGH |
| docs/help-center/09-email-sending-gmail.md:84 | Vectorae | A | docs prose | LOW |
| docs/help-center/09-email-sending-gmail.md:86 | Vectorae | A-slug | help-center heading: display text, but slugify(heading) forms the chunk id persisted in chat_messages.faq_ids and LEGACY_FAQ_ALIASES | HIGH |
| docs/help-center/09-email-sending-gmail.md:97 | Vectorae | A | docs prose | LOW |
| docs/help-center/09-email-sending-gmail.md:99 | Vectorae | A | docs prose | LOW |
| docs/help-center/09-email-sending-gmail.md:112 | Vectorae | A | docs prose | LOW |
| docs/help-center/10-whatsapp-outreach.md:45 | Vectorae | A | docs prose | LOW |
| docs/help-center/10-whatsapp-outreach.md:45 | Vectorae | A | docs prose | LOW |
| docs/help-center/10-whatsapp-outreach.md:56 | Vectorae | A | docs prose | LOW |
| docs/help-center/10-whatsapp-outreach.md:68 | Vectorae | A | docs prose | LOW |
| docs/help-center/10-whatsapp-outreach.md:71 | Vectorae | A | docs prose | LOW |
| docs/help-center/10-whatsapp-outreach.md:89 | Vectorae | A | docs prose | LOW |
| docs/help-center/10-whatsapp-outreach.md:91 | Vectorae | A | docs prose | LOW |
| docs/help-center/10-whatsapp-outreach.md:98 | Vectorae | A | docs prose | LOW |
| docs/help-center/10-whatsapp-outreach.md:106 | Vectorae | A | docs prose | LOW |
| docs/help-center/10-whatsapp-outreach.md:108 | Vectorae | A | docs prose | LOW |
| docs/help-center/10-whatsapp-outreach.md:120 | Vectorae | A | docs prose | LOW |
| docs/help-center/10-whatsapp-outreach.md:126 | Vectorae | A | docs prose | LOW |
| docs/help-center/10-whatsapp-outreach.md:130 | Vectorae | A | docs prose | LOW |
| docs/help-center/11-linkedin.md:80 | Vectorae | A-slug | help-center heading: display text, but slugify(heading) forms the chunk id persisted in chat_messages.faq_ids and LEGACY_FAQ_ALIASES | HIGH |
| docs/help-center/11-linkedin.md:117 | Vectorae | A-slug | help-center heading: display text, but slugify(heading) forms the chunk id persisted in chat_messages.faq_ids and LEGACY_FAQ_ALIASES | HIGH |
| docs/help-center/11-linkedin.md:146 | Vectorae | A-slug | help-center heading: display text, but slugify(heading) forms the chunk id persisted in chat_messages.faq_ids and LEGACY_FAQ_ALIASES | HIGH |
| docs/help-center/11-linkedin.md:L42-L164 (18 occurrences on 17 lines) | Vectorae | A | docs prose (homogeneous; collapsed) | LOW |
| docs/help-center/12-send-review-queue.md:32 | Vectorae | A | docs prose | LOW |
| docs/help-center/12-send-review-queue.md:32 | Vectorae | A | docs prose | LOW |
| docs/help-center/12-send-review-queue.md:39 | Vectorae | A | docs prose | LOW |
| docs/help-center/12-send-review-queue.md:41 | Vectorae | A | docs prose | LOW |
| docs/help-center/12-send-review-queue.md:47 | Vectorae | A | docs prose | LOW |
| docs/help-center/12-send-review-queue.md:49 | Vectorae | A | docs prose | LOW |
| docs/help-center/12-send-review-queue.md:51 | Vectorae | A | docs prose | LOW |
| docs/help-center/12-send-review-queue.md:57 | Vectorae | A | docs prose | LOW |
| docs/help-center/12-send-review-queue.md:61 | Vectorae | A | docs prose | LOW |
| docs/help-center/12-send-review-queue.md:75 | Vectorae | A | docs prose | LOW |
| docs/help-center/12-send-review-queue.md:85 | Vectorae | A | docs prose | LOW |
| docs/help-center/12-send-review-queue.md:93 | Vectorae | A | docs prose | LOW |
| docs/help-center/12-send-review-queue.md:112 | Vectorae | A | docs prose | LOW |
| docs/help-center/13-replies-and-unified-inbox.md:34 | Vectorae | A | docs prose | LOW |
| docs/help-center/13-replies-and-unified-inbox.md:34 | Vectorae | A | docs prose | LOW |
| docs/help-center/13-replies-and-unified-inbox.md:36 | Vectorae | A-slug | help-center heading: display text, but slugify(heading) forms the chunk id persisted in chat_messages.faq_ids and LEGACY_FAQ_ALIASES | HIGH |
| docs/help-center/13-replies-and-unified-inbox.md:38 | Vectorae | A | docs prose | LOW |
| docs/help-center/13-replies-and-unified-inbox.md:57 | Vectorae | A-slug | help-center heading: display text, but slugify(heading) forms the chunk id persisted in chat_messages.faq_ids and LEGACY_FAQ_ALIASES | HIGH |
| docs/help-center/13-replies-and-unified-inbox.md:68 | Vectorae | A | docs prose | LOW |
| docs/help-center/13-replies-and-unified-inbox.md:80 | Vectorae | A | docs prose | LOW |
| docs/help-center/14-booking-and-calendar.md:31 | Vectorae | A | docs prose | LOW |
| docs/help-center/14-booking-and-calendar.md:31 | Vectorae | A | docs prose | LOW |
| docs/help-center/14-booking-and-calendar.md:33 | Vectorae | A-slug | help-center heading: display text, but slugify(heading) forms the chunk id persisted in chat_messages.faq_ids and LEGACY_FAQ_ALIASES | HIGH |
| docs/help-center/14-booking-and-calendar.md:35 | Vectorae | A | docs prose | LOW |
| docs/help-center/14-booking-and-calendar.md:35 | Vectorae | A | docs prose | LOW |
| docs/help-center/14-booking-and-calendar.md:35 | Vectorae | A | docs prose | LOW |
| docs/help-center/14-booking-and-calendar.md:36 | Vectorae | A | docs prose | LOW |
| docs/help-center/14-booking-and-calendar.md:36 | Vectorae | A | docs prose | LOW |
| docs/help-center/14-booking-and-calendar.md:36 | Vectorae | A | docs prose | LOW |
| docs/help-center/14-booking-and-calendar.md:38 | Vectorae | A | docs prose | LOW |
| docs/help-center/14-booking-and-calendar.md:56 | Vectorae | A | docs prose | LOW |
| docs/help-center/14-booking-and-calendar.md:66 | Vectorae | A-slug | help-center heading: display text, but slugify(heading) forms the chunk id persisted in chat_messages.faq_ids and LEGACY_FAQ_ALIASES | HIGH |
| docs/help-center/14-booking-and-calendar.md:72 | Vectorae | A | docs prose | LOW |
| docs/help-center/14-booking-and-calendar.md:72 | Vectorae | A | docs prose | LOW |
| docs/help-center/14-booking-and-calendar.md:82 | Vectorae | A | docs prose | LOW |
| docs/help-center/14-booking-and-calendar.md:92 | Vectorae | A | docs prose | LOW |
| docs/help-center/14-booking-and-calendar.md:96 | Vectorae | A | docs prose | LOW |
| docs/help-center/15-meetings-prep-room-transcripts.md:33 | Vectorae | A | docs prose | LOW |
| docs/help-center/15-meetings-prep-room-transcripts.md:37 | Vectorae | A | docs prose | LOW |
| docs/help-center/15-meetings-prep-room-transcripts.md:37 | Vectorae | A | docs prose | LOW |
| docs/help-center/15-meetings-prep-room-transcripts.md:44 | Vectorae | A | docs prose | LOW |
| docs/help-center/15-meetings-prep-room-transcripts.md:48 | Vectorae | A | docs prose | LOW |
| docs/help-center/15-meetings-prep-room-transcripts.md:52 | Vectorae | A | docs prose | LOW |
| docs/help-center/15-meetings-prep-room-transcripts.md:70 | Vectorae | A | docs prose | LOW |
| docs/help-center/15-meetings-prep-room-transcripts.md:76 | Vectorae | A | docs prose | LOW |
| docs/help-center/15-meetings-prep-room-transcripts.md:80 | Vectorae | A-slug | help-center heading: display text, but slugify(heading) forms the chunk id persisted in chat_messages.faq_ids and LEGACY_FAQ_ALIASES | HIGH |
| docs/help-center/15-meetings-prep-room-transcripts.md:84 | Vectorae | A | docs prose | LOW |
| docs/help-center/15-meetings-prep-room-transcripts.md:88 | Vectorae | A | docs prose | LOW |
| docs/help-center/15-meetings-prep-room-transcripts.md:92 | Vectorae | A | docs prose | LOW |
| docs/help-center/15-meetings-prep-room-transcripts.md:92 | Vectorae | A | docs prose | LOW |
| docs/help-center/15-meetings-prep-room-transcripts.md:96 | Vectorae | A | docs prose | LOW |
| docs/help-center/15-meetings-prep-room-transcripts.md:98 | Vectorae | A | docs prose | LOW |
| docs/help-center/15-meetings-prep-room-transcripts.md:98 | Vectorae | A | docs prose | LOW |
| docs/help-center/16-crm-and-integrations.md:30 | Vectorae | A | docs prose | LOW |
| docs/help-center/16-crm-and-integrations.md:32 | Vectorae | A-slug | help-center heading: display text, but slugify(heading) forms the chunk id persisted in chat_messages.faq_ids and LEGACY_FAQ_ALIASES | HIGH |
| docs/help-center/16-crm-and-integrations.md:45 | Vectorae | A | docs prose | LOW |
| docs/help-center/16-crm-and-integrations.md:47 | Vectorae | A | docs prose | LOW |
| docs/help-center/16-crm-and-integrations.md:55 | Vectorae | A | docs prose | LOW |
| docs/help-center/16-crm-and-integrations.md:63 | Vectorae | A | docs prose | LOW |
| docs/help-center/16-crm-and-integrations.md:63 | Vectorae | A | docs prose | LOW |
| docs/help-center/16-crm-and-integrations.md:68 | Vectorae | A | docs prose | LOW |
| docs/help-center/16-crm-and-integrations.md:74 | Vectorae | A | docs prose | LOW |
| docs/help-center/16-crm-and-integrations.md:82 | LeadPilot | B | webhook signature header name (customer verifiers depend on it) | HIGH |
| docs/help-center/16-crm-and-integrations.md:82 | Vectorae | A | docs prose | LOW |
| docs/help-center/16-crm-and-integrations.md:95 | lpk_ | B | API key prefix (issued keys carry it) | HIGH |
| docs/help-center/16-crm-and-integrations.md:95 | Vectorae | A | docs prose | LOW |
| docs/help-center/16-crm-and-integrations.md:95 | lpk_ | B | API key prefix (issued keys carry it) | HIGH |
| docs/help-center/17-learning-loop-and-ab-tests.md:34 | Vectorae | A | docs prose | LOW |
| docs/help-center/17-learning-loop-and-ab-tests.md:36 | Vectorae | A-slug | help-center heading: display text, but slugify(heading) forms the chunk id persisted in chat_messages.faq_ids and LEGACY_FAQ_ALIASES | HIGH |
| docs/help-center/17-learning-loop-and-ab-tests.md:38 | Vectorae | A | docs prose | LOW |
| docs/help-center/17-learning-loop-and-ab-tests.md:40 | Vectorae | A | docs prose | LOW |
| docs/help-center/17-learning-loop-and-ab-tests.md:50 | Vectorae | A | docs prose | LOW |
| docs/help-center/17-learning-loop-and-ab-tests.md:75 | Vectorae | A | docs prose | LOW |
| docs/help-center/17-learning-loop-and-ab-tests.md:81 | Vectorae | A | docs prose | LOW |
| docs/help-center/17-learning-loop-and-ab-tests.md:87 | Vectorae | A | docs prose | LOW |
| docs/help-center/18-analytics-health-score-roi.md:34 | Vectorae | A | docs prose | LOW |
| docs/help-center/18-analytics-health-score-roi.md:54 | Vectorae | A | docs prose | LOW |
| docs/help-center/18-analytics-health-score-roi.md:64 | Vectorae | A | docs prose | LOW |
| docs/help-center/18-analytics-health-score-roi.md:75 | Vectorae | A | docs prose | LOW |
| docs/help-center/19-deliverability-and-mailbox-health.md:25 | Vectorae | A | docs prose | LOW |
| docs/help-center/19-deliverability-and-mailbox-health.md:35 | Vectorae | A | docs prose | LOW |
| docs/help-center/19-deliverability-and-mailbox-health.md:55 | Vectorae | A | docs prose | LOW |
| docs/help-center/19-deliverability-and-mailbox-health.md:61 | Vectorae | A | docs prose | LOW |
| docs/help-center/19-deliverability-and-mailbox-health.md:74 | Vectorae | A | docs prose | LOW |
| docs/help-center/20-compliance.md:38 | Vectorae | A | docs prose | LOW |
| docs/help-center/20-compliance.md:42 | Vectorae | A | docs prose | LOW |
| docs/help-center/20-compliance.md:56 | Vectorae | A | docs prose | LOW |
| docs/help-center/20-compliance.md:66 | Vectorae | A | docs prose | LOW |
| docs/help-center/20-compliance.md:74 | Vectorae | A-slug | help-center heading: display text, but slugify(heading) forms the chunk id persisted in chat_messages.faq_ids and LEGACY_FAQ_ALIASES | HIGH |
| docs/help-center/20-compliance.md:78 | Vectorae | A | docs prose | LOW |
| docs/help-center/20-compliance.md:81 | Vectorae | A | docs prose | LOW |
| docs/help-center/20-compliance.md:87 | Vectorae | A | docs prose | LOW |
| docs/help-center/20-compliance.md:100 | Vectorae | A | docs prose | LOW |
| docs/help-center/20-compliance.md:100 | Vectorae | A | docs prose | LOW |
| docs/help-center/20-compliance.md:104 | Vectorae | A | docs prose | LOW |
| docs/help-center/20-compliance.md:106 | Vectorae | A | docs prose | LOW |
| docs/help-center/20-compliance.md:121 | Vectorae | A | docs prose | LOW |
| docs/help-center/21-privacy-data-retention-deletion.md:42 | Vectorae | A | docs prose | LOW |
| docs/help-center/21-privacy-data-retention-deletion.md:44 | Vectorae | A-slug | help-center heading: display text, but slugify(heading) forms the chunk id persisted in chat_messages.faq_ids and LEGACY_FAQ_ALIASES | HIGH |
| docs/help-center/21-privacy-data-retention-deletion.md:46 | Vectorae | A | docs prose | LOW |
| docs/help-center/21-privacy-data-retention-deletion.md:55 | Vectorae | A | docs prose | LOW |
| docs/help-center/21-privacy-data-retention-deletion.md:57 | Vectorae | A-slug | help-center heading: display text, but slugify(heading) forms the chunk id persisted in chat_messages.faq_ids and LEGACY_FAQ_ALIASES | HIGH |
| docs/help-center/21-privacy-data-retention-deletion.md:59 | Vectorae | A | docs prose | LOW |
| docs/help-center/21-privacy-data-retention-deletion.md:63 | Vectorae | A | docs prose | LOW |
| docs/help-center/21-privacy-data-retention-deletion.md:67 | Vectorae | A | docs prose | LOW |
| docs/help-center/21-privacy-data-retention-deletion.md:81 | LeadPilot | B | account-export download file name generated by code | LOW |
| docs/help-center/21-privacy-data-retention-deletion.md:96 | Vectorae | A | docs prose | LOW |
| docs/help-center/21-privacy-data-retention-deletion.md:130 | Vectorae | A | docs prose | LOW |
| docs/help-center/21-privacy-data-retention-deletion.md:140 | Vectorae | A | docs prose | LOW |
| docs/help-center/21-privacy-data-retention-deletion.md:140 | Vectorae | A | docs prose | LOW |
| docs/help-center/21-privacy-data-retention-deletion.md:144 | Vectorae | A | docs prose | LOW |
| docs/help-center/21-privacy-data-retention-deletion.md:156 | Vectorae | A | docs prose | LOW |
| docs/help-center/21-privacy-data-retention-deletion.md:156 | Vectorae | A | docs prose | LOW |
| docs/help-center/21-privacy-data-retention-deletion.md:161 | Vectorae | A | docs prose | LOW |
| docs/help-center/22-plans-limits-billing.md:42 | Vectorae | A | docs prose | LOW |
| docs/help-center/22-plans-limits-billing.md:92 | Vectorae | A | docs prose | LOW |
| docs/help-center/22-plans-limits-billing.md:98 | Vectorae | A | docs prose | LOW |
| docs/help-center/22-plans-limits-billing.md:104 | Vectorae | A | docs prose | LOW |
| docs/help-center/22-plans-limits-billing.md:117 | Vectorae | A | docs prose | LOW |
| docs/help-center/22-plans-limits-billing.md:119 | Vectorae | A | docs prose | LOW |
| docs/help-center/22-plans-limits-billing.md:121 | Vectorae | A | docs prose | LOW |
| docs/help-center/22-plans-limits-billing.md:130 | Vectorae | A | docs prose | LOW |
| docs/help-center/22-plans-limits-billing.md:157 | Vectorae | A | docs prose | LOW |
| docs/help-center/22-plans-limits-billing.md:167 | Vectorae | A | docs prose | LOW |
| docs/help-center/23-account-security.md:37 | Vectorae | A | docs prose | LOW |
| docs/help-center/23-account-security.md:39 | Vectorae | A | docs prose | LOW |
| docs/help-center/23-account-security.md:54 | Vectorae | A | docs prose | LOW |
| docs/help-center/23-account-security.md:82 | Vectorae | A | docs prose | LOW |
| docs/help-center/23-account-security.md:94 | Vectorae | A | docs prose | LOW |
| docs/help-center/23-account-security.md:95 | Vectorae | A | docs prose | LOW |
| docs/help-center/23-account-security.md:101 | Vectorae | A | docs prose | LOW |
| docs/help-center/23-account-security.md:109 | lpk_ | B | API key prefix (issued keys carry it) | HIGH |
| docs/help-center/23-account-security.md:109 | Vectorae | A | docs prose | LOW |
| docs/help-center/24-workspaces-and-agency-mode.md:35 | Vectorae | A | docs prose | LOW |
| docs/help-center/24-workspaces-and-agency-mode.md:92 | Vectorae | A | docs prose | LOW |
| docs/help-center/24-workspaces-and-agency-mode.md:106 | Vectorae | A | docs prose | LOW |
| docs/help-center/24-workspaces-and-agency-mode.md:110 | Vectorae | A | docs prose | LOW |
| docs/help-center/24-workspaces-and-agency-mode.md:114 | Vectorae | A | docs prose | LOW |
| docs/help-center/24-workspaces-and-agency-mode.md:118 | Vectorae | A | docs prose | LOW |
| docs/help-center/25-pause-stop-kill-switch.md:36 | Vectorae | A | docs prose | LOW |
| docs/help-center/25-pause-stop-kill-switch.md:52 | Vectorae | A | docs prose | LOW |
| docs/help-center/25-pause-stop-kill-switch.md:66 | Vectorae | A | docs prose | LOW |
| docs/help-center/25-pause-stop-kill-switch.md:68 | Vectorae | A | docs prose | LOW |
| docs/help-center/25-pause-stop-kill-switch.md:79 | Vectorae | A | docs prose | LOW |
| docs/help-center/25-pause-stop-kill-switch.md:93 | Vectorae | A | docs prose | LOW |
| docs/help-center/26-mobile-app.md:35 | Vectorae | A | docs prose | LOW |
| docs/help-center/26-mobile-app.md:35 | Vectorae | A | docs prose | LOW |
| docs/help-center/26-mobile-app.md:39 | ClientHunter | B | Android applicationId | HIGH |
| docs/help-center/26-mobile-app.md:39 | Vectorae | A | docs prose | LOW |
| docs/help-center/26-mobile-app.md:47 | Vectorae | A | docs prose | LOW |
| docs/help-center/26-mobile-app.md:56 | Vectorae | A | docs prose | LOW |
| docs/help-center/26-mobile-app.md:57 | Vectorae | A | docs prose | LOW |
| docs/help-center/26-mobile-app.md:57 | Vectorae | A | docs prose | LOW |
| docs/help-center/26-mobile-app.md:57 | Vectorae | A | docs prose | LOW |
| docs/help-center/26-mobile-app.md:65 | Vectorae | A | docs prose | LOW |
| docs/help-center/26-mobile-app.md:65 | Vectorae | A | docs prose | LOW |
| docs/help-center/26-mobile-app.md:79 | Vectorae | A | docs prose | LOW |
| docs/help-center/26-mobile-app.md:81 | Vectorae | A | docs prose | LOW |
| docs/help-center/26-mobile-app.md:89 | Vectorae | A | docs prose | LOW |
| docs/help-center/26-mobile-app.md:95 | Vectorae | A | docs prose | LOW |
| docs/help-center/26-mobile-app.md:98 | Vectorae | A | docs prose | LOW |
| docs/help-center/26-mobile-app.md:98 | LeadPilot | B | help-center article id/file name (chunk ids persisted in chat_messages.faq_ids; app/services/help_center.py:182 alias map; support_kb.py:76) | HIGH |
| docs/help-center/27-troubleshooting.md:87 | Vectorae | A | docs prose | LOW |
| docs/help-center/28-glossary.md:3 | Vectorae | A | help-center article title (shown as Help AI "Sources:") | LOW |
| docs/help-center/28-glossary.md:40 | Vectorae | A-slug | help-center heading: display text, but slugify(heading) forms the chunk id persisted in chat_messages.faq_ids and LEGACY_FAQ_ALIASES | HIGH |
| docs/help-center/28-glossary.md:42 | Vectorae | A | docs prose | LOW |
| docs/help-center/28-glossary.md:47 | Vectorae | A | docs prose | LOW |
| docs/help-center/28-glossary.md:49 | Vectorae | A | docs prose | LOW |
| docs/help-center/28-glossary.md:56 | Vectorae | A | docs prose | LOW |
| docs/help-center/28-glossary.md:69 | Vectorae | A | docs prose | LOW |
| docs/help-center/28-glossary.md:90 | Vectorae | A | docs prose | LOW |
| docs/help-center/28-glossary.md:94 | Vectorae | A | docs prose | LOW |
| docs/help-center/28-glossary.md:96 | Vectorae | A | docs prose | LOW |
| docs/help-center/28-glossary.md:101 | Vectorae | A | docs prose | LOW |
| docs/help-center/28-glossary.md:108 | Vectorae | A | docs prose | LOW |
| docs/help-center/28-glossary.md:115 | lpk_ | B | API key prefix (issued keys carry it) | HIGH |
| docs/help-center/28-glossary.md:116 | Vectorae | A | docs prose | LOW |
| docs/help-center/28-glossary.md:119 | Vectorae | A | docs prose | LOW |
| docs/help-center/28-glossary.md:119 | LeadPilot | B | help-center article id/file name (chunk ids persisted in chat_messages.faq_ids; app/services/help_center.py:182 alias map; support_kb.py:76) | HIGH |
| docs/help-center/29-known-limitations.md:51 | Vectorae | A | docs prose | LOW |
| docs/help-center/29-known-limitations.md:56 | Vectorae | A | docs prose | LOW |
| docs/help-center/29-known-limitations.md:56 | Vectorae | A | docs prose | LOW |
| docs/help-center/29-known-limitations.md:60 | Vectorae | A | docs prose | LOW |
| docs/help-center/29-known-limitations.md:64 | Vectorae | A | docs prose | LOW |
| docs/help-center/29-known-limitations.md:72 | Vectorae | A | docs prose | LOW |
| docs/help-center/29-known-limitations.md:92 | Vectorae | A-slug | help-center heading: display text, but slugify(heading) forms the chunk id persisted in chat_messages.faq_ids and LEGACY_FAQ_ALIASES | HIGH |
| docs/help-center/29-known-limitations.md:106 | Vectorae | A | docs prose | LOW |
| docs/help-center/30-contact-support-and-status.md:94 | Vectorae | A-slug | help-center heading: display text, but slugify(heading) forms the chunk id persisted in chat_messages.faq_ids and LEGACY_FAQ_ALIASES | HIGH |
| docs/help-center/30-contact-support-and-status.md:L40-L119 (18 occurrences on 12 lines) | Vectorae | A | docs prose (homogeneous; collapsed) | LOW |
| docs/help-center/31-guide-solo-founder.md:3 | Vectorae | A | help-center article title (shown as Help AI "Sources:") | LOW |
| docs/help-center/31-guide-solo-founder.md:43 | Vectorae | A-slug | help-center heading: display text, but slugify(heading) forms the chunk id persisted in chat_messages.faq_ids and LEGACY_FAQ_ALIASES | HIGH |
| docs/help-center/31-guide-solo-founder.md:45 | Vectorae | A | docs prose | LOW |
| docs/help-center/31-guide-solo-founder.md:47 | Vectorae | A-slug | help-center heading: display text, but slugify(heading) forms the chunk id persisted in chat_messages.faq_ids and LEGACY_FAQ_ALIASES | HIGH |
| docs/help-center/31-guide-solo-founder.md:49 | Vectorae | A | docs prose | LOW |
| docs/help-center/31-guide-solo-founder.md:63 | Vectorae | A | docs prose | LOW |
| docs/help-center/31-guide-solo-founder.md:67 | Vectorae | A | docs prose | LOW |
| docs/help-center/31-guide-solo-founder.md:71 | Vectorae | A | docs prose | LOW |
| docs/help-center/31-guide-solo-founder.md:73 | Vectorae | A | docs prose | LOW |
| docs/help-center/31-guide-solo-founder.md:81 | Vectorae | A | docs prose | LOW |
| docs/help-center/31-guide-solo-founder.md:86 | Vectorae | A | docs prose | LOW |
| docs/help-center/32-guide-sdr-team-member.md:40 | Vectorae | A | docs prose | LOW |
| docs/help-center/33-product-profile-and-icp.md:36 | Vectorae | A | docs prose | LOW |
| docs/help-center/33-product-profile-and-icp.md:36 | Vectorae | A | docs prose | LOW |
| docs/help-center/33-product-profile-and-icp.md:49 | Vectorae | A | docs prose | LOW |
| docs/help-center/33-product-profile-and-icp.md:55 | Vectorae | A | docs prose | LOW |
| docs/help-center/33-product-profile-and-icp.md:57 | Vectorae | A | docs prose | LOW |
| docs/help-center/33-product-profile-and-icp.md:70 | Vectorae | A | docs prose | LOW |
| docs/help-center/33-product-profile-and-icp.md:74 | Vectorae | A | docs prose | LOW |
| docs/help-center/33-product-profile-and-icp.md:88 | Vectorae | A | docs prose | LOW |
| docs/help-center/33-product-profile-and-icp.md:103 | Vectorae | A | docs prose | LOW |
| docs/help-center/33-product-profile-and-icp.md:111 | Vectorae | A | docs prose | LOW |
| docs/help-center/34-strategy-patterns-and-playbooks.md:39 | Vectorae | A | docs prose | LOW |
| docs/help-center/34-strategy-patterns-and-playbooks.md:39 | Vectorae | A | docs prose | LOW |
| docs/help-center/34-strategy-patterns-and-playbooks.md:71 | Vectorae | A | docs prose | LOW |
| docs/help-center/34-strategy-patterns-and-playbooks.md:80 | Vectorae | A | docs prose | LOW |
| docs/help-center/34-strategy-patterns-and-playbooks.md:82 | Vectorae | A-slug | help-center heading: display text, but slugify(heading) forms the chunk id persisted in chat_messages.faq_ids and LEGACY_FAQ_ALIASES | HIGH |
| docs/help-center/34-strategy-patterns-and-playbooks.md:89 | Vectorae | A-slug | help-center heading: display text, but slugify(heading) forms the chunk id persisted in chat_messages.faq_ids and LEGACY_FAQ_ALIASES | HIGH |
| docs/help-center/35-google-workspace-dns-setup.md:26 | Vectorae | A | docs prose | LOW |
| docs/help-center/35-google-workspace-dns-setup.md:26 | Vectorae | A | docs prose | LOW |
| docs/help-center/35-google-workspace-dns-setup.md:26 | Vectorae | A | docs prose | LOW |
| docs/help-center/35-google-workspace-dns-setup.md:28 | Vectorae | A-slug | help-center heading: display text, but slugify(heading) forms the chunk id persisted in chat_messages.faq_ids and LEGACY_FAQ_ALIASES | HIGH |
| docs/help-center/35-google-workspace-dns-setup.md:30 | Vectorae | A | docs prose | LOW |
| docs/help-center/35-google-workspace-dns-setup.md:32 | Vectorae | A | docs prose | LOW |
| docs/help-center/35-google-workspace-dns-setup.md:38 | Vectorae | A | docs prose | LOW |
| docs/help-center/35-google-workspace-dns-setup.md:42 | Vectorae | A | docs prose | LOW |
| docs/help-center/35-google-workspace-dns-setup.md:42 | Vectorae | A | docs prose | LOW |
| docs/help-center/35-google-workspace-dns-setup.md:50 | Vectorae | A | docs prose | LOW |
| docs/help-center/35-google-workspace-dns-setup.md:50 | Vectorae | A | docs prose | LOW |
| docs/help-center/35-google-workspace-dns-setup.md:57 | Vectorae | A | docs prose | LOW |
| docs/help-center/35-google-workspace-dns-setup.md:81 | Vectorae | A-slug | help-center heading: display text, but slugify(heading) forms the chunk id persisted in chat_messages.faq_ids and LEGACY_FAQ_ALIASES | HIGH |
| docs/help-center/35-google-workspace-dns-setup.md:83 | Vectorae | A | docs prose | LOW |
| docs/help-center/35-google-workspace-dns-setup.md:83 | Vectorae | A | docs prose | LOW |
| docs/help-center/35-google-workspace-dns-setup.md:85 | Vectorae | A | docs prose | LOW |
| docs/help-center/35-google-workspace-dns-setup.md:89 | Vectorae | A | docs prose | LOW |
| docs/help-center/36-crm-sync-field-mapping.md:25 | Vectorae | A-slug | help-center heading: display text, but slugify(heading) forms the chunk id persisted in chat_messages.faq_ids and LEGACY_FAQ_ALIASES | HIGH |
| docs/help-center/36-crm-sync-field-mapping.md:46 | Vectorae | A-slug | help-center heading: display text, but slugify(heading) forms the chunk id persisted in chat_messages.faq_ids and LEGACY_FAQ_ALIASES | HIGH |
| docs/help-center/36-crm-sync-field-mapping.md:80 | Vectorae | A-slug | help-center heading: display text, but slugify(heading) forms the chunk id persisted in chat_messages.faq_ids and LEGACY_FAQ_ALIASES | HIGH |
| docs/help-center/36-crm-sync-field-mapping.md:L23-L120 (30 occurrences on 21 lines) | Vectorae | A | docs prose (homogeneous; collapsed) | LOW |
| docs/help-center/37-webhooks-and-slack-events.md:36 | Vectorae | A | docs prose | LOW |
| docs/help-center/37-webhooks-and-slack-events.md:44 | Vectorae | A | docs prose | LOW |
| docs/help-center/37-webhooks-and-slack-events.md:71 | LeadPilot | B | webhook header name | HIGH |
| docs/help-center/37-webhooks-and-slack-events.md:71 | LeadPilot | B | webhook header name | HIGH |
| docs/help-center/37-webhooks-and-slack-events.md:71 | LeadPilot | B | webhook signature header name (customer verifiers depend on it) | HIGH |
| docs/help-center/37-webhooks-and-slack-events.md:71 | ClientHunter | B | legacy webhook signature header name | HIGH |
| docs/help-center/37-webhooks-and-slack-events.md:75 | LeadPilot | B | webhook payload enum value (`source`) | HIGH |
| docs/help-center/37-webhooks-and-slack-events.md:92 | Vectorae | A-slug | help-center heading: display text, but slugify(heading) forms the chunk id persisted in chat_messages.faq_ids and LEGACY_FAQ_ALIASES | HIGH |
| docs/help-center/37-webhooks-and-slack-events.md:96 | LeadPilot | B | webhook signature header name (customer verifiers depend on it) | HIGH |
| docs/help-center/37-webhooks-and-slack-events.md:109 | LeadPilot | A | sample function name in customer code sample | LOW |
| docs/help-center/37-webhooks-and-slack-events.md:118 | ClientHunter | B | legacy webhook signature header name | HIGH |
| docs/help-center/37-webhooks-and-slack-events.md:118 | LeadPilot | B | webhook signature header name (customer verifiers depend on it) | HIGH |
| docs/help-center/37-webhooks-and-slack-events.md:122 | Vectorae | A | docs prose | LOW |
| docs/help-center/37-webhooks-and-slack-events.md:145 | Vectorae | A | docs prose | LOW |
| docs/help-center/37-webhooks-and-slack-events.md:157 | Vectorae | A | docs prose | LOW |
| docs/help-center/38-reply-copilot-and-classification.md:28 | Vectorae | A | docs prose | LOW |
| docs/help-center/38-reply-copilot-and-classification.md:30 | Vectorae | A-slug | help-center heading: display text, but slugify(heading) forms the chunk id persisted in chat_messages.faq_ids and LEGACY_FAQ_ALIASES | HIGH |
| docs/help-center/38-reply-copilot-and-classification.md:69 | Vectorae | A | docs prose | LOW |
| docs/help-center/38-reply-copilot-and-classification.md:69 | Vectorae | A | docs prose | LOW |
| docs/help-center/38-reply-copilot-and-classification.md:76 | Vectorae | A | docs prose | LOW |
| docs/help-center/38-reply-copilot-and-classification.md:80 | Vectorae | A | docs prose | LOW |
| docs/help-center/39-daily-send-approval-and-notifications.md:27 | Vectorae | A | docs prose | LOW |
| docs/help-center/39-daily-send-approval-and-notifications.md:27 | Vectorae | A | docs prose | LOW |
| docs/help-center/39-daily-send-approval-and-notifications.md:29 | Vectorae | A-slug | help-center heading: display text, but slugify(heading) forms the chunk id persisted in chat_messages.faq_ids and LEGACY_FAQ_ALIASES | HIGH |
| docs/help-center/39-daily-send-approval-and-notifications.md:31 | Vectorae | A | docs prose | LOW |
| docs/help-center/39-daily-send-approval-and-notifications.md:33 | Vectorae | A | docs prose | LOW |
| docs/help-center/39-daily-send-approval-and-notifications.md:46 | Vectorae | A | docs prose | LOW |
| docs/help-center/39-daily-send-approval-and-notifications.md:60 | Vectorae | A | docs prose | LOW |
| docs/help-center/39-daily-send-approval-and-notifications.md:70 | Vectorae | A | docs prose | LOW |
| docs/help-center/39-daily-send-approval-and-notifications.md:72 | Vectorae | A | docs prose | LOW |
| docs/help-center/39-daily-send-approval-and-notifications.md:81 | Vectorae | A | docs prose | LOW |
| docs/help-center/39-daily-send-approval-and-notifications.md:83 | Vectorae | A | docs prose | LOW |
| docs/help-center/39-daily-send-approval-and-notifications.md:83 | Vectorae | A | docs prose | LOW |
| docs/help-center/39-daily-send-approval-and-notifications.md:84 | Vectorae | A | docs prose | LOW |
| docs/help-center/39-daily-send-approval-and-notifications.md:94 | Vectorae | A | docs prose | LOW |
| docs/help-center/40-annual-billing-and-plan-changes.md:29 | Vectorae | A | docs prose | LOW |
| docs/help-center/40-annual-billing-and-plan-changes.md:44 | Vectorae | A | docs prose | LOW |
| docs/help-center/40-annual-billing-and-plan-changes.md:50 | Vectorae | A | docs prose | LOW |
| docs/help-center/40-annual-billing-and-plan-changes.md:68 | Vectorae | A | docs prose | LOW |
| docs/help-center/41-benchmarks-what-good-looks-like.md:32 | Vectorae | A | docs prose | LOW |
| docs/help-center/41-benchmarks-what-good-looks-like.md:32 | Vectorae | A | docs prose | LOW |
| docs/help-center/41-benchmarks-what-good-looks-like.md:34 | Vectorae | A-slug | help-center heading: display text, but slugify(heading) forms the chunk id persisted in chat_messages.faq_ids and LEGACY_FAQ_ALIASES | HIGH |
| docs/help-center/41-benchmarks-what-good-looks-like.md:36 | Vectorae | A | docs prose | LOW |
| docs/help-center/41-benchmarks-what-good-looks-like.md:38 | Vectorae | A | docs prose | LOW |
| docs/help-center/41-benchmarks-what-good-looks-like.md:38 | Vectorae | A | docs prose | LOW |
| docs/help-center/41-benchmarks-what-good-looks-like.md:44 | Vectorae | A-slug | help-center heading: display text, but slugify(heading) forms the chunk id persisted in chat_messages.faq_ids and LEGACY_FAQ_ALIASES | HIGH |
| docs/help-center/41-benchmarks-what-good-looks-like.md:55 | Vectorae | A | docs prose | LOW |
| docs/help-center/41-benchmarks-what-good-looks-like.md:59 | Vectorae | A | docs prose | LOW |
| docs/help-center/41-benchmarks-what-good-looks-like.md:67 | Vectorae | A | docs prose | LOW |
| docs/help-center/41-benchmarks-what-good-looks-like.md:71 | Vectorae | A-slug | help-center heading: display text, but slugify(heading) forms the chunk id persisted in chat_messages.faq_ids and LEGACY_FAQ_ALIASES | HIGH |
| docs/help-center/41-benchmarks-what-good-looks-like.md:73 | Vectorae | A | docs prose | LOW |
| docs/help-center/41-benchmarks-what-good-looks-like.md:80 | Vectorae | A-slug | help-center heading: display text, but slugify(heading) forms the chunk id persisted in chat_messages.faq_ids and LEGACY_FAQ_ALIASES | HIGH |
| docs/help-center/41-benchmarks-what-good-looks-like.md:82 | Vectorae | A | docs prose | LOW |
| docs/help-center/41-benchmarks-what-good-looks-like.md:88 | Vectorae | A | docs prose | LOW |
| docs/help-center/42-security-faq-for-buyers.md:32 | Vectorae | A | docs prose | LOW |
| docs/help-center/42-security-faq-for-buyers.md:34 | Vectorae | A-slug | help-center heading: display text, but slugify(heading) forms the chunk id persisted in chat_messages.faq_ids and LEGACY_FAQ_ALIASES | HIGH |
| docs/help-center/42-security-faq-for-buyers.md:36 | Vectorae | A | docs prose | LOW |
| docs/help-center/42-security-faq-for-buyers.md:42 | Vectorae | A | docs prose | LOW |
| docs/help-center/42-security-faq-for-buyers.md:42 | Vectorae | A | docs prose | LOW |
| docs/help-center/42-security-faq-for-buyers.md:50 | Vectorae | A-slug | help-center heading: display text, but slugify(heading) forms the chunk id persisted in chat_messages.faq_ids and LEGACY_FAQ_ALIASES | HIGH |
| docs/help-center/42-security-faq-for-buyers.md:54 | LeadPilot | B | webhook header name | HIGH |
| docs/help-center/42-security-faq-for-buyers.md:55 | LeadPilot | B | webhook header name | HIGH |
| docs/help-center/42-security-faq-for-buyers.md:56 | LeadPilot | B | webhook signature header name (customer verifiers depend on it) | HIGH |
| docs/help-center/42-security-faq-for-buyers.md:58 | ClientHunter | B | legacy webhook signature header name | HIGH |
| docs/help-center/42-security-faq-for-buyers.md:62 | Vectorae | A-slug | help-center heading: display text, but slugify(heading) forms the chunk id persisted in chat_messages.faq_ids and LEGACY_FAQ_ALIASES | HIGH |
| docs/help-center/42-security-faq-for-buyers.md:64 | Vectorae | A | docs prose | LOW |
| docs/help-center/42-security-faq-for-buyers.md:77 | Vectorae | A | docs prose | LOW |
| docs/help-center/42-security-faq-for-buyers.md:89 | Vectorae | A-slug | help-center heading: display text, but slugify(heading) forms the chunk id persisted in chat_messages.faq_ids and LEGACY_FAQ_ALIASES | HIGH |
| docs/help-center/42-security-faq-for-buyers.md:95 | Vectorae | A-slug | help-center heading: display text, but slugify(heading) forms the chunk id persisted in chat_messages.faq_ids and LEGACY_FAQ_ALIASES | HIGH |
| docs/help-center/42-security-faq-for-buyers.md:99 | Vectorae | A | docs prose | LOW |
| docs/help-center/43-data-processing-and-subprocessors.md:51 | Vectorae | A | docs prose | LOW |
| docs/help-center/43-data-processing-and-subprocessors.md:51 | Vectorae | A | docs prose | LOW |
| docs/help-center/43-data-processing-and-subprocessors.md:55 | Vectorae | A | docs prose | LOW |
| docs/help-center/43-data-processing-and-subprocessors.md:59 | Vectorae | A | docs prose | LOW |
| docs/help-center/43-data-processing-and-subprocessors.md:74 | Vectorae | A-slug | help-center heading: display text, but slugify(heading) forms the chunk id persisted in chat_messages.faq_ids and LEGACY_FAQ_ALIASES | HIGH |
| docs/help-center/43-data-processing-and-subprocessors.md:114 | Vectorae | A | docs prose | LOW |
| docs/help-center/43-data-processing-and-subprocessors.md:120 | Vectorae | A-slug | help-center heading: display text, but slugify(heading) forms the chunk id persisted in chat_messages.faq_ids and LEGACY_FAQ_ALIASES | HIGH |
| docs/help-center/43-data-processing-and-subprocessors.md:124 | Vectorae | A | docs prose | LOW |
| docs/help-center/43-data-processing-and-subprocessors.md:126 | Vectorae | A-slug | help-center heading: display text, but slugify(heading) forms the chunk id persisted in chat_messages.faq_ids and LEGACY_FAQ_ALIASES | HIGH |
| docs/help-center/43-data-processing-and-subprocessors.md:134 | Vectorae | A | docs prose | LOW |
| docs/help-center/44-learn-tab-and-tutorials.md:26 | Vectorae | A | docs prose | LOW |
| docs/help-center/44-learn-tab-and-tutorials.md:30 | Vectorae | A | docs prose | LOW |
| docs/help-center/44-learn-tab-and-tutorials.md:34 | Vectorae | A | docs prose | LOW |
| docs/help-center/44-learn-tab-and-tutorials.md:34 | Vectorae | A | docs prose | LOW |
| docs/help-center/44-learn-tab-and-tutorials.md:42 | Vectorae | A | docs prose | LOW |
| docs/help-center/44-learn-tab-and-tutorials.md:48 | Vectorae | A | docs prose | LOW |
| docs/help-center/44-learn-tab-and-tutorials.md:48 | Vectorae | A | docs prose | LOW |
| docs/help-center/44-learn-tab-and-tutorials.md:48 | Vectorae | A | docs prose | LOW |
| docs/help-center/44-learn-tab-and-tutorials.md:57 | Vectorae | A | docs prose | LOW |
| docs/help-center/44-learn-tab-and-tutorials.md:63 | Vectorae | A | docs prose | LOW |
| docs/help-center/44-learn-tab-and-tutorials.md:66 | Vectorae | A | docs prose | LOW |
| docs/setup/environment-variables.md:3 | Vectorae | A | docs prose | LOW |
| docs/setup/environment-variables.md:27 | Vectorae | A | documented default of EMAIL_FROM_NAME (From display name of platform mail); config value lives in app/config.py | MED |
| docs/setup/environment-variables.md:195 | Vectorae | A | documented default of EMAIL_FROM_NAME (From display name of platform mail); config value lives in app/config.py | MED |

## 3. File / directory names containing a variant

| path | variant | class | reason | risk |
|---|---|---|---|---|
| docs/help-center/01-what-is-leadpilot.md | LeadPilot | B | Article file name = article id `what-is-leadpilot` = public URL slug `/help/what-is-leadpilot/` (frontend/src/lib/content/helpCenter.ts reads `id:`), = chunk-id prefix persisted in `chat_messages.faq_ids`, hard-coded in app/services/help_center.py:182-185 (LEGACY_FAQ_ALIASES) and app/services/support_kb.py:76; linked from 00-index.md:13, 02:115, 26:98, 28:119; copied to frontend/src/content/help-center/ | HIGH |
| docs/features/vectorae-agents.md | Vectorae | B (low) | Doc path cited from code comments and docs: Dockerfile:16, .github/workflows/verify.yml:232, alembic/versions/0092_agent_runs.py:3 (sealed migration, never edit), app/agents/__init__.py:2, app/api/agents.py:12, app/services/account_erasure.py:166, docs/api-reference.md:677. Renaming leaves dangling references, including one in an immutable migration | LOW |

## 4. Generated or git-ignored files

- No git-ignored or untracked files under the scoped paths (`git status --ignored --porcelain` empty).
- **Generated copy outside this area:** `frontend/src/content/help-center/NN-*.md` (44 tracked files) is a copy of `docs/help-center/` made by `node frontend/scripts/help/sync_help_center.mjs` (run from `frontend/`); `frontend/src/tests/helpCenterCopy.test.ts` fails on drift. Edit `docs/help-center/` then re-run the sync; do not inventory the copy separately. `00-index.md` and `_synonyms.yaml` are not copied.
- `docs/help-center/` is also baked into the API image (Dockerfile:77-81, `HELP_CENTER_DIR=/code/docs/help-center`; `.dockerignore:103-105`) and indexed at runtime by app/services/help_center.py for the Help AI. It is runtime content, not just docs.

## 5. Surprises / things a rename must not miss

1. **Help-center headings are identifiers in disguise (58 A-slug rows).** `slugify(heading)` (app/services/help_center.py:271) builds chunk ids `article-id#heading-slug`; those ids are stored on support chat rows (`faq_ids`, resolved at read time by `sources_for`) and hard-coded in `LEGACY_FAQ_ALIASES` (help_center.py:182-190: `#what-does-vectorae-do-start-to-finish`, `#who-is-vectorae-designed-for`, `#what-does-vectorae-learn-from`, `#what-does-vectorae-store-about-me`). Renaming "Vectorae" in a heading silently orphans stored citations; tests/help_center/test_corpus.py fails for the alias map but not for already-stored rows. Needs an alias entry per renamed heading. The BM25 ranker also has brand-specific logic ("is_vectorae", "=what_is_vectorae", "is_leadpilot") in help_center.py:564-567, 753 — out of area, flag for the code inventory.
2. **`what-is-leadpilot` is a public URL, a stored id and a filename at once** (see §3). Keep the id, change only the title/body.
3. **`_leadpilot-verify.<domain>` DNS TXT record** (docs/features/workspaces.md:59; code app/services/workspaces.py:33) — customers have published this record in their own DNS. Renaming breaks verification for existing workspaces unless both prefixes are accepted.
4. **Android keystore alias `clienthunter`** (docs/SIGNING.md, docs/DEPLOY.md) is baked into the existing upload/release key; it cannot be renamed without a Play key reset. `com.clienthunter.app` (DEPLOY, FIREBASE, PLAY_STORE, help-center 26:39) is permanent once published. The help-center even tells users the app id is `com.clienthunter.app` while "its name on the phone is Vectorae" — the display name changes, the id must not.
5. **Webhook headers**: both `X-LeadPilot-*` and a legacy `X-ClientHunter-Signature` are documented as live (help-center 37:71/118, 42:58). Customer verification code depends on them. `source: "leadpilot_calendar"` is a payload enum value (api-reference:176, help-center 37:75).
6. **OAuth scopes `leadpilot:read`/`leadpilot:write`** appear on the connector consent page and in issued tokens (connectors/README:99-100, features/mcp-connector.md:26-27,69,109,111). B, and also user-visible — rename needs dual-acceptance.
7. **Celery task names `leadpilot.*`** documented in features (autopilot-launch, email-network, f04, f06, f10): messages already queued or scheduled by beat reference them.
8. **Tutorial slug `getting-started-with-leadpilot`** is explicitly marked `# <- DO NOT CHANGE` (features/tutorial-section.md:110; code app/services/tutorials.py:97); its title next to it is A.
9. **Account export**: download file name `leadpilot-account-export-<date>.json` (help-center 21:81; app/api/account_data.py:106) and the in-file `"format": "leadpilot-account-export"` (app/services/account_export.py:317) — the format id is what a re-import tool would key on; treat as B.
10. **User-Agent `Vectorae/1.0 quickstart`** (features/f06-quickstart.md:199; app/services/safe_fetch.py:58, plus geolocation.py:74 and market_intel.py:83 out of area) — seen by third-party sites; changing is safe but is an external-facing string.
11. **`EMAIL_FROM_NAME` default `Vectorae`** (setup/environment-variables.md:27,195; features/email-verification.md:84) is the display name on every platform email; the doc mirrors app/config.py and render.yaml, which must change together. Classed A (MED).
12. **Stale brands in shipping docs.** DEPLOY, SIGNING, PLAY_STORE_CHECKLIST, STORE_ASSETS, FIREBASE_SETUP_CHECKLIST and the api-reference title still say "ClientHunter Enterprise" and point to `app.clienthunter.com` / `api.clienthunter.app` (not the live domain, which is calendarharvest.com per CLAUDE.md). The Play Store app name/description in STORE_ASSETS (C) would publish the old brand.
13. **Privacy policy (all C)** names the service "ClientHunter Enterprise, also sold as Vectorae" and the operator "Calendarharvest"; legal entity naming needs founder/legal decision, not a find-replace.
14. **Connector checklist** (connectors/README:38, 159-164): the name users enter for the custom connector and the directory submission are third-party listing surfaces (C). Plugin/marketplace ids `Rmasood1122/LeadPilot`, `leadpilot@leadpilot`, `plugins/leadpilot/`, skill `leadpilot-outbound` are B (installed users reference them).
15. No customer-voice DEFECT found in this area: the only outreach-adjacent copy (reengagement, reply copilot, daily-send-approval) describes what the product does; it does not show message templates that inject a product name.

# Part 5 — Brand inventory: docs/ (program, audits, other docs), root *.md, status-page/, reports/

_Source: subagent sweep, file `brand-docs-program-root.md`._

Read-only sweep of git-tracked files at HEAD `7872f9c` (2026-10-20). No repository file was modified.

**Scope.** Everything under `docs/` except docs/help-center, docs/features, docs/connectors, docs/api, docs/api-reference.md, docs/setup, docs/backup, docs/PRIVACY_POLICY.md, docs/PLAY_STORE_CHECKLIST.md, docs/STORE_ASSETS.md, docs/SIGNING.md, docs/FIREBASE_SETUP_CHECKLIST.md, docs/ICP.md, docs/DEPLOY.md (another agent covers those), plus every root-level `*.md`, `status-page/` and `reports/`.

**Regex** (case-insensitive, over contents): `lead[ _.-]?pilot|client[ _.-]?hunter|vectorae|lpk_|calendarharvest`. `git grep -c` gives **1,435 matching lines in 103 files**; `grep -o` gives **1,908 occurrences** (1,686 inventoried below + 222 `calendarharvest` domain uses tallied separately in section 6).

## 1. Summary

### Counts per class (occurrences)

| Class | Occurrences | Meaning here |
|---|---|---|
| A | 951 | display text. Sub-tags: A-current 465, A-historical 474, A-test 8, A-comment 4 |
| B | 438 | identifier an external system/person depends on |
| C | 198 | needs a human: company/site name "Calendarharvest" (product-name use), our third-party listings, store/OAuth app names, legal footer, logo |
| DEFECT | 0 | no customer-voice text in this area injects a product name (one adjacent finding outside this area: see section 5) |
| EXCL | 99 | **not our brand**: LeadPilot AB, Twenty Over Ten "Lead Pilot", other "LeadPilot" products. Must NOT be renamed (extra category, added because a blind find-replace would corrupt the disambiguation copy) |
| (calendarharvest domain) | 222 | domain use (`calendarharvest.com`, `status.`/`www.`/`api.`/`noreply@`); out of scope per the brief, tallied per file in section 6 |

**A-historical vs A-current.** A-historical = the text records a past event, a dated evidence log, a quoted checker verdict, an audit or a session handoff (renaming it would falsify the record): docs/program/BASELINE.md, PROGRESS.md, DECISIONS.md, STAR_PROMPT.md, status.json, fixes/, plans/, help-center-factcheck/eval/discoveries, ai-visibility BASELINE/NOTES/REPORT/state/questions/research, docs/FULL_PRODUCT_AUDIT, VERIFICATION_REPORT, FINDINGS_REGISTER, PREVIOUS_EVALUATION_RECONCILIATION, BRANCH_COVERAGE, docs/README_M7_*, reports/, root CLAUDE_CODE_HANDOFF, CHANGES, INTEGRATION_NOTES, PROGRESS, BUILD_DECISIONS. Everything else in A is A-current (living runbooks, READMEs, specs, publishable GEO content drafts, status-page UI). A-test = a test/checker asserting a display string; A-comment = code comment.

### Counts per variant (occurrences, by class)

| Variant | Total | A | B | C | EXCL |
|---|---|---|---|---|---|
| Vectorae | 933 | 914 | 18 | 1 | 0 |
| leadpilot | 270 | 2 | 210 | 32 | 26 |
| LeadPilot | 164 | 9 | 83 | 7 | 65 |
| Calendarharvest(name) | 155 | 0 | 0 | 155 | 0 |
| clienthunter | 82 | 0 | 82 | 0 | 0 |
| ClientHunter | 32 | 21 | 9 | 2 | 0 |
| LEADPILOT | 17 | 0 | 17 | 0 | 0 |
| lpk_ | 14 | 0 | 14 | 0 | 0 |
| Lead Pilot | 9 | 1 | 0 | 0 | 8 |
| lead-pilot | 5 | 0 | 5 | 0 | 0 |
| VECTORAE | 4 | 3 | 0 | 1 | 0 |
| vectorae | 1 | 1 | 0 | 0 | 0 |

Not found in this area: `lead_pilot`, `Client Hunter`, `client-hunter`, `client_hunter` (as words), `CLIENTHUNTER`, "LeadPilot Enterprises" as a legal entity (only the YouTube handle `@LeadPilotEnterprise`). "LeadsPilot" (with an s) is not matched by the regex; it appears in ai-visibility docs as the founders' GetApp/Capterra listing name (C, not counted).

### Files: 103 files with at least one occurrence

| File | A | B | C | EXCL | domain |
|---|---|---|---|---|---|
| docs/program/help-center-factcheck.md | 307 | 59 | 0 | 0 | 3 |
| docs/program/ai-visibility/REPORT.md | 21 | 1 | 25 | 2 | 33 |
| docs/program/ai-visibility/BASELINE.md | 21 | 7 | 6 | 0 | 41 |
| docs/program/ai-visibility/geo/content/faq_library.md | 58 | 0 | 4 | 4 | 4 |
| docs/program/ai-visibility/geo/technical/schema_markup.md | 23 | 0 | 17 | 3 | 18 |
| docs/program/ai-visibility/geo/content/definitions/leadpilot_use_cases.md | 51 | 0 | 1 | 0 | 0 |
| docs/program/STATUS_PAGE.md | 8 | 21 | 1 | 0 | 20 |
| CLAUDE_CODE_HANDOFF.md | 10 | 38 | 2 | 0 | 0 |
| docs/program/ai-visibility/SPEC.md | 18 | 1 | 10 | 9 | 10 |
| docs/program/ai-visibility/geo/technical/crawler_access_strategy.md | 12 | 10 | 5 | 4 | 17 |
| docs/program/ai-visibility/geo/research/competitor_analysis.md | 27 | 0 | 8 | 11 | 0 |
| docs/program/ai-visibility/geo/entity_card.md | 27 | 2 | 7 | 7 | 2 |
| docs/program/ai-visibility/geo/authority/citation_acquisition_plan.md | 15 | 0 | 17 | 6 | 5 |
| docs/program/ai-visibility/geo/content/definitions/what_is_leadpilot.md | 22 | 1 | 7 | 5 | 3 |
| docs/program/ai-visibility/geo/technical/site_architecture.md | 10 | 24 | 0 | 0 | 0 |
| docs/program/ai-visibility/geo/monitoring/ai_mention_tracker.md | 10 | 0 | 4 | 15 | 4 |
| docs/program/ai-visibility/NOTES.md | 8 | 1 | 19 | 1 | 2 |
| docs/program/ai-visibility/geo/state.md | 10 | 7 | 4 | 7 | 3 |
| docs/program/ai-visibility/geo/research/query_library.md | 9 | 18 | 1 | 1 | 1 |
| docs/program/ai-visibility/geo/content/comparisons/leadpilot_vs_apollo.md | 17 | 2 | 2 | 2 | 2 |
| docs/program/ai-visibility/geo/questions.md | 8 | 1 | 10 | 4 | 2 |
| docs/program/ai-visibility/PROMPT_TRACKER.md | 9 | 0 | 7 | 5 | 3 |
| BACKUP.md | 2 | 22 | 0 | 0 | 0 |
| docs/program/ai-visibility/geo/tools/geo_audit.py | 7 | 8 | 6 | 0 | 0 |
| docs/program/ai-visibility/geo/content/comparisons/leadpilot_vs_instantly.md | 13 | 1 | 2 | 2 | 2 |
| docs/program/BASELINE.md | 1 | 18 | 0 | 0 | 0 |
| docs/program/ai-visibility/geo/content/comparison_matrix.md | 17 | 0 | 2 | 0 | 0 |
| docs/program/ai-visibility/geo/content/comparisons/leadpilot_vs_artisan.md | 12 | 1 | 2 | 2 | 2 |
| docs/program/ai-visibility/geo/content/comparisons/leadpilot_vs_clay.md | 12 | 1 | 2 | 2 | 2 |
| docs/program/ai-visibility/geo/content/comparisons/leadpilot_vs_smartlead.md | 12 | 1 | 2 | 2 | 2 |
| DEPLOY_RENDER_FREE.md | 2 | 17 | 0 | 0 | 0 |
| docs/program/STAR_PROMPT.md | 7 | 5 | 0 | 0 | 6 |
| docs/program/plans/help-ai-v2-01-new-questions.md | 18 | 0 | 0 | 0 | 0 |
| docs/program/ai-visibility/geo/platforms/chatgpt_bing_playbook.md | 10 | 0 | 5 | 0 | 2 |
| docs/program/status.json | 1 | 14 | 0 | 0 | 2 |
| docs/program/ai-visibility/geo/authority/reddit_strategy.md | 15 | 0 | 0 | 0 | 0 |
| docs/program/ai-visibility/geo/authority/syndication_map.md | 2 | 12 | 0 | 0 | 0 |
| docs/program/ai-visibility/geo/platforms/claude_playbook.md | 8 | 1 | 1 | 1 | 3 |
| docs/program/ai-visibility/geo/platforms/perplexity_playbook.md | 9 | 0 | 3 | 1 | 0 |
| status-page/lib/config.ts | 2 | 9 | 0 | 0 | 2 |
| docs/program/ai-visibility/geo/README.md | 6 | 2 | 2 | 1 | 1 |
| docs/program/ai-visibility/geo/platforms/gemini_playbook.md | 7 | 0 | 2 | 1 | 2 |
| FEATURES.md | 10 | 2 | 0 | 0 | 0 |
| docs/FULL_PRODUCT_AUDIT.md | 5 | 6 | 0 | 0 | 0 |
| docs/program/GATES.md | 1 | 10 | 0 | 0 | 0 |
| docs/program/ai-visibility/geo/platforms/emerging_ai_playbook.md | 4 | 0 | 3 | 1 | 3 |
| docs/program/fixes/gaps-sweep-2.md | 0 | 11 | 0 | 0 | 0 |
| reports/LP-T-004-launch-checklist-decomposition.md | 0 | 9 | 1 | 0 | 1 |
| docs/program/DECISIONS.md | 1 | 4 | 1 | 0 | 4 |
| docs/program/plans/connector-00-recon.md | 2 | 6 | 0 | 0 | 2 |
| docs/program/ai-visibility/geo/content/statistics_and_proof.md | 7 | 0 | 1 | 0 | 1 |
| docs/program/plans/help-ai-v2-00-recon.md | 1 | 8 | 0 | 0 | 0 |
| docs/VERIFICATION_REPORT.md | 1 | 7 | 0 | 0 | 0 |
| docs/program/ai-visibility/geo/positioning/niche_statement.md | 4 | 2 | 2 | 0 | 0 |
| README.md | 1 | 7 | 0 | 0 | 0 |
| docs/program/fixes/platform-gaps.md | 3 | 4 | 0 | 0 | 0 |
| docs/PRODUCTION_READINESS.md | 2 | 0 | 0 | 0 | 3 |
| docs/README_M7_COMPLETE.md | 0 | 5 | 0 | 0 | 0 |
| status-page/components/SiteChrome.tsx | 3 | 0 | 0 | 0 | 2 |
| status-page/tests/sources.test.ts | 1 | 4 | 0 | 0 | 0 |
| CHANGES.md | 1 | 4 | 0 | 0 | 0 |
| LAUNCH_CHECKLIST.md | 1 | 4 | 0 | 0 | 0 |
| SYSTEM_HANDOFF.md | 2 | 3 | 0 | 0 | 0 |
| docs/README_M7_CHUNKS_2_3.md | 1 | 3 | 0 | 0 | 0 |
| docs/program/PROGRESS.md | 0 | 4 | 0 | 0 | 0 |
| status-page/lib/snapshot.ts | 4 | 0 | 0 | 0 | 0 |
| CLAUDE.md | 2 | 0 | 1 | 0 | 1 |
| DEPLOY_RAILWAY.md | 0 | 4 | 0 | 0 | 0 |
| docs/NEXT_STEPS.md | 1 | 1 | 0 | 0 | 1 |
| docs/outreach_tools.md | 3 | 0 | 0 | 0 | 0 |
| docs/program/help-center-eval.md | 2 | 1 | 0 | 0 | 0 |
| docs/program/plans/connector-05-verification.md | 0 | 2 | 0 | 0 | 1 |
| docs/program/plans/phase1-01-integration-repair.md | 0 | 3 | 0 | 0 | 0 |
| status-page/app/layout.tsx | 3 | 0 | 0 | 0 | 0 |
| status-page/lib/backend.ts | 1 | 2 | 0 | 0 | 0 |
| status-page/lib/feeds.ts | 3 | 0 | 0 | 0 | 0 |
| status-page/package.json | 1 | 1 | 0 | 0 | 1 |
| status-page/tests/snapshot.test.ts | 0 | 3 | 0 | 0 | 0 |
| DEPLOY.md | 1 | 2 | 0 | 0 | 0 |
| INTEGRATION_NOTES.md | 1 | 2 | 0 | 0 | 0 |
| docs/FINDINGS_REGISTER.md | 1 | 1 | 0 | 0 | 0 |
| docs/architecture.md | 1 | 1 | 0 | 0 | 0 |
| docs/program/ai-visibility/geo/research/ai_search_mechanics_factcheck.md | 0 | 0 | 2 | 0 | 0 |
| status-page/package-lock.json | 0 | 2 | 0 | 0 | 0 |
| PROGRESS.md | 2 | 0 | 0 | 0 | 0 |
| SECURITY.md | 1 | 0 | 1 | 0 | 0 |
| docs/BRANCH_COVERAGE.md | 1 | 0 | 0 | 0 | 0 |
| docs/PREVIOUS_EVALUATION_RECONCILIATION.md | 1 | 0 | 0 | 0 | 0 |
| docs/README_M7_MOBILE_SECTION.md | 0 | 1 | 0 | 0 | 0 |
| docs/compliance.md | 1 | 0 | 0 | 0 | 0 |
| docs/learning-loop.md | 1 | 0 | 0 | 0 | 0 |
| docs/program/help-center-discoveries.md | 1 | 0 | 0 | 0 | 0 |
| docs/program/plans/p0-5b-meter-every-call.md | 0 | 1 | 0 | 0 | 0 |
| docs/program/plans/p0-d-enf-signup-switch.md | 1 | 0 | 0 | 0 | 0 |
| docs/program/plans/phase1-01b-pd1-webhook-schema.md | 0 | 1 | 0 | 0 | 0 |
| reports/LP-T-002-tenancy-authz-audit.md | 0 | 1 | 0 | 0 | 0 |
| status-page/app/page.tsx | 1 | 0 | 0 | 0 | 0 |
| status-page/lib/uptimerobot.ts | 1 | 0 | 0 | 0 | 0 |
| status-page/scripts/drill.ts | 0 | 1 | 0 | 0 | 0 |
| BUILD_DECISIONS.md | 1 | 0 | 0 | 0 | 0 |
| status-page/incidents/README.md | 0 | 0 | 0 | 0 | 1 |
| status-page/next.config.mjs | 0 | 0 | 0 | 0 | 1 |
| status-page/tests/feeds.test.ts | 0 | 0 | 0 | 0 | 1 |

## 2. Occurrence table

One row per line per (variant, class, reason); `×n` = n occurrences on that line. B, C and EXCL occurrences are never collapsed. A rows are collapsed per file when one (class, variant, reason) group exceeds 15 occurrences; the collapsed row lists every line.

| path:line | variant | class | reason | risk |
|---|---|---|---|---|
| BACKUP.md:1 | ClientHunter | A-current | old product/repo name in prose/title | low |
| BACKUP.md:24 | clienthunter | B | ops file/dir/repo path name (backup script, backup dir, local checkout, secrets file, placeholder repo URL) | existing paths, cron jobs and scripts keep the old name |
| BACKUP.md:29 | ClientHunter | A-current | old product/repo name in prose/title | low |
| BACKUP.md:30 | clienthunter | B | ops file/dir/repo path name (backup script, backup dir, local checkout, secrets file, placeholder repo URL) | existing paths, cron jobs and scripts keep the old name |
| BACKUP.md:34 | clienthunter | B | ops file/dir/repo path name (backup script, backup dir, local checkout, secrets file, placeholder repo URL) | existing paths, cron jobs and scripts keep the old name |
| BACKUP.md:35 | clienthunter | B | Postgres DB/user/container name | existing databases/containers keep the name |
| BACKUP.md:36 | clienthunter | B | Postgres DB/user/container name | existing databases/containers keep the name |
| BACKUP.md:37 | clienthunter | B | Postgres DB/user/container name | existing databases/containers keep the name |
| BACKUP.md:61 | clienthunter | B | ops file/dir/repo path name (backup script, backup dir, local checkout, secrets file, placeholder repo URL) | existing paths, cron jobs and scripts keep the old name |
| BACKUP.md:62 | clienthunter | B | ops file/dir/repo path name (backup script, backup dir, local checkout, secrets file, placeholder repo URL) | existing paths, cron jobs and scripts keep the old name |
| BACKUP.md:68 | clienthunter | B | ops file/dir/repo path name (backup script, backup dir, local checkout, secrets file, placeholder repo URL) | existing paths, cron jobs and scripts keep the old name |
| BACKUP.md:70 | clienthunter | B | ops file/dir/repo path name (backup script, backup dir, local checkout, secrets file, placeholder repo URL) | existing paths, cron jobs and scripts keep the old name |
| BACKUP.md:70 | clienthunter | B | ops file/dir/repo path name (backup script, backup dir, local checkout, secrets file, placeholder repo URL) | existing paths, cron jobs and scripts keep the old name |
| BACKUP.md:84 | clienthunter | B | Postgres DB/user/container name | existing databases/containers keep the name |
| BACKUP.md:84 | clienthunter | B | Postgres DB/user/container name | existing databases/containers keep the name |
| BACKUP.md:84 | clienthunter | B | Postgres DB/user/container name | existing databases/containers keep the name |
| BACKUP.md:85 | clienthunter | B | Postgres DB/user/container name | existing databases/containers keep the name |
| BACKUP.md:85 | clienthunter | B | Postgres DB/user/container name | existing databases/containers keep the name |
| BACKUP.md:85 | clienthunter | B | Postgres DB/user/container name | existing databases/containers keep the name |
| BACKUP.md:88 | clienthunter | B | Postgres DB/user/container name | existing databases/containers keep the name |
| BACKUP.md:88 | clienthunter | B | Postgres DB/user/container name | existing databases/containers keep the name |
| BACKUP.md:88 | clienthunter | B | Postgres DB/user/container name | existing databases/containers keep the name |
| BACKUP.md:89 | clienthunter | B | ops file/dir/repo path name (backup script, backup dir, local checkout, secrets file, placeholder repo URL) | existing paths, cron jobs and scripts keep the old name |
| BACKUP.md:98 | clienthunter | B | ops file/dir/repo path name (backup script, backup dir, local checkout, secrets file, placeholder repo URL) | existing paths, cron jobs and scripts keep the old name |
| BUILD_DECISIONS.md:207 | Vectorae | A-historical | product name in prose/UI | renaming falsifies a dated record |
| CHANGES.md:1 | ClientHunter | A-historical | old product/repo name in prose/title | renaming falsifies a dated record |
| CHANGES.md:72 | clienthunter | B | PyPI package / CLI command name (sdk/) | published package + user scripts |
| CHANGES.md:96 | clienthunter | B | Android applicationId (com/io.clienthunter.app) | cannot change after Play publish |
| CHANGES.md:108 | clienthunter | B | PyPI package / CLI command name (sdk/) | published package + user scripts |
| CHANGES.md:112 | ClientHunter | B | Python exception class name ClientHunterError (SDK/app API) | SDK users catching it |
| CLAUDE.md:1 | Vectorae | A-current | product name in prose/UI | low |
| CLAUDE.md:1 | ClientHunter | A-current | old product/repo name in prose/title | low |
| CLAUDE.md:5 | LeadPilot | C | name of the external Claude Project holding governing records | external workspace rename (manual) |
| CLAUDE_CODE_HANDOFF.md:1 | ClientHunter | A-historical | old product/repo name in prose/title | renaming falsifies a dated record |
| CLAUDE_CODE_HANDOFF.md:26 | ClientHunter | A-historical | old product/repo name in prose/title | renaming falsifies a dated record |
| CLAUDE_CODE_HANDOFF.md:26 | Vectorae | A-historical | product name in prose/UI | renaming falsifies a dated record |
| CLAUDE_CODE_HANDOFF.md:189 | clienthunter | B | ops file/dir/repo path name (backup script, backup dir, local checkout, secrets file, placeholder repo URL) | existing paths, cron jobs and scripts keep the old name |
| CLAUDE_CODE_HANDOFF.md:229 | clienthunter | B | PyPI package / CLI command name (sdk/) | published package + user scripts |
| CLAUDE_CODE_HANDOFF.md:246 | clienthunter | B | Postgres DB/user/container name | existing databases/containers keep the name |
| CLAUDE_CODE_HANDOFF.md:288 | clienthunter | B | deep-link URL scheme (clienthunter://) | links in sent emails/push break |
| CLAUDE_CODE_HANDOFF.md:348 | clienthunter | B | PyPI package / CLI command name (sdk/) | published package + user scripts |
| CLAUDE_CODE_HANDOFF.md:429 | ClientHunter | B | Python exception class name ClientHunterError (SDK/app API) | SDK users catching it |
| CLAUDE_CODE_HANDOFF.md:590 | clienthunter | B | PyPI package / CLI command name (sdk/) | published package + user scripts |
| CLAUDE_CODE_HANDOFF.md:1044 | leadpilot | B | Postgres user/database name in a connection string | local/test DB identity |
| CLAUDE_CODE_HANDOFF.md:1053 | clienthunter | B | Postgres DB/user/container name | existing databases/containers keep the name |
| CLAUDE_CODE_HANDOFF.md:1075 | clienthunter | B | utm_source value in a test mock (seen by Calendly) | low |
| CLAUDE_CODE_HANDOFF.md:1438 | leadpilot | B | Celery task name prefix (leadpilot.*) | queued tasks/beat schedule/routing break |
| CLAUDE_CODE_HANDOFF.md:1438 | leadpilot | B | Celery task name prefix (leadpilot.*) | queued tasks/beat schedule/routing break |
| CLAUDE_CODE_HANDOFF.md:1438 | leadpilot | B | Celery task name prefix (leadpilot.*) | queued tasks/beat schedule/routing break |
| CLAUDE_CODE_HANDOFF.md:1439 | leadpilot | B | Celery task name prefix (leadpilot.*) | queued tasks/beat schedule/routing break |
| CLAUDE_CODE_HANDOFF.md:1441 | leadpilot | B | Celery task name prefix (leadpilot.*) | queued tasks/beat schedule/routing break |
| CLAUDE_CODE_HANDOFF.md:1707 | clienthunter | B | ops file/dir/repo path name (backup script, backup dir, local checkout, secrets file, placeholder repo URL) | existing paths, cron jobs and scripts keep the old name |
| CLAUDE_CODE_HANDOFF.md:1727 | leadpilot | B | domain leadpilot.com / api.leadpilot.com used as our deploy config | domain is owned by LeadPilot AB (see entity_card) - stale/wrong config |
| CLAUDE_CODE_HANDOFF.md:1727 | leadpilot | B | domain leadpilot.com / api.leadpilot.com used as our deploy config | domain is owned by LeadPilot AB (see entity_card) - stale/wrong config |
| CLAUDE_CODE_HANDOFF.md:1869 | leadpilot | B | domain leadpilot.com / api.leadpilot.com used as our deploy config | domain is owned by LeadPilot AB (see entity_card) - stale/wrong config |
| CLAUDE_CODE_HANDOFF.md:1881 | Vectorae | C | CAN-SPAM footer placeholder identity (legal footer text) | legal; same string is app/config.py default sender_identity |
| CLAUDE_CODE_HANDOFF.md:1897 | leadpilot | B | domain leadpilot.com / api.leadpilot.com used as our deploy config | domain is owned by LeadPilot AB (see entity_card) - stale/wrong config |
| CLAUDE_CODE_HANDOFF.md:1897 | leadpilot | B | domain leadpilot.com / api.leadpilot.com used as our deploy config | domain is owned by LeadPilot AB (see entity_card) - stale/wrong config |
| CLAUDE_CODE_HANDOFF.md:1898 | leadpilot | B | domain leadpilot.com / api.leadpilot.com used as our deploy config | domain is owned by LeadPilot AB (see entity_card) - stale/wrong config |
| CLAUDE_CODE_HANDOFF.md:1899 | leadpilot | B | domain leadpilot.com / api.leadpilot.com used as our deploy config | domain is owned by LeadPilot AB (see entity_card) - stale/wrong config |
| CLAUDE_CODE_HANDOFF.md:1900 | leadpilot | B | domain leadpilot.com / api.leadpilot.com used as our deploy config | domain is owned by LeadPilot AB (see entity_card) - stale/wrong config |
| CLAUDE_CODE_HANDOFF.md:1901 | leadpilot | B | domain leadpilot.com / api.leadpilot.com used as our deploy config | domain is owned by LeadPilot AB (see entity_card) - stale/wrong config |
| CLAUDE_CODE_HANDOFF.md:1902 | leadpilot | B | domain leadpilot.com / api.leadpilot.com used as our deploy config | domain is owned by LeadPilot AB (see entity_card) - stale/wrong config |
| CLAUDE_CODE_HANDOFF.md:1937 | leadpilot | B | domain leadpilot.com / api.leadpilot.com used as our deploy config | domain is owned by LeadPilot AB (see entity_card) - stale/wrong config |
| CLAUDE_CODE_HANDOFF.md:1937 | leadpilot | B | domain leadpilot.com / api.leadpilot.com used as our deploy config | domain is owned by LeadPilot AB (see entity_card) - stale/wrong config |
| CLAUDE_CODE_HANDOFF.md:1943 | VECTORAE | C | describes the VECTORAE logo wordmark | logo asset decision |
| CLAUDE_CODE_HANDOFF.md:1974 | Vectorae | A-historical | product name in prose/UI | renaming falsifies a dated record |
| CLAUDE_CODE_HANDOFF.md:1999 | leadpilot | B | domain leadpilot.com / api.leadpilot.com used as our deploy config | domain is owned by LeadPilot AB (see entity_card) - stale/wrong config |
| CLAUDE_CODE_HANDOFF.md:2325 | ClientHunter | A-historical | old product/repo name in prose/title | renaming falsifies a dated record |
| CLAUDE_CODE_HANDOFF.md:2329 | ClientHunter | A-historical | old product/repo name in prose/title | renaming falsifies a dated record |
| CLAUDE_CODE_HANDOFF.md:2330 | Vectorae | A-historical | product name in prose/UI | renaming falsifies a dated record |
| CLAUDE_CODE_HANDOFF.md:2331 | clienthunter | B | Android applicationId (com/io.clienthunter.app) | cannot change after Play publish |
| CLAUDE_CODE_HANDOFF.md:2352 | clienthunter | B | domain/email on clienthunter.* (not owned/used in prod) | stale domain reference |
| CLAUDE_CODE_HANDOFF.md:2353 | clienthunter | B | domain/email on clienthunter.* (not owned/used in prod) | stale domain reference |
| CLAUDE_CODE_HANDOFF.md:2354 | leadpilot | B | domain leadpilot.com / api.leadpilot.com used as our deploy config | domain is owned by LeadPilot AB (see entity_card) - stale/wrong config |
| CLAUDE_CODE_HANDOFF.md:2376 | Vectorae | A-historical | product name in prose/UI | renaming falsifies a dated record |
| CLAUDE_CODE_HANDOFF.md:2377 | Vectorae | A-historical | product name in prose/UI | renaming falsifies a dated record |
| CLAUDE_CODE_HANDOFF.md:2378 | Vectorae | A-historical | product name in prose/UI | renaming falsifies a dated record |
| CLAUDE_CODE_HANDOFF.md:2591 | leadpilot | B | Celery task name prefix (leadpilot.*) | queued tasks/beat schedule/routing break |
| CLAUDE_CODE_HANDOFF.md:2653 | LeadPilot | B | GitHub repo name / URL | links + CI + Render/Vercel git hooks |
| CLAUDE_CODE_HANDOFF.md:2728 | leadpilot | B | Celery task name prefix (leadpilot.*) | queued tasks/beat schedule/routing break |
| CLAUDE_CODE_HANDOFF.md:2748 | ClientHunter | B | Redis key namespace (leftover keys) | cache keys |
| CLAUDE_CODE_HANDOFF.md:2821 | leadpilot | B | domain leadpilot.com / api.leadpilot.com used as our deploy config | domain is owned by LeadPilot AB (see entity_card) - stale/wrong config |
| DEPLOY.md:1 | ClientHunter | A-current | old product/repo name in prose/title | low |
| DEPLOY.md:190 | clienthunter | B | Postgres DB/user/container name | existing databases/containers keep the name |
| DEPLOY.md:190 | clienthunter | B | Postgres DB/user/container name | existing databases/containers keep the name |
| DEPLOY_RAILWAY.md:102 | leadpilot | B | domain leadpilot.com / api.leadpilot.com used as our deploy config | domain is owned by LeadPilot AB (see entity_card) - stale/wrong config |
| DEPLOY_RAILWAY.md:134 | leadpilot | B | Celery task name prefix (leadpilot.*) | queued tasks/beat schedule/routing break |
| DEPLOY_RAILWAY.md:146 | leadpilot | B | domain leadpilot.com / api.leadpilot.com used as our deploy config | domain is owned by LeadPilot AB (see entity_card) - stale/wrong config |
| DEPLOY_RAILWAY.md:167 | leadpilot | B | domain leadpilot.com / api.leadpilot.com used as our deploy config | domain is owned by LeadPilot AB (see entity_card) - stale/wrong config |
| DEPLOY_RENDER_FREE.md:112 | leadpilot | B | Render service name / onrender.com hostname | live service; renaming changes hostname |
| DEPLOY_RENDER_FREE.md:113 | leadpilot | B | Render service name / onrender.com hostname | live service; renaming changes hostname |
| DEPLOY_RENDER_FREE.md:138 | leadpilot | B | Render service name / onrender.com hostname | live service; renaming changes hostname |
| DEPLOY_RENDER_FREE.md:155 | leadpilot | B | Render service name / onrender.com hostname | live service; renaming changes hostname |
| DEPLOY_RENDER_FREE.md:207 | leadpilot | B | Celery task name prefix (leadpilot.*) | queued tasks/beat schedule/routing break |
| DEPLOY_RENDER_FREE.md:217 | leadpilot | B | Render service name / onrender.com hostname | live service; renaming changes hostname |
| DEPLOY_RENDER_FREE.md:245 | leadpilot | B | Render service name / onrender.com hostname | live service; renaming changes hostname |
| DEPLOY_RENDER_FREE.md:380 | leadpilot | B | Render service name / onrender.com hostname | live service; renaming changes hostname |
| DEPLOY_RENDER_FREE.md:408 | leadpilot | B | Render service name / onrender.com hostname | live service; renaming changes hostname |
| DEPLOY_RENDER_FREE.md:423 | leadpilot | B | Render service name / onrender.com hostname | live service; renaming changes hostname |
| DEPLOY_RENDER_FREE.md:425 | Vectorae | A-current | product name in prose/UI ×2 | low |
| DEPLOY_RENDER_FREE.md:438 | lead-pilot | B | Vercel deployment hostname | live URL |
| DEPLOY_RENDER_FREE.md:444 | leadpilot | B | Render service name / onrender.com hostname | live service; renaming changes hostname |
| DEPLOY_RENDER_FREE.md:444 | leadpilot | B | Render service name / onrender.com hostname | live service; renaming changes hostname |
| DEPLOY_RENDER_FREE.md:507 | leadpilot | B | Render service name / onrender.com hostname | live service; renaming changes hostname |
| DEPLOY_RENDER_FREE.md:523 | leadpilot | B | Render service name / onrender.com hostname | live service; renaming changes hostname |
| DEPLOY_RENDER_FREE.md:550 | leadpilot | B | Vercel deployment hostname | live URL |
| DEPLOY_RENDER_FREE.md:551 | lead-pilot | B | Vercel deployment hostname | live URL |
| FEATURES.md:1 | Vectorae | A-current | product name in prose/UI | low |
| FEATURES.md:3 | Vectorae | A-current | product name in prose/UI | low |
| FEATURES.md:3 | ClientHunter | A-current | old product/repo name in prose/title | low |
| FEATURES.md:47 | VECTORAE | A-current | product name in prose/UI | low |
| FEATURES.md:420 | leadpilot | B | Celery task name prefix (leadpilot.*) | queued tasks/beat schedule/routing break |
| FEATURES.md:594 | Vectorae | A-current | product name in prose/UI | low |
| FEATURES.md:651 | Vectorae | A-current | product name in prose/UI | low |
| FEATURES.md:759 | Vectorae | A-current | product name in prose/UI | low |
| FEATURES.md:1111 | Vectorae | A-current | product name in prose/UI | low |
| FEATURES.md:1271 | Vectorae | A-current | product name in prose/UI | low |
| FEATURES.md:1324 | LEADPILOT | B | environment variable name (LEADPILOT_*) | deploy env config (Vercel/Render) must change in lockstep |
| FEATURES.md:1342 | Vectorae | A-current | product name in prose/UI | low |
| INTEGRATION_NOTES.md:1 | ClientHunter | A-historical | old product/repo name in prose/title | renaming falsifies a dated record |
| INTEGRATION_NOTES.md:27 | leadpilot | B | archive file name of a past delivery | historical artifact name |
| INTEGRATION_NOTES.md:50 | ClientHunter | B | Python exception class name ClientHunterError (SDK/app API) | SDK users catching it |
| LAUNCH_CHECKLIST.md:1 | ClientHunter | A-current | old product/repo name in prose/title | low |
| LAUNCH_CHECKLIST.md:124 | clienthunter | B | PyPI package / CLI command name (sdk/) | published package + user scripts |
| LAUNCH_CHECKLIST.md:124 | clienthunter | B | PyPI package / CLI command name (sdk/) | published package + user scripts |
| LAUNCH_CHECKLIST.md:125 | clienthunter | B | PyPI package / CLI command name (sdk/) | published package + user scripts |
| LAUNCH_CHECKLIST.md:126 | clienthunter | B | PyPI package / CLI command name (sdk/) | published package + user scripts |
| PROGRESS.md:27 | Vectorae | A-historical | product name in prose/UI | renaming falsifies a dated record |
| PROGRESS.md:456 | Vectorae | A-historical | product name in prose/UI | renaming falsifies a dated record |
| README.md:1 | ClientHunter | A-current | old product/repo name in prose/title | low |
| README.md:54 | clienthunter | B | ops file/dir/repo path name (backup script, backup dir, local checkout, secrets file, placeholder repo URL) | existing paths, cron jobs and scripts keep the old name |
| README.md:55 | clienthunter | B | ops file/dir/repo path name (backup script, backup dir, local checkout, secrets file, placeholder repo URL) | existing paths, cron jobs and scripts keep the old name |
| README.md:93 | clienthunter | B | PyPI package / CLI command name (sdk/) | published package + user scripts |
| README.md:96 | clienthunter | B | PyPI package / CLI command name (sdk/) | published package + user scripts |
| README.md:99 | clienthunter | B | PyPI package / CLI command name (sdk/) | published package + user scripts |
| README.md:102 | clienthunter | B | PyPI package / CLI command name (sdk/) | published package + user scripts |
| README.md:105 | clienthunter | B | PyPI package / CLI command name (sdk/) | published package + user scripts |
| SECURITY.md:1 | ClientHunter | A-current | old product/repo name in prose/title | low |
| SECURITY.md:92 | ClientHunter | C | Google OAuth consent-screen app name users look for when revoking | third-party consent screen |
| SYSTEM_HANDOFF.md:1 | ClientHunter | A-current | old product/repo name in prose/title | low |
| SYSTEM_HANDOFF.md:47 | clienthunter | B | PyPI package / CLI command name (sdk/) | published package + user scripts |
| SYSTEM_HANDOFF.md:48 | clienthunter | B | PyPI package / CLI command name (sdk/) | published package + user scripts |
| SYSTEM_HANDOFF.md:122 | clienthunter | B | domain/email on clienthunter.* (not owned/used in prod) | stale domain reference |
| SYSTEM_HANDOFF.md:126 | Vectorae | A-current | product name in prose/UI | low |
| docs/BRANCH_COVERAGE.md:1 | Vectorae | A-historical | product name in prose/UI | renaming falsifies a dated record |
| docs/FINDINGS_REGISTER.md:1 | Vectorae | A-historical | product name in prose/UI | renaming falsifies a dated record |
| docs/FINDINGS_REGISTER.md:16 | lpk_ | B | API key prefix (issued keys start with it) | existing customer keys + Zapier/Make configs break |
| docs/FULL_PRODUCT_AUDIT.md:1 | Vectorae | A-historical | product name in prose/UI | renaming falsifies a dated record |
| docs/FULL_PRODUCT_AUDIT.md:3 | Vectorae | A-historical | product name in prose/UI | renaming falsifies a dated record |
| docs/FULL_PRODUCT_AUDIT.md:4 | ClientHunter | A-historical | old product/repo name in prose/title | renaming falsifies a dated record |
| docs/FULL_PRODUCT_AUDIT.md:11 | LeadPilot | B | GitHub repo name / URL | links + CI + Render/Vercel git hooks |
| docs/FULL_PRODUCT_AUDIT.md:20 | Vectorae | A-historical | product name in prose/UI | renaming falsifies a dated record |
| docs/FULL_PRODUCT_AUDIT.md:87 | Vectorae | A-historical | product name in prose/UI | renaming falsifies a dated record |
| docs/FULL_PRODUCT_AUDIT.md:101 | LeadPilot | B | GitHub repo name / URL | links + CI + Render/Vercel git hooks |
| docs/FULL_PRODUCT_AUDIT.md:186 | clienthunter | B | PyPI package / CLI command name (sdk/) | published package + user scripts |
| docs/FULL_PRODUCT_AUDIT.md:233 | clienthunter | B | PyPI package / CLI command name (sdk/) | published package + user scripts |
| docs/FULL_PRODUCT_AUDIT.md:283 | lpk_ | B | API key prefix (issued keys start with it) | existing customer keys + Zapier/Make configs break |
| docs/FULL_PRODUCT_AUDIT.md:340 | lpk_ | B | API key prefix (issued keys start with it) | existing customer keys + Zapier/Make configs break |
| docs/NEXT_STEPS.md:1 | Vectorae | A-current | product name in prose/UI | low |
| docs/NEXT_STEPS.md:38 | lpk_ | B | API key prefix (issued keys start with it) | existing customer keys + Zapier/Make configs break |
| docs/PREVIOUS_EVALUATION_RECONCILIATION.md:1 | Vectorae | A-historical | product name in prose/UI | renaming falsifies a dated record |
| docs/PRODUCTION_READINESS.md:1 | VECTORAE | A-current | product name in prose/UI | low |
| docs/PRODUCTION_READINESS.md:164 | Vectorae | A-current | product name in prose/UI | low |
| docs/README_M7_CHUNKS_2_3.md:37 | ClientHunter | A-historical | old product/repo name in prose/title | renaming falsifies a dated record |
| docs/README_M7_CHUNKS_2_3.md:41 | clienthunter | B | deep-link URL scheme (clienthunter://) | links in sent emails/push break |
| docs/README_M7_CHUNKS_2_3.md:41 | clienthunter | B | Android applicationId (com/io.clienthunter.app) | cannot change after Play publish |
| docs/README_M7_CHUNKS_2_3.md:65 | clienthunter | B | Android applicationId (com/io.clienthunter.app) | cannot change after Play publish |
| docs/README_M7_COMPLETE.md:12 | clienthunter | B | PyPI package / CLI command name (sdk/) | published package + user scripts |
| docs/README_M7_COMPLETE.md:20 | clienthunter | B | Android applicationId (com/io.clienthunter.app) | cannot change after Play publish |
| docs/README_M7_COMPLETE.md:24 | clienthunter | B | deep-link URL scheme (clienthunter://) | links in sent emails/push break |
| docs/README_M7_COMPLETE.md:24 | clienthunter | B | domain/email on clienthunter.* (not owned/used in prod) | stale domain reference |
| docs/README_M7_COMPLETE.md:88 | clienthunter | B | PyPI package / CLI command name (sdk/) | published package + user scripts |
| docs/README_M7_MOBILE_SECTION.md:100 | clienthunter | B | domain/email on clienthunter.* (not owned/used in prod) | stale domain reference |
| docs/VERIFICATION_REPORT.md:1 | Vectorae | A-historical | product name in prose/UI | renaming falsifies a dated record |
| docs/VERIFICATION_REPORT.md:120 | LeadPilot | B | GitHub repo name / URL | links + CI + Render/Vercel git hooks |
| docs/VERIFICATION_REPORT.md:124 | LeadPilot | B | GitHub repo name / URL | links + CI + Render/Vercel git hooks |
| docs/VERIFICATION_REPORT.md:127 | LeadPilot | B | GitHub repo name / URL | links + CI + Render/Vercel git hooks |
| docs/VERIFICATION_REPORT.md:162 | clienthunter | B | Postgres DB/user/container name | existing databases/containers keep the name |
| docs/VERIFICATION_REPORT.md:188 | lpk_ | B | API key prefix (issued keys start with it) | existing customer keys + Zapier/Make configs break |
| docs/VERIFICATION_REPORT.md:195 | lpk_ | B | API key prefix (issued keys start with it) | existing customer keys + Zapier/Make configs break |
| docs/VERIFICATION_REPORT.md:473 | lpk_ | B | API key prefix (issued keys start with it) | existing customer keys + Zapier/Make configs break |
| docs/architecture.md:1 | ClientHunter | A-current | old product/repo name in prose/title | low |
| docs/architecture.md:18 | clienthunter | B | PyPI package / CLI command name (sdk/) | published package + user scripts |
| docs/compliance.md:1 | ClientHunter | A-current | old product/repo name in prose/title | low |
| docs/learning-loop.md:1 | ClientHunter | A-current | old product/repo name in prose/title | low |
| docs/outreach_tools.md:9 | Vectorae | A-current | product name in prose/UI | low |
| docs/outreach_tools.md:68 | Vectorae | A-current | product name in prose/UI | low |
| docs/outreach_tools.md:132 | Vectorae | A-current | product name in prose/UI | low |
| docs/program/BASELINE.md:1 | Vectorae | A-historical | product name in prose/UI | renaming falsifies a dated record |
| docs/program/BASELINE.md:64 | LeadPilot | B | GitHub repo name / URL | links + CI + Render/Vercel git hooks |
| docs/program/BASELINE.md:65 | LeadPilot | B | GitHub repo name / URL | links + CI + Render/Vercel git hooks |
| docs/program/BASELINE.md:183 | leadpilot | B | local machine path | historical machine path |
| docs/program/BASELINE.md:204 | LEADPILOT | B | environment variable name (LEADPILOT_*) | deploy env config (Vercel/Render) must change in lockstep |
| docs/program/BASELINE.md:204 | LEADPILOT | B | environment variable name (LEADPILOT_*) | deploy env config (Vercel/Render) must change in lockstep |
| docs/program/BASELINE.md:294 | leadpilot | B | Render service name / onrender.com hostname | live service; renaming changes hostname |
| docs/program/BASELINE.md:295 | leadpilot | B | Render service name / onrender.com hostname | live service; renaming changes hostname |
| docs/program/BASELINE.md:296 | leadpilot | B | Render service name / onrender.com hostname | live service; renaming changes hostname |
| docs/program/BASELINE.md:297 | leadpilot | B | Render service name / onrender.com hostname | live service; renaming changes hostname |
| docs/program/BASELINE.md:321 | leadpilot | B | Render service name / onrender.com hostname | live service; renaming changes hostname |
| docs/program/BASELINE.md:330 | leadpilot | B | Render service name / onrender.com hostname | live service; renaming changes hostname |
| docs/program/BASELINE.md:330 | leadpilot | B | Render service name / onrender.com hostname | live service; renaming changes hostname |
| docs/program/BASELINE.md:330 | leadpilot | B | Render service name / onrender.com hostname | live service; renaming changes hostname |
| docs/program/BASELINE.md:331 | leadpilot | B | Render service name / onrender.com hostname | live service; renaming changes hostname |
| docs/program/BASELINE.md:377 | leadpilot | B | Render service name / onrender.com hostname | live service; renaming changes hostname |
| docs/program/BASELINE.md:377 | leadpilot | B | Render service name / onrender.com hostname | live service; renaming changes hostname |
| docs/program/BASELINE.md:377 | leadpilot | B | Render service name / onrender.com hostname | live service; renaming changes hostname |
| docs/program/BASELINE.md:437 | LeadPilot | B | GitHub repo name / URL | links + CI + Render/Vercel git hooks |
| docs/program/DECISIONS.md:9 | Calendarharvest(name) | C | company/site name ("Vectorae by Calendarharvest"); human decides if it survives rebrand | brand/legal naming decision |
| docs/program/DECISIONS.md:32 | lpk_ | B | API key prefix (issued keys start with it) | existing customer keys + Zapier/Make configs break |
| docs/program/DECISIONS.md:33 | leadpilot | B | OAuth scope string (leadpilot:read/write) | issued tokens + connector clients |
| docs/program/DECISIONS.md:41 | leadpilot | B | Render service name / onrender.com hostname | live service; renaming changes hostname |
| docs/program/DECISIONS.md:42 | leadpilot | B | Render service name / onrender.com hostname | live service; renaming changes hostname |
| docs/program/DECISIONS.md:49 | Vectorae | A-historical | product name in prose/UI | renaming falsifies a dated record |
| docs/program/GATES.md:1 | Vectorae | A-current | product name in prose/UI | low |
| docs/program/GATES.md:42 | LeadPilot | B | GitHub repo name / URL | links + CI + Render/Vercel git hooks |
| docs/program/GATES.md:43 | LeadPilot | B | GitHub repo name / URL | links + CI + Render/Vercel git hooks |
| docs/program/GATES.md:44 | LeadPilot | B | GitHub repo name / URL | links + CI + Render/Vercel git hooks |
| docs/program/GATES.md:45 | LeadPilot | B | GitHub repo name / URL | links + CI + Render/Vercel git hooks |
| docs/program/GATES.md:50 | LeadPilot | B | GitHub repo name / URL | links + CI + Render/Vercel git hooks |
| docs/program/GATES.md:64 | leadpilot | B | Render service name / onrender.com hostname | live service; renaming changes hostname |
| docs/program/GATES.md:64 | leadpilot | B | Render service name / onrender.com hostname | live service; renaming changes hostname |
| docs/program/GATES.md:66 | leadpilot | B | Render service name / onrender.com hostname | live service; renaming changes hostname |
| docs/program/GATES.md:68 | leadpilot | B | Render service name / onrender.com hostname | live service; renaming changes hostname |
| docs/program/GATES.md:78 | lead-pilot | B | Vercel project name | external project identifier |
| docs/program/PROGRESS.md:51 | LeadPilot | B | GitHub repo name / URL | links + CI + Render/Vercel git hooks |
| docs/program/PROGRESS.md:64 | LeadPilot | B | GitHub repo name / URL | links + CI + Render/Vercel git hooks |
| docs/program/PROGRESS.md:74 | leadpilot | B | local machine path | historical machine path |
| docs/program/PROGRESS.md:80 | LeadPilot | B | GitHub repo name / URL | links + CI + Render/Vercel git hooks |
| docs/program/STAR_PROMPT.md:1 | Vectorae | A-historical | product name in prose/UI | renaming falsifies a dated record |
| docs/program/STAR_PROMPT.md:26 | leadpilot | B | Render service name / onrender.com hostname | live service; renaming changes hostname |
| docs/program/STAR_PROMPT.md:27 | LeadPilot | B | GitHub repo name / URL | links + CI + Render/Vercel git hooks |
| docs/program/STAR_PROMPT.md:42 | Vectorae | A-historical | product name in prose/UI | renaming falsifies a dated record |
| docs/program/STAR_PROMPT.md:42 | ClientHunter | A-historical | old product/repo name in prose/title | renaming falsifies a dated record |
| docs/program/STAR_PROMPT.md:87 | Vectorae | A-historical | product name in prose/UI | renaming falsifies a dated record |
| docs/program/STAR_PROMPT.md:137 | leadpilot | B | Render service name / onrender.com hostname | live service; renaming changes hostname |
| docs/program/STAR_PROMPT.md:148 | leadpilot | B | gate stamp directory .git/leadpilot-gate/ (hooks read it) | pre-push hook + Claude hooks look for stamps here |
| docs/program/STAR_PROMPT.md:190 | leadpilot | B | file name / file-path reference (repo file or help-center slug) | links + scripts (geo_audit.py, help-center ids) break if file renamed |
| docs/program/STAR_PROMPT.md:200 | Vectorae | A-historical | product name in prose/UI | renaming falsifies a dated record |
| docs/program/STAR_PROMPT.md:291 | Vectorae | A-historical | product name in prose/UI | renaming falsifies a dated record |
| docs/program/STAR_PROMPT.md:318 | Vectorae | A-historical | product name in prose/UI | renaming falsifies a dated record |
| docs/program/STATUS_PAGE.md:1 | Vectorae | A-current | product name in prose/UI | low |
| docs/program/STATUS_PAGE.md:5 | lead-pilot | B | Vercel project name | external project identifier |
| docs/program/STATUS_PAGE.md:22 | lead-pilot | B | Vercel project name | external project identifier |
| docs/program/STATUS_PAGE.md:25 | Vectorae | A-current | product name in prose/UI | low |
| docs/program/STATUS_PAGE.md:36 | Vectorae | A-current | product name in prose/UI | low |
| docs/program/STATUS_PAGE.md:78 | leadpilot | B | Render service name / onrender.com hostname | live service; renaming changes hostname |
| docs/program/STATUS_PAGE.md:80 | leadpilot | B | Render service name / onrender.com hostname | live service; renaming changes hostname |
| docs/program/STATUS_PAGE.md:124 | Vectorae | A-current | product name in prose/UI | low |
| docs/program/STATUS_PAGE.md:124 | Calendarharvest(name) | C | company/site name ("Vectorae by Calendarharvest"); human decides if it survives rebrand | brand/legal naming decision |
| docs/program/STATUS_PAGE.md:159 | Vectorae | A-current | product name in prose/UI | low |
| docs/program/STATUS_PAGE.md:202 | Vectorae | A-current | product name in prose/UI | low |
| docs/program/STATUS_PAGE.md:256 | Vectorae | B | documents UptimeRobot monitor names (external identifiers) | must match UptimeRobot + status-page/lib/config.ts |
| docs/program/STATUS_PAGE.md:257 | Vectorae | B | documents UptimeRobot monitor names (external identifiers) | must match UptimeRobot + status-page/lib/config.ts |
| docs/program/STATUS_PAGE.md:258 | Vectorae | B | documents UptimeRobot monitor names (external identifiers) | must match UptimeRobot + status-page/lib/config.ts |
| docs/program/STATUS_PAGE.md:284 | Vectorae | B | documents UptimeRobot monitor names (external identifiers) | must match UptimeRobot + status-page/lib/config.ts |
| docs/program/STATUS_PAGE.md:291 | Vectorae | B | documents UptimeRobot monitor names (external identifiers) | must match UptimeRobot + status-page/lib/config.ts |
| docs/program/STATUS_PAGE.md:292 | Vectorae | B | documents UptimeRobot monitor names (external identifiers) | must match UptimeRobot + status-page/lib/config.ts |
| docs/program/STATUS_PAGE.md:293 | Vectorae | B | documents UptimeRobot monitor names (external identifiers) | must match UptimeRobot + status-page/lib/config.ts |
| docs/program/STATUS_PAGE.md:294 | leadpilot | B | Render service name / onrender.com hostname | live service; renaming changes hostname |
| docs/program/STATUS_PAGE.md:294 | Vectorae | B | documents UptimeRobot monitor names (external identifiers) | must match UptimeRobot + status-page/lib/config.ts |
| docs/program/STATUS_PAGE.md:295 | leadpilot | B | Render service name / onrender.com hostname | live service; renaming changes hostname |
| docs/program/STATUS_PAGE.md:295 | Vectorae | B | documents UptimeRobot monitor names (external identifiers) | must match UptimeRobot + status-page/lib/config.ts |
| docs/program/STATUS_PAGE.md:301 | Vectorae | B | documents UptimeRobot monitor names (external identifiers) | must match UptimeRobot + status-page/lib/config.ts |
| docs/program/STATUS_PAGE.md:306 | LeadPilot | B | GitHub repo name / URL | links + CI + Render/Vercel git hooks |
| docs/program/STATUS_PAGE.md:315 | leadpilot | B | Render service name / onrender.com hostname | live service; renaming changes hostname |
| docs/program/STATUS_PAGE.md:315 | LEADPILOT | B | environment variable name (LEADPILOT_*) | deploy env config (Vercel/Render) must change in lockstep |
| docs/program/STATUS_PAGE.md:379 | Vectorae | A-current | product name in prose/UI | low |
| docs/program/STATUS_PAGE.md:393 | Vectorae | A-current | product name in prose/UI | low |
| docs/program/STATUS_PAGE.md:477 | leadpilot | B | Render service name / onrender.com hostname | live service; renaming changes hostname |
| docs/program/STATUS_PAGE.md:477 | LEADPILOT | B | environment variable name (LEADPILOT_*) | deploy env config (Vercel/Render) must change in lockstep |
| docs/program/ai-visibility/BASELINE.md:13 | leadpilot | B | Render service name / onrender.com hostname | live service; renaming changes hostname |
| docs/program/ai-visibility/BASELINE.md:15 | leadpilot | B | Render service name / onrender.com hostname | live service; renaming changes hostname |
| docs/program/ai-visibility/BASELINE.md:23 | leadpilot | B | Render service name / onrender.com hostname | live service; renaming changes hostname |
| docs/program/ai-visibility/BASELINE.md:30 | leadpilot | B | public URL slug on calendarharvest.com (indexed, in sitemap/llms.txt) | SEO + inbound links; needs 301 redirects |
| docs/program/ai-visibility/BASELINE.md:L47-48,53-57,62-63,121-123,129 (21 occurrences) | Vectorae | A-historical | product name in prose/UI | renaming falsifies a dated record |
| docs/program/ai-visibility/BASELINE.md:47 | Calendarharvest(name) | C | company/site name ("Vectorae by Calendarharvest"); human decides if it survives rebrand | brand/legal naming decision |
| docs/program/ai-visibility/BASELINE.md:48 | Calendarharvest(name) | C | company/site name ("Vectorae by Calendarharvest"); human decides if it survives rebrand | brand/legal naming decision |
| docs/program/ai-visibility/BASELINE.md:50 | leadpilot | B | public URL slug on calendarharvest.com (indexed, in sitemap/llms.txt) | SEO + inbound links; needs 301 redirects |
| docs/program/ai-visibility/BASELINE.md:54 | Calendarharvest(name) | C | company/site name ("Vectorae by Calendarharvest"); human decides if it survives rebrand | brand/legal naming decision |
| docs/program/ai-visibility/BASELINE.md:56 | Calendarharvest(name) | C | company/site name ("Vectorae by Calendarharvest"); human decides if it survives rebrand | brand/legal naming decision |
| docs/program/ai-visibility/BASELINE.md:57 | Calendarharvest(name) | C | company/site name ("Vectorae by Calendarharvest"); human decides if it survives rebrand | brand/legal naming decision |
| docs/program/ai-visibility/BASELINE.md:84 | leadpilot | B | public URL slug on calendarharvest.com (indexed, in sitemap/llms.txt) | SEO + inbound links; needs 301 redirects |
| docs/program/ai-visibility/BASELINE.md:84 | leadpilot | B | public URL slug on calendarharvest.com (indexed, in sitemap/llms.txt) | SEO + inbound links; needs 301 redirects |
| docs/program/ai-visibility/BASELINE.md:122 | Calendarharvest(name) | C | company/site name ("Vectorae by Calendarharvest"); human decides if it survives rebrand | brand/legal naming decision |
| docs/program/ai-visibility/NOTES.md:8 | leadpilot | C | our third-party listing/profile handle (LinkedIn/G2/Crunchbase/GetApp/YouTube) | external listing; renaming is a manual platform action, URL may change |
| docs/program/ai-visibility/NOTES.md:21 | leadpilot | C | our third-party listing/profile handle (LinkedIn/G2/Crunchbase/GetApp/YouTube) | external listing; renaming is a manual platform action, URL may change |
| docs/program/ai-visibility/NOTES.md:48 | leadpilot | B | Render service name / onrender.com hostname | live service; renaming changes hostname |
| docs/program/ai-visibility/NOTES.md:58 | Vectorae | A-historical | product name in prose/UI | renaming falsifies a dated record |
| docs/program/ai-visibility/NOTES.md:58 | Calendarharvest(name) | C | company/site name ("Vectorae by Calendarharvest"); human decides if it survives rebrand | brand/legal naming decision |
| docs/program/ai-visibility/NOTES.md:58 | Calendarharvest(name) | C | company/site name ("Vectorae by Calendarharvest"); human decides if it survives rebrand | brand/legal naming decision |
| docs/program/ai-visibility/NOTES.md:64 | Vectorae | A-historical | product name in prose/UI ×2 | renaming falsifies a dated record |
| docs/program/ai-visibility/NOTES.md:64 | Calendarharvest(name) | C | company/site name ("Vectorae by Calendarharvest"); human decides if it survives rebrand | brand/legal naming decision |
| docs/program/ai-visibility/NOTES.md:64 | Calendarharvest(name) | C | company/site name ("Vectorae by Calendarharvest"); human decides if it survives rebrand | brand/legal naming decision |
| docs/program/ai-visibility/NOTES.md:75 | Vectorae | A-historical | product name in prose/UI | renaming falsifies a dated record |
| docs/program/ai-visibility/NOTES.md:75 | Calendarharvest(name) | C | company/site name ("Vectorae by Calendarharvest"); human decides if it survives rebrand | brand/legal naming decision |
| docs/program/ai-visibility/NOTES.md:76 | Vectorae | A-historical | product name in prose/UI | renaming falsifies a dated record |
| docs/program/ai-visibility/NOTES.md:77 | Vectorae | A-historical | product name in prose/UI ×2 | renaming falsifies a dated record |
| docs/program/ai-visibility/NOTES.md:101 | leadpilot | C | our third-party listing/profile handle (LinkedIn/G2/Crunchbase/GetApp/YouTube) | external listing; renaming is a manual platform action, URL may change |
| docs/program/ai-visibility/NOTES.md:101 | leadpilot | C | our third-party listing/profile handle (LinkedIn/G2/Crunchbase/GetApp/YouTube) | external listing; renaming is a manual platform action, URL may change |
| docs/program/ai-visibility/NOTES.md:108 | Vectorae | A-historical | product name in prose/UI | renaming falsifies a dated record |
| docs/program/ai-visibility/NOTES.md:108 | Calendarharvest(name) | C | company/site name ("Vectorae by Calendarharvest"); human decides if it survives rebrand | brand/legal naming decision |
| docs/program/ai-visibility/NOTES.md:122 | leadpilot | C | our third-party listing/profile handle (LinkedIn/G2/Crunchbase/GetApp/YouTube) | external listing; renaming is a manual platform action, URL may change |
| docs/program/ai-visibility/NOTES.md:122 | leadpilot | C | our third-party listing/profile handle (LinkedIn/G2/Crunchbase/GetApp/YouTube) | external listing; renaming is a manual platform action, URL may change |
| docs/program/ai-visibility/NOTES.md:124 | LeadPilot | C | our third-party listing/profile handle (LinkedIn/G2/Crunchbase/GetApp/YouTube) | external listing; renaming is a manual platform action, URL may change |
| docs/program/ai-visibility/NOTES.md:125 | leadpilot | C | our third-party listing/profile handle (LinkedIn/G2/Crunchbase/GetApp/YouTube) | external listing; renaming is a manual platform action, URL may change |
| docs/program/ai-visibility/NOTES.md:125 | leadpilot | C | our third-party listing/profile handle (LinkedIn/G2/Crunchbase/GetApp/YouTube) | external listing; renaming is a manual platform action, URL may change |
| docs/program/ai-visibility/NOTES.md:125 | LeadPilot | C | our third-party listing/profile handle (LinkedIn/G2/Crunchbase/GetApp/YouTube) | external listing; renaming is a manual platform action, URL may change |
| docs/program/ai-visibility/NOTES.md:126 | leadpilot | C | our third-party listing/profile handle (LinkedIn/G2/Crunchbase/GetApp/YouTube) | external listing; renaming is a manual platform action, URL may change |
| docs/program/ai-visibility/NOTES.md:132 | leadpilot | C | our third-party listing/profile handle (LinkedIn/G2/Crunchbase/GetApp/YouTube) | external listing; renaming is a manual platform action, URL may change |
| docs/program/ai-visibility/NOTES.md:133 | LeadPilot | EXCL | refers to a DIFFERENT company/product (LeadPilot AB, Lead Pilot/Twenty Over Ten, other "LeadPilot" products) | do NOT rename; blind replace corrupts disambiguation copy |
| docs/program/ai-visibility/NOTES.md:149 | Calendarharvest(name) | C | company/site name ("Vectorae by Calendarharvest"); human decides if it survives rebrand | brand/legal naming decision |
| docs/program/ai-visibility/PROMPT_TRACKER.md:7 | Vectorae | A-current | product name in prose/UI | low |
| docs/program/ai-visibility/PROMPT_TRACKER.md:7 | Calendarharvest(name) | C | company/site name ("Vectorae by Calendarharvest"); human decides if it survives rebrand | brand/legal naming decision |
| docs/program/ai-visibility/PROMPT_TRACKER.md:7 | LeadPilot | EXCL | refers to a DIFFERENT company/product (LeadPilot AB, Lead Pilot/Twenty Over Ten, other "LeadPilot" products) | do NOT rename; blind replace corrupts disambiguation copy |
| docs/program/ai-visibility/PROMPT_TRACKER.md:7 | leadpilot | EXCL | leadpilot.com = LeadPilot AB's domain (third party) | do NOT rename |
| docs/program/ai-visibility/PROMPT_TRACKER.md:10 | LeadPilot | EXCL | refers to a DIFFERENT company/product (LeadPilot AB, Lead Pilot/Twenty Over Ten, other "LeadPilot" products) | do NOT rename; blind replace corrupts disambiguation copy |
| docs/program/ai-visibility/PROMPT_TRACKER.md:17 | Vectorae | A-current | product name in prose/UI | low |
| docs/program/ai-visibility/PROMPT_TRACKER.md:17 | Calendarharvest(name) | C | company/site name ("Vectorae by Calendarharvest"); human decides if it survives rebrand | brand/legal naming decision |
| docs/program/ai-visibility/PROMPT_TRACKER.md:18 | Vectorae | A-current | product name in prose/UI | low |
| docs/program/ai-visibility/PROMPT_TRACKER.md:19 | Vectorae | A-current | product name in prose/UI | low |
| docs/program/ai-visibility/PROMPT_TRACKER.md:20 | Vectorae | A-current | product name in prose/UI | low |
| docs/program/ai-visibility/PROMPT_TRACKER.md:20 | Calendarharvest(name) | C | company/site name ("Vectorae by Calendarharvest"); human decides if it survives rebrand | brand/legal naming decision |
| docs/program/ai-visibility/PROMPT_TRACKER.md:21 | Vectorae | A-current | product name in prose/UI | low |
| docs/program/ai-visibility/PROMPT_TRACKER.md:21 | Calendarharvest(name) | C | company/site name ("Vectorae by Calendarharvest"); human decides if it survives rebrand | brand/legal naming decision |
| docs/program/ai-visibility/PROMPT_TRACKER.md:22 | Vectorae | A-current | product name in prose/UI | low |
| docs/program/ai-visibility/PROMPT_TRACKER.md:22 | Calendarharvest(name) | C | company/site name ("Vectorae by Calendarharvest"); human decides if it survives rebrand | brand/legal naming decision |
| docs/program/ai-visibility/PROMPT_TRACKER.md:22 | LeadPilot | EXCL | refers to a DIFFERENT company/product (LeadPilot AB, Lead Pilot/Twenty Over Ten, other "LeadPilot" products) | do NOT rename; blind replace corrupts disambiguation copy |
| docs/program/ai-visibility/PROMPT_TRACKER.md:22 | leadpilot | EXCL | leadpilot.com = LeadPilot AB's domain (third party) | do NOT rename |
| docs/program/ai-visibility/PROMPT_TRACKER.md:38 | Vectorae | A-current | product name in prose/UI | low |
| docs/program/ai-visibility/PROMPT_TRACKER.md:38 | Calendarharvest(name) | C | company/site name ("Vectorae by Calendarharvest"); human decides if it survives rebrand | brand/legal naming decision |
| docs/program/ai-visibility/PROMPT_TRACKER.md:39 | Vectorae | A-current | product name in prose/UI | low |
| docs/program/ai-visibility/PROMPT_TRACKER.md:39 | Calendarharvest(name) | C | company/site name ("Vectorae by Calendarharvest"); human decides if it survives rebrand | brand/legal naming decision |
| docs/program/ai-visibility/REPORT.md:13 | leadpilot | C | our third-party listing/profile handle (LinkedIn/G2/Crunchbase/GetApp/YouTube) | external listing; renaming is a manual platform action, URL may change |
| docs/program/ai-visibility/REPORT.md:26 | leadpilot | C | our third-party listing/profile handle (LinkedIn/G2/Crunchbase/GetApp/YouTube) | external listing; renaming is a manual platform action, URL may change |
| docs/program/ai-visibility/REPORT.md:L76-82,96,165,185,196,250 (20 occurrences) | Vectorae | A-historical | product name in prose/UI | renaming falsifies a dated record |
| docs/program/ai-visibility/REPORT.md:76 | Calendarharvest(name) | C | company/site name ("Vectorae by Calendarharvest"); human decides if it survives rebrand | brand/legal naming decision |
| docs/program/ai-visibility/REPORT.md:77 | Calendarharvest(name) | C | company/site name ("Vectorae by Calendarharvest"); human decides if it survives rebrand | brand/legal naming decision |
| docs/program/ai-visibility/REPORT.md:77 | Calendarharvest(name) | C | company/site name ("Vectorae by Calendarharvest"); human decides if it survives rebrand | brand/legal naming decision |
| docs/program/ai-visibility/REPORT.md:77 | Calendarharvest(name) | C | company/site name ("Vectorae by Calendarharvest"); human decides if it survives rebrand | brand/legal naming decision |
| docs/program/ai-visibility/REPORT.md:78 | Calendarharvest(name) | C | company/site name ("Vectorae by Calendarharvest"); human decides if it survives rebrand | brand/legal naming decision |
| docs/program/ai-visibility/REPORT.md:78 | Calendarharvest(name) | C | company/site name ("Vectorae by Calendarharvest"); human decides if it survives rebrand | brand/legal naming decision |
| docs/program/ai-visibility/REPORT.md:78 | Calendarharvest(name) | C | company/site name ("Vectorae by Calendarharvest"); human decides if it survives rebrand | brand/legal naming decision |
| docs/program/ai-visibility/REPORT.md:79 | Calendarharvest(name) | C | company/site name ("Vectorae by Calendarharvest"); human decides if it survives rebrand | brand/legal naming decision |
| docs/program/ai-visibility/REPORT.md:79 | Calendarharvest(name) | C | company/site name ("Vectorae by Calendarharvest"); human decides if it survives rebrand | brand/legal naming decision |
| docs/program/ai-visibility/REPORT.md:79 | Calendarharvest(name) | C | company/site name ("Vectorae by Calendarharvest"); human decides if it survives rebrand | brand/legal naming decision |
| docs/program/ai-visibility/REPORT.md:80 | Calendarharvest(name) | C | company/site name ("Vectorae by Calendarharvest"); human decides if it survives rebrand | brand/legal naming decision |
| docs/program/ai-visibility/REPORT.md:80 | Calendarharvest(name) | C | company/site name ("Vectorae by Calendarharvest"); human decides if it survives rebrand | brand/legal naming decision |
| docs/program/ai-visibility/REPORT.md:80 | Calendarharvest(name) | C | company/site name ("Vectorae by Calendarharvest"); human decides if it survives rebrand | brand/legal naming decision |
| docs/program/ai-visibility/REPORT.md:81 | Calendarharvest(name) | C | company/site name ("Vectorae by Calendarharvest"); human decides if it survives rebrand | brand/legal naming decision |
| docs/program/ai-visibility/REPORT.md:81 | Calendarharvest(name) | C | company/site name ("Vectorae by Calendarharvest"); human decides if it survives rebrand | brand/legal naming decision |
| docs/program/ai-visibility/REPORT.md:81 | Calendarharvest(name) | C | company/site name ("Vectorae by Calendarharvest"); human decides if it survives rebrand | brand/legal naming decision |
| docs/program/ai-visibility/REPORT.md:82 | Calendarharvest(name) | C | company/site name ("Vectorae by Calendarharvest"); human decides if it survives rebrand | brand/legal naming decision |
| docs/program/ai-visibility/REPORT.md:82 | Calendarharvest(name) | C | company/site name ("Vectorae by Calendarharvest"); human decides if it survives rebrand | brand/legal naming decision |
| docs/program/ai-visibility/REPORT.md:82 | Calendarharvest(name) | C | company/site name ("Vectorae by Calendarharvest"); human decides if it survives rebrand | brand/legal naming decision |
| docs/program/ai-visibility/REPORT.md:96 | Calendarharvest(name) | C | company/site name ("Vectorae by Calendarharvest"); human decides if it survives rebrand | brand/legal naming decision |
| docs/program/ai-visibility/REPORT.md:98 | leadpilot | EXCL | refers to a DIFFERENT company/product (LeadPilot AB, Lead Pilot/Twenty Over Ten, other "LeadPilot" products) | do NOT rename; blind replace corrupts disambiguation copy |
| docs/program/ai-visibility/REPORT.md:127 | leadpilot | B | Render service name / onrender.com hostname | live service; renaming changes hostname |
| docs/program/ai-visibility/REPORT.md:129 | Calendarharvest(name) | C | company/site name ("Vectorae by Calendarharvest"); human decides if it survives rebrand | brand/legal naming decision |
| docs/program/ai-visibility/REPORT.md:129 | VECTORAE | A-historical | product name in prose/UI | renaming falsifies a dated record |
| docs/program/ai-visibility/REPORT.md:165 | Calendarharvest(name) | C | company/site name ("Vectorae by Calendarharvest"); human decides if it survives rebrand | brand/legal naming decision |
| docs/program/ai-visibility/REPORT.md:165 | LeadPilot | EXCL | refers to a DIFFERENT company/product (LeadPilot AB, Lead Pilot/Twenty Over Ten, other "LeadPilot" products) | do NOT rename; blind replace corrupts disambiguation copy |
| docs/program/ai-visibility/REPORT.md:185 | Calendarharvest(name) | C | company/site name ("Vectorae by Calendarharvest"); human decides if it survives rebrand | brand/legal naming decision |
| docs/program/ai-visibility/SPEC.md:L1,6,10,31,43,45-46,96-97,103,123 (18 occurrences) | Vectorae | A-current | product name in prose/UI | low |
| docs/program/ai-visibility/SPEC.md:6 | Calendarharvest(name) | C | company/site name ("Vectorae by Calendarharvest"); human decides if it survives rebrand | brand/legal naming decision |
| docs/program/ai-visibility/SPEC.md:30 | Calendarharvest(name) | C | company/site name ("Vectorae by Calendarharvest"); human decides if it survives rebrand | brand/legal naming decision |
| docs/program/ai-visibility/SPEC.md:30 | Calendarharvest(name) | C | company/site name ("Vectorae by Calendarharvest"); human decides if it survives rebrand | brand/legal naming decision |
| docs/program/ai-visibility/SPEC.md:30 | LeadPilot | EXCL | refers to a DIFFERENT company/product (LeadPilot AB, Lead Pilot/Twenty Over Ten, other "LeadPilot" products) | do NOT rename; blind replace corrupts disambiguation copy |
| docs/program/ai-visibility/SPEC.md:30 | LeadPilot | EXCL | refers to a DIFFERENT company/product (LeadPilot AB, Lead Pilot/Twenty Over Ten, other "LeadPilot" products) | do NOT rename; blind replace corrupts disambiguation copy |
| docs/program/ai-visibility/SPEC.md:30 | leadpilot | EXCL | leadpilot.com = LeadPilot AB's domain (third party) | do NOT rename |
| docs/program/ai-visibility/SPEC.md:30 | leadpilot | EXCL | refers to a DIFFERENT company/product (LeadPilot AB, Lead Pilot/Twenty Over Ten, other "LeadPilot" products) | do NOT rename; blind replace corrupts disambiguation copy |
| docs/program/ai-visibility/SPEC.md:30 | leadpilot | EXCL | refers to a DIFFERENT company/product (LeadPilot AB, Lead Pilot/Twenty Over Ten, other "LeadPilot" products) | do NOT rename; blind replace corrupts disambiguation copy |
| docs/program/ai-visibility/SPEC.md:30 | Lead Pilot | EXCL | refers to a DIFFERENT company/product (LeadPilot AB, Lead Pilot/Twenty Over Ten, other "LeadPilot" products) | do NOT rename; blind replace corrupts disambiguation copy |
| docs/program/ai-visibility/SPEC.md:30 | leadpilot | C | our third-party listing/profile handle (LinkedIn/G2/Crunchbase/GetApp/YouTube) | external listing; renaming is a manual platform action, URL may change |
| docs/program/ai-visibility/SPEC.md:35 | LeadPilot | B | GitHub repo name / URL | links + CI + Render/Vercel git hooks |
| docs/program/ai-visibility/SPEC.md:46 | Calendarharvest(name) | C | company/site name ("Vectorae by Calendarharvest"); human decides if it survives rebrand | brand/legal naming decision |
| docs/program/ai-visibility/SPEC.md:69 | LeadPilot | EXCL | refers to a DIFFERENT company/product (LeadPilot AB, Lead Pilot/Twenty Over Ten, other "LeadPilot" products) | do NOT rename; blind replace corrupts disambiguation copy |
| docs/program/ai-visibility/SPEC.md:69 | Lead Pilot | EXCL | refers to a DIFFERENT company/product (LeadPilot AB, Lead Pilot/Twenty Over Ten, other "LeadPilot" products) | do NOT rename; blind replace corrupts disambiguation copy |
| docs/program/ai-visibility/SPEC.md:96 | Calendarharvest(name) | C | company/site name ("Vectorae by Calendarharvest"); human decides if it survives rebrand | brand/legal naming decision |
| docs/program/ai-visibility/SPEC.md:96 | Calendarharvest(name) | C | company/site name ("Vectorae by Calendarharvest"); human decides if it survives rebrand | brand/legal naming decision |
| docs/program/ai-visibility/SPEC.md:96 | Calendarharvest(name) | C | company/site name ("Vectorae by Calendarharvest"); human decides if it survives rebrand | brand/legal naming decision |
| docs/program/ai-visibility/SPEC.md:96 | LeadPilot | EXCL | refers to a DIFFERENT company/product (LeadPilot AB, Lead Pilot/Twenty Over Ten, other "LeadPilot" products) | do NOT rename; blind replace corrupts disambiguation copy |
| docs/program/ai-visibility/SPEC.md:97 | Calendarharvest(name) | C | company/site name ("Vectorae by Calendarharvest"); human decides if it survives rebrand | brand/legal naming decision |
| docs/program/ai-visibility/SPEC.md:97 | Calendarharvest(name) | C | company/site name ("Vectorae by Calendarharvest"); human decides if it survives rebrand | brand/legal naming decision |
| docs/program/ai-visibility/geo/README.md:1 | Vectorae | A-current | product name in prose/UI | low |
| docs/program/ai-visibility/geo/README.md:3 | Vectorae | A-current | product name in prose/UI | low |
| docs/program/ai-visibility/geo/README.md:3 | Calendarharvest(name) | C | company/site name ("Vectorae by Calendarharvest"); human decides if it survives rebrand | brand/legal naming decision |
| docs/program/ai-visibility/geo/README.md:13 | Vectorae | A-current | product name in prose/UI | low |
| docs/program/ai-visibility/geo/README.md:15 | Vectorae | A-current | product name in prose/UI | low |
| docs/program/ai-visibility/geo/README.md:15 | Calendarharvest(name) | C | company/site name ("Vectorae by Calendarharvest"); human decides if it survives rebrand | brand/legal naming decision |
| docs/program/ai-visibility/geo/README.md:16 | LeadPilot | A-current | former product name in prose | low |
| docs/program/ai-visibility/geo/README.md:16 | LeadPilot | EXCL | refers to a DIFFERENT company/product (LeadPilot AB, Lead Pilot/Twenty Over Ten, other "LeadPilot" products) | do NOT rename; blind replace corrupts disambiguation copy |
| docs/program/ai-visibility/geo/README.md:24 | leadpilot | B | file name / file-path reference (repo file or help-center slug) | links + scripts (geo_audit.py, help-center ids) break if file renamed |
| docs/program/ai-visibility/geo/README.md:24 | leadpilot | B | file name / file-path reference (repo file or help-center slug) | links + scripts (geo_audit.py, help-center ids) break if file renamed |
| docs/program/ai-visibility/geo/README.md:35 | LeadPilot | A-current | former product name in prose | low |
| docs/program/ai-visibility/geo/authority/citation_acquisition_plan.md:9 | LeadPilot | EXCL | refers to a DIFFERENT company/product (LeadPilot AB, Lead Pilot/Twenty Over Ten, other "LeadPilot" products) | do NOT rename; blind replace corrupts disambiguation copy |
| docs/program/ai-visibility/geo/authority/citation_acquisition_plan.md:9 | LeadPilot | EXCL | refers to a DIFFERENT company/product (LeadPilot AB, Lead Pilot/Twenty Over Ten, other "LeadPilot" products) | do NOT rename; blind replace corrupts disambiguation copy |
| docs/program/ai-visibility/geo/authority/citation_acquisition_plan.md:10 | LeadPilot | EXCL | refers to a DIFFERENT company/product (LeadPilot AB, Lead Pilot/Twenty Over Ten, other "LeadPilot" products) | do NOT rename; blind replace corrupts disambiguation copy |
| docs/program/ai-visibility/geo/authority/citation_acquisition_plan.md:10 | Vectorae | A-current | product name in prose/UI | low |
| docs/program/ai-visibility/geo/authority/citation_acquisition_plan.md:10 | Calendarharvest(name) | C | company/site name ("Vectorae by Calendarharvest"); human decides if it survives rebrand | brand/legal naming decision |
| docs/program/ai-visibility/geo/authority/citation_acquisition_plan.md:20 | Vectorae | A-current | product name in prose/UI | low |
| docs/program/ai-visibility/geo/authority/citation_acquisition_plan.md:20 | Calendarharvest(name) | C | company/site name ("Vectorae by Calendarharvest"); human decides if it survives rebrand | brand/legal naming decision |
| docs/program/ai-visibility/geo/authority/citation_acquisition_plan.md:24 | Vectorae | A-current | product name in prose/UI | low |
| docs/program/ai-visibility/geo/authority/citation_acquisition_plan.md:24 | Calendarharvest(name) | C | company/site name ("Vectorae by Calendarharvest"); human decides if it survives rebrand | brand/legal naming decision |
| docs/program/ai-visibility/geo/authority/citation_acquisition_plan.md:26 | LeadPilot | EXCL | refers to a DIFFERENT company/product (LeadPilot AB, Lead Pilot/Twenty Over Ten, other "LeadPilot" products) | do NOT rename; blind replace corrupts disambiguation copy |
| docs/program/ai-visibility/geo/authority/citation_acquisition_plan.md:26 | Vectorae | A-current | product name in prose/UI ×4 | low |
| docs/program/ai-visibility/geo/authority/citation_acquisition_plan.md:26 | Calendarharvest(name) | C | company/site name ("Vectorae by Calendarharvest"); human decides if it survives rebrand | brand/legal naming decision |
| docs/program/ai-visibility/geo/authority/citation_acquisition_plan.md:26 | Calendarharvest(name) | C | company/site name ("Vectorae by Calendarharvest"); human decides if it survives rebrand | brand/legal naming decision |
| docs/program/ai-visibility/geo/authority/citation_acquisition_plan.md:26 | leadpilot | EXCL | leadpilot.com = LeadPilot AB's domain (third party) | do NOT rename |
| docs/program/ai-visibility/geo/authority/citation_acquisition_plan.md:29 | Vectorae | A-current | product name in prose/UI ×2 | low |
| docs/program/ai-visibility/geo/authority/citation_acquisition_plan.md:29 | Calendarharvest(name) | C | company/site name ("Vectorae by Calendarharvest"); human decides if it survives rebrand | brand/legal naming decision |
| docs/program/ai-visibility/geo/authority/citation_acquisition_plan.md:40 | Vectorae | A-current | product name in prose/UI | low |
| docs/program/ai-visibility/geo/authority/citation_acquisition_plan.md:40 | Calendarharvest(name) | C | company/site name ("Vectorae by Calendarharvest"); human decides if it survives rebrand | brand/legal naming decision |
| docs/program/ai-visibility/geo/authority/citation_acquisition_plan.md:40 | leadpilot | C | our third-party listing/profile handle (LinkedIn/G2/Crunchbase/GetApp/YouTube) | external listing; renaming is a manual platform action, URL may change |
| docs/program/ai-visibility/geo/authority/citation_acquisition_plan.md:41 | Vectorae | A-current | product name in prose/UI | low |
| docs/program/ai-visibility/geo/authority/citation_acquisition_plan.md:41 | Calendarharvest(name) | C | company/site name ("Vectorae by Calendarharvest"); human decides if it survives rebrand | brand/legal naming decision |
| docs/program/ai-visibility/geo/authority/citation_acquisition_plan.md:42 | leadpilot | C | our third-party listing/profile handle (LinkedIn/G2/Crunchbase/GetApp/YouTube) | external listing; renaming is a manual platform action, URL may change |
| docs/program/ai-visibility/geo/authority/citation_acquisition_plan.md:46 | leadpilot | C | our third-party listing/profile handle (LinkedIn/G2/Crunchbase/GetApp/YouTube) | external listing; renaming is a manual platform action, URL may change |
| docs/program/ai-visibility/geo/authority/citation_acquisition_plan.md:47 | leadpilot | C | our third-party listing/profile handle (LinkedIn/G2/Crunchbase/GetApp/YouTube) | external listing; renaming is a manual platform action, URL may change |
| docs/program/ai-visibility/geo/authority/citation_acquisition_plan.md:47 | leadpilot | C | our third-party listing/profile handle (LinkedIn/G2/Crunchbase/GetApp/YouTube) | external listing; renaming is a manual platform action, URL may change |
| docs/program/ai-visibility/geo/authority/citation_acquisition_plan.md:52 | LeadPilot | C | our third-party listing/profile handle (LinkedIn/G2/Crunchbase/GetApp/YouTube) | external listing; renaming is a manual platform action, URL may change |
| docs/program/ai-visibility/geo/authority/citation_acquisition_plan.md:65 | Vectorae | A-current | product name in prose/UI | low |
| docs/program/ai-visibility/geo/authority/citation_acquisition_plan.md:65 | Calendarharvest(name) | C | company/site name ("Vectorae by Calendarharvest"); human decides if it survives rebrand | brand/legal naming decision |
| docs/program/ai-visibility/geo/authority/citation_acquisition_plan.md:75 | leadpilot | EXCL | refers to a DIFFERENT company/product (LeadPilot AB, Lead Pilot/Twenty Over Ten, other "LeadPilot" products) | do NOT rename; blind replace corrupts disambiguation copy |
| docs/program/ai-visibility/geo/authority/citation_acquisition_plan.md:77 | leadpilot | C | our third-party listing/profile handle (LinkedIn/G2/Crunchbase/GetApp/YouTube) | external listing; renaming is a manual platform action, URL may change |
| docs/program/ai-visibility/geo/authority/citation_acquisition_plan.md:95 | Vectorae | A-current | product name in prose/UI | low |
| docs/program/ai-visibility/geo/authority/citation_acquisition_plan.md:104 | Vectorae | A-current | product name in prose/UI | low |
| docs/program/ai-visibility/geo/authority/citation_acquisition_plan.md:104 | Calendarharvest(name) | C | company/site name ("Vectorae by Calendarharvest"); human decides if it survives rebrand | brand/legal naming decision |
| docs/program/ai-visibility/geo/authority/citation_acquisition_plan.md:105 | Vectorae | A-current | product name in prose/UI | low |
| docs/program/ai-visibility/geo/authority/reddit_strategy.md:11 | Vectorae | A-current | product name in prose/UI ×2 | low |
| docs/program/ai-visibility/geo/authority/reddit_strategy.md:16 | Vectorae | A-current | product name in prose/UI | low |
| docs/program/ai-visibility/geo/authority/reddit_strategy.md:17 | Vectorae | A-current | product name in prose/UI | low |
| docs/program/ai-visibility/geo/authority/reddit_strategy.md:53 | Vectorae | A-current | product name in prose/UI | low |
| docs/program/ai-visibility/geo/authority/reddit_strategy.md:59 | Vectorae | A-current | product name in prose/UI | low |
| docs/program/ai-visibility/geo/authority/reddit_strategy.md:65 | Vectorae | A-current | product name in prose/UI | low |
| docs/program/ai-visibility/geo/authority/reddit_strategy.md:73 | Vectorae | A-current | product name in prose/UI | low |
| docs/program/ai-visibility/geo/authority/reddit_strategy.md:91 | Vectorae | A-current | product name in prose/UI | low |
| docs/program/ai-visibility/geo/authority/reddit_strategy.md:96 | Vectorae | A-current | product name in prose/UI | low |
| docs/program/ai-visibility/geo/authority/reddit_strategy.md:100 | Vectorae | A-current | product name in prose/UI | low |
| docs/program/ai-visibility/geo/authority/reddit_strategy.md:129 | Vectorae | A-current | product name in prose/UI | low |
| docs/program/ai-visibility/geo/authority/reddit_strategy.md:130 | Vectorae | A-current | product name in prose/UI | low |
| docs/program/ai-visibility/geo/authority/reddit_strategy.md:131 | Vectorae | A-current | product name in prose/UI | low |
| docs/program/ai-visibility/geo/authority/reddit_strategy.md:139 | Vectorae | A-current | product name in prose/UI | low |
| docs/program/ai-visibility/geo/authority/syndication_map.md:11 | Vectorae | A-current | product name in prose/UI | low |
| docs/program/ai-visibility/geo/authority/syndication_map.md:18 | leadpilot | B | file name / file-path reference (repo file or help-center slug) | links + scripts (geo_audit.py, help-center ids) break if file renamed |
| docs/program/ai-visibility/geo/authority/syndication_map.md:18 | leadpilot | B | public URL slug on calendarharvest.com (indexed, in sitemap/llms.txt) | SEO + inbound links; needs 301 redirects |
| docs/program/ai-visibility/geo/authority/syndication_map.md:22 | Vectorae | A-current | product name in prose/UI | low |
| docs/program/ai-visibility/geo/authority/syndication_map.md:22 | leadpilot | B | file name / file-path reference (repo file or help-center slug) | links + scripts (geo_audit.py, help-center ids) break if file renamed |
| docs/program/ai-visibility/geo/authority/syndication_map.md:22 | leadpilot | B | public URL slug on calendarharvest.com (indexed, in sitemap/llms.txt) | SEO + inbound links; needs 301 redirects |
| docs/program/ai-visibility/geo/authority/syndication_map.md:23 | leadpilot | B | file name / file-path reference (repo file or help-center slug) | links + scripts (geo_audit.py, help-center ids) break if file renamed |
| docs/program/ai-visibility/geo/authority/syndication_map.md:23 | leadpilot | B | public URL slug on calendarharvest.com (indexed, in sitemap/llms.txt) | SEO + inbound links; needs 301 redirects |
| docs/program/ai-visibility/geo/authority/syndication_map.md:24 | leadpilot | B | file name / file-path reference (repo file or help-center slug) | links + scripts (geo_audit.py, help-center ids) break if file renamed |
| docs/program/ai-visibility/geo/authority/syndication_map.md:24 | leadpilot | B | public URL slug on calendarharvest.com (indexed, in sitemap/llms.txt) | SEO + inbound links; needs 301 redirects |
| docs/program/ai-visibility/geo/authority/syndication_map.md:25 | leadpilot | B | file name / file-path reference (repo file or help-center slug) | links + scripts (geo_audit.py, help-center ids) break if file renamed |
| docs/program/ai-visibility/geo/authority/syndication_map.md:25 | leadpilot | B | public URL slug on calendarharvest.com (indexed, in sitemap/llms.txt) | SEO + inbound links; needs 301 redirects |
| docs/program/ai-visibility/geo/authority/syndication_map.md:26 | leadpilot | B | file name / file-path reference (repo file or help-center slug) | links + scripts (geo_audit.py, help-center ids) break if file renamed |
| docs/program/ai-visibility/geo/authority/syndication_map.md:26 | leadpilot | B | public URL slug on calendarharvest.com (indexed, in sitemap/llms.txt) | SEO + inbound links; needs 301 redirects |
| docs/program/ai-visibility/geo/content/comparison_matrix.md:L3-4,7,9,12,22,29,31,47,49,63,65,69,78,80,93,95 (17 occurrences) | Vectorae | A-current | product name in prose/UI | low |
| docs/program/ai-visibility/geo/content/comparison_matrix.md:7 | Calendarharvest(name) | C | company/site name ("Vectorae by Calendarharvest"); human decides if it survives rebrand | brand/legal naming decision |
| docs/program/ai-visibility/geo/content/comparison_matrix.md:9 | Calendarharvest(name) | C | company/site name ("Vectorae by Calendarharvest"); human decides if it survives rebrand | brand/legal naming decision |
| docs/program/ai-visibility/geo/content/comparisons/leadpilot_vs_apollo.md:2 | leadpilot | B | public URL slug on calendarharvest.com (indexed, in sitemap/llms.txt) | SEO + inbound links; needs 301 redirects |
| docs/program/ai-visibility/geo/content/comparisons/leadpilot_vs_apollo.md:3 | leadpilot | B | public URL slug on calendarharvest.com (indexed, in sitemap/llms.txt) | SEO + inbound links; needs 301 redirects |
| docs/program/ai-visibility/geo/content/comparisons/leadpilot_vs_apollo.md:L8,10,15,19,21,31,33,37,52,61,68,71-73,75,81 (17 occurrences) | Vectorae | A-current | product name in prose/UI | low |
| docs/program/ai-visibility/geo/content/comparisons/leadpilot_vs_apollo.md:15 | Calendarharvest(name) | C | company/site name ("Vectorae by Calendarharvest"); human decides if it survives rebrand | brand/legal naming decision |
| docs/program/ai-visibility/geo/content/comparisons/leadpilot_vs_apollo.md:75 | Calendarharvest(name) | C | company/site name ("Vectorae by Calendarharvest"); human decides if it survives rebrand | brand/legal naming decision |
| docs/program/ai-visibility/geo/content/comparisons/leadpilot_vs_apollo.md:75 | LeadPilot | EXCL | refers to a DIFFERENT company/product (LeadPilot AB, Lead Pilot/Twenty Over Ten, other "LeadPilot" products) | do NOT rename; blind replace corrupts disambiguation copy |
| docs/program/ai-visibility/geo/content/comparisons/leadpilot_vs_apollo.md:75 | leadpilot | EXCL | leadpilot.com = LeadPilot AB's domain (third party) | do NOT rename |
| docs/program/ai-visibility/geo/content/comparisons/leadpilot_vs_artisan.md:2 | leadpilot | B | public URL slug on calendarharvest.com (indexed, in sitemap/llms.txt) | SEO + inbound links; needs 301 redirects |
| docs/program/ai-visibility/geo/content/comparisons/leadpilot_vs_artisan.md:7 | Vectorae | A-current | product name in prose/UI | low |
| docs/program/ai-visibility/geo/content/comparisons/leadpilot_vs_artisan.md:9 | Vectorae | A-current | product name in prose/UI ×2 | low |
| docs/program/ai-visibility/geo/content/comparisons/leadpilot_vs_artisan.md:13 | Vectorae | A-current | product name in prose/UI | low |
| docs/program/ai-visibility/geo/content/comparisons/leadpilot_vs_artisan.md:13 | Calendarharvest(name) | C | company/site name ("Vectorae by Calendarharvest"); human decides if it survives rebrand | brand/legal naming decision |
| docs/program/ai-visibility/geo/content/comparisons/leadpilot_vs_artisan.md:16 | Vectorae | A-current | product name in prose/UI | low |
| docs/program/ai-visibility/geo/content/comparisons/leadpilot_vs_artisan.md:19 | Vectorae | A-current | product name in prose/UI | low |
| docs/program/ai-visibility/geo/content/comparisons/leadpilot_vs_artisan.md:40 | Vectorae | A-current | product name in prose/UI | low |
| docs/program/ai-visibility/geo/content/comparisons/leadpilot_vs_artisan.md:53 | Vectorae | A-current | product name in prose/UI | low |
| docs/program/ai-visibility/geo/content/comparisons/leadpilot_vs_artisan.md:64 | Vectorae | A-current | product name in prose/UI | low |
| docs/program/ai-visibility/geo/content/comparisons/leadpilot_vs_artisan.md:66 | Vectorae | A-current | product name in prose/UI | low |
| docs/program/ai-visibility/geo/content/comparisons/leadpilot_vs_artisan.md:68 | Vectorae | A-current | product name in prose/UI | low |
| docs/program/ai-visibility/geo/content/comparisons/leadpilot_vs_artisan.md:68 | Calendarharvest(name) | C | company/site name ("Vectorae by Calendarharvest"); human decides if it survives rebrand | brand/legal naming decision |
| docs/program/ai-visibility/geo/content/comparisons/leadpilot_vs_artisan.md:68 | LeadPilot | EXCL | refers to a DIFFERENT company/product (LeadPilot AB, Lead Pilot/Twenty Over Ten, other "LeadPilot" products) | do NOT rename; blind replace corrupts disambiguation copy |
| docs/program/ai-visibility/geo/content/comparisons/leadpilot_vs_artisan.md:68 | leadpilot | EXCL | leadpilot.com = LeadPilot AB's domain (third party) | do NOT rename |
| docs/program/ai-visibility/geo/content/comparisons/leadpilot_vs_artisan.md:76 | Vectorae | A-current | product name in prose/UI | low |
| docs/program/ai-visibility/geo/content/comparisons/leadpilot_vs_clay.md:2 | leadpilot | B | public URL slug on calendarharvest.com (indexed, in sitemap/llms.txt) | SEO + inbound links; needs 301 redirects |
| docs/program/ai-visibility/geo/content/comparisons/leadpilot_vs_clay.md:7 | Vectorae | A-current | product name in prose/UI | low |
| docs/program/ai-visibility/geo/content/comparisons/leadpilot_vs_clay.md:9 | Vectorae | A-current | product name in prose/UI ×2 | low |
| docs/program/ai-visibility/geo/content/comparisons/leadpilot_vs_clay.md:14 | Vectorae | A-current | product name in prose/UI | low |
| docs/program/ai-visibility/geo/content/comparisons/leadpilot_vs_clay.md:14 | Calendarharvest(name) | C | company/site name ("Vectorae by Calendarharvest"); human decides if it survives rebrand | brand/legal naming decision |
| docs/program/ai-visibility/geo/content/comparisons/leadpilot_vs_clay.md:17 | Vectorae | A-current | product name in prose/UI | low |
| docs/program/ai-visibility/geo/content/comparisons/leadpilot_vs_clay.md:20 | Vectorae | A-current | product name in prose/UI | low |
| docs/program/ai-visibility/geo/content/comparisons/leadpilot_vs_clay.md:34 | Vectorae | A-current | product name in prose/UI | low |
| docs/program/ai-visibility/geo/content/comparisons/leadpilot_vs_clay.md:46 | Vectorae | A-current | product name in prose/UI | low |
| docs/program/ai-visibility/geo/content/comparisons/leadpilot_vs_clay.md:59 | Vectorae | A-current | product name in prose/UI | low |
| docs/program/ai-visibility/geo/content/comparisons/leadpilot_vs_clay.md:61 | Vectorae | A-current | product name in prose/UI | low |
| docs/program/ai-visibility/geo/content/comparisons/leadpilot_vs_clay.md:63 | Vectorae | A-current | product name in prose/UI | low |
| docs/program/ai-visibility/geo/content/comparisons/leadpilot_vs_clay.md:63 | Calendarharvest(name) | C | company/site name ("Vectorae by Calendarharvest"); human decides if it survives rebrand | brand/legal naming decision |
| docs/program/ai-visibility/geo/content/comparisons/leadpilot_vs_clay.md:63 | LeadPilot | EXCL | refers to a DIFFERENT company/product (LeadPilot AB, Lead Pilot/Twenty Over Ten, other "LeadPilot" products) | do NOT rename; blind replace corrupts disambiguation copy |
| docs/program/ai-visibility/geo/content/comparisons/leadpilot_vs_clay.md:63 | leadpilot | EXCL | leadpilot.com = LeadPilot AB's domain (third party) | do NOT rename |
| docs/program/ai-visibility/geo/content/comparisons/leadpilot_vs_clay.md:70 | Vectorae | A-current | product name in prose/UI | low |
| docs/program/ai-visibility/geo/content/comparisons/leadpilot_vs_instantly.md:2 | leadpilot | B | public URL slug on calendarharvest.com (indexed, in sitemap/llms.txt) | SEO + inbound links; needs 301 redirects |
| docs/program/ai-visibility/geo/content/comparisons/leadpilot_vs_instantly.md:7 | Vectorae | A-current | product name in prose/UI | low |
| docs/program/ai-visibility/geo/content/comparisons/leadpilot_vs_instantly.md:9 | Vectorae | A-current | product name in prose/UI ×2 | low |
| docs/program/ai-visibility/geo/content/comparisons/leadpilot_vs_instantly.md:14 | Vectorae | A-current | product name in prose/UI | low |
| docs/program/ai-visibility/geo/content/comparisons/leadpilot_vs_instantly.md:14 | Calendarharvest(name) | C | company/site name ("Vectorae by Calendarharvest"); human decides if it survives rebrand | brand/legal naming decision |
| docs/program/ai-visibility/geo/content/comparisons/leadpilot_vs_instantly.md:17 | Vectorae | A-current | product name in prose/UI | low |
| docs/program/ai-visibility/geo/content/comparisons/leadpilot_vs_instantly.md:19 | Vectorae | A-current | product name in prose/UI | low |
| docs/program/ai-visibility/geo/content/comparisons/leadpilot_vs_instantly.md:34 | Vectorae | A-current | product name in prose/UI | low |
| docs/program/ai-visibility/geo/content/comparisons/leadpilot_vs_instantly.md:49 | Vectorae | A-current | product name in prose/UI | low |
| docs/program/ai-visibility/geo/content/comparisons/leadpilot_vs_instantly.md:62 | Vectorae | A-current | product name in prose/UI | low |
| docs/program/ai-visibility/geo/content/comparisons/leadpilot_vs_instantly.md:64 | Vectorae | A-current | product name in prose/UI | low |
| docs/program/ai-visibility/geo/content/comparisons/leadpilot_vs_instantly.md:65 | Vectorae | A-current | product name in prose/UI | low |
| docs/program/ai-visibility/geo/content/comparisons/leadpilot_vs_instantly.md:67 | Vectorae | A-current | product name in prose/UI | low |
| docs/program/ai-visibility/geo/content/comparisons/leadpilot_vs_instantly.md:67 | Calendarharvest(name) | C | company/site name ("Vectorae by Calendarharvest"); human decides if it survives rebrand | brand/legal naming decision |
| docs/program/ai-visibility/geo/content/comparisons/leadpilot_vs_instantly.md:67 | LeadPilot | EXCL | refers to a DIFFERENT company/product (LeadPilot AB, Lead Pilot/Twenty Over Ten, other "LeadPilot" products) | do NOT rename; blind replace corrupts disambiguation copy |
| docs/program/ai-visibility/geo/content/comparisons/leadpilot_vs_instantly.md:67 | leadpilot | EXCL | leadpilot.com = LeadPilot AB's domain (third party) | do NOT rename |
| docs/program/ai-visibility/geo/content/comparisons/leadpilot_vs_instantly.md:74 | Vectorae | A-current | product name in prose/UI | low |
| docs/program/ai-visibility/geo/content/comparisons/leadpilot_vs_smartlead.md:2 | leadpilot | B | public URL slug on calendarharvest.com (indexed, in sitemap/llms.txt) | SEO + inbound links; needs 301 redirects |
| docs/program/ai-visibility/geo/content/comparisons/leadpilot_vs_smartlead.md:7 | Vectorae | A-current | product name in prose/UI | low |
| docs/program/ai-visibility/geo/content/comparisons/leadpilot_vs_smartlead.md:9 | Vectorae | A-current | product name in prose/UI ×2 | low |
| docs/program/ai-visibility/geo/content/comparisons/leadpilot_vs_smartlead.md:13 | Vectorae | A-current | product name in prose/UI | low |
| docs/program/ai-visibility/geo/content/comparisons/leadpilot_vs_smartlead.md:14 | Calendarharvest(name) | C | company/site name ("Vectorae by Calendarharvest"); human decides if it survives rebrand | brand/legal naming decision |
| docs/program/ai-visibility/geo/content/comparisons/leadpilot_vs_smartlead.md:18 | Vectorae | A-current | product name in prose/UI | low |
| docs/program/ai-visibility/geo/content/comparisons/leadpilot_vs_smartlead.md:20 | Vectorae | A-current | product name in prose/UI | low |
| docs/program/ai-visibility/geo/content/comparisons/leadpilot_vs_smartlead.md:34 | Vectorae | A-current | product name in prose/UI | low |
| docs/program/ai-visibility/geo/content/comparisons/leadpilot_vs_smartlead.md:48 | Vectorae | A-current | product name in prose/UI | low |
| docs/program/ai-visibility/geo/content/comparisons/leadpilot_vs_smartlead.md:61 | Vectorae | A-current | product name in prose/UI | low |
| docs/program/ai-visibility/geo/content/comparisons/leadpilot_vs_smartlead.md:63 | Vectorae | A-current | product name in prose/UI | low |
| docs/program/ai-visibility/geo/content/comparisons/leadpilot_vs_smartlead.md:65 | Vectorae | A-current | product name in prose/UI | low |
| docs/program/ai-visibility/geo/content/comparisons/leadpilot_vs_smartlead.md:65 | Calendarharvest(name) | C | company/site name ("Vectorae by Calendarharvest"); human decides if it survives rebrand | brand/legal naming decision |
| docs/program/ai-visibility/geo/content/comparisons/leadpilot_vs_smartlead.md:65 | LeadPilot | EXCL | refers to a DIFFERENT company/product (LeadPilot AB, Lead Pilot/Twenty Over Ten, other "LeadPilot" products) | do NOT rename; blind replace corrupts disambiguation copy |
| docs/program/ai-visibility/geo/content/comparisons/leadpilot_vs_smartlead.md:65 | leadpilot | EXCL | leadpilot.com = LeadPilot AB's domain (third party) | do NOT rename |
| docs/program/ai-visibility/geo/content/comparisons/leadpilot_vs_smartlead.md:71 | Vectorae | A-current | product name in prose/UI | low |
| docs/program/ai-visibility/geo/content/definitions/leadpilot_use_cases.md:L9,11,13,18,37,49,51,55,62,69,74,88-89,95,104,109,119,126,133,138,140,149,156,164,169,179,185,194,199,201,210,220,223,228,239,244,250,256,264,266,269,275,280,282,290,301,306,314-315,323 (51 occurrences) | Vectorae | A-current | product name in prose/UI | low |
| docs/program/ai-visibility/geo/content/definitions/leadpilot_use_cases.md:11 | Calendarharvest(name) | C | company/site name ("Vectorae by Calendarharvest"); human decides if it survives rebrand | brand/legal naming decision |
| docs/program/ai-visibility/geo/content/definitions/what_is_leadpilot.md:2 | leadpilot | B | public URL slug on calendarharvest.com (indexed, in sitemap/llms.txt) | SEO + inbound links; needs 301 redirects |
| docs/program/ai-visibility/geo/content/definitions/what_is_leadpilot.md:L8,10,12,19,21,25,29,34,41,44,48,58,60,70,75,80,84,86,92,104-105,108 (22 occurrences) | Vectorae | A-current | product name in prose/UI | low |
| docs/program/ai-visibility/geo/content/definitions/what_is_leadpilot.md:8 | Calendarharvest(name) | C | company/site name ("Vectorae by Calendarharvest"); human decides if it survives rebrand | brand/legal naming decision |
| docs/program/ai-visibility/geo/content/definitions/what_is_leadpilot.md:10 | Calendarharvest(name) | C | company/site name ("Vectorae by Calendarharvest"); human decides if it survives rebrand | brand/legal naming decision |
| docs/program/ai-visibility/geo/content/definitions/what_is_leadpilot.md:90 | Calendarharvest(name) | C | company/site name ("Vectorae by Calendarharvest"); human decides if it survives rebrand | brand/legal naming decision |
| docs/program/ai-visibility/geo/content/definitions/what_is_leadpilot.md:104 | Calendarharvest(name) | C | company/site name ("Vectorae by Calendarharvest"); human decides if it survives rebrand | brand/legal naming decision |
| docs/program/ai-visibility/geo/content/definitions/what_is_leadpilot.md:104 | LeadPilot | EXCL | refers to a DIFFERENT company/product (LeadPilot AB, Lead Pilot/Twenty Over Ten, other "LeadPilot" products) | do NOT rename; blind replace corrupts disambiguation copy |
| docs/program/ai-visibility/geo/content/definitions/what_is_leadpilot.md:105 | Calendarharvest(name) | C | company/site name ("Vectorae by Calendarharvest"); human decides if it survives rebrand | brand/legal naming decision |
| docs/program/ai-visibility/geo/content/definitions/what_is_leadpilot.md:105 | LeadPilot | EXCL | refers to a DIFFERENT company/product (LeadPilot AB, Lead Pilot/Twenty Over Ten, other "LeadPilot" products) | do NOT rename; blind replace corrupts disambiguation copy |
| docs/program/ai-visibility/geo/content/definitions/what_is_leadpilot.md:106 | leadpilot | EXCL | leadpilot.com = LeadPilot AB's domain (third party) | do NOT rename |
| docs/program/ai-visibility/geo/content/definitions/what_is_leadpilot.md:107 | LeadPilot | EXCL | refers to a DIFFERENT company/product (LeadPilot AB, Lead Pilot/Twenty Over Ten, other "LeadPilot" products) | do NOT rename; blind replace corrupts disambiguation copy |
| docs/program/ai-visibility/geo/content/definitions/what_is_leadpilot.md:107 | Lead Pilot | EXCL | refers to a DIFFERENT company/product (LeadPilot AB, Lead Pilot/Twenty Over Ten, other "LeadPilot" products) | do NOT rename; blind replace corrupts disambiguation copy |
| docs/program/ai-visibility/geo/content/definitions/what_is_leadpilot.md:108 | Calendarharvest(name) | C | company/site name ("Vectorae by Calendarharvest"); human decides if it survives rebrand | brand/legal naming decision |
| docs/program/ai-visibility/geo/content/definitions/what_is_leadpilot.md:109 | leadpilot | C | our third-party listing/profile handle (LinkedIn/G2/Crunchbase/GetApp/YouTube) | external listing; renaming is a manual platform action, URL may change |
| docs/program/ai-visibility/geo/content/faq_library.md:L9,11,13-14,21,23,30-31,37,42,44-45,51,53,66-67,73-74,76,88-89,91,97,106,110,114,123,127,131,133,137,143,148,151,158,160,162,164,167,169,173,175,178,180,183,185-187,190-191,193,195,199,207,216,222,227,231 (58 occurrences) | Vectorae | A-current | product name in prose/UI | low |
| docs/program/ai-visibility/geo/content/faq_library.md:14 | Calendarharvest(name) | C | company/site name ("Vectorae by Calendarharvest"); human decides if it survives rebrand | brand/legal naming decision |
| docs/program/ai-visibility/geo/content/faq_library.md:45 | Calendarharvest(name) | C | company/site name ("Vectorae by Calendarharvest"); human decides if it survives rebrand | brand/legal naming decision |
| docs/program/ai-visibility/geo/content/faq_library.md:47 | LeadPilot | EXCL | refers to a DIFFERENT company/product (LeadPilot AB, Lead Pilot/Twenty Over Ten, other "LeadPilot" products) | do NOT rename; blind replace corrupts disambiguation copy |
| docs/program/ai-visibility/geo/content/faq_library.md:47 | leadpilot | EXCL | leadpilot.com = LeadPilot AB's domain (third party) | do NOT rename |
| docs/program/ai-visibility/geo/content/faq_library.md:48 | LeadPilot | EXCL | refers to a DIFFERENT company/product (LeadPilot AB, Lead Pilot/Twenty Over Ten, other "LeadPilot" products) | do NOT rename; blind replace corrupts disambiguation copy |
| docs/program/ai-visibility/geo/content/faq_library.md:48 | Lead Pilot | EXCL | refers to a DIFFERENT company/product (LeadPilot AB, Lead Pilot/Twenty Over Ten, other "LeadPilot" products) | do NOT rename; blind replace corrupts disambiguation copy |
| docs/program/ai-visibility/geo/content/faq_library.md:204 | Calendarharvest(name) | C | company/site name ("Vectorae by Calendarharvest"); human decides if it survives rebrand | brand/legal naming decision |
| docs/program/ai-visibility/geo/content/faq_library.md:211 | Calendarharvest(name) | C | company/site name ("Vectorae by Calendarharvest"); human decides if it survives rebrand | brand/legal naming decision |
| docs/program/ai-visibility/geo/content/statistics_and_proof.md:11 | Vectorae | A-current | product name in prose/UI | low |
| docs/program/ai-visibility/geo/content/statistics_and_proof.md:11 | Calendarharvest(name) | C | company/site name ("Vectorae by Calendarharvest"); human decides if it survives rebrand | brand/legal naming decision |
| docs/program/ai-visibility/geo/content/statistics_and_proof.md:26 | Vectorae | A-current | product name in prose/UI | low |
| docs/program/ai-visibility/geo/content/statistics_and_proof.md:35 | Vectorae | A-current | product name in prose/UI | low |
| docs/program/ai-visibility/geo/content/statistics_and_proof.md:77 | Vectorae | A-current | product name in prose/UI | low |
| docs/program/ai-visibility/geo/content/statistics_and_proof.md:79 | Vectorae | A-current | product name in prose/UI | low |
| docs/program/ai-visibility/geo/content/statistics_and_proof.md:90 | Vectorae | A-current | product name in prose/UI | low |
| docs/program/ai-visibility/geo/content/statistics_and_proof.md:92 | Vectorae | A-current | product name in prose/UI | low |
| docs/program/ai-visibility/geo/entity_card.md:L1,16,18,25,28,30,37,53,69-70,73,116,131-135,137,141,147,149 (24 occurrences) | Vectorae | A-current | product name in prose/UI | low |
| docs/program/ai-visibility/geo/entity_card.md:16 | LeadPilot | A-current | alias/old-name list for our product (entity card "do not use" column) ×2 | low |
| docs/program/ai-visibility/geo/entity_card.md:16 | Lead Pilot | A-current | alias/old-name list for our product (entity card "do not use" column) | low |
| docs/program/ai-visibility/geo/entity_card.md:17 | Calendarharvest(name) | C | company/site name ("Vectorae by Calendarharvest"); human decides if it survives rebrand | brand/legal naming decision |
| docs/program/ai-visibility/geo/entity_card.md:17 | Calendarharvest(name) | C | company/site name ("Vectorae by Calendarharvest"); human decides if it survives rebrand | brand/legal naming decision |
| docs/program/ai-visibility/geo/entity_card.md:18 | Calendarharvest(name) | C | company/site name ("Vectorae by Calendarharvest"); human decides if it survives rebrand | brand/legal naming decision |
| docs/program/ai-visibility/geo/entity_card.md:18 | LeadPilot | EXCL | refers to a DIFFERENT company/product (LeadPilot AB, Lead Pilot/Twenty Over Ten, other "LeadPilot" products) | do NOT rename; blind replace corrupts disambiguation copy |
| docs/program/ai-visibility/geo/entity_card.md:19 | LeadPilot | EXCL | refers to a DIFFERENT company/product (LeadPilot AB, Lead Pilot/Twenty Over Ten, other "LeadPilot" products) | do NOT rename; blind replace corrupts disambiguation copy |
| docs/program/ai-visibility/geo/entity_card.md:19 | leadpilot | EXCL | leadpilot.com = LeadPilot AB's domain (third party) | do NOT rename |
| docs/program/ai-visibility/geo/entity_card.md:20 | LeadPilot | EXCL | refers to a DIFFERENT company/product (LeadPilot AB, Lead Pilot/Twenty Over Ten, other "LeadPilot" products) | do NOT rename; blind replace corrupts disambiguation copy |
| docs/program/ai-visibility/geo/entity_card.md:20 | leadpilot | C | our third-party listing/profile handle (LinkedIn/G2/Crunchbase/GetApp/YouTube) | external listing; renaming is a manual platform action, URL may change |
| docs/program/ai-visibility/geo/entity_card.md:20 | leadpilot | EXCL | refers to a DIFFERENT company/product (LeadPilot AB, Lead Pilot/Twenty Over Ten, other "LeadPilot" products) | do NOT rename; blind replace corrupts disambiguation copy |
| docs/program/ai-visibility/geo/entity_card.md:25 | Calendarharvest(name) | C | company/site name ("Vectorae by Calendarharvest"); human decides if it survives rebrand | brand/legal naming decision |
| docs/program/ai-visibility/geo/entity_card.md:25 | LeadPilot | EXCL | refers to a DIFFERENT company/product (LeadPilot AB, Lead Pilot/Twenty Over Ten, other "LeadPilot" products) | do NOT rename; blind replace corrupts disambiguation copy |
| docs/program/ai-visibility/geo/entity_card.md:26 | leadpilot | EXCL | leadpilot.com = LeadPilot AB's domain (third party) | do NOT rename |
| docs/program/ai-visibility/geo/entity_card.md:30 | Calendarharvest(name) | C | company/site name ("Vectorae by Calendarharvest"); human decides if it survives rebrand | brand/legal naming decision |
| docs/program/ai-visibility/geo/entity_card.md:141 | Calendarharvest(name) | C | company/site name ("Vectorae by Calendarharvest"); human decides if it survives rebrand | brand/legal naming decision |
| docs/program/ai-visibility/geo/entity_card.md:142 | leadpilot | B | file name / file-path reference (repo file or help-center slug) | links + scripts (geo_audit.py, help-center ids) break if file renamed |
| docs/program/ai-visibility/geo/entity_card.md:145 | leadpilot | B | file name / file-path reference (repo file or help-center slug) | links + scripts (geo_audit.py, help-center ids) break if file renamed |
| docs/program/ai-visibility/geo/monitoring/ai_mention_tracker.md:14 | Vectorae | A-current | product name in prose/UI | low |
| docs/program/ai-visibility/geo/monitoring/ai_mention_tracker.md:17 | LeadPilot | EXCL | refers to a DIFFERENT company/product (LeadPilot AB, Lead Pilot/Twenty Over Ten, other "LeadPilot" products) | do NOT rename; blind replace corrupts disambiguation copy |
| docs/program/ai-visibility/geo/monitoring/ai_mention_tracker.md:17 | LeadPilot | EXCL | refers to a DIFFERENT company/product (LeadPilot AB, Lead Pilot/Twenty Over Ten, other "LeadPilot" products) | do NOT rename; blind replace corrupts disambiguation copy |
| docs/program/ai-visibility/geo/monitoring/ai_mention_tracker.md:43 | Vectorae | A-current | product name in prose/UI | low |
| docs/program/ai-visibility/geo/monitoring/ai_mention_tracker.md:44 | Vectorae | A-current | product name in prose/UI | low |
| docs/program/ai-visibility/geo/monitoring/ai_mention_tracker.md:44 | Calendarharvest(name) | C | company/site name ("Vectorae by Calendarharvest"); human decides if it survives rebrand | brand/legal naming decision |
| docs/program/ai-visibility/geo/monitoring/ai_mention_tracker.md:45 | Vectorae | A-current | product name in prose/UI | low |
| docs/program/ai-visibility/geo/monitoring/ai_mention_tracker.md:45 | Calendarharvest(name) | C | company/site name ("Vectorae by Calendarharvest"); human decides if it survives rebrand | brand/legal naming decision |
| docs/program/ai-visibility/geo/monitoring/ai_mention_tracker.md:46 | Vectorae | A-current | product name in prose/UI | low |
| docs/program/ai-visibility/geo/monitoring/ai_mention_tracker.md:47 | Vectorae | A-current | product name in prose/UI | low |
| docs/program/ai-visibility/geo/monitoring/ai_mention_tracker.md:47 | LeadPilot | EXCL | refers to a DIFFERENT company/product (LeadPilot AB, Lead Pilot/Twenty Over Ten, other "LeadPilot" products) | do NOT rename; blind replace corrupts disambiguation copy |
| docs/program/ai-visibility/geo/monitoring/ai_mention_tracker.md:79 | Vectorae | A-current | product name in prose/UI | low |
| docs/program/ai-visibility/geo/monitoring/ai_mention_tracker.md:79 | Calendarharvest(name) | C | company/site name ("Vectorae by Calendarharvest"); human decides if it survives rebrand | brand/legal naming decision |
| docs/program/ai-visibility/geo/monitoring/ai_mention_tracker.md:81 | LeadPilot | EXCL | refers to a DIFFERENT company/product (LeadPilot AB, Lead Pilot/Twenty Over Ten, other "LeadPilot" products) | do NOT rename; blind replace corrupts disambiguation copy |
| docs/program/ai-visibility/geo/monitoring/ai_mention_tracker.md:81 | LeadPilot | EXCL | refers to a DIFFERENT company/product (LeadPilot AB, Lead Pilot/Twenty Over Ten, other "LeadPilot" products) | do NOT rename; blind replace corrupts disambiguation copy |
| docs/program/ai-visibility/geo/monitoring/ai_mention_tracker.md:81 | LeadPilot | EXCL | refers to a DIFFERENT company/product (LeadPilot AB, Lead Pilot/Twenty Over Ten, other "LeadPilot" products) | do NOT rename; blind replace corrupts disambiguation copy |
| docs/program/ai-visibility/geo/monitoring/ai_mention_tracker.md:81 | LeadPilot | EXCL | refers to a DIFFERENT company/product (LeadPilot AB, Lead Pilot/Twenty Over Ten, other "LeadPilot" products) | do NOT rename; blind replace corrupts disambiguation copy |
| docs/program/ai-visibility/geo/monitoring/ai_mention_tracker.md:81 | Calendarharvest(name) | C | company/site name ("Vectorae by Calendarharvest"); human decides if it survives rebrand | brand/legal naming decision |
| docs/program/ai-visibility/geo/monitoring/ai_mention_tracker.md:81 | LeadPilot | A-current | former product name in prose | low |
| docs/program/ai-visibility/geo/monitoring/ai_mention_tracker.md:81 | leadpilot | EXCL | refers to a DIFFERENT company/product (LeadPilot AB, Lead Pilot/Twenty Over Ten, other "LeadPilot" products) | do NOT rename; blind replace corrupts disambiguation copy |
| docs/program/ai-visibility/geo/monitoring/ai_mention_tracker.md:83 | LeadPilot | EXCL | refers to a DIFFERENT company/product (LeadPilot AB, Lead Pilot/Twenty Over Ten, other "LeadPilot" products) | do NOT rename; blind replace corrupts disambiguation copy |
| docs/program/ai-visibility/geo/monitoring/ai_mention_tracker.md:83 | LeadPilot | EXCL | refers to a DIFFERENT company/product (LeadPilot AB, Lead Pilot/Twenty Over Ten, other "LeadPilot" products) | do NOT rename; blind replace corrupts disambiguation copy |
| docs/program/ai-visibility/geo/monitoring/ai_mention_tracker.md:83 | LeadPilot | EXCL | refers to a DIFFERENT company/product (LeadPilot AB, Lead Pilot/Twenty Over Ten, other "LeadPilot" products) | do NOT rename; blind replace corrupts disambiguation copy |
| docs/program/ai-visibility/geo/monitoring/ai_mention_tracker.md:92 | Vectorae | A-current | product name in prose/UI | low |
| docs/program/ai-visibility/geo/monitoring/ai_mention_tracker.md:92 | LeadPilot | EXCL | refers to a DIFFERENT company/product (LeadPilot AB, Lead Pilot/Twenty Over Ten, other "LeadPilot" products) | do NOT rename; blind replace corrupts disambiguation copy |
| docs/program/ai-visibility/geo/monitoring/ai_mention_tracker.md:95 | LeadPilot | EXCL | refers to a DIFFERENT company/product (LeadPilot AB, Lead Pilot/Twenty Over Ten, other "LeadPilot" products) | do NOT rename; blind replace corrupts disambiguation copy |
| docs/program/ai-visibility/geo/monitoring/ai_mention_tracker.md:95 | LeadPilot | EXCL | refers to a DIFFERENT company/product (LeadPilot AB, Lead Pilot/Twenty Over Ten, other "LeadPilot" products) | do NOT rename; blind replace corrupts disambiguation copy |
| docs/program/ai-visibility/geo/monitoring/ai_mention_tracker.md:104 | LeadPilot | EXCL | refers to a DIFFERENT company/product (LeadPilot AB, Lead Pilot/Twenty Over Ten, other "LeadPilot" products) | do NOT rename; blind replace corrupts disambiguation copy |
| docs/program/ai-visibility/geo/monitoring/ai_mention_tracker.md:107 | Vectorae | A-current | product name in prose/UI | low |
| docs/program/ai-visibility/geo/platforms/chatgpt_bing_playbook.md:3 | Vectorae | A-current | product name in prose/UI | low |
| docs/program/ai-visibility/geo/platforms/chatgpt_bing_playbook.md:4 | Vectorae | A-current | product name in prose/UI | low |
| docs/program/ai-visibility/geo/platforms/chatgpt_bing_playbook.md:39 | Vectorae | A-current | product name in prose/UI | low |
| docs/program/ai-visibility/geo/platforms/chatgpt_bing_playbook.md:43 | Vectorae | A-current | product name in prose/UI | low |
| docs/program/ai-visibility/geo/platforms/chatgpt_bing_playbook.md:43 | Calendarharvest(name) | C | company/site name ("Vectorae by Calendarharvest"); human decides if it survives rebrand | brand/legal naming decision |
| docs/program/ai-visibility/geo/platforms/chatgpt_bing_playbook.md:55 | Vectorae | A-current | product name in prose/UI | low |
| docs/program/ai-visibility/geo/platforms/chatgpt_bing_playbook.md:58 | Vectorae | A-current | product name in prose/UI | low |
| docs/program/ai-visibility/geo/platforms/chatgpt_bing_playbook.md:58 | Calendarharvest(name) | C | company/site name ("Vectorae by Calendarharvest"); human decides if it survives rebrand | brand/legal naming decision |
| docs/program/ai-visibility/geo/platforms/chatgpt_bing_playbook.md:61 | Calendarharvest(name) | C | company/site name ("Vectorae by Calendarharvest"); human decides if it survives rebrand | brand/legal naming decision |
| docs/program/ai-visibility/geo/platforms/chatgpt_bing_playbook.md:69 | Vectorae | A-current | product name in prose/UI | low |
| docs/program/ai-visibility/geo/platforms/chatgpt_bing_playbook.md:69 | Calendarharvest(name) | C | company/site name ("Vectorae by Calendarharvest"); human decides if it survives rebrand | brand/legal naming decision |
| docs/program/ai-visibility/geo/platforms/chatgpt_bing_playbook.md:72 | Vectorae | A-current | product name in prose/UI | low |
| docs/program/ai-visibility/geo/platforms/chatgpt_bing_playbook.md:82 | Vectorae | A-current | product name in prose/UI | low |
| docs/program/ai-visibility/geo/platforms/chatgpt_bing_playbook.md:83 | Vectorae | A-current | product name in prose/UI | low |
| docs/program/ai-visibility/geo/platforms/chatgpt_bing_playbook.md:83 | Calendarharvest(name) | C | company/site name ("Vectorae by Calendarharvest"); human decides if it survives rebrand | brand/legal naming decision |
| docs/program/ai-visibility/geo/platforms/claude_playbook.md:5 | Vectorae | A-current | product name in prose/UI | low |
| docs/program/ai-visibility/geo/platforms/claude_playbook.md:11 | Vectorae | A-current | product name in prose/UI | low |
| docs/program/ai-visibility/geo/platforms/claude_playbook.md:25 | Vectorae | A-current | product name in prose/UI | low |
| docs/program/ai-visibility/geo/platforms/claude_playbook.md:34 | Vectorae | A-current | product name in prose/UI | low |
| docs/program/ai-visibility/geo/platforms/claude_playbook.md:52 | Vectorae | A-current | product name in prose/UI | low |
| docs/program/ai-visibility/geo/platforms/claude_playbook.md:53 | clienthunter | B | PyPI package / CLI command name (sdk/) | published package + user scripts |
| docs/program/ai-visibility/geo/platforms/claude_playbook.md:54 | Vectorae | A-current | product name in prose/UI | low |
| docs/program/ai-visibility/geo/platforms/claude_playbook.md:58 | Vectorae | A-current | product name in prose/UI | low |
| docs/program/ai-visibility/geo/platforms/claude_playbook.md:58 | Calendarharvest(name) | C | company/site name ("Vectorae by Calendarharvest"); human decides if it survives rebrand | brand/legal naming decision |
| docs/program/ai-visibility/geo/platforms/claude_playbook.md:59 | Vectorae | A-current | product name in prose/UI | low |
| docs/program/ai-visibility/geo/platforms/claude_playbook.md:60 | LeadPilot | EXCL | refers to a DIFFERENT company/product (LeadPilot AB, Lead Pilot/Twenty Over Ten, other "LeadPilot" products) | do NOT rename; blind replace corrupts disambiguation copy |
| docs/program/ai-visibility/geo/platforms/emerging_ai_playbook.md:11 | Vectorae | A-current | product name in prose/UI | low |
| docs/program/ai-visibility/geo/platforms/emerging_ai_playbook.md:19 | LeadPilot | EXCL | refers to a DIFFERENT company/product (LeadPilot AB, Lead Pilot/Twenty Over Ten, other "LeadPilot" products) | do NOT rename; blind replace corrupts disambiguation copy |
| docs/program/ai-visibility/geo/platforms/emerging_ai_playbook.md:20 | Vectorae | A-current | product name in prose/UI | low |
| docs/program/ai-visibility/geo/platforms/emerging_ai_playbook.md:20 | Calendarharvest(name) | C | company/site name ("Vectorae by Calendarharvest"); human decides if it survives rebrand | brand/legal naming decision |
| docs/program/ai-visibility/geo/platforms/emerging_ai_playbook.md:48 | LeadPilot | C | our third-party listing/profile handle (LinkedIn/G2/Crunchbase/GetApp/YouTube) | external listing; renaming is a manual platform action, URL may change |
| docs/program/ai-visibility/geo/platforms/emerging_ai_playbook.md:65 | Vectorae | A-current | product name in prose/UI | low |
| docs/program/ai-visibility/geo/platforms/emerging_ai_playbook.md:66 | Vectorae | A-current | product name in prose/UI | low |
| docs/program/ai-visibility/geo/platforms/emerging_ai_playbook.md:67 | Calendarharvest(name) | C | company/site name ("Vectorae by Calendarharvest"); human decides if it survives rebrand | brand/legal naming decision |
| docs/program/ai-visibility/geo/platforms/gemini_playbook.md:24 | Vectorae | A-current | product name in prose/UI | low |
| docs/program/ai-visibility/geo/platforms/gemini_playbook.md:24 | Calendarharvest(name) | C | company/site name ("Vectorae by Calendarharvest"); human decides if it survives rebrand | brand/legal naming decision |
| docs/program/ai-visibility/geo/platforms/gemini_playbook.md:38 | Vectorae | A-current | product name in prose/UI | low |
| docs/program/ai-visibility/geo/platforms/gemini_playbook.md:38 | Calendarharvest(name) | C | company/site name ("Vectorae by Calendarharvest"); human decides if it survives rebrand | brand/legal naming decision |
| docs/program/ai-visibility/geo/platforms/gemini_playbook.md:48 | LeadPilot | EXCL | refers to a DIFFERENT company/product (LeadPilot AB, Lead Pilot/Twenty Over Ten, other "LeadPilot" products) | do NOT rename; blind replace corrupts disambiguation copy |
| docs/program/ai-visibility/geo/platforms/gemini_playbook.md:60 | Vectorae | A-current | product name in prose/UI | low |
| docs/program/ai-visibility/geo/platforms/gemini_playbook.md:65 | Vectorae | A-current | product name in prose/UI ×2 | low |
| docs/program/ai-visibility/geo/platforms/gemini_playbook.md:66 | Vectorae | A-current | product name in prose/UI | low |
| docs/program/ai-visibility/geo/platforms/gemini_playbook.md:73 | Vectorae | A-current | product name in prose/UI | low |
| docs/program/ai-visibility/geo/platforms/perplexity_playbook.md:12 | Vectorae | A-current | product name in prose/UI | low |
| docs/program/ai-visibility/geo/platforms/perplexity_playbook.md:30 | Vectorae | A-current | product name in prose/UI | low |
| docs/program/ai-visibility/geo/platforms/perplexity_playbook.md:36 | Vectorae | A-current | product name in prose/UI | low |
| docs/program/ai-visibility/geo/platforms/perplexity_playbook.md:37 | Vectorae | A-current | product name in prose/UI | low |
| docs/program/ai-visibility/geo/platforms/perplexity_playbook.md:39 | Vectorae | A-current | product name in prose/UI | low |
| docs/program/ai-visibility/geo/platforms/perplexity_playbook.md:44 | Vectorae | A-current | product name in prose/UI | low |
| docs/program/ai-visibility/geo/platforms/perplexity_playbook.md:44 | Calendarharvest(name) | C | company/site name ("Vectorae by Calendarharvest"); human decides if it survives rebrand | brand/legal naming decision |
| docs/program/ai-visibility/geo/platforms/perplexity_playbook.md:48 | Vectorae | A-current | product name in prose/UI | low |
| docs/program/ai-visibility/geo/platforms/perplexity_playbook.md:54 | Vectorae | A-current | product name in prose/UI | low |
| docs/program/ai-visibility/geo/platforms/perplexity_playbook.md:54 | Calendarharvest(name) | C | company/site name ("Vectorae by Calendarharvest"); human decides if it survives rebrand | brand/legal naming decision |
| docs/program/ai-visibility/geo/platforms/perplexity_playbook.md:54 | leadpilot | C | our third-party listing/profile handle (LinkedIn/G2/Crunchbase/GetApp/YouTube) | external listing; renaming is a manual platform action, URL may change |
| docs/program/ai-visibility/geo/platforms/perplexity_playbook.md:54 | LeadPilot | EXCL | refers to a DIFFERENT company/product (LeadPilot AB, Lead Pilot/Twenty Over Ten, other "LeadPilot" products) | do NOT rename; blind replace corrupts disambiguation copy |
| docs/program/ai-visibility/geo/platforms/perplexity_playbook.md:64 | Vectorae | A-current | product name in prose/UI | low |
| docs/program/ai-visibility/geo/positioning/niche_statement.md:5 | Vectorae | A-current | product name in prose/UI | low |
| docs/program/ai-visibility/geo/positioning/niche_statement.md:9 | Vectorae | A-current | product name in prose/UI | low |
| docs/program/ai-visibility/geo/positioning/niche_statement.md:30 | Vectorae | A-current | product name in prose/UI | low |
| docs/program/ai-visibility/geo/positioning/niche_statement.md:30 | Calendarharvest(name) | C | company/site name ("Vectorae by Calendarharvest"); human decides if it survives rebrand | brand/legal naming decision |
| docs/program/ai-visibility/geo/positioning/niche_statement.md:46 | Vectorae | A-current | product name in prose/UI | low |
| docs/program/ai-visibility/geo/positioning/niche_statement.md:46 | Calendarharvest(name) | C | company/site name ("Vectorae by Calendarharvest"); human decides if it survives rebrand | brand/legal naming decision |
| docs/program/ai-visibility/geo/positioning/niche_statement.md:56 | leadpilot | B | file name / file-path reference (repo file or help-center slug) | links + scripts (geo_audit.py, help-center ids) break if file renamed |
| docs/program/ai-visibility/geo/positioning/niche_statement.md:56 | leadpilot | B | file name / file-path reference (repo file or help-center slug) | links + scripts (geo_audit.py, help-center ids) break if file renamed |
| docs/program/ai-visibility/geo/questions.md:19 | Vectorae | A-historical | product name in prose/UI | renaming falsifies a dated record |
| docs/program/ai-visibility/geo/questions.md:29 | Vectorae | A-historical | product name in prose/UI | renaming falsifies a dated record |
| docs/program/ai-visibility/geo/questions.md:30 | Vectorae | A-historical | product name in prose/UI | renaming falsifies a dated record |
| docs/program/ai-visibility/geo/questions.md:41 | LeadPilot | A-historical | former product name in prose | renaming falsifies a dated record |
| docs/program/ai-visibility/geo/questions.md:42 | LeadPilot | EXCL | refers to a DIFFERENT company/product (LeadPilot AB, Lead Pilot/Twenty Over Ten, other "LeadPilot" products) | do NOT rename; blind replace corrupts disambiguation copy |
| docs/program/ai-visibility/geo/questions.md:42 | leadpilot | EXCL | leadpilot.com = LeadPilot AB's domain (third party) | do NOT rename |
| docs/program/ai-visibility/geo/questions.md:42 | Lead Pilot | EXCL | refers to a DIFFERENT company/product (LeadPilot AB, Lead Pilot/Twenty Over Ten, other "LeadPilot" products) | do NOT rename; blind replace corrupts disambiguation copy |
| docs/program/ai-visibility/geo/questions.md:43 | Vectorae | A-historical | product name in prose/UI | renaming falsifies a dated record |
| docs/program/ai-visibility/geo/questions.md:43 | Calendarharvest(name) | C | company/site name ("Vectorae by Calendarharvest"); human decides if it survives rebrand | brand/legal naming decision |
| docs/program/ai-visibility/geo/questions.md:49 | Calendarharvest(name) | C | company/site name ("Vectorae by Calendarharvest"); human decides if it survives rebrand | brand/legal naming decision |
| docs/program/ai-visibility/geo/questions.md:49 | Calendarharvest(name) | C | company/site name ("Vectorae by Calendarharvest"); human decides if it survives rebrand | brand/legal naming decision |
| docs/program/ai-visibility/geo/questions.md:50 | Calendarharvest(name) | C | company/site name ("Vectorae by Calendarharvest"); human decides if it survives rebrand | brand/legal naming decision |
| docs/program/ai-visibility/geo/questions.md:50 | Calendarharvest(name) | C | company/site name ("Vectorae by Calendarharvest"); human decides if it survives rebrand | brand/legal naming decision |
| docs/program/ai-visibility/geo/questions.md:51 | Calendarharvest(name) | C | company/site name ("Vectorae by Calendarharvest"); human decides if it survives rebrand | brand/legal naming decision |
| docs/program/ai-visibility/geo/questions.md:52 | Calendarharvest(name) | C | company/site name ("Vectorae by Calendarharvest"); human decides if it survives rebrand | brand/legal naming decision |
| docs/program/ai-visibility/geo/questions.md:58 | Vectorae | A-historical | product name in prose/UI | renaming falsifies a dated record |
| docs/program/ai-visibility/geo/questions.md:67 | leadpilot | C | our third-party listing/profile handle (LinkedIn/G2/Crunchbase/GetApp/YouTube) | external listing; renaming is a manual platform action, URL may change |
| docs/program/ai-visibility/geo/questions.md:95 | Calendarharvest(name) | C | company/site name ("Vectorae by Calendarharvest"); human decides if it survives rebrand | brand/legal naming decision |
| docs/program/ai-visibility/geo/questions.md:101 | Vectorae | A-historical | product name in prose/UI | renaming falsifies a dated record |
| docs/program/ai-visibility/geo/questions.md:102 | Calendarharvest(name) | C | company/site name ("Vectorae by Calendarharvest"); human decides if it survives rebrand | brand/legal naming decision |
| docs/program/ai-visibility/geo/questions.md:105 | Vectorae | A-historical | product name in prose/UI | renaming falsifies a dated record |
| docs/program/ai-visibility/geo/questions.md:105 | LeadPilot | EXCL | refers to a DIFFERENT company/product (LeadPilot AB, Lead Pilot/Twenty Over Ten, other "LeadPilot" products) | do NOT rename; blind replace corrupts disambiguation copy |
| docs/program/ai-visibility/geo/questions.md:118 | clienthunter | B | PyPI package / CLI command name (sdk/) | published package + user scripts |
| docs/program/ai-visibility/geo/research/ai_search_mechanics_factcheck.md:14 | Calendarharvest(name) | C | company/site name ("Vectorae by Calendarharvest"); human decides if it survives rebrand | brand/legal naming decision |
| docs/program/ai-visibility/geo/research/ai_search_mechanics_factcheck.md:15 | Calendarharvest(name) | C | company/site name ("Vectorae by Calendarharvest"); human decides if it survives rebrand | brand/legal naming decision |
| docs/program/ai-visibility/geo/research/competitor_analysis.md:24 | leadpilot | C | our third-party listing/profile handle (LinkedIn/G2/Crunchbase/GetApp/YouTube) | external listing; renaming is a manual platform action, URL may change |
| docs/program/ai-visibility/geo/research/competitor_analysis.md:24 | leadpilot | C | our third-party listing/profile handle (LinkedIn/G2/Crunchbase/GetApp/YouTube) | external listing; renaming is a manual platform action, URL may change |
| docs/program/ai-visibility/geo/research/competitor_analysis.md:24 | leadpilot | C | our third-party listing/profile handle (LinkedIn/G2/Crunchbase/GetApp/YouTube) | external listing; renaming is a manual platform action, URL may change |
| docs/program/ai-visibility/geo/research/competitor_analysis.md:24 | leadpilot | C | our third-party listing/profile handle (LinkedIn/G2/Crunchbase/GetApp/YouTube) | external listing; renaming is a manual platform action, URL may change |
| docs/program/ai-visibility/geo/research/competitor_analysis.md:24 | LeadPilot | C | our third-party listing/profile handle (LinkedIn/G2/Crunchbase/GetApp/YouTube) | external listing; renaming is a manual platform action, URL may change |
| docs/program/ai-visibility/geo/research/competitor_analysis.md:24 | Calendarharvest(name) | C | company/site name ("Vectorae by Calendarharvest"); human decides if it survives rebrand | brand/legal naming decision |
| docs/program/ai-visibility/geo/research/competitor_analysis.md:24 | LeadPilot | EXCL | refers to a DIFFERENT company/product (LeadPilot AB, Lead Pilot/Twenty Over Ten, other "LeadPilot" products) | do NOT rename; blind replace corrupts disambiguation copy |
| docs/program/ai-visibility/geo/research/competitor_analysis.md:L26,29,37,42-44,49,64,66,70,83-85,93,95,105-106,117,120,126,149,165,167,180-181 (26 occurrences) | Vectorae | A-historical | product name in prose/UI | renaming falsifies a dated record |
| docs/program/ai-visibility/geo/research/competitor_analysis.md:149 | Calendarharvest(name) | C | company/site name ("Vectorae by Calendarharvest"); human decides if it survives rebrand | brand/legal naming decision |
| docs/program/ai-visibility/geo/research/competitor_analysis.md:170 | LeadPilot | A-historical | former product name in prose | renaming falsifies a dated record |
| docs/program/ai-visibility/geo/research/competitor_analysis.md:173 | LeadPilot | EXCL | refers to a DIFFERENT company/product (LeadPilot AB, Lead Pilot/Twenty Over Ten, other "LeadPilot" products) | do NOT rename; blind replace corrupts disambiguation copy |
| docs/program/ai-visibility/geo/research/competitor_analysis.md:173 | leadpilot | EXCL | leadpilot.com = LeadPilot AB's domain (third party) | do NOT rename |
| docs/program/ai-visibility/geo/research/competitor_analysis.md:173 | leadpilot | EXCL | refers to a DIFFERENT company/product (LeadPilot AB, Lead Pilot/Twenty Over Ten, other "LeadPilot" products) | do NOT rename; blind replace corrupts disambiguation copy |
| docs/program/ai-visibility/geo/research/competitor_analysis.md:174 | LeadPilot | EXCL | refers to a DIFFERENT company/product (LeadPilot AB, Lead Pilot/Twenty Over Ten, other "LeadPilot" products) | do NOT rename; blind replace corrupts disambiguation copy |
| docs/program/ai-visibility/geo/research/competitor_analysis.md:175 | LeadPilot | EXCL | refers to a DIFFERENT company/product (LeadPilot AB, Lead Pilot/Twenty Over Ten, other "LeadPilot" products) | do NOT rename; blind replace corrupts disambiguation copy |
| docs/program/ai-visibility/geo/research/competitor_analysis.md:177 | Lead Pilot | EXCL | refers to a DIFFERENT company/product (LeadPilot AB, Lead Pilot/Twenty Over Ten, other "LeadPilot" products) | do NOT rename; blind replace corrupts disambiguation copy |
| docs/program/ai-visibility/geo/research/competitor_analysis.md:178 | LeadPilot | EXCL | refers to a DIFFERENT company/product (LeadPilot AB, Lead Pilot/Twenty Over Ten, other "LeadPilot" products) | do NOT rename; blind replace corrupts disambiguation copy |
| docs/program/ai-visibility/geo/research/competitor_analysis.md:178 | leadpilot | EXCL | refers to a DIFFERENT company/product (LeadPilot AB, Lead Pilot/Twenty Over Ten, other "LeadPilot" products) | do NOT rename; blind replace corrupts disambiguation copy |
| docs/program/ai-visibility/geo/research/competitor_analysis.md:178 | Lead Pilot | EXCL | refers to a DIFFERENT company/product (LeadPilot AB, Lead Pilot/Twenty Over Ten, other "LeadPilot" products) | do NOT rename; blind replace corrupts disambiguation copy |
| docs/program/ai-visibility/geo/research/competitor_analysis.md:181 | Calendarharvest(name) | C | company/site name ("Vectorae by Calendarharvest"); human decides if it survives rebrand | brand/legal naming decision |
| docs/program/ai-visibility/geo/research/competitor_analysis.md:181 | LeadPilot | EXCL | refers to a DIFFERENT company/product (LeadPilot AB, Lead Pilot/Twenty Over Ten, other "LeadPilot" products) | do NOT rename; blind replace corrupts disambiguation copy |
| docs/program/ai-visibility/geo/research/query_library.md:1 | Vectorae | A-historical | product name in prose/UI | renaming falsifies a dated record |
| docs/program/ai-visibility/geo/research/query_library.md:7 | Vectorae | A-historical | product name in prose/UI | renaming falsifies a dated record |
| docs/program/ai-visibility/geo/research/query_library.md:9 | Vectorae | A-historical | product name in prose/UI | renaming falsifies a dated record |
| docs/program/ai-visibility/geo/research/query_library.md:12 | Vectorae | A-historical | product name in prose/UI | renaming falsifies a dated record |
| docs/program/ai-visibility/geo/research/query_library.md:27 | leadpilot | B | file name / file-path reference (repo file or help-center slug) | links + scripts (geo_audit.py, help-center ids) break if file renamed |
| docs/program/ai-visibility/geo/research/query_library.md:32 | leadpilot | B | file name / file-path reference (repo file or help-center slug) | links + scripts (geo_audit.py, help-center ids) break if file renamed |
| docs/program/ai-visibility/geo/research/query_library.md:43 | leadpilot | B | file name / file-path reference (repo file or help-center slug) | links + scripts (geo_audit.py, help-center ids) break if file renamed |
| docs/program/ai-visibility/geo/research/query_library.md:44 | leadpilot | B | file name / file-path reference (repo file or help-center slug) | links + scripts (geo_audit.py, help-center ids) break if file renamed |
| docs/program/ai-visibility/geo/research/query_library.md:45 | leadpilot | B | file name / file-path reference (repo file or help-center slug) | links + scripts (geo_audit.py, help-center ids) break if file renamed |
| docs/program/ai-visibility/geo/research/query_library.md:47 | leadpilot | B | file name / file-path reference (repo file or help-center slug) | links + scripts (geo_audit.py, help-center ids) break if file renamed |
| docs/program/ai-visibility/geo/research/query_library.md:49 | leadpilot | B | file name / file-path reference (repo file or help-center slug) | links + scripts (geo_audit.py, help-center ids) break if file renamed |
| docs/program/ai-visibility/geo/research/query_library.md:50 | leadpilot | B | file name / file-path reference (repo file or help-center slug) | links + scripts (geo_audit.py, help-center ids) break if file renamed |
| docs/program/ai-visibility/geo/research/query_library.md:58 | Vectorae | A-historical | product name in prose/UI | renaming falsifies a dated record |
| docs/program/ai-visibility/geo/research/query_library.md:58 | leadpilot | B | file name / file-path reference (repo file or help-center slug) | links + scripts (geo_audit.py, help-center ids) break if file renamed |
| docs/program/ai-visibility/geo/research/query_library.md:59 | Vectorae | A-historical | product name in prose/UI | renaming falsifies a dated record |
| docs/program/ai-visibility/geo/research/query_library.md:59 | leadpilot | B | file name / file-path reference (repo file or help-center slug) | links + scripts (geo_audit.py, help-center ids) break if file renamed |
| docs/program/ai-visibility/geo/research/query_library.md:59 | Calendarharvest(name) | C | company/site name ("Vectorae by Calendarharvest"); human decides if it survives rebrand | brand/legal naming decision |
| docs/program/ai-visibility/geo/research/query_library.md:60 | leadpilot | B | file name / file-path reference (repo file or help-center slug) | links + scripts (geo_audit.py, help-center ids) break if file renamed |
| docs/program/ai-visibility/geo/research/query_library.md:61 | leadpilot | B | file name / file-path reference (repo file or help-center slug) | links + scripts (geo_audit.py, help-center ids) break if file renamed |
| docs/program/ai-visibility/geo/research/query_library.md:62 | leadpilot | B | file name / file-path reference (repo file or help-center slug) | links + scripts (geo_audit.py, help-center ids) break if file renamed |
| docs/program/ai-visibility/geo/research/query_library.md:63 | Vectorae | A-historical | product name in prose/UI | renaming falsifies a dated record |
| docs/program/ai-visibility/geo/research/query_library.md:63 | leadpilot | B | file name / file-path reference (repo file or help-center slug) | links + scripts (geo_audit.py, help-center ids) break if file renamed |
| docs/program/ai-visibility/geo/research/query_library.md:64 | leadpilot | B | file name / file-path reference (repo file or help-center slug) | links + scripts (geo_audit.py, help-center ids) break if file renamed |
| docs/program/ai-visibility/geo/research/query_library.md:65 | Vectorae | A-historical | product name in prose/UI | renaming falsifies a dated record |
| docs/program/ai-visibility/geo/research/query_library.md:65 | LeadPilot | EXCL | refers to a DIFFERENT company/product (LeadPilot AB, Lead Pilot/Twenty Over Ten, other "LeadPilot" products) | do NOT rename; blind replace corrupts disambiguation copy |
| docs/program/ai-visibility/geo/research/query_library.md:66 | leadpilot | B | file name / file-path reference (repo file or help-center slug) | links + scripts (geo_audit.py, help-center ids) break if file renamed |
| docs/program/ai-visibility/geo/research/query_library.md:88 | leadpilot | B | file name / file-path reference (repo file or help-center slug) | links + scripts (geo_audit.py, help-center ids) break if file renamed |
| docs/program/ai-visibility/geo/research/query_library.md:91 | leadpilot | B | file name / file-path reference (repo file or help-center slug) | links + scripts (geo_audit.py, help-center ids) break if file renamed |
| docs/program/ai-visibility/geo/research/query_library.md:101 | Vectorae | A-historical | product name in prose/UI | renaming falsifies a dated record |
| docs/program/ai-visibility/geo/state.md:1 | Vectorae | A-historical | product name in prose/UI | renaming falsifies a dated record |
| docs/program/ai-visibility/geo/state.md:30 | Vectorae | A-historical | product name in prose/UI | renaming falsifies a dated record |
| docs/program/ai-visibility/geo/state.md:33 | LeadPilot | A-historical | former product name in prose | renaming falsifies a dated record |
| docs/program/ai-visibility/geo/state.md:33 | LeadPilot | EXCL | refers to a DIFFERENT company/product (LeadPilot AB, Lead Pilot/Twenty Over Ten, other "LeadPilot" products) | do NOT rename; blind replace corrupts disambiguation copy |
| docs/program/ai-visibility/geo/state.md:33 | leadpilot | EXCL | leadpilot.com = LeadPilot AB's domain (third party) | do NOT rename |
| docs/program/ai-visibility/geo/state.md:50 | leadpilot | B | file name / file-path reference (repo file or help-center slug) | links + scripts (geo_audit.py, help-center ids) break if file renamed |
| docs/program/ai-visibility/geo/state.md:50 | leadpilot | B | file name / file-path reference (repo file or help-center slug) | links + scripts (geo_audit.py, help-center ids) break if file renamed |
| docs/program/ai-visibility/geo/state.md:57 | Vectorae | A-historical | product name in prose/UI | renaming falsifies a dated record |
| docs/program/ai-visibility/geo/state.md:57 | Calendarharvest(name) | C | company/site name ("Vectorae by Calendarharvest"); human decides if it survives rebrand | brand/legal naming decision |
| docs/program/ai-visibility/geo/state.md:58 | LeadPilot | EXCL | refers to a DIFFERENT company/product (LeadPilot AB, Lead Pilot/Twenty Over Ten, other "LeadPilot" products) | do NOT rename; blind replace corrupts disambiguation copy |
| docs/program/ai-visibility/geo/state.md:58 | LeadPilot | EXCL | refers to a DIFFERENT company/product (LeadPilot AB, Lead Pilot/Twenty Over Ten, other "LeadPilot" products) | do NOT rename; blind replace corrupts disambiguation copy |
| docs/program/ai-visibility/geo/state.md:58 | LeadPilot | EXCL | refers to a DIFFERENT company/product (LeadPilot AB, Lead Pilot/Twenty Over Ten, other "LeadPilot" products) | do NOT rename; blind replace corrupts disambiguation copy |
| docs/program/ai-visibility/geo/state.md:79 | Vectorae | A-historical | product name in prose/UI | renaming falsifies a dated record |
| docs/program/ai-visibility/geo/state.md:126 | Calendarharvest(name) | C | company/site name ("Vectorae by Calendarharvest"); human decides if it survives rebrand | brand/legal naming decision |
| docs/program/ai-visibility/geo/state.md:136 | Vectorae | A-historical | product name in prose/UI | renaming falsifies a dated record |
| docs/program/ai-visibility/geo/state.md:137 | leadpilot | B | file name / file-path reference (repo file or help-center slug) | links + scripts (geo_audit.py, help-center ids) break if file renamed |
| docs/program/ai-visibility/geo/state.md:141 | leadpilot | B | file name / file-path reference (repo file or help-center slug) | links + scripts (geo_audit.py, help-center ids) break if file renamed |
| docs/program/ai-visibility/geo/state.md:142 | Vectorae | A-historical | product name in prose/UI | renaming falsifies a dated record |
| docs/program/ai-visibility/geo/state.md:143 | Vectorae | A-historical | product name in prose/UI | renaming falsifies a dated record |
| docs/program/ai-visibility/geo/state.md:156 | LeadPilot | A-historical | former product name in prose | renaming falsifies a dated record |
| docs/program/ai-visibility/geo/state.md:156 | LeadPilot | EXCL | refers to a DIFFERENT company/product (LeadPilot AB, Lead Pilot/Twenty Over Ten, other "LeadPilot" products) | do NOT rename; blind replace corrupts disambiguation copy |
| docs/program/ai-visibility/geo/state.md:184 | leadpilot | B | public URL slug on calendarharvest.com (indexed, in sitemap/llms.txt) | SEO + inbound links; needs 301 redirects |
| docs/program/ai-visibility/geo/state.md:186 | leadpilot | B | public URL slug on calendarharvest.com (indexed, in sitemap/llms.txt) | SEO + inbound links; needs 301 redirects |
| docs/program/ai-visibility/geo/state.md:207 | leadpilot | B | public URL slug on calendarharvest.com (indexed, in sitemap/llms.txt) | SEO + inbound links; needs 301 redirects |
| docs/program/ai-visibility/geo/state.md:213 | Vectorae | A-historical | product name in prose/UI | renaming falsifies a dated record |
| docs/program/ai-visibility/geo/state.md:213 | Calendarharvest(name) | C | company/site name ("Vectorae by Calendarharvest"); human decides if it survives rebrand | brand/legal naming decision |
| docs/program/ai-visibility/geo/state.md:214 | LeadPilot | EXCL | refers to a DIFFERENT company/product (LeadPilot AB, Lead Pilot/Twenty Over Ten, other "LeadPilot" products) | do NOT rename; blind replace corrupts disambiguation copy |
| docs/program/ai-visibility/geo/state.md:214 | leadpilot | C | our third-party listing/profile handle (LinkedIn/G2/Crunchbase/GetApp/YouTube) | external listing; renaming is a manual platform action, URL may change |
| docs/program/ai-visibility/geo/technical/crawler_access_strategy.md:122 | leadpilot | B | public URL slug on calendarharvest.com (indexed, in sitemap/llms.txt) | SEO + inbound links; needs 301 redirects |
| docs/program/ai-visibility/geo/technical/crawler_access_strategy.md:123 | leadpilot | B | public URL slug on calendarharvest.com (indexed, in sitemap/llms.txt) | SEO + inbound links; needs 301 redirects |
| docs/program/ai-visibility/geo/technical/crawler_access_strategy.md:124 | leadpilot | B | public URL slug on calendarharvest.com (indexed, in sitemap/llms.txt) | SEO + inbound links; needs 301 redirects |
| docs/program/ai-visibility/geo/technical/crawler_access_strategy.md:131 | leadpilot | B | public URL slug on calendarharvest.com (indexed, in sitemap/llms.txt) | SEO + inbound links; needs 301 redirects |
| docs/program/ai-visibility/geo/technical/crawler_access_strategy.md:131 | leadpilot | B | public URL slug on calendarharvest.com (indexed, in sitemap/llms.txt) | SEO + inbound links; needs 301 redirects |
| docs/program/ai-visibility/geo/technical/crawler_access_strategy.md:131 | leadpilot | B | public URL slug on calendarharvest.com (indexed, in sitemap/llms.txt) | SEO + inbound links; needs 301 redirects |
| docs/program/ai-visibility/geo/technical/crawler_access_strategy.md:137 | leadpilot | B | public URL slug on calendarharvest.com (indexed, in sitemap/llms.txt) | SEO + inbound links; needs 301 redirects |
| docs/program/ai-visibility/geo/technical/crawler_access_strategy.md:157 | Vectorae | A-current | product name in prose/UI | low |
| docs/program/ai-visibility/geo/technical/crawler_access_strategy.md:157 | Calendarharvest(name) | C | company/site name ("Vectorae by Calendarharvest"); human decides if it survives rebrand | brand/legal naming decision |
| docs/program/ai-visibility/geo/technical/crawler_access_strategy.md:158 | Vectorae | A-current | product name in prose/UI | low |
| docs/program/ai-visibility/geo/technical/crawler_access_strategy.md:158 | Calendarharvest(name) | C | company/site name ("Vectorae by Calendarharvest"); human decides if it survives rebrand | brand/legal naming decision |
| docs/program/ai-visibility/geo/technical/crawler_access_strategy.md:161 | Vectorae | A-current | product name in prose/UI ×4 | low |
| docs/program/ai-visibility/geo/technical/crawler_access_strategy.md:163 | Calendarharvest(name) | C | company/site name ("Vectorae by Calendarharvest"); human decides if it survives rebrand | brand/legal naming decision |
| docs/program/ai-visibility/geo/technical/crawler_access_strategy.md:166 | Vectorae | A-current | product name in prose/UI | low |
| docs/program/ai-visibility/geo/technical/crawler_access_strategy.md:169 | leadpilot | B | public URL slug on calendarharvest.com (indexed, in sitemap/llms.txt) | SEO + inbound links; needs 301 redirects |
| docs/program/ai-visibility/geo/technical/crawler_access_strategy.md:169 | Vectorae | A-current | product name in prose/UI | low |
| docs/program/ai-visibility/geo/technical/crawler_access_strategy.md:170 | leadpilot | B | public URL slug on calendarharvest.com (indexed, in sitemap/llms.txt) | SEO + inbound links; needs 301 redirects |
| docs/program/ai-visibility/geo/technical/crawler_access_strategy.md:170 | Vectorae | A-current | product name in prose/UI | low |
| docs/program/ai-visibility/geo/technical/crawler_access_strategy.md:171 | leadpilot | B | public URL slug on calendarharvest.com (indexed, in sitemap/llms.txt) | SEO + inbound links; needs 301 redirects |
| docs/program/ai-visibility/geo/technical/crawler_access_strategy.md:171 | Vectorae | A-current | product name in prose/UI | low |
| docs/program/ai-visibility/geo/technical/crawler_access_strategy.md:185 | Vectorae | A-current | product name in prose/UI ×2 | low |
| docs/program/ai-visibility/geo/technical/crawler_access_strategy.md:185 | Calendarharvest(name) | C | company/site name ("Vectorae by Calendarharvest"); human decides if it survives rebrand | brand/legal naming decision |
| docs/program/ai-visibility/geo/technical/crawler_access_strategy.md:185 | Calendarharvest(name) | C | company/site name ("Vectorae by Calendarharvest"); human decides if it survives rebrand | brand/legal naming decision |
| docs/program/ai-visibility/geo/technical/crawler_access_strategy.md:185 | LeadPilot | EXCL | refers to a DIFFERENT company/product (LeadPilot AB, Lead Pilot/Twenty Over Ten, other "LeadPilot" products) | do NOT rename; blind replace corrupts disambiguation copy |
| docs/program/ai-visibility/geo/technical/crawler_access_strategy.md:185 | LeadPilot | EXCL | refers to a DIFFERENT company/product (LeadPilot AB, Lead Pilot/Twenty Over Ten, other "LeadPilot" products) | do NOT rename; blind replace corrupts disambiguation copy |
| docs/program/ai-visibility/geo/technical/crawler_access_strategy.md:185 | leadpilot | EXCL | leadpilot.com = LeadPilot AB's domain (third party) | do NOT rename |
| docs/program/ai-visibility/geo/technical/crawler_access_strategy.md:185 | Lead Pilot | EXCL | refers to a DIFFERENT company/product (LeadPilot AB, Lead Pilot/Twenty Over Ten, other "LeadPilot" products) | do NOT rename; blind replace corrupts disambiguation copy |
| docs/program/ai-visibility/geo/technical/schema_markup.md:36 | Calendarharvest(name) | C | company/site name ("Vectorae by Calendarharvest"); human decides if it survives rebrand | brand/legal naming decision |
| docs/program/ai-visibility/geo/technical/schema_markup.md:39 | Calendarharvest(name) | C | company/site name ("Vectorae by Calendarharvest"); human decides if it survives rebrand | brand/legal naming decision |
| docs/program/ai-visibility/geo/technical/schema_markup.md:L39,54,68-70,102,112-116,118,120-121,135,137,178,207-208,210,217,221,227 (23 occurrences) | Vectorae | A-current | product name in prose/UI | low |
| docs/program/ai-visibility/geo/technical/schema_markup.md:44 | leadpilot | C | our third-party listing/profile handle (LinkedIn/G2/Crunchbase/GetApp/YouTube) | external listing; renaming is a manual platform action, URL may change |
| docs/program/ai-visibility/geo/technical/schema_markup.md:47 | leadpilot | C | our third-party listing/profile handle (LinkedIn/G2/Crunchbase/GetApp/YouTube) | external listing; renaming is a manual platform action, URL may change |
| docs/program/ai-visibility/geo/technical/schema_markup.md:48 | leadpilot | C | our third-party listing/profile handle (LinkedIn/G2/Crunchbase/GetApp/YouTube) | external listing; renaming is a manual platform action, URL may change |
| docs/program/ai-visibility/geo/technical/schema_markup.md:49 | leadpilot | C | our third-party listing/profile handle (LinkedIn/G2/Crunchbase/GetApp/YouTube) | external listing; renaming is a manual platform action, URL may change |
| docs/program/ai-visibility/geo/technical/schema_markup.md:50 | LeadPilot | C | our third-party listing/profile handle (LinkedIn/G2/Crunchbase/GetApp/YouTube) | external listing; renaming is a manual platform action, URL may change |
| docs/program/ai-visibility/geo/technical/schema_markup.md:68 | Calendarharvest(name) | C | company/site name ("Vectorae by Calendarharvest"); human decides if it survives rebrand | brand/legal naming decision |
| docs/program/ai-visibility/geo/technical/schema_markup.md:70 | Calendarharvest(name) | C | company/site name ("Vectorae by Calendarharvest"); human decides if it survives rebrand | brand/legal naming decision |
| docs/program/ai-visibility/geo/technical/schema_markup.md:113 | Calendarharvest(name) | C | company/site name ("Vectorae by Calendarharvest"); human decides if it survives rebrand | brand/legal naming decision |
| docs/program/ai-visibility/geo/technical/schema_markup.md:119 | Calendarharvest(name) | C | company/site name ("Vectorae by Calendarharvest"); human decides if it survives rebrand | brand/legal naming decision |
| docs/program/ai-visibility/geo/technical/schema_markup.md:120 | Calendarharvest(name) | C | company/site name ("Vectorae by Calendarharvest"); human decides if it survives rebrand | brand/legal naming decision |
| docs/program/ai-visibility/geo/technical/schema_markup.md:120 | LeadPilot | EXCL | refers to a DIFFERENT company/product (LeadPilot AB, Lead Pilot/Twenty Over Ten, other "LeadPilot" products) | do NOT rename; blind replace corrupts disambiguation copy |
| docs/program/ai-visibility/geo/technical/schema_markup.md:121 | Calendarharvest(name) | C | company/site name ("Vectorae by Calendarharvest"); human decides if it survives rebrand | brand/legal naming decision |
| docs/program/ai-visibility/geo/technical/schema_markup.md:121 | LeadPilot | EXCL | refers to a DIFFERENT company/product (LeadPilot AB, Lead Pilot/Twenty Over Ten, other "LeadPilot" products) | do NOT rename; blind replace corrupts disambiguation copy |
| docs/program/ai-visibility/geo/technical/schema_markup.md:121 | leadpilot | EXCL | leadpilot.com = LeadPilot AB's domain (third party) | do NOT rename |
| docs/program/ai-visibility/geo/technical/schema_markup.md:135 | Calendarharvest(name) | C | company/site name ("Vectorae by Calendarharvest"); human decides if it survives rebrand | brand/legal naming decision |
| docs/program/ai-visibility/geo/technical/schema_markup.md:178 | Calendarharvest(name) | C | company/site name ("Vectorae by Calendarharvest"); human decides if it survives rebrand | brand/legal naming decision |
| docs/program/ai-visibility/geo/technical/schema_markup.md:208 | Calendarharvest(name) | C | company/site name ("Vectorae by Calendarharvest"); human decides if it survives rebrand | brand/legal naming decision |
| docs/program/ai-visibility/geo/technical/schema_markup.md:210 | Calendarharvest(name) | C | company/site name ("Vectorae by Calendarharvest"); human decides if it survives rebrand | brand/legal naming decision |
| docs/program/ai-visibility/geo/technical/site_architecture.md:23 | leadpilot | B | public URL slug on calendarharvest.com (indexed, in sitemap/llms.txt) | SEO + inbound links; needs 301 redirects |
| docs/program/ai-visibility/geo/technical/site_architecture.md:24 | leadpilot | B | public URL slug on calendarharvest.com (indexed, in sitemap/llms.txt) | SEO + inbound links; needs 301 redirects |
| docs/program/ai-visibility/geo/technical/site_architecture.md:25 | leadpilot | B | public URL slug on calendarharvest.com (indexed, in sitemap/llms.txt) | SEO + inbound links; needs 301 redirects |
| docs/program/ai-visibility/geo/technical/site_architecture.md:35 | leadpilot | B | public URL slug on calendarharvest.com (indexed, in sitemap/llms.txt) | SEO + inbound links; needs 301 redirects |
| docs/program/ai-visibility/geo/technical/site_architecture.md:35 | Vectorae | A-current | product name in prose/UI | low |
| docs/program/ai-visibility/geo/technical/site_architecture.md:38 | leadpilot | B | public URL slug on calendarharvest.com (indexed, in sitemap/llms.txt) | SEO + inbound links; needs 301 redirects |
| docs/program/ai-visibility/geo/technical/site_architecture.md:39 | leadpilot | B | public URL slug on calendarharvest.com (indexed, in sitemap/llms.txt) | SEO + inbound links; needs 301 redirects |
| docs/program/ai-visibility/geo/technical/site_architecture.md:47 | leadpilot | B | public URL slug on calendarharvest.com (indexed, in sitemap/llms.txt) | SEO + inbound links; needs 301 redirects |
| docs/program/ai-visibility/geo/technical/site_architecture.md:47 | Vectorae | A-current | product name in prose/UI | low |
| docs/program/ai-visibility/geo/technical/site_architecture.md:49 | leadpilot | B | public URL slug on calendarharvest.com (indexed, in sitemap/llms.txt) | SEO + inbound links; needs 301 redirects |
| docs/program/ai-visibility/geo/technical/site_architecture.md:50 | Vectorae | A-current | product name in prose/UI | low |
| docs/program/ai-visibility/geo/technical/site_architecture.md:56 | leadpilot | B | public URL slug on calendarharvest.com (indexed, in sitemap/llms.txt) | SEO + inbound links; needs 301 redirects |
| docs/program/ai-visibility/geo/technical/site_architecture.md:56 | leadpilot | B | file name / file-path reference (repo file or help-center slug) | links + scripts (geo_audit.py, help-center ids) break if file renamed |
| docs/program/ai-visibility/geo/technical/site_architecture.md:57 | leadpilot | B | public URL slug on calendarharvest.com (indexed, in sitemap/llms.txt) | SEO + inbound links; needs 301 redirects |
| docs/program/ai-visibility/geo/technical/site_architecture.md:57 | leadpilot | B | file name / file-path reference (repo file or help-center slug) | links + scripts (geo_audit.py, help-center ids) break if file renamed |
| docs/program/ai-visibility/geo/technical/site_architecture.md:58 | leadpilot | B | public URL slug on calendarharvest.com (indexed, in sitemap/llms.txt) | SEO + inbound links; needs 301 redirects |
| docs/program/ai-visibility/geo/technical/site_architecture.md:58 | leadpilot | B | file name / file-path reference (repo file or help-center slug) | links + scripts (geo_audit.py, help-center ids) break if file renamed |
| docs/program/ai-visibility/geo/technical/site_architecture.md:59 | leadpilot | B | public URL slug on calendarharvest.com (indexed, in sitemap/llms.txt) | SEO + inbound links; needs 301 redirects |
| docs/program/ai-visibility/geo/technical/site_architecture.md:59 | leadpilot | B | file name / file-path reference (repo file or help-center slug) | links + scripts (geo_audit.py, help-center ids) break if file renamed |
| docs/program/ai-visibility/geo/technical/site_architecture.md:60 | leadpilot | B | public URL slug on calendarharvest.com (indexed, in sitemap/llms.txt) | SEO + inbound links; needs 301 redirects |
| docs/program/ai-visibility/geo/technical/site_architecture.md:60 | leadpilot | B | file name / file-path reference (repo file or help-center slug) | links + scripts (geo_audit.py, help-center ids) break if file renamed |
| docs/program/ai-visibility/geo/technical/site_architecture.md:64 | leadpilot | B | public URL slug on calendarharvest.com (indexed, in sitemap/llms.txt) | SEO + inbound links; needs 301 redirects |
| docs/program/ai-visibility/geo/technical/site_architecture.md:64 | leadpilot | B | file name / file-path reference (repo file or help-center slug) | links + scripts (geo_audit.py, help-center ids) break if file renamed |
| docs/program/ai-visibility/geo/technical/site_architecture.md:78 | Vectorae | A-current | product name in prose/UI | low |
| docs/program/ai-visibility/geo/technical/site_architecture.md:79 | leadpilot | B | public URL slug on calendarharvest.com (indexed, in sitemap/llms.txt) | SEO + inbound links; needs 301 redirects |
| docs/program/ai-visibility/geo/technical/site_architecture.md:79 | Vectorae | A-current | product name in prose/UI | low |
| docs/program/ai-visibility/geo/technical/site_architecture.md:82 | Vectorae | A-current | product name in prose/UI ×3 | low |
| docs/program/ai-visibility/geo/technical/site_architecture.md:83 | Vectorae | A-current | product name in prose/UI ×2 | low |
| docs/program/ai-visibility/geo/technical/site_architecture.md:87 | leadpilot | B | public URL slug on calendarharvest.com (indexed, in sitemap/llms.txt) | SEO + inbound links; needs 301 redirects |
| docs/program/ai-visibility/geo/technical/site_architecture.md:88 | leadpilot | B | public URL slug on calendarharvest.com (indexed, in sitemap/llms.txt) | SEO + inbound links; needs 301 redirects |
| docs/program/ai-visibility/geo/technical/site_architecture.md:98 | leadpilot | B | public URL slug on calendarharvest.com (indexed, in sitemap/llms.txt) | SEO + inbound links; needs 301 redirects |
| docs/program/ai-visibility/geo/tools/geo_audit.py:8 | leadpilot | B | file name / file-path reference (repo file or help-center slug) | links + scripts (geo_audit.py, help-center ids) break if file renamed |
| docs/program/ai-visibility/geo/tools/geo_audit.py:8 | leadpilot | B | file name / file-path reference (repo file or help-center slug) | links + scripts (geo_audit.py, help-center ids) break if file renamed |
| docs/program/ai-visibility/geo/tools/geo_audit.py:13 | leadpilot | B | file name / file-path reference (repo file or help-center slug) | links + scripts (geo_audit.py, help-center ids) break if file renamed |
| docs/program/ai-visibility/geo/tools/geo_audit.py:21 | leadpilot | B | file name / file-path reference (repo file or help-center slug) | links + scripts (geo_audit.py, help-center ids) break if file renamed |
| docs/program/ai-visibility/geo/tools/geo_audit.py:44 | Vectorae | A-test | product name in prose/UI | low |
| docs/program/ai-visibility/geo/tools/geo_audit.py:44 | Calendarharvest(name) | C | company/site name ("Vectorae by Calendarharvest"); human decides if it survives rebrand | brand/legal naming decision |
| docs/program/ai-visibility/geo/tools/geo_audit.py:50 | Calendarharvest(name) | C | company/site name ("Vectorae by Calendarharvest"); human decides if it survives rebrand | brand/legal naming decision |
| docs/program/ai-visibility/geo/tools/geo_audit.py:52 | leadpilot | B | file name / file-path reference (repo file or help-center slug) | links + scripts (geo_audit.py, help-center ids) break if file renamed |
| docs/program/ai-visibility/geo/tools/geo_audit.py:53 | Vectorae | A-test | product name in prose/UI ×2 | low |
| docs/program/ai-visibility/geo/tools/geo_audit.py:53 | Calendarharvest(name) | C | company/site name ("Vectorae by Calendarharvest"); human decides if it survives rebrand | brand/legal naming decision |
| docs/program/ai-visibility/geo/tools/geo_audit.py:53 | Calendarharvest(name) | C | company/site name ("Vectorae by Calendarharvest"); human decides if it survives rebrand | brand/legal naming decision |
| docs/program/ai-visibility/geo/tools/geo_audit.py:55 | leadpilot | B | file name / file-path reference (repo file or help-center slug) | links + scripts (geo_audit.py, help-center ids) break if file renamed |
| docs/program/ai-visibility/geo/tools/geo_audit.py:55 | leadpilot | B | file name / file-path reference (repo file or help-center slug) | links + scripts (geo_audit.py, help-center ids) break if file renamed |
| docs/program/ai-visibility/geo/tools/geo_audit.py:57 | leadpilot | B | file name / file-path reference (repo file or help-center slug) | links + scripts (geo_audit.py, help-center ids) break if file renamed |
| docs/program/ai-visibility/geo/tools/geo_audit.py:58 | Vectorae | A-test | product name in prose/UI ×2 | low |
| docs/program/ai-visibility/geo/tools/geo_audit.py:58 | Calendarharvest(name) | C | company/site name ("Vectorae by Calendarharvest"); human decides if it survives rebrand | brand/legal naming decision |
| docs/program/ai-visibility/geo/tools/geo_audit.py:58 | Calendarharvest(name) | C | company/site name ("Vectorae by Calendarharvest"); human decides if it survives rebrand | brand/legal naming decision |
| docs/program/ai-visibility/geo/tools/geo_audit.py:59 | Vectorae | A-test | product name in prose/UI ×2 | low |
| docs/program/fixes/gaps-sweep-2.md:257 | ClientHunter | B | Python exception class name ClientHunterError (SDK/app API) | SDK users catching it |
| docs/program/fixes/gaps-sweep-2.md:333 | ClientHunter | B | Python exception class name ClientHunterError (SDK/app API) | SDK users catching it |
| docs/program/fixes/gaps-sweep-2.md:333 | ClientHunter | B | Python exception class name ClientHunterError (SDK/app API) | SDK users catching it |
| docs/program/fixes/gaps-sweep-2.md:370 | leadpilot | B | Postgres user/database name in a connection string | local/test DB identity |
| docs/program/fixes/gaps-sweep-2.md:370 | leadpilot | B | Postgres user/database name in a connection string | local/test DB identity |
| docs/program/fixes/gaps-sweep-2.md:370 | leadpilot | B | Postgres user/database name in a connection string | local/test DB identity |
| docs/program/fixes/gaps-sweep-2.md:370 | clienthunter | B | Postgres DB/user/container name | existing databases/containers keep the name |
| docs/program/fixes/gaps-sweep-2.md:370 | clienthunter | B | Postgres DB/user/container name | existing databases/containers keep the name |
| docs/program/fixes/gaps-sweep-2.md:384 | leadpilot | B | Postgres user/database name in a connection string | local/test DB identity |
| docs/program/fixes/gaps-sweep-2.md:384 | leadpilot | B | Postgres user/database name in a connection string | local/test DB identity |
| docs/program/fixes/gaps-sweep-2.md:384 | clienthunter | B | Postgres DB/user/container name | existing databases/containers keep the name |
| docs/program/fixes/platform-gaps.md:222 | Vectorae | A-historical | product name in prose/UI | renaming falsifies a dated record |
| docs/program/fixes/platform-gaps.md:224 | Vectorae | A-historical | product name in prose/UI | renaming falsifies a dated record |
| docs/program/fixes/platform-gaps.md:228 | Vectorae | A-historical | product name in prose/UI | renaming falsifies a dated record |
| docs/program/fixes/platform-gaps.md:300 | leadpilot | B | Celery task name prefix (leadpilot.*) | queued tasks/beat schedule/routing break |
| docs/program/fixes/platform-gaps.md:429 | leadpilot | B | Postgres user/database name in a connection string | local/test DB identity |
| docs/program/fixes/platform-gaps.md:429 | leadpilot | B | Postgres user/database name in a connection string | local/test DB identity |
| docs/program/fixes/platform-gaps.md:429 | clienthunter | B | Postgres DB/user/container name | existing databases/containers keep the name |
| docs/program/help-center-discoveries.md:75 | Vectorae | A-historical | product name in prose/UI | renaming falsifies a dated record |
| docs/program/help-center-eval.md:73 | leadpilot | B | file name / file-path reference (repo file or help-center slug) | links + scripts (geo_audit.py, help-center ids) break if file renamed |
| docs/program/help-center-eval.md:121 | Vectorae | A-historical | product name in prose/UI | renaming falsifies a dated record |
| docs/program/help-center-eval.md:190 | Vectorae | A-historical | product name in prose/UI | renaming falsifies a dated record |
| docs/program/help-center-factcheck.md:41 | leadpilot | B | file name / file-path reference (repo file or help-center slug) | links + scripts (geo_audit.py, help-center ids) break if file renamed |
| docs/program/help-center-factcheck.md:L44,46,51,56,58,61,63,67,74,77,81,93,101,103,106,109-110,112-113,115,122-123,125,128-129,143-144,146,149,157,161,164,173,186-187,189,208,218,221,223,235,239,266,269,271,274,290-291,302,317,327,329,331,371,376,396,406,409,414,416,419,424,429,456,458,469,480,492,500,502,506,508,519,522-524,526-527,530,544,552,554,564,578-579,584,586,592-593,604,607,612,617,620,624,632,637,702,714,717,721,735,744,754,757,762,775,780,789,799,802,817,825,841,856-857,874,881,891,922-924,926-927,929-930,947,958,970-971,983,994-995,1018,1023,1033,1036,1038,1041,1043,1054,1064-1065,1072,1076,1081,1095,1108,1111,1113,1120,1137,1143,1159,1170,1175,1184,1219,1222,1235,1240,1250,1270,1294,1299,1314,1316,1322,1358,1374,1410,1414-1415,1466,1477,1479,1485,1495,1500,1528-1529,1541,1549-1550,1555-1556,1560,1608,1614,1626,1635,1645,1647,1660,1670,1674,1676,1681,1691,1700,1765,1780,1795,1800,1804,1811,1825,1831,1869,1872-1873,1886,1895-1896,1978,2004,2013,2026-2027,2097,2152,2163,2170,2202,2346-2347,2355-2356,2361-2362,2392,2402,2440,2471,2478,2481-2482,2485,2493,2531,2536,2538,2541,2551,2564,2566-2567,2569,2589,2656,2669,2721-2722,2725,2752-2753,2763,2781,2783,2790-2792,2811,2813,2820-2821,2827,2832,2847,2855,2890,2894,2903,2928,2930,2933,2951,2963,2972,2997,3006,3020,3053-3054,3056,3100,3172,3184,3195,3281,3323,3335,3371,3385 (305 occurrences) | Vectorae | A-historical | product name in prose/UI | renaming falsifies a dated record |
| docs/program/help-center-factcheck.md:1088 | LeadPilot | B | webhook HTTP header name (X-LeadPilot-*) | customer webhook receivers verify on it |
| docs/program/help-center-factcheck.md:1095 | lpk_ | B | API key prefix (issued keys start with it) | existing customer keys + Zapier/Make configs break |
| docs/program/help-center-factcheck.md:1096 | lpk_ | B | API key prefix (issued keys start with it) | existing customer keys + Zapier/Make configs break |
| docs/program/help-center-factcheck.md:1421 | leadpilot | A-historical | user-visible export file name (quoted) ×2 | set in frontend/src/lib/profile.ts |
| docs/program/help-center-factcheck.md:1560 | lpk_ | B | API key prefix (issued keys start with it) | existing customer keys + Zapier/Make configs break |
| docs/program/help-center-factcheck.md:1626 | leadpilot | B | Celery task name prefix (leadpilot.*) | queued tasks/beat schedule/routing break |
| docs/program/help-center-factcheck.md:1670 | clienthunter | B | Android applicationId (com/io.clienthunter.app) | cannot change after Play publish |
| docs/program/help-center-factcheck.md:1810 | lpk_ | B | API key prefix (issued keys start with it) | existing customer keys + Zapier/Make configs break |
| docs/program/help-center-factcheck.md:2129 | LeadPilot | B | local checkout path (repo dir name) | machine path; historical |
| docs/program/help-center-factcheck.md:2327 | LeadPilot | B | local checkout path (repo dir name) | machine path; historical |
| docs/program/help-center-factcheck.md:2331 | LeadPilot | B | local checkout path (repo dir name) | machine path; historical |
| docs/program/help-center-factcheck.md:2332 | LeadPilot | B | local checkout path (repo dir name) | machine path; historical |
| docs/program/help-center-factcheck.md:2333 | LeadPilot | B | local checkout path (repo dir name) | machine path; historical |
| docs/program/help-center-factcheck.md:2519 | LeadPilot | B | local checkout path (repo dir name) | machine path; historical |
| docs/program/help-center-factcheck.md:2534 | Vectorae | B | LeadSource value written into customers' Salesforce (reports/filters depend on it) | customer CRM data/reporting |
| docs/program/help-center-factcheck.md:2608 | LeadPilot | B | webhook HTTP header name (X-LeadPilot-*) | customer webhook receivers verify on it |
| docs/program/help-center-factcheck.md:2608 | LeadPilot | B | webhook HTTP header name (X-LeadPilot-*) | customer webhook receivers verify on it |
| docs/program/help-center-factcheck.md:2608 | LeadPilot | B | webhook HTTP header name (X-LeadPilot-*) | customer webhook receivers verify on it |
| docs/program/help-center-factcheck.md:2608 | ClientHunter | B | legacy webhook header X-ClientHunter-Signature | customer receivers verifying the legacy header |
| docs/program/help-center-factcheck.md:2688 | LeadPilot | B | local checkout path (repo dir name) | machine path; historical |
| docs/program/help-center-factcheck.md:2876 | LeadPilot | B | local checkout path (repo dir name) | machine path; historical |
| docs/program/help-center-factcheck.md:2924 | LeadPilot | B | local checkout path (repo dir name) | machine path; historical |
| docs/program/help-center-factcheck.md:3014 | LeadPilot | B | webhook HTTP header name (X-LeadPilot-*) | customer webhook receivers verify on it |
| docs/program/help-center-factcheck.md:3014 | LeadPilot | B | webhook HTTP header name (X-LeadPilot-*) | customer webhook receivers verify on it |
| docs/program/help-center-factcheck.md:3015 | LeadPilot | B | webhook HTTP header name (X-LeadPilot-*) | customer webhook receivers verify on it |
| docs/program/help-center-factcheck.md:3017 | ClientHunter | B | legacy webhook header X-ClientHunter-Signature | customer receivers verifying the legacy header |
| docs/program/help-center-factcheck.md:3118 | LeadPilot | B | local checkout path (repo dir name) | machine path; historical |
| docs/program/help-center-factcheck.md:3118 | LeadPilot | B | local checkout path (repo dir name) | machine path; historical |
| docs/program/help-center-factcheck.md:3286 | LeadPilot | B | local checkout path (repo dir name) | machine path; historical |
| docs/program/help-center-factcheck.md:3286 | LeadPilot | B | local checkout path (repo dir name) | machine path; historical |
| docs/program/help-center-factcheck.md:3286 | LeadPilot | B | local checkout path (repo dir name) | machine path; historical |
| docs/program/help-center-factcheck.md:3286 | LeadPilot | B | local checkout path (repo dir name) | machine path; historical |
| docs/program/help-center-factcheck.md:3286 | LeadPilot | B | local checkout path (repo dir name) | machine path; historical |
| docs/program/help-center-factcheck.md:3286 | LeadPilot | B | local checkout path (repo dir name) | machine path; historical |
| docs/program/help-center-factcheck.md:3286 | LeadPilot | B | local checkout path (repo dir name) | machine path; historical |
| docs/program/help-center-factcheck.md:3286 | LeadPilot | B | local checkout path (repo dir name) | machine path; historical |
| docs/program/help-center-factcheck.md:3286 | LeadPilot | B | local checkout path (repo dir name) | machine path; historical |
| docs/program/help-center-factcheck.md:3286 | LeadPilot | B | local checkout path (repo dir name) | machine path; historical |
| docs/program/help-center-factcheck.md:3286 | LeadPilot | B | local checkout path (repo dir name) | machine path; historical |
| docs/program/help-center-factcheck.md:3292 | LeadPilot | B | local checkout path (repo dir name) | machine path; historical |
| docs/program/help-center-factcheck.md:3371 | LeadPilot | B | local checkout path (repo dir name) | machine path; historical |
| docs/program/help-center-factcheck.md:3371 | LeadPilot | B | local checkout path (repo dir name) | machine path; historical |
| docs/program/help-center-factcheck.md:3372 | LeadPilot | B | local checkout path (repo dir name) | machine path; historical |
| docs/program/help-center-factcheck.md:3372 | LeadPilot | B | local checkout path (repo dir name) | machine path; historical |
| docs/program/help-center-factcheck.md:3372 | LeadPilot | B | local checkout path (repo dir name) | machine path; historical |
| docs/program/help-center-factcheck.md:3373 | LeadPilot | B | local checkout path (repo dir name) | machine path; historical |
| docs/program/help-center-factcheck.md:3373 | LeadPilot | B | local checkout path (repo dir name) | machine path; historical |
| docs/program/help-center-factcheck.md:3373 | LeadPilot | B | local checkout path (repo dir name) | machine path; historical |
| docs/program/help-center-factcheck.md:3374 | LeadPilot | B | local checkout path (repo dir name) | machine path; historical |
| docs/program/help-center-factcheck.md:3374 | LeadPilot | B | local checkout path (repo dir name) | machine path; historical |
| docs/program/help-center-factcheck.md:3374 | LeadPilot | B | local checkout path (repo dir name) | machine path; historical |
| docs/program/help-center-factcheck.md:3383 | LeadPilot | B | local checkout path (repo dir name) | machine path; historical |
| docs/program/help-center-factcheck.md:3383 | LeadPilot | B | local checkout path (repo dir name) | machine path; historical |
| docs/program/help-center-factcheck.md:3383 | LeadPilot | B | local checkout path (repo dir name) | machine path; historical |
| docs/program/help-center-factcheck.md:3384 | LeadPilot | B | local checkout path (repo dir name) | machine path; historical |
| docs/program/help-center-factcheck.md:3385 | LeadPilot | B | local checkout path (repo dir name) | machine path; historical |
| docs/program/help-center-factcheck.md:3386 | LeadPilot | B | local checkout path (repo dir name) | machine path; historical |
| docs/program/help-center-factcheck.md:3386 | LeadPilot | B | local checkout path (repo dir name) | machine path; historical |
| docs/program/help-center-factcheck.md:3386 | LeadPilot | B | local checkout path (repo dir name) | machine path; historical |
| docs/program/plans/connector-00-recon.md:4 | Vectorae | A-historical | product name in prose/UI | renaming falsifies a dated record |
| docs/program/plans/connector-00-recon.md:27 | leadpilot | B | Celery task name prefix (leadpilot.*) | queued tasks/beat schedule/routing break |
| docs/program/plans/connector-00-recon.md:68 | lpk_ | B | API key prefix (issued keys start with it) | existing customer keys + Zapier/Make configs break |
| docs/program/plans/connector-00-recon.md:105 | Vectorae | A-historical | product name in prose/UI | renaming falsifies a dated record |
| docs/program/plans/connector-00-recon.md:109 | lpk_ | B | API key prefix (issued keys start with it) | existing customer keys + Zapier/Make configs break |
| docs/program/plans/connector-00-recon.md:158 | leadpilot | B | OAuth scope string (leadpilot:read/write) | issued tokens + connector clients |
| docs/program/plans/connector-00-recon.md:158 | leadpilot | B | OAuth scope string (leadpilot:read/write) | issued tokens + connector clients |
| docs/program/plans/connector-00-recon.md:286 | leadpilot | B | domain leadpilot.com / api.leadpilot.com used as our deploy config | domain is owned by LeadPilot AB (see entity_card) - stale/wrong config |
| docs/program/plans/connector-05-verification.md:69 | leadpilot | B | OAuth scope string (leadpilot:read/write) | issued tokens + connector clients |
| docs/program/plans/connector-05-verification.md:69 | leadpilot | B | OAuth scope string (leadpilot:read/write) | issued tokens + connector clients |
| docs/program/plans/help-ai-v2-00-recon.md:18 | leadpilot | B | file name / file-path reference (repo file or help-center slug) | links + scripts (geo_audit.py, help-center ids) break if file renamed |
| docs/program/plans/help-ai-v2-00-recon.md:43 | leadpilot | B | Render service name / onrender.com hostname | live service; renaming changes hostname |
| docs/program/plans/help-ai-v2-00-recon.md:48 | leadpilot | B | Render service name / onrender.com hostname | live service; renaming changes hostname |
| docs/program/plans/help-ai-v2-00-recon.md:55 | leadpilot | B | Render service name / onrender.com hostname | live service; renaming changes hostname |
| docs/program/plans/help-ai-v2-00-recon.md:77 | Vectorae | A-historical | product name in prose/UI | renaming falsifies a dated record |
| docs/program/plans/help-ai-v2-00-recon.md:92 | leadpilot | B | Render service name / onrender.com hostname | live service; renaming changes hostname |
| docs/program/plans/help-ai-v2-00-recon.md:92 | leadpilot | B | Render service name / onrender.com hostname | live service; renaming changes hostname |
| docs/program/plans/help-ai-v2-00-recon.md:170 | leadpilot | B | Render service name / onrender.com hostname | live service; renaming changes hostname |
| docs/program/plans/help-ai-v2-00-recon.md:177 | leadpilot | B | Render service name / onrender.com hostname | live service; renaming changes hostname |
| docs/program/plans/help-ai-v2-01-new-questions.md:L14-15,34,56-58,63,68,70,85-86,92,113,115,118,127 (17 occurrences) | Vectorae | A-historical | product name in prose/UI | renaming falsifies a dated record |
| docs/program/plans/help-ai-v2-01-new-questions.md:17 | vectorae | A-historical | product name in prose/UI | renaming falsifies a dated record |
| docs/program/plans/p0-5b-meter-every-call.md:6 | leadpilot | B | Celery task name prefix (leadpilot.*) | queued tasks/beat schedule/routing break |
| docs/program/plans/p0-d-enf-signup-switch.md:12 | Vectorae | A-historical | product name in prose/UI | renaming falsifies a dated record |
| docs/program/plans/phase1-01-integration-repair.md:5 | leadpilot | B | Postgres user/database name in a connection string | local/test DB identity |
| docs/program/plans/phase1-01-integration-repair.md:5 | leadpilot | B | Postgres user/database name in a connection string | local/test DB identity |
| docs/program/plans/phase1-01-integration-repair.md:5 | clienthunter | B | Postgres DB/user/container name | existing databases/containers keep the name |
| docs/program/plans/phase1-01b-pd1-webhook-schema.md:76 | leadpilot | B | Render service name / onrender.com hostname | live service; renaming changes hostname |
| docs/program/status.json:2 | Vectorae | A-historical | product name in prose/UI | renaming falsifies a dated record |
| docs/program/status.json:13 | LeadPilot | B | GitHub repo name / URL | links + CI + Render/Vercel git hooks |
| docs/program/status.json:14 | LeadPilot | B | GitHub repo name / URL | links + CI + Render/Vercel git hooks |
| docs/program/status.json:73 | LeadPilot | B | GitHub repo name / URL | links + CI + Render/Vercel git hooks |
| docs/program/status.json:85 | LeadPilot | B | GitHub repo name / URL | links + CI + Render/Vercel git hooks |
| docs/program/status.json:96 | LeadPilot | B | GitHub repo name / URL | links + CI + Render/Vercel git hooks |
| docs/program/status.json:97 | LeadPilot | B | GitHub repo name / URL | links + CI + Render/Vercel git hooks |
| docs/program/status.json:106 | LeadPilot | B | GitHub repo name / URL | links + CI + Render/Vercel git hooks |
| docs/program/status.json:114 | LeadPilot | B | GitHub repo name / URL | links + CI + Render/Vercel git hooks |
| docs/program/status.json:122 | LeadPilot | B | GitHub repo name / URL | links + CI + Render/Vercel git hooks |
| docs/program/status.json:129 | LeadPilot | B | GitHub repo name / URL | links + CI + Render/Vercel git hooks |
| docs/program/status.json:130 | LeadPilot | B | GitHub repo name / URL | links + CI + Render/Vercel git hooks |
| docs/program/status.json:138 | LeadPilot | B | GitHub repo name / URL | links + CI + Render/Vercel git hooks |
| docs/program/status.json:156 | LeadPilot | B | GitHub repo name / URL | links + CI + Render/Vercel git hooks |
| docs/program/status.json:250 | LeadPilot | B | GitHub repo name / URL | links + CI + Render/Vercel git hooks |
| reports/LP-T-002-tenancy-authz-audit.md:22 | leadpilot | B | domain leadpilot.io (quoted code comment; stale domain) | stale domain reference |
| reports/LP-T-004-launch-checklist-decomposition.md:121 | clienthunter | B | PyPI package / CLI command name (sdk/) | published package + user scripts |
| reports/LP-T-004-launch-checklist-decomposition.md:121 | clienthunter | B | PyPI package / CLI command name (sdk/) | published package + user scripts |
| reports/LP-T-004-launch-checklist-decomposition.md:122 | clienthunter | B | PyPI package / CLI command name (sdk/) | published package + user scripts |
| reports/LP-T-004-launch-checklist-decomposition.md:123 | clienthunter | B | PyPI package / CLI command name (sdk/) | published package + user scripts |
| reports/LP-T-004-launch-checklist-decomposition.md:138 | clienthunter | B | domain/email on clienthunter.* (not owned/used in prod) | stale domain reference |
| reports/LP-T-004-launch-checklist-decomposition.md:142 | ClientHunter | C | Play Store / launcher app name in a store checklist | store listing |
| reports/LP-T-004-launch-checklist-decomposition.md:153 | clienthunter | B | deep-link URL scheme (clienthunter://) | links in sent emails/push break |
| reports/LP-T-004-launch-checklist-decomposition.md:188 | leadpilot | B | local machine path | historical machine path |
| reports/LP-T-004-launch-checklist-decomposition.md:211 | clienthunter | B | PyPI package / CLI command name (sdk/) | published package + user scripts |
| reports/LP-T-004-launch-checklist-decomposition.md:237 | clienthunter | B | domain/email on clienthunter.* (not owned/used in prod) | stale domain reference |
| status-page/app/layout.tsx:11 | Vectorae | A-current | product name in prose/UI ×2 | low |
| status-page/app/layout.tsx:12 | Vectorae | A-current | product name in prose/UI | low |
| status-page/app/page.tsx:90 | Vectorae | A-current | product name in prose/UI | low |
| status-page/components/SiteChrome.tsx:7 | Vectorae | A-current | product name in prose/UI | low |
| status-page/components/SiteChrome.tsx:26 | Vectorae | A-current | product name in prose/UI ×2 | low |
| status-page/lib/backend.ts:2 | LEADPILOT | B | environment variable name (LEADPILOT_*) | deploy env config (Vercel/Render) must change in lockstep |
| status-page/lib/backend.ts:2 | Vectorae | A-comment | product name in prose/UI | low |
| status-page/lib/backend.ts:46 | LEADPILOT | B | environment variable name (LEADPILOT_*) | deploy env config (Vercel/Render) must change in lockstep |
| status-page/lib/config.ts:2 | Vectorae | A-comment | product name in prose/UI | low |
| status-page/lib/config.ts:29 | Vectorae | A-current | product name in prose/UI | low |
| status-page/lib/config.ts:65 | Vectorae | B | UptimeRobot monitor friendly_name, matched by exact string against the external account | status page shows No data unless monitors renamed in UptimeRobot in lockstep |
| status-page/lib/config.ts:66 | Vectorae | B | UptimeRobot monitor friendly_name, matched by exact string against the external account | status page shows No data unless monitors renamed in UptimeRobot in lockstep |
| status-page/lib/config.ts:67 | Vectorae | B | UptimeRobot monitor friendly_name, matched by exact string against the external account | status page shows No data unless monitors renamed in UptimeRobot in lockstep |
| status-page/lib/config.ts:68 | Vectorae | B | UptimeRobot monitor friendly_name, matched by exact string against the external account | status page shows No data unless monitors renamed in UptimeRobot in lockstep |
| status-page/lib/config.ts:69 | Vectorae | B | UptimeRobot monitor friendly_name, matched by exact string against the external account | status page shows No data unless monitors renamed in UptimeRobot in lockstep |
| status-page/lib/config.ts:70 | Vectorae | B | UptimeRobot monitor friendly_name, matched by exact string against the external account | status page shows No data unless monitors renamed in UptimeRobot in lockstep |
| status-page/lib/config.ts:97 | LEADPILOT | B | environment variable name (LEADPILOT_*) | deploy env config (Vercel/Render) must change in lockstep |
| status-page/lib/config.ts:105 | LEADPILOT | B | environment variable name (LEADPILOT_*) | deploy env config (Vercel/Render) must change in lockstep |
| status-page/lib/config.ts:105 | LEADPILOT | B | environment variable name (LEADPILOT_*) | deploy env config (Vercel/Render) must change in lockstep |
| status-page/lib/feeds.ts:7 | Vectorae | A-current | product name in prose/UI | low |
| status-page/lib/feeds.ts:54 | Vectorae | A-current | product name in prose/UI | low |
| status-page/lib/feeds.ts:92 | Vectorae | A-current | product name in prose/UI | low |
| status-page/lib/snapshot.ts:6 | Vectorae | A-comment | product name in prose/UI | low |
| status-page/lib/snapshot.ts:200 | Vectorae | A-current | product name in prose/UI | low |
| status-page/lib/snapshot.ts:201 | Vectorae | A-current | product name in prose/UI | low |
| status-page/lib/snapshot.ts:207 | Vectorae | A-current | product name in prose/UI | low |
| status-page/lib/uptimerobot.ts:3 | Vectorae | A-comment | product name in prose/UI | low |
| status-page/package-lock.json:2 | leadpilot | B | npm package name (status-page/package.json) | regenerates package-lock; low external impact (private) |
| status-page/package-lock.json:8 | leadpilot | B | npm package name (status-page/package.json) | regenerates package-lock; low external impact (private) |
| status-page/package.json:2 | leadpilot | B | npm package name (status-page/package.json) | regenerates package-lock; low external impact (private) |
| status-page/package.json:5 | Vectorae | A-current | product name in prose/UI | low |
| status-page/scripts/drill.ts:5 | LEADPILOT | B | environment variable name (LEADPILOT_*) | deploy env config (Vercel/Render) must change in lockstep |
| status-page/tests/snapshot.test.ts:8 | LEADPILOT | B | environment variable name (LEADPILOT_*) | deploy env config (Vercel/Render) must change in lockstep |
| status-page/tests/snapshot.test.ts:113 | LEADPILOT | B | environment variable name (LEADPILOT_*) | deploy env config (Vercel/Render) must change in lockstep |
| status-page/tests/snapshot.test.ts:210 | Vectorae | B | test asserts UptimeRobot monitor friendly_name (identifier) | move with config.ts |
| status-page/tests/sources.test.ts:78 | Vectorae | A-test | product name in prose/UI | low |
| status-page/tests/sources.test.ts:97 | LEADPILOT | B | environment variable name (LEADPILOT_*) | deploy env config (Vercel/Render) must change in lockstep |
| status-page/tests/sources.test.ts:98 | LEADPILOT | B | environment variable name (LEADPILOT_*) | deploy env config (Vercel/Render) must change in lockstep |
| status-page/tests/sources.test.ts:99 | LEADPILOT | B | environment variable name (LEADPILOT_*) | deploy env config (Vercel/Render) must change in lockstep |
| status-page/tests/sources.test.ts:111 | LEADPILOT | B | environment variable name (LEADPILOT_*) | deploy env config (Vercel/Render) must change in lockstep |

## 3. File/dir NAMES containing a variant

`git ls-files | grep -iE 'lead[ _.-]?pilot|client[ _.-]?hunter|vectorae'` restricted to this area (no directory names match; no root-level, status-page/ or reports/ file names match).

| path | variant | class | reason | risk |
|---|---|---|---|---|
| docs/program/ai-visibility/geo/content/comparisons/leadpilot_vs_apollo.md | leadpilot | B | repo file name; referenced by `geo/tools/geo_audit.py` (lines 8, 13 glob `leadpilot_vs_*.md`, 21, 52, 55, 57) and by ~50 path references in README/site_architecture/syndication_map/query_library/state/niche_statement/entity_card | renaming breaks geo_audit.py and every doc link; each file mirrors a live URL slug (`/compare/leadpilot-vs-*/`, `/what-is-leadpilot/`) |
| docs/program/ai-visibility/geo/content/comparisons/leadpilot_vs_artisan.md | leadpilot | B | repo file name; referenced by `geo/tools/geo_audit.py` (lines 8, 13 glob `leadpilot_vs_*.md`, 21, 52, 55, 57) and by ~50 path references in README/site_architecture/syndication_map/query_library/state/niche_statement/entity_card | renaming breaks geo_audit.py and every doc link; each file mirrors a live URL slug (`/compare/leadpilot-vs-*/`, `/what-is-leadpilot/`) |
| docs/program/ai-visibility/geo/content/comparisons/leadpilot_vs_clay.md | leadpilot | B | repo file name; referenced by `geo/tools/geo_audit.py` (lines 8, 13 glob `leadpilot_vs_*.md`, 21, 52, 55, 57) and by ~50 path references in README/site_architecture/syndication_map/query_library/state/niche_statement/entity_card | renaming breaks geo_audit.py and every doc link; each file mirrors a live URL slug (`/compare/leadpilot-vs-*/`, `/what-is-leadpilot/`) |
| docs/program/ai-visibility/geo/content/comparisons/leadpilot_vs_instantly.md | leadpilot | B | repo file name; referenced by `geo/tools/geo_audit.py` (lines 8, 13 glob `leadpilot_vs_*.md`, 21, 52, 55, 57) and by ~50 path references in README/site_architecture/syndication_map/query_library/state/niche_statement/entity_card | renaming breaks geo_audit.py and every doc link; each file mirrors a live URL slug (`/compare/leadpilot-vs-*/`, `/what-is-leadpilot/`) |
| docs/program/ai-visibility/geo/content/comparisons/leadpilot_vs_smartlead.md | leadpilot | B | repo file name; referenced by `geo/tools/geo_audit.py` (lines 8, 13 glob `leadpilot_vs_*.md`, 21, 52, 55, 57) and by ~50 path references in README/site_architecture/syndication_map/query_library/state/niche_statement/entity_card | renaming breaks geo_audit.py and every doc link; each file mirrors a live URL slug (`/compare/leadpilot-vs-*/`, `/what-is-leadpilot/`) |
| docs/program/ai-visibility/geo/content/definitions/leadpilot_use_cases.md | leadpilot | B | repo file name; referenced by `geo/tools/geo_audit.py` (lines 8, 13 glob `leadpilot_vs_*.md`, 21, 52, 55, 57) and by ~50 path references in README/site_architecture/syndication_map/query_library/state/niche_statement/entity_card | renaming breaks geo_audit.py and every doc link; each file mirrors a live URL slug (`/compare/leadpilot-vs-*/`, `/what-is-leadpilot/`) |
| docs/program/ai-visibility/geo/content/definitions/what_is_leadpilot.md | leadpilot | B | repo file name; referenced by `geo/tools/geo_audit.py` (lines 8, 13 glob `leadpilot_vs_*.md`, 21, 52, 55, 57) and by ~50 path references in README/site_architecture/syndication_map/query_library/state/niche_statement/entity_card | renaming breaks geo_audit.py and every doc link; each file mirrors a live URL slug (`/compare/leadpilot-vs-*/`, `/what-is-leadpilot/`) |

Outside this area (reported for the other agent, not inventoried here): `docs/features/vectorae-agents.md`, `docs/help-center/01-what-is-leadpilot.md` (the latter is referenced from this area as an article id: STAR_PROMPT.md:190, help-center-factcheck.md:41, plans/help-ai-v2-00-recon.md:18, help-center-eval.md:73).

## 4. Generated or git-ignored files

- `git ls-files -o -i --exclude-standard` over docs/, status-page/, reports/ and root *.md returns nothing: no ignored or untracked generated files exist in this area in the checkout (status-page/node_modules and .next are not present).
- `status-page/package-lock.json:2,8` (`"name": "leadpilot-status-page"`) is generated by `npm install` from `status-page/package.json:2`; change package.json and rerun `npm install` in status-page/, do not hand-edit the lock.
- `docs/program/status.json` looks generated but is hand-maintained per STAR_PROMPT.md:123 (every task updates it); its 14 `LeadPilot` hits are GitHub PR/run URLs (B).
- `docs/program/ai-visibility/geo/tools/geo_audit.py` is a checker script, not generated; its brand-string assertions (A-test) and file-name references (B) move with the content files.

## 5. Surprises and top risks

1. **Docs point production config at a third party's domain.** CLAUDE_CODE_HANDOFF.md:1727 ("Domain confirmed: leadpilot.com / api.leadpilot.com"), :1869, :1897-1902 (CORS_ORIGINS, NEXT_PUBLIC_API_URL, PUBLIC_BASE_URL, FRONTEND_URL, GMAIL_REDIRECT_URI, ADMIN_EMAIL), :1937, :1999, :2821; DEPLOY_RAILWAY.md:102, :146, :167; plans/connector-00-recon.md:286 (says `.env.production.example:110` still has `https://api.leadpilot.com`). Per ai-visibility/geo/entity_card.md:19 and SPEC.md:30, leadpilot.com belongs to LeadPilot AB (Sweden). Production is calendarharvest.com. Classified B (stale domain); someone following DEPLOY_RAILWAY.md would register a Gmail OAuth redirect on a domain the founders do not own.
2. **99 occurrences are NOT our brand (EXCL)** and must survive any find-replace: LeadPilot AB / leadpilot.com, Twenty Over Ten "Lead Pilot", LeadPilot AI (Rish AI Labs), AWS Marketplace LeadPilot, leadpilot.live, hf.space LeadPilot, and AB's linkedin.com/company/leadpilot. They sit in the disambiguation sentence ("not affiliated with LeadPilot AB (leadpilot.com)") that is repeated in every comparison page, FAQ, entity_card, schema_markup JSON-LD and llms.txt draft. ai-visibility/REPORT.md:98 records that our own /contact JSON-LD once pointed sameAs at AB's LinkedIn page.
3. **"Calendarharvest" is used as the company/site brand 155 times (C).** The canonical name is "Vectorae by Calendarharvest" (entity_card.md:17-18, :141), page titles are built from brand constants and a check asserts every title contains it (REPORT.md:165), and product-facts.json holds the brand name (SPEC.md:96). A Victorae rename must change the brand constants, product-facts.json, the title check, and every GEO draft together; whether "Calendarharvest" itself stays is a founder decision.
4. **Display-looking identifiers.** UptimeRobot monitor friendly names `Vectorae - Website/App login/Booking page/API/API healthy/Worker` (status-page/lib/config.ts:65-70, asserted in status-page/tests/snapshot.test.ts:210, documented in STATUS_PAGE.md:256-258, 284, 291-295, 301) are matched by exact string against the external UptimeRobot account: renaming them in code without renaming the monitors makes the status page show No data. Salesforce `LeadSource=Vectorae` (help-center-factcheck.md:2534) is a value written into customers' CRMs.
5. **Old-name identifiers that outlived two rebrands (B):** Celery task prefix `leadpilot.*` (CLAUDE_CODE_HANDOFF.md:1438-1441, FEATURES.md:420, connector-00-recon.md:27); OAuth scopes `leadpilot:read`/`leadpilot:write` (DECISIONS.md:33, connector-05-verification.md:69); webhook headers `X-LeadPilot-Event/Delivery/Signature` and legacy `X-ClientHunter-Signature` (help-center-factcheck.md:1088, 2608, 3014-3017); env var `LEADPILOT_API_URL` on the status-page Vercel project and `LEADPILOT_LIVE_*` test vars; Render services `leadpilot-api`/`leadpilot-worker`(-708k)/`leadpilot-workers`; Vercel project `lead-pilot` (lead-pilot-coral.vercel.app); repo `Rmasood1122/LeadPilot`; `.git/leadpilot-gate/` stamp dir (STAR_PROMPT.md:148); API key prefix `lpk_`; Android appId `com.clienthunter.app` (cannot change after Play publish); deep-link scheme `clienthunter://`; PyPI/CLI `clienthunter`; `ClientHunterError`.
6. **Public URL slugs still carry the old name:** `/what-is-leadpilot/`, `/compare/leadpilot-vs-{apollo,instantly,smartlead,clay,artisan}/`, old `/blog/apollo-clay-leadpilot-comparison/` (48 B rows; geo/state.md:184-186 says 12 pages shipped on these slugs). Renaming needs 301s, sitemap/llms.txt/IndexNow updates.
7. **Our third-party listings use LeadPilot handles (C):** linkedin.com/company/leadpilot-app, linkedin.com/in/rehan-rana-leadpilot, g2.com/products/leadpilot-2026-10-14, crunchbase.com/organization/leadpilot, getapp.com/all-software/a/leadpilot, YouTube @LeadPilotEnterprise; they are also in schema_markup.md:44-50 sameAs (and so in the live JSON-LD). geo/state.md:156 warns renaming after ~50 listings is expensive.
8. **Root docs are two rebrands behind (A-current):** titles of README.md:1, SECURITY.md:1, BACKUP.md:1/29, DEPLOY.md:1, LAUNCH_CHECKLIST.md:1, SYSTEM_HANDOFF.md:1, docs/architecture.md:1, docs/compliance.md:1, docs/learning-loop.md:1 still say "ClientHunter Enterprise". FEATURES.md:3 and STAR_PROMPT.md:42 claim "repo name: ClientHunter Enterprise", but the repo is `Rmasood1122/LeadPilot`. CLAUDE.md:1 is "Vectorae (ClientHunter Enterprise)" and CLAUDE.md:5 names the external Claude Project "LeadPilot Production Readiness" (C).
9. **C items needing a human:** SECURITY.md:92 tells users to revoke "ClientHunter" access in their Google account (the OAuth consent-screen app name); reports/LP-T-004-launch-checklist-decomposition.md:142 lists Play Store app name `ClientHunter Enterprise`; CLAUDE_CODE_HANDOFF.md:1943 describes the VECTORAE logo wordmark; CLAUDE_CODE_HANDOFF.md:1881 records the CAN-SPAM footer placeholder.
10. **Customer-voice finding just outside this area (not counted as DEFECT here):** the CAN-SPAM footer identity printed in every outbound email defaults to `"Vectorae User, 123 Main St, City, Country"` (app/config.py:106, .env.production.example:114; app/core/production_guard.py:227-234 blocks it in production). Tests still use the older `"LeadPilot User, 123 Main St, City, Country"` (tests/test_production_guard.py:287, tests/test_reply_copilot_review_fixes.py:321). tests/integration/mocks/calendly_mock.py:79 sets `utm_source: "clienthunter"`. Forwarded for the code-area agent.
11. **Historical records dominate docs/program/.** help-center-factcheck.md has 307 A-historical occurrences (dated 2026-10-10/11 per-sentence verdicts quoting the help center). Rewriting them would falsify the evidence record; a dated header note ("product since renamed Victorae") preserves the record. The same applies to BASELINE, PROGRESS, DECISIONS, status.json, fixes/, plans/, the audits and CLAUDE_CODE_HANDOFF.md.
12. **Stale/unowned domains (B):** clienthunter.com/.app/.io (README_M7_COMPLETE.md:24, README_M7_MOBILE_SECTION.md:100, LP-T-004:138/237, CLAUDE_CODE_HANDOFF.md:2352-2353, SYSTEM_HANDOFF.md:122 `upgrade@clienthunter.io` as the live plan-upgrade route); leadpilot.io (reports/LP-T-002:22, quoting a code comment at app/db/models.py:3396-3397).

## 6. calendarharvest domain uses (out of scope per brief; tallied, not inventoried)

These are `calendarharvest.com` / `www.` / `status.` / `api.` / `noreply@` hosts and addresses (B-type identifiers: the live production domain per CLAUDE.md). Product-name uses of "Calendarharvest" are in section 2 as C.

| File | domain occurrences |
|---|---|
| docs/program/ai-visibility/BASELINE.md | 41 |
| docs/program/ai-visibility/REPORT.md | 33 |
| docs/program/STATUS_PAGE.md | 20 |
| docs/program/ai-visibility/geo/technical/schema_markup.md | 18 |
| docs/program/ai-visibility/geo/technical/crawler_access_strategy.md | 17 |
| docs/program/ai-visibility/SPEC.md | 10 |
| docs/program/STAR_PROMPT.md | 6 |
| docs/program/ai-visibility/geo/authority/citation_acquisition_plan.md | 5 |
| docs/program/DECISIONS.md | 4 |
| docs/program/ai-visibility/geo/content/faq_library.md | 4 |
| docs/program/ai-visibility/geo/monitoring/ai_mention_tracker.md | 4 |
| docs/PRODUCTION_READINESS.md | 3 |
| docs/program/ai-visibility/PROMPT_TRACKER.md | 3 |
| docs/program/ai-visibility/geo/content/definitions/what_is_leadpilot.md | 3 |
| docs/program/ai-visibility/geo/platforms/claude_playbook.md | 3 |
| docs/program/ai-visibility/geo/platforms/emerging_ai_playbook.md | 3 |
| docs/program/ai-visibility/geo/state.md | 3 |
| docs/program/help-center-factcheck.md | 3 |
| docs/program/ai-visibility/NOTES.md | 2 |
| docs/program/ai-visibility/geo/content/comparisons/leadpilot_vs_apollo.md | 2 |
| docs/program/ai-visibility/geo/content/comparisons/leadpilot_vs_artisan.md | 2 |
| docs/program/ai-visibility/geo/content/comparisons/leadpilot_vs_clay.md | 2 |
| docs/program/ai-visibility/geo/content/comparisons/leadpilot_vs_instantly.md | 2 |
| docs/program/ai-visibility/geo/content/comparisons/leadpilot_vs_smartlead.md | 2 |
| docs/program/ai-visibility/geo/entity_card.md | 2 |
| docs/program/ai-visibility/geo/platforms/chatgpt_bing_playbook.md | 2 |
| docs/program/ai-visibility/geo/platforms/gemini_playbook.md | 2 |
| docs/program/ai-visibility/geo/questions.md | 2 |
| docs/program/plans/connector-00-recon.md | 2 |
| docs/program/status.json | 2 |
| status-page/components/SiteChrome.tsx | 2 |
| status-page/lib/config.ts | 2 |
| docs/NEXT_STEPS.md | 1 |
| docs/program/ai-visibility/geo/README.md | 1 |
| docs/program/ai-visibility/geo/content/statistics_and_proof.md | 1 |
| docs/program/ai-visibility/geo/research/query_library.md | 1 |
| docs/program/plans/connector-05-verification.md | 1 |
| reports/LP-T-004-launch-checklist-decomposition.md | 1 |
| status-page/incidents/README.md | 1 |
| status-page/next.config.mjs | 1 |
| status-page/package.json | 1 |
| status-page/tests/feeds.test.ts | 1 |
| CLAUDE.md | 1 |
| **Total** | **222** |

## 7. Method and verification

- Hit list: `git grep -nIiE <regex> -- docs/ status-page/ reports/ <15 exclusion pathspecs>` plus the same over the 17 root-level `*.md` files; 1,435 lines. Per-file counts cross-checked with `git grep -cIiE`.
- Each occurrence was classified by its surrounding text with rules (domain suffix, header prefix `X-`, `_`-suffixed env var, `-api/-worker` service names, `.run_pipeline` task names, `:read/:write` scopes, `/compare/` slugs, `_vs_`/`what_is_` file names, listing-handle URLs, third-party markers such as " AB", "Twenty Over Ten", "use the name"), then every B, C and EXCL row and every legacy-name A row was reviewed by hand against the line text; misfires were fixed (e.g. entity_card.md:16 alias list, entity_card.md:20 ours vs AB's LinkedIn, STATUS_PAGE.md:5 Vercel project, STAR_PROMPT.md:148 stamp dir).
- Not verified: whether the external listings, UptimeRobot monitors, Render/Vercel names still exist as written (no network calls made). Line-level A rows for Vectorae were classified by rule and sampled, not each read.

# Part 6 — Brand inventory: Python tests, root test files, evals

_Source: subagent sweep, file `brand-tests.md`._

Area: `tests/` (Python + YAML golden sets), root `test_*.py` (`test_calendly_webhook.py`, `test_whatsapp_webhook.py`), `smoke_test.py`, `evals/`.
Method: `git grep -nIiE 'lead[ _.-]?pilot|client[ _.-]?hunter|vectorae|victorae|lpk_|calendarharvest'` over those paths (491 matching lines, branch `claude/bold-heisenberg-58xvzj`, clean tree). Every line classified by a rule table (script: `classify_tests.py` next to this file), with app-side sources checked for every asserted display string. `Victorae` has 0 hits.

Sealed list used (from `evals/compliance_testset.yaml` + `.claude/hooks/protect_sealed.py` SEALED_FILES): the 36 test files in compliance_testset.yaml, plus `evals/registry.yaml`, `evals/compliance_testset.yaml`, `evals/baseline.json`, `.claude/settings.json`, `scripts/gate/required_checks.txt`, `.github/workflows/`, `.githooks/`, `.claude/hooks/`. Edits to these are blocked by the Claude hook except on `gate/` or `claude/gate-` branches and need their own reviewed PR (CLAUDE.md).

Class `A` includes `A-comment` (comments/docstrings) and `A` test fixtures/inputs; the reason column says whether the line **asserts** the string (`[assert]`) or only supplies it (fixture/input).

## 1. Summary

- Files with hits: **103** (17 of them SEALED). Root `test_calendly_webhook.py`, `test_whatsapp_webhook.py`, `smoke_test.py`: **0 hits**. `evals/baseline.json`, `evals/fixtures/*`, `evals/tools/*`: 0 hits.
- Matching lines: 491 total = 481 in scope + 10 calendarharvest-as-domain (out of scope, listed in 2b).
- No file or directory NAME in this area contains a variant.

| class | lines | occurrences |
|---|---|---|
| A | 199 | 202 |
| B | 280 | 317 |
| C | 2 | 2 |
| DEFECT | 0 | 0 |

(A breaks down as 168 display/fixture lines + 31 comment/docstring lines.)

| variant | lines | occurrences | A occ | B occ | C occ |
|---|---|---|---|---|---|
| LeadPilot | 293 | 322 | 38 | 284 | 0 |
| Vectorae | 169 | 171 | 157 | 12 | 2 |
| ClientHunter | 24 | 26 | 7 | 19 | 0 |
| lpk_ | 2 | 2 | 0 | 2 | 0 |
| Victorae | 0 | 0 | 0 | 0 | 0 |

DEFECT: **0** in this area (no customer-voice text injecting the product name is produced by tests; see section 5 for fixtures that look like it).

### SEALED files with hits

| sealed file | hit lines | what the hits are |
|---|---|---|
| `tests/test_email_network_guards.py` | 21 | B: synthetic test email address / domain (fixture only) (21) |
| `tests/test_whatsapp_template_optout.py` | 20 | A: fixture: customer WhatsApp template body ('Sam from LeadPilot') used t (19); B: synthetic test email address / domain (fixture only) (1) |
| `tests/test_deliverability_autopilot.py` | 13 | B: synthetic test email address / domain (fixture only) (13) |
| `tests/test_password_reset.py` | 11 | B: synthetic test email address / domain (fixture only) (11) |
| `tests/test_reply_copilot_review_fixes.py` | 10 | B: synthetic test email address / domain (fixture only) (9); A: fixture: compliant email footer sender identity (1) |
| `tests/test_unsubscribe_headers_raw.py` | 7 | EXCL: calendarharvest used as a domain/address, not a product name (2); B: synthetic test email address / domain (fixture only) (5) |
| `tests/test_pilot_mode.py` | 5 | B: synthetic test email address / domain (fixture only) (1); A: asserts download filename `leadpilot-pilot-verdict-*.pdf/csv` (2); A: asserts PDF title `LeadPilot meetings-per-dollar ledger` (app/services (1); A: asserts owner email copy `...running on your LeadPilot account` (app/s (1) |
| `tests/test_champion_tracker.py` | 4 | B: asserts Celery task name / route (queued tasks + beat schedule depend  (4) |
| `tests/test_annual_billing.py` | 3 | B: synthetic test email address / domain (fixture only) (3) |
| `evals/registry.yaml` | 2 | A: comment / docstring naming the product (2) |
| `evals/compliance_testset.yaml` | 1 | A: comment / docstring naming the product (1) |
| `tests/test_account_export.py` | 1 | B: asserts GDPR export `format` identifier (machine-readable) (1) |
| `tests/test_daily_send_approval_e2e.py` | 1 | B: synthetic test email address / domain (fixture only) (1) |
| `tests/test_guardrails.py` | 1 | B: synthetic test email address / domain (fixture only) (1) |
| `tests/test_privacy_docs_truth.py` | 1 | EXCL: calendarharvest used as a domain/address, not a product name (1) |
| `tests/test_production_guard.py` | 1 | A: fixture: placeholder SENDER_IDENTITY value that must block startup (na (1) |
| `tests/test_reply_copilot.py` | 1 | B: synthetic test email address / domain (fixture only) (1) |

## 2. Occurrence table

| path:line | variant | class | reason | risk |
|---|---|---|---|---|
| `evals/compliance_testset.yaml:1` | LeadPilot | A | comment: comment / docstring naming the product | SEALED |
| `evals/registry.yaml:2` | LeadPilot | A | comment: comment / docstring naming the product | SEALED |
| `evals/registry.yaml:3` | LeadPilot | A | comment: comment / docstring naming the product | SEALED |
| `evals/run_evals.py:2` | LeadPilot | A | comment: comment / docstring naming the product |  |
| `evals/run_evals.py:4` | LeadPilot | A | comment: comment / docstring naming the product |  |
| `tests/conftest.py:304` | Vectorae | A | FakeClaude routes support-chat calls on substring 'Vectorae in-app support assistant' of the app system prompt (app/services/support_chat.py:98) | COUPLING: renaming the system prompt silently misroutes FakeClaude -> many support tests fail |
| `tests/conftest.py:312` | Vectorae | A | FakeClaude default support answer text (fixture) |  |
| `tests/conftest.py:313` | LeadPilot | B | help-center article id / legacy FAQ alias / frontend route `what-is-leadpilot` |  |
| `tests/conftest.py:556` | Vectorae | A | fixture: customer WhatsApp template body ('Sam from Vectorae'); name incidental |  |
| `tests/conftest.py:727` | LeadPilot | B | default temp export dir name (fixture) |  |
| `tests/conftest.py:1059` | LeadPilot | B | synthetic test email address / domain (fixture only) |  |
| `tests/conftest.py:1490` | LeadPilot | B | synthetic test email address / domain (fixture only) |  |
| `tests/conftest.py:1562` | Vectorae | A | fixture: customer WhatsApp template body ('Sam from Vectorae'); name incidental |  |
| `tests/help_center/code_facts.yaml:189` | Vectorae | A | help-center fact-check `phrase` that must appear verbatim in the article prose | lockstep with docs/help-center + frontend/src/content/help-center |
| `tests/help_center/code_facts.yaml:799` | Vectorae | A | help-center fact-check `phrase` that must appear verbatim in the article prose | lockstep with docs/help-center + frontend/src/content/help-center |
| `tests/help_center/code_facts.yaml:803` | Vectorae | A | help-center fact-check `phrase` that must appear verbatim in the article prose | lockstep with docs/help-center + frontend/src/content/help-center |
| `tests/help_center/code_facts.yaml:894` | Vectorae | A | help-center fact-check `phrase` that must appear verbatim in the article prose | lockstep with docs/help-center + frontend/src/content/help-center |
| `tests/help_center/code_facts.yaml:898` | Vectorae | A | help-center fact-check `phrase` that must appear verbatim in the article prose | lockstep with docs/help-center + frontend/src/content/help-center |
| `tests/help_center/code_facts.yaml:935` | Vectorae | A | help-center fact-check `phrase` that must appear verbatim in the article prose | lockstep with docs/help-center + frontend/src/content/help-center |
| `tests/help_center/code_facts.yaml:939` | Vectorae | A | help-center fact-check `phrase` that must appear verbatim in the article prose | lockstep with docs/help-center + frontend/src/content/help-center |
| `tests/help_center/code_facts.yaml:1169` | Vectorae | A | fact-check regex reads default CRM deal name `Vectorae deal` from app/services/crm_sync.py (written into customers' HubSpot/Salesforce) | regex breaks if crm_sync string changes; deal name lands in third-party CRM |
| `tests/help_center/golden_questions.yaml:13` | Vectorae | A | comment: comment |  |
| `tests/help_center/golden_questions.yaml`:L21-936 (27 lines: 21,31,132,197,337,387,392,444,474,491,501,564,643,648,653,668,685,697,746,751,774,828,868,916,920,928,936) | Vectorae x27 | A | golden-set question text (user input) (collapsed, homogeneous) |  |
| `tests/help_center/golden_questions.yaml:23` | LeadPilot, Vectorae | B | help-center article id / legacy FAQ alias / frontend route `what-is-leadpilot` |  |
| `tests/help_center/golden_questions.yaml:28` | LeadPilot | B | help-center article id / legacy FAQ alias / frontend route `what-is-leadpilot` |  |
| `tests/help_center/golden_questions.yaml`:L33-830 (36 lines: 33,46,56,97,113,149,351,357,374,394,406,424,425,436,446,451,481,498,566,604,623,645,650,660,670,671,687,709,725,748,753,766,776,788,793,830) | Vectorae x36 | A | expected chunk id heading-slug derived from article heading text (slugify) (collapsed, homogeneous) | id regenerates from heading; rename heading => golden id must change in lockstep (test fails intentionally) |
| `tests/help_center/golden_questions.yaml:389` | LeadPilot, Vectorae | B | help-center article id / legacy FAQ alias / frontend route `what-is-leadpilot` |  |
| `tests/help_center/golden_questions.yaml:399` | LeadPilot | B | help-center article id / legacy FAQ alias / frontend route `what-is-leadpilot` |  |
| `tests/help_center/golden_questions.yaml:400` | LeadPilot, Vectorae | B | help-center article id / legacy FAQ alias / frontend route `what-is-leadpilot` |  |
| `tests/help_center/test_retrieval_eval.py:193` | Vectorae | A | comment: docstring |  |
| `tests/help_center/test_support_integration.py:166` | Vectorae | A | input question `What is Vectorae?` |  |
| `tests/help_center/test_support_integration.py:167` | LeadPilot | B | help-center article id / legacy FAQ alias / frontend route `what-is-leadpilot` |  |
| `tests/help_center/test_support_integration.py:170` | LeadPilot | B | [assert] help-center article id / legacy FAQ alias / frontend route `what-is-leadpilot` |  |
| `tests/help_center/test_support_integration.py:171` | Vectorae | A | asserts help-center article title `What is Vectorae?` |  |
| `tests/help_center/test_support_integration.py:211` | LeadPilot, Vectorae x2 | B | help-center article id / legacy FAQ alias / frontend route `what-is-leadpilot` |  |
| `tests/help_center/test_support_integration.py:212` | Vectorae | A | asserts answer starts with help-center prose `Vectorae is an outbound sales system.` |  |
| `tests/help_center/test_support_integration.py:232` | Vectorae | A | comment: docstring |  |
| `tests/help_center/test_support_integration.py:233` | Vectorae | A | comment: docstring |  |
| `tests/help_center/test_support_integration.py:235` | Vectorae | A | input question `What is Vectorae?` |  |
| `tests/integration/conftest.py:49` | LeadPilot | A | comment: comment naming leadpilot DB role |  |
| `tests/integration/conftest.py:55` | LeadPilot x2, ClientHunter | B | Postgres role / database name in DSN (CI + local DB) |  |
| `tests/integration/conftest.py:570` | Vectorae | A | fixture: synthetic customer product/sender named after us (assert on it only echoes the fixture) |  |
| `tests/integration/mocks/calendly_mock.py:79` | ClientHunter | B | mock Calendly utm_source value (app does not read it) |  |
| `tests/integration/mocks/calendly_mock.py:140` | ClientHunter | B | synthetic test email address / domain (fixture only) |  |
| `tests/integration/pg_root_suite.py:65` | LeadPilot x2 | B | Postgres role / database name in DSN (CI + local DB) |  |
| `tests/integration/test_chunk5_production_launch.py:199` | LeadPilot | B | fixture webhook URL path |  |
| `tests/integration/test_flows.py:50` | Vectorae | A | [assert] fixture: synthetic customer product/sender named after us (assert on it only echoes the fixture) |  |
| `tests/integration/test_flows.py:448` | ClientHunter | B | [assert] asserts Android deep-link URL scheme `clienthunter://` | app-side scheme must change in lockstep |
| `tests/integration/test_flows.py:653` | Vectorae | A | fixture: synthetic customer product/sender named after us (assert on it only echoes the fixture) |  |
| `tests/integration/test_flows.py:678` | Vectorae | A | fixture: synthetic customer product/sender named after us (assert on it only echoes the fixture) |  |
| `tests/integration/test_flows.py:702` | Vectorae | A | fixture: synthetic customer product/sender named after us (assert on it only echoes the fixture) |  |
| `tests/integration/test_mcp_connector_pg.py:78` | LeadPilot x2 | B | OAuth/MCP scope string (stored in issued tokens, connector configs) |  |
| `tests/integration/test_mcp_connector_pg.py:178` | LeadPilot | B | [assert] OAuth/MCP scope string (stored in issued tokens, connector configs) |  |
| `tests/integration/test_notifications_wiring.py:62` | ClientHunter | B | [assert] asserts Android deep-link URL scheme `clienthunter://` | app-side scheme must change in lockstep |
| `tests/integration/test_notifications_wiring.py:92` | ClientHunter | B | [assert] asserts Android deep-link URL scheme `clienthunter://` | app-side scheme must change in lockstep |
| `tests/integration/test_notifications_wiring.py:129` | ClientHunter | B | [assert] asserts Android deep-link URL scheme `clienthunter://` | app-side scheme must change in lockstep |
| `tests/integration/test_notifications_wiring.py:162` | ClientHunter | B | [assert] asserts Android deep-link URL scheme `clienthunter://` | app-side scheme must change in lockstep |
| `tests/mcp/conftest.py:50` | LeadPilot | B | OAuth/MCP scope string (stored in issued tokens, connector configs) |  |
| `tests/mcp/conftest.py:86` | LeadPilot | B | OAuth/MCP scope string (stored in issued tokens, connector configs) |  |
| `tests/mcp/conftest.py:169` | LeadPilot | B | synthetic test email address / domain (fixture only) |  |
| `tests/mcp/test_http_endpoint.py:50` | LeadPilot x2 | B | [assert] OAuth/MCP scope string (stored in issued tokens, connector configs) |  |
| `tests/mcp/test_oauth_flow.py:43` | LeadPilot x2 | B | OAuth/MCP scope string (stored in issued tokens, connector configs) |  |
| `tests/mcp/test_oauth_flow.py:76` | LeadPilot x2 | B | OAuth/MCP scope string (stored in issued tokens, connector configs) |  |
| `tests/mcp/test_oauth_flow.py:202` | LeadPilot | B | OAuth/MCP scope string (stored in issued tokens, connector configs) |  |
| `tests/mcp/test_oauth_flow.py:234` | LeadPilot x2 | B | [assert] OAuth/MCP scope string (stored in issued tokens, connector configs) |  |
| `tests/mcp/test_oauth_flow.py:301` | LeadPilot x2 | B | [assert] OAuth/MCP scope string (stored in issued tokens, connector configs) |  |
| `tests/mcp/test_oauth_flow.py:363` | LeadPilot | B | OAuth/MCP scope string (stored in issued tokens, connector configs) |  |
| `tests/mcp/test_oauth_flow.py:365` | LeadPilot | B | [assert] OAuth/MCP scope string (stored in issued tokens, connector configs) |  |
| `tests/mcp/test_oauth_flow.py:369` | LeadPilot | B | OAuth/MCP scope string (stored in issued tokens, connector configs) |  |
| `tests/mcp/test_oauth_flow.py:372` | LeadPilot x2 | B | OAuth/MCP scope string (stored in issued tokens, connector configs) |  |
| `tests/mcp/test_read_tools.py:180` | Vectorae | A | asserts MCP tool error message `... must be a Vectorae id` |  |
| `tests/mcp/test_read_tools.py:181` | Vectorae | A | asserts MCP tool error message `... must be a Vectorae id` |  |
| `tests/mcp/test_read_tools.py:182` | Vectorae | A | asserts MCP tool error message `... must be a Vectorae id` |  |
| `tests/mcp/test_read_tools.py:183` | Vectorae | A | asserts MCP tool error message `... must be a Vectorae id` |  |
| `tests/mcp/test_read_tools.py:184` | Vectorae | A | asserts MCP tool error message `... must be a Vectorae id` |  |
| `tests/mcp/test_read_tools.py:185` | Vectorae | A | asserts MCP tool error message `... must be a Vectorae id` |  |
| `tests/mcp/test_read_tools.py:186` | Vectorae | A | asserts MCP tool error message `... must be a Vectorae id` |  |
| `tests/mcp/test_read_tools.py:187` | Vectorae | A | asserts MCP tool error message `... must be a Vectorae id` |  |
| `tests/mcp/test_read_tools.py:188` | Vectorae | A | asserts MCP tool error message `... must be a Vectorae id` |  |
| `tests/mcp/test_read_tools.py:282` | LeadPilot | B | [assert] OAuth/MCP scope string (stored in issued tokens, connector configs) |  |
| `tests/mcp/test_write_tools.py:4` | LeadPilot | A | comment: docstring naming scope leadpilot:write (B identifier) |  |
| `tests/mcp/test_write_tools.py:21` | LeadPilot x2 | B | OAuth/MCP scope string (stored in issued tokens, connector configs) |  |
| `tests/mcp/test_write_tools.py:102` | Vectorae | A | [assert] asserts MCP tool error message `... must be a Vectorae id` |  |
| `tests/mcp/test_write_tools.py:170` | LeadPilot | B | [assert] OAuth/MCP scope string (stored in issued tokens, connector configs) |  |
| `tests/mcp/test_write_tools.py:180` | LeadPilot x2 | B | [assert] OAuth/MCP scope string (stored in issued tokens, connector configs) |  |
| `tests/test_account_export.py:207` | LeadPilot | B | [assert] asserts GDPR export `format` identifier (machine-readable) | SEALED |
| `tests/test_agent_runs_migration.py:1` | Vectorae | A | comment: docstring |  |
| `tests/test_agents_api.py:1` | Vectorae | A | comment: docstring |  |
| `tests/test_agents_api.py:54` | LeadPilot | B | synthetic test email address / domain (fixture only) |  |
| `tests/test_agents_native_parity.py:1` | Vectorae | A | comment: docstring |  |
| `tests/test_agents_native_parity.py:9` | Vectorae | B | env var name |  |
| `tests/test_agents_native_parity.py:28` | Vectorae | B | env var name |  |
| `tests/test_agents_native_parity.py:29` | Vectorae | B | env var name |  |
| `tests/test_agents_native_parity.py:35` | Vectorae | B | native wheel/module import name |  |
| `tests/test_agents_native_parity.py:40` | Vectorae | B | native wheel/module import name |  |
| `tests/test_agents_reference.py:1` | Vectorae | A | comment: docstring |  |
| `tests/test_annual_billing.py:396` | LeadPilot | B | synthetic test email address / domain (fixture only) | SEALED |
| `tests/test_annual_billing.py:675` | LeadPilot | B | synthetic test email address / domain (fixture only) | SEALED |
| `tests/test_annual_billing.py:681` | LeadPilot | B | [assert] synthetic test email address / domain (fixture only) | SEALED |
| `tests/test_autopilot_launch.py:651` | LeadPilot | B | synthetic test email address / domain (fixture only) |  |
| `tests/test_autopilot_review_fixes.py:419` | LeadPilot | B | [assert] asserts Celery task name / route (queued tasks + beat schedule depend on it) |  |
| `tests/test_autopilot_review_fixes.py:668` | LeadPilot | B | asserts Celery task name / route (queued tasks + beat schedule depend on it) |  |
| `tests/test_billing.py:390` | LeadPilot | B | booking channel / meeting source enum value (DB) |  |
| `tests/test_billing.py:519` | LeadPilot | B | synthetic test email address / domain (fixture only) |  |
| `tests/test_calendar_api.py:148` | LeadPilot | B | synthetic test email address / domain (fixture only) |  |
| `tests/test_calendar_api.py:221` | LeadPilot | B | synthetic test email address / domain (fixture only) |  |
| `tests/test_calendar_api.py:504` | LeadPilot | B | synthetic test email address / domain (fixture only) |  |
| `tests/test_calendar_api.py:601` | LeadPilot | B | synthetic test email address / domain (fixture only) |  |
| `tests/test_campaign_lowered_limits.py:31` | LeadPilot | B | synthetic test email address / domain (fixture only) |  |
| `tests/test_champion_tracker.py:1059` | LeadPilot | B | [assert] asserts Celery task name / route (queued tasks + beat schedule depend on it) | SEALED |
| `tests/test_champion_tracker.py:1060` | LeadPilot | B | [assert] asserts Celery task name / route (queued tasks + beat schedule depend on it) | SEALED |
| `tests/test_champion_tracker.py:1061` | LeadPilot | B | [assert] asserts Celery task name / route (queued tasks + beat schedule depend on it) | SEALED |
| `tests/test_champion_tracker.py:1062` | LeadPilot x2 | B | [assert] asserts Celery task name / route (queued tasks + beat schedule depend on it) | SEALED |
| `tests/test_compliance_rules.py:89` | LeadPilot | B | synthetic test email address / domain (fixture only) |  |
| `tests/test_connector_skill.py:1` | LeadPilot x2 | A | comment: docstring naming the leadpilot-outbound skill / leadpilot plugin |  |
| `tests/test_connector_skill.py:19` | LeadPilot | B | asserts Claude skill name / plugin name / MCP server key `leadpilot` | skill + plugin dirs renamed in lockstep |
| `tests/test_connector_skill.py:20` | LeadPilot | B | asserts Claude skill name / plugin name / MCP server key `leadpilot` | skill + plugin dirs renamed in lockstep |
| `tests/test_connector_skill.py:38` | LeadPilot | B | [assert] asserts Claude skill name / plugin name / MCP server key `leadpilot` | skill + plugin dirs renamed in lockstep |
| `tests/test_connector_skill.py:63` | LeadPilot | B | [assert] asserts Claude skill name / plugin name / MCP server key `leadpilot` | skill + plugin dirs renamed in lockstep |
| `tests/test_connector_skill.py:65` | LeadPilot | B | [assert] asserts Claude skill name / plugin name / MCP server key `leadpilot` | skill + plugin dirs renamed in lockstep |
| `tests/test_connector_skill.py:67` | LeadPilot | B | [assert] asserts Claude skill name / plugin name / MCP server key `leadpilot` | skill + plugin dirs renamed in lockstep |
| `tests/test_connector_skill.py:71` | LeadPilot | B | asserts Claude skill name / plugin name / MCP server key `leadpilot` | skill + plugin dirs renamed in lockstep |
| `tests/test_consent.py:189` | LeadPilot | B | domain leadpilot.io (marketing SITE_ORIGIN in app/services/sitemap.py & website_builder.py, or fixture URL) |  |
| `tests/test_crm_ecosystem.py:145` | LeadPilot | B | webhook signature/delivery/timestamp header name (receivers verify it) |  |
| `tests/test_crm_ecosystem.py:147` | LeadPilot | B | webhook signature/delivery/timestamp header name (receivers verify it) |  |
| `tests/test_crm_ecosystem.py:148` | LeadPilot | B | [assert] webhook signature/delivery/timestamp header name (receivers verify it) |  |
| `tests/test_crm_ecosystem.py:217` | lpk_ | B | [assert] asserts API-key prefix `lpk_` (keys already issued to customers) |  |
| `tests/test_crm_ecosystem.py:236` | lpk_ | B | asserts API-key prefix `lpk_` (keys already issued to customers) |  |
| `tests/test_crm_ecosystem.py:581` | LeadPilot x2 | B | webhook signature/delivery/timestamp header name (receivers verify it) |  |
| `tests/test_crm_ecosystem.py:593` | Vectorae | B | asserts Salesforce Lead `LeadSource` picklist value `Vectorae` (app/services/crm_sync.py:414) | customers' Salesforce reports/picklists key on it |
| `tests/test_crm_ecosystem.py:601` | LeadPilot | B | webhook signature/delivery/timestamp header name (receivers verify it) |  |
| `tests/test_daily_send_approval_e2e.py:320` | LeadPilot | B | synthetic test email address / domain (fixture only) | SEALED |
| `tests/test_deliverability_autopilot.py:37` | LeadPilot | B | synthetic test email address / domain (fixture only) | SEALED |
| `tests/test_deliverability_autopilot.py:64` | LeadPilot | B | synthetic test email address / domain (fixture only) | SEALED |
| `tests/test_deliverability_autopilot.py:129` | LeadPilot | B | synthetic test email address / domain (fixture only) | SEALED |
| `tests/test_deliverability_autopilot.py:130` | LeadPilot | B | synthetic test email address / domain (fixture only) | SEALED |
| `tests/test_deliverability_autopilot.py:194` | LeadPilot | B | [assert] synthetic test email address / domain (fixture only) | SEALED |
| `tests/test_deliverability_autopilot.py:235` | LeadPilot | B | synthetic test email address / domain (fixture only) | SEALED |
| `tests/test_deliverability_autopilot.py:240` | LeadPilot | B | synthetic test email address / domain (fixture only) | SEALED |
| `tests/test_deliverability_autopilot.py:252` | LeadPilot | B | synthetic test email address / domain (fixture only) | SEALED |
| `tests/test_deliverability_autopilot.py:266` | LeadPilot | B | synthetic test email address / domain (fixture only) | SEALED |
| `tests/test_deliverability_autopilot.py:292` | LeadPilot | B | [assert] synthetic test email address / domain (fixture only) | SEALED |
| `tests/test_deliverability_autopilot.py:293` | LeadPilot | B | synthetic test email address / domain (fixture only) | SEALED |
| `tests/test_deliverability_autopilot.py:470` | LeadPilot | B | [assert] synthetic test email address / domain (fixture only) | SEALED |
| `tests/test_deliverability_autopilot.py:833` | LeadPilot | B | synthetic test email address / domain (fixture only) | SEALED |
| `tests/test_dependency_pins.py:34` | LeadPilot | B | Postgres role / database name in DSN (CI + local DB) |  |
| `tests/test_devices.py:2` | ClientHunter | A | comment: module docstring 'ClientHunter Enterprise' |  |
| `tests/test_devices.py:214` | LeadPilot | B | synthetic test email address / domain (fixture only) |  |
| `tests/test_displacement_alerts.py:104` | Vectorae | A | input: DM naming the product must be rejected (FORBIDDEN_MENTIONS in app/services/displacement_monitor.py:74) | add new name to FORBIDDEN_MENTIONS |
| `tests/test_displacement_alerts.py:130` | Vectorae | A | input: DM naming the product must be rejected (FORBIDDEN_MENTIONS in app/services/displacement_monitor.py:74) | add new name to FORBIDDEN_MENTIONS |
| `tests/test_displacement_alerts.py:146` | Vectorae | A | input: DM naming the product must be rejected (FORBIDDEN_MENTIONS in app/services/displacement_monitor.py:74) | add new name to FORBIDDEN_MENTIONS |
| `tests/test_email_network.py:274` | LeadPilot | B | synthetic test email address / domain (fixture only) |  |
| `tests/test_email_network.py:275` | LeadPilot | B | synthetic test email address / domain (fixture only) |  |
| `tests/test_email_network.py:295` | LeadPilot | B | synthetic test email address / domain (fixture only) |  |
| `tests/test_email_network.py:338` | LeadPilot | B | synthetic test email address / domain (fixture only) |  |
| `tests/test_email_network.py:339` | LeadPilot | B | synthetic test email address / domain (fixture only) |  |
| `tests/test_email_network.py:340` | LeadPilot | B | synthetic test email address / domain (fixture only) |  |
| `tests/test_email_network.py:373` | LeadPilot | B | [assert] asserts Celery task name / route (queued tasks + beat schedule depend on it) |  |
| `tests/test_email_network.py:374` | LeadPilot | B | [assert] asserts Celery task name / route (queued tasks + beat schedule depend on it) |  |
| `tests/test_email_network.py:375` | LeadPilot | B | [assert] asserts Celery task name / route (queued tasks + beat schedule depend on it) |  |
| `tests/test_email_network.py:394` | LeadPilot | B | synthetic test email address / domain (fixture only) |  |
| `tests/test_email_network.py:412` | LeadPilot | B | synthetic test email address / domain (fixture only) |  |
| `tests/test_email_network.py:413` | LeadPilot | B | synthetic test email address / domain (fixture only) |  |
| `tests/test_email_network.py:425` | LeadPilot | B | synthetic test email address / domain (fixture only) |  |
| `tests/test_email_network.py:460` | LeadPilot | B | synthetic test email address / domain (fixture only) |  |
| `tests/test_email_network.py:475` | LeadPilot | B | synthetic test email address / domain (fixture only) |  |
| `tests/test_email_network.py:570` | LeadPilot | B | synthetic test email address / domain (fixture only) |  |
| `tests/test_email_network.py:634` | LeadPilot | B | synthetic test email address / domain (fixture only) |  |
| `tests/test_email_network_guards.py:71` | LeadPilot | B | synthetic test email address / domain (fixture only) | SEALED |
| `tests/test_email_network_guards.py:81` | LeadPilot | B | synthetic test email address / domain (fixture only) | SEALED |
| `tests/test_email_network_guards.py:200` | LeadPilot | B | synthetic test email address / domain (fixture only) | SEALED |
| `tests/test_email_network_guards.py:276` | LeadPilot | B | synthetic test email address / domain (fixture only) | SEALED |
| `tests/test_email_network_guards.py:277` | LeadPilot | B | synthetic test email address / domain (fixture only) | SEALED |
| `tests/test_email_network_guards.py:320` | LeadPilot | B | synthetic test email address / domain (fixture only) | SEALED |
| `tests/test_email_network_guards.py:343` | LeadPilot | B | [assert] synthetic test email address / domain (fixture only) | SEALED |
| `tests/test_email_network_guards.py:346` | LeadPilot | B | synthetic test email address / domain (fixture only) | SEALED |
| `tests/test_email_network_guards.py:472` | LeadPilot | B | synthetic test email address / domain (fixture only) | SEALED |
| `tests/test_email_network_guards.py:603` | LeadPilot | B | synthetic test email address / domain (fixture only) | SEALED |
| `tests/test_email_network_guards.py:619` | LeadPilot | B | synthetic test email address / domain (fixture only) | SEALED |
| `tests/test_email_network_guards.py:951` | LeadPilot | B | synthetic test email address / domain (fixture only) | SEALED |
| `tests/test_email_network_guards.py:1038` | LeadPilot | B | synthetic test email address / domain (fixture only) | SEALED |
| `tests/test_email_network_guards.py:1052` | LeadPilot | B | synthetic test email address / domain (fixture only) | SEALED |
| `tests/test_email_network_guards.py:1067` | LeadPilot | B | synthetic test email address / domain (fixture only) | SEALED |
| `tests/test_email_network_guards.py:1068` | LeadPilot | B | synthetic test email address / domain (fixture only) | SEALED |
| `tests/test_email_network_guards.py:1069` | LeadPilot | B | synthetic test email address / domain (fixture only) | SEALED |
| `tests/test_email_network_guards.py:1070` | LeadPilot | B | synthetic test email address / domain (fixture only) | SEALED |
| `tests/test_email_network_guards.py:1259` | LeadPilot | B | synthetic test email address / domain (fixture only) | SEALED |
| `tests/test_email_network_guards.py:1279` | LeadPilot | B | synthetic test email address / domain (fixture only) | SEALED |
| `tests/test_email_network_guards.py:1282` | LeadPilot | B | synthetic test email address / domain (fixture only) | SEALED |
| `tests/test_email_verification.py:173` | LeadPilot | B | synthetic test email address / domain (fixture only) |  |
| `tests/test_engagement_crm.py:124` | LeadPilot | B | [assert] booking channel / meeting source enum value (DB) |  |
| `tests/test_firebase_credentials_env.py:25` | LeadPilot | B | fixture Firebase project id / service account |  |
| `tests/test_firebase_credentials_env.py:27` | LeadPilot | B | fixture Firebase project id / service account |  |
| `tests/test_followup.py:259` | LeadPilot | B | synthetic test email address / domain (fixture only) |  |
| `tests/test_followup.py:478` | LeadPilot | B | synthetic test email address / domain (fixture only) |  |
| `tests/test_gaps_sweep_2.py:284` | LeadPilot | B | synthetic test email address / domain (fixture only) |  |
| `tests/test_gaps_sweep_2.py:285` | LeadPilot x2 | B | synthetic test email address / domain (fixture only) |  |
| `tests/test_gaps_sweep_2.py:288` | LeadPilot x2 | B | [assert] synthetic test email address / domain (fixture only) |  |
| `tests/test_gaps_sweep_2.py:1045` | ClientHunter | A | comment: docstring naming exception class ClientHunterError (B identifier in app code) |  |
| `tests/test_gate_scripts.py:73` | LeadPilot | B | gate stamp directory name (git common dir) |  |
| `tests/test_gate_scripts.py:110` | LeadPilot x2, ClientHunter | B | Postgres role / database name in DSN (CI + local DB) |  |
| `tests/test_gate_scripts.py:115` | LeadPilot x3 | B | Postgres role / database name in DSN (CI + local DB) |  |
| `tests/test_gate_scripts.py:227` | LeadPilot | B | gate stamp directory name (git common dir) |  |
| `tests/test_guardrails.py:52` | LeadPilot | B | synthetic test email address / domain (fixture only) | SEALED |
| `tests/test_identity_verification.py:193` | LeadPilot | B | synthetic test email address / domain (fixture only) |  |
| `tests/test_inbox.py:6` | Vectorae | A | comment: docstring |  |
| `tests/test_intake_api.py:6` | LeadPilot | B | synthetic test email address / domain (fixture only) |  |
| `tests/test_linkedin_channel.py:457` | LeadPilot | B | webhook signature/delivery/timestamp header name (receivers verify it) |  |
| `tests/test_linkedin_network.py:341` | LeadPilot | B | [assert] asserts Celery task name / route (queued tasks + beat schedule depend on it) |  |
| `tests/test_manual_pass_override.py:178` | LeadPilot | B | synthetic test email address / domain (fixture only) |  |
| `tests/test_meeting_platforms.py:35` | LeadPilot | B | synthetic test email address / domain (fixture only) |  |
| `tests/test_meeting_platforms_live.py:7` | LeadPilot | B | env var name |  |
| `tests/test_meeting_platforms_live.py:9` | LeadPilot | B | env var name |  |
| `tests/test_meeting_platforms_live.py:10` | LeadPilot | B | env var name |  |
| `tests/test_meeting_platforms_live.py:12` | LeadPilot | B | env var name |  |
| `tests/test_meeting_platforms_live.py:28` | LeadPilot | B | env var name |  |
| `tests/test_meeting_platforms_live.py:30` | LeadPilot | B | env var name |  |
| `tests/test_meeting_platforms_live.py:31` | LeadPilot | B | env var name |  |
| `tests/test_meeting_platforms_live.py:32` | LeadPilot | B | env var name |  |
| `tests/test_meeting_platforms_live.py:33` | LeadPilot | B | env var name |  |
| `tests/test_meeting_platforms_live.py:37` | LeadPilot | B | env var name |  |
| `tests/test_meeting_platforms_live.py:46` | Vectorae | A | title of event/meeting the live-only test creates in a real account | live test, skipped offline |
| `tests/test_meeting_platforms_live.py:55` | LeadPilot | B | env var name |  |
| `tests/test_meeting_platforms_live.py:60` | Vectorae | A | title of event/meeting the live-only test creates in a real account | live test, skipped offline |
| `tests/test_meeting_prep.py:300` | LeadPilot | B | [assert] booking channel / meeting source enum value (DB) |  |
| `tests/test_meeting_recording.py:92` | Vectorae | A | fake Recall signature default bot_name `Vectorae Notetaker` (mirrors app/integrations/recall.py:154; shown to meeting attendees) | judge: third-party-visible name |
| `tests/test_meetings_api.py:209` | LeadPilot | B | synthetic test email address / domain (fixture only) |  |
| `tests/test_meetings_api.py:288` | LeadPilot | B | synthetic test email address / domain (fixture only) |  |
| `tests/test_meetings_api.py:350` | LeadPilot | B | webhook signature/delivery/timestamp header name (receivers verify it) |  |
| `tests/test_meetings_api.py:375` | LeadPilot | B | webhook signature/delivery/timestamp header name (receivers verify it) |  |
| `tests/test_meetings_api.py:394` | LeadPilot | B | webhook signature/delivery/timestamp header name (receivers verify it) |  |
| `tests/test_meetings_api.py:411` | LeadPilot | B | webhook signature/delivery/timestamp header name (receivers verify it) |  |
| `tests/test_meetings_api.py:431` | LeadPilot | B | webhook signature/delivery/timestamp header name (receivers verify it) |  |
| `tests/test_meetings_ledger.py:97` | LeadPilot | B | synthetic test email address / domain (fixture only) |  |
| `tests/test_meetings_ledger.py:623` | LeadPilot | B | [assert] asserts JSON export `version` identifier (consumers parse it) |  |
| `tests/test_meetings_ledger.py:661` | LeadPilot | A | [assert] asserts CSV download filename `leadpilot-meetings-ledger-*.csv` |  |
| `tests/test_messages_dispatch_index.py:3` | LeadPilot | A | comment: docstring naming Celery task leadpilot.outreach.dispatch |  |
| `tests/test_monitoring_task_names.py:5` | LeadPilot | A | comment: docstring naming the leadpilot.* Celery task prefix |  |
| `tests/test_monitoring_task_names.py:26` | LeadPilot x2 | B | asserts Celery task name / route (queued tasks + beat schedule depend on it) |  |
| `tests/test_monitoring_task_names.py:27` | LeadPilot x2 | B | asserts Celery task name / route (queued tasks + beat schedule depend on it) |  |
| `tests/test_monitoring_task_names.py:28` | LeadPilot | B | asserts Celery task name / route (queued tasks + beat schedule depend on it) |  |
| `tests/test_monitoring_task_names.py:38` | LeadPilot | B | asserts Celery task name / route (queued tasks + beat schedule depend on it) |  |
| `tests/test_monitoring_task_names.py:40` | LeadPilot | B | [assert] asserts Celery task name / route (queued tasks + beat schedule depend on it) |  |
| `tests/test_monitoring_task_names.py:48` | LeadPilot | B | asserts Celery task name / route (queued tasks + beat schedule depend on it) |  |
| `tests/test_no_legacy_send_path.py:42` | LeadPilot | B | [assert] asserts Celery task name / route (queued tasks + beat schedule depend on it) |  |
| `tests/test_no_legacy_send_path.py:43` | LeadPilot | B | [assert] asserts Celery task name / route (queued tasks + beat schedule depend on it) |  |
| `tests/test_no_legacy_send_path.py:44` | LeadPilot | B | [assert] asserts Celery task name / route (queued tasks + beat schedule depend on it) |  |
| `tests/test_notifications.py:2` | ClientHunter | A | comment: module docstring 'ClientHunter Enterprise' |  |
| `tests/test_notifications.py:98` | ClientHunter | B | asserts Android deep-link URL scheme `clienthunter://` | app-side scheme must change in lockstep |
| `tests/test_notifications.py:252` | ClientHunter | B | [assert] asserts Android deep-link URL scheme `clienthunter://` | app-side scheme must change in lockstep |
| `tests/test_notifications.py:259` | ClientHunter | B | [assert] asserts Android deep-link URL scheme `clienthunter://` | app-side scheme must change in lockstep |
| `tests/test_notifications.py:266` | ClientHunter | B | [assert] asserts Android deep-link URL scheme `clienthunter://` | app-side scheme must change in lockstep |
| `tests/test_notifications.py:274` | ClientHunter | B | [assert] asserts Android deep-link URL scheme `clienthunter://` | app-side scheme must change in lockstep |
| `tests/test_notifications.py:281` | ClientHunter | B | [assert] asserts Android deep-link URL scheme `clienthunter://` | app-side scheme must change in lockstep |
| `tests/test_outcome_attribution.py:49` | LeadPilot | B | synthetic test email address / domain (fixture only) |  |
| `tests/test_password_reset.py:27` | LeadPilot | B | synthetic test email address / domain (fixture only) | SEALED |
| `tests/test_password_reset.py:79` | LeadPilot | B | synthetic test email address / domain (fixture only) | SEALED |
| `tests/test_password_reset.py:90` | LeadPilot | B | [assert] synthetic test email address / domain (fixture only) | SEALED |
| `tests/test_password_reset.py:91` | LeadPilot | B | synthetic test email address / domain (fixture only) | SEALED |
| `tests/test_password_reset.py:106` | LeadPilot | B | synthetic test email address / domain (fixture only) | SEALED |
| `tests/test_password_reset.py:108` | LeadPilot | B | synthetic test email address / domain (fixture only) | SEALED |
| `tests/test_password_reset.py:130` | LeadPilot | B | synthetic test email address / domain (fixture only) | SEALED |
| `tests/test_password_reset.py:135` | LeadPilot | B | synthetic test email address / domain (fixture only) | SEALED |
| `tests/test_password_reset.py:142` | LeadPilot | B | [assert] synthetic test email address / domain (fixture only) | SEALED |
| `tests/test_password_reset.py:268` | LeadPilot | B | synthetic test email address / domain (fixture only) | SEALED |
| `tests/test_password_reset.py:378` | LeadPilot | B | synthetic test email address / domain (fixture only) | SEALED |
| `tests/test_pilot_mode.py:113` | LeadPilot | B | synthetic test email address / domain (fixture only) | SEALED |
| `tests/test_pilot_mode.py:771` | LeadPilot | A | asserts download filename `leadpilot-pilot-verdict-*.pdf/csv` | SEALED |
| `tests/test_pilot_mode.py:790` | LeadPilot | A | [assert] asserts download filename `leadpilot-pilot-verdict-*.pdf/csv` | SEALED |
| `tests/test_pilot_mode.py:806` | LeadPilot | A | [assert] asserts PDF title `LeadPilot meetings-per-dollar ledger` (app/services/meetings_ledger.py:672 still says LeadPilot) | SEALED; app still emits OLD brand |
| `tests/test_pilot_mode.py:1020` | LeadPilot | A | [assert] asserts owner email copy `...running on your LeadPilot account` (app/services/pilot_mode.py:597-598 still says LeadPilot) | SEALED; app still emits OLD brand |
| `tests/test_plan_downgrade_holds.py:367` | LeadPilot | B | [assert] asserts Celery task name / route (queued tasks + beat schedule depend on it) |  |
| `tests/test_plan_downgrade_holds.py:369` | LeadPilot | B | [assert] asserts Celery task name / route (queued tasks + beat schedule depend on it) |  |
| `tests/test_plumbing.py:168` | LeadPilot | B | logger name (log filters/alerts key on it) |  |
| `tests/test_plumbing.py:171` | LeadPilot | B | logger name (log filters/alerts key on it) |  |
| `tests/test_production_guard.py:287` | LeadPilot | A | fixture: placeholder SENDER_IDENTITY value that must block startup (name incidental; guard keys on '123 Main St') | SEALED |
| `tests/test_profile.py:47` | LeadPilot | B | [assert] synthetic test email address / domain (fixture only) |  |
| `tests/test_profile.py:91` | LeadPilot | B | synthetic test email address / domain (fixture only) |  |
| `tests/test_quickstart.py:602` | LeadPilot x2 | B | [assert] asserts Celery task name / route (queued tasks + beat schedule depend on it) |  |
| `tests/test_quickstart.py:603` | LeadPilot x2 | B | asserts Celery task name / route (queued tasks + beat schedule depend on it) |  |
| `tests/test_quickstart.py:604` | LeadPilot x2 | B | asserts Celery task name / route (queued tasks + beat schedule depend on it) |  |
| `tests/test_quickstart.py:629` | LeadPilot x2 | B | asserts Celery task name / route (queued tasks + beat schedule depend on it) |  |
| `tests/test_reengagement.py:273` | LeadPilot | B | synthetic test email address / domain (fixture only) |  |
| `tests/test_reengagement.py:471` | LeadPilot | B | [assert] asserts Celery task name / route (queued tasks + beat schedule depend on it) |  |
| `tests/test_regression.py:23` | ClientHunter | A | comment: comment naming the `clienthunter` SDK package / config path |  |
| `tests/test_regression.py:203` | ClientHunter x2 | A | comment: comment naming the `clienthunter` SDK package / config path |  |
| `tests/test_regression.py:206` | ClientHunter | A | comment: comment naming the `clienthunter` SDK package / config path |  |
| `tests/test_regression.py:207` | ClientHunter x2 | B | imports the `clienthunter` Python SDK package (PyPI name, ~/.clienthunter config dir) |  |
| `tests/test_regression.py:208` | ClientHunter | B | imports the `clienthunter` Python SDK package (PyPI name, ~/.clienthunter config dir) |  |
| `tests/test_regression.py:210` | ClientHunter | B | imports the `clienthunter` Python SDK package (PyPI name, ~/.clienthunter config dir) |  |
| `tests/test_replies.py:27` | LeadPilot | B | synthetic test email address / domain (fixture only) |  |
| `tests/test_reply_authenticity.py:102` | LeadPilot | B | synthetic test email address / domain (fixture only) |  |
| `tests/test_reply_copilot.py:652` | LeadPilot | B | synthetic test email address / domain (fixture only) | SEALED |
| `tests/test_reply_copilot_review_fixes.py:71` | LeadPilot | B | synthetic test email address / domain (fixture only) | SEALED |
| `tests/test_reply_copilot_review_fixes.py:268` | LeadPilot | B | synthetic test email address / domain (fixture only) | SEALED |
| `tests/test_reply_copilot_review_fixes.py:287` | LeadPilot x2 | B | synthetic test email address / domain (fixture only) | SEALED |
| `tests/test_reply_copilot_review_fixes.py:312` | LeadPilot | B | synthetic test email address / domain (fixture only) | SEALED |
| `tests/test_reply_copilot_review_fixes.py:321` | LeadPilot | A | fixture: compliant email footer sender identity | SEALED |
| `tests/test_reply_copilot_review_fixes.py:323` | LeadPilot | B | synthetic test email address / domain (fixture only) | SEALED |
| `tests/test_reply_copilot_review_fixes.py:327` | LeadPilot | B | synthetic test email address / domain (fixture only) | SEALED |
| `tests/test_reply_copilot_review_fixes.py:334` | LeadPilot | B | synthetic test email address / domain (fixture only) | SEALED |
| `tests/test_reply_copilot_review_fixes.py:340` | LeadPilot | B | synthetic test email address / domain (fixture only) | SEALED |
| `tests/test_reply_copilot_review_fixes.py:350` | LeadPilot | B | synthetic test email address / domain (fixture only) | SEALED |
| `tests/test_reply_threading.py:27` | LeadPilot x2 | B | synthetic test email address / domain (fixture only) |  |
| `tests/test_reply_threading.py:33` | LeadPilot x2 | B | [assert] synthetic test email address / domain (fixture only) |  |
| `tests/test_reply_threading.py:40` | LeadPilot | B | synthetic test email address / domain (fixture only) |  |
| `tests/test_revenue_analytics.py:69` | LeadPilot | B | synthetic test email address / domain (fixture only) |  |
| `tests/test_reverify_needs_review.py:104` | LeadPilot | B | synthetic test email address / domain (fixture only) |  |
| `tests/test_safe_merge.py:215` | LeadPilot | B | GitHub repo URL / owner/repo slug Rmasood1122/LeadPilot (repo_from_remote parsing) |  |
| `tests/test_safe_merge.py:216` | LeadPilot | B | GitHub repo URL / owner/repo slug Rmasood1122/LeadPilot (repo_from_remote parsing) |  |
| `tests/test_safe_merge.py:217` | LeadPilot | B | GitHub repo URL / owner/repo slug Rmasood1122/LeadPilot (repo_from_remote parsing) |  |
| `tests/test_safe_merge.py:220` | LeadPilot | B | [assert] GitHub repo URL / owner/repo slug Rmasood1122/LeadPilot (repo_from_remote parsing) |  |
| `tests/test_send_time.py:234` | LeadPilot | B | synthetic test email address / domain (fixture only) |  |
| `tests/test_send_time.py:465` | LeadPilot | B | synthetic test email address / domain (fixture only) |  |
| `tests/test_sequence_reviews.py:137` | Vectorae | A | fixture: synthetic customer product/sender named after us (assert on it only echoes the fixture) |  |
| `tests/test_share_links.py:134` | LeadPilot | B | synthetic test email address / domain (fixture only) |  |
| `tests/test_strategy_budget.py:405` | LeadPilot | B | synthetic test email address / domain (fixture only) |  |
| `tests/test_support_chat.py:27` | LeadPilot | A | comment: comment naming article id what-is-leadpilot (B identifier) |  |
| `tests/test_support_chat.py:28` | Vectorae | A | comment: comment |  |
| `tests/test_support_chat.py:31` | LeadPilot | B | help-center article id / legacy FAQ alias / frontend route `what-is-leadpilot` |  |
| `tests/test_support_chat.py:34` | Vectorae | A | [assert] asserts help-center answer prose starts `Vectorae is an outbound sales system.` |  |
| `tests/test_support_chat.py:65` | LeadPilot, Vectorae | B | help-center article id / legacy FAQ alias / frontend route `what-is-leadpilot` |  |
| `tests/test_support_chat.py`:L145-936 (25 lines: 145,194,213,236,255,264,272,289,692,697,698,722,723,741,757,775,782,783,792,816,850,895,913,924,936) | Vectorae x26 | A | input question naming the product (support KB / Help AI retrieval) (collapsed, homogeneous) | retrieval depends on corpus containing the name |
| `tests/test_support_chat.py:160` | Vectorae | A | fixture: ungrounded FakeClaude answer |  |
| `tests/test_support_chat.py:171` | LeadPilot | B | help-center article id / legacy FAQ alias / frontend route `what-is-leadpilot` |  |
| `tests/test_support_chat.py:224` | LeadPilot | B | help-center article id / legacy FAQ alias / frontend route `what-is-leadpilot` |  |
| `tests/test_support_chat.py:241` | Vectorae | A | [assert] asserts stored/forwarded user question text (echo of input) |  |
| `tests/test_support_chat.py:274` | Vectorae | A | [assert] asserts stored/forwarded user question text (echo of input) |  |
| `tests/test_support_chat.py:487` | LeadPilot | B | [assert] synthetic test email address / domain (fixture only) |  |
| `tests/test_support_chat.py:718` | Vectorae | A | comment: docstring |  |
| `tests/test_support_chat.py:724` | LeadPilot | B | help-center article id / legacy FAQ alias / frontend route `what-is-leadpilot` |  |
| `tests/test_support_chat.py:743` | LeadPilot | B | [assert] help-center article id / legacy FAQ alias / frontend route `what-is-leadpilot` |  |
| `tests/test_support_chat.py:797` | Vectorae | A | [assert] asserts stored/forwarded user question text (echo of input) |  |
| `tests/test_tool_integrations.py:354` | Vectorae | A | comment: docstring |  |
| `tests/test_trust.py:44` | LeadPilot | B | synthetic test email address / domain (fixture only) |  |
| `tests/test_trust.py:61` | LeadPilot | B | synthetic test email address / domain (fixture only) |  |
| `tests/test_trust.py:67` | LeadPilot | B | synthetic test email address / domain (fixture only) |  |
| `tests/test_trust.py:119` | LeadPilot | B | synthetic test email address / domain (fixture only) |  |
| `tests/test_trust.py:127` | LeadPilot | B | [assert] synthetic test email address / domain (fixture only) |  |
| `tests/test_trust.py:160` | LeadPilot | B | [assert] synthetic test email address / domain (fixture only) |  |
| `tests/test_trust.py:205` | LeadPilot | B | synthetic test email address / domain (fixture only) |  |
| `tests/test_tutorials.py:1` | Vectorae | A | comment: docstring |  |
| `tests/test_tutorials.py:144` | Vectorae | A | search input q='vectorae' against tutorial catalogue text | depends on tutorial content containing the name |
| `tests/test_tutorials.py:351` | LeadPilot | B | asserts tutorial badge slug (persisted id) |  |
| `tests/test_tutorials.py:355` | LeadPilot | B | [assert] asserts tutorial badge slug (persisted id) |  |
| `tests/test_tutorials.py:468` | LeadPilot | B | [assert] synthetic test email address / domain (fixture only) |  |
| `tests/test_tutorials.py:511` | Vectorae | A | comment: docstring |  |
| `tests/test_unsubscribe_headers_raw.py:68` | LeadPilot | B | synthetic test email address / domain (fixture only) | SEALED |
| `tests/test_unsubscribe_headers_raw.py:105` | LeadPilot | B | synthetic test email address / domain (fixture only) | SEALED |
| `tests/test_unsubscribe_headers_raw.py:124` | LeadPilot | B | synthetic test email address / domain (fixture only) | SEALED |
| `tests/test_unsubscribe_headers_raw.py:134` | LeadPilot | B | synthetic test email address / domain (fixture only) | SEALED |
| `tests/test_unsubscribe_headers_raw.py:139` | LeadPilot | B | [assert] synthetic test email address / domain (fixture only) | SEALED |
| `tests/test_verification_oscillation.py:38` | Vectorae | A | fixture: synthetic customer product/sender named after us (assert on it only echoes the fixture) |  |
| `tests/test_verification_oscillation.py:43` | Vectorae | A | fixture: synthetic customer product/sender named after us (assert on it only echoes the fixture) |  |
| `tests/test_voice_profile.py:25` | Vectorae | A | fixture: synthetic customer product/sender named after us (assert on it only echoes the fixture) |  |
| `tests/test_voice_twin.py:110` | Vectorae | C | [assert] asserts ElevenLabs voice-clone name `Vectorae - <name>` (third-party account; consent instructions at app/services/voice_twin.py:884 quote it) | third-party + consent wording |
| `tests/test_voice_twin.py:292` | Vectorae | C | [assert] asserts ElevenLabs voice-clone name `Vectorae - <name>` (third-party account; consent instructions at app/services/voice_twin.py:884 quote it) | third-party + consent wording |
| `tests/test_website_builder.py:25` | Vectorae | A | fixture marketing-page HTML/meta title `| Vectorae`, footer copyright (SEO checker input) |  |
| `tests/test_website_builder.py:30` | LeadPilot | B | domain leadpilot.io (marketing SITE_ORIGIN in app/services/sitemap.py & website_builder.py, or fixture URL) |  |
| `tests/test_website_builder.py:46` | LeadPilot | B | fixture HTML internal link to blog slug `apollo-clay-leadpilot-comparison` (public URL) |  |
| `tests/test_website_builder.py:48` | Vectorae | A | fixture marketing-page HTML/meta title `| Vectorae`, footer copyright (SEO checker input) |  |
| `tests/test_website_builder.py:61` | Vectorae | A | fixture marketing-page HTML/meta title `| Vectorae`, footer copyright (SEO checker input) |  |
| `tests/test_website_builder.py:89` | Vectorae | A | fixture marketing-page HTML/meta title `| Vectorae`, footer copyright (SEO checker input) |  |
| `tests/test_website_builder.py:304` | LeadPilot | B | [assert] domain leadpilot.io (marketing SITE_ORIGIN in app/services/sitemap.py & website_builder.py, or fixture URL) |  |
| `tests/test_website_builder.py:306` | LeadPilot | B | [assert] domain leadpilot.io (marketing SITE_ORIGIN in app/services/sitemap.py & website_builder.py, or fixture URL) |  |
| `tests/test_website_builder.py:318` | LeadPilot | B | [assert] domain leadpilot.io (marketing SITE_ORIGIN in app/services/sitemap.py & website_builder.py, or fixture URL) |  |
| `tests/test_website_builder.py:393` | LeadPilot | B | domain leadpilot.io (marketing SITE_ORIGIN in app/services/sitemap.py & website_builder.py, or fixture URL) |  |
| `tests/test_website_builder.py:400` | Vectorae | A | fixture marketing-page HTML/meta title `| Vectorae`, footer copyright (SEO checker input) |  |
| `tests/test_website_builder.py:464` | LeadPilot | B | [assert] domain leadpilot.io (marketing SITE_ORIGIN in app/services/sitemap.py & website_builder.py, or fixture URL) |  |
| `tests/test_website_builder.py:470` | LeadPilot | B | [assert] domain leadpilot.io (marketing SITE_ORIGIN in app/services/sitemap.py & website_builder.py, or fixture URL) |  |
| `tests/test_whatsapp_template_lifecycle.py:59` | Vectorae | A | fixture: customer WhatsApp template body ('Sam from Vectorae'); name incidental |  |
| `tests/test_whatsapp_template_optout.py`:L43-154 (19 lines: 43,44,45,46,47,49,50,58,59,60,61,62,73,75,89,109,124,137,154) | LeadPilot x19 | A | fixture: customer WhatsApp template body ('Sam from LeadPilot') used to test STOP opt-out detection; name incidental (collapsed, homogeneous) | SEALED |
| `tests/test_whatsapp_template_optout.py:48` | LeadPilot x2 | B | synthetic test email address / domain (fixture only) | SEALED |
| `tests/test_workspaces.py:244` | LeadPilot | B | [assert] asserts DNS TXT verification record name customers already published |  |
| `tests/test_workspaces.py:247` | Vectorae | A | [assert] asserts default public brand_name `Vectorae` (app/services/workspaces.py:293) |  |
| `tests/test_workspaces.py:254` | LeadPilot | B | white-label base domain fixture |  |
| `tests/test_workspaces.py:255` | LeadPilot | B | [assert] white-label base domain fixture |  |
| `tests/test_workspaces.py:256` | LeadPilot | B | [assert] white-label base domain fixture |  |

### 2b. calendarharvest used as a domain/address (out of scope per brief; listed for completeness, not counted)

| path:line | snippet | risk |
|---|---|---|
| `tests/mcp/test_http_endpoint.py:55` | `monkeypatch.setattr(settings, "mcp_resource_url", "https://api.calendarharvest.com/mcp")` |  |
| `tests/mcp/test_http_endpoint.py:59` | `assert meta["resource"] == "https://api.calendarharvest.com/mcp"` |  |
| `tests/mcp/test_http_endpoint.py:60` | `assert meta["authorization_servers"] == ["https://api.calendarharvest.com"]` |  |
| `tests/test_connector_skill.py:21` | `MCP_URL = "https://api.calendarharvest.com/mcp"` |  |
| `tests/test_privacy_docs_truth.py:53` | `assert "ahmadshahid@calendarharvest.com" in POLICY` | SEALED |
| `tests/test_status_page_frontend_contract.py:1` | `"""The /status page in the main frontend (www.calendarharvest.com/status/)` |  |
| `tests/test_status_page_frontend_contract.py:45` | `production that list must hold https://www.calendarharvest.com — a` |  |
| `tests/test_status_public.py:1` | `"""Phase 3 (status.calendarharvest.com): GET /status/public, and GET /health` |  |
| `tests/test_unsubscribe_headers_raw.py:45` | `monkeypatch.setattr(settings, "public_base_url", "https://api.calendarharvest.com")` | SEALED |
| `tests/test_unsubscribe_headers_raw.py:87` | `uri = "<https://api.calendarharvest.com/unsubscribe/" + "gAAAAA" + "z" * 230 + ">"` | SEALED |

## 3. File / directory names containing a variant

None in this area. `git ls-files | grep -iE 'lead[ _.-]?pilot|client[ _.-]?hunter|vectorae|victorae'` restricted to `tests/`, `evals/`, root `test_*.py`, `smoke_test.py` returns nothing. (Tests do reference named paths outside the area: `.claude/skills/leadpilot-outbound/`, `plugins/leadpilot/` in `tests/test_connector_skill.py`, and `docs/help-center/01-what-is-leadpilot.md` / `frontend/src/app/what-is-leadpilot/` through the `what-is-leadpilot` article id.)

## 4. Generated or git-ignored files

- `evals/candidate.json` (git-ignored, `.gitignore:30`): written by `python3 evals/run_evals.py` from the junit run. It holds metric numbers only, no brand strings.
- `out_evals/` and `.pytest_cache/` (git-ignored): run outputs. They come back on the next run.
- `evals/baseline.json` (SEALED, tracked, 0 hits): numbers only. Only a reviewed gate PR may refresh it.
- Nothing under `tests/` is generated. `tests/help_center/golden_questions.yaml` and `code_facts.yaml` are written by hand. Their chunk ids (`<article-id>#<heading-slug>`) come from the help-center headings through `app/services/help_center.py:slugify`, so renaming a heading changes the id. The recall test is designed to fail when an id goes stale.

## 5. Surprises and risks

1. **The app still sends the OLD brand "LeadPilot", and a SEALED test locks it in.** `tests/test_pilot_mode.py:806` asserts the PDF title `"LeadPilot meetings-per-dollar ledger"` (app source: `app/services/meetings_ledger.py:672`). `tests/test_pilot_mode.py:1020` asserts the owner email line `"a 30-day pilot is running on your LeadPilot account"` (app source: `app/services/pilot_mode.py:597-598`). PR #113 (to Vectorae) missed both strings. Renaming them is a display change, but it fails a sealed compliance test. That test edit needs a `gate/` branch and its own reviewed PR, or the app change and the test change land in one gate PR.
2. **A hidden coupling between FakeClaude and the system prompt.** `tests/conftest.py:304` sends support-chat calls to the fake only when the system prompt contains `"Vectorae in-app support assistant"` (`app/services/support_chat.py:98`). If the prompt is renamed to Victorae and conftest is not, FakeClaude falls through to another branch. Dozens of support-chat and help-center tests then fail in confusing ways. Rename both in the same commit.
3. **Display strings that tests pin, which must change together with app and docs.**
   - `tests/test_workspaces.py:247`: default `brand_name == "Vectorae"` (`app/services/workspaces.py:293`).
   - `tests/mcp/test_read_tools.py:180-188` and `test_write_tools.py:102`: MCP error text `"... must be a Vectorae id"`.
   - `tests/test_support_chat.py:34` and `tests/help_center/test_support_integration.py:171,212`: help-center article title and first sentence.
   - `tests/help_center/code_facts.yaml` (7 phrases): must match the help-center prose word for word.
   - `tests/help_center/golden_questions.yaml`: 36 chunk ids whose heading slugs contain `vectorae`. They change as soon as the headings are renamed.
   - `tests/test_tutorials.py:144`: searches the catalogue for `q="vectorae"`.
4. **Product names forbidden in DMs.** `app/services/displacement_monitor.py:74` `FORBIDDEN_MENTIONS = ("vectorae", "leadpilot", "lead pilot")` lists no `victorae`. Without it, a new-name mention in a customer DM would pass the check. Add the new name to the list; do not swap it in. `tests/test_displacement_alerts.py` only tests "Vectorae", so a Victorae case should be added.
5. **Values in third-party systems that look like display text.**
   - Class B: `tests/test_crm_ecosystem.py:593` asserts the Salesforce `LeadSource = "Vectorae"` (`app/services/crm_sync.py:414`). Customers' Salesforce picklists and reports filter on this value. `code_facts.yaml:1169` reads the HubSpot/Salesforce deal-name default `"Vectorae deal"` from `crm_sync.py:460,466`.
   - Class C: `tests/test_voice_twin.py:110,292` asserts the ElevenLabs voice name `"Vectorae - <name>"`. The consent instructions at `app/services/voice_twin.py:884` tell the owner to look for this name, so it is consent and third-party wording.
   - `tests/test_meeting_recording.py:92` repeats the Recall bot name `"Vectorae Notetaker"` (`app/integrations/recall.py:154`). Prospects see this name in their meetings.
6. **Many identifiers still carry the OLD names, and the tests pin them (class B; do not rename for branding):**
   - Celery task names `leadpilot.*` (one sealed test: `test_champion_tracker.py:1059-1062`)
   - OAuth/MCP scopes `leadpilot:read|write|admin`
   - headers `X-LeadPilot-Signature|Delivery|Timestamp`
   - Android deep-link scheme `clienthunter://`
   - API-key prefix `lpk_`
   - DNS TXT record `_leadpilot-verify`
   - badge slug `leadpilot-certified`
   - enum value `leadpilot_calendar`
   - export ids `leadpilot-account-export` (SEALED `test_account_export.py:207`) and `leadpilot.meetings-ledger.v1`
   - logger name `leadpilot.external`
   - SDK package `clienthunter`
   - skill/plugin/MCP server name `leadpilot-outbound` / `leadpilot`
   - env vars `LEADPILOT_LIVE_*` and `VECTORAE_REQUIRE_NATIVE`, native modules `vectorae_native_rs|cpp` (a Victorae rename would leave these Vectorae-named)
   - repo slug `Rmasood1122/LeadPilot`
   - Postgres role/db `leadpilot` / `clienthunter_test`
7. **The marketing domain is `leadpilot.io`, not calendarharvest.com.** `tests/test_website_builder.py` asserts sitemap and robots URLs on `https://leadpilot.io`, which comes from `SITE_ORIGIN` in `app/services/sitemap.py:26` and `app/services/website_builder.py:39`. CLAUDE.md says the production domain is calendarharvest.com. This is outside my area; reported, not fixed.
8. **Fixtures shaped like customer messages contain the product name, but they are not DEFECTs.**
   - `tests/test_whatsapp_template_optout.py` (SEALED, 19 lines "Sam from LeadPilot")
   - `tests/conftest.py:556,1562` and `test_whatsapp_template_lifecycle.py:59` ("Sam from Vectorae")
   - Synthetic customer products named "Vectorae" in `test_verification_oscillation.py`, `test_voice_profile.py`, `integration/test_flows.py`, `integration/conftest.py:570`, `test_sequence_reviews.py:137`

   These are synthetic customer data in which the customer's company happens to share our name. No test checks that the product name gets into outreach. They can stay. Renaming them is cosmetic, and in the sealed file it is a gate-PR edit.
9. **The `leadpilot.dev` test-email domain is everywhere (141 lines, class B fixture, low risk).** The shared `test_user` is `test@leadpilot.dev` (`tests/conftest.py:1059`). Several tests assert that address (`test_profile.py:47`, `test_email_verification.py:173`, `test_support_chat.py:487`, `test_tutorials.py:468`, `test_share_links.py:134`). Eleven sealed files also hard-code `@leadpilot.dev`. Changing conftest alone breaks those asserts. Recommendation: leave these alone; nothing outside the tests depends on them.
10. **Two lines contain both an A and a B occurrence.**
    - `test_whatsapp_template_optout.py:48`: "Sam from LeadPilot" plus the URL `leadpilot.example`.
    - `golden_questions.yaml` lines with `what-is-leadpilot#...vectorae...`: the article id is B and the heading slug is A.

    The table classifies each of these by its stricter (B) part.

# Part 7 — Brand inventory: config / infra / tooling area

_Source: subagent sweep, file `brand-config-infra.md`._

Scope: git-tracked files under `alembic/`, `alembic.ini`, `.github/`, `.claude/`, `.claude-plugin/`, `.githooks/`, `claude/`, `plugins/`, `scripts/`, `.env.example`, `.env.production.example`, `Dockerfile` (root), `docker-compose*.yml`, `render.yaml`, `railway/`, `nginx/`, `pyproject.toml`, `requirements*.txt/lock`, `celerybeat-schedule.*`, `.vscode`, `.gitattributes`, `.dockerignore` (172 tracked files). Read-only sweep, nothing in the repo was modified.

Command: `git grep -nIiE 'lead[ _.-]?pilot|client[ _.-]?hunter|vectorae'` over that file list (plus a separate pass for `victorae`, `lpk_`, `calendar ?harvest`). Counts were checked with `git grep -c` and `git grep -o | uniq -c`.

## 1. Summary

- **186 matching lines, 218 occurrences, in 48 files.**
- By variant (occurrences): **Vectorae 103**, **LeadPilot / leadpilot 81**, **ClientHunter / clienthunter 34**. `Victorae`: 0. `lpk_`: 0 in this area. `calendarharvest`: 17 occurrences, all used as a **domain** (none as a product name), so they are outside the brief's count. They are listed in section 6.
- By class (occurrences): **B 110**, **A 73**, **A-comment 26**, **C 8**, **DEFECT 1**.
- No hits in `alembic.ini`, `railway/`, `requirements.lock`, `.vscode/settings.json`, `.gitattributes`, `.claude/settings*`, or anything in `.github/` outside the workflows. `.dockerignore` has only a calendarharvest domain hit.
- Not covered here: `frontend/Dockerfile` (frontend area). It had no hits in this sweep's file list.

Top risks (B/C that must not change by a plain find-and-replace):
1. Android `ANDROID_PACKAGE_NAME` / `KEY_ALIAS` (`com.clienthunter.app`, `io.clienthunter.app`, the "clienthunter" keystore alias). These cannot be changed after a Play publish.
2. PyPI package and CLI `clienthunter` (pypi-release.yml). It is published, so renaming means shipping a new package.
3. Render service names `leadpilot-api` / `leadpilot-worker`. Renaming creates new services with new URLs.
4. MCP server name `leadpilot`, plugin and marketplace id `leadpilot`, skill `leadpilot-outbound`, OAuth scope `leadpilot:write`. Existing users' installs, tool allowlists and OAuth grants depend on these.
5. Prod Postgres DB/role `clienthunter` (docker-compose.prod.yml, .env.production.example). Renaming the default orphans the existing volume.
6. C items: `EMAIL_FROM_NAME=Vectorae` (Resend sender name, 3 places), `SENDER_IDENTITY=Vectorae, <street>…` (the CAN-SPAM postal identity, which is legal text), the plugin/marketplace author/owner name.

## 2. Occurrences

Class key: A = display, A-comment = code comment/docstring, B = identifier, C = needs human, DEFECT = customer-voice injection. "(xN)" = N occurrences on that line. Every line is listed. No file had more than 15 homogeneous rows, so nothing was collapsed.

| path:line | variant | class | reason | risk |
|---|---|---|---|---|
| `.claude-plugin/marketplace.json:2` | LeadPilot | B | marketplace name; users run `/plugin marketplace add` and refer to it as `leadpilot` | High: renaming breaks installs of `plugin@leadpilot` |
| `.claude-plugin/marketplace.json:4` | Vectorae | C | marketplace owner name shown in Claude Code plugin UI (third-party listing) | Med |
| `.claude-plugin/marketplace.json:8` | LeadPilot | B | plugin name in marketplace (install id `leadpilot@leadpilot`) | High |
| `.claude-plugin/marketplace.json:9` | LeadPilot | B | path to plugin dir (must match dir name plugins/leadpilot) | Med: change with dir rename |
| `.claude-plugin/marketplace.json:10` | LeadPilot/Vectorae (x2) | A | marketplace description text (Vectorae display + `leadpilot-outbound` skill id inside it) | Low; skill id part is B |
| `.claude/agents/help-center-fact-checker.md:7` | Vectorae | A | dev-agent prompt prose naming the product | Low |
| `.claude/hooks/require_gate.py:8` | LeadPilot | B | gate-stamp dir `leadpilot-gate` under git-common-dir; writer (quick_gate.py) and readers (pre-push, Claude hooks) must agree | Med: rename all 3 together or pushes are blocked; existing stamps invalidated |
| `.claude/hooks/require_gate.py:49` | LeadPilot | B | gate-stamp dir `leadpilot-gate` under git-common-dir; writer (quick_gate.py) and readers (pre-push, Claude hooks) must agree | Med: rename all 3 together or pushes are blocked; existing stamps invalidated |
| `.claude/hooks/stop_check.py:51` | LeadPilot | B | gate-stamp dir `leadpilot-gate` under git-common-dir; writer (quick_gate.py) and readers (pre-push, Claude hooks) must agree | Med: rename all 3 together or pushes are blocked; existing stamps invalidated |
| `.claude/skills/leadpilot-outbound/SKILL.md:2` | LeadPilot | B | skill name `leadpilot-outbound` (invocation id; listed in skill registry) | Med: user/agent invocations by name break |
| `.claude/skills/leadpilot-outbound/SKILL.md:3` | Vectorae (x3) | A | skill prose shown to/used by Claude, names the product to the user | Low |
| `.claude/skills/leadpilot-outbound/SKILL.md:6` | Vectorae | A | skill prose shown to/used by Claude, names the product to the user | Low |
| `.claude/skills/leadpilot-outbound/SKILL.md:8` | Vectorae | A | skill prose shown to/used by Claude, names the product to the user | Low |
| `.claude/skills/leadpilot-outbound/SKILL.md:13` | Vectorae | A | skill prose shown to/used by Claude, names the product to the user | Low |
| `.claude/skills/leadpilot-outbound/SKILL.md:19` | Vectorae | A | skill prose shown to/used by Claude, names the product to the user | Low |
| `.claude/skills/leadpilot-outbound/SKILL.md:21` | Vectorae | A | skill prose shown to/used by Claude, names the product to the user | Low |
| `.claude/skills/leadpilot-outbound/SKILL.md:74` | Vectorae | A | skill prose shown to/used by Claude, names the product to the user | Low |
| `.claude/skills/leadpilot-outbound/references/glossary.md:1` | Vectorae | A | doc heading | Low |
| `.claude/skills/leadpilot-outbound/references/tools.md:1` | Vectorae | A | doc heading | Low |
| `.claude/skills/leadpilot-outbound/references/tools.md:37` | Vectorae | A | quotes an API error string "must be a Vectorae id" (must track the server-side message) | Low: keep in sync with app error text |
| `.claude/skills/leadpilot-outbound/references/tools.md:39` | LeadPilot | B | quotes OAuth scope string `leadpilot:write` | High: scope string is an identifier granted to existing OAuth clients |
| `.claude/skills/leadpilot-outbound/references/tools.md:46` | Vectorae | A | instruction prose "sign in to Vectorae" | Low |
| `.claude/skills/leadpilot-outbound/references/tools.md:47` | LeadPilot | B | plugin id `leadpilot` users install | Med |
| `.claude/skills/leadpilot-outbound/references/tools.md:48` | LeadPilot | B | MCP server name `leadpilot` in `claude mcp add` command | Med: users' existing configs use this name |
| `.env.example:1` | ClientHunter | A-comment | file header comment | Low |
| `.env.example:24` | ClientHunter | B | local DB name `clienthunter` in DATABASE_URL | Low (dev), but must match local DBs |
| `.env.example:159` | Vectorae | C | EMAIL_FROM_NAME value: Resend sender display name recipients see | Med: deliverability/sender-identity; founder decision |
| `.env.example:278` | ClientHunter | B | ANDROID_PACKAGE_NAME com.clienthunter.app (Play Store applicationId) | Critical: immutable after Play publish |
| `.env.example:455` | Vectorae | A-comment | comment describing Vectorae's SignalForge API key scopes | Low |
| `.env.example:456` | Vectorae | A-comment | comment describing Vectorae's SignalForge API key scopes | Low |
| `.env.example:458` | Vectorae | A-comment | comment describing Vectorae's SignalForge API key scopes | Low |
| `.env.production.example:2` | ClientHunter | A-comment | file header comment | Low |
| `.env.production.example:21` | LeadPilot | B | ADMIN_EMAIL admin@leadpilot.com (mailbox/domain, stale: prod domain is calendarharvest.com) | Med: stale domain in prod template |
| `.env.production.example:34` | ClientHunter | B | POSTGRES_DB clienthunter | High in prod: renaming orphans existing DB/volume |
| `.env.production.example:35` | ClientHunter | B | POSTGRES_USER clienthunter | High in prod |
| `.env.production.example:38` | ClientHunter (x2) | B | DATABASE_URL user+db clienthunter (x2) | High in prod |
| `.env.production.example:72` | LeadPilot | B | GMAIL_REDIRECT_URI on api.leadpilot.com (OAuth redirect registered at Google; stale domain) | High: must match Google console |
| `.env.production.example:110` | LeadPilot | B | PUBLIC_BASE_URL api.leadpilot.com (stale domain) | Med |
| `.env.production.example:114` | Vectorae | C | comment quoting the CAN-SPAM footer placeholder "Vectorae User, 123 Main St..." (code default) | Med: legal footer text |
| `.env.production.example:116` | Vectorae | C | SENDER_IDENTITY value: CAN-SPAM postal identity printed in every outbound email footer | High: legal identity; must be the real legal entity, not the brand |
| `.env.production.example:118` | LeadPilot | B | FRONTEND_URL leadpilot.com (stale domain) | Med |
| `.env.production.example:129` | LeadPilot (x2) | B | CORS_ORIGINS leadpilot.com, www.leadpilot.com (x2; stale domain) | Med: wrong CORS breaks frontend |
| `.env.production.example:136` | LeadPilot | B | NEXT_PUBLIC_API_URL api.leadpilot.com (stale domain) | Med |
| `.env.production.example:190` | ClientHunter | B | ANDROID_PACKAGE_NAME io.clienthunter.app (applicationId; NOTE differs from actual com.clienthunter.app) | Critical: immutable; also an existing mismatch |
| `.env.production.example:203` | Vectorae | C | EMAIL_FROM_NAME value Vectorae (sender name recipients see) | Med |
| `.env.production.example:292` | Vectorae | A-comment | comment on SignalForge key scopes | Low |
| `.env.production.example:293` | Vectorae | A-comment | comment on SignalForge key scopes | Low |
| `.env.production.example:295` | Vectorae | A-comment | comment on SignalForge key scopes | Low |
| `.githooks/pre-push:2` | Vectorae | A-comment | hook header comment | Low |
| `.githooks/pre-push:7` | LeadPilot | B | gate-stamp dir `leadpilot-gate` under git-common-dir; writer (quick_gate.py) and readers (pre-push, Claude hooks) must agree | Med: rename all 3 together or pushes are blocked; existing stamps invalidated |
| `.githooks/pre-push:19` | LeadPilot | B | gate-stamp dir `leadpilot-gate` under git-common-dir; writer (quick_gate.py) and readers (pre-push, Claude hooks) must agree | Med: rename all 3 together or pushes are blocked; existing stamps invalidated |
| `.github/workflows/android-release.yml:16` | ClientHunter | B | comment documenting KEY_ALIAS example "clienthunter" (Android upload-keystore alias) | Critical if real alias: keystore alias cannot be renamed without re-keying |
| `.github/workflows/android-release.yml:18` | ClientHunter | B | comment example URL api.clienthunter.app (domain, stale) | Low |
| `.github/workflows/android-release.yml:120` | ClientHunter | B | CI artifact name clienthunter-prod-release-<sha> | Low: only downstream download scripts depend on it |
| `.github/workflows/eval-gate.yml:2` | LeadPilot | A-comment | header comment of SEALED file .github/workflows/eval-gate.yml | Low, but SEALED: needs its own reviewed PR |
| `.github/workflows/pypi-release.yml:101` | ClientHunter | B | PyPI package name `clienthunter` (sdk/pyproject.toml name) | Critical: published PyPI name; rename = new package |
| `.github/workflows/pypi-release.yml:106` | ClientHunter | B | CLI entry-point command `clienthunter` | High: users' scripts call it |
| `.github/workflows/pypi-release.yml:107` | ClientHunter | B | CLI entry-point command `clienthunter` | High |
| `.github/workflows/pypi-release.yml:138` | ClientHunter | A | GitHub release notes heading "clienthunter SDK release" (display, but names the PyPI pkg) | Low |
| `.github/workflows/pypi-release.yml:142` | ClientHunter | B | pip install clienthunter== in release notes (PyPI name) | High |
| `.github/workflows/verify.yml:41` | LeadPilot | B | CI Postgres service credential/db name (POSTGRES_USER); must match scripts/gate/full_gate.sh and scripts/verify_debug_router_guard.py defaults | Low (ephemeral CI), change together |
| `.github/workflows/verify.yml:42` | LeadPilot | B | CI Postgres service credential/db name (POSTGRES_PASSWORD); must match scripts/gate/full_gate.sh and scripts/verify_debug_router_guard.py defaults | Low (ephemeral CI), change together |
| `.github/workflows/verify.yml:43` | ClientHunter | B | CI Postgres service credential/db name (POSTGRES_DB clienthunter_test); must match scripts/gate/full_gate.sh and scripts/verify_debug_router_guard.py defaults | Low (ephemeral CI), change together |
| `.github/workflows/verify.yml:46` | LeadPilot | B | CI Postgres service credential/db name (pg_isready -U leadpilot); must match scripts/gate/full_gate.sh and scripts/verify_debug_router_guard.py defaults | Low (ephemeral CI), change together |
| `.github/workflows/verify.yml:52` | ClientHunter/LeadPilot (x3) | B | CI Postgres service credential/db name (TEST_DATABASE_URL user/pass/db); must match scripts/gate/full_gate.sh and scripts/verify_debug_router_guard.py defaults | Low (ephemeral CI), change together |
| `.github/workflows/verify.yml:91` | LeadPilot (x2) | B | CI Postgres service credential/db name (DATABASE_URL user/pass); must match scripts/gate/full_gate.sh and scripts/verify_debug_router_guard.py defaults | Low (ephemeral CI), change together |
| `.github/workflows/verify.yml:92` | LeadPilot | B | CI Postgres service credential/db name (PGPASSWORD); must match scripts/gate/full_gate.sh and scripts/verify_debug_router_guard.py defaults | Low (ephemeral CI), change together |
| `.github/workflows/verify.yml:94` | ClientHunter/LeadPilot (x2) | B | CI Postgres service credential/db name (psql -U leadpilot -d clienthunter_test); must match scripts/gate/full_gate.sh and scripts/verify_debug_router_guard.py defaults | Low (ephemeral CI), change together |
| `.github/workflows/verify.yml:155` | LeadPilot | B | env var name LEADPILOT_API_URL (status-page build) | Med: Vercel env var must be renamed in lockstep |
| `.github/workflows/verify.yml:222` | LeadPilot | B | Docker image tag leadpilot-verify:ci (CI-local) | Low |
| `.github/workflows/verify.yml:230` | LeadPilot/Vectorae (x3) | B | image tag leadpilot-verify + Python module names vectorae_native_rs / vectorae_native_cpp (compiled extension import names) | Med: module names are wheel/import identifiers |
| `.github/workflows/verify.yml:232` | Vectorae (x2) | A-comment | comment + doc path docs/features/vectorae-agents.md (path = B if doc renamed) | Low |
| `.github/workflows/verify.yml:236` | Vectorae | B | env var VECTORAE_REQUIRE_NATIVE in comment | Med |
| `.github/workflows/verify.yml:281` | Vectorae | B | env var VECTORAE_REQUIRE_NATIVE | Med: read by app/agents/native.py |
| `Dockerfile:16` | Vectorae (x2) | A-comment | section comment + doc path vectorae-agents.md | Low |
| `Dockerfile:65` | Vectorae | B | comment naming env var VECTORAE_REQUIRE_NATIVE | Low |
| `Dockerfile:70` | Vectorae | B | ENV VECTORAE_REQUIRE_NATIVE=1 | Med |
| `alembic/versions/0016_tutorial_progress.py:1` | Vectorae | B | docstring "Learn Vectorae" in SHIPPED migration (A-comment content, frozen by rule) | None if untouched; never edit |
| `alembic/versions/0029_crm_ecosystem.py:5` | Vectorae | B | docstring in SHIPPED migration (A-comment content) | Never edit |
| `alembic/versions/0058_inbox_handling.py:15` | Vectorae | B | docstring in SHIPPED migration (A-comment content) | Never edit |
| `alembic/versions/0065_messages_dispatch_index.py:3` | LeadPilot | B | docstring naming Celery task `leadpilot.outreach.dispatch` in SHIPPED migration | Never edit; task name itself is B (see celerybeat note) |
| `alembic/versions/0068_linkedin_network.py:10` | Vectorae | B | docstring in SHIPPED migration (A-comment content) | Never edit |
| `alembic/versions/0092_agent_runs.py:1` | Vectorae | B | docstring in SHIPPED migration (A-comment content) | Never edit |
| `alembic/versions/0092_agent_runs.py:3` | Vectorae | B | doc path in SHIPPED migration docstring | Never edit |
| `claude/STATUS_2026-09-29_LEADPILOT_GATE_LIVE_ROLLOUT_COMPLETE.md:1` | Vectorae | A | historical status report prose | Low: historical record, arguably leave as-is |
| `claude/STATUS_2026-09-29_LEADPILOT_GATE_LIVE_ROLLOUT_COMPLETE.md:6` | LeadPilot | A | names the Claude Project "LeadPilot Production Readiness" (external project name) | Low |
| `claude/STATUS_2026-09-29_LEADPILOT_GATE_LIVE_ROLLOUT_COMPLETE.md:8` | LeadPilot (x2) | B | GitHub repo slug Rmasood1122/LeadPilot + actions URL (x2) | Low: historical link; repo rename would redirect |
| `claude/STATUS_2026-09-29_LEADPILOT_GATE_LIVE_ROLLOUT_COMPLETE.md:11` | Vectorae | A | historical prose | Low |
| `claude/STATUS_2026-09-29_LEADPILOT_GATE_LIVE_ROLLOUT_COMPLETE.md:40` | Vectorae | A | historical table cell | Low |
| `docker-compose.prod.yml:1` | ClientHunter | A-comment | header comment | Low |
| `docker-compose.prod.yml:52` | ClientHunter | B | prod Postgres default DB/user `clienthunter` | High: renaming default orphans existing prod volume/role |
| `docker-compose.prod.yml:53` | ClientHunter | B | prod Postgres default DB/user `clienthunter` | High: renaming default orphans existing prod volume/role |
| `docker-compose.prod.yml:58` | ClientHunter | B | prod Postgres default DB/user `clienthunter` | High: renaming default orphans existing prod volume/role |
| `docker-compose.yml:19` | LeadPilot | B | dev Postgres user/password/db `leadpilot` | Low (dev), but existing local volumes break |
| `docker-compose.yml:20` | LeadPilot | B | dev Postgres user/password/db `leadpilot` | Low (dev), but existing local volumes break |
| `docker-compose.yml:21` | LeadPilot | B | dev Postgres user/password/db `leadpilot` | Low (dev), but existing local volumes break |
| `docker-compose.yml:27` | LeadPilot | B | dev Postgres user/password/db `leadpilot` | Low (dev), but existing local volumes break |
| `docker-compose.yml:47` | LeadPilot (x3) | B | dev DATABASE_URL leadpilot:leadpilot@db/leadpilot (x3) | Low (dev) |
| `docker-compose.yml:78` | LeadPilot (x3) | B | dev DATABASE_URL leadpilot:leadpilot@db/leadpilot (x3) | Low (dev) |
| `docker-compose.yml:109` | LeadPilot (x3) | B | dev DATABASE_URL leadpilot:leadpilot@db/leadpilot (x3) | Low (dev) |
| `nginx/certbot-setup.sh:17` | ClientHunter | A | console banner printed to operator | Low |
| `nginx/nginx.conf:1` | ClientHunter | A-comment | header comment | Low |
| `plugins/leadpilot/.claude-plugin/plugin.json:2` | LeadPilot | B | plugin name `leadpilot` (install id in marketplace) | High |
| `plugins/leadpilot/.claude-plugin/plugin.json:4` | LeadPilot/Vectorae (x3) | A | plugin description (display) incl. skill id `leadpilot-outbound` (B part) | Low |
| `plugins/leadpilot/.claude-plugin/plugin.json:6` | Vectorae | C | plugin author name shown in marketplace listing | Med |
| `plugins/leadpilot/.claude-plugin/plugin.json:9` | LeadPilot | B | marketplace search keyword `leadpilot` (discoverability; old users search it) | Low: could keep both |
| `plugins/leadpilot/.mcp.json:3` | LeadPilot | B | MCP server name `leadpilot` (tool prefix mcp__leadpilot__* in users' permission allowlists) | High: renaming changes every tool id users have allowed |
| `plugins/leadpilot/skills/leadpilot-outbound/SKILL.md:2` | LeadPilot | B | skill name `leadpilot-outbound` (invocation id; listed in skill registry) | Med: user/agent invocations by name break |
| `plugins/leadpilot/skills/leadpilot-outbound/SKILL.md:3` | Vectorae (x3) | A | skill prose shown to/used by Claude, names the product to the user | Low |
| `plugins/leadpilot/skills/leadpilot-outbound/SKILL.md:6` | Vectorae | A | skill prose shown to/used by Claude, names the product to the user | Low |
| `plugins/leadpilot/skills/leadpilot-outbound/SKILL.md:8` | Vectorae | A | skill prose shown to/used by Claude, names the product to the user | Low |
| `plugins/leadpilot/skills/leadpilot-outbound/SKILL.md:13` | Vectorae | A | skill prose shown to/used by Claude, names the product to the user | Low |
| `plugins/leadpilot/skills/leadpilot-outbound/SKILL.md:19` | Vectorae | A | skill prose shown to/used by Claude, names the product to the user | Low |
| `plugins/leadpilot/skills/leadpilot-outbound/SKILL.md:21` | Vectorae | A | skill prose shown to/used by Claude, names the product to the user | Low |
| `plugins/leadpilot/skills/leadpilot-outbound/SKILL.md:74` | Vectorae | A | skill prose shown to/used by Claude, names the product to the user | Low |
| `plugins/leadpilot/skills/leadpilot-outbound/references/glossary.md:1` | Vectorae | A | doc heading | Low |
| `plugins/leadpilot/skills/leadpilot-outbound/references/tools.md:1` | Vectorae | A | doc heading | Low |
| `plugins/leadpilot/skills/leadpilot-outbound/references/tools.md:37` | Vectorae | A | quotes an API error string "must be a Vectorae id" (must track the server-side message) | Low: keep in sync with app error text |
| `plugins/leadpilot/skills/leadpilot-outbound/references/tools.md:39` | LeadPilot | B | quotes OAuth scope string `leadpilot:write` | High: scope string is an identifier granted to existing OAuth clients |
| `plugins/leadpilot/skills/leadpilot-outbound/references/tools.md:46` | Vectorae | A | instruction prose "sign in to Vectorae" | Low |
| `plugins/leadpilot/skills/leadpilot-outbound/references/tools.md:47` | LeadPilot | B | plugin id `leadpilot` users install | Med |
| `plugins/leadpilot/skills/leadpilot-outbound/references/tools.md:48` | LeadPilot | B | MCP server name `leadpilot` in `claude mcp add` command | Med: users' existing configs use this name |
| `pyproject.toml:6` | LeadPilot | B | Python project/dist name `leadpilot` (backend; not published to PyPI as far as seen) | Med: pip metadata, dependency pins tests |
| `pyproject.toml:8` | Vectorae | A | package description | Low |
| `render.yaml:1` | Vectorae | A-comment | header comment | Low |
| `render.yaml:8` | LeadPilot | B | comment naming Render service leadpilot-api | Low |
| `render.yaml:9` | LeadPilot | B | comment naming Render service leadpilot-worker | Low |
| `render.yaml:37` | LeadPilot | B | Render service name leadpilot-api (determines *.onrender.com URL; Blueprint sync) | Critical: rename = new service/URL |
| `render.yaml:118` | Vectorae | C | EMAIL_FROM_NAME value Vectorae (Resend sender name) | Med |
| `render.yaml:149` | LeadPilot | B | Render service name leadpilot-worker | Critical |
| `render.yaml:218` | Vectorae | C | EMAIL_FROM_NAME value Vectorae (worker) | Med |
| `requirements.txt:1` | ClientHunter | A-comment | header comment | Low |
| `scripts/TUTORIAL_VIDEO_URLS.md:30` | LeadPilot | B | tutorial slug welcome-to-leadpilot in admin API path | Med: DB key in tutorial_catalogue |
| `scripts/TUTORIAL_VIDEO_URLS.md:45` | LeadPilot/Vectorae (x2) | B | slug welcome-to-leadpilot (B) + title "Welcome to Vectorae" (A) on same line | Med |
| `scripts/TUTORIAL_VIDEO_URLS.md:58` | LeadPilot | B | SQL WHERE slug = welcome-to-leadpilot | Med |
| `scripts/TUTORIAL_VIDEO_URLS.md:103` | Vectorae | A | doc prose (tutorial title) | Low |
| `scripts/activate_with_keys.py:1` | Vectorae | A-comment | module docstring | Low |
| `scripts/activate_with_keys.py:428` | Vectorae | A | subject of activation test email sent in platform's own name | Low |
| `scripts/activate_with_keys.py:587` | Vectorae | A | operator console banner | Low |
| `scripts/activate_with_keys.py:632` | Vectorae | A | operator console output | Low |
| `scripts/benchmark.py:2` | ClientHunter | A | docstring / console output / argparse description | Low |
| `scripts/benchmark.py:207` | ClientHunter | A | docstring / console output / argparse description | Low |
| `scripts/benchmark.py:234` | ClientHunter | A | docstring / console output / argparse description | Low |
| `scripts/bump_version.py:2` | ClientHunter | B | names PyPI package clienthunter (docstring) | Low |
| `scripts/gate/full_gate.sh:9` | ClientHunter/LeadPilot (x3) | B | comment: default test DB URL leadpilot/clienthunter_test | Low; matches verify.yml |
| `scripts/gate/full_gate.sh:36` | ClientHunter/LeadPilot (x3) | B | default PG_URL leadpilot:leadpilot@.../clienthunter_test | Low; must match CI service |
| `scripts/gate/quick_gate.py:24` | LeadPilot | B | gate-stamp dir `leadpilot-gate` under git-common-dir; writer (quick_gate.py) and readers (pre-push, Claude hooks) must agree | Med: rename all 3 together or pushes are blocked; existing stamps invalidated |
| `scripts/gate/quick_gate.py:72` | LeadPilot | B | gate-stamp dir `leadpilot-gate` under git-common-dir; writer (quick_gate.py) and readers (pre-push, Claude hooks) must agree | Med: rename all 3 together or pushes are blocked; existing stamps invalidated |
| `scripts/help_center/build_index.py:27` | Vectorae | A-comment | comment example sentence | Low |
| `scripts/help_center/live_eval.py:121` | Vectorae | A | probe question to Help AI "What is Vectorae?" (eval expects product-named answer) | Med: Help AI answers must follow rename |
| `scripts/phase_c_pipeline.py:3` | LeadPilot | B | Celery task name leadpilot.run_pipeline (in docstring) | Med: task names are queue identifiers |
| `scripts/phase_c_pipeline.py:172` | LeadPilot | DEFECT | synthetic booking_url calendly.example/leadpilot/15min injected into a rendered outreach message (customer voice) | Low: manual verification script, placeholder domain; see section 5 |
| `scripts/seed_seo_pages.py:1` | LeadPilot | A-comment | docstring; names stale domain leadpilot.io | Low |
| `scripts/seed_seo_pages.py:11` | LeadPilot | A-comment | docstring; stale domain leadpilot.io | Low |
| `scripts/seed_seo_pages.py:34` | Vectorae | A | public SEO page title/meta/brief text | Med: public site/SEO |
| `scripts/seed_seo_pages.py:35` | Vectorae | A | public SEO page title/meta/brief text | Med: public site/SEO |
| `scripts/seed_seo_pages.py:37` | Vectorae | A | public SEO page title/meta/brief text | Med: public site/SEO |
| `scripts/seed_seo_pages.py:43` | Vectorae | A | public SEO page title/meta/brief text | Med: public site/SEO |
| `scripts/seed_seo_pages.py:46` | Vectorae | A | public SEO page title/meta/brief text | Med: public site/SEO |
| `scripts/seed_seo_pages.py:55` | Vectorae | A | public SEO page title/meta/brief text | Med: public site/SEO |
| `scripts/seed_seo_pages.py:73` | LeadPilot | B | public URL slug blog/apollo-clay-leadpilot-comparison (indexed URL) | Med: SEO URL; needs redirect if renamed |
| `scripts/seed_seo_pages.py:74` | Vectorae | A | public SEO page title/meta/brief text | Med: public site/SEO |
| `scripts/seed_seo_pages.py:75` | Vectorae (x2) | A | public SEO page title/meta/brief text | Med: public site/SEO |
| `scripts/seed_seo_pages.py:97` | Vectorae | A | public SEO page title/meta/brief text | Med: public site/SEO |
| `scripts/seed_seo_pages.py:117` | Vectorae | A | public SEO page title/meta/brief text | Med: public site/SEO |
| `scripts/seed_seo_pages.py:160` | LeadPilot | A-comment | comment; stale domain leadpilot.io | Low |
| `scripts/seed_tutorials.py:1` | Vectorae | A-comment | docstring "Learn Vectorae" | Low |
| `scripts/seed_tutorials.py:47` | LeadPilot | B | tutorial slug welcome-to-leadpilot (tutorial_catalogue key, referenced by tutorial_progress rows) | Med |
| `scripts/seed_tutorials.py:48` | Vectorae | A | tutorial title/description shown in app | Low |
| `scripts/seed_tutorials.py:53` | Vectorae | A | tutorial title/description shown in app | Low |
| `scripts/seed_tutorials.py:65` | Vectorae | A | tutorial title/description shown in app | Low |
| `scripts/seed_tutorials.py:75` | Vectorae | A | tutorial title/description shown in app | Low |
| `scripts/seed_tutorials.py:99` | Vectorae | A | tutorial title/description shown in app | Low |
| `scripts/seed_tutorials.py:123` | Vectorae | A | tutorial title/description shown in app | Low |
| `scripts/seed_tutorials.py:136` | Vectorae | A | tutorial title/description shown in app | Low |
| `scripts/support_chat_adversarial.py:21` | Vectorae | A-comment | docstring | Low |
| `scripts/support_chat_adversarial.py:38` | Vectorae | A | adversarial eval question to support chat naming the product | Low: test-like; update with Help AI |
| `scripts/support_chat_adversarial.py:69` | Vectorae | A | adversarial eval question to support chat naming the product | Low: test-like; update with Help AI |
| `scripts/support_chat_adversarial.py:70` | Vectorae | A | adversarial eval question to support chat naming the product | Low: test-like; update with Help AI |
| `scripts/support_chat_adversarial.py:73` | Vectorae | A-comment | comment | Low |
| `scripts/support_chat_adversarial.py:77` | Vectorae | A | adversarial eval question to support chat naming the product | Low: test-like; update with Help AI |
| `scripts/support_chat_adversarial.py:105` | Vectorae | A | adversarial eval question to support chat naming the product | Low: test-like; update with Help AI |
| `scripts/verify_debug_router_guard.py:51` | ClientHunter/LeadPilot (x3) | B | test DATABASE_URL leadpilot/clienthunter_test | Low |
| `scripts/verify_meeting_platforms.py:56` | Vectorae | A | calendar event title created on real Google Calendar (operator-visible) | Low |
| `scripts/verify_meeting_platforms.py:82` | Vectorae | A | Zoom meeting topic (operator-visible) | Low |
| `scripts/verify_meeting_platforms.py:95` | Vectorae | A | argparse help text | Low |

## 3. File / directory NAMES containing a variant

| path | variant | class | reason | risk |
|---|---|---|---|---|
| `plugins/leadpilot/` (dir) | LeadPilot | B | plugin source dir. `.claude-plugin/marketplace.json:9` points at it | Med: rename together with marketplace `source` |
| `plugins/leadpilot/skills/leadpilot-outbound/` (dir) | LeadPilot | B | skill dir = skill name `leadpilot-outbound` | Med |
| `.claude/skills/leadpilot-outbound/` (dir) | LeadPilot | B | project-local copy of the same skill (byte-identical to the plugin copy, checked with `diff -r`) | Med: the two copies must stay in sync |
| `claude/STATUS_2026-09-29_LEADPILOT_GATE_LIVE_ROLLOUT_COMPLETE.md` | LeadPilot | A | historical status report filename | Low: historical record, best left alone |

There are no variant names in the `alembic/versions/*` filenames, the workflows, or the scripts.

## 4. Generated / non-source files

- **`celerybeat-schedule.dat` / `.dir` / `.bak`**: Celery beat's `shelve` (dbm.dumb) persistence file. It is written by `celery beat` at runtime and is regenerated from the beat schedule in `app/workers/celery_app.py` on the next beat start. `.dat` is binary pickle data. A raw byte scan finds the **Celery task names** `leadpilot.outreach.dispatch` (x2), `leadpilot.outreach.poll_replies` (x2) and `leadpilot.outreach.check_followup_due` (x1). These are class B identifiers (task names plus the routing glob `leadpilot.outreach.*` in `app/workers/celery_app.py:114`). Not inventoried line by line. **Surprise:** these files are *tracked in git* (last touched by the merge of PR #62). They are excluded in `.dockerignore:90` but NOT in `.gitignore`. They should probably be untracked and gitignored, and they regenerate automatically. If the task names are ever renamed, delete the shelve file so beat does not keep stale entries.
- No other generated or ignored files in this area carry the brand.

## 5. Surprises / notes for triage (reported, not fixed)

1. **Customer-voice DEFECT (low): `scripts/phase_c_pipeline.py:172`** passes `booking_url="https://calendly.example/leadpilot/15min"` into `render_message()`, and then asserts the URL survives into the generated outreach body. The brand ends up inside a message written in a customer's voice. It is a manual verification script with a placeholder `.example` domain, so no real prospect receives it. Rename the path segment when the scripts are touched.
2. **Android package mismatch (not a brand issue, but found here):** `.env.example:278` says `com.clienthunter.app`, `.env.production.example:190` says `io.clienthunter.app`, and the code default `app/core/config.py:438` is `io.clienthunter.app`. The real applicationId is `com.clienthunter.app` (`frontend/android/app/build.gradle:31`, `frontend/capacitor.config.ts:8`). The prod template and the code default appear wrong today, whatever happens with the rebrand.
3. **Stale `leadpilot.com` / `leadpilot.io` domains** in `.env.production.example` (ADMIN_EMAIL, GMAIL_REDIRECT_URI, PUBLIC_BASE_URL, FRONTEND_URL, CORS_ORIGINS, NEXT_PUBLIC_API_URL) and in `scripts/seed_seo_pages.py` docstrings. Also `api.clienthunter.app` in the android-release.yml comment. Production uses `calendarharvest.com` (render.yaml, `.env.example`). Anyone copying the prod template gets the wrong domains. Classed B because they are domains/URLs. Treat them as stale config, not as a rename target.
4. **Identifiers that read like display strings:** `EMAIL_FROM_NAME` and `SENDER_IDENTITY` values look like plain config but end up in recipients' inboxes and in the CAN-SPAM footer, hence C. The tutorial slug `welcome-to-leadpilot` and the SEO slug `blog/apollo-clay-leadpilot-comparison` look like text but are DB keys / public URLs (B). The second needs a 301 redirect if renamed.
5. **Gate stamp dir `leadpilot-gate`** is shared by `scripts/gate/quick_gate.py` (writer), `.githooks/pre-push` and `.claude/hooks/require_gate.py` / `stop_check.py` (readers). A partial rename silently blocks every push.
6. **Sealed file:** `.github/workflows/eval-gate.yml:2` (an A-comment "LeadPilot release gate") is sealed per CLAUDE.md. Changing it needs its own reviewed PR.
7. **Shipped migrations:** 7 hits in 6 `alembic/versions/*` files. All are docstrings (A-comment content) and are frozen as B. Leave them untouched. `0065` names the Celery task `leadpilot.outreach.dispatch`.
8. The DB user/name `leadpilot` / `clienthunter_test` is duplicated across `.github/workflows/verify.yml`, `scripts/gate/full_gate.sh` and `scripts/verify_debug_router_guard.py`. CI-only and low risk, but they must change together.
9. Three brands coexist in one area: ClientHunter (oldest: env headers, nginx, compose prod, SDK/PyPI, Android), LeadPilot (identifiers: Render, MCP, plugin, DB, Celery), Vectorae (current display). The display layer is mostly Vectorae already. Most remaining LeadPilot/ClientHunter hits are B.

## 6. calendarharvest (domain use only, excluded from counts)

All 17 are domains, so none counts as a product-name use: `.claude/skills/leadpilot-outbound/references/tools.md:3,46,48` and the identical plugin copy (`api.calendarharvest.com/mcp`), `.dockerignore:53`, `.env.example:158,271`, `.env.production.example:202,316`, `.github/workflows/verify.yml:152`, `render.yaml:116,216`, `scripts/activate_with_keys.py:62`, `plugins/leadpilot/.claude-plugin/plugin.json:8`, `plugins/leadpilot/.mcp.json:5`. All B (sending domain / MCP URL).

# Part 8 — Brand inventory: binary and visual assets

_Source: subagent sweep, file `brand-assets.md`._

Repo: /home/user/LeadPilot (git-tracked files only). This was a read-only sweep. I wrote nothing to the repo.
Method:
- `git ls-files` filtered by extension.
- The full list of binaries is `git ls-files` minus `git grep -I -l ''`.
- Each binary was checked with `file`, `identify` and `strings`.
- Every image was viewed. For the videos I extracted frames with ffmpeg: 7 frames from the mp4 and 26 tiled frames (1 fps) from the webm, plus the email scene cropped at full resolution.
- `ffprobe` was used for the video metadata tags.
- I read the text files that produce or reference the assets.

## 1. Summary

**What was found.** 16 binary files are tracked in git.
- 9 of them are visual: 5 PNG, 1 ICO, 1 JPG, 1 MP4, 1 WebM.
- The other 7 are not visual: 3 `celerybeat-schedule.*` runtime files and empty `__init__.py` files.

**What was not found (0 of each):** tracked SVG, GIF, WebP, AVIF, ICNS, PDF or font files. There is also no tracked Android mipmap or drawable folder, no splash image, and no `opengraph-image`/`icon.tsx` generator. Fonts come from `next/font/google` (Inter) and are not stored in the repo.

**Inline SVGs.** Four files contain inline SVG: `crm/dashboard/primitives.tsx`, `ui/OfflineBanner.tsx`, `status-page/components/StatusIcon.tsx`, and `tests/test_workspaces.py` (an upload test). None has `<text>` or `<tspan>`, and none contains a brand name. They are plain path icons.

**Headline finding: the binaries were never re-rendered after the rebrand (PR #113, commit 6ada8b0, 2026-10-18).**
- Every binary that shows a brand name still shows **LeadPilot**.
- All binaries were last changed on 2026-10-11 (commits 7818591 and 25bda6c).
- Meanwhile their text sources, captions, alt text and docs were find-replaced to "Vectorae". As a result, the docs and code comments now describe pixels that are not there.

Counts by class (one row per occurrence in my area; text rows only where they produce, label or describe an asset):

| class | count | notes |
|---|---|---|
| A (display) | 16 | walkthrough.html ×5, .vtt captions ×2, Logo.tsx ×3 (2 comments + alt), manifest.json ×2, strings.xml ×2 (ClientHunter), content.ts:58 label, CLAUDE_CODE_HANDOFF.md:1943 |
| B (identifier) | 22 | celerybeat-schedule.dat ×5 (embedded task names), render.mjs ×5, content.ts ×5, page.tsx:30, vtt:4, strings.xml ×2 (`com.clienthunter.app`), 4 media file names (section 3) |
| C (human) | 9 | logo-full.png (wordmark), poster JPG (wordmark + copy, also the og:image), mp4, webm, plus 4 PNG/ICO icons and the icon generator script |
| DEFECT | 0 | The sample outreach email in the video has no product name. Its footer reads "Sample Agency LLC … Unsubscribe instantly". |

The C row counts all icons, including the five arrow-only icons that contain no name (see section 2).

Counts by variant:

| variant | where it appears |
|---|---|
| LeadPilot | In pixels: logo-full.png ("LEADPILOT"), poster JPG (×2), every frame of mp4 and webm. In identifiers: celerybeat .dat ×5, render.mjs ×5, content.ts ×5, page.tsx ×1, vtt ×1, 4 file names. |
| Vectorae | walkthrough.html ×5, vtt ×2, Logo.tsx ×3, manifest.json ×2, content.ts:58 ×1, CLAUDE_CODE_HANDOFF.md ×1 (wordmark claim) |
| ClientHunter | strings.xml ×4 (2 display, 2 identifier). Also the initials "CH" rendered by scripts/generate_placeholder_icons.py. |
| Victorae, Lead Pilot, client_hunter, lpk_ | 0 in assets |

About 25 files are involved.

## 2. Occurrence table

| path:line | variant | class | reason | risk |
|---|---|---|---|---|
| frontend/public/brand/logo-full.png | LeadPilot (pixels: "LEADPILOT" wordmark under a blue arrow on #100F14, 528×532) | C | Logo lockup; needs new artwork, do not redraw. Shown on the login hero through `LogoLockup` (Logo.tsx:56). No brand in its metadata (`strings` and `identify -verbose` show only dates). | **HIGH**: visible old name at login. Its `alt="Vectorae"` contradicts the pixels. |
| frontend/public/icons/icon-192.png | none (arrow mark only, no text) | C | PWA icon, also the inline `LogoMark` used across the app. No text, no metadata. | Low. Needs no name change unless the new brand changes the mark. |
| frontend/public/icons/icon-512.png | none (arrow only) | C | PWA icon. Also the Organization `logo` in JSON-LD (product-facts.json:9, schema_markup.md:38). | Low |
| frontend/public/icons/icon-maskable-512.png | none (arrow only) | C | PWA maskable icon | Low |
| frontend/src/app/apple-icon.png | none (arrow only, 180×180) | C | Apple touch icon | Low |
| frontend/src/app/favicon.ico | none (arrow only; 16/32/48 PNGs viewed) | C | Favicon | Low |
| frontend/public/media/leadpilot-walkthrough-poster.jpg | LeadPilot ×2 in pixels: top-left wordmark "LeadPilot"; caption "Prospects book on your LeadPilot booking page." | C | Poster frame (1280×720) rendered from video-src at t=25.4s. **It is also the home page og:image** (page.tsx:30). Fix: re-render with render.mjs, not redraw. | **HIGH**: old name in every social share preview. |
| frontend/public/media/leadpilot-walkthrough.mp4 | LeadPilot in pixels on every frame (wordmark), plus "from what LeadPilot stored about them" (sequences scene) and "your LeadPilot booking page" (meetings scene) | C | 26-second homepage video; metadata tag is only `encoder=Lavf60.16.100`. Fix: re-render from walkthrough.html, which already says Vectorae. | **HIGH**: the captions say Vectorae and the video says LeadPilot. |
| frontend/public/media/leadpilot-walkthrough.webm | LeadPilot in pixels (same as the mp4; all 26 sampled frames checked) | C | Same video in VP9; only the `ENCODER` tag | **HIGH** |
| celerybeat-schedule.dat (5 strings) | leadpilot | B | Pickled Celery beat state holding task names `leadpilot.outreach.dispatch`, `.poll_replies`, `.check_followup_due`. These match live task names (app/workers/outreach_tasks.py:1960,1999,2350; celery_app.py:271,275,304). It is a committed runtime artifact (already flagged in docs/NEXT_STEPS.md:162 and BASELINE.md:154). `.bak` and `.dir` contain no brand. | Medium. Do not rename the task names. The file should be deleted, not edited. |
| frontend/video-src/walkthrough.html:3 | Vectorae | A-comment | Source header comment | Low |
| frontend/video-src/walkthrough.html:18 | Vectorae | A | `<title>` of the render page; not visible in the video | Low |
| frontend/video-src/walkthrough.html:152 | Vectorae | A | `<div class="brand">`: the text wordmark burned into every video frame | Medium. Change this, then re-render all three media files. |
| frontend/video-src/walkthrough.html:213 | Vectorae | A | Scene subtitle that is burned into the video | Medium |
| frontend/video-src/walkthrough.html:255 | Vectorae | A | "your Vectorae booking page"; burned into the video and the poster | Medium |
| frontend/video-src/render.mjs:8 | leadpilot | B | Comment naming the output path | Low |
| frontend/video-src/render.mjs:9 | leadpilot | B | Same | Low |
| frontend/video-src/render.mjs:10 | leadpilot | B | Same | Low |
| frontend/video-src/render.mjs:12 | leadpilot | B | Same (the .vtt path) | Low |
| frontend/video-src/render.mjs:34 | leadpilot | B | `const NAME = "leadpilot-walkthrough"` sets the public asset URLs | Medium. Renaming it changes public URLs and the og:image path. |
| frontend/public/media/leadpilot-walkthrough.en.vtt:4 | leadpilot | B | NOTE block naming the file names | Low |
| frontend/public/media/leadpilot-walkthrough.en.vtt:14 | Vectorae | A | Caption cue 2 (test: homeVideo.test.ts matches it against content.ts) | Medium. Must stay in sync with content.ts. |
| frontend/public/media/leadpilot-walkthrough.en.vtt:34 | Vectorae | A | Caption cue ("your Vectorae booking page") | Medium |
| frontend/src/components/home/content.ts:54 | leadpilot | B | Video URL `/media/leadpilot-walkthrough.mp4` | Medium (public URL) |
| frontend/src/components/home/content.ts:55 | leadpilot | B | `.webm` URL | Medium |
| frontend/src/components/home/content.ts:56 | leadpilot | B | Poster URL | Medium |
| frontend/src/components/home/content.ts:57 | leadpilot | B | Captions URL | Medium |
| frontend/src/components/home/content.ts:58 | Vectorae | A | Video `label` "Vectorae product walkthrough" (screen readers) | Low |
| frontend/src/components/home/content.ts:60 | leadpilot | B | Comment naming the .vtt path | Low |
| frontend/src/app/page.tsx:30 | leadpilot | B | og:image path `/media/leadpilot-walkthrough-poster.jpg` | Medium |
| frontend/src/components/ui/Logo.tsx:4 | Vectorae ("VECTORAE" wordmark) | A-comment | **Factually wrong**: the artwork's wordmark reads LEADPILOT | Medium (misleading) |
| frontend/src/components/ui/Logo.tsx:38 | Vectorae | A-comment | Comment on the decorative alt | Low |
| frontend/src/components/ui/Logo.tsx:61 | Vectorae | A | `alt="Vectorae"` on an image that shows "LEADPILOT" | **HIGH**: screen readers and visible pixels disagree. |
| frontend/public/manifest.json:2 | Vectorae | A | PWA `name` (install dialog and home-screen label) | Medium |
| frontend/public/manifest.json:3 | Vectorae | A | PWA `short_name` | Medium |
| frontend/android/app/src/main/res/values/strings.xml:3 | ClientHunter | A | Android `app_name`, the launcher label (AndroidManifest.xml:53) | **HIGH**: two brands out of date in the shipped app label. |
| frontend/android/app/src/main/res/values/strings.xml:4 | ClientHunter | A | `title_activity_main` (AndroidManifest.xml:78) | High |
| frontend/android/app/src/main/res/values/strings.xml:5 | clienthunter | B | `package_name` com.clienthunter.app (Play Store app ID) | Do not change |
| frontend/android/app/src/main/res/values/strings.xml:6 | clienthunter | B | `custom_url_scheme` (deep links) | Do not change |
| scripts/generate_placeholder_icons.py:23 | ClientHunter (initials `INITIALS = "CH"`) | C | Re-running it **overwrites** the three real PWA icons with a "CH" initials square. Its docstring (lines 3-8) wrongly says the repo has no brand mark. | Medium: a hazard rather than a display string. |
| CLAUDE_CODE_HANDOFF.md:1943 | Vectorae ("VECTORAE" wordmark) | A | The doc says the lockup's wordmark reads VECTORAE; the pixels say LEADPILOT. This is a find-replace artifact of the rebrand. | Medium (misleading) |
| frontend/src/content/product-facts.json:9 / docs/program/ai-visibility/geo/technical/schema_markup.md:38 | none (URL `calendarharvest.com/icons/icon-512.png`) | B | JSON-LD logo URL; the image itself has no text | Low |

## 3. File and folder names containing a variant (assets)

All four are B (public URLs referenced by content.ts:54-57, page.tsx:30 and render.mjs:34):

| path | variant | class | note |
|---|---|---|---|
| frontend/public/media/leadpilot-walkthrough.mp4 | leadpilot | B | Renaming it changes a public URL; fine for a static site if the references move with it, but cached share cards point at the poster URL. |
| frontend/public/media/leadpilot-walkthrough.webm | leadpilot | B | Same |
| frontend/public/media/leadpilot-walkthrough-poster.jpg | leadpilot | B | og:image URL; already-scraped social cards keep the old URL |
| frontend/public/media/leadpilot-walkthrough.en.vtt | leadpilot | B | Path also listed in frontend/src/tests/homeClaims.test.ts:32 |

No other tracked asset has a brand name in its file name. `brand/`, `icons/`, `favicon.ico` and `apple-icon.png` are generic.

## 4. Generated or git-ignored assets

- **Walkthrough media** (mp4, webm, poster jpg) are generated but committed.
  - Command: `node frontend/video-src/render.mjs`, which uses Playwright and ffmpeg (`FFMPEG` env var). It records `walkthrough.html` at 1280×720, 30 fps, and takes the poster at t=25.4s.
  - Because the source already says Vectorae (or whatever new name replaces it at walkthrough.html:152/213/255), re-running it is the fix. The .vtt is hand-maintained; render.mjs:12 says it is written separately, and it must match content.ts VIDEO.transcript.
- **PWA icons:** `python -m scripts.generate_placeholder_icons` regenerates the icons, but only as "CH" placeholders. Do not run it. The real icons came from the source artwork (`image.png`, not in the repo) as described in CLAUDE_CODE_HANDOFF.md:1938-1958.
- **Android launcher icons, splash and adaptive icons:** none are tracked, and `frontend/android/.gitignore` does not ignore them. They are absent from the repo.
  - AndroidManifest.xml:52 references `@mipmap/ic_launcher`. The release workflow (`.github/workflows/android-release.yml:78`) only runs `npx cap sync android`, which does not create mipmaps.
  - They must exist only on a developer machine, or the release build is relying on something not in git. They need a human check (class C) once the brand changes.
- `frontend/android/app/src/main/assets/public` is git-ignored and regenerated by `cap sync` from the web build. It will contain copies of the PNGs, video and so on.
- `celerybeat-schedule.{dat,bak,dir}` are runtime state that Celery rewrites. They should be untracked and are listed in `.dockerignore:90`. Do not edit them.

## 5. Surprises

1. **The rebrand left the binaries behind.** Text was changed to Vectorae, but the logo PNG, poster, mp4 and webm still show LeadPilot. Visitors see "LeadPilot" in the homepage video, in the og:image share card, and in the login-hero logo.
2. **Docs and alt text describe artwork that does not exist.**
   - Logo.tsx:4 and CLAUDE_CODE_HANDOFF.md:1943 say the wordmark reads "VECTORAE". `alt="Vectorae"` (Logo.tsx:61) sits on an image whose pixels read "LEADPILOT". This is an accessibility mismatch that came from find-replace.
   - The brand artwork has no vector source in the repo. The source `image.png` lives outside git, so a new wordmark requires new artwork from a human.
3. **Captions and video disagree.** The .vtt and the transcript in content.ts say "Vectorae researches…" and "your Vectorae booking page", while the video frames say LeadPilot. The test homeVideo.test.ts checks captions against the transcript only, so it cannot catch this.
4. **The Android app label is two brands behind.** `app_name` is "ClientHunter", while the PWA manifest says "Vectorae". The package id `com.clienthunter.app` is B and must not change.
5. **The icon generator is a trap.** `scripts/generate_placeholder_icons.py` would replace the real arrow icons with "CH" (ClientHunter) initials. Its docstring wrongly claims there is no brand mark.
6. **Committed Celery state contains identifiers.** `celerybeat-schedule.dat` holds `leadpilot.outreach.*` task names. These are live B identifiers (in-flight queued tasks depend on them). The file is a stale runtime artifact.
7. **No customer-voice defect in the assets.** The sample outreach email in the video contains no product name; its footer names the sender's own company ("Sample Agency LLC").
8. **The icons themselves need no rename.** All five icon PNG/ICO files are the arrow mark with no text, so they are unaffected by a name change unless the mark itself changes.
