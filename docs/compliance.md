# Compliance Documentation — ClientHunter Enterprise

## Enforcement Architecture

Compliance rules are enforced at the **adapter layer** — it is not possible to send a non-compliant message by calling the adapter. The API layer catches `ComplianceError` and returns a 422 with a `compliance_code` field.

---

## Email (CAN-SPAM / GDPR)

| Rule | Implementation |
|---|---|
| Unsubscribe header required | `GmailChannel.send()` raises `ComplianceError(MISSING_UNSUBSCRIBE)` if `List-Unsubscribe` header is absent |
| Unsubscribe link in body | Template renderer checks for `{unsubscribe_link}` token in every email body |
| Signed unsubscribe token | `GET /unsubscribe?token=...` uses HMAC-SHA256 signed token so non-users can unsubscribe without auth |
| Suppression checked at send time | `outreach_tasks.send_sequence_step` queries suppression list immediately before calling Gmail API |
| Bounce rate auto-pause | Bounce rate tracked per campaign; if `bounce_rate > GMAIL_BOUNCE_PAUSE_THRESHOLD` (default 3%), campaign status set to `paused_bounce_rate` |
| Daily send cap | `GMAIL_DAILY_SEND_CAP` (default 500). Sends above cap are deferred, not dropped |
| Warm-up | New accounts start at `GMAIL_WARMUP_START_DAILY` (default 20/day), ramping up over 30 days |
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
