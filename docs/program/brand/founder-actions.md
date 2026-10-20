# Founder actions for the Victorae rename (Class C)

Phase 1, step 5 of `docs/program/STAR_VICTORAE.md`. Code and docs now say Victorae everywhere
except the items below. Each one stays on the old name until its owner acts. Every item has a
matching `C:` entry in `.brand-allowlist`; remove that entry in the same change that renames the
item, or `brand_lint` will flag the entry as stale.

**Before any public switch:** "Victorae" is not trademarked yet (VIC-TM, 2026-10-20). The
recommendation on record is to clear the name in software classes (Nice 9 and 42) before
changing the public listings in section 2.

Who acts: **R** = Rehan Masood, **A** = Ahmad Shahid, **C** = counsel, **E** = an engineer (a
Claude session).

## 1. Legal and consent text (counsel first)

| # | Where | What it says now | Action | Who |
|---|---|---|---|---|
| L1 | `frontend/src/app/terms/page.tsx` (whole page, title included) | "Calendarharvest, which operates Vectorae Enterprise" | Counsel rewrites with the new product name and the open entity questions in the page's header comment; then E updates the page and removes the allowlist entry | C, then E |
| L2 | `frontend/src/app/privacy/page.tsx` and `docs/PRIVACY_POLICY.md` | "Vectorae Enterprise is operated by Calendarharvest"; the policy source also says "ClientHunter Enterprise, also sold as Vectorae" | Same as L1 | C, then E |
| L3 | `app/services/voice_twin.py` consent text (`CONSENT_VERSION`) | "owner of this Vectorae account… consent for Vectorae…" | Counsel approves the new wording. E updates it and **bumps `CONSENT_VERSION`**: every owner re-consents before the next clone | C, then E |
| L4 | `app/services/daily_send_approval.py` LinkedIn risk disclosure (`LINKEDIN_WARNING_VERSION`) | "Vectorae's automatic LinkedIn sending" | New wording, then E bumps `LINKEDIN_WARNING_VERSION` | C, then E |
| L5 | `app/services/consent.py:135`, `app/services/system_settings.py:92`, `app/services/local_business.py:494,505,510` | DNC/TCPA/PDPA and HIPAA statements naming Vectorae | Approve "Victorae" in these statements | C |
| L6 | `frontend/src/app/oauth/consent/page.tsx` | "{app} wants to connect to Vectorae" | Approve the consent-screen wording | R or A |
| L7 | `frontend/src/components/settings/VoiceTwinCard.tsx` | "not kept by Vectorae" (3 lines) | Approve together with L3 | C |
| L8 | `docs/connectors/README.md` data-handling disclosures | "What leaves Vectorae…" | Approve the new wording | R or A |
| L9 | Legal entity "LeadPilot Enterprises" (wherever it is cited) | Company name | Renaming the product does not rename the company. Decide whether it stays | R and A |

## 2. Third-party dashboards and listings

| # | Where | Action (dashboard steps) | Who |
|---|---|---|---|
| T1 | **Resend sender name**: `EMAIL_FROM_NAME=Vectorae` on Render (`render.yaml` ×2, `.env*.example`, default in `app/config.py:246`) | dashboard.render.com → `leadpilot-api` and `leadpilot-worker` → Environment → set `EMAIL_FROM_NAME` to `Victorae` → Save (each redeploys). Then E updates `render.yaml`, the templates and the default | A |
| T2 | **CAN-SPAM sender identity**: placeholder "Vectorae User, 123 Main St…" (`app/config.py:106`, `.env.production.example:114-116`) | Set `SENDER_IDENTITY` on Render to the real legal name and postal address. Production already refuses the placeholder | R or A |
| T3 | **Google OAuth consent screen** (Gmail connect) shows "ClientHunter" (`SECURITY.md:92`) | console.cloud.google.com → the project → APIs & Services → OAuth consent screen → Edit app → App name "Victorae", logo, support email → Save. A name change may trigger Google re-verification | A |
| T4 | **Google Play listing**: app name "ClientHunter Enterprise" (`docs/STORE_ASSETS.md`, `docs/PLAY_STORE_CHECKLIST.md`) | play.google.com/console → the app → Grow → Store presence → Main store listing → App name and descriptions → Save, then submit for review. Do **not** change the app id `com.clienthunter.app` (installed users would never get updates). The installed launcher label already changes to "Victorae" with the next build (`strings.xml`) | R or A |
| T5 | **Firebase** app nickname "ClientHunter" (`docs/FIREBASE_SETUP_CHECKLIST.md:26`) | console.firebase.google.com → Project settings → Your apps → nickname → "Victorae". Cosmetic; the package stays | A |
| T6 | **ElevenLabs** voice names "Vectorae - <owner>" (`app/services/voice_twin.py:836-839`, `:884`) | Existing voices keep their name. To rename new voices, change L3 first, then E updates the name and the owner instruction at `:884` together | C, then E |
| T7 | **Recall.ai meeting bot** "Vectorae Notetaker" (`app/integrations/recall.py:154`), visible to prospects | Decide the bot name; it is part of the recording disclosure. E then updates the default and `tests/test_meeting_recording.py` | R and A |
| T8 | **Stripe** product names "Vectorae <plan>" (`app/integrations/stripe_billing.py:141`), the renewal notice (`app/services/billing.py:964`) and the billing catalogue tagline "…through Vectorae" (`app/core/billing_catalog.py`, shown on pricing) | Out of scope for this program (do not touch billing or Stripe). Decide when billing work resumes; existing Stripe products keep their names | R and A |
| T9 | **Social and directory listings** under old handles: LinkedIn `company/leadpilot-app`, G2 `products/leadpilot-2026-10-14`, Crunchbase `organization/leadpilot`, YouTube `@LeadPilotEnterprise` (in `frontend/src/content/product-facts.json` `same_as`, i.e. the site's JSON-LD) | Rename each profile in its own admin page. Where the handle changes, E updates `same_as` with the new URLs | R and A |
| T10 | **Claude Code plugin publisher name** "Vectorae" (`.claude-plugin/marketplace.json` owner, `plugins/leadpilot/.claude-plugin/plugin.json` author) | Decide the publisher name. The plugin id `leadpilot` stays (installs depend on it) | R or A |
| T11 | **PyPI author** "ClientHunter", `hello@clienthunter.ai` (`sdk/pyproject.toml:12`) | The SDK is unpublished. Decide the author name and a real mailbox before the first release | R or A |
| T12 | **UptimeRobot** monitor names "Vectorae - …" (`status-page/lib/config.ts`, B: matched by exact string) | uptimerobot.com → each monitor → Edit → Friendly name "Victorae - …". **Then** E changes `MONITOR_NAMES` the same day, or the status page loses its uptime history | A, then E |
| T13 | **Claude Project** "LeadPilot Production Readiness" (`CLAUDE.md:5`) | claude.ai → Projects → rename. Then E updates `CLAUDE.md` | R or A |

## 3. Logos and media (do not hand-edit asset files)

| # | Where | Action | Who |
|---|---|---|---|
| M1 | `frontend/public/brand/logo-full.png`: the login/app logo shows a **"LEADPILOT"** wordmark (checked visually 2026-10-20). Its alt text still says "Vectorae" (`frontend/src/components/ui/Logo.tsx`) | Supply new artwork with the Victorae wordmark. E then swaps the file and the alt text | R or A |
| M2 | Homepage walkthrough video `frontend/public/media/leadpilot-walkthrough.{mp4,webm}` and poster `-poster.jpg` (also the homepage share image): every frame shows **"LeadPilot"** | Its source `frontend/video-src/walkthrough.html` now says Victorae. Re-render with `node frontend/video-src/render.mjs` (see its header) and commit the new files under the same names (URLs are B). The captions `.vtt` already say Victorae | E, after a founder OK on the frames |
| M3 | Favicon and app icons (`frontend/public/icons/*`, `favicon.ico`) | They show the arrow mark only, with no wordmark. No action unless the mark changes | — |
| M4 | Android launcher icon `@mipmap/ic_launcher` | Not in git (the release workflow does not create it). Confirm where it lives and whether it carries a wordmark | R or A |

## 4. Waiting on a sealed-file (gate/) PR

These old names are pinned by sealed compliance tests, so they change only in a reviewed PR on
a `gate/` branch (CLAUDE.md, GATES.md):

| # | App string | Sealed test |
|---|---|---|
| S1 | Meetings-ledger PDF title "LeadPilot meetings-per-dollar ledger" (`app/services/meetings_ledger.py:672`) | `tests/test_pilot_mode.py:806` |
| S2 | Pilot scorecard email "…your LeadPilot account" (`app/services/pilot_mode.py:597-598`) | `tests/test_pilot_mode.py:1020` |
| S3 | Pilot-verdict download names `leadpilot-pilot-verdict-*` (API and `frontend/src/lib/pilot.ts`) | `tests/test_pilot_mode.py:771,790` |
| S4 | Fixture text in 14 sealed test files (synthetic `@leadpilot.dev` addresses, "Sam from LeadPilot" sample copy) | the files themselves; renaming is optional |

## 5. Deliberately unchanged identifiers (Class B, approved in VIC-KEEP)

The full list with reasons is `.brand-allowlist` and `rename-inventory.md` §2. A later rename of
any of them needs a migration plan (alias both names, dual-read, deprecate), not a
find-and-replace. Examples: `com.clienthunter.app`, `clienthunter://`, `X-LeadPilot-*` headers,
`leadpilot:read/write` scopes, `leadpilot.*` Celery tasks, the `lpk_` key prefix,
`/what-is-leadpilot/` and `/compare/leadpilot-vs-*` URLs, `leadpilot-api`/`-worker` on Render, and
the `clienthunter` SDK package.
