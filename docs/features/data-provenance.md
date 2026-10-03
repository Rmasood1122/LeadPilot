# Data Provenance Tags (Part 1, Feature 10)

**Migration** `0062_data_provenance` ·
**Service** `app/services/provenance.py` ·
**UI** `frontend/src/lib/provenance.ts`,
`components/leads/ProvenancePanel.tsx`

## Why

Every field on a prospect arrives from somewhere, and those somewheres are not
equally trustworthy:

- a title **typed by a person** is not a title Apollo guessed from a job posting;
- an email a verifier **confirmed accepts mail** is not one built from a first
  name and a domain;
- a tech stack **scraped from a careers page** is not one inferred from a logo.

They all render identically today, so someone about to write *"I saw you're
hiring three more inspectors"* has no way to know whether that came from the
company's own job board or from a guess.

## What is stored

`leads.provenance_json` — `{field: {source, confidence, observed_at, detail,
value}}`.

### Why a JSON column and not an EAV table

This schema argued the **opposite** case for custom fields (see
`CrmCustomFieldValue`): a JSON bag is wrong when values are **sorted and
filtered server-side** across thousands of rows, because JSON extraction is
spelled differently on SQLite and PostgreSQL and the test suite would exercise a
different query than production runs.

Provenance is the other case. It is never sorted, never filtered, never
aggregated — it is read **once, for one prospect**, when a person hovers a field
and asks where it came from. One column read alongside the lead it describes is
the cheapest possible answer; a per-field table would mean a second query (or a
join fanning one lead into twenty rows) on the lead detail page for data nobody
queries. A migration test asserts the columns are deliberately **unindexed**.

### The confidence belongs to the source

| Source | Confidence | Why |
|--------|-----------|-----|
| `manual` | 1.00 | Typed or corrected by a person |
| `reply` | 0.98 | The prospect said it themselves |
| `hunter_verified` | 0.95 | A provider confirmed the mailbox accepts mail |
| `crm_sync` | 0.90 | Synced from a CRM a person maintains |
| `linkedin` | 0.80 | Read from their own profile or posts |
| `apollo` | 0.75 | Good coverage, not verified |
| `company_news` | 0.70 | From a published article |
| `import` | 0.60 | Only as good as its source |
| `hunter_risky` | 0.50 | Flagged as risky by the verifier |
| `hunter_pattern` | 0.45 | Built from a name and a domain, never checked |
| `inferred` | 0.35 | Nobody observed it |

These are **documented constants**, not model output: each is a claim about the
*source*, not about the value. A caller may override with something it knows
better (a verification score), and an out-of-range value is **clamped**, because
a confidence above 1 would render as "140% sure".

**An unknown source is treated as `inferred`**, not as certain — the safe
direction when something wrote a field without saying what it was.

### Age is reported separately

`staleness` gives `days` and a band: **fresh** (< 90 days), **stale** (< 365),
**very_stale** (≥ 365). It is deliberately **not** multiplied into the
confidence, because the two need different fixes: a weak source needs a better
source, an old fact needs a refresh — and one blended score hides which.

### The value is snapshotted

So "this title came from Apollo" can be checked against a title someone has
since edited by hand. The mismatch is exactly when provenance matters.

## Where tags are written

| Stage | Tag |
|-------|-----|
| `enrich_leads_impl` | every field the stage actually filled, with the provider's own name |
| `find_missing_emails_impl` | `email` → `hunter_pattern` (built from a domain) |
| `verify_emails_impl` | `email` → `hunter_verified` / `hunter_risky` / `hunter_pattern` |
| `personalization_context.ensure_fresh` | `intent_signal` → `linkedin` or `company_news` |

The verifier's three verdicts are three **sources**, not one source with three
scores: deliverable is a checked fact, risky is a warning, unknown was never
checked at all.

Every write path is wrapped so it **never raises into the sourcing chain** —
enrichment has already succeeded by the time a tag is written, and losing a tag
must not lose the lead.

## Reading it

`GET /leads/{id}/provenance` returns the items **weakest first**, because the
list exists to answer *"what here should I not rely on?"* — and alphabetical
order buries that under Company and Email.

`tracked: false` means **nothing was ever recorded**, which is not the same as
"unknown source", and the UI says which rather than implying the data came from
nowhere.

A corrupt entry (a string where a dict belongs) is skipped rather than crashing
the page.

## UI

`ProvenancePanel` on the lead page lists each field with its source, confidence
and age, and flags the ones worth checking before quoting back to the prospect.
`ProvenanceTag` is the inline badge for use anywhere a single enriched field is
rendered; its `title` is `hoverText()` — source, confidence, age and the reason,
in one string.

## Tests

`tests/test_provenance.py` (38) — source ordering, the clamp, the unknown-source
rule, per-verdict email sources, age kept separate from confidence,
"never recorded" vs "unknown source", a corrupt entry not crashing the page, and
the real sourcing pipeline tagging what it filled.
`tests/test_provenance_migration.py` (5) — including that the columns are
unindexed. `frontend/src/tests/provenance.test.ts` (16).
