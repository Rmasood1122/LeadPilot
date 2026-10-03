# Founder / Agency Mode — Per-Client Workspaces (Part 1, Feature 11)

**Migration** `0063_client_workspaces` ·
**Service** `app/services/client_workspaces.py` ·
**API** `app/api/client_workspaces.py` ·
**UI** `frontend/src/lib/clients.ts`, `app/(app)/clients/page.tsx`

## Why this is not `workspaces`

`Workspace` is a **team** around one owner. `owner_user_id` is **UNIQUE**, and
its own docstring says *"the workspace's data is its owner's data"* — thirteen
modules resolve ownership through `Product.user_id` because of that.

An agency's SDRs are **shared** across every client; the clients are **separate
books of business**. Conflating the two would mean either a login per client
(and re-inviting the same three SDRs to each) or breaking the unique constraint
that ownership resolution rests on.

So a client **hangs off** the team workspace rather than replacing it, and
isolation is achieved by **scoping**.

## The three things an agency actually needs

### Separate reporting

`report(client)` scopes to that client's strategies **at the query**. There is
no "filter the shared dashboard" step that someone can forget, and no path by
which another client's prospect can appear in a total that is about to be
forwarded to this one.

Rates are `null`, never `0.0`, when nothing has been sent — 0% reads as failure
in a report a client is about to read.

### Separate sending domains

`ClientSendingDomain` reserves domains per client, and `domain_allowed()` is
checked **in the send path** (`outreach_tasks.send_message_impl`), not just
rendered in a settings page. *An isolation rule that lives in a form is an
isolation rule that leaks.*

The pool is defined over **domains**, not mailbox rows, because that is what the
isolation is about: a client's prospects must never see another client's sending
domain, whichever mailbox on it happens to send.

**An empty pool means no restriction.** An agency that has not set pools up
sends exactly as it does today, and the pool only ever *narrows*. The UI says so
explicitly, so nobody assumes an isolation they have not configured.

A refused send is `FAILED` with a readable reason on the message, not a silent
drop.

### Separate billing view

`billing_view(client)` returns the retainer, the per-meeting fee, **the meeting
count for the current month**, and the **lines** that make up the total — in
that client's currency.

The working is shown deliberately: a retainer plus a per-meeting fee times a
meeting count is an invoice a client will query, and an agency that cannot show
the count loses the argument. The UI even checks the lines against the total and
says so if they disagree.

Money is **integer cents** throughout, for the reason `Deal.value_cents` gives.

## The unassigned case is first-class

A strategy with **no** client is the agency's own work — not an error, and not a
client that does not exist. `overview()` reports `unassigned_strategies` and the
UI raises it as *"That work is not on any invoice"*, because work that belongs
to nobody is exactly the work that stops being billed.

**An account that never creates a client workspace behaves exactly as it does
today.** That is the property that makes this safe to ship to every account at
once.

## Assignment

`POST /strategies/{id}/client` with `{client_id}` — or `null` to move it back.
Allowed **while the campaign is running**: an agency that wins a client
mid-flight should not have to stop outreach to file it correctly.

Deleting a client is `ON DELETE SET NULL` on `strategies.client_workspace_id`:
losing a client must not erase the outreach done for them.

## Permissions

Creating, re-pricing and changing domain pools need a **manager** in the team
workspace. Those are decisions, not data entry: an SDR should not be able to
re-price a client or point their sending at a new domain. Reading is open to any
member.

A client belonging to another agency is a **404**, never a 403 — its existence
must not be probeable.

## API

| Method | Path |
|--------|------|
| `GET` | `/clients?include_archived=` |
| `POST` | `/clients` |
| `GET` `PATCH` | `/clients/{id}` |
| `GET` | `/clients/{id}/report` |
| `GET` | `/clients/{id}/billing` |
| `POST` | `/clients/{id}/domains` |
| `DELETE` | `/clients/{id}/domains/{domain}` |
| `POST` | `/strategies/{id}/client` |

## Known limitation

`GmailAccount.user_id` is **UNIQUE** — one connected mailbox per user today. A
client's pool can therefore name several domains, but the account still has one
mailbox to send from, so the pool's practical effect right now is to **refuse**
sends from the wrong domain rather than to **route** between several. Multiple
mailboxes per account is the change that would make pools fully useful; nothing
here needs to change when it lands.

## Tests

`tests/test_client_workspaces.py` (45) — slug uniqueness, refusals, archive
round-trip, assignment both ways, domain normalisation and validation, the empty
pool being permissive, the send path blocking and allowing, reporting isolation
between two clients on the same account, the billing working and its period
boundary, and the API including the cross-agency 404s.
`tests/test_client_workspaces_migration.py` (10) — both tables, the strategies
column, `SET NULL` on client delete, and a full downgrade round-trip.
`frontend/src/tests/clients.test.ts` (19).
