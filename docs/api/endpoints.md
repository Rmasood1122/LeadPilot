# API Endpoints

Live, always-current reference: **`/docs`** (Swagger) and **`/openapi.json`**
on the running service. This file documents the auth surface in detail and
indexes the rest.

Base URL: `PUBLIC_BASE_URL` (production) / `http://localhost:8000` (dev).

---

## Authentication model

- **Bearer JWT**, HS256. `Authorization: Bearer <access_token>`.
- Access tokens live 15 minutes; refresh tokens 14 days.
- A `typ` claim separates the two — a refresh token never works as an access
  token, or vice versa.
- Every authenticated route resolves its user through **one** dependency,
  `app/services/auth.py::get_current_user`.

### Failure codes shared by every authenticated route

| Code | `detail` | Meaning | What the client should do |
|---|---|---|---|
| 401 | `missing bearer token` | No `Authorization` header | Send to `/login` |
| 401 | `token expired` | Access token past `exp` | Refresh, then retry once |
| 401 | `invalid token` | Signature/format bad | Clear session, `/login` |
| 401 | `not a access token` | A refresh token was sent as an access token | Clear session |
| 401 | `user not found` | Token valid, row gone | Clear session |
| **403** | **`EMAIL_NOT_VERIFIED`** | **Credentials are valid; the address is unverified** | **Send to `/check-email`. Do NOT refresh and do NOT log out.** |
| 403 | `admin privileges required` | Non-admin on `/admin/*` | |
| 403 | `account suspended` | Suspended admin | |
| 429 | *(object)* | Rate limited; `Retry-After` header set | Back off |

> `EMAIL_NOT_VERIFIED` is deliberately a **403, not a 401**. A 401 would send
> `frontend/src/lib/api/client.ts` into its refresh-then-retry path, which
> succeeds at refreshing, retries, gets 401 again, and finally clears the
> session — logging out a user whose only problem is an unread email.
> The string is a **contract**; `frontend/src/lib/api/auth.ts` matches on it.

---

## Auth

### `POST /auth/signup` → `201`

Creates an account (or claims a pre-auth row that has no password yet) and
emails a verification link.

Rate limited per IP (`RATE_LIMIT_AUTH`, 15-min window). The limiter runs
*after* body validation, so a malformed payload costs nothing.

```jsonc
// request
{ "email": "user@example.com", "password": "at least 8 chars" }
```
```jsonc
// 201
{
  "user": { "id": "uuid", "email": "user@example.com", "plan": "free",
            "is_admin": false, "email_verified": false },
  "access_token": "eyJ…", "refresh_token": "eyJ…",
  "token_type": "bearer", "expires_in": 900,
  "email_verification_required": true,
  "verification_email_sent": true
}
```

| Field | Meaning |
|---|---|
| `email_verification_required` | Always `true`. The tokens are real but every authenticated route will answer 403 until the link is clicked. |
| `verification_email_sent` | `false` when the account was created but the mail transport failed. **The account still exists** — show "resend", not "check your inbox". |

Errors: `409 account already exists` · `422` (password < 8 chars, bad email) ·
`429`.

> Signup deliberately does **not** fail when the mail transport is down.
> Returning a 500 would destroy an account the user just created: the address
> is taken, the password is lost, and the signup is unrepeatable.

---

### `POST /auth/login` → `200`

Two independent limits, both governed by `RATE_LIMIT_AUTH`: per IP (one host
brute-forcing) and per account (credential stuffing spread across many IPs).

```jsonc
{ "email": "user@example.com", "password": "…" }
```
Returns the same `user` + token bundle as signup (without the two verification
fields).

**Login succeeds for an unverified account** — otherwise there is no session
from which to request a new link. The client must branch on
`user.email_verified` and route to `/check-email` when it is `false`.

Errors: `401 invalid email or password` (one message for both wrong-password
and unknown-account — no account enumeration) · `429`.

---

### `GET /auth/verify?token=<token>` → `302`

The target of the link in the verification email. **Unauthenticated** — it is
clicked from an inbox, often in a browser with no session.

Always redirects; never renders. `302`, not 307: a GET answered with a GET is
what every mail client and link scanner handles predictably.

| Outcome | `Location` |
|---|---|
| Verified now | `{FRONTEND_URL}/login?verified=true` |
| Was already verified | `{FRONTEND_URL}/login?verified=already` |
| Expired, or superseded by a resend | `{FRONTEND_URL}/login?error=expired` |
| Unknown / missing / malformed token | `{FRONTEND_URL}/login?error=invalid` |

Not rate limited: the token is 43 URL-safe characters of `os.urandom` inside a
24-hour window, so there is nothing to brute force, and an IP-keyed limiter
would punish the shared corporate NAT of exactly the customer we want.

Single use — `used_at` is stamped on the first success, so a forwarded email or
a mail-scanner prefetch cannot re-verify an account.

---

### `POST /auth/resend-verification` → `202`

```jsonc
// request
{ "email": "user@example.com" }
// 202 — ALWAYS this body, whatever the address
{ "status": "accepted",
  "detail": "If that address has an unverified account, a verification email has been sent." }
```

**Always 202**, identical body, for every syntactically valid address.
Reporting "no such account" would hand anyone an account-existence oracle for
any address they cared to try — and `/auth/login` goes to the trouble of
avoiding exactly that.

Mail is actually sent only when the address has an account, that account has a
password, and it is not already verified.

Issuing a new link **invalidates every outstanding one** for that user.

Rate limited on both `ip:` and `acct:` keys — otherwise this is a free
mail-bomb aimed at any address you name.

Errors: `422` (not an email address) · `429`.

---

### `POST /auth/refresh` → `200`

```jsonc
{ "refresh_token": "eyJ…" }
```
Returns a fresh token pair. **Not** rate limited: a legitimate client hits it
every 15 minutes, and guessing a signed refresh token is not a brute-forceable
attack.

Not gated on verification — it resolves the user directly, not through
`get_current_user`.

Errors: `401 not a refresh token` · `401 token expired` · `401 user not found`.

---

### `GET /auth/me` → `200` 🔒

```jsonc
{ "id": "uuid", "email": "user@example.com", "plan": "free",
  "is_admin": false, "email_verified": true }
```
The cheapest request that goes through `get_current_user`, which makes it the
canonical probe for "is this session usable?". `Shell.tsx` calls it once before
rendering the dashboard.

---

## Theme 🔒

| Endpoint | Notes |
|---|---|
| `GET /me/theme` | `{ "theme": {…} }` |
| `PUT /me/theme` | Validates `#rrggbb`; persists `contrast_warnings` so the user was demonstrably informed |
| `POST /me/theme/background` | multipart; png/jpeg/webp; ≤5 MB; returns a `/media/*` URL |

## Other routers

All 🔒 routes are subject to the `EMAIL_NOT_VERIFIED` gate.

| Prefix | Router | Auth |
|---|---|---|
| `/health` | `app/api/health.py` | public |
| `/plans` | `app/api/strategies_advanced.py` | public |
| `/unsubscribe` | `app/api/unsubscribe.py` | public (token in URL) |
| `/webhooks/calendly`, `/webhooks/whatsapp` | `webhooks.py`, `webhooks_whatsapp.py` | signature-verified |
| `/products`, `/strategies`, `/leads`, `/sequences`, `/analytics`, `/integrations`, `/onboarding`, `/devices`, `/webhooks/targets`, `/whatsapp/*` | respective modules | 🔒 |
| `/admin/*`, `/playbook/*` | `admin.py`, `playbook.py` | 🔒 + `is_admin` |
| `/debug/*` | `debug.py` | **test only** — never mounted in a deployed environment |

## Conventions

- Errors are `{"detail": "..."}`; validation errors put a list in `detail`.
- `X-Request-ID` on every response (`RequestIDMiddleware`).
- `429` bodies carry `{error, retry_after, limit, window}` plus a `Retry-After`
  header.
- Rate limiting is called **inside** handlers, never as a route dependency, so
  a `422` never burns quota.
