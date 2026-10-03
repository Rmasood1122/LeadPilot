# Verification artifacts

Scripts and notes supporting `docs/VERIFICATION_REPORT.md` (audit of
`integrate/eval-gate-into-feature-8` @ `934a145`, 2026-10-01).

These are **verification artifacts, not tests.** They deliberately live outside
`tests/` and must never be added to the offline suite or the sealed set: they are
one-off reproductions that need a local throwaway PostgreSQL, and the gate is
offline by design.

| File | Purpose |
|---|---|
| `repro_stop_duplicate_suppression_sqlite.py` | NEW-01: calls `revoke_opt_in` directly for a phone-only lead and for a lead with **both** email and phone. Shows the row counts and that a default (`autoflush=True`) sessionmaker does **not** reproduce the failure — which is why the 45 green STOP/consent tests miss it. |
| `repro_stop_webhook_sequence_pg.py` | NEW-01: replays the webhook's two-call STOP sequence (`revoke_opt_in` then `unsubscribe_lead`) against local PostgreSQL. Also does not reproduce in isolation — the live failure needs the app's own `autoflush=False` session, which is the point of the finding. |

Both scripts are run with the repo root on `PYTHONPATH`, e.g.

```bash
PYTHONPATH=. python3 docs/verification/repro_stop_duplicate_suppression_sqlite.py
```

The authoritative reproduction of NEW-01 is the **live HTTP** one recorded in
`docs/VERIFICATION_REPORT.md` §4: a signed `POST /webhooks/whatsapp` carrying `STOP`
returns HTTP 500 and writes zero `suppression_list` rows. The traceback quoted there
is the primary evidence; these scripts document the narrowing process and the
negative results that isolated `autoflush=False` as the discriminator.

No real credentials, no vendor calls, no production systems were used.
