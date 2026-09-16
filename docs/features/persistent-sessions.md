# Persistent sign-in, plan-based routing, password-confirmed strategy deletion

Migration: `0052_auth_sessions` (tables `auth_sessions`, `security_audit_events`).

## 1. Persistent sign-in ("Keep me signed in")

| | Web app | Native app, SDK, CLI |
|---|---|---|
| Access token (15 min) | `sessionStorage` + memory | Capacitor Preferences + memory |
| Refresh token | **HttpOnly cookie** (`lp_refresh`), never visible to script | Request/response body, as before |
| How the client opts in | `X-Auth-Transport: cookie` header + `credentials: "include"` on `/auth/*` | nothing (default) |

- **Lifetime.** 30-day sliding window (`JWT_REFRESH_TTL_SECONDS`). Every refresh rotates the token and restarts the window, so an account in regular use is not asked to sign in again. Unticking "Keep me signed in" issues a browser-session cookie backed by a 12-hour server session (`AUTH_EPHEMERAL_SESSION_TTL_SECONDS`).
- **Silent restore.** On app load, `restoreSession()` (`frontend/src/lib/api/client.ts`) calls `POST /auth/refresh` when the tab has no access token. The login page, the root page, the Shell, the pricing page, the theme provider and `authStore` all go through it. Concurrent callers share one request.
- **Background refresh.** A timer refreshes 60 s before the access token expires. A 401 still triggers one refresh-and-retry as a backstop. Only a 401 from `/auth/refresh` ends the session; network errors and 5xx do not.
- **Rotation and reuse detection.** Each refresh token names an `auth_sessions` row (`jti`). Using it marks the row `rotated`. A rotated token presented again after `AUTH_REFRESH_REUSE_GRACE_SECONDS` (30 s) revokes the whole session family and writes `auth.refresh_reuse_detected` to the security audit log. Inside the grace window (two tabs refreshing at once) the late caller gets an access token only.
- **Logout.** `POST /auth/logout` revokes the family and clears the cookie. The client clears local state even if the call fails.
- **CSRF.** The cookie is read only when `X-Auth-Transport: cookie` is present. A cross-site page cannot send that header past CORS. The cookie path is scoped to `/auth`.
- **Deploying.** Refresh tokens issued before 0052 carry no `jti` and are exchanged for a tracked session on first use. Set `AUTH_ACCEPT_LEGACY_REFRESH_TOKENS=false` 30 days after deploying.

Cookie settings (all optional): `AUTH_REFRESH_COOKIE_PATH` (use `/api/v1/auth` behind a path-prefix proxy), `AUTH_REFRESH_COOKIE_DOMAIN`, `AUTH_REFRESH_COOKIE_SAMESITE` (`lax` default; `none` if the frontend and API are on different *sites*, which forces `Secure`), `AUTH_REFRESH_COOKIE_SECURE` (default: on in production).

## 2. Post-login routing by plan

Every `/auth/login`, `/auth/signup`, `/auth/refresh` and `/auth/me` response now carries `user.has_active_plan` and `user.subscription_status`, recomputed from the database each time (`billing.plan_access`). A plan counts as active when any of these holds:

- the subscription is `trialing`, `active` or `past_due`;
- `users.plan` is not `free`;
- the user is an admin;
- the user is a member of a workspace whose owner has a plan.

`frontend/src/lib/post-login.ts::postLoginDestination` picks the route, checked in this order:

1. Email not verified: `/check-email`
2. Identity or phone not verified: `/onboarding/verify`
3. No plan: `/pricing` — **only straight after an explicit sign-in** (`afterLogin: true`)
4. Otherwise: `/pipeline`

The plan check does not run on a silent session restore or on navigation, and nothing sends a no-plan user back to `/pricing` later in the session; they can open it themselves.

## 3. Deleting a strategy

`DELETE /strategies/{id}` with body `{"password": "..."}`.

- The password checked is the **signed-in person's** (a workspace manager uses their own, not the owner's). SDRs and viewers are refused by RBAC.
- Wrong password: `403 INVALID_PASSWORD`, nothing deleted, `strategy.delete_denied` audited. Missing password: `422`. Another account's strategy: `404`. A campaign still sending: `409` (pause it first).
- Attempts share `RATE_LIMIT_AUTH` / 15 min with a bucket separate from login.
- Success: `strategy.deleted` is audited (actor, owner, strategy id, IP, user agent, timestamp) in the same transaction as the delete. Children go through the schema's `ON DELETE CASCADE`. The tamper-evident activity trail is kept by design.
- UI: the **Delete** button on the strategy detail page opens `DeleteStrategyDialog`, which shows a success toast on completion.
