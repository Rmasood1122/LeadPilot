# M7 Complete — Mobile App (Android) + M8 Handoff

## Milestones 1–7: what has been built

| Milestone | What it delivered |
|---|---|
| M1 | FastAPI + PostgreSQL + Celery/Redis backend; 72/144-step resumable pipeline engine; 10× verification loop |
| M2 | Apollo.io + Hunter.io adapters; lead database; enrichment pipeline |
| M3 | Gmail OAuth sequences; Calendly webhook; reply detection and classification |
| M4 | WhatsApp Business Cloud API; template registry; opt-in management; 24-hour window enforcement |
| M5 | Next.js 14 web app; kanban pipeline; campaigns view; analytics; full theme engine (5 presets + custom) |
| M6 | `clienthunter` pip package + CLI (`init`, `run`, `status`, `serve`, `leads`, `campaign`) |
| **M7** | **Android app (Play Store); native behaviors; FCM push notifications; signed release build** |

---

## M7 completion — what the Android app can and cannot do

### Can do (by design)
- **Installs from the Play Store** as `com.clienthunter.app`
- **Connects to the cloud backend** over HTTPS; all API calls go to the deployed FastAPI service
- **Shows all core views** from the M5 web app: pipeline kanban, campaigns, strategies, analytics, settings/theme
- **Receives push notifications** for: strategy ready, strategy needs review, new lead reply, meeting booked, campaign paused, WhatsApp template approved/rejected
- **Handles deep links** (`clienthunter://` custom scheme + `https://app.clienthunter.com` App Links): links from push notifications and outreach emails open the correct in-app view
- **Stores auth tokens securely** in Capacitor Preferences (OS-level key storage), not in browser localStorage
- **Shows offline awareness** via the OfflineBanner: distinguishes "no network" from "backend temporarily down"; always reassures that campaigns continue server-side
- **Handles the Android back button** correctly: root sections show an exit confirmation dialog; nested views navigate up. Play Store reviewers check this.
- **Works on Android 8+** (API 26+, matching Capacitor 6 minimum — TODO: verify exact minimum)

### Cannot do (by design — not bugs)
- **Cannot run campaign logic locally.** The app is a window into the cloud backend. Campaigns run on the server whether or not the app is open — this is the correct architecture per project spec (section F). A phone that is powered off does not pause any campaign.
- **Cannot send messages directly.** All outreach (Gmail, WhatsApp) is orchestrated by the Celery workers on the backend. The app monitors and controls; the backend executes.
- **Cannot work offline for writes.** Strategy creation, campaign launch, lead status updates all require the backend to be reachable. Read-only views fall back to React Query cached data when offline.
- **Not available on iOS.** iOS requires a Mac + Xcode + Apple Developer account ($99/year). The `ios/` Capacitor platform can be added with `npx cap add ios` when ready; the codebase is already iOS-compatible by design (Capacitor targets both). Push notifications on iOS additionally require APNs certificate configuration in Firebase.
- **Not published via direct APK.** The Play Store is the distribution channel; sideloading is possible but not the supported path.

---

## M8 Handoff — Learning Loop

M8 implements the self-learning feedback loop described in project spec section C (Flow 3) and section J. Here is exactly what it will consume and what the database is waiting to hand it.

### What the `outcomes` table already contains

Every action taken across M1–M7 is logged as a row in `outcomes`:

| Event type | Logged since | What it encodes |
|---|---|---|
| `sent` | M3 | Email/WhatsApp message sent; includes `lead_id`, timestamp, channel |
| `opened` | M3 | Email opened (Gmail read receipt) |
| `replied` | M3 | Reply received and classified |
| `booked` | M3 | Meeting booked via Calendly |
| `won` / `lost` | M1 | Final deal outcome (manually set or inferred) |
| `unsubscribed` | M3 | CAN-SPAM/GDPR unsubscribe |
| `bounced` | M3 | Email bounced; campaign auto-paused if rate > 3% |
| `notification_sent` | **M7** | Push notification delivered; includes `data.deepLink` |

Each row links to `lead_id` → `strategy_id` → `product_id` → `user_id`, giving M8 a complete chain from "which product" through "which strategy and channel" to "which outcome."

### What `playbook_scores` is waiting for

The `playbook_scores` table was created in M1 with the schema `(pattern_key, metric, score, sample_size)`. It has never been written to — that is M8's job. The `pattern_key` will encode strategy patterns (e.g. `"industry:saas|channel:email|persona:cto"`), and `score` will encode the empirical conversion rate for that pattern based on real `outcomes` data.

New strategies (M1 pipeline) already have a TODO hook that says "consult playbook_scores first." M8 will wire in the lookup so strategies built after the first learning cycle automatically favour patterns that have shown high reply and booking rates.

### What the A/B test groundwork (M5) hands to M8

M5 sequence steps have a `variant` label (e.g. `"subject_v1"`, `"subject_v2"`). M8's nightly aggregation job will:
1. Group `outcomes` by `(sequence_id, variant, event)` to compute per-variant conversion rates.
2. Run a significance test (chi-squared or Bayesian A/B) when `sample_size` is sufficient.
3. Auto-promote the winning variant by setting all other variants' `is_active=False` on the `messages` table.
4. Update `playbook_scores` with the promoted variant's performance data.

### M8 Celery tasks to build

- `nightly_aggregation` (Celery Beat, daily): reads all `outcomes` since last run → updates `playbook_scores`
- `ab_test_evaluator` (Celery Beat, daily after aggregation): evaluates variant significance → promotes winners
- `strategy_playbook_lookup` (hook in M1 pipeline, Phase 1, Step 1): before running research, query `playbook_scores` for this `product_id`'s best-performing patterns → seed Phase 1 context

### Estimated M8 scope

4–6 build chunks:
1. Nightly aggregation task + playbook score writer
2. A/B test evaluator + auto-promotion
3. Strategy pipeline hook (consult playbook before research)
4. Analytics UI additions (M5 dashboard): "What's working" panel showing top playbook patterns with scores and sample sizes
5. (Optional) Manual A/B test creator in the Campaigns UI
6. (Optional) Playbook export for the CLI (`clienthunter playbook` command)
