# Gate change: seal the email-network legal/safety guard tests, refresh the baseline

Date: 2026-10-12. Branch `claude/gate-seal-email-network`, stacked on `claude/email-network` (PR #96), because it seals the guard file that PR adds. Merge it **after #96**.

## Why this is its own PR

CLAUDE.md requires a seal or baseline change to be its own reviewed PR, with a written justification. The `protect_sealed` hook only allows sealed-file edits on `gate/` or `claude/gate-` branches. This follows the same pattern as #86, #92 and #95.

## 1. `evals/compliance_testset.yaml`: 1 file added (30 → 31)

| File | Tests | Guard |
|---|---|---|
| tests/test_email_network_guards.py | 92 | See the list below. |

What the guard covers:
- **Headers only.** Subjects, bodies, Message-IDs and snippets are never stored. A From_-line in a body is never parsed as headers. Upload bodies are never written to a temp file.
- **B2B-only filtering.** It excludes consumer domains (including regional variants), role inboxes, automated and list senders, and the user's own domain and its subdomains.
- **Exclusions respected.** Suppressed, F05-excluded and erased people are respected at import, at draft, at attach, at add-to-campaign and at send.
- **Tenancy.** Contacts, scans and the saved-opener owner check are tenant-scoped. A Gmail scan can only be started by the owner.
- **Sending.**
  - A saved opener is sent only by `send_message_impl`, through `build_compliant_email` (unsubscribe link, postal address, region notice).
  - Unknown-region leads get the strictest regime: notice on, no tracking.
  - CASL's 2-year window is re-checked at send.
  - Over-claimed relationship wording is refused.
  - An unsaved draft can never be sent, even under a race.
- **Rights.** Export, account erasure, lead erasure, unsubscribe purge and single-contact delete are all covered.
- **Caps.** Per-import and per-account caps hold.

The legal basis needs founder/legal confirmation; see `docs/features/email-network.md` §10:
- CAN-SPAM 15 U.S.C. §7704 (opt-out and postal address).
- GDPR Art. 6(1)(f), Art. 14 and Art. 21, plus Art. 5(1)(c) data minimisation.
- UK PECR reg. 22 (corporate subscribers).
- CASL s.10(10) (existing business relationship, 2 years).

All 24 of the reviewer's mutations are killed (spec §17).

Not sealed: `tests/test_email_network.py` (parsers and features) and `tests/test_email_network_migration.py`.

## 2. `evals/baseline.json` and block fixtures: refreshed

The sealed set changed, so `dataset_hash` changed. The baseline is rebuilt from 2 runs, and the fixtures are regenerated from the honest junit. Thresholds and the registry are unchanged.

## Evidence

| Command | Exit | Result |
|---|---|---|
| `python3 evals/tools/registry_lint.py evals/registry.yaml` | 0 | OK (registry unchanged) |
| `python3 evals/tools/baseline.py --cmd 'python3 evals/run_evals.py' --runs 2` | 0 | both runs: 5,981 tests, pass 1.000, compliance 1.000 (31 sealed files); 1,036.6 s and 1,003.9 s; runtime mean 1,020.2 s, band_2sigma 46.3 s |
| `--sabotage compliance` → `block_compliance_suite_pass_rate.json` | 0 | 0.9677 (30 of 31; `tests/test_compliance.py` removed for real) |
| `--sabotage count` → `block_offline_test_count.json` | 0 | 1,402 (< floor 3,150) |
| `--sabotage suite` → `block_full_suite_pass_rate.json` | 0 | 0.99983 (one injected failing test) |
| `python3 evals/tools/promote.py` | 0 | PROMOTE with 1 soft warning (runtime 1,004 s vs the 900 s registry ceiling; see #95 for the founder decision) |
| `python3 evals/fixtures/verify_block_fixtures.py` | 0 | all 3 hard gates proven to fire; healthy run PROMOTEs |
