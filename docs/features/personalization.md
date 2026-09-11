# Feature Group 2 — Hyper-personalization

## LinkedIn posts in the first line
Right before an email is written (the send path, not sourcing — step 3 goes
out a week after step 1), `personalization_context.ensure_fresh` fetches the
lead's three most recent LinkedIn posts (cached 7 days) via **Unipile**, or the
**RapidAPI** scraper as a fallback, and stores them on the lead
(`linkedin_posts_json`). The prompt requires the email's first line to
reference one specific detail from them, accurately. `linkedin_url` is captured
from Apollo at sourcing and can be edited on the lead page.

Unipile needs a LinkedIn account to read through: the user's connected account
(Feature Group 5) or the admin's optional `reader_account_id`.

## Company news in the hook
**NewsAPI**, cached 3 days: the company name as an exact phrase, last 30 days,
and an article is kept only if the name appears in its title or description
(whole word). The prompt references it in the opening hook only if it plausibly
concerns this company.

## Voice-matched messaging
Settings › Voice: paste up to five samples; Claude extracts a style profile
(tone, formality 1–5, vocabulary, sentence length, humour, habits). It is
appended to the **system prompt** of email rendering, WhatsApp variable filling
and the post-meeting follow-up (and LinkedIn/call scripts in later groups).
The samples are stored so they can be edited, but never reach an outreach
prompt — only the profile does.

## Personal Loom video for high-likelihood leads
Loom has no API to record on someone's behalf, so the honest version:
1. leads scoring above `loom_score_threshold` (75) after a sourcing batch get a
   personalised recording script, and the owner one `loom_requested` notification;
2. the user records in Loom and pastes the share link on the lead page;
3. sequence step 2 then carries a CTA to `/v?t=<token>` — a public page with the
   lead's first name and company that embeds the video.

No CTA is added until a real video exists. The page token is Fernet-encrypted;
the public endpoint is IP-rate-limited and returns only first name, company,
title and the embed URL.

## Audit
Each sent email records what it was written from in
`messages.personalization_json` (`linkedin_post_url`, `news_url`,
`style_profile`, `loom_cta`).

## Never blocks a send
An unconfigured provider is skipped; a failing one is logged and the email is
written without that input.
