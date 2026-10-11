# Compliance Documentation — ClientHunter Enterprise

## Enforcement Architecture

Compliance is enforced in two places. The **send chokepoint** (`app/workers/outreach_tasks.py` `send_message_impl`) re-checks suppression, consent, send windows and caps for every channel, and builds every email through `sequence_engine.build_compliant_email` (headers + visible unsubscribe footer). The **WhatsApp adapter** additionally refuses a non-compliant message itself (`app/integrations/whatsapp.py` raises `ComplianceError`); the Gmail adapter only transports what the send path built. The API layer catches `ComplianceError` and returns a 422 with a `compliance_code` field. *(Corrected 2026-10-11: this said every adapter enforces compliance; the Gmail adapter does not.)*

---

## Email (CAN-SPAM / GDPR)

*Corrected 2026-10-11 against the code (platform-gaps item 8,
help-center-discoveries D6). The earlier rows named a `{unsubscribe_link}`
template token, a `GMAIL_DAILY_SEND_CAP` of 500, an HMAC token, an adapter-level
`ComplianceError` and a 20/day warm-up start; none of those is what the code
does. Line numbers are as of that date.*

| Rule | Implementation |
|---|---|
| Unsubscribe headers on every email | `sequence_engine.build_compliant_email` (`app/services/sequence_engine.py:515-531`) adds `List-Unsubscribe` and `List-Unsubscribe-Post: List-Unsubscribe=One-Click` (RFC 8058). The send path always builds the email through it (`app/workers/outreach_tasks.py` `_render_email_outbound`). `GmailChannel.send()` only transports the pre-built headers (`app/integrations/gmail.py:284-287`); it does not itself raise `MISSING_UNSUBSCRIBE` — that refusal exists only on the debug send endpoint (`app/api/debug.py:269-276`). |
| Unsubscribe link in body | Not a template token. `build_compliant_email` appends a visible footer, `compliance_footer()` (`sequence_engine.py:507-512`): the configured `SENDER_IDENTITY` plus "Don't want these emails? Unsubscribe instantly: <url>". GDPR/UK and CASL recipients also get a region notice before it (`compliance_audit.region_notice`). |
| Unsubscribe token | `make_unsubscribe_token` (`sequence_engine.py:496-497`) encrypts `{"lead_id", "purpose": "unsubscribe"}` with the app's Fernet key (`app/core/crypto.py`), so non-users can unsubscribe without signing in. Route: `GET`/`POST /unsubscribe/{token}` (`app/api/unsubscribe.py:54,59`), path parameter, not `?token=`. |
| Suppression checked at send time | `send_message_impl` re-checks `is_suppressed` immediately before sending (`app/workers/outreach_tasks.py:205`), for every channel. |
| Bounce rate auto-pause | Above `BOUNCE_RATE_PAUSE_THRESHOLD` (`bounce_rate_pause_threshold`, default 0.03, `app/config.py:113`), after `bounce_min_sends`, the campaign state becomes `paused_bounce_rate` (`sequence_engine.py:618`). A workspace compliance rule may lower the threshold, never raise it. (`GMAIL_BOUNCE_PAUSE_THRESHOLD` in `app/core/config.py` is read by nothing.) |
| Daily send cap | `GMAIL_DAILY_CAP` (`gmail_daily_cap`, **default 100**, `app/config.py:106`), read by `daily_allowance` (`sequence_engine.py:166`), `compliance_rules` and `mailbox_health`; a compliance rule or a throttled mailbox can only lower it. Sends above the allowance are deferred to the next day's window, not dropped. (`GMAIL_DAILY_SEND_CAP`, default 500, in `app/core/config.py:392` is read by nothing.) |
| Warm-up | `gmail_warmup_start_sends` (10) plus `gmail_warmup_daily_increment` (10) per day since the account was connected, capped at the daily cap (`sequence_engine.py:165-167`, `app/config.py:107-108`). With the Deliverability Autopilot on, a stepped ramp can lower it further. (`GMAIL_WARMUP_START_DAILY` is read by nothing.) |
| Reply classification | "stop emailing me", "unsubscribe", "remove me" → classified `unsubscribe_request` → suppression + sequence stop |

---

## WhatsApp (Meta Policy)

| Rule | Implementation |
|---|---|
| Template-only for cold contact | `WhatsAppChannel.send()` raises `ComplianceError(WHATSAPP_NO_FREE_FORM_COLD)` for cold contacts |
| Template must be approved | Before sending, template status is checked via Meta API; `REJECTED` → `ComplianceError(WHATSAPP_TEMPLATE_NOT_APPROVED)` |
| Opt-in required | `WhatsAppChannel.send()` checks `whatsapp_optins` table; no opt-in → `ComplianceError(WHATSAPP_NO_OPTIN)` |
| 24-hour window for free-form | Customer-service window tracked per phone number; free-form outside window → `ComplianceError(WHATSAPP_WINDOW_CLOSED)` |
| STOP handling | `STOP` inbound message triggers atomic transaction: suppression + opt-out audit + sequence stop. All three or none (rollback on failure) |

---

## GDPR

| Right | Implementation |
|---|---|
| Right to erasure | `DELETE /leads/{id}` wipes: email, phone, first_name, last_name, company, raw_data; sets `deleted_at` |
| Tombstone | Lead row is kept with `deleted_at` set, PII fields nulled. Prevents re-sourcing |
| Tombstone suppresses re-import | `lead_service.source_leads()` checks `lead_tombstones` before inserting from Apollo |
| Right of access | `GET /leads/{id}` returns all stored data (for authenticated owner only) |
| Data portability | `GET /strategies/{id}/leads?format=csv` (TODO: verify this endpoint was added in M2) |

---

## Verification Gating

Before lead sourcing can begin on a strategy, **all 10 verification passes must be PASS**. If any pass has `result=FAIL`, `POST /strategies/{id}/leads/source` returns 422. This prevents unresearched or non-compliant strategies from going live.

---

## Suppression List

The suppression list is checked:
1. At lead sourcing time (pre-import filter)
2. At email send time (last-moment guard)
3. At WhatsApp send time

An email or phone number added to the suppression list is never contacted again. Admin can add entries globally; users can add entries for their own campaigns.

---

## Audit Trail

Every compliance-relevant action is an event in the `outcomes` table:
- `unsubscribed` — from email link or reply
- `opted_out` — WhatsApp STOP
- `bounced` — email bounce
- `suppressed` — blocked at send time
- `gdpr_deleted` — right-to-erasure exercise

The `whatsapp_opt_out_audit` table (separate from outcomes) stores the full STOP message payload for regulatory purposes.
