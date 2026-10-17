# Connector Phase 5: verification and handover

Date: 2026-10-17. Covers PRs 1/5 – 5/5 (#105, #106, #107 and the two that
follow). Decisions: `DECISIONS.md` CONN-AS, CONN-WRITES, CONN-HOST,
CONN-SERVICES, CONN-DEPS, CONN-WORKSPACE, CONN-AUDIT. Spec:
`docs/features/mcp-connector.md`. User guide: `docs/connectors/README.md`.

Each section says what was run, on what, and the result. "SQLite" =
the offline suite (in-memory SQLite, FakeClaude, eager Celery). "PostgreSQL" =
a real PostgreSQL 16 server in the cloud container (local) or in CI.

## 1. Offline gate on the final code (all four phases)

Run in a clean worktree at the final tree (`db1105b`, the Phase 4 commit),
CPython 3.13, the pinned dependencies (`mcp==2.3.0`, `uvicorn==0.31.1`).

| Command | Exit | Result |
|---|---|---|
| `registry_lint.py evals/registry.yaml` | 0 | OK |
| `run_evals.py` | 0 | 6,110 tests, compliance 1.000, full 1.000 (baseline 5,981: +129 connector tests) |
| `promote.py` | 0 | PROMOTE; 1 soft warning: `suite_runtime_s` 2,057 s against a 900 s band — the container ran other jobs at the same time; CI's `gate` job is the timing reference |
| `verify_block_fixtures.py` | 0 | all 3 hard gates proven to fire; a healthy run promotes |

The new tests are picked up by `run_evals.py` on their own; the count is a
floor (`offline_test_count`), so no baseline change was needed (GATES.md).

## 2. PostgreSQL

| What | Where | Result |
|---|---|---|
| `alembic upgrade head`, `downgrade -1`, `upgrade head` (0091) | local PostgreSQL 16 | exit 0 each; `\d oauth_authorization_codes` and `auth_sessions` match the model |
| `tests/integration` (whole suite, incl. `test_mcp_connector_pg.py`) | local PostgreSQL 16 + Redis 7 | **151 passed** in 481 s |
| `verify-backend-postgres` | CI, per PR | green on #105, #106 (PR 3/5 onwards: see the PR) |
| `verify-image` (image builds and every module imports) | CI | green on #105, #106 |

`test_mcp_connector_pg.py` drives the real app (lifespan, OAuth endpoints,
MCP endpoint) on PostgreSQL: DCR → authorize → consent → code → token →
tools (`list_leads`, `get_lead`, cross-tenant `get_lead` and
`pause_campaign` refused, `pause_campaign`, `create_strategy`) → audit rows →
refresh → rotated-token reuse → `invalid_grant` and both access tokens 401;
and a code redeemed twice.

Claims that rest on SQLite only: the per-tool unit behaviour in
`tests/mcp/` (130 tests) — the same paths are exercised on PostgreSQL by the
integration test above, but not every edge case is.

## 3. A running server, MCP Inspector, real OAuth

Local `uvicorn app.main:app` against the migrated PostgreSQL database,
`MCP_ENABLED=true`, `MCP_RESOURCE_URL=http://localhost:8000/mcp`.

- `GET /.well-known/oauth-protected-resource/mcp` → 200, `resource` =
  `http://localhost:8000/mcp`, `authorization_servers` = `["http://localhost:8000"]`.
- `GET /.well-known/oauth-authorization-server` → 200, `issuer` byte-identical,
  `code_challenge_methods_supported: ["S256"]`, iss parameter supported.
- `POST /mcp` without a token → 401 `Bearer error="invalid_token", …,
  resource_metadata="http://localhost:8000/.well-known/oauth-protected-resource/mcp"`.
- Real flow over HTTP: password login (`/auth/login`) → DCR → authorize (302
  to `/oauth/consent/`) → consent API → redirect carrying `code`, `state`,
  `iss` → token (refresh token, `Cache-Control: no-store`).
- **MCP Inspector 2.11.0 CLI**, `tools/list --strict` in both protocol eras
  (`legacy`, `auto`): 15 tools, each with a title; 12 `readOnlyHint: true`,
  3 `destructiveHint: true`; no schema portability problems reported.
- Inspector `tools/call` for every tool: all valid calls succeed; another
  account's lead / strategy → "not found"; `create_strategy` with $2 →
  the web app's 422 text ("needs at least $2.66"); with $5 → created;
  `limit=51` → validation message.
- A read-only token calling `pause_campaign` → 403 `Bearer
  error="insufficient_scope", scope="leadpilot:read leadpilot:write",
  resource_metadata="…"`; the same token on a read tool → 200.
- `security_audit_events` after the run: `oauth.consent_granted`, then
  `mcp.pause_campaign` paused, `mcp.resume_campaign` resumed,
  `mcp.pause_campaign` refused_404, `mcp.create_strategy` refused_422 and
  created — each with `actor_channel: "mcp"` and the client id.
- Server log (298 lines): no access token, refresh token, code or verifier
  (`grep -c eyJ` = 0; `bearer|code=|refresh_token|code_verifier` = 0).

## 4. Frontend

`tsc --noEmit` clean; `npm run lint` only pre-existing warnings; vitest
`oauthConsent.test.ts` + `post-login.test.ts` 14 passed; `next build`
(static export) emits `/oauth/consent`. The consent page itself was not
clicked through in a browser (§6).

## 5. Mutation checks (each guard removed → a test fails)

PKCE compare; rotated-refresh reuse revocation; token-endpoint
`redirect_uri` match; redirect-URI allowlist; family liveness (the test for
rotated sessions was added after this mutation first survived); message
tenant filter; untrusted-content escaping; plan check in `create_strategy`;
HTTP scope challenge; tool-level scope check.

## 6. Not verified — needs the public host or a person

- **The claude.ai custom-connector handshake** (Anthropic's cloud,
  egress `160.79.104.0/21`, reaching `https://api.calendarharvest.com/mcp`)
  and **ChatGPT Developer Mode**: impossible without the production host
  live with `MCP_ENABLED=true`. Steps: `docs/features/mcp-connector.md`,
  "Turning it on"; then `docs/connectors/README.md`.
- **The consent page in a real browser** (sign-in redirect and return,
  Allow / Decline) — covered by unit tests and the API flow, not clicked.
- **Claude Code** OAuth through a loopback port — redirect matching is
  unit-tested; the CLI flow itself was not run here.
- **Known client-side issues to watch for**, from Anthropic's issue
  tracker: (a) a custom connector whose tools are discovered but never
  offered to the model; (b) refresh tokens never refreshed through
  Anthropic's proxy (the connection then fails after the access token's
  hour). If either happens: capture the API's access log lines for
  `/mcp`, `/oauth/token` and the metadata URLs for that window (they carry
  no tokens) and the `security_audit_events` rows, and report them. Do
  **not** lengthen the access-token lifetime or relax any check to work
  around it.

## 7. Follow-ups (reported, not done)

| # | Item | Why not here |
|---|---|---|
| F1 | **Seal the connector guard tests** (`tests/mcp/test_read_tools.py` cross-tenant + untrusted-content, `tests/mcp/test_oauth_flow.py`, `tests/mcp/test_write_tools.py`) in `evals/compliance_testset.yaml`. CLAUDE.md asks for that in the same commit as the tests; the sealed file can only be edited on a `gate/` or `claude/gate-` branch (`.claude/hooks/protect_sealed.py`), and this session may push to one branch only. | Needs a founder-approved `claude/gate-…` branch and its own PR. |
| F2 | A "connected apps" page (list and revoke connector sessions). | Not in the brief; today a password change ends every connection. |
| F3 | CIMD client registration (`client_id_metadata_document_supported`), which OpenAI and Anthropic prefer at scale. | Needs a safe fetch of the client's metadata URL through the SSRF guard; v1 is DCR. |
| F4 | Expired `oauth_clients` / unused registrations are never cleaned up. | Clients must stay valid while a connection uses them (OpenAI's guidance); needs a usage-based policy. |
| F5 | `.claude/hooks/require_gate.py` resolves the stamp path wrongly when the shell's cwd is a subdirectory (it joins a relative `--git-common-dir` to the top level). | Gate infrastructure is sealed. |
| F6 | Recon OOS-1 … OOS-7 (`connector-00-recon.md` §8): `send_review.gate` fails open; review approvals record the owner, not the actor; unwrapped prompt input in `fpta_scoring._model_pass` and WhatsApp variables; unregistered validation handler; Reply Copilot 500 on a spend refusal (unverified); no plan check on strategy resume/reverify. | Out of scope; for triage. |
