# P0-D-ENF — make single-tenancy enforceable: a switch for public sign-up

Branch `claude/p0-d-enf-signup-switch`. Finding: `DECISIONS.md` P0-D and
`BASELINE.md` §3.5 — `POST /auth/signup` (`app/api/auth.py`) accepted any
visitor and no setting turned it off, so a deployment that leaves it open is
multi-tenant in practice and the HIGH ratings of F-DB-01 and RF-5 return.

## Behaviour (defined)

| Setting | Default | Effect |
|---|---|---|
| `SIGNUP_ENABLED` | `true` | `false`: every `POST /auth/signup` → 403 "Sign-up is closed on this LeadPilot deployment. Ask your administrator for an account." |
| `SIGNUP_ALLOWED_EMAIL_DOMAINS` | empty (any) | comma list of exact domains (`acme.com, acme.co.uk`); any other domain → 403 "limited to approved email domains". The list is never echoed back. |

- Checked after the per-IP rate limiter and before the VPN-provider lookup and
  any account lookup: a closed deployment gives the same 403 for new and
  existing addresses (no enumeration) and a passwordless pre-auth row cannot
  be claimed.
- Closed wins over the domain list. Login, refresh and existing accounts are
  untouched. Both settings are read per request (env change + restart).
- Defaults keep today's behaviour. **Whether production closes sign-up, or
  limits it to a domain, is a founder decision** (`DECISIONS.md` P0-D-ENF).
- Accounts on a closed deployment come from
  `python -m app.cli.create_admin` (creates admins only).

## Residual (reported, not fixed here)

- No CLI or admin UI creates a **non-admin** user or sends an invite. With
  `SIGNUP_ENABLED=false` every new account is an admin; use the domain list to
  let colleagues self-register instead. An invite flow is its own task.
- The web app still shows the sign-up page and "Create account" links; the
  refusal text appears on submit. Hiding them needs a public
  "sign-up policy" endpoint — its own small task.
- Not added to the sealed compliance list: this is an access-control switch,
  not a CAN-SPAM/GDPR/CASL/PDPA guard. Founders may ask for it to be sealed
  in its own PR.

## Tests

`tests/test_signup_policy.py` (15): defaults open; lenient parsing; closed →
403 + no row + no email; existing address same 403; pre-auth row not
claimable; existing account logs in; refused before the VPN provider; allowed
domains register (case-insensitive); suffix/prefix/subdomain look-alikes
refused and the domains not leaked; closed beats an allowed domain.
Pre-fix on `origin/master` afcccd3: 2 failed, 12 errors, 1 passed (the
"default stays open" control).
