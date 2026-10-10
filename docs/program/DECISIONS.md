# Founder decisions

One row per decision from `STAR_PROMPT.md` Part 0 (D1–D6) and the Phase 0
baseline (P0-D). A decision is recorded here only when a founder has stated it.
Help-center articles and specs may cite this file as a source.

| ID | Decision | Date decided | Recorded | Consequences |
|---|---|---|---|---|
| D1 | Website copy vs. what the code does | — | — | **Unanswered.** Blocks Phase 2 articles 01, 09, 10, 11. |
| D2 | Production worker hosting | **Deferred to Phase 3** | 2026-10-10 | No production requests in Phase 0 follow-up sessions. Options A/B/C stay as written in `BASELINE.md` §6. |
| D3 | Repository visibility | **Private**, 2026-10-10 | 2026-10-10 | `BASELINE.md` may be pushed. On GitHub Free, rulesets and branch protection are not available on private repositories (see GH-PRO). |
| D4 | "70% better than competitors" | n/a | — | Not a decision; replaced by the R.3 scorecard. Do not publish the claim. |
| D5 | One required approval on PRs to `master` | **Yes, as a written policy**, 2026-10-10 | 2026-10-10 | The other co-founder approves every PR to `master` before merge. **GitHub cannot enforce this:** required reviews need branch protection or a ruleset, which on a private repository need GitHub Pro (declined, GH-PRO). It is an honour-system rule until a replacement mechanism exists. |
| D6 | Status page data (UptimeRobot key, DNS) | — | — | **Unanswered.** Blocks Phase 3. |
| GH-PRO | Buy GitHub Pro | **No**, 2026-10-10 | 2026-10-10 | Will not be purchased. The Layer 4 ruleset (`STAR_PROMPT.md` §A.3: `ruleset_master.json`, `apply_ruleset.sh`, required status checks and approvals on `master`) is **dropped**. Phase 1 will use a replacement design the founders supply in the next session. Actions budget stays at 2,000 min/month (Free); see `BASELINE.md` §11.2. |
| P0-D | Deployment model | **Self-hosted, single-tenant**, 2026-10-04 | 2026-10-10 | See below. |

## P0-D — self-hosted, single-tenant (decided 2026-10-04)

Meaning, as applied in `BASELINE.md`: each deployment of LeadPilot (database,
Redis, API, worker) serves **one customer organisation**. Several user accounts
may exist in one deployment, but they all belong to that customer.

Effects on the baseline (detail in `BASELINE.md` §3.5):

- **F-DB-01** (shared `playbook_scores`): HIGH → **MEDIUM**.
- **RF-5** (one WhatsApp sender per deployment): HIGH → **MEDIUM**.
- **Not downgraded**, by founder instruction and on their own merits:
  GDPR account export/deletion, the per-account AI spend cap (P0-5), plan
  enforcement. Each is a defect whether a deployment has one tenant or many.

The decision is **not enforced by the code today**. `POST /auth/signup`
(`app/api/auth.py:207`) accepts any visitor, and no setting in `app/config.py`,
`app/core/config.py` or `app/services/system_settings.py` turns it off. A
deployment that leaves sign-up open is multi-tenant in practice, and the HIGH
ratings return for it. Tracked as **P0-D-ENF** in `BASELINE.md`.

`CLAUDE.md` line 11 was updated to "Self-hosted, single-tenant per P0-D" on
2026-10-10, with founder approval.
