# Gate change: seal the voice-twin legal/safety guard tests, refresh the baseline

Date: 2026-10-12. Branch `claude/gate-seal-voice-twin`, stacked on
`claude/voice-twin` (PR #94), because it seals the test file that PR adds. Merge it
**after #94**.

## Why this is its own PR

CLAUDE.md: a seal or baseline change is its own reviewed PR with a written
justification. The `protect_sealed` hook allows sealed-file edits only on
`gate/` or `claude/gate-` branches, so the feature branch could not seal its
own guard file. Same pattern as #86 and #92.

## 1. `evals/compliance_testset.yaml`: 1 file added (29 → 30)

| File | Tests | Guard |
|---|---|---|
| tests/test_voice_twin_guards.py | 128 | The guard covers eight areas: <br>• **Disclosure:** every AI call and voicemail opens with the AI disclosure and recording notice, enforced in code on every path (Call now, sequence send, ElevenLabs fallback, inbound, last-moment `PhoneChannel`). <br>• **No impersonation:** sentences that impersonate the owner or claim to be human are stripped. <br>• **Refused on save:** concealment instructions get a 422. <br>• **Post-call check:** a claim found in the transcript pauses all AI calls for the account. <br>• **Consent:** the clone needs the owner's written consent before any upload. <br>• **No audio stored:** audio is never written to our disk or database. <br>• **Deletion:** revoke and account erasure delete the voice at ElevenLabs, with a retrying deletion queue. <br>• **Tenancy and gates:** tenancy holds, the outbound gates are kept, and the inbound webhook is signed and scoped to the account's own number. |

Legal basis (needs founder/legal confirmation, see `docs/features/voice-twin.md` §7):
- Maine 10 MRSA §1500-Y;
- EU AI Act Art. 50;
- Utah AI Policy Act (SB 226);
- Cal. Pub. Util. Code §2874;
- TCPA artificial voice (FCC Declaratory Ruling, Feb. 2024);
- two-party recording consent;
- BIPA 740 ILCS 14 and GDPR Art. 9 (voiceprint).

The reviewer's 16 mutations, each removing one guard, are all killed by tests (spec §13).

Not sealed: `tests/test_voice_twin.py` (feature behaviour) and
`tests/test_voice_twin_migration.py`.

## 2. `evals/baseline.json` and block fixtures: refreshed

The sealed set changed, so `dataset_hash` changed and the baseline must be rebuilt. It is
rebuilt from 2 runs with `baseline.py --runs 2`, and the fixtures are regenerated from the
honest junit. Thresholds and the registry are unchanged.

## Evidence

| Command | Exit | Result |
|---|---|---|
| `python3 evals/tools/registry_lint.py evals/registry.yaml` | 0 | OK (registry unchanged) |
| `python3 evals/tools/baseline.py --cmd 'python3 evals/run_evals.py' --runs 2` | 0 | both runs: 5,797 tests, pass 1.000, compliance 1.000 (30 sealed files); 1,037.8 s and 992.1 s; runtime mean 1,014.9 s, band_2sigma 64.7 s |
| `--sabotage compliance` → `block_compliance_suite_pass_rate.json` | 0 | 0.9667 (29 of 30; `tests/test_compliance.py` removed for real) |
| `--sabotage count` → `block_offline_test_count.json` | 0 | 1,306 (< floor 3,150) |
| `--sabotage suite` → `block_full_suite_pass_rate.json` | 0 | 0.99983 (one injected failing test) |
| `python3 evals/tools/promote.py` | 0 | PROMOTE with 1 soft warning: runtime 992 s vs the 900 s registry ceiling |
| `python3 evals/fixtures/verify_block_fixtures.py` | 0 | all 3 hard gates proven to fire; healthy PROMOTEs |

**Founder decision (not changed here).** The suite now runs about 1,000 s, above the 900 s soft ceiling in `evals/registry.yaml`, so every run shows a soft warning. A soft warning never blocks. The options are to raise the ceiling, which is a threshold change and needs its own reviewed PR, or to make the suite faster.
