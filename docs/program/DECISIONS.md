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
| D5 | One required approval on PRs to `master` | ~~Yes, as a written policy~~ **Superseded by MERGE-B**, 2026-10-10 | 2026-10-10 | Replaced after INC-43. Kept for history. |
| INC-43 | Incident: PR #43 merged before CI and review | Recorded 2026-10-10 | 2026-10-10 | The founder merged PR #43 at 09:51:47 UTC on 2026-10-10, before CI finished and without co-founder review. CI later passed (runs 38042867994, 38042869509, 38042886592). Nothing broke, but D5 and "wait for CI" were both honour-system rules and both were skipped in one click. |
| INC-44/45 | Incident: draft PR and red-CI PR merged; master red | Recorded 2026-10-10 | 2026-10-10 | At 12:08 UTC PR #45 was merged with failing CI (run 38050781015) and PR #44 two seconds later while still a draft. The eval-gate run on master then failed at "Gate (candidate vs baseline)" (run 38050896788). PR #46 (green before merge) restored master at 12:28 UTC. Second honour-system failure in one day; `scripts/gate/safe_merge.sh` and the `.claude/hooks/guard_merge.py` PreToolUse hook (Phase 1 item 1.4) are the response. |
| MERGE-B | Merge policy (replaces D5) | **B**, 2026-10-10 | 2026-10-10 | Every merge to `master` goes through `scripts/gate/safe_merge.sh`, which refuses unless every required check on the PR head is green and the PR is not a draft, then squash-merges. Co-founder review happens **after** merge. Not enforced by GitHub on Free: a merge from the web UI bypasses it; deploy gating (Render "After CI Checks Pass", Vercel Deployment Checks) is the backstop. `safe_merge.sh` lands in Phase 1 item 4; until then, merge only a non-draft PR whose checks are all green. |
| D6 | Status page data (UptimeRobot key, DNS) | — | — | **Unanswered.** Blocks Phase 3. |
| GH-PRO | Buy GitHub Pro | **No**, 2026-10-10 | 2026-10-10 | Will not be purchased. The Layer 4 ruleset (`STAR_PROMPT.md` §A.3: `ruleset_master.json`, `apply_ruleset.sh`, required status checks and approvals on `master`) is **dropped**. Phase 1 will use a replacement design the founders supply in the next session. Actions budget stays at 2,000 min/month (Free); see `BASELINE.md` §11.2. |
| P0-D | Deployment model | **Self-hosted, single-tenant**, 2026-10-04 | 2026-10-10 | See below. |
| P0-5-CAPS | Daily AI spend cap per plan (USD per UTC day) | — | — | **Unanswered.** `app/core/plans.py` ships placeholders so no plan is unlimited: free 10, starter 25, growth 60, pay_per_meeting 60, scale 150, pro 150, enterprise 400. Founders confirm or replace the numbers, and say whether a monthly cap is wanted as well (`BASELINE.md` §12 item 3 proposed monthly). Detail: `plans/p0-5-account-spend-cap.md`. |

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

**P0-D-ENF — unanswered decision.** The switch now exists (`SIGNUP_ENABLED`,
`SIGNUP_ALLOWED_EMAIL_DOMAINS`; the defaults keep sign-up open to anyone).
Founders choose per deployment: closed, limited to the customer's own email
domains, or open (then the HIGH ratings above apply to it). Detail:
`plans/p0-d-enf-signup-switch.md`.

`CLAUDE.md` line 11 was updated to "Self-hosted, single-tenant per P0-D" on
2026-10-10, with founder approval.
