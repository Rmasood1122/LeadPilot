# LeadPilot connector for Claude and ChatGPT (remote MCP server)

Status: **Phase 1 — read-only server.** Off by default (`MCP_ENABLED=false`)
until the OAuth authorization server (Phase 2) ships. Decisions:
`docs/program/DECISIONS.md` CONN-AS, CONN-WRITES, CONN-HOST, CONN-SERVICES,
CONN-DEPS, CONN-WORKSPACE, CONN-AUDIT. Recon: `docs/program/plans/connector-00-recon.md`.

## What it is

A remote [MCP](https://modelcontextprotocol.io) server served by the LeadPilot
API at **`https://api.calendarharvest.com/mcp`**. Claude (claude.ai, Desktop,
mobile, Cowork, Claude Code) and ChatGPT connect to it from their own servers
over HTTPS and act in the signed-in user's account. A Skill
(`.claude/skills/leadpilot-outbound/`, Phase 4) only teaches Claude when and
how to use these tools; the server is what reaches the data.

## Behaviour (Phase 1)

| | |
|---|---|
| Transport | Streamable HTTP, **stateless**: no session map, no `Mcp-Session-Id`; JSON responses. Serves MCP protocol revisions up to 2026-07-28 (mcp 2.3.0). |
| Where it runs | Inside the API process (`app/main.py` lifespan + routes, `app/mcp/server.py`); same settings and DB session factory as the REST API. |
| Off switch | `MCP_ENABLED=false` (default) → `/mcp` and its metadata answer 404. |
| Unauthenticated | 401 with `WWW-Authenticate: Bearer error="invalid_token", ..., resource_metadata="https://<host>/.well-known/oauth-protected-resource/mcp"`. |
| Metadata | `GET /.well-known/oauth-protected-resource/mcp` (RFC 9728): `resource` = the MCP URL exactly, `authorization_servers` = [the API origin], `scopes_supported` = `leadpilot:read`, `leadpilot:write`, `offline_access`. |
| Tokens accepted | Only connector access tokens: JWT `typ="mcp_access"`, `aud` = the MCP URL, scope `leadpilot:read` at least. A web session token, a refresh token and a personal API key (`lpk_…`) are refused (401). A connector token is refused by the REST API (401). |
| Account checks | The same as every REST route (`auth.check_account_usable`): erased → refused, suspended → refused, unverified email → refused; a token issued before a password change → refused. At the HTTP layer these are 401; inside a tool call, an error naming the reason. |
| Whose data | The signed-in user's own account only (CONN-WORKSPACE); no workspace switching. |
| Host check | DNS-rebinding protection: only the MCP URL's host (plus `MCP_ALLOWED_HOSTS`) is served; others get 421. |

### Tools (all `readOnlyHint: true`, all tenant-scoped)

| Tool | What it returns | Service it reads through |
|---|---|---|
| `list_leads` | leads with status and F-P-T-A; filters `strategy_id`, `status`, `min_fpta`, `search`; sort `fpta` / `booking_likelihood` / `newest` | `crm_service.grid_page` |
| `get_lead` | one lead: F-P-T-A sub-scores, band, method; score reasons and signals, LinkedIn posts (≤5), company news (≤5), enrichment (≤4,000 chars) | `crm_service.owned_lead`, `fpta_scoring.detail` |
| `list_strategies` | strategies, newest first, with status and campaign state | `strategy_read.list_owned` |
| `get_strategy` | one strategy: product, status, campaign state, budget/spend, documents ready | `crm_service.owned_strategy`, `strategy_read.pipeline_status` |
| `get_pipeline_status` | steps done per pipeline and phase, verification passes, error | `strategy_read.pipeline_status` |
| `list_messages` | outreach messages without their text; filters `status`, `channel`, `strategy_id`, `lead_id` | `message_read.list_owned` |
| `get_message` | one message with subject and body | `message_read.owned_message` |
| `get_attribution_summary` | outcomes by step / channel / method, certain vs inferred, median hours, recent outcomes (0–20) | `attribution.summary`, `attribution.ledger` |
| `get_claim_verification` | a lead's claim-verification log (verdict counts and rows) | `claim_verification.lead_log` after `owned_lead` |
| `search` | ChatGPT shape: `{results: [{id, title, url}]}`, ≤10 leads | `crm_service.grid_page(search=…)` |
| `fetch` | ChatGPT shape: `{id, title, text, url, metadata}` for `lead:<uuid>` | as `get_lead` |

Every list has `limit` 1–50 (default 20) and `offset`, and returns `total` and
`has_more`. Invalid input returns an error that names the argument and what
is expected; another account's id returns "… not found" (never "forbidden").

### Untrusted content

Prospect and third-party text (names, titles, companies, emails, scraped
posts, news, enrichment, F-P-T-A reasons, message bodies, attribution
snapshots, claim text) appears **only** under an `untrusted_content` key, with
the `<<<EXTERNAL_TEXT` / `EXTERNAL_TEXT>>>` delimiters of
`app/services/prompt_safety.py` escaped inside it. The `summary` and every
other field are built from ids, enums, numbers and timestamps. `fetch` puts
the third-party text in one delimited block after a notice.

## Not in Phase 1

- Obtaining a token: the OAuth 2.1 authorization server (DCR, PKCE S256,
  consent page, refresh rotation) is Phase 2. Until then the endpoint stays
  off in production.
- Write tools (`create_strategy`, `pause_campaign`, `resume_campaign`) are
  Phase 3; nothing sends or schedules outreach from a connector in v1.

## Code

`app/mcp/` (server, auth, context, untrusted, scopes, tools/),
`app/services/strategy_read.py` and `app/services/message_read.py` (moved
out of `app/api/ui_support.py` and `app/api/strategies.py`, which now call
them), `app/services/auth.py` (`check_account_usable`, `issue_mcp_access_token`,
`decode_mcp_access_token`), `app/config.py` (`MCP_*` settings).
Tests: `tests/mcp/`.

## Settings

| Variable | Default | Meaning |
|---|---|---|
| `MCP_ENABLED` | `false` | Serve `/mcp` and its metadata. |
| `MCP_RESOURCE_URL` | `PUBLIC_BASE_URL` + `/mcp` | The MCP URL exactly as users type it. Production: `https://api.calendarharvest.com/mcp`. |
| `MCP_ACCESS_TTL_SECONDS` | `3600` | Connector access-token lifetime. |
| `MCP_ALLOWED_HOSTS` | empty | Extra Host headers to serve (e.g. `localhost:8000` for MCP Inspector). |
| `MCP_ALLOWED_ORIGINS` | empty | Origin headers to accept (requests without one always pass). |
