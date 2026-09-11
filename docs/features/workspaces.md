# Feature Group 8 — Workspaces, roles, approvals, white label

## The model
A **workspace is its owner's account.** Every product, strategy, lead,
integration and deal keeps the ownership it always had; members of the
workspace act on the owner's records. Every user owns exactly one workspace
(created the first time they open Team) and can be a member of others.

The browser sends `X-Workspace-Id` with every request once a workspace other
than your own is selected (the switcher in the top bar). The server checks
membership and role on each request, in the same place it checks email
verification (`app/services/auth.py::get_current_user`), so a new route is
covered automatically. A workspace you are not in answers **404**.

Routes about the *person* ignore the header and always act as whoever signed
in: `/auth`, `/me` (theme, API keys, voice profile), `/devices`, `/support`,
`/tutorials`, `/onboarding`, `/workspaces`, `/branding`. Admin rights come
from the signed-in person, never from the workspace owner.

## Roles
| | Owner | Manager | SDR | Viewer |
|---|---|---|---|---|
| Read everything in the workspace | ✓ | ✓ | ✓ | ✓ |
| Work leads, sequences, deals, meetings | ✓ | ✓ | ✓ | – |
| Launch a campaign | ✓ | ✓ | after approval¹ | – |
| Approve / decline SDR launches | ✓ | ✓ | – | – |
| Integrations, webhooks, costs, deleting | ✓ | ✓ | – | – |
| Invite / manage SDRs and viewers | ✓ | ✓ | – | – |
| Invite / manage managers | ✓ | – | – | – |
| Workspace settings, white label | ✓ | – | – | – |

¹ When the workspace requires approval (the default; Team › Settings).

## Manager approval
An SDR's first launch of a sequence (`POST /sequences/{id}/enroll`) is held as
`pending_approval`: nothing is enrolled or scheduled. The owner and managers
get an `approval_requested` push/Slack notification; Team › Approvals shows
the request. Approving replays the SDR's launch exactly (same lead statuses);
declining returns the sequence to draft with a note the SDR sees. Either way
the SDR gets `approval_decided`. Once approved, later launches of that
sequence need no further approval.

## Invitations
Owners and managers invite by email (managers can invite SDRs and viewers
only). The link is emailed and also shown to the inviter; it expires after
7 days, works once, and only for a signed-in user with the invited address.
Re-inviting an address replaces the earlier link.

## White label (owner)
Team › White label: brand name, logo (PNG/JPEG/WebP ≤ 1 MB — SVG is refused,
the bytes are checked against the declared type), primary colour, support
email, custom domain. The admin can disable white label for the whole
deployment (Admin › System Settings › `white_label_allowed`).

The branded experience is served to:
- `<slug>.<WHITE_LABEL_BASE_DOMAIN>` when that setting is configured, and
- a **verified** custom domain. Verification: a TXT record
  `_leadpilot-verify.<domain>` holding the token shown on the page, or a CNAME
  from the domain to `WHITE_LABEL_CNAME_TARGET`.

`GET /branding?host=` (public) is what the login page and the app shell read.

**Operator steps for a custom domain** (outside the app): add the domain to
the frontend host (Render/Railway custom domains, which also issue TLS), and
add its origin to the API's CORS allowed origins.

## Limits
- One owner's data per workspace; a member's own account stays separate.
- The voice profile used for outreach is the account owner's (`/me` is personal).
- Branded transactional email uses the brand name in invitations only; outreach
  is sent from the owner's connected Gmail, as before.
