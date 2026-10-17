# Connector Phase 0: recon (read-only)

Date: 2026-10-17. Branch `claude/awesome-lovelace-okii9j`, read at `master @ 2813fbc`.
Scope: Phase 0 of the LeadPilot ↔ Claude/ChatGPT integration. That integration has three parts: a remote MCP server in the FastAPI app, an OAuth 2.1 authorization server, and a Skill plus a Claude Code plugin.
No code changed in this phase. Every citation below was read in this session. Where a sub-agent found a citation, it was spot-checked against the file.

**Status: STOPPED. The founder questions are in §9. No production code will be written until they are answered.**

---

## 0. Headline findings (read these first)

1. **The database layer is synchronous.** It uses `create_engine` + `SessionLocal = sessionmaker(...)` (`app/db/base.py:30-40`) and `get_db()` (`app/db/base.py:43-49`). There is no `AsyncSession` anywhere in `app/`.
   - The brief's "one AsyncSession per tool call" therefore becomes "one `SessionLocal()` per tool call".
   - MCP tools will be plain `def` functions. The SDK runs sync tools in a worker thread (`mcp/server/mcpserver/utilities/func_metadata.py:164`, `anyio.to_thread.run_sync`).
2. **Many capabilities have no service function; the logic lives in route handlers.** This applies to most reads and to two of the four proposed writes.
   - `create_strategy` (`app/api/strategies.py:141-208`) runs the plan check, spend guard, autopilot opt-in and Celery enqueue inline.
   - Pause and resume are inline in `app/api/analytics.py:143-185`.
   - Under the rule "never expose a tool that does not go through the service function that carries the gates", these cannot be wrapped as they are. They first need a behaviour-preserving extraction into `app/services/`. That is founder question Q4.
3. **The `mcp` SDK is not a project dependency, and its current version conflicts with our pins.**
   - `mcp` 2.2.0 is installed system-wide in this container (pulled in by `claude-agent-sdk`). It is in neither `requirements.txt`, `requirements.lock` nor `pyproject.toml`.
   - `mcp` 2.x requires `uvicorn>=0.31.1`. We pin `uvicorn[standard]>=0.30.0,<0.31` (`requirements.txt:7`, `pyproject.toml:23`; lock `uvicorn==0.30.6`).
   - With our pins, pip resolves only `mcp==1.12.4` (dry-run, §3). That release predates `TokenVerifier`.
   - `mcp==2.3.0` resolves against `fastapi==0.111.1` + `starlette==0.37.2` once uvicorn is raised to `>=0.31.1`. Runtime compatibility of mcp 2.x with starlette 0.37.2 is **not yet tested**. That is founder question Q5.
4. **There is no server-rendered login page.** Login is a JSON API (`POST /auth/login`, `app/api/auth.py:377`) used by the Next.js frontend. `app/templates/` holds only `roi_card.html`. The OAuth `/authorize` step therefore needs a login + consent UI built new: in Next.js, or as a small HTML page served by the API. That is part of Q1.
5. **The "15-check outreach gate" does not exist under that name.**
   - The send-time gate is `send_message_impl` (`app/workers/outreach_tasks.py:132`), run by the Celery task `leadpilot.outreach.send` (`outreach_tasks.py:1969-1970`).
   - It runs about 26 checks in sequence, at actual send time, not at schedule time.
   - Nothing proposed here touches it. A tool that schedules or releases a message only feeds this gate.
6. **"Audit event with `actor_channel="mcp"`" has no direct home.**
   - The hash-chained trail (`app/services/audit_trail.py:132` `record_outcome`) records only `Outcome` rows for sent/opened/clicked/replied/booked. It has no actor or channel parameters. Writing to it from MCP would change what the chain means.
   - The general recorder is `security_audit.record(db, *, action, request=None, user_id=None, owner_user_id=None, target_type=None, target_id=None, details=None)` (`app/services/security_audit.py:73-76`). Its `details_json` can carry `actor_channel` and `oauth_client_id`.
   - Proposed default: new `security_audit` action constants (`MCP_*`) with those two fields in `details`. The hash-chained trail stays untouched.
7. **RBAC is path-based and runs inside `get_current_user`.** `rbac.enforce(role, method, path)` (`app/services/rbac.py:49`) is called from `_workspace_principal` (`app/services/auth.py:231-257`), and only when an `X-Workspace-Id` header is present.
   - MCP tool calls have no REST method or path, so this check does not carry over automatically. That is founder question Q6.

---

## 1. Program documents read

- `docs/program/BASELINE.md` (§1-4 read in full; the rest skimmed for connector-relevant rows)
- `DECISIONS.md`, `GATES.md`, `PROGRESS.md`
- `coding_standards.md` and `current_situation.md` **do not exist** (`find . -name …` found nothing). The binding conventions are therefore `CLAUDE.md` and the decisions above.

Constraints carried forward:
- **P0-D-ENF.** Sign-up is open, so the deployment is multi-tenant in practice and every tenant-owned query needs an owner filter (`DECISIONS.md`).
- **MERGE-B.** Merge only via `scripts/gate/safe_merge.sh`.
- **FEATURE-SPECS.** A spec ships in the same PR as its code.
- **AUTHOR.** New commits are authored as `Ahmad317-Engineer <devsahmad37@gmail.com>`.
- **Sealed files.** Not touched. Per `CLAUDE.md`, any new legal/safety guard test file must be added to the sealed list in the same commit that introduces it. That will apply to the MCP tenant-isolation and untrusted-content tests in Phase 1.
- **The test count is a floor** (`offline_test_count` 3,150). New tests raise the count and need no baseline edit. A baseline refresh is its own sealed PR (`phase1-03-baseline-refresh.md`).

---

## 2. Authentication and identity: what is reused

### 2.1 `get_current_user` (`app/services/auth.py:157`)

```python
def get_current_user(request: Request, db: Session = Depends(get_db)) -> User:
```

It is synchronous and reads headers by hand (no `HTTPBearer`). In order:

| Step | Lines | Behaviour |
|---|---|---|
| Header | 181-186 | `Authorization: Bearer …`. Falls back to `X-API-Key`. Otherwise 401 `"missing bearer token"`. |
| API key | 191-197 | Token prefix `lpk_` (`api_keys.py:21`) → `api_keys.authenticate(db, token)` (`api_keys.py:48`), a SHA-256 hash lookup. Sets `request.state.auth_via="api_key"`. Keys have **no scopes**. |
| JWT | 199-210 | `decode_token_payload(token, "access")` (`auth.py:121-137`), HS256 with `settings.jwt_secret`. Then `db.get(User, sub)`, then `auth_sessions._issued_before_password_change`. |
| Tombstone | 216-219 | Erased account → 401. |
| Suspension | 224-225 | `is_suspended` → **403 `"account suspended"`** |
| Email verification | 226-227 | 403 `EMAIL_NOT_VERIFIED` when `require_email_verification` is on. |
| Workspace / RBAC | 228, 231-257 | `X-Workspace-Id` → `workspaces.resolve`. A non-owner goes through `rbac.enforce(role, method, path)` and the **owner's** `User` is returned. The signed-in person is kept in `request.state.actor`. |

**Reuse plan.** Do not call `get_current_user` with a fake `Request`. Factor its post-decode checks (tombstone, suspension, email verification) into one function both paths call, e.g. `auth.check_principal(db, user)`.
- The REST dependency keeps its exact behaviour, and the MCP `TokenVerifier` calls the same function.
- That is a small edit to `auth.py`, covered by the existing suspension tests (`tests/test_account_suspension.py`).
- The alternative is duplicating the checks, which drifts. Rejected.

### 2.2 Sessions and refresh tokens (`app/services/auth_sessions.py`)

- **Table:** `AuthSession` / `auth_sessions` (`app/db/models.py:4881-4918`). Columns: `id` (= refresh JWT `jti`), `user_id`, `family_id`, `persistent`, `expires_at`, `last_used_at`, `rotated_at`, `replaced_by_id`, `revoked_at`, `revoked_reason`, `ip`, `user_agent`, `created_at`. The raw token is never stored.
- **Functions:**
  - `issue_session_tokens(db, user, *, persistent=True, request=None, now=None)` at `:117`
  - `rotate(db, refresh_token, *, request=None, now=None)` at `:189`
  - `revoke(db, refresh_token, …)` at `:265`
  - `revoke_family(db, family_id, reason, now=None)` at `:127`
  - `revoke_all_for_user` at `:139`
- **Rotation and reuse:**
  - The old row is claimed atomically: `UPDATE … WHERE revoked_at IS NULL`.
  - Reuse outside the 30 s grace window (`auth_refresh_reuse_grace_seconds`, `app/config.py:189`) revokes the whole family and writes `security_audit.AUTH_REFRESH_REUSE` (`:223-233`).
  - **Reuse inside the grace window returns an access token only** (`:217-222`). Losing the race also returns access only (`:244-253`).
- **Claims:** access tokens carry `sub, typ="access", iat, exp`. Refresh tokens add `jti` and `fam`. No `aud`, no `scope`, no client id. HS256 is hard-coded (`auth.py:90,124`).
- **TTLs:** access 900 s (`config.py:166`), refresh 30 days (`:170`).

**Verdict: the session model can support OAuth rotation** (family, atomic claim, reuse → family revoke). Three gaps must be closed before reuse:

1. **No client or scope binding.** OAuth refresh tokens must be bound to `client_id` and the granted scopes. The proposal adds nullable `oauth_client_id` and `scope` columns to `auth_sessions`, plus an Alembic migration.
2. **Grace-window semantics are wrong for OAuth.**
   - Our `rotate()` answers a replayed refresh token (within 30 s) with an access token and no refresh token.
   - The brief requires `invalid_grant` on reuse.
   - Claude refreshes proactively 5 min before expiry and reactively on 401, so a racing double refresh is plausible.
   - Proposal: an OAuth-specific rotate path that reuses the claim and family logic but returns `invalid_grant` instead of access-only.
   - The web session path keeps its grace window unchanged.
3. **Token confusion.** A LeadPilot web access token (`typ="access"`, no audience) must not be accepted at `/mcp`, and an MCP token must not be accepted by the REST API.
   - Proposal: MCP access tokens carry `typ="mcp_access"`, `aud=<MCP resource URL>`, `scope`, `client_id` and `sid` (session row).
   - The `TokenVerifier` accepts only that `typ` plus a matching `aud`, and sets `AccessToken.resource`.
   - `decode_token_payload(…, "access")` already rejects any other `typ` (`auth.py:121-137`), so the REST API refuses MCP tokens with no change.
   - Personal API keys (`lpk_`) will not be accepted at `/mcp`: they have no scopes, and the brief says not to design around static keys.

### 2.3 Models

- **`User`** (`models.py:397-512`): `is_admin` 411, `is_suspended` 412, `email_verified` 434, `password_changed_at` 493. It has **no role and no tenant FK**.
- **Tenant key is `Product.user_id`** (`models.py:843`). Ownership chains Lead → Strategy → Product. The same filter appears in:
  - `crm_service.py:554`
  - `champion_tracker.py:284-287`
  - `admin_service.py:28`
- **Denormalised `user_id`** exists on `AttributionEntry` (`models.py:4679`), `ClaimVerificationLog` (`:4294`) and `LeadSignal` (`:5309`).
- **`Workspace`** (`:3575-3615`, `owner_user_id` UNIQUE) and **`WorkspaceMember`** (`:3693-3714`, role in owner/manager/sdr/viewer). Data rows keep owner `user_id`; there is no `workspace_id` on data.
- **`ApiKey`** (`:3545-3567`). **`AuthSession`** (`:4881-4918`). **`SecurityAuditEvent`** (`:4921-4953`).
- **There is no OAuth server model.** The only OAuth code is client-side: `app/services/oauth_state.py` (Fernet-encrypted `state` for Slack, HubSpot and Salesforce).

### 2.4 App wiring (`app/main.py`)

- `FastAPI(lifespan=_lifespan, …)` at `:163-175`. `_lifespan` is at `:131-160`.
- Middleware: `RequestIDMiddleware` (`:179`) and `CORSMiddleware` (`:191-198`, `allow_credentials=True`, configured origins). There is **no** TrustedHost, CSP or auth middleware.
- Exception handlers are at `:215-218`; `HTTPException` uses FastAPI's default `{"detail": …}`.
- There are **no `/.well-known` routes** today.

---

## 3. The MCP SDK as actually installed

| Item | Value | Evidence |
|---|---|---|
| Installed | `mcp` **2.2.0** at `/usr/local/lib/python3.13/dist-packages` (Python 3.13.16), required by `claude-agent-sdk` | `pip show mcp` |
| In project manifests | **no** | `grep mcp requirements.txt requirements.lock pyproject.toml` → nothing |
| Latest on PyPI | 2.3.0 (2.x line: 2.0.0 … 2.3.0; 1.x up to 1.30.0) | `pip index versions mcp` |
| Server class | `mcp.server.mcpserver.MCPServer` (`from mcp.server import MCPServer`). **`mcp.server.fastmcp` raises `ModuleNotFoundError`** in 2.x | `mcp/server/__init__.py`, `mcp/server/fastmcp.py` |
| Constructor | `MCPServer(name=None, title=None, description=None, instructions=None, website_url=None, icons=None, version="", auth_server_provider=None, token_verifier=None, *, …, auth: AuthSettings \| None = None, middleware=…)` | `mcpserver/server.py:158-185` |
| Tool decorator | `@server.tool(name=None, title=None, description=None, annotations: ToolAnnotations \| None = None, icons=None, meta=None, structured_output=None)` | `server.py:660-668` |
| Annotations | `mcp.types.ToolAnnotations` with fields `title, read_only_hint, destructive_hint, idempotent_hint, open_world_hint` (wire names `readOnlyHint` etc.) | `mcp_types/_types.py:1365` |
| HTTP app | `server.streamable_http_app(*, streamable_http_path="/mcp", json_response=False, stateless_http=False, …, transport_security=None, host="127.0.0.1") -> Starlette` | `server.py:1279-1307` |
| Stateless | `stateless_http=True`: a fresh transport per request and no session map (`streamable_http_manager.py:67,201-206`). 2.2.0 also serves the **2026-07-28** single-exchange wire (`_streamable_http_modern.py`: no `initialize`, no `Mcp-Session-Id`). | read |
| Auth (RS half) | `TokenVerifier` protocol: `async verify_token(token) -> AccessToken \| None` (`auth/provider.py:124`). `AccessToken(token, client_id, scopes, expires_at, resource, subject, claims)` (`:53-60`). `AuthSettings(issuer_url, resource_server_url, required_scopes, validate_token_resource, …)` (`auth/settings.py`). `get_access_token()` from `mcp.server.auth.middleware.auth_context` gives the token inside a tool. | read |
| 401 / WWW-Authenticate | `RequireAuthMiddleware` sends 401 `invalid_token` with `resource_metadata=` built by `build_resource_metadata_url(resource_server_url)` → `https://host/.well-known/oauth-protected-resource/<path>` (`auth/routes.py:201-216`, `lowlevel/server.py:801-812`). A missing *endpoint-level* required scope gets **403 `insufficient_scope`** (`bearer_auth.py:129`). | read |
| PRM (RFC 9728) | Published automatically when `resource_server_url` is set: `create_protected_resource_routes(resource_url, authorization_servers=[issuer_url], scopes_supported=auth.required_scopes)` (`lowlevel/server.py:823-830`). **Note:** `scopes_supported` is taken from `required_scopes`. | read |
| In-memory test client | `mcp.client.Client(server, …)` accepts an `MCPServer` directly (`client/client.py:262`, `_connect_inproc` `:103`) | `inspect.signature` |
| Resolver vs our pins | `fastapi==0.111.1, starlette==0.37.2, uvicorn==0.30.6, pydantic==2.13.5` + `mcp==2.2.0` → **ResolutionImpossible**. Same pins + `mcp<2` → resolves to **`mcp==1.12.4`**. With `uvicorn>=0.31.1` + `mcp==2.3.0` → resolves (exit 0). | `pip install --dry-run` in a scratch venv |

**Four mounting consequences, to design for in Phase 1:**

1. **The PRM route is in the wrong place if the sub-app is mounted.** `streamable_http_app()` returns a Starlette app whose PRM route path is `/.well-known/oauth-protected-resource/mcp`. If FastAPI mounts that app at `/mcp`, the PRM ends up at `/mcp/.well-known/…`, which is wrong. Two fixes:
   - Mount the Starlette app at the root via `app.mount("/", …)`. Not acceptable: it would shadow `GET /` (`main.py:383`).
   - **Proposed:** mount only the MCP endpoint, and register the PRM and AS metadata routes on the FastAPI app itself.
2. **The sub-app's lifespan does not run when mounted.** The returned Starlette app's lifespan is `session_manager.run()` (`lowlevel/server.py:840`), and FastAPI does not run a mounted sub-app's lifespan. **Proposed:** enter `server.session_manager.run()` inside `app/main.py:_lifespan`, so the MCP server shares the existing process, settings and `SessionLocal`.
3. **Per-tool step-up is not built in.** The SDK enforces `required_scopes` for the whole endpoint only.
   - Write tools need `leadpilot:write` per tool, answered with the spec's step-up 403 `insufficient_scope` and `scope="leadpilot:write"`.
   - Inside a stateless JSON-RPC exchange this needs a thin ASGI check that reads the `tools/call` name before dispatch.
   - The fallback is a tool-level error, which Claude will not treat as step-up.
   - Phase 2 design; flagged here because it decides whether "step-up 401/403" is fully met.
4. **`transport_security` (DNS-rebinding Host/Origin check) must be configured for the public host.** The SDK enables it for loopback hosts only.

---

## 4. Read capabilities: service functions and their gates

Gate legend:
- **Plan.** No read route applies a plan check today, and none will be added.
- **Spend cap.** Read paths make no AI calls. Every function listed is a DB read.
- **Outreach gate.** Not applicable to reads.
- **RBAC.** All GETs pass `rbac.enforce`.

So for reads the only gate that matters is **tenant scoping**, plus the suspension and verification checks in §2.1.

| Tool (proposed) | Service function today | Tenant scoping | Gap |
|---|---|---|---|
| `list_leads` | `crm_service.grid_page(db, current_user, *, strategy_id=None, filters=None, sort=None, search=None, tag_ids=None, limit=100, offset=0) -> dict` (`crm_service.py:962`) | `owned_leads_select(current_user, strategy_id)` (`:142`), `Product.user_id` | none. Clamp `limit ≤ 50` in the tool. The strategy-scoped list `GET /strategies/{id}/leads` is router-only (`app/api/leads.py:145-180`) and is not needed. |
| `get_lead` | `crm_service.owned_lead(db, lead_id, current_user) -> Lead` (`crm_service.py:92`, 404 if not owned) + `fpta_scoring.detail(lead) -> dict` (`fpta_scoring.py:506`) + `fpta_scoring.band` (`:482`) | `owned_lead` | `detail` is not scoped itself, so it is safe only after `owned_lead`. Research lives on the lead row (`enrichment_json`, `linkedin_posts_json`, `company_news_json`, `models.py:1142…`). F-P-T-A is stored as columns `fpta_fit/problem/timing/access/overall`, `fpta_reasons_json`, `fpta_method`, `fpta_scored_at` (`models.py:1291-1302`). |
| `list_strategies` | **none** (router-only, `app/api/ui_support.py:91-92`: inline `Product.user_id` join, **no pagination**) | inline | **extract** a service function `strategies_service.list_owned(db, user, *, limit, offset)` |
| `get_strategy` | **none** (router-only, `app/api/strategies.py:279-334` builds `StrategyStatusOut` inline). Campaign state is on `Strategy.campaign_state` (`"active" \| "paused_bounce_rate" \| "paused_manual"`). There is **no `Campaign` model**. | `_owned_strategy` (router) / `crm_service.owned_strategy` (`:111`) | **extract** the status builder |
| `get_pipeline_status` | **none.** There is no `PipelineRun` model. Status = `Strategy.status` + `ResearchStep` rows + `usage_meter.spent_micros` (`usage_meter.py:207`). It is built inline in the same handler as `get_strategy`. | as above | same extraction. Could fold into `get_strategy`; a separate tool is kept per the brief. |
| `list_messages` | **There is no account-wide list of scheduled or sent messages.** Replies: `inbox.threads(db, user_id, *, filter="needs_reply", channel=None, limit=50, offset=0)` (`app/services/inbox.py:138`, owned-lead scoped; paginates in Python after loading every owned reply). `GET /crm/replies` is router-only (`app/api/crm.py:1288`). | `inbox._owned_leads` (`:83`) | **extract** a scoped, SQL-paginated `messages.list_owned(...)` over `Message` (`models.py:1594`), filtered by `MessageStatus` (`:152`) |
| `get_message` | **none** for a single message. Per-lead: `conversation_thread.build_thread(session, lead, limit=500)` (`conversation_thread.py:60`, unscoped, so use after `owned_lead`). | via `owned_lead` | **extract** `messages.owned_message(db, message_id, user)` (Message → Lead → Strategy → Product) |
| `get_attribution_summary` | `attribution.summary(db, user_id, strategy_id=None)` (`attribution.py:379`); `attribution.ledger(db, user_id, *, outcome_kind=None, strategy_id=None, limit=100, offset=0)` (`:355`) | `AttributionEntry.user_id` | none. Note: `entry_out` (`:329`) includes the message `body`, which is untrusted. |
| `get_claim_verification` | `claim_verification.lead_log(session, lead_id, limit=100)` (`claim_verification.py:546`, **unscoped**); account summary is router-only (`app/api/claims.py:47`) | use after `owned_lead` | per-lead: none. Summary: extract it if wanted. |
| `search` (ChatGPT) | `grid_page(…, search=q)` (`ilike` on full_name/company/email/title, `crm_service.py:979-986`) | owned | none |
| `fetch` (ChatGPT) | `owned_lead` + `fpta_scoring.detail` + `attribution.for_lead` (`:371`, unscoped) + `lead_log` | owned | none, if `owned_lead` runs first |

**Extraction work for Phase 1** (behaviour-preserving; each router switches to the new function, and the existing route tests are the regression proof):
- strategy list
- strategy/pipeline status
- message list
- single owned message

**Untrusted free text** (it must sit in `untrusted_content` and never in the summary text):
- `Lead.full_name/title/company` (provider data)
- `enrichment_json`, `linkedin_posts_json[].text`, `company_news_json[]`
- `ai_score_reason` and `fpta_reasons_json`. Signals quote scraped text verbatim, e.g. `fpta_scoring.py:199,236,248`.
- `InboundReply.body/subject/from_address`
- `ai_draft_response`, `intent_reason`
- `Message.subject/body`
- `AttributionEntry.subject_snapshot/body_snapshot`
- `ClaimVerificationLog.claim_text/evidence_excerpt`

Existing containment helper: `app/services/prompt_safety.py` (`OPEN="<<<EXTERNAL_TEXT"`, `escape()`, `block()` `:50`, `inline()` `:55`, `NOTICE`). Proposal: put lead text in a separate `untrusted_content` object **and** escape it with `prompt_safety.escape`, so the existing delimiter scheme cannot be closed early.

---

## 5. Write capabilities: functions and gates

| Write | Service function? | Plan | Spend cap | Send gate | Audit | RBAC |
|---|---|---|---|---|---|---|
| **create_strategy** | **No.** `app/api/strategies.py:141-208` does everything inline: rate limit `:159`, ownership `:161-163`, autopilot opt-in `:169`, `check_new_strategy_allowed` (`:234`, which calls `check_plan_limit(…,"max_strategies",…)` at `:249`), `plan_budget` `:194`, `spend_guard_api.guard_new_strategy` `:196`, commit, then `run_pipeline.delay` `:207` | yes (402 `{"detail": plan_limit_response}`) | yes: up-front daily 429 (`:127,252`), monthly forecast 429, and per call in the worker (`usage_meter.check_budget`, `usage_meter.py:299`) | n/a | **none** | global only |
| **pause_campaign** | **No.** `app/api/analytics.py:143-164` sets `campaign_state="paused_manual"` inline | n/a | n/a | takes effect at dispatch (`outreach_tasks.py:120`) and send (`:202`) | **none** | global only |
| **resume_campaign** | **No.** `analytics.py:167-185`; calls service `deliverability_autopilot.launch_block(…, action="resume")` (409) then sets active inline | not checked at resume; re-checked per message by `plan_holds.check` (`outreach_tasks.py:394`) | n/a | yes, at send | **none** | global only |
| **approve_message**, review queue | **Yes:** `send_review.approve(db, review, *, actor_user_id=None, note=None, subject=None, body=None, now=None)` (`app/services/send_review.py:350`) moves the message from `AWAITING_REVIEW` to `SCHEDULED` with `scheduled_at=now` | n/a | n/a | yes, at send | **none** | global only (an SDR can approve) |
| approve, daily send approval | Yes: `daily_send_approval.approve(db, user_id, *, actor_id, channels, linkedin_risk_acknowledged=False, …)` (`daily_send_approval.py:559`) **releases every deferred message** | n/a | n/a | yes | ComplianceAuditLog | manager, in router (`send_approval.py:52`); API keys refused (`:66`) |
| approve, Reply Copilot draft | Yes: `reply_copilot.approve(session, draft, *, actor, …)` (`reply_copilot.py:1006`). Runs a **synchronous AI** claim check, then enqueues a send. | n/a | yes (`reply_copilot` purpose is capped) | yes | none | global only |
| schedule a send | `sequence_engine.enroll_leads` (`:289`) via routers `sequences.py:421,549` | `check_plan_quantity` + `check_send_channel` (402) | "launch" is counted, not capped | yes, at send | `launch_consent.record` | SDR → pending approval; approve needs manager |

`check_plan_limit` (`app/core/plans.py:225`) raises `PlanLimitExceeded` (`:212`), a bare `Exception` with no global handler. Every caller maps it to `HTTPException(402, plan_limit_response(exc))` (`:338`). The "same error as the HTTP route" test in Phase 3 will therefore compare against the `plan_limit_response` dict.

**Paths that bypass gates (none will be exposed):**
- `POST /debug/schedule-send` (`app/api/debug.py:307`) inserts a SCHEDULED Message directly. It is debug-only and mounted only when `debug_routes_allowed`.

---

## 6. What Phase 1 will build (for review, not yet started)

- **Dependency:** pin `mcp` in `requirements.txt` / `pyproject.toml` / `requirements.lock` and raise uvicorn (Q5). Before any tool code, a spike PR proves `MCPServer` serves on starlette 0.37.2 under the full offline suite.
- **`app/mcp/`:**
  - `server.py`: factory, `MCPServer(..., token_verifier=…, auth=AuthSettings(...))`, `stateless_http=True`, `json_response=True`
  - `auth.py`: TokenVerifier → `User` via the shared `check_principal`
  - `tools/leads.py`, `tools/strategies.py`, `tools/messages.py`, `tools/insights.py`, `tools/chatgpt.py`
  - `schemas.py`, with the `untrusted_content` envelope
- **Mounting:** the MCP endpoint is mounted on the existing app; PRM and AS metadata routes are registered on FastAPI; the session manager runs in `_lifespan`.
- **Database:** one `SessionLocal()` per tool call, closed in `finally`.
- **Principal:** the owner `User` exactly as `get_current_user` returns it.
- **Tests:** `tests/mcp/` using `mcp.client.Client(server)` in-memory with SQLite, offline. Every tool gets five cases: valid, invalid, cross-tenant (empty / not found), suspended (refused), and a pagination boundary.
- **Service extractions** listed in §4.

Phase 1 cannot ship to production on its own: without the AS (Phase 2) no client can obtain a token. Its tests use a verifier fed by test-issued tokens.

---

## 7. What these recon claims rest on

- Every file:line above comes from reading this checkout. No production system was contacted.
- The dependency-resolution results come from `pip install --dry-run` against PyPI in a scratch venv. They say nothing about runtime compatibility.
- Nothing in this phase ran against PostgreSQL. The project's own dependencies are **not installed** in this container (`pip show fastapi` → nothing), so no test was run in Phase 0.

## 8. Out-of-scope discoveries (reported, not fixed)

| # | Finding | Where |
|---|---|---|
| OOS-1 | `send_review.gate` **fails open**: on an internal error it returns `"send"`. Documented in its docstring, but it is a human-review gate on a zero-tolerance compliance product. | `app/services/send_review.py:309-316` |
| OOS-2 | Review-queue approval records the workspace **owner** as the decider, not the signed-in actor (`actor_user_id=current_user.id`). | `app/api/send_reviews.py:95` |
| OOS-3 | `fpta_scoring._model_pass` puts prospect lines and signal excerpts into a model prompt without `prompt_safety` wrapping. | `app/services/fpta_scoring.py:341` |
| OOS-4 | `message_personalization.render_whatsapp_variables` passes `title`, `company` and `str(enrichment_json)[:1500]` unwrapped; follow-up and re-engagement briefs pass title and company unwrapped. | `app/services/message_personalization.py:271-277`, around `:423`, `:513` |
| OOS-5 | `validation_exception_handler` is defined but never registered; the `HTTPException` branch of `global_exception_handler` is unreachable for route-raised HTTPExceptions (inferred, not tested). | `app/core/errors.py:32-37,91`; `app/main.py:215-218` |
| OOS-6 | Reply Copilot approve can raise `AccountBudgetExceededError` in-request without `metered()`, and may surface as a 500 (not verified). | `app/services/reply_copilot.py:953` |
| OOS-7 | `resume_strategy` / `reverify_strategy` re-enqueue AI work with spend checks but no plan check. | `app/api/strategies.py:337,397` |

---

## 9. Questions for the founder (answer before Phase 1 code)

**Q1 — Authorization server.** **Recommend: a minimal OAuth 2.1 AS inside FastAPI, reusing `auth_sessions`, with login and consent on a new Next.js page.**
- The session model supports rotation (§2.2). Its three gaps (client/scope columns, `invalid_grant` instead of the 30 s access-only grace, an audience-bound `mcp_access` token type) are additive.
- There is no server-rendered login (§0.4), so the consent screen must be built either way. The proposed flow:
  1. `/oauth/authorize` validates the client, redirect and PKCE, then redirects to `FRONTEND_URL/oauth/consent?request=<opaque id>`. The request id is a server-side record, so no token or code goes in the URL.
  2. The page uses the existing login and shows the redirect host and scopes.
  3. On approval it POSTs back to the API, which issues the code.
- Alternative: a self-contained HTML login + consent page served by the API. One less moving part, but a second password form on a second origin needs its own CSRF and rate limiting.
- External IdP (Auth0, WorkOS): not recommended. It means a second user directory, account linking, and a monthly bill.

**Q2 — v1 write tools.** **Recommend: `create_strategy`, `pause_campaign`, `resume_campaign`. Leave `approve_message` out of v1.**
- In this codebase, "approve" releases a specific message for sending: `send_review.approve` sets `scheduled_at=now` (§5). That contradicts "nothing is sent or scheduled from Claude in v1".
- There are also three different approve paths, and the review-queue one has no manager check.
- `resume_campaign` re-enables already-approved automation. Every send still passes daily approval and the full send gate, but tell me if you want it excluded too.
- `create_strategy` starts a paid AI pipeline, up to the strategy budget ($0.50–$50, default $15). It stays behind the existing plan, daily and monthly checks and is marked destructive.

**Q3 — Public MCP hostname.** **Need the exact URL**, e.g. `https://api.calendarharvest.com/mcp`.
- `PUBLIC_BASE_URL` is `sync: false` in `render.yaml:100-101`, so the real production API host is not in the repo.
- `.env.production.example:110` has the placeholder `https://api.leadpilot.com`.
- PRM `resource` must equal this string exactly. Also confirm the AS issuer: recommend the same origin, `https://<api host>`.

**Q4 — Service extraction (new, from recon).** **Recommend: yes.** Approve moving the router-only logic into `app/services/` before exposing it as tools:
- strategy list
- strategy/pipeline status
- message list and single message
- in Phase 3, `create_strategy` and pause/resume, with every inline plan, spend and autopilot check moved verbatim

The routers then call the same functions, so REST and MCP share one gated path. The existing route tests are the regression proof. This widens Phases 1 and 3 beyond "thin wrappers", which is why I'm asking.

**Q5 — Dependency change (new).** **Recommend: pin `mcp==2.3.0` and raise uvicorn to `>=0.31.1,<0.32` in `requirements.txt`, `pyproject.toml` and the lock, as a first spike PR that must pass the full offline suite and the PostgreSQL integration suite before any connector code.**
- The alternative, `mcp==1.12.4` (fits today's pins), lacks `TokenVerifier` and the 2026-07-28 stateless wire.
- The uvicorn bump affects the production server process, so it needs your OK.

**Q6 — Workspaces and roles (new).** **Recommend for v1: the token belongs to the signed-in user's own account only, with no workspace selection.**
- Members acting inside someone else's workspace keep using the web app until v2. The path-based `rbac.enforce` has no meaning for tool calls, and inventing a tool→role map is a policy decision, not a technical one.
- If you want workspace support in v1: workspace chosen at consent, then read tools for every role, and write tools for owner/manager only.

**Q7 — Audit location (new, a default unless you object).** Every write tool writes one `security_audit_events` row (`action="mcp.<tool>"`, `details={"actor_channel":"mcp","oauth_client_id":…}`). The hash-chained `activity_audit_events` trail is unchanged (§0.6).
