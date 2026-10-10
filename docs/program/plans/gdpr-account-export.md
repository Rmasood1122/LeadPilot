# GDPR account export (Art. 15 / 20) — part 1 of the account-rights finding

Branch `claude/gdpr-account-export`. Finding: `BASELINE.md` §3 "GDPR export /
deletion for user accounts" (HIGH, not downgraded by P0-D). This PR closes the
**export** half. Erasure is part 2 and needs founder decisions first (below).

## Behaviour (defined)

- `POST /me/data-export {"password"}` → 200 `application/json` attachment,
  `Cache-Control: no-store`: `format`, `format_version` 1, `generated_at`,
  `account_id`, `redacted` (column list), `not_exported` (table → reason),
  `row_counts`, `tables` (table → rows; every owned table present, empty or not).
- Rows reached only through **ownership** paths (`app/services/account_export.py`
  `OWNERSHIP`): FK chains ending at `users.id`, e.g. leads via
  strategy → product → user. Actor columns (author, approver) are never followed.
  Every query is filtered by the caller's own id.
- Credentials are redacted: password hash, Gmail token ciphertext, webhook
  secrets, integration token values, API-key / share-link / verification hashes,
  unsubscribe tokens, device push tokens, encrypted tool settings.
- Access: the signed-in person re-types their password (403 `INVALID_PASSWORD`
  + `account.data_export_denied` audit row); personal API keys are refused
  (403); rate limit = the `password_confirm` bucket (same as strategy delete);
  success writes `account.data_exported` with the row count. `/me` is a personal
  route, so a workspace member always exports their own account, never the
  owner's.
- Web app: Profile → "Download your data" (password field + button).

## Completeness guard

`tests/test_account_export.py` fails when any table in the schema is on neither
`OWNERSHIP` nor `EXCLUDED`, when a path hop is not a real foreign key, or when a
path does not end at `users.id`. Today: the `users` row, 85 ownership paths and 12 exclusions (98 tables).

## Limits (reported, not fixed here)

- Built in memory and returned in one response. Fine for a single-tenant
  deployment's accounts; a very large account (hundreds of thousands of
  messages) would need an async job + download link.
- Not exported: unmatched `inbound_replies` (no lead, `account_ref` only) and
  lead-less `outcomes` (system events). Both have no FK path to the account.
- The Capacitor Android app saves the file through the WebView's download
  handling; not tested on a device.
- Not sealed: an access-right feature, not a sending-compliance guard. Founders
  may ask for the test to be sealed in its own PR.

## Part 2 — account erasure: decisions needed before it is built

Mapping the schema for this PR (every table, every FK, migrations checked)
found that deleting a `users` row today would do the wrong thing in four ways:

1. **Billing records are deleted with the user.** `billing_subscriptions` and
   `billable_meetings` are `ON DELETE CASCADE` from `users`. Invoices and
   Stripe ids usually must be kept for accounting/tax. → **Decision E1:** keep
   billing rows (anonymised: owner id kept, no PII) for N years, or delete?
2. **Rows that outlive the account still hold personal data.**
   `attribution_entries` and `claim_verification_log` (message bodies),
   `consent_events` (prospect email/phone), `account_security_events` (the
   user's own email and IP), unmatched `inbound_replies` (reply bodies). Their
   user FKs are `SET NULL`. → **Decision E2:** consent events and the
   suppression list are the proof that opt-outs are honoured (CAN-SPAM/CASL);
   keep those, delete or redact the rest?
3. **`activity_audit_events` cannot be deleted** (Postgres trigger, migration
   0042). It holds opaque ids, no email. → keep (no decision needed unless the
   founders disagree).
4. **Webhook tables have no FK in PostgreSQL** (`webhook_targets.user_id`,
   `webhook_deliveries.target_id`; migration 0011 never created them; the ORM
   claims CASCADE). Erasure must delete them explicitly. Separately, this is a
   schema defect: orphans already accumulate when a target's owner is removed
   by hand. Reported as **PD-2**, not fixed here.

Also needed for erasure: revoke sessions (`auth_sessions.revoke_all_for_user`),
disconnect Gmail / LinkedIn (Unipile) / CRM, cancel the Stripe subscription,
and decide what happens to the account's **workspace members** (deleting the
owner's workspace removes everyone's membership).
