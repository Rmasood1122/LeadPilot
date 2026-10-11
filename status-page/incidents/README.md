# Incidents

Every file in this folder except this README is a public incident on
status.calendarharvest.com. There are no example incidents on purpose: a file
here is published as a real event. Posting, updating and resolving an incident
is a pull request (steps: `docs/program/STATUS_PAGE.md`, "Posting an incident").

## File name

`YYYY-MM-DD-<slug>.md`, for example `2026-10-11-background-processing-delayed.md`.

- The date is the UTC date of the incident's **first** update.
- The slug is lowercase letters, digits and single hyphens. It becomes the URL:
  `/incidents/2026-10-11-background-processing-delayed`. Never rename a
  published file; the URL is in people's feed readers.

## Front matter

```yaml
---
title: Scheduled sends delayed
impact: major
components: [background-processing]
updates:
  - status: investigating
    at: 2026-10-11T14:05:00Z
    text: Scheduled emails are not going out. We are investigating.
  - status: identified
    at: 2026-10-11T14:20:00Z
    text: The background worker stopped. We are restarting it.
  - status: resolved
    at: 2026-10-11T14:40:00Z
    text: Sends resumed at 14:35 UTC. Messages queued during the delay went out in order.
---
Optional longer write-up after the closing line. Plain paragraphs separated by
a blank line; Markdown formatting is not rendered.
```

| Key | Required | Allowed values |
|---|---|---|
| `title` | yes | Up to 120 characters. Say what customers noticed, not the internal cause. |
| `impact` | yes | `none`, `minor`, `major`, `critical`, `maintenance` |
| `components` | yes | One or more of `website`, `api`, `background-processing`, `ai-features`, `booking-pages` |
| `updates` | yes | A list; each item has `status`, `at`, `text` |
| `updates[].status` | yes | `investigating`, `identified`, `monitoring`, `resolved` |
| `updates[].at` | yes | UTC time ending in `Z`, e.g. `2026-10-11T14:05:00Z`. Not in the future. |
| `updates[].text` | yes | What changed for customers, in plain words. |

Rules the lint enforces (`npm run incident-lint` in `status-page/`, and in CI):

- No other keys. No duplicate keys.
- At most one `resolved` update, and it must be the latest.
- The file-name date equals the date of the earliest update.

## What the impact does to the page

While the incident is **not resolved**, each listed component is shown at
least as bad as the impact says, even if the automatic checks look fine:

| impact | component shown as (at least) |
|---|---|
| `none` | unchanged |
| `minor` | Degraded performance |
| `major` | Partial outage |
| `critical` | Major outage |
| `maintenance` | Under maintenance (only while the checks say Operational) |

An incident can never make a component look *better* than its checks.
Once the latest update is `resolved`, the incident stops affecting component
status and stays in the history, the RSS feed and the Atom feed.

## Writing rules

- Facts only: what customers saw, when (UTC), what we did, what they need to do.
- No internal hostnames, error messages, queue names, customer names or counts.
- Do not promise a time to fix unless you can keep it.
