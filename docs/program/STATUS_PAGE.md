# status.calendarharvest.com — Phase 3

Status: built and drilled locally on branch `claude/status-page` (2026-10-11).
**Not live.** The founders still have to do D6 (UptimeRobot read-only key and the DNS
record) and decide D2 (the production worker). The CI job must land in its own
`gate/` PR (section 9). Spec: `STAR_PROMPT.md` §A.5.

Principle: the page must not depend on what it reports on. If the API is down,
the page still loads and says so. If it cannot check something, it says "No data",
never "Operational".

## 1. Architecture

```
 browser ──► status.calendarharvest.com   (Vercel project #2, root dir status-page/)
               │  Next.js 15 App Router, server-rendered, revalidated every 60 s (ISR)
               │
               ├─► UptimeRobot API v2 getMonitors      read-only key, server-side env only
               │     6 external monitors (section 4): up/down now + 90 daily uptime values
               │
               └─► LeadPilot API  GET /status/public   5 s timeout
                     the same checks as GET /health (app/services/health_checks.py)
```

- **Separate.** `status-page/` imports nothing from `frontend/` or `app/`. It has its own
  `package.json` (next, react, react-dom, yaml) and its own Vercel project. `.dockerignore`
  keeps it out of the API image.
- **Key stays on the server.** `UPTIMEROBOT_API_KEY` is read only by `lib/config.ts` and sent
  only in the POST body to UptimeRobot. Tests prove it is not in the snapshot, the HTML,
  `/api/status` or any client bundle (`tests/hygiene.test.ts`, `tests/snapshot.test.ts`; drill
  in section 8 checked the built `.next/static`).
- **Rate.** The home page and `/api/status` regenerate at most once a minute however many
  people visit, so UptimeRobot's free limit (10 requests/minute) is never approached. In
  drill (a) the served site answered about 10 page requests between 20:02:21 and 20:03:27 UTC
  and the stub UptimeRobot received one `getMonitors` call in that window (the 20:03:17
  regeneration); its other calls came from the two builds and one CLI drill run.
- **Without JavaScript.** Everything is server-rendered. JavaScript adds only the local-time
  tooltip on timestamps.

### Pages

| Path | What |
|---|---|
| `/` | Data notice (when a source is missing), overall banner, active incidents, 5 components with status icon + label, 90-day uptime bars (per-day tooltip; days below 100% listed as text), the last 14 days of incidents |
| `/incidents/<file name without .md>` | One incident with every update |
| `/history` | All incidents by month |
| `/history.rss`, `/history.atom` | Feeds, built at deploy time |
| `/api/status` | The home page's data as JSON (no key in it) |

Quality points: status by text and a distinct icon shape (check, triangle, half-filled square,
octagon with cross, clock, question mark), never colour alone; colours in `lib/palette.ts` are
tested for WCAG AA (4.5:1 text, 3:1 graphics) in light and dark mode
(`tests/palette.test.ts`); dark mode follows the OS setting; the layout uses a 16 px gutter and
flexible bars, so it fits 360 px; all times are UTC with a local-time tooltip.
**Lighthouse accessibility was not measured**: there is no browser in the build sandbox and
the Playwright browser download is outside the allowed registries. Run it on the Vercel
preview URL (section 10).

## 2. Components and what measures each

| Component | Normal source | When `/status/public` cannot be read |
|---|---|---|
| Website & app | UptimeRobot: Website + App login monitors. All up = Operational; one down = Partial outage; both down = Major outage; otherwise No data | same |
| API | Backend: DB `SELECT 1` + Redis PING. Both ok = Operational; Redis down = Partial outage; DB down = Major outage | "LeadPilot - API" monitor: up = Operational, down = Major outage, else No data. Note: "Detail unavailable — status from external monitoring" |
| Background processing | Backend: Celery heartbeat age. ≤120 s = Operational; 120–300 s = Degraded; missing, unreadable or Redis down = Major outage | Keyword monitor up = Operational; worker monitor down, or API up but keyword down = Major outage; else No data |
| AI features | Backend: Anthropic Models API with the gateway key (no model call, no tokens billed). 200 = Operational; 429/5xx/529/timeout = Degraded; 401/403/404 or no key = Major outage | Never derived: No data |
| Booking pages | Backend: DB reachable and the 3 booking tables queryable = Operational, else Major outage. Also Major outage if the "Booking page" monitor is down | API monitor down or booking monitor down = Major outage; else No data |

The overall banner is the worst known status. If any component is No data and nothing is
worse than Operational, the banner reads "Some systems could not be checked" — never "All
systems operational".

**AI check blind spots.** The Models API does not use credit, so an exhausted credit balance
or a wrong `ANTHROPIC_MODEL` still reads Operational; those surface in the pipeline's
terminal-failure path. The probe result is cached 5 minutes per API process.

**Detection time.** Backend-detected problems: up to 30 s (endpoint cache) + up to 2 × 60 s
(page regeneration). A dead API: UptimeRobot's 5-minute interval + up to 2 × 60 s. If the
status site cannot reach the API but UptimeRobot can, the API shows Operational (derived,
labelled), because the independent check says it answers.

## 3. `GET /status/public` (backend)

`app/api/status_public.py`, registered in `app/main.py`. Unauthenticated. No auth middleware
exists in this app (auth is per-route), so nothing needed allow-listing; CORS is not widened
because only the status site's server calls it.

```json
{"components":[
 {"id":"api","name":"API","status":"operational","checked_at":"2026-10-10T20:01:36Z"},
 {"id":"background-processing","name":"Background processing","status":"operational","checked_at":"2026-10-10T20:01:36Z"},
 {"id":"ai-features","name":"AI features","status":"major_outage","checked_at":"2026-10-10T20:01:36Z"},
 {"id":"booking-pages","name":"Booking pages","status":"operational","checked_at":"2026-10-10T20:01:36Z"}]}
```
(Real response from the local drill; AI is `major_outage` there because no Anthropic key was set.)

- Statuses: `operational | degraded | partial_outage | major_outage | maintenance`. The backend
  never emits `maintenance`; an incident file with `impact: maintenance` does.
- No error strings, hostnames, queue names, counts, ages or tenant data:
  `tests/test_status_public.py` asserts the exact key set and scans every failure-mode body for
  internal text.
- Cached in-process for 30 s (`Cache-Control: public, max-age=30`).
- Rate limit: `enforce_rate_limit` as the handler's first statement, per client IP,
  `RATE_LIMIT_PUBLIC_STATUS` (default 600/hour), same pattern as `/public/roi`.
- `GET /health` is unchanged. Its checks moved to `app/services/health_checks.py`; its exact
  response bytes are pinned by `TestHealthUnchanged` (9 tests), which passed against the original
  `health.py` before the move and again after.

## 4. UptimeRobot — what the founders do (D6)

Names must match exactly (case ignored): the site finds monitors by name.

**Current account (read 2026-10-11 through the UptimeRobot connector, read-only):**

| id | name | type | state |
|---|---|---|---|
| 804163676 | LeadPilot API /health (keyword) | Keyword, alert if `"status":"ok"` does NOT exist | UP for 7 days |
| 804162778 | LeadPilot API | HTTP | PAUSED (duplicate) |
| 804162687 | LeadPilot API /health | HTTP | PAUSED (duplicate) |

**The active keyword monitor cannot detect the outage it was made for.** A degraded `/health`
body still contains `"status":"ok"` inside its healthy sub-components:
`{"status":"degraded","components":{"database":{"status":"ok"},...}}`. That is why it stayed UP
through the 2026-10-10 production degradation (`BASELINE.md`). The keyword must be the start of
the healthy body, which only the top-level status produces:

```
{"status":"ok","components"
```
`tests/test_status_public.py` pins that prefix (healthy body starts with it; degraded body does
not contain it).

Steps:
1. **Delete** the two paused duplicates (804162778, 804162687).
2. **Edit** 804163676: rename to `LeadPilot - API healthy`; keyword value
   `{"status":"ok","components"`; keep "alert when keyword does not exist", 5-minute interval.
   Expect it to go DOWN immediately while the worker is asleep — that is the truth (D2).
3. **Create** five monitors (5-minute interval, HTTP(s), follow redirects):

| Friendly name | Type | URL | Notes |
|---|---|---|---|
| `LeadPilot - Website` | HTTP(s) | `https://calendarharvest.com/` | Marketing home |
| `LeadPilot - App login` | HTTP(s) | `https://calendarharvest.com/login/` | Static export uses trailing slashes |
| `LeadPilot - Booking page` | HTTP(s) | `https://calendarharvest.com/book/` | The public booking shell (`/book/<slug>` rewrites to it). Proves the page is served; the backend half is in `/status/public` |
| `LeadPilot - API` | HTTP(s) | `https://leadpilot-api-ph3t.onrender.com/health` | Down on 503 (DB/Redis down) or no answer. 200 for "degraded", so this means "API answers" |
| `LeadPilot - Worker` | HTTP(s) | `https://leadpilot-worker-708k.onrender.com/health` | **Needs D2 first.** The worker does expose HTTP: `render.yaml` runs it as a free web service, `scripts/render_worker_entrypoint.sh` starts `app/worker_health.py`, which answers 503 when a Celery child died. A 5-minute ping keeps the free worker awake (D2 option A) but uses ~730 of the 750 free instance-hours per month shared with the API (`BASELINE.md` §6, unverified against Render's current terms). If D2 = paid Background Worker, the service has no HTTP; skip this monitor and the page derives background status from the keyword monitor. |

4. **Read-only API key:** UptimeRobot dashboard → Integrations & API (older dashboards: My
   Settings → API Settings) → Read-Only API Key → create. Menu labels unverified; the key type is
   "read-only" (it can call `get*` methods only). Do not use the main or a monitor-specific key.
5. Do **not** create an UptimeRobot public status page; this site replaces it.

## 5. Vercel — what the founders do (D6)

1. vercel.com → Add New → Project → import `Rmasood1122/LeadPilot` (same repo as the frontend;
   a second project).
2. **Root Directory: `status-page`**. Framework preset: Next.js. Build command, output and
   install: defaults (`npm install`/`npm ci`, `next build`). Node.js version: 22.x.
3. Environment variables (Production and Preview), **none prefixed `NEXT_PUBLIC_`**:

| Name | Value |
|---|---|
| `UPTIMEROBOT_API_KEY` | the read-only key from step 4 above (mark Sensitive) |
| `LEADPILOT_API_URL` | `https://leadpilot-api-ph3t.onrender.com` |
| `STATUS_SITE_URL` | `https://status.calendarharvest.com` (optional; this is the default, used in feeds) |

4. Deploy; open the preview URL; check: banner, five components, bars, `/history.rss`.
5. Settings → Domains → add `status.calendarharvest.com`. Vercel then shows the exact DNS record.
   For a subdomain it is normally **CNAME `status` → the target Vercel displays** (often
   `cname.vercel-dns.com`); use the value Vercel shows, not this one. Add it at the DNS host of
   `calendarharvest.com`. Leave the apex and existing records alone (email SPF/DKIM live there).
6. Optional: Settings → Git → Ignored Build Step so only `status-page/` changes rebuild it.
   (Incident files are inside `status-page/`, so they still deploy.)

## 6. Go-live checklist

- [ ] D2 decided; worker monitor created or deliberately skipped (section 4).
- [ ] Monitors renamed/created, duplicates deleted, keyword fixed.
- [ ] Vercel project, env vars, domain, DNS (section 5); page loads on its domain.
- [ ] Lighthouse accessibility ≥ 95 on the live URL recorded here.
- [ ] `gate/` PR with the `verify-status-page` job merged (section 9).
- [ ] Then set `SHOW_STATUS_LINK = true` in `frontend/src/lib/statusPage.ts`: shows "Status" in
      the marketing footer (Company column) and an icon link in the support widget header.
      It is `false` now so nobody is sent to a domain that does not resolve.
- [ ] Help-center article 30 links here (Phase 2; `docs/help-center/` does not exist on this branch).

## 7. Posting an incident

A pull request that adds or edits one file. Format and rules: `status-page/incidents/README.md`.

1. Branch, add `status-page/incidents/YYYY-MM-DD-<slug>.md` (date = UTC date of the first update).
2. `cd status-page && npm run incident-lint` (≈1 s).
3. Open the PR, merge with `scripts/gate/safe_merge.sh <PR>`. Vercel redeploys; the incident is
   on the page and in both feeds once the deploy finishes.
4. For each new update, append to `updates:` in the same file. Resolve with a final
   `status: resolved` update. Never rename the file (its URL is in feed readers).

An invalid incident file fails `incident-lint` and also fails `next build`, so a broken file can
never deploy silently. **Limitation:** an incident-only PR still runs the `gate` job of the
sealed `eval-gate.yml` (~9 minutes; it has no path filter and cannot be changed in a feature PR),
so an incident cannot be merged through `safe_merge` faster than that. The `verify-*` jobs
skip-but-succeed in under a minute except `verify-status-page` (~1–2 min, estimated) and
`verify-security` (~1 min).

## 8. Exit-gate 3 drills (performed locally, 2026-10-10 UTC)

Set-up: the real API (`uvicorn app.main:app`, SQLite with all tables, local Redis on 6390,
heartbeat key set by hand, no Anthropic key) on `127.0.0.1:8011`; a stub of UptimeRobot's
`getMonitors` on `127.0.0.1:9911` (via `UPTIMEROBOT_API_URL`); the status site built and served
with `next start` on port 3100. The stub is a drill aid kept outside the repo.

**(a) API stopped.** Baseline page: API, Background processing, Booking pages Operational
(source: backend); AI features Major outage (no key — correct). API killed at 20:02:37; the stub
then reported the API monitors down, as UptimeRobot would on its next check. Page polled every
10 s:

```
20:02:37    +0s api=operational  page_generated=20:02:10
...
20:03:17   +41s api=operational  page_generated=20:02:10   (this request triggered regeneration)
20:03:27   +51s api=major_outage bg=unknown booking=major_outage ai=unknown
                 notice='Detail unavailable'  page_generated=20:03:17
notes: 'Detail unavailable — status from external monitoring', 'Detail unavailable'
```
Outage shown 51 s after the stop: within two refresh cycles. AI features and Background
processing showed "No data" rather than Operational. Data layer alone (`npm run drill` with the
API down):
```
sources        uptimerobot=ok backend=unreachable
DATA NOTICE    Detail unavailable: LeadPilot's own component checks could not be reached. ...
BANNER         Major outage
  Website & app          Operational           source=external
  API                    Major outage          source=external Detail unavailable — status from external monitoring
  Background processing  No data               source=none     Detail unavailable
  AI features            No data               source=none     Detail unavailable
  Booking pages          Major outage          source=external Detail unavailable — status from external monitoring
```

**(b) UptimeRobot key removed.** Rebuilt and served without `UPTIMEROBOT_API_KEY`: every route
200 (`/`, `/api/status`, `/history`, `/history.rss`, `/history.atom`), no error in the server log.
```
notice: Status data unavailable — External monitoring is not configured for this page, so uptime
        history is missing and the Website & app component cannot be checked. The other
        components show LeadPilot's own checks.
Website & app = unknown (No data); API, Background processing, Booking pages = operational
(backend); AI features = major_outage (backend); uptime bars rendered: 0
```
With no env vars at all (the CI build), the page renders "Status data unavailable" and
"Current status unknown".

**(c) Incident file added.** A file marked "DRILL (not a real incident)" (impact `major`,
component `background-processing`, two updates) was added, linted (`ok`), built and served:
home page showed it under Active incidents and raised Background processing to Partial outage
with "Set by an open incident below"; `/incidents/2026-10-10-drill-…` rendered both updates and
the body; `/history` listed it; `/history.rss` had one `<item>` with title, permalink, pubDate
19:45 GMT and both updates; `/history.atom` had one `<entry>`. The file was then deleted. A
deliberately broken file made `incident-lint` exit 1 with five specific errors.

**Still needed for exit gate 3:** a Vercel preview URL, the same three drills against the real
UptimeRobot account and production API once D6 is done, the Lighthouse score, and founder
confirmation of DNS and D2.

## 9. CI job (its own `gate/` PR)

`.claude/hooks/protect_sealed.py` allows `.github/workflows/*` changes only on `gate/` or
`claude/gate-` branches, so the job is **not** in the `claude/status-page` diff. Add this job to
`.github/workflows/verify.yml` (before `verify-image`) in a `gate/verify-status-page` PR, then add
`verify-status-page` to `scripts/gate/required_checks.txt` once it has run green on `master`:

```yaml
  verify-status-page:
    if: github.event_name == 'push' || github.event.pull_request.draft == false
    runs-on: ubuntu-latest
    timeout-minutes: 15
    defaults:
      run:
        working-directory: status-page
    steps:
      - uses: actions/checkout@11d5960a326750d5838078e36cf38b85af677262 # v4.4.0
        with:
          fetch-depth: 0
      - name: Scope
        id: scope
        working-directory: .
        run: |
          if [ "${{ github.event_name }}" = "push" ]; then echo "run=true" >> "$GITHUB_OUTPUT"; exit 0; fi
          base="${{ github.event.pull_request.base.sha }}"
          if git diff --name-only "$base" HEAD | grep -qE '^status-page/'; then
            echo "run=true" >> "$GITHUB_OUTPUT"
          else
            echo "run=false" >> "$GITHUB_OUTPUT"
            echo "No status-page changes: skipped (success)." >> "$GITHUB_STEP_SUMMARY"
          fi
      - uses: actions/setup-node@49933ea5288caeca8642d1e84afbd3f7d6820020 # v4.4.0
        if: steps.scope.outputs.run == 'true'
        with:
          node-version: "22"   # 22.18+ runs the TypeScript tests and scripts natively
          cache: npm
          cache-dependency-path: status-page/package-lock.json
      - name: npm ci
        if: steps.scope.outputs.run == 'true'
        run: npm ci --no-audit --no-fund
      - name: Incident lint
        if: steps.scope.outputs.run == 'true'
        run: npm run incident-lint
      - name: Type-check
        if: steps.scope.outputs.run == 'true'
        run: npm run type-check
      - name: Unit tests (data layer, incidents, feeds, contrast)
        if: steps.scope.outputs.run == 'true'
        run: npm test
      - name: Production build (no env vars)
        if: steps.scope.outputs.run == 'true'
        run: npm run build
```
Same pinned SHAs and skip-but-succeed pattern as the existing jobs. Until it lands, nothing in CI
builds or tests `status-page/` (the `gate` job runs Python only).

## 10. Local commands

```bash
cd status-page
npm ci
npm run incident-lint      # incident files
npm run type-check         # next typegen && tsc --noEmit
npm test                   # node:test, offline (fake fetch)
npm run build              # must pass with no env vars
UPTIMEROBOT_API_KEY=... LEADPILOT_API_URL=https://leadpilot-api-ph3t.onrender.com npm run drill
```
There is no ESLint in `status-page/` (kept to 4 runtime dependencies); `tsc` runs in strict mode
with unused-code checks, and `npm run lint` = type-check + incident-lint.

`package.json` overrides `postcss` to 8.5.29: Next 15.5.27 pins postcss 8.4.31, which
`npm audit` reports as high (GHSA-qx2v-qp2m-jg93 and three source-map advisories), and npm's
only suggested fix is Next 16. postcss runs at build time on this project's own CSS, so the real
exposure was low; with the override the build passes and `npm audit --omit=dev` reports 0.
Remove the override when Next ships a fixed postcss.

## 11. Out of scope / follow-ups

- Email/SMS subscriptions (need double opt-in and unsubscribe handling).
- Scheduled-maintenance announcements ahead of time (an incident with `impact: maintenance`
  covers "in progress" only).
- UptimeRobot v2 is a legacy API ("no longer receiving updates"; no end date announced). Moving
  to v3 is a contained change in `lib/uptimerobot.ts`.
- `GET /health` exposes raw exception text in its `celery.error` field (pre-existing, unchanged
  here on purpose; reported for triage).
