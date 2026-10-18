# Help-center fact check

Every factual sentence in `docs/help-center/01…30-*.md` was checked against the
cited sources and the code by the read-only `help-center-fact-checker` agent
(`.claude/agents/help-center-fact-checker.md`), in two passes on 2026-10-10/11:
a full pass, then a re-check of every flagged sentence after the writers fixed
it. The last two sentences still flagged after the re-check (06 "dropped lead",
22 "sequence form") were corrected with the checker's exact wording.

| Articles | Sentences checked (final) | Supported | Unsupported | Contradicted |
|---|---|---|---|---|
| 01–10 | 525 | 525 | 0 | 0 |
| 11–20 | 549 | 549 | 0 | 0 |
| 21–30 | 419 | 419 | 0 | 0 |
| **All** | **1,493** | **1,493** | **0** | **0** |

First pass: 1,467 sentences, 1 unsupported and 65 contradicted. All 66 were
fixed against the code. The per-sentence tables below carry the final verdicts
(re-checked rows are marked).

Code defects the check found are reported, not fixed, in
`docs/program/help-center-discoveries.md`.


---

# Help-center fact check: articles 01–10

Checker: help-center-fact-checker (read-only). Repo: /home/claude/wt-help (HEAD b045cc6, help-center files untracked).
Method: every product-claim sentence was checked against the cited sources, then against the rest of the repo. Where code and docs disagree, the code wins. Pure navigation and general advice are skipped.

Source-path check (step 1): every path in the `sources:` front matter of 01–10 exists. None are missing.

## Process flags (read before merging)

- **D1 is not decided.** `docs/program/DECISIONS.md:9` says D1 ("Website copy vs. what the code does") is **Unanswered** and "Blocks Phase 2 articles 01, 09, 10, 11". The agent brief describes D1 as settled (automatic sending; research once per strategy). The code does support both of those behaviours (`app/workers/outreach_tasks.py:1-7`, `app/workers/tasks.py:95-146`). But by the project's own record, 01, 09 and 10 are blocked until a founder answers D1.
- **The daily AI limits are placeholders.** `docs/program/DECISIONS.md:20` (P0-5-CAPS, Unanswered) says the per-plan dollar figures in `app/core/plans.py:52-177` are placeholders. Articles 01, 03 and 04 state them as fixed facts. They match the code today, but a founder still has to confirm them.

---

### 01-what-is-leadpilot.md
| # | Sentence (verbatim, may be shortened with …) | Verdict | Evidence (path:line) / what the code says |
|---|---|---|---|
| 1 | Vectorae is an outbound sales system. You describe a product … then sends personalized outreach by email (and, where set up, WhatsApp) automatically, within compliance limits you can see. | supported | FEATURES.md:6; app/workers/outreach_tasks.py:1-7; app/services/sequence_engine.py:1-15 (D1 caveat above) |
| 2 | The work happens in a fixed order. | supported | FEATURES.md:44-67; app/workers/tasks.py:143-145; app/api/leads.py:83-90 |
| 3 | **Intake.** You give Vectorae a name and a plain-language description … Optionally, you describe past clients and how you won them. | supported | frontend/src/app/(app)/strategies/new/page.tsx:57-140 |
| 4 | **Research.** … 72 steps if you described past clients, or 144 steps if you did not. | supported | app/pipeline/engine.py:10-11,37-40 |
| 5 | It runs once per strategy, not once per prospect. | supported | app/workers/tasks.py:95-146; app/api/strategies.py:132-209 |
| 6 | **Verification.** The finished strategy is checked against 10 criteria, including a legal and compliance check. | supported | app/verification/passes.py:103-161 |
| 7 | Leads cannot be sourced and outreach cannot start until the strategy is verified. | supported | app/api/leads.py:83-90; app/api/sequences.py:247-251 |
| 8 | **Lead sourcing.** Vectorae searches for people …, adds details …, finds and checks their email address, and removes anyone on the suppression list. | supported | app/workers/lead_tasks.py:3-13,221-223,283-285,340-348 |
| 9 | **Writing and sending.** Each email is written for one specific person at the moment it is sent (a WhatsApp template's wording is fixed; only its variables are filled per person). | supported | app/workers/outreach_tasks.py:554-589,646-653; app/services/message_personalization.py:1-4 |
| 10 | Messages are then sent automatically from your connected Gmail account (or the deployment's WhatsApp Business number), inside send windows and daily limits. | supported | app/workers/outreach_tasks.py:268-352,396-398 |
| 11 | **Follow-up.** Later steps go out after the delay you set. | supported | app/services/sequence_engine.py:325,352-386 |
| 12 | When someone replies, their sequence stops. | supported | app/workers/outreach_tasks.py:1104-1108 (an out-of-office reply pauses instead, 1095-1102) |
| 13 | **Booking and meetings.** Vectorae has its own booking pages and a meeting room for notes and an AI summary. | supported | app/api/calendar.py:327-433; app/api/meetings.py:134-156,432 |
| 14 | **Learning.** Results are rolled up every night and fed into the starting point for new strategies. | supported | app/workers/celery_app.py:234-238 (nightly 02:05 UTC); app/pipeline/engine.py:128-139 (playbook injected into phases 6 and 8) |
| 15 | No. Once you launch a sequence, Vectorae sends the messages automatically. | supported | app/workers/celery_app.py:226-229; app/workers/outreach_tasks.py:99-123 (D1 caveat) |
| 16 | Before every single send it re-checks the suppression list, the campaign and contact state, the send window, and the daily allowance. | supported | app/workers/outreach_tasks.py:1-7,171-196,268-352 |
| 17 | Some messages can be held for a person to approve first … | supported | app/workers/outreach_tasks.py:416-432; app/services/send_review.py:1-40 |
| 18 | Vectorae does not reply to people on your behalf: when a prospect replies, the reply is classified and routed to you, and you write the answer. | supported | app/workers/outreach_tasks.py:996-998,1115-1117; app/services/reply_classification.py:12 |
| 19 | No. The research pipeline runs once for each strategy you create. | supported | app/workers/tasks.py:95-146 |
| 20 | Messages to individual prospects are written separately, at send time, from that strategy's messaging research plus what Vectorae has stored about the person. | supported | app/services/message_personalization.py:47-59,97-174 |
| 21 | The research instructions tell the model never to invent statistics and to label estimates as assumptions. | supported | app/pipeline/registry.py:46-51 |
| 22 | Verification check #1 then tests for this. | supported | app/verification/passes.py:104-107 |
| 23 | Every AI-written message is checked before it is sent. | supported | app/workers/outreach_tasks.py:576-584; app/services/system_settings.py:142 (on by default; an administrator can turn the whole check off with `claim_verification_enabled`, app/services/claim_verification.py:442-461) |
| 24 | Any claim about the prospect or their company … must be backed by data Vectorae actually stored for that lead. | supported | app/services/claim_verification.py:1-20 |
| 25 | Unsupported claims are removed or replaced with a neutral line. | supported | app/services/claim_verification.py:7-9,363-372 |
| 26 | The legal and compliance verification check can never be passed manually by a person. It has to pass on its own. | supported | app/services/verification_override.py:24-28,161-166 |
| 27 | Every outreach email carries a footer with the sender identity and an unsubscribe link, plus one-click unsubscribe headers. | supported | app/services/sequence_engine.py:439-463 |
| 28 | An unsubscribe, or a reply asking to stop, suppresses the person and stops all of their sequences immediately. | supported | app/services/sequence_engine.py:484-508; app/api/unsubscribe.py:50; app/workers/outreach_tasks.py:1084-1088 |
| 29 | WhatsApp messages only go to contacts with a recorded opt-in, and a first WhatsApp touch must use a Meta-approved template. | supported | app/workers/outreach_tasks.py:222-255; app/api/sequences.py:181-199 |
| 30 | If a campaign's bounce rate goes above the threshold (3% by default, after at least 10 sends), the whole campaign pauses until a person resumes it. | supported | app/config.py:113-114; app/services/sequence_engine.py:527-557 |
| 31 | Vectorae gives no legal advice; you remain responsible for having a lawful basis to contact each person. | supported | app/services/compliance_rules.py:36; frontend/src/components/strategy/OutreachPanel.tsx:198-205 |
| 32 | Each plan sets how many strategies …, how many leads one strategy can hold, how many steps …, which channels …, and a daily AI spending limit. | supported | app/core/plans.py:52-177 |
| 33 | When the daily AI limit is used up, new strategies and resumes are refused until it resets at 00:00 UTC. | supported | app/api/strategies.py:102-126,167,322 (figures are placeholders, DECISIONS.md:20) |
| 34 | Vectorae runs on a server, so sequences keep sending and follow-ups keep firing when your computer is off. | supported | app/workers/celery_app.py:207-262 |
| 35 | (RE-CHECK, rewritten) Each deployment (database, workers and app) is intended to serve one customer organization. | supported | docs/program/DECISIONS.md:22-26 |
| 35a | (RE-CHECK, new) Public sign-up is open to any email address by default, so a deployment stays limited to one organization only if its administrator closes sign-up or limits it to the organization's email domains. | supported | app/config.py:434-448; app/api/auth.py:214-228; DECISIONS.md:36-46 |
| 36 | You use it through the web app; there is also an Android app. | supported | frontend/android (Capacitor project) |
| 37 | Vectorae connects to outside services such as Apollo, Hunter, Gmail, Meta's WhatsApp Cloud API, Calendly, Stripe and Recall.ai. | supported | docs/VERIFICATION_REPORT.md:579 |
| 38 | These integrations were built and tested against simulated responses. | supported | docs/VERIFICATION_REPORT.md:84 (F-QA-02 "integrations mock-only"), :579 |
| 39 | They have not yet been verified end to end against the live services. | supported | docs/VERIFICATION_REPORT.md:579 |
| 40 | ~~Where an article describes one of these integrations, it says so.~~ | removed | RE-CHECK: the writer deleted this sentence (and 03 and 08 now carry the Stripe and Calendly caveats anyway). |

Summary (after re-check): 40 supported, 0 unsupported, 0 contradicted.

---

### 02-who-its-for-and-not-for.md
| # | Sentence (verbatim, may be shortened with …) | Verdict | Evidence (path:line) / what the code says |
|---|---|---|---|
| 1 | The first part comes from Vectorae's own customer research (its ideal customer profile). | supported | docs/ICP.md:1 |
| 2 | … target customer as a business-to-business company in the United States with roughly 5 to 50 employees, and a sweet spot of about 8 to 25. | supported | docs/ICP.md:1,6,51 |
| 3 | At that size there is usually one named person who decides … owner, founder, general manager or head of sales, but no dedicated sales team or sales infrastructure yet. | supported | docs/ICP.md:91-96,199-203 |
| 4 | 1. Small marketing, web development and design agencies. | supported | docs/ICP.md:76 |
| 5 | 2. Commercial cleaning and janitorial companies that have grown past a one- or two-person operation. | supported | docs/ICP.md:77 |
| 6 | 3. Small accounting, immigration and law consultancies (the research marks this one as an assumption …). | supported | docs/ICP.md:78 |
| 7 | 4. Business-to-business staffing and recruiting agencies. | supported | docs/ICP.md:79 |
| 8 | 5. Commercial HVAC and facilities maintenance companies (the lowest-confidence rank). | supported | docs/ICP.md:80 |
| 9 | These are targets, not requirements. You can run Vectorae for any product or service you sell to other businesses. | supported | app/api/strategies.py:132-209 (no product-type restriction) |
| 10 | Companies that already run Salesforce or HubSpot and have a dedicated sales or business development hire. | supported | docs/ICP.md:201-203 |
| 11 | The problem Vectorae addresses is the absence of that setup. | supported | docs/ICP.md:202-203 |
| 12 | Owner-operators with fewer than 5 employees and no budget for software. | supported | docs/ICP.md:204-206 |
| 13 | Businesses that sell only to consumers or homeowners. | supported | docs/ICP.md:207-209 |
| 14 | Vectorae finds and contacts people at companies. It has no consumer prospecting. | supported | app/integrations/apollo.py:90-92; app/workers/lead_tasks.py:227-240 |
| 15 | The new-strategy form asks for a name and a description, and optionally details of past clients and how you won them. | supported | frontend/src/app/(app)/strategies/new/page.tsx:57-133 |
| 16 | Email outreach is sent through the Gmail account you connect in Settings. | supported | app/workers/outreach_tasks.py:70-85 |
| 17 | Vectorae stores one Gmail connection per user account. | supported | app/db/models.py:1659-1661 (user_id unique) |
| 18 | Before you launch, Vectorae asks you to confirm that you may lawfully email each person on the list. | supported | frontend/src/components/strategy/OutreachPanel.tsx:198-205; frontend/src/lib/leadOutreach.ts:56-67 |
| 19 | It applies compliance checks at send time, but it does not give legal advice. | supported | app/workers/outreach_tasks.py:1-7; app/services/compliance_rules.py:36 |
| 20 | **For WhatsApp:** a plan that includes WhatsApp, a WhatsApp Business number configured on your Vectorae deployment, Meta-approved message templates, and a recorded opt-in for each contact. | supported | app/core/plans.py:58,75; app/config.py:135-158; app/workers/outreach_tasks.py:222-255 |
| 21 | (RE-CHECK, rewritten) Not as leads. Leads for email and WhatsApp sequences come only from Vectorae's own sourcing step … | supported | app/workers/lead_tasks.py:227 (the only place a Lead is created) |
| 22 | (RE-CHECK, rewritten) There is no way to import your own contact list as leads. | supported | app/workers/lead_tasks.py:227; no lead-import route in app/api |
| 23 | (RE-CHECK, rewritten) If your business depends on emailing or messaging a list you already have, Vectorae does not currently support that. | supported | Same as #22; the LinkedIn exception is stated next (#23a). |
| 23a | (RE-CHECK, new) The one exception is LinkedIn. On the Growth, Scale, Pro and Enterprise plans, the **Network** page lets you upload your LinkedIn `Connections.csv` export and send saved messages to people who are still your 1st-degree connections. | supported | app/core/plans.py:180-186; app/services/linkedin_network.py:343-345; app/api/linkedin_network.py:68-87,215-230; app/services/network_messages.py:1-9; frontend/src/components/shell/nav.ts:50 |
| 23b | (RE-CHECK, new) Those connections do not become leads. | supported | app/api/linkedin_network.py:19-22 (stored as LinkedInConnection; no Lead created) |
| 24 | By default, a newly connected Gmail account starts at 10 emails on its first day, adds 10 per day, and stops at a ceiling of 100 emails per day. | supported | app/config.py:106-108; app/services/sequence_engine.py:115-123 |
| 25 | These numbers are set per deployment, and compliance rules can only lower the cap, never raise it. | supported | app/services/compliance_rules.py:13-15; app/services/sequence_engine.py:122 |
| 26 | Messages over the day's allowance wait for the next day; they are not dropped. | supported | app/workers/outreach_tasks.py:339-352 |
| 27 | The deployment's WhatsApp number follows the same pattern by default. | supported | app/config.py:155-158; app/services/sequence_engine.py:161-179 |
| 28 | No. Vectorae does not auto-reply to people. | supported | app/workers/outreach_tasks.py:996-998; app/services/reply_classification.py:12 |
| 29 | When someone replies, Vectorae classifies the reply, stops their sequence (or pauses it for an out-of-office), and tells you. | supported | app/workers/outreach_tasks.py:1037,1095-1117 |
| 30 | You write the answer. | supported | app/workers/outreach_tasks.py:996-998 |
| 31 | (RE-CHECK, rewritten) Partly. A Vectorae deployment is intended to serve one customer organization (this holds only if the administrator closes public sign-up or limits it to the organization's email domains; by default sign-up is open). | supported | DECISIONS.md:22-26,36-46; app/config.py:434-448 |
| 32 | For email, client workspaces can restrict each client's outreach to that client's own sending domains. | supported | app/workers/outreach_tasks.py:319-332 |
| 33 | For WhatsApp, there is one sending number per deployment, so every client's prospects see the same WhatsApp number. | supported | app/config.py:137; app/services/sequence_engine.py:162-164; docs/program/BASELINE.md:164 |
| 34 | If you need a separate WhatsApp number per client, Vectorae does not support that yet. | supported | docs/program/BASELINE.md:92 |
| 35 | Vectorae works out which region a lead is in from their country or time zone and applies region-specific rules. | supported | app/services/compliance_region.py:9-17,124-131 |
| 36 | … it never adds an open-tracking pixel to email sent to leads in the EU, EEA or UK … | supported | app/services/compliance_region.py:134-137; app/services/open_tracking.py:76-80 |
| 37 | … and it adds a regional notice to the email footer where that region's rules ask for one. | supported | app/services/compliance_audit.py:49-64; app/services/sequence_engine.py:456-463 |
| 38 | Leads with neither a country nor a time zone are treated as "unknown". | supported | app/services/compliance_region.py:15-17; app/services/compliance_audit.py:70-73 (for open tracking, unknown counts as allowed) |

Summary (after re-check): 40 supported, 0 unsupported, 0 contradicted. New sources (app/api/auth.py, app/api/linkedin_network.py, app/services/linkedin_network.py, app/services/network_messages.py, frontend/src/app/(app)/network/page.tsx) all exist.

---

### 03-getting-started.md
| # | Sentence (verbatim, may be shortened with …) | Verdict | Evidence (path:line) / what the code says |
|---|---|---|---|
| 1 | (RE-CHECK, rewritten) Email verification is required before you can use anything; the phone step and the plan choice can be put off, with the limits described below. | supported | app/config.py:276-281; frontend/src/lib/post-login.ts:4-7,25-32; onboarding/verify/page.tsx:274 |
| 2 | … enter your email address and a password of at least 8 characters, and press **Create account**. | supported | app/api/auth.py:78; frontend/src/app/(auth)/signup/page.tsx:55-64 |
| 3 | Each Vectorae deployment can turn public sign-up off, or allow only certain email domains. By default it is open to any address. | supported | app/config.py:434-448 |
| 4 | If it is closed you will see "Sign-up is closed on this Vectorae deployment. Ask your administrator for an account." | supported | app/api/auth.py:207-208,222-223 |
| 5 | If your domain is not allowed, you will see a similar message about approved email domains. | supported | app/api/auth.py:209-211,224-228 |
| 6 | On production deployments, Vectorae refuses sign-up and sign-in from these networks and asks you to try again from your normal network. | supported | app/config.py:411-416,502-506; app/services/network_guard.py:36-38; app/api/auth.py:250 |
| 7 | Sign-up and other account requests are limited to 10 per 15 minutes from one network address. | supported | app/core/config.py:320; app/api/auth.py:242-243,344-348 |
| 8 | **The address already has an account.** Sign in instead. | supported | app/api/auth.py:254-255 |
| 9 | Right after sign-up, Vectorae emails you a verification link and shows a **Check your email** screen. | supported | app/api/auth.py:282-289; frontend/src/lib/post-login.ts:25-27; frontend/src/app/(auth)/check-email/page.tsx:74 |
| 10 | Click the link in the email to activate your account. | supported | app/api/auth.py:292-326 |
| 11 | The link expires after 24 hours. | supported | app/config.py:236-238 |
| 12 | Until you click it, your account exists but cannot use any features. | supported | app/config.py:276-281; app/api/auth.py:277-281 |
| 13 | If you sign in before verifying, you are sent back to the **Check your email** screen. | supported | frontend/src/lib/post-login.ts:25-27 |
| 14 | On the **Check your email** screen, press **Resend verification email**. A new link replaces the old one. | supported | frontend/src/app/(auth)/check-email/page.tsx:121; app/services/email_verification.py:100-112 |
| 15 | If the screen says the email could not be sent, your account was still created. | supported | app/api/auth.py:183-204; frontend/src/app/(auth)/check-email/page.tsx:78-82 |
| 16 | … the resend screen always answers the same way ("If that address has an unverified account, a new link is on its way") … | supported | frontend/src/app/(auth)/check-email/page.tsx:110-116; app/api/auth.py:329-357 |
| 17 | Vectorae's system emails come from noreply@calendarharvest.com by default. | supported | app/config.py:226 |
| 18 | New accounts go through a short, two-step verification screen after the email link. | supported | app/api/auth.py:270-273; frontend/src/app/(app)/onboarding/verify/page.tsx:5-7,59 |
| 19 | You choose the country you are personally in, and whether you are signing up as an individual or a company. | supported | frontend/src/app/(app)/onboarding/verify/page.tsx:121-142 |
| 20 | A company also gives the country it is registered or operating in, and optionally its name. | supported | frontend/src/app/(app)/onboarding/verify/page.tsx:156-168 |
| 21 | Vectorae compares your stated country with where your connection appears to come from. | supported | app/services/identity.py:3-6 |
| 22 | A mismatch never blocks you; it only flags your account for an administrator to review. | supported | app/services/identity.py:8-14 |
| 23 | Enter your mobile number with its country code (for example +44 20 7946 0958) and press **Send code**. | supported | frontend/src/app/(app)/onboarding/verify/page.tsx:240-245 |
| 24 | Vectorae texts you a 6-digit code. | supported | app/services/phone_verification.py:3,140 |
| 25 | The code expires after 10 minutes. | supported | app/config.py:462 |
| 26 | After 5 wrong attempts the code is locked. | supported | app/config.py:463; app/services/phone_verification.py:176-185 |
| 27 | You can request a new code after 60 seconds, and up to 5 codes per hour. | supported | app/config.py:464; app/core/config.py:294-301 |
| 28 | You can press **Do this later**. | supported | frontend/src/app/(app)/onboarding/verify/page.tsx:274 |
| 29 | Until your phone is verified you can explore and research, including running strategies, but you cannot launch outreach, choose a paid plan or share dashboards. | supported | app/api/sequences.py:298,399; app/api/billing.py:17,77; app/api/share_links.py (require_verified_phone); app/config.py:465-468 |
| 30 | The text-message service behind this step (Twilio) has not yet been verified against the live service. | supported | BUILD_BLOCKERS.md:10-22 |
| 31 | If your deployment has not finished setting it up, codes may not arrive. | supported | app/config.py:451-456 (default `sms_provider="console"` delivers nothing) |
| 32 | (RE-CHECK, rewritten) Not to start. An account without a paid plan uses the Free plan's limits (for example 3 strategies, a $10 daily AI limit, and email only). | supported | app/db/models.py:405 (default plan FREE); app/core/plans.py:53-69; no server route requires a paid plan (app/api/auth.py:166 only reports it) |
| 33 | (RE-CHECK, rewritten) Right after you sign in, if your account has no paid plan, Vectorae shows you the **Pricing** page ("Choose a plan to start using Vectorae"); it does not send you back there later. | supported | frontend/src/lib/post-login.ts:4-7,31; frontend/src/app/pricing/page.tsx:112 |
| 34 | Each monthly tier starts with a 14-day free trial. | supported | app/core/billing_catalog.py:29; frontend/src/app/pricing/page.tsx:133 |
| 35 | Choosing a plan requires a verified phone number. | supported | app/api/billing.py:17,77 |
| 35a | (RE-CHECK, new) The payment integration (Stripe) has not yet been verified against the live service; if checkout is not available on your deployment, contact support. | supported | docs/VERIFICATION_REPORT.md:579; app/api/billing.py:79-84 (503 in production when no Stripe key) |
| 36 | Members of a workspace whose owner has a plan do not need their own. | supported | app/services/billing.py:539-540 |
| 37 | Go to **Settings**, open the **Integrations** tab, and press **Connect** on the Gmail card. | supported | frontend/src/app/(app)/settings/page.tsx:298-327 |
| 38 | Google asks you to approve access. | supported | app/integrations/gmail.py:96-112 |
| 39 | Email outreach cannot be sent until a Gmail account is connected. | supported | app/workers/outreach_tasks.py:70-80 |
| 40 | Go to **Strategies** and press **New strategy**. The form has four short steps: | supported | frontend/src/app/(app)/strategies/page.tsx:16; frontend/src/app/(app)/strategies/new/page.tsx:55-161 |
| 41 | **What do you want clients for?** Give a name, describe the product or skill …, and choose **A product** or **A skill / service**. | supported | frontend/src/app/(app)/strategies/new/page.tsx:57-78 |
| 42 | **Do you have any past clients for this?** Choose **Yes — build on proven patterns** or **No — research the market from scratch**. | supported | frontend/src/app/(app)/strategies/new/page.tsx:86-101 |
| 43 | **Past clients** (only if you said yes). For each client, describe who they were and how you won them. You can add more than one. | supported | frontend/src/app/(app)/strategies/new/page.tsx:107-140 |
| 44 | **Ready to launch.** Review the flow and press **Launch pipeline**. | supported | frontend/src/app/(app)/strategies/new/page.tsx:144-171 |
| 45 | If you added past clients, Vectorae runs a 72-step research pipeline anchored on them. If not, it runs 144 steps (72 strategy plus 72 go-to-market). | supported | frontend/src/app/(app)/strategies/new/page.tsx:151-153; app/pipeline/engine.py:10-11 |
| 46 | Each time you complete this form, Vectorae creates a new product and a new strategy for it. | supported | frontend/src/app/(app)/strategies/new/page.tsx:29-38 |
| 47 | You land on the strategy's page. | supported | frontend/src/app/(app)/strategies/new/page.tsx:38 |
| 48 | (RE-CHECK, rewritten) The research runs on Vectorae's servers, so you can close the tab; the strategy page shows research progress as steps done out of the total for each pipeline. | supported | app/api/strategies.py:221-251; detail/page.tsx:38-60,167-171 |
| 49 | When research finishes, the 10 verification checks run. | supported | app/workers/tasks.py:143-145 |
| 50 | … you have reached your plan's number of strategies (for example, 3 on the Free plan); | supported | app/api/strategies.py:158-166; app/core/plans.py:54 |
| 51 | … your plan's daily AI limit is used up (it resets at 00:00 UTC); | supported | app/api/strategies.py:102-126,167 |
| 52 | … you have already started 2 strategies in the past hour. | supported | app/core/config.py:172; app/api/strategies.py:149. Nuance: the counter counts every well-formed create request, including ones refused for other reasons (app/core/rate_limiting.py:246-251). |
| 53 | On the verified strategy's page, use **1. Find leads** …, then **2. Write the email and launch** to start outreach. | supported | frontend/src/components/strategy/OutreachPanel.tsx:103,160-163 (card 2 appears only once at least one verified lead with an email exists) |
| 54 | Launching needs a verified phone number, and emails only go out once a Gmail account is connected. | supported | app/api/sequences.py:298; app/workers/outreach_tasks.py:70-80 |

Summary (after re-check): 55 supported, 0 unsupported, 0 contradicted. New source docs/VERIFICATION_REPORT.md exists.

---

### 04-research-pipeline.md
| # | Sentence (verbatim, may be shortened with …) | Verdict | Evidence (path:line) / what the code says |
|---|---|---|---|
| 1 | … a fixed series of AI research steps that ends in a written strategy document. | supported | app/pipeline/engine.py:232-258 |
| 2 | The pipeline is organized into 8 phases of 9 steps each. The ninth step of every phase is a summary step … | supported | app/pipeline/registry.py:9-12; app/pipeline/budget_plan.py:7-11 |
| 3 | The strategy document is built from those 8 phase summaries. | supported | app/pipeline/engine.py:232-245 |
| 4 | The 8 strategy phases are: Product decomposition, ICP definition, … and Execution plan. | supported | frontend/src/app/(app)/strategies/detail/page.tsx:21-26 (short labels); app/pipeline/registry.py:57-146 |
| 5 | Before the first phase, Vectorae fetches recent market signals once …: news headlines from the last 30 days (from Google News) and, where available, company funding and headcount signals from Apollo. | supported | app/services/market_intel.py:1-17,53-57; app/workers/tasks.py:113-120 |
| 6 | They are labelled as headlines to check, not facts to quote. | supported | app/services/market_intel.py:26-27 |
| 7 | If this fetch fails, the pipeline continues without them. | supported | app/services/market_intel.py:29-32 |
| 8 | The pipeline runs **once per strategy**. It does not run again for each prospect. | supported | app/workers/tasks.py:95-146 |
| 9 | It depends on your answer to "Do you have any past clients for this?" … | supported | frontend/src/lib/api/strategies.ts:49-55 |
| 10 | Yes, and added past clients → strategy pipeline anchored on your past clients → 72 | supported | app/pipeline/engine.py:37-40,81-90 |
| 11 | No → strategy pipeline, then GTM pipeline → 144 | supported | app/pipeline/engine.py:37-40 |
| 12 | The GTM pipeline's 8 phases are: Positioning, Pricing, … and Funnel metrics. | supported | frontend/src/app/(app)/strategies/detail/page.tsx:27-30; app/pipeline/registry.py:152-241 |
| 13 | When both run, the strategy pipeline runs first and the GTM pipeline second. | supported | app/pipeline/engine.py:37-40 (FEATURES.md:153 says GTM runs first; that doc is stale) |
| 14 | There is no fixed duration; it depends on the AI service's response times. | supported | app/core/config.py:190-193 |
| 15 | The research runs on Vectorae's servers, so you can close the browser tab. | supported | app/workers/tasks.py:95 |
| 16 | (RE-CHECK, rewritten) The strategy page shows progress for each pipeline (the strategy pipeline, and the GTM pipeline when it runs) as steps done out of the total. | supported | app/api/strategies.py:221-251; detail/page.tsx:38-60,167-171 |
| 16a | (RE-CHECK, new) In the current release these progress cards are labelled "Phase pending" rather than with phase names, and they do not break progress down by phase. | supported | detail/page.tsx:38-41 (entries have no `phase`, so `numbered` is false); app/api/schemas.py:127-131 |
| 17 | When verification finishes, Vectorae sends a push notification ("Your strategy is ready" or "Strategy needs review") to devices registered for notifications. | supported | app/verification/loop.py:360-368; app/services/notifications.py:355-382 |
| 18 | Each pipeline run has a time limit of 2 hours. | supported | app/config.py:346-350; app/workers/tasks.py:95-97 |
| 19 | … Vectorae retries it automatically up to 3 times, 30 seconds apart, and each retry continues from the last finished step. | supported | app/workers/tasks.py:95,160-181; app/pipeline/engine.py:58-69 |
| 20 | If the error cannot succeed on retry, or the retries run out, the strategy is marked `failed` and the reason is shown on the strategy page. | supported | app/workers/tasks.py:43-69,160-172; detail/page.tsx:161-165 |
| 21 | `pending` — Created; research has not started yet. | supported | app/api/strategies.py:202-208,323-325 |
| 22 | `researching` — The research steps are running. | supported | app/workers/tasks.py:109 |
| 23 | `verifying` — Research is done; the 10 verification checks are running. | supported | app/workers/tasks.py:143-145; app/verification/loop.py:252 |
| 24 | `verified` — All 10 checks passed (or a person signed off failed checks …). You can now find leads and launch outreach. | supported | app/verification/loop.py:355-357; app/api/strategies.py:420 |
| 25 | `needs_human_review` — At least one check still failed after its fix attempts. | supported | app/verification/loop.py:351-357 |
| 26 | `executing` — Reserved … The current release does not set it … | supported | grep: no assignment of StrategyStatus.EXECUTING anywhere in app/ |
| 27 | `failed` — The run stopped on an error it could not recover from. | supported | app/workers/tasks.py:43-69 |
| 28 | `budget_exhausted` — … the next AI call could have gone over the strategy's budget or your daily AI limit. Everything already done is saved. | supported | app/workers/tasks.py:72-86; app/services/usage_meter.py:63-82 |
| 29 | Every strategy has a dollar budget for the AI spending of its research and verification. | supported | app/services/usage_meter.py:42-45; app/config.py:50-60 |
| 30 | Writing outreach messages later does not count against it. | supported | app/services/usage_meter.py:42-45,166-184 (see out-of-scope note 4) |
| 31 | Before each AI call, Vectorae checks whether the call could take the run past its budget, assuming the worst case. If it could, the call is not made … Nothing is spent on the refused call. | supported | app/services/usage_meter.py:258-287; app/workers/tasks.py:147-148 |
| 32 | The default budget is $15. Through the API you can choose any amount from $0.50 up to the server's ceiling, which is $50 by default. The New strategy form uses the default. | supported | app/config.py:59-60; app/api/strategies.py:57-69,186-189; frontend/src/lib/api/strategies.ts:49-55 |
| 33 | (RE-CHECK, rewritten) … runs fewer of the supporting research steps (between 2 and 8 steps per phase, instead of the full 9). | supported | app/pipeline/budget_plan.py:64-73 |
| 34 | A shorter run also gets at most 2 attempts per verification check. | supported | app/verification/loop.py:133-141 |
| 35 | If the budget cannot cover even 2 steps per phase, Vectorae refuses to create the strategy and tells you the minimum needed. | supported | app/api/strategies.py:192-201; app/pipeline/budget_plan.py:60-69 |
| 36 | … every plan has a limit on how much AI spending your whole account can run up per day. The day resets at 00:00 UTC. | supported | app/core/plans.py:45-51; app/services/usage_meter.py:187-195 |
| 37 | Daily AI limit table (Free $10, Starter $25, Growth $60, Pay per meeting $60, Scale $150, Pro $150, Enterprise $400) | supported | app/core/plans.py:55,72,91,107,126,142,164 (placeholders: DECISIONS.md:20) |
| 38 | All AI use on your account counts toward the day's total. | supported | app/services/usage_meter.py:47-49,198-215 |
| 39 | The limit is enforced on research, verification and lead scoring. | supported | app/services/usage_meter.py:55 |
| 40 | Message writing, meeting briefs and call analysis are not stopped partway when the limit is reached. | supported | app/services/usage_meter.py:47-54 |
| 41 | Starting a new strategy is refused with a message like "Your Free plan's daily AI limit ($10.00) is used up. It resets at 00:00 UTC." | supported | app/api/strategies.py:115-125 |
| 42 | A strategy that is already running stops as `budget_exhausted`. Resume it after the reset, or upgrade your plan. | supported | app/services/usage_meter.py:77-82,288-300; app/workers/tasks.py:147-148 |
| 43 | Resuming is refused until the reset. In the current app, the **Resume** button may show only "Too many requests. Wait a few minutes and try again." … | supported | app/api/strategies.py:322; frontend/src/lib/api/strategies.ts:100 |
| 44 | Press **Resume** … It appears when the status is `pending`, `researching`, `verifying`, `failed` or `budget_exhausted`. Then press **Confirm resume**. | supported | frontend/src/components/strategy/ResumeStrategyButton.tsx:13-15,77-80 |
| 45 | The run continues from the last finished step. Finished steps are not repeated or paid for again. | supported | app/pipeline/engine.py:58-69; app/api/strategies.py:277-282 |
| 46 | If the status is `pending`, `researching` or `verifying`, only resume if progress has really stopped. Resuming a run that is still working can duplicate work. | supported | ResumeStrategyButton.tsx:17-21,60-62 |
| 47 | For a `budget_exhausted` strategy you can enter a **New budget $**. It must be more than what the strategy has already spent. | supported | ResumeStrategyButton.tsx:64-75; app/api/strategies.py:312-321 |
| 48 | Resume is refused for `verified` and `needs_human_review` strategies. For `needs_human_review`, use **Re-verify** instead … | supported | app/api/strategies.py:295-300; ReverifyStrategyButton.tsx:13-14 |
| 49 | By default you can start at most 2 strategies per hour; this is a deployment setting. | supported | app/core/config.py:172 (counts well-formed requests; see 03 #52) |
| 50 | … 3 on Free, 10 on Starter and on Pay per meeting, 25 on Growth, and no limit on Scale, Pro and Enterprise. | supported | app/core/plans.py:54,71,90,106,125,141,163 |
| 51 | (RE-CHECK, rewritten) You can read the finished documents. | supported | detail/page.tsx:121-125; app/api/ui_support.py:116 |
| 51a | (RE-CHECK, new) The outputs of individual research steps are not shown in the current release: opening a progress card only shows "Step outputs appear here as they complete." | supported | app/api/schemas.py:120-146 (no `steps`); detail/page.tsx:71-77 |
| 52 | When the documents are ready, **View documents** opens the strategy document (and the GTM document for 144-step strategies). | supported | detail/page.tsx:121-125; app/api/ui_support.py:116; app/pipeline/engine.py:248-258 |

Summary (after re-check): 54 supported, 0 unsupported, 0 contradicted.

---

### 05-strategy-verification.md
| # | Sentence (verbatim, may be shortened with …) | Verdict | Evidence (path:line) / what the code says |
|---|---|---|---|
| 1 | … Vectorae checks the strategy document against 10 separate criteria before anything can reach a real person. | supported | app/verification/passes.py:159-161; app/api/leads.py:83; app/api/sequences.py:249 |
| 2 | Each check is judged on its own, one criterion at a time. | supported | app/verification/passes.py:15-23 |
| 3 | An AI reviewer answers PASS, or FAIL with a concrete instruction for what to change. | supported | app/verification/passes.py:15-23 |
| 4 | On a FAIL, Vectorae rewrites the strategy document to resolve that one finding and runs the same check again. | supported | app/verification/loop.py:3-7,287-349 |
| 5 | By default each check gets up to 3 attempts. A strategy that was shortened to fit a small budget gets at most 2. | supported | app/config.py:353; app/verification/loop.py:133-141 |
| 6 | Vectorae runs all 10 checks even if an earlier one fails. | supported | app/verification/loop.py:258-353 |
| 7 | If every check ends in PASS, the strategy becomes `verified`. | supported | app/verification/loop.py:355-357 |
| 8 | If any check still fails after its attempts, the strategy becomes `needs_human_review`. | supported | app/verification/loop.py:351-357 |
| 9 | Until a strategy is `verified`, Vectorae will not source leads for it or launch a sequence from it. | supported | app/api/leads.py:83-90; app/api/sequences.py:247-251 |
| 10 | 1 Factual accuracy — … estimates are labelled as assumptions. No invented statistics. | supported | app/verification/passes.py:104-107 |
| 11 | 2 ICP fit — … no drift toward excluded audiences. | supported | app/verification/passes.py:108-111 |
| 12 | 3 Channel–message fit — … | supported | app/verification/passes.py:112-115 |
| 13 | 4 Legal & compliance — CAN-SPAM …, GDPR …, cold WhatsApp only through approved templates to opted-in numbers, and no scraping … | supported | app/verification/passes.py:116-121 |
| 14 | 5 Deliverability risk — warm-up ramp, realistic daily caps, bounce-rate pause threshold. No day-one mass sending. | supported | app/verification/passes.py:122-125 |
| 15 | 6 Competitive realism — … | supported | app/verification/passes.py:126-129 |
| 16 | 7 Resource feasibility — … your stated (or a solo founder's) time and budget. | supported | app/verification/passes.py:130-133 |
| 17 | 8 KPI realism — … | supported | app/verification/passes.py:134-137 |
| 18 | 9 Personalization quality — … not generic copy with a first-name token. | supported | app/verification/passes.py:138-140 |
| 19 | 10 Consistency — With past clients: … past-client patterns …. Without past clients: … agrees with the GTM plan. | supported | app/verification/passes.py:144-156 |
| 20 | When research phases give different values for the same fact …, the reviewer is told that the later phase is authoritative. … | supported | app/verification/passes.py:41-58 |
| 21 | (RE-CHECK, rewritten) … the **10x verification loop** card lists every attempt of every check, each marked PASS or FAIL. | supported | app/api/strategies.py:258; app/verification/loop.py:106-130; detail/page.tsx:186-208 |
| 22 | (RE-CHECK, rewritten) A check that took three attempts therefore appears three times (for example FAIL, FAIL, PASS), and a re-verified strategy also keeps the rows from earlier runs. | supported | loop.py:129 (append-only); app/api/strategies.py:372-378 (re-verify does not clear the log) |
| 23 | (RE-CHECK, rewritten) The card does not show the reviewer's reasons; the reason a check failed is shown in the **Review and pass manually** form ("Why it failed"). | supported | detail/page.tsx:197-201 (`pass.fix` is never sent); OverridePassesPanel.tsx:72-76. Note: that form appears only when 1–3 checks failed and Legal & compliance is not among them (verificationReview.ts:27-47). |
| 24 | A check can also stop early, before using all its attempts, for two reasons: | supported | app/verification/loop.py:119-128 |
| 25 | **Conflicting sources.** The proposed fix would put the document back the way it was …. Vectorae stops that check and leaves it for a person. | supported | app/verification/loop.py:319-342 |
| 26 | **Rewrite too long.** … cut off even after one retry with a larger limit. Vectorae leaves the document exactly as it was … and fails that check. | supported | app/verification/loop.py:179-199,293-317 |
| 27 | At least one check still failed. The strategy page shows a **Needs your review** notice. | supported | detail/page.tsx:140-155 |
| 28 | Three options: **Re-verify** …; **Pass the failed checks manually**, if no more than 3 failed, the Legal & compliance check is not one of them …; **Start a new strategy** … | supported | app/api/strategies.py:333-379; app/services/verification_override.py:24-28 |
| 29 | Resume is not available from this status, because the research is already complete. | supported | app/api/strategies.py:295-300 |
| 30 | Press **Re-verify** on the strategy page (it appears only for `needs_human_review`). | supported | ReverifyStrategyButton.tsx:13-14,48-55 |
| 31 | **Attempts per check**, from 1 to 5. The form starts at 4. | supported | ReverifyStrategyButton.tsx:28,32; app/api/schemas.py:89-93 |
| 32 | An optional **New budget $**, which must be more than the strategy has already spent. | supported | app/api/strategies.py:361-370 |
| 33 | Press **Confirm re-verify**. | supported | ReverifyStrategyButton.tsx:92 |
| 34 | The finished research is reused, not repeated, but the checks cost AI spending again and count toward your daily AI limit. | supported | app/api/strategies.py:341-352,377-378; app/services/usage_meter.py:55 |
| 35 | Every check is judged from scratch, and the strategy becomes `verified` only if all 10 pass. Otherwise it returns to `needs_human_review`. | supported | app/api/strategies.py:346-348; app/verification/loop.py:355-357 |
| 36 | Press **Review and pass manually**. It is offered when the strategy is `needs_human_review` or `budget_exhausted`, and also while it shows `verifying`. | supported | detail/page.tsx:140-159; OverridePassesPanel.tsx:37-55; frontend/src/lib/verificationReview.ts:65 |
| 37 | For a `verifying` strategy, Vectorae refuses the sign-off until nothing has been logged for 15 minutes … | supported | app/services/verification_override.py:31-34,110-128 |
| 38 | If the Legal & compliance check is among the failures, the button is replaced by a note saying it cannot be passed manually. | supported | frontend/src/lib/verificationReview.ts:30-36; OverridePassesPanel.tsx:41-47 |
| 39 | The form lists each failed check and why it failed. | supported | OverridePassesPanel.tsx:68-79 |
| 40 | Write why the failure is acceptable, in at least 20 characters. This reason is kept on record. | supported | app/services/verification_override.py:25,140-144,189; OverridePassesPanel.tsx:80-81 |
| 41 | Tick the box confirming you have checked these points yourself, and that the document is not independently verified. | supported | OverridePassesPanel.tsx:90-94; app/api/strategies.py:401-406 |
| 42 | Press **Pass manually**. | supported | OverridePassesPanel.tsx:96-100 |
| 43 | It is based on the latest verification run that reached all 10 checks. A later run that stopped partway is ignored. | supported | app/services/verification_override.py:81-89,148-152 |
| 44 | You must pass exactly the checks that failed, all at once. | supported | app/services/verification_override.py:168-171 |
| 45 | No more than 3 checks may have failed. With more, re-verify or fix the strategy. | supported | app/services/verification_override.py:156-159 |
| 46 | **The Legal & compliance check can never be passed manually.** It has to pass verification. | supported | app/services/verification_override.py:161-166 |
| 47 | The strategy then becomes `verified`. | supported | app/api/strategies.py:420 |
| 48 | The original FAIL results stay in the log. | supported | app/services/verification_override.py:3-8,175-195 |
| 49 | Each manually passed check shows **PASS (manual)** with "passed manually by" your email address and your reason … | supported | detail/page.tsx:192-205; verification_override.py:184-189 |
| 50 | … and the decision is also written to the security audit trail. | supported | app/api/strategies.py:422-426 |
| 51 | It varies with how many checks fail and need a rewrite. | supported | app/verification/loop.py:268-349 |
| 52 | Vectorae's own notes estimate one check-and-fix cycle at about 3 to 4 minutes. | supported | app/services/verification_override.py:32 |
| 53 | Each verification run has the same 2-hour time limit and automatic retries as the research pipeline. | supported | app/workers/tasks.py:186-188,209-225 |

Summary (after re-check): 53 supported, 0 unsupported, 0 contradicted.

---

### 06-lead-sourcing-and-email-verification.md
| # | Sentence (verbatim, may be shortened with …) | Verdict | Evidence (path:line) / what the code says |
|---|---|---|---|
| 1 | Once a strategy is verified, Vectorae can find people who match it, look up their email addresses and check that those addresses accept mail. | supported | app/workers/lead_tasks.py:3-4 |
| 2 | In the **1. Find leads** card, enter **How many leads** (1 to 25 per click; the form starts at 5) and press **Find leads**. | supported | OutreachPanel.tsx:103-123; frontend/src/lib/leadOutreach.ts:10-11,21-25 |
| 3 | Vectorae shows "Finding leads. This takes a few minutes." and the list fills in as leads move through the stages. | supported | OutreachPanel.tsx:35-50 |
| 4 | Lead sourcing only works for a strategy whose status is `verified`. For any other status the request is refused. | supported | app/api/leads.py:83-90 |
| 5 | Vectorae builds the search from the strategy's research: job titles, industries, locations, company size ranges and keywords from the ideal customer profile. | supported | app/api/schemas.py:155-158; app/api/leads.py:105 |
| 6 | Through the API a request can ask for up to 1,000 leads, but one sourcing run is capped at 200 by default. | supported | app/api/schemas.py:153; app/config.py:87; app/api/leads.py:114-116 |
| 7 | By default you can start 5 sourcing requests per hour. | supported | app/core/config.py:200; app/api/leads.py:80 |
| 8 | Each lead uses paid Apollo and Hunter credits, so the screen suggests starting small. | supported | OutreachPanel.tsx:106-109 |
| 9 | Search results are cached for 1 day, and enrichment, email-finding and email-check results for 30 days … (an email check repeated within 30 days returns the earlier result). | supported | app/config.py:79-80; app/integrations/apollo.py:90-92,124-126; app/integrations/hunter.py:60-62,70-72; app/integrations/plumbing.py:195,252-253 |
| 10 | Each sourcing request runs five stages in order: | supported | app/workers/lead_tasks.py:3-4,515-523 |
| 11 | **Sourcing.** Apollo is searched for people matching the profile. | supported | app/workers/lead_tasks.py:204-209; app/config.py:85 |
| 12 | **Enriching.** … more detail from Apollo, such as company domain and profile information. | supported | app/workers/lead_tasks.py:256-298 |
| 13 | **Finding emails.** If a person has no email address yet, Hunter tries to find one … If none is found, the lead is dropped. | supported | app/workers/lead_tasks.py:318-348 |
| 14 | **Verifying.** Hunter checks every email address. | supported | app/workers/lead_tasks.py:374-407 |
| 15 | **Finalizing.** Counts are recorded, and the surviving leads are given an AI booking-likelihood score. | supported | app/workers/lead_tasks.py:410-434; app/services/lead_scoring.py:260-261 |
| 16 | Each lead is saved as it finishes each stage, so a stage that is interrupted can resume without creating duplicates. | supported | app/workers/lead_tasks.py:6-11,242,307,400 |
| 17 | The same person is never stored twice in one strategy: … same email address, or the same record from the same provider, and the database itself enforces this. | supported | app/db/models.py:1062-1063; app/workers/lead_tasks.py:155-168 |
| 18 | The same person can appear in two different strategies. | supported | app/db/models.py:1062-1063 (scoped by strategy_id) |
| 19 | `sourced` — Found by the search. | supported | app/workers/lead_tasks.py:238 |
| 20 | `enriched` — Details added. | supported | app/workers/lead_tasks.py:298 |
| 21 | `email_found` — Has an email address that has not been checked yet. | supported | app/workers/lead_tasks.py:331-351 |
| 22 | `verified` — Hunter reported the address as deliverable. | supported | app/integrations/base.py:70-77 |
| 23 | `flagged` — Hunter reported the address as risky, or could not tell. | supported | app/integrations/base.py:70-77 |
| 24 | `dropped` — Undeliverable, suppressed, no email found, a duplicate, removed by you, or erased. | supported | lead_tasks.py:284,341-344,366-367; app/api/leads.py:340; app/api/ui_support.py:49-54 |
| 25 | `contacted` — At least one message has been sent. | supported | app/workers/outreach_tasks.py:529-530 |
| 26 | `replied` — The person replied. | supported | app/workers/outreach_tasks.py:1108 |
| 27 | `meeting_booked` — The person booked a meeting. | supported | app/api/webhooks.py:154 |
| 28 | It means Hunter's check returned "deliverable" for that email address. | supported | app/integrations/hunter.py:66-83; base.py:70-77 |
| 29 | It is the provider's verdict at the time of the check, not a guarantee that a future email will arrive. | supported | app/workers/lead_tasks.py:387-392 |
| 30 | **Risky** addresses, and addresses Hunter could not judge, become `flagged`. They are left for you to decide on. | supported | app/integrations/base.py:70-77 |
| 31 | … you can move the lead to `verified` (and a verified lead back to `flagged`) on the **Pipeline** board. | supported | app/api/ui_support.py:52-53; frontend/src/lib/api/leads.ts:42-43; pipeline/page.tsx:194-209 |
| 32 | **Undeliverable** addresses become `dropped`. | supported | app/integrations/base.py:75 |
| 33 | (RE-CHECK, rewritten) A dropped lead is never enrolled in a new sequence. | **contradicted** | The app's launch form enrolls only `verified` leads (leadOutreach.ts:39-41; sequences.py:139-143 default). But `POST /sequences/{id}/enroll` accepts any `lead_statuses` list with no validation (app/api/sequences.py:139-143), and `enroll_leads` enrolls whatever statuses it is given (sequence_engine.py:202-216). Suppression is still checked (227-228), but a lead dropped by **Remove** is not suppressed. Correct: "The app never enrolls a dropped lead. Through the API, an enroll request can name other statuses, including `dropped`, and those leads will be enrolled unless they are suppressed." (Or simpler: "When you launch from the app, dropped leads are never enrolled.") |
| 34 | An address that Hunter built from a name and a company domain is recorded as found that way, separately from one a provider confirmed. | supported | app/workers/lead_tasks.py:352-359 |
| 35 | By default, launching a sequence enrolls only `verified` leads that have an email address. | supported | app/api/sequences.py:139-143; app/services/sequence_engine.py:202-216 |
| 36 | The launch form on the strategy page says how many verified leads will be contacted. | supported | OutreachPanel.tsx:170-175,209 |
| 37 | The suppression list holds people who must not be contacted. | supported | app/workers/lead_tasks.py:61-142 |
| 38 | A person is added when they unsubscribe, reply asking to stop, send STOP on WhatsApp, or when you erase their lead. | supported | sequence_engine.py:484-508; webhooks_whatsapp.py:455-469; app/api/leads.py:292-323 |
| 39 | Suppression covers their email address, phone number and LinkedIn profile, so opting out on one channel stops all of them. | supported | app/services/consent.py:219-264; app/workers/lead_tasks.py:113-142 |
| 40 | (checks the list) when a lead is first found; | supported | app/workers/lead_tasks.py:221 |
| 41 | again whenever a new email or phone number is discovered for them; | supported | app/workers/lead_tasks.py:283,340 |
| 42 | when a lead is enrolled in a sequence; | supported | app/services/sequence_engine.py:227-228 |
| 43 | immediately before every single message is sent. | supported | app/workers/outreach_tasks.py:187-196 |
| 44 | A suppressed lead is skipped or dropped, never contacted. | supported | lead_tasks.py:221-223,283-285; outreach_tasks.py:187-196 |
| 45 | The list applies across your whole Vectorae deployment. | supported | app/workers/lead_tasks.py:124-142 (no owner filter); frontend/src/lib/settings-tabs.ts:4-7 |
| 46 | Administrators can view it in **Settings** under the **Suppression** tab; other users do not see that tab. | supported | frontend/src/lib/settings-tabs.ts:21-35 |
| 47 | Your plan limits the number of leads per strategy. Dropped leads do not count. | supported | app/workers/lead_tasks.py:179-201 |
| 48 | Plan table (Free 100, Starter 500, Growth 2,500, Pay per meeting 1,000, Scale 10,000, Pro/Enterprise no limit) | supported | app/core/plans.py:56,73,92,108,127,143,165 |
| 49 | When a strategy is full, a new sourcing request is refused with an upgrade message. | supported | app/api/leads.py:95-103 |
| 50 | When it is nearly full, Vectorae asks for no more leads than the room left, and checks again for each lead it adds. | supported | app/api/leads.py:114-116; app/workers/lead_tasks.py:211-220 |
| 51 | (RE-CHECK, rewritten) **Remove** … marks the lead `dropped`, so it is not included when you launch. | supported | app/api/ui_support.py:133-148; leadOutreach.ts:39-41 |
| 51a | (RE-CHECK, new) It does not stop a sequence the lead is already in; that sequence keeps sending to them. | supported | app/api/ui_support.py:133-148 (no enrollment change); outreach_tasks.py:160-196 (no lead-status check) |
| 51b | (RE-CHECK, new) To stop contacting someone who is already enrolled, use **Delete (GDPR erasure)** below. | supported | app/api/leads.py:313-340 (address erased and suppressed); outreach_tasks.py:185-196 (the next due message is cancelled and the enrollment stopped) |
| 52 | A dropped lead cannot be moved back to another status. | supported | app/api/ui_support.py:54; frontend/src/lib/api/leads.ts:44 |
| 53 | **Delete (GDPR erasure)** … permanently erases the lead's personal data and adds their email address, phone number and LinkedIn profile to the suppression list, so they are never contacted or sourced again. | supported | app/api/leads.py:275-341; pipeline/page.tsx:127-140 |
| 54 | A record that the erasure happened is kept. | supported | app/api/leads.py:306-311 |
| 55 | You confirm with **Delete**. | supported | pipeline/page.tsx:134-141 |
| 56 | (RE-CHECK, rewritten) Not as leads. Leads come only from the sourcing process described above, and there is no way to import your own contacts as leads. | supported | app/workers/lead_tasks.py:227 |
| 57 | (RE-CHECK, rewritten) On the Growth, Scale, Pro and Enterprise plans you can upload your LinkedIn connections on the **Network** page and message them there, but they do not become leads … | supported | app/core/plans.py:180-186; app/api/linkedin_network.py:68-87; app/services/network_messages.py:1-9; frontend/src/components/shell/nav.ts:50 |
| 58 | Not yet. (Apollo and Hunter verified against live services?) | supported | docs/VERIFICATION_REPORT.md:579 |
| 59 | Both integrations were built from the providers' documentation and tested against simulated responses. Several request details are still marked … as needing confirmation …, and neither has been run end to end against the live service. | supported | app/integrations/apollo.py:8 (9 TODOs); app/integrations/hunter.py:9 (7 TODOs); docs/VERIFICATION_REPORT.md:579 |

Summary (after re-check): 60 supported, 0 unsupported, 1 contradicted (#33). New sources (app/api/linkedin_network.py, app/services/network_messages.py, frontend/src/app/(app)/network/page.tsx) exist.

---

### 07-personalization-and-claim-verification.md
| # | Sentence (verbatim, may be shortened with …) | Verdict | Evidence (path:line) / what the code says |
|---|---|---|---|
| 1 | Vectorae writes each outreach message for one person, using what it actually knows about them. | supported | app/services/message_personalization.py:97-174 |
| 2 | Before a message is sent, every factual claim it makes about that person or their company is checked against stored data, and anything unsupported is taken out. | supported | app/services/claim_verification.py:1-20 (default on; admin switch `claim_verification_enabled`, system_settings.py:142) |
| 3 | Messages are written at the moment they are sent, not when the sequence is created. | supported | app/services/sequence_engine.py:323-324; app/workers/outreach_tasks.py:554-589 |
| 4 | the step's **brief** … | supported | message_personalization.py:31-32 |
| 5 | the strategy's **messaging research** (the summary of research phase 6); | supported | message_personalization.py:47-59 |
| 6 | the lead's **name, title, company** and enrichment details; | supported | message_personalization.py:37-41,122-127 |
| 7 | any recent **LinkedIn posts** and **company news** it has stored for the lead; | supported | message_personalization.py:132; personalization_context.py:19-22 |
| 8 | your **voice profile**, if you set one up; | supported | message_personalization.py:137-148 |
| 9 | the sequence's booking link, if it has one. | supported | message_personalization.py:128-131; outreach_tasks.py:571 |
| 10 | The AI is asked for a plain-text email under 140 words, with no placeholders such as [Name]. | supported | message_personalization.py:18-27 |
| 11 | It does not write the unsubscribe footer; Vectorae adds the compliant footer itself. | supported | message_personalization.py:24-26; outreach_tasks.py:585 |
| 12 | The exact subject and body are saved on the message before it is sent … | supported | outreach_tasks.py:414,586-588 |
| 13 | **Enrichment** gathered during lead sourcing (from Apollo). | supported | app/workers/lead_tasks.py:256-298 |
| 14 | Right before writing an email, Vectorae fetches the lead's three most recent posts if its stored copy is more than 7 days old. | supported | personalization_context.py:1-6,37,75-92; app/integrations/linkedin_posts.py:28 |
| 15 | It reads them through Unipile, which needs a connected LinkedIn account, or through a RapidAPI scraper as a fallback. | supported | linkedin_posts.py:6-9,153-164 (Unipile can also use a deployment "reader" account) |
| 16 | When posts are available, the email's first line is asked to reference one specific detail from them. | supported | personalization_context.py:19-21 |
| 17 | **Company news.** News from NewsAPI from the last 30 days, refreshed if the stored copy is more than 3 days old. | supported | personalization_context.py:5-6,38-39,107-112 |
| 18 | An article is kept only if the company name appears in its title or description, and the AI is told to use it only if it plausibly concerns this company. | supported | app/integrations/newsapi.py:37-80; personalization_context.py:20-22,170-171 |
| 19 | In **Settings**, on the **Voice** tab, you can paste up to 5 writing samples. Vectorae extracts a style profile from them … | supported | app/services/style_profile.py:1-6,27,59-60; frontend/src/components/settings/VoiceSettings.tsx:3 |
| 20 | Only the profile is used when writing; your samples are stored for editing but never go into an outreach prompt. | supported | style_profile.py:13-15; VoiceSettings.tsx:6,38 |
| 21 | If a provider is not set up or fails, Vectorae writes the email without that input. It never holds back a send because of it. | supported | personalization_context.py:13-17,126-130 |
| 22 | The LinkedIn post and news integrations have not yet been verified against the live services. | supported | docs/VERIFICATION_REPORT.md:579 |
| 23 | Several request details for the LinkedIn post providers are still marked in the code as needing confirmation. | supported | app/integrations/linkedin_posts.py:14,89,115 |
| 24 | You can see what Vectorae has stored on a lead's detail page, on the **Personalization** tab (**Company news** and **Recent LinkedIn posts**). | supported | leads/detail/page.tsx:53,134-136; components/leads/PersonalizationPanel.tsx:51,106 |
| 25 | Every AI-written message goes through a claim check after it is written and before it is sent. | supported | outreach_tasks.py:576-584 (default on; see #2) |
| 26 | The check looks for claims … in these categories: funding, headcount, hiring, a job change, news, metrics, expansion, and references to their own content … | supported | claim_verification.py:61-90 |
| 27 | stored data of the right kind mentions the topic (for example, a funding claim needs funding evidence); | supported | claim_verification.py:31-33,94-110 |
| 28 | every specific detail in the sentence, such as a number, an amount, a "Series B", a quoted phrase or a proper name, appears in that stored data. | supported | claim_verification.py:34-38 |
| 29 | The only evidence that counts is what Vectorae has stored on the lead … Nothing new is looked up during the check. | supported | claim_verification.py:12-20,182-200 |
| 30 | the sentence is **removed**; | supported | claim_verification.py:370-372 |
| 31 | … where removing it would break the message (the opening line, the subject line, or a WhatsApp template variable), it is **rewritten** to a neutral line that asserts nothing. | supported | claim_verification.py:7-9,297-300,364-369,448-489 |
| 32 | A replaced subject line becomes "Quick question". | supported | claim_verification.py:58,476 |
| 33 | If the check itself fails with an error, every claim it detected by its rules is removed rather than sent unchecked. | supported | claim_verification.py:40-41,466-469 |
| 34 | … Vectorae also asks the AI to find claims the rules missed. This is on by default; an administrator can turn it off, and it costs one extra AI call per message. | supported | app/services/system_settings.py:146; claim_verification.py:396-410 |
| 35 | The check runs on email, on WhatsApp free-form replies and template variables (the approved template text itself is fixed …), and on LinkedIn messages. | supported | outreach_tasks.py:581-584,621-653,784-786 (phone call scripts are also checked, 867-888) |
| 36 | No. The check only looks at sentences about the prospect: second person ("you", "your"), their name, or their company. | supported | claim_verification.py:22-26,303-307 |
| 37 | A sentence such as "We helped 40 agencies grow" is a claim about you, and it is your responsibility … | supported | claim_verification.py:24-26 |
| 38 | Open the lead's detail page and choose the **Claim checks** tab. For each message you see either "All claims verified" or how many were removed. | supported | leads/detail/page.tsx:58; components/leads/ClaimChecksPanel.tsx:46-47 |
| 39 | the verdict (verified, stripped or rewritten) and the category; | supported | ClaimChecksPanel.tsx:55-58 |
| 40 | for a verified claim, the stored data that backed it; | supported | ClaimChecksPanel.tsx:64-68 |
| 41 | for an unsupported claim, the original text struck through, what it was replaced with, and what could not be found in stored data. | supported | ClaimChecksPanel.tsx:61-79 |
| 42 | A variable mapped to a lead field (full name, first name, title, company or email) is filled straight from the lead record, with no AI call. | supported | message_personalization.py:208-247 (an empty lead field falls back to an AI brief, 248-250) |
| 43 | Any other variable is filled by the AI from the lead's data and the messaging research, and it is told never to invent facts, names or statistics. | supported | message_personalization.py:181-189,250-271 |
| 44 | If a variable cannot be filled, the message is not sent with an empty slot. | supported | message_personalization.py:233-235,267-275; outreach_tasks.py:482-485 |
| 45 | On a lead's detail page, the **Overview** tab includes **Why this prospect**. | supported | leads/detail/page.tsx:50,213-221 |
| 46 | It explains the lead's F-P-T-A score, which rates four things from 0 to 100: | supported | app/services/fpta_scoring.py:1-22; app/api/leads.py:218-231 |
| 47 | Fit / Problem / Timing / Access definitions | supported | app/services/fpta_scoring.py:7-16 |
| 48 | The overall score weights Fit and Problem at 30% each and Timing and Access at 20% each. | supported | app/services/fpta_scoring.py:54 |
| 49 | Leads are scored when they are enrolled in a sequence. | supported | app/services/sequence_engine.py:242-248 |
| 50 | Each dimension starts from a baseline computed from stored data, and one AI call per batch of 10 leads writes an explanation and may move each baseline by at most 15 points. | supported | app/services/fpta_scoring.py:18-25,56-57 |
| 51 | The panel names the strongest and weakest dimension, suggests a next step when the weakest is below 60, and shows the evidence behind every dimension. | supported | frontend/src/lib/fpta.ts:103-152 |
| 52 | A lead that has not been scored says "Not scored yet", and a score made without the AI step is labelled as such. | supported | frontend/src/lib/fpta.ts:123,154-157; WhyThisProspectPanel.tsx:114-116 |

Summary: 52 supported, 0 unsupported, 0 contradicted. (RE-CHECK: file unchanged since the first pass.)

---

### 08-sequences-and-follow-ups.md
| # | Sentence (verbatim, may be shortened with …) | Verdict | Evidence (path:line) / what the code says |
|---|---|---|---|
| 1 | A sequence is the series of messages Vectorae sends to each lead in a strategy. | supported | app/api/sequences.py:116-121 |
| 2 | A sequence belongs to one strategy and has numbered steps. | supported | app/api/sequences.py:146-167 |
| 3 | a **brief** … It is not the final text; Vectorae writes the final message for each lead at send time. | supported | app/api/sequences.py:84; app/services/sequence_engine.py:323-324 |
| 4 | a **delay**: how many days to wait after the previous step is sent (0 to 60). | supported | app/api/sequences.py:86; sequence_engine.py:325 |
| 5 | a **channel**: email by default. Steps can also use WhatsApp, LinkedIn or phone, if your plan includes them. A step without its own channel uses the sequence's channel. | supported | app/api/sequences.py:88-90,118,224-225; sequence_engine.py:336-338 |
| 6 | optionally a **variant** label, for testing different versions of a step. | supported | app/api/sequences.py:85 |
| 7 | On a verified strategy's page, after finding leads, use the **2. Write the email and launch** card: | supported | OutreachPanel.tsx:160-163 |
| 8 | Enter a **Sequence name**. | supported | OutreachPanel.tsx:176-179 |
| 9 | Under **First email: what should it say?**, describe the first email … | supported | OutreachPanel.tsx:181-186 |
| 10 | Optionally add a **Follow-up email** and the **Days to wait before the follow-up** (the form starts at 3). | supported | OutreachPanel.tsx:30,187-197 |
| 11 | Tick the box confirming you may lawfully email each person on the list. | supported | OutreachPanel.tsx:198-206 |
| 12 | Press **Launch to N lead(s)**. | supported | OutreachPanel.tsx:207-210 |
| 13 | In the app today, this creates an email-only sequence with one or two steps. | supported | frontend/src/lib/leadOutreach.ts:43-54; OutreachPanel.tsx:68-71 |
| 14 | Longer sequences, and steps on other channels, are created through the Vectorae API, which accepts up to 20 steps numbered 1, 2, 3 … with no gaps. | supported | app/api/sequences.py:83,120,164-167 |
| 15 | Plan table (Free 5 / Gmail; Starter 10 / Gmail, WhatsApp; Pay per meeting 10 / +LinkedIn; Growth 15 / +LinkedIn; Scale, Pro, Enterprise no limit / +phone) | supported | app/core/plans.py:57-58,74-75,93-94,109-110,128-129,144-149,166-167 |
| 16 | These are checked when the sequence is created and again at every launch, so a sequence built on a higher plan cannot be launched after a downgrade. | supported | app/api/sequences.py:57-79,224-225,300,401 |
| 17 | A sequence over the limit is refused with an upgrade message. | supported | app/core/plans.py:279-300; app/api/sequences.py:71-72 |
| 18 | In order, a launch is refused if: phone not verified; strategy not `verified` or campaign paused; outside plan; pre-launch review blocking problem. | supported | app/api/sequences.py:298-303,247-255 |
| 19 | The **pre-launch review** scans … spam and pressure phrases, compliance problems (…deceptive subject line, or a WhatsApp step without an approved template), and briefs that ask the writer to state facts about the prospect. | supported | app/services/adversarial_review.py:1-14,59-71,184-207 (a missing template blocks; a pending one is a warning only) |
| 20 | Only blocking findings stop the launch. | supported | app/services/adversarial_review.py:15-19; app/api/sequences.py:258-268 |
| 21 | A workspace owner or manager can override them with a written reason of at least 10 characters. | supported | app/services/adversarial_review.py:57,321-327; app/api/sequence_reviews.py:57-60 |
| 22 | Changing the content after an override brings the review back. | supported | app/services/adversarial_review.py:22-24,310-318 |
| 23 | You can see the review under **Campaigns**, on the **Sequences** tab. | supported | campaigns/page.tsx:405-407,554-555 |
| 24 | If you are an SDR in a workspace that requires approval, your first launch is sent to a manager instead: "Sent to a manager for approval. Nothing is sent until they approve." | supported | app/api/sequences.py:330-362; OutreachPanel.tsx:78-80 |
| 25 | On launch, Vectorae enrolls the strategy's `verified` leads that have an email address (or … LinkedIn profile). It skips anyone suppressed or already enrolled, and schedules step 1. | supported | app/services/sequence_engine.py:193-240 |
| 26 | If your sending domain has deliverability problems, the launch still goes ahead but shows a warning. | supported | app/api/sequences.py:307-313 |
| 27 | **Step 1** is scheduled for the next moment inside the send window. | supported | sequence_engine.py:325-326 (smart send time may hold it, #30) |
| 28 | **Each later step** is scheduled when the previous step is actually sent: its delay in days is added, then the time is moved into the next send window. | supported | sequence_engine.py:325,352-386 |
| 29 | The send window is business hours in the lead's own time zone, 09:00 to 17:00 by default, with weekends skipped. A lead with no known time zone uses the deployment's fallback zone (UTC by default). | supported | app/config.py:109-112; sequence_engine.py:64-102 |
| 30 | If smart send time is turned on for the campaign, a step may be held … for up to 72 hours by default. | supported | app/services/send_windows.py:160-181; system_settings.py:72 |
| 31 | Every send also passes the daily cap, the suppression check and, where triggered, the send-review queue. | supported | outreach_tasks.py:187-196,300-352,416-432 |
| 32 | Messages over the day's cap wait for the next day; they are not dropped. | supported | outreach_tasks.py:300-308,339-352 |
| 33 | The lead replies (interested, question, objection or not interested) → All of that lead's sequences stop, on every channel. | supported | outreach_tasks.py:1104-1108,1170-1173,1224-1226 |
| 34 | The lead unsubscribes or asks to stop → Suppressed everywhere; all sequences stop immediately. | supported | sequence_engine.py:484-508 |
| 35 | An email bounces → The lead is dropped and their sequences stop. | supported | sequence_engine.py:511-524 |
| 36 | An out-of-office reply → Sequences pause for 7 days by default, then continue. | supported | app/config.py:117; outreach_tasks.py:1095-1102; sequence_engine.py:300-312 |
| 37 | A meeting is booked on Vectorae's own calendar → Sequences pause. If the meeting is cancelled they resume; otherwise they resume a day after the meeting ends … | supported | sequence_engine.py:611-685; app/workers/calendar_tasks.py:199-204,287 |
| 38 | A meeting is booked through Calendly → Sequences stop. | supported | app/api/webhooks.py:3,154-165 |
| 38a | (RE-CHECK, new) (The Calendly integration has not yet been verified against the live service.) | supported | docs/VERIFICATION_REPORT.md:579 |
| 39 | The lead is suppressed by the time a message is due → That message is cancelled and the sequence stops. | supported | outreach_tasks.py:187-196 |
| 40 | An automated reply (ticket receipts, no-reply bots) → Nothing changes; it is stored but not treated as a reply. | supported | outreach_tasks.py:1073-1076; reply_classification.py:43-44 |
| 41 | … After a lead has had 4 unanswered sends (the default), a lead judged to have gone cold may have its sequence paused ("cooling") or stopped ("archived"). | supported | app/services/conversion_probability.py:27-35,248-258; system_settings.py:158-170 |
| 42 | A stopped sequence can never send to that lead again. | supported | sequence_engine.py:252-279; outreach_tasks.py:173-177 |
| 43 | Automatic follow-ups are separate from step delays. They catch a lead whose sequence is still active but has nothing queued, for example because a send failed permanently, a WhatsApp step needed a template, or a step was deleted. | supported | outreach_tasks.py:1286-1307,1440-1444 |
| 44 | Every 30 minutes, Vectorae looks for active sequences where the last message has had no reply for longer than that step's follow-up delay (72 hours by default; you can set 1 to 2,160 hours). | supported | app/config.py:326; celery_app.py:256-262; app/api/sequences.py:103-108,495-505; outreach_tasks.py:1450-1458 |
| 45 | If the sequence has a next step, that step is sent. | supported | outreach_tasks.py:1515-1522 |
| 46 | If it does not, Vectorae writes a follow-up from the lead's own message history and your product description, on the same channel as the last message, and sends it through the normal checks. | supported | outreach_tasks.py:1523-1567; message_personalization.py:355-421 |
| 47 | It does not write automatic follow-ups for WhatsApp, because a WhatsApp first contact needs an approved template. | supported | outreach_tasks.py:1529-1537 (an existing WhatsApp next step is still sent) |
| 48 | No follow-up goes to a lead who has replied, or from a paused campaign. | supported | outreach_tasks.py:1458-1467,1506-1513 |
| 49 | … go to **Campaigns**, choose the strategy, open the **Sequences** tab, and use **Auto follow-up** and **after N hours of silence** under each step. | supported | campaigns/page.tsx:340-359,395 |
| 50 | When every step has been sent to a lead, their sequence is marked completed. Vectorae does not keep following up after that. | supported | sequence_engine.py:378-383; outreach_tasks.py:1309-1315 |
| 51 | A separate re-engagement feature can send one more email to leads who finished without replying, but it is off for every campaign until an owner or manager turns it on. | supported | app/services/reengagement.py:1-26,73 |
| 52 | Vectorae also reports a completion rate, and lists each reason a sequence ended early. | supported | app/services/sequence_completion.py:1-27; app/api/sequences.py:549-562 |
| 53 | A sequence where every step was skipped … is flagged for your attention. | supported | sequence_engine.py:405-420 |
| 54 | Skipped steps do not count as sent. | supported | sequence_engine.py:352-371,389-402 |

Summary (after re-check): 55 supported, 0 unsupported, 0 contradicted. New sources app/integrations/calendly.py and docs/VERIFICATION_REPORT.md exist.

---

### 09-email-sending-gmail.md
| # | Sentence (verbatim, may be shortened with …) | Verdict | Evidence (path:line) / what the code says |
|---|---|---|---|
| 1 | Vectorae sends outreach email from the Gmail account you connect, automatically, inside a send window and a daily limit that grows slowly while the account warms up. | supported | outreach_tasks.py:70-85,268-352; sequence_engine.py:115-123 (D1 caveat) |
| 2 | Go to **Settings** and open the **Integrations** tab. | supported | settings/page.tsx:266-298; settings-tabs.ts:21-23 |
| 3 | On the **Gmail** card, press **Connect**. | supported | settings/page.tsx:322-328 |
| 4 | Vectorae requests permission to send email, read email (to detect replies and bounces), create calendar events (…Google Meet links), and create drafts (…). | supported | app/integrations/gmail.py:39-59 |
| 5 | After you approve, Google sends you to Vectorae's server, which records the connection. … the Gmail card should say "Connected:" followed by your address. | supported | app/api/integrations.py:41-82; settings/page.tsx:304-306 |
| 6 | Vectorae keeps one Gmail connection per user account. Connecting again updates that same connection. | supported | app/db/models.py:1659-1661; gmail.py:170-177 |
| 7 | Your Google access tokens are stored encrypted and refreshed automatically. | supported | gmail.py:170-224 |
| 8 | If you see "Gmail is not configured on the server", your Vectorae deployment has not been set up with Google sign-in credentials yet. | supported | app/api/integrations.py:27-36 |
| 9 | Press **Reconnect** on the Gmail card when: you removed Vectorae's access in your Google account; | supported | settings/page.tsx:322-327 |
| 10 | the card says "Calendar access missing — reconnect to create Google Meet links. Your Gmail access is kept." The button then reads **Reconnect for Calendar**. | supported | settings/page.tsx:308-327; app/integrations/google_meet.py:79-86 |
| 11 | Accounts connected before calendar access was added need this once; | supported | gmail.py:48-52 |
| 12 | Vectorae asks you to "Reconnect Gmail in Settings to allow saving drafts" after a meeting. | supported | frontend/src/lib/meeting-prep.ts:43 |
| 13 | Use **Test** on the Gmail card to check whether the connection is healthy. | supported | settings/page.tsx:271-282,316-321 |
| 14 | If no Gmail account is connected, email steps are not sent. | supported | outreach_tasks.py:70-80 |
| 15 | Each connected Gmail account follows a warm-up ramp, counted per UTC day: 10 emails on the day you connect it; 10 more each day after that; up to a ceiling of 100 emails per day. | supported | app/config.py:106-108; sequence_engine.py:115-134 |
| 16 | These are the deployment's default settings. | supported | app/config.py:106-108 |
| 17 | Reconnecting the same account does not restart the ramp. | supported | gmail.py:174-177 (the row is reused, created_at unchanged); sequence_engine.py:119 |
| 18 | your workspace's **compliance rules**, set by an administrator; (can only lower the cap) | supported | app/services/compliance_rules.py:1-15 |
| 19 | **mailbox health**: a Gmail account with poor deliverability health can be throttled to a lower cap, or paused. | supported | outreach_tasks.py:311-352 |
| 20 | When the day's allowance is used up, or the mailbox is paused, the remaining emails move to the next day's send window. They are deferred, never dropped. | supported | outreach_tasks.py:339-352 |
| 21 | On **Campaigns**, the **Overview** tab's **Gmail** card shows "Today / cap". | supported | campaigns/page.tsx:62-66,512 (see out-of-scope note 6) |
| 22 | 09:00 to 17:00 by default; | supported | app/config.py:109-110 |
| 23 | weekends skipped by default; | supported | app/config.py:112 |
| 24 | leads with no known time zone use the deployment's fallback zone, UTC by default. | supported | app/config.py:111; sequence_engine.py:64-72 |
| 25 | An administrator can change the window for a workspace, a recipient region or a channel, but only within 07:00 to 20:00 local time. | supported | compliance_rules.py:1-20,59-63 |
| 26 | Vectorae checks for due messages every 60 seconds and re-checks every rule at the moment of sending. | supported | app/config.py:116; celery_app.py:226-229; outreach_tasks.py:1-7 |
| 27 | **A footer** with your sender identity (name and postal address) and the line "Don't want these emails? Unsubscribe instantly:" followed by a personal unsubscribe link. | supported | sequence_engine.py:428-444 |
| 28 | The sender identity is a deployment setting; a production deployment refuses to start while it is missing or still the placeholder address. | supported | app/config.py:105; app/core/production_guard.py:220-245,331 |
| 29 | **One-click unsubscribe headers** (`List-Unsubscribe` and `List-Unsubscribe-Post`) … | supported | sequence_engine.py:452-455 |
| 30 | **A regional notice** …: for leads in the EU or UK, a line about legitimate interest and the right to object; for leads in Canada, a line naming the sender and how to unsubscribe. | supported | app/services/compliance_audit.py:49-58 |
| 31 | **An open-tracking pixel**, in an HTML copy of the email, unless open tracking is turned off or the lead is in the EU, EEA or UK. | supported | outreach_tasks.py:590-601; open_tracking.py:76-80; compliance_region.py:134-137 |
| 32 | **Click tracking** is off by default. | supported | app/services/system_settings.py:191 |
| 33 | Clicking the unsubscribe link, or replying with a request to stop, suppresses that person immediately and stops all of their sequences. | supported | app/api/unsubscribe.py:50; sequence_engine.py:484-508; outreach_tasks.py:1084-1088 |
| 34 | Vectorae checks each connected inbox for replies every 5 minutes by default. | supported | app/config.py:115; celery_app.py:230-233 |
| 35 | A delivery-failure notice that it can match to a sent message is treated as a bounce: the lead is dropped and all of their sequences stop. | supported | outreach_tasks.py:1015-1035,1090-1093; reply_classification.py:41-42; sequence_engine.py:511-524 |
| 36 | After each bounce, Vectorae checks the campaign's bounce rate (bounces divided by messages sent across the strategy). | supported | sequence_engine.py:523-543 |
| 37 | Once at least 10 messages have been sent, a bounce rate above **3%** pauses the whole campaign automatically. | supported | app/config.py:113-114; sequence_engine.py:536-550 |
| 38 | Your workspace's compliance rules may set a lower threshold, never a higher one. | supported | sequence_engine.py:544-548; compliance_rules.py:13-15 |
| 39 | You get a notification, and nothing more is sent until a person resumes the campaign. | supported | sequence_engine.py:559-581; outreach_tasks.py:119-120,171-172 |
| 40 | … go to **Campaigns**, open the **Overview** tab, and press **Resume** in the "Campaign paused" notice, which asks you to fix deliverability issues before resuming. | supported | campaigns/page.tsx:492-506 |
| 41 | The notice always shows the default 3% figure, even if your workspace uses a lower threshold. | supported | campaigns/page.tsx:501 (hard-coded "≥ 3%") |
| 42 | If Google rejects the message outright, it is marked failed and is not retried automatically. | supported | gmail.py:286-293 (400/403 = permanent); outreach_tasks.py:494-498 |
| 43 | Other errors are retried later. | supported | outreach_tasks.py:482-485,499-502 |
| 44 | If a send was interrupted at the moment of sending, the message is flagged and never resent automatically … | supported | outreach_tasks.py:150-156 |
| 45 | If you use client workspaces, an email is blocked when your Gmail address's domain is not in that client's sending-domain list. | supported | outreach_tasks.py:319-332 |
| 46 | (RE-CHECK, rewritten) By default Vectorae holds a message when … the lead's job title contains founder or co-founder, owner, a C-level title (CEO, COO, CFO, CTO, CMO, CRO or "Chief …"), president, managing director, partner, VP or vice president, "head of", board member or chair, or when the written copy trips the tone and spam rules. | supported | app/services/send_review.py:86-89,145-148,166-183; system_settings.py:114-125 |
| 46a | (RE-CHECK, new) If most of your prospects are owners or founders, expect many of their messages to wait for approval … | supported | app/services/send_review.py:86-89 (matches "owner" and "founder") |
| 46b | (RE-CHECK, new) … an administrator can turn the job-title rule off. | supported | app/services/system_settings.py:120 (`send_review_vip_titles`); send_review.py:188-193 |
| 47 | Approved messages send as approved. | supported | send_review.py:26-35; outreach_tasks.py:438-445 |
| 48 | Not yet. (Gmail verified against Google's live service?) | supported | docs/VERIFICATION_REPORT.md:579 |
| 49 | It was built from Google's documentation and tested against simulated responses. Some request details are still marked in the code as needing confirmation, and it has not yet been run end to end … | supported | app/integrations/gmail.py:9 (10 TODOs); docs/VERIFICATION_REPORT.md:84,579 |

Summary (after re-check): 51 supported, 0 unsupported, 0 contradicted.

---

### 10-whatsapp-outreach.md
| # | Sentence (verbatim, may be shortened with …) | Verdict | Evidence (path:line) / what the code says |
|---|---|---|---|
| 1 | Vectorae can send outreach on WhatsApp through Meta's WhatsApp Business Cloud API. | supported | app/config.py:135-158; app/integrations/whatsapp.py |
| 2 | … Vectorae enforces them at the moment of sending: a contact needs a recorded opt-in, a first message must use a Meta-approved template, and free-form messages can only go out inside the 24-hour window the contact opens by messaging you. | supported | outreach_tasks.py:218-255; app/api/sequences.py:181-199 |
| 3 | The Free plan is email only. Starter, Growth, Pay per meeting, Scale, Pro and Enterprise include WhatsApp. | supported | app/core/plans.py:58,75,94,110,129,149,167 |
| 4 | This is set up by your administrator in the server settings, not in the app. | supported | app/config.py:135-158; settings/page.tsx:341 |
| 5 | … the **WhatsApp Business** card shows the phone number ID when it is set up, or "Not configured — set WHATSAPP_* env vars on the server" when it is not. | supported | settings/page.tsx:337-341 |
| 6 | Use **Test** on that card to check the connection. | supported | settings/page.tsx:345-348 |
| 7 | There is **one WhatsApp Business number per Vectorae deployment**, and every user in the deployment sends from it. | supported | app/config.py:137; outreach_tasks.py:396-398; sequence_engine.py:162-164 |
| 8 | (RE-CHECK, rewritten) A deployment is intended to serve one customer organization, but public sign-up is open to any email address by default; unless your administrator closes sign-up or limits it to your organization's email domains, other people's accounts on the same deployment would share this number too. | supported | DECISIONS.md:22-26,36-46; app/config.py:434-448; sequence_engine.py:162-164 |
| 9 | **Agencies:** … every client's prospects see the same WhatsApp number. Unlike email, Vectorae has no per-client WhatsApp number. | supported | docs/program/BASELINE.md:92,164 |
| 10 | **Templates are shared.** … Anyone signed in to the deployment can see, create, edit and submit them. | supported | app/api/whatsapp_templates.py:98-106; docs/program/BASELINE.md:106 |
| 11 | **The daily cap is shared.** By default the number sends at most 10 messages on the day of its first WhatsApp send, 10 more each day after that, up to 100 per day, counted across all users. | supported | sequence_engine.py:149-179; app/config.py:156-158 |
| 12 | Messages over the cap wait for the next day's send window; they are not dropped. | supported | outreach_tasks.py:300-308 |
| 13 | Go to **Campaigns**, choose a strategy, and open the **Templates** tab. | supported | campaigns/page.tsx:424,557-558 |
| 14 | **+ New draft** opens an editor. Give the template a name (lowercase letters, digits and underscores, for example `intro_offer`) and a body. | supported | campaigns/page.tsx:103,118-122,189; app/services/whatsapp_templates.py:51-52,91-98 |
| 15 | (RE-CHECK, rewritten) In the current release, a template written in this editor must not contain placeholders such as `{{1}}`: Vectorae requires a description for every placeholder, and this editor cannot add one, so saving fails with "missing variable descriptions" (even though the editor's example text shows `{{1}}`). | supported | campaigns/page.tsx:102-106,129; app/services/whatsapp_templates.py:101-118,151-152 |
| 15a | (RE-CHECK, new) Templates with placeholders come from **Generate with AI** or from the Vectorae API. | supported | app/services/whatsapp_templates.py:383-424; app/api/whatsapp_templates.py:55-63 |
| 16 | Templates created here use the language `en_US` and the category "marketing". | supported | campaigns/page.tsx:104 |
| 17 | **Generate with AI** drafts 2 or 3 candidate templates from the strategy's research. | supported | app/services/whatsapp_templates.py:17,343,399; app/api/whatsapp_templates.py:11-14 (note: every candidate is saved as a draft at once, not only the one you pick) |
| 17a | (RE-CHECK, new) Each draft comes with a description of every placeholder. | supported | app/services/whatsapp_templates.py:407-418 (a candidate whose descriptions do not match is dropped). Note on #17: because invalid candidates are dropped, a run can yield 1 draft. |
| 18 | Choose one and press **Edit & save this draft** … | supported | campaigns/page.tsx:195-206 |
| 18a | (RE-CHECK, new) … keep the same placeholders when you edit it, because the saved descriptions must still match. | supported | campaigns/page.tsx:100-101 (edit sends body only); app/services/whatsapp_templates.py:203-211 |
| 19 | Drafts are never submitted automatically. | supported | app/api/whatsapp_templates.py:13-14,222-228 |
| 20 | **Submit** sends a draft to Meta for review. Meta's review "takes minutes to days". | supported | campaigns/page.tsx:166-170 (toast: "Approval takes minutes to days.") |
| 21 | **Sync status** fetches the latest decision from Meta. | supported | campaigns/page.tsx:176-184,242-245; app/api/whatsapp_templates.py:189-200 |
| 22 | A rejected template shows Meta's reason, and you can edit and resubmit it. | supported | campaigns/page.tsx:227-240 |
| 23 | … the body cannot be empty, must be at most 1,024 characters by default, and its placeholders must run `{{1}}`, `{{2}}`, … in order with no gaps or repeats. | supported | app/services/whatsapp_templates.py:60-88; app/config.py:154 (the code checks the set of numbers, not their order in the text) |
| 24 | The editor reminds you to include "Reply STOP to opt out."; Vectorae does not add this line for you. | supported | campaigns/page.tsx:129-131 (no code appends it) |
| 25 | Editing an approved template creates a new draft version rather than changing the approved one. | supported | app/services/whatsapp_templates.py:169-200 (only via the API: the app shows **Edit** only for draft/rejected, campaigns/page.tsx:234) |
| 26 | Only **approved** templates are sent. Approval is checked again at the moment of sending; if … no longer approved …, that message stops with the status "needs template" … | supported | outreach_tasks.py:242-255 |
| 27 | The launch form on the strategy page creates email sequences only. WhatsApp steps are added through the Vectorae API. | supported | frontend/src/lib/leadOutreach.ts:43-54; app/api/sequences.py:82-120 |
| 28 | (RE-CHECK, rewritten) **Template step:** names any template that has not been rejected (a draft, a submitted one or an approved one) and says how each variable is filled. | supported | app/api/sequences.py:191-220 |
| 28a | (RE-CHECK, new) It only sends once the template is approved. | supported | outreach_tasks.py:242-255 |
| 29 | A variable can be filled from the lead's record (…) or from a short brief that the AI fills …, without inventing facts. If a variable cannot be filled, the message is not sent with an empty slot. | supported | app/services/message_personalization.py:208-276 |
| 30 | **Free-form text step:** only sends inside an open 24-hour window, and can never be the first step of a sequence. | supported | app/api/sequences.py:181-190; outreach_tasks.py:228-241 |
| 31 | Vectorae will not send a WhatsApp message to a contact without a recorded opt-in. | supported | outreach_tasks.py:222-226 |
| 32 | A WhatsApp step for a contact without one is **skipped**, and the sequence carries on …. If every step of a sequence was skipped, the sequence is flagged for your attention. | supported | sequence_engine.py:389-420 |
| 33 | **The contact messages your WhatsApp number first.** If their status was unknown, that message is recorded as an opt-in, with the message ID as evidence. | supported | webhooks_whatsapp.py:471-476; app/services/whatsapp_optin.py:241-260 |
| 34 | (RE-CHECK, rewritten) **Through the API, one contact at a time.** Evidence of where, when and how they agreed is recommended, and is required when the opt-in is recorded as a manual import. | supported | app/api/whatsapp_optin.py:56-66,102-128; app/services/whatsapp_optin.py:129-136 |
| 35 | **Through the API, as a CSV import.** Every row must include evidence; rows without it are rejected with a reason. | supported | app/api/whatsapp_optin.py:257-351 |
| 36 | Vectorae also contains a hosted opt-in page, but the app does not currently give you a way to get a contact's link to it. | supported | app/api/whatsapp_optin.py:211-249 (`optin_url` is defined but never called) |
| 37 | Every opt-in and opt-out is kept as a history that is only ever added to. | supported | app/services/whatsapp_optin.py:1-17 |
| 38 | You can see a contact's current status as **WhatsApp opt-in** when you open a lead on the **Pipeline** page. | supported | pipeline/page.tsx:96-108 |
| 39 | A number on the suppression list cannot be opted in again through Vectorae. | supported | app/services/whatsapp_optin.py:140-147 |
| 40 | When a contact sends you a WhatsApp message, a 24-hour window opens, and each new message from them restarts it. | supported | app/services/whatsapp_window.py:3-10,41-52 |
| 41 | Template messages you send do not open it. | supported | whatsapp_window.py:9-10 |
| 42 | Inside the window, free-form text steps can send; outside it, only templates can. | supported | outreach_tasks.py:228-241 |
| 43 | Vectorae works the window out at the moment of sending, so a free-form message queued while the window was open, but due after it closed, is not sent. It is marked "needs template". | supported | outreach_tasks.py:228-241; whatsapp_window.py:12-14 |
| 44 | On **Campaigns**, the **Overview** tab's **WhatsApp** card shows how many windows are open and how many messages need a template. | supported | campaigns/page.tsx:68-77,513; app/api/strategies.py:594-619 (the "need template" badge appears only when the count is above 0) |
| 45 | The 24-hour length follows Meta's policy as understood when the feature was built and has not been re-checked against Meta's current policy. | supported | whatsapp_window.py:3,25 |
| 46 | … treats these messages as an opt-out …: "stop", "unsubscribe", "opt out", "optout", "cancel", "remove me", "stop messaging me", "no more messages", and any message that starts with "stop" or "unsubscribe" (capital letters do not matter). | supported | webhooks_whatsapp.py:57-70 |
| 47 | records the contact as opted out; | supported | webhooks_whatsapp.py:463-467; whatsapp_optin.py:176-198 |
| 48 | suppresses their phone number, email address and LinkedIn profile; | supported | whatsapp_optin.py:209-219; consent.py:219-264 |
| 49 | stops all of their sequences on every channel. | supported | webhooks_whatsapp.py:468-469; sequence_engine.py:505-507 |
| 50 | If the AI later reads another reply as a request to stop, it has the same effect. | supported | outreach_tasks.py:1145-1153 |
| 51 | A STOP from a number Vectorae cannot match to one lead still suppresses that number. | supported | webhooks_whatsapp.py:396-406,361-378 |
| 52 | If an opted-out contact messages you again, they are not opted back in automatically. | supported | whatsapp_optin.py:241-250; webhooks_whatsapp.py:472-476 |
| 53 | WhatsApp replies are classified the same way as email replies. | supported | outreach_tasks.py:1122-1132 |
| 54 | A real reply stops all of the contact's sequences, including pending email steps. | supported | outreach_tasks.py:1170-1173 |
| 55 | An out-of-office reply pauses them. | supported | outreach_tasks.py:1161-1168 |
| 56 | Vectorae never replies to people automatically. | supported | outreach_tasks.py:1131 |
| 57 | A reply is matched to a lead by phone number. If any lead … has been sent a WhatsApp message, it goes to the one messaged most recently; otherwise, if exactly one lead has the number …; … several leads … none was messaged, the reply is not attached to any lead. | supported | webhooks_whatsapp.py:321-358 |
| 58 | If Meta reports that a message failed to deliver, it is handled like an email bounce. | supported | webhooks_whatsapp.py:276-299 |
| 59 | Not yet. (WhatsApp verified against Meta's live service?) | supported | docs/VERIFICATION_REPORT.md:579 |
| 60 | The integration was built from Meta's documentation and tested against simulated responses. Many request details are still marked in the code as needing confirmation …, and it has not been run end to end … | supported | app/integrations/whatsapp.py (17 TODOs); app/api/webhooks_whatsapp.py (7 TODOs); app/services/whatsapp_templates.py (3 TODOs) |

Summary (after re-check): 64 supported, 0 unsupported, 0 contradicted. New source app/api/auth.py exists.

---

## Totals (01–10), final state after the re-check on 2026-10-11

| Article | Supported | Unsupported | Contradicted |
|---|---|---|---|
| 01 | 40 | 0 | 0 |
| 02 | 40 | 0 | 0 |
| 03 | 55 | 0 | 0 |
| 04 | 54 | 0 | 0 |
| 05 | 53 | 0 | 0 |
| 06 | 60 | 0 | 1 |
| 07 | 52 | 0 | 0 |
| 08 | 55 | 0 | 0 |
| 09 | 51 | 0 | 0 |
| 10 | 64 | 0 | 0 |
| **All** | **524** | **0** | **1** |

First pass: 489 / 1 / 21. Re-check scope: every flagged sentence, the sentences rewritten or added around them, and the new `sources:` paths (all exist). Article 07 was unchanged.

Still open: 06 #33, "A dropped lead is never enrolled in a new sequence." The app never enrolls dropped leads, but the enroll API accepts any `lead_statuses` (app/api/sequences.py:139-143; sequence_engine.py:202-216). Fix the sentence to: "When you launch from the app, dropped leads are never enrolled." Or state the API exception.

## Out-of-scope discoveries (reported, not fixed)

1. **Strategy detail page reads the wrong response shape** (HIGH; this is why 03 #48, 04 #16/#51 and 05 #21–23 are contradicted).
   - What the server sends: GET /strategies/{id} returns `progress: PipelineProgress[]` with nested `phases`, and `verification: list[dict]` with one entry per attempt carrying `attempt` and `fix_description` (app/api/strategies.py:212-267; app/api/schemas.py:120-146).
   - What the page expects: flat `PhaseProgress` objects with `steps`, and `VerificationPass` objects with `attempts` and `fix` (frontend/src/lib/api/types.ts:263-292; frontend/src/app/(app)/strategies/detail/page.tsx:33-91,173-206).
   - Effect: progress shows "Phase pending" cards with whole-pipeline totals, step outputs can never be read, the verification card lists every attempt, and "xN" and the fix text never render.
   - No frontend test covers this shape.
2. **The in-app WhatsApp template editor cannot save placeholders.** It sends `variable_descriptions: {}` (frontend/src/app/(app)/campaigns/page.tsx:102-106), but the server requires one description per placeholder (app/services/whatsapp_templates.py:101-118,151-152). The editor's own example body "Hi {{1}}, …" is rejected.
3. **Removing a lead does not stop its sequence.** PATCH /leads/{id} to `dropped` (app/api/ui_support.py:133-148) leaves enrollments untouched, and send_message_impl never checks lead status (app/workers/outreach_tasks.py:160-196). An enrolled lead that is "Removed" before its scheduled step still gets emailed.
4. **Message writing may be blocked by the strategy budget** (PLAUSIBLE, not executed).
   - The send task opens `usage_meter.owner_scope(..., "outreach")` (outreach_tasks.py:1260). That passes the strategy's `budget_micros` (app/services/usage_meter.py:449-460), so `check_budget` is armed with prior pipeline+verification spend (usage_meter.py:340-343,278-287).
   - If the strategy has less budget left than one call's worst case, message rendering raises BudgetExceededError. The message goes back to SCHEDULED and is retried every dispatch tick (outreach_tasks.py:482-485).
   - Outreach spend does not *count* toward the budget, but the remaining budget can still *gate* outreach.
5. **FEATURES.md is stale on pipeline order.** FEATURES.md:153 says the GTM phases "run first". The code runs the strategy pipeline first, then GTM (app/pipeline/engine.py:37-40).
6. **The "Today / cap" figure ignores lowered caps.** The Campaigns "Today / cap" number uses the raw warm-up allowance (app/api/strategies.py:556). It ignores compliance-rule and mailbox-health caps, so it can overstate today's real cap.
7. **The VIP review rule catches most of the target ICP.** It matches "owner", "partner", "head of" and similar titles (app/services/send_review.py:86-89) and is on by default (system_settings.py:120). For the ICP in docs/ICP.md:91-93 (owner/founder/GM/head of sales), most first-touch messages will sit in the review queue by default. This is a product question, not just a documentation one.
9. (Re-check) **The enroll API has no status allow-list.** `POST /sequences/{id}/enroll` accepts any `lead_statuses` (app/api/sequences.py:139-143). An API caller can enroll `dropped`, `flagged`, `replied` or other leads; only the suppression check stands in the way. This is a product question: consider restricting it to verified/flagged.
8. **Process.** D1 is "Unanswered" in docs/program/DECISIONS.md:9 and blocks 01/09/10, while the fact-checker brief treats D1 as decided. The P0-5-CAPS figures quoted in 01/03/04 are placeholders (DECISIONS.md:20).

---

# Help-center fact check — articles 11 to 20

Checker: help-center-fact-checker (read-only). Repository: /home/claude/wt-help. Date: 2026-10-11.
Method: front-matter `sources` confirmed with Glob (all exist), then every factual sentence was checked against code first (code wins over docs), docs second. Navigation, disclaimers and generic advice are skipped. Bulleted lists are checked one row per bullet unless the bullets share one piece of evidence.

Source-path check: every path in every front-matter `sources` list of articles 11–20 exists (161 paths, 0 missing).

Verdicts: S = supported, U = unsupported, C = contradicted.

---

### 11-linkedin.md
| # | Sentence (verbatim, may be shortened with …) | Verdict | Evidence (path:line) / what the code says |
|---|---|---|---|
| 1 | Vectorae has two separate LinkedIn features. | S | app/api/sequences.py:110-113 (LinkedIn steps); frontend/src/components/shell/nav.ts:49-50 (Network) |
| 2 | LinkedIn steps in a sequence send connection requests, messages and InMail … through a LinkedIn account you connect. | S | app/services/linkedin_outreach.py:13-21; frontend/src/components/settings/LinkedInAccountsCard.tsx:59 |
| 3 | The Network page lets you upload your own LinkedIn connections, see which of them may fit your products, and write messages to them. | S | frontend/src/app/(app)/network/page.tsx:3,212-217,268-299; app/services/network_messages.py:1-10 |
| 4 | There are two different plan checks | S | app/api/sequences.py:57-72 (channels); app/core/plans.py:180-186 (linkedin_network) |
| 5 | LinkedIn steps in sequences are part of the plan's channel list. | S | app/core/plans.py:58,75,94,110,129,149,167; :260-276 |
| 6 | The Growth, Scale, Pay per meeting, Pro and Enterprise plans include the LinkedIn channel. Free and Starter do not. | S | app/core/plans.py:58 (free: gmail), 75 (starter: gmail, whatsapp), 94, 110, 129, 149, 167 |
| 7 | If your plan does not include it, creating a sequence with a LinkedIn step is refused with an upgrade message. | S | app/api/sequences.py:222-225,66-72 (HTTP 402 plan_limit_response); app/core/plans.py:266-276 |
| 8 | The check runs again when a sequence is launched, so a sequence built on a higher plan cannot be launched after a downgrade. | S | app/api/sequences.py:60-63,300 |
| 9 | The Network page … is included with Growth, Scale, Pro and Enterprise. | S | app/core/plans.py:184 |
| 10 | It is not included with Pay per meeting, even though that plan includes the LinkedIn channel. | S | app/core/plans.py:129,180-184 |
| 11 | On other plans the Network page still opens and shows "Upgrade in Settings". | S | frontend/src/app/(app)/network/page.tsx:198-208; app/api/linkedin_network.py:47-49 (status readable on every plan) |
| 12 | (Has LinkedIn sending been verified against the live service?) No. | S | app/integrations/unipile_linkedin.py:16 and the `# TODO: verify` markers below |
| 13 | Vectorae talks to LinkedIn through a third-party service called Unipile. | S | app/integrations/unipile_linkedin.py:1-31; app/integrations/linkedin_channel.py |
| 14 | The code that calls Unipile is marked … not yet checked … profiles, connection requests, starting chats, sending messages, the account-connection page, reading InMail credits, and the incoming webhook … | S | app/integrations/unipile_linkedin.py:71,84,93,103,115,126,137; app/api/linkedin.py:288 |
| 15 | Until that check is done, treat LinkedIn sending as not yet verified against the live service. | S | same as #14 |
| 16 | Your Vectorae administrator must also set up Unipile (Admin > Integrations > Unipile) before any LinkedIn sending can work. | S | app/workers/outreach_tasks.py:733-737 |
| 17 | If it is not set up, LinkedIn steps fail with the reason "LinkedIn is not configured". | S | app/workers/outreach_tasks.py:736-737 (full text: "LinkedIn is not configured (Admin > Integrations > Unipile)") |
| 18 | Go to Settings, open the Integrations tab, and find the LinkedIn card. Click Connect an account. | S | frontend/src/lib/settings-tabs.ts:16; frontend/src/app/(app)/settings/page.tsx:390,531; LinkedInAccountsCard.tsx:57,64 |
| 19 | You are sent to Unipile's hosted sign-in page and sign in to LinkedIn there. | S | LinkedInAccountsCard.tsx:6-8,40-43; app/integrations/unipile_linkedin.py:111-122 |
| 20 | Vectorae does not see your LinkedIn password; it stores only an account id. | S | LinkedInAccountsCard.tsx:6-8; app/api/linkedin.py:120-134 |
| 21 | There is also an option to "Link an existing Unipile account id instead" … | S | LinkedInAccountsCard.tsx:74-84 |
| 22 | You can connect more than one LinkedIn account. | S | app/services/linkedin_limits.py:6-8 |
| 23 | Each connected account shows a Premium badge …, a Paused badge if it is inactive, and two usage bars for today: Connection requests and Messages + InMail. | S | LinkedInAccountsCard.tsx:121-122,136-137 |
| 24 | You can refresh an account's details or remove it from the same card. | S | LinkedInAccountsCard.tsx:126-132 |
| 25 | LinkedIn steps are sent automatically … within your send window, your daily limits, and the send-review queue if you use it. | S | app/workers/outreach_tasks.py:268-291,416-432 (note: the review queue is switched by the administrator, not chosen per user — system_settings.py:114) |
| 26 | Each step has an action. The default, auto, decides at send time based on the prospect | S | app/api/sequences.py:110-113,157-158; app/workers/outreach_tasks.py:748 |
| 27 | Already connected to you: a message. | S | app/services/linkedin_outreach.py:126-127 |
| 28 | A connection request is still pending: the step is skipped and the sequence continues. | S | app/services/linkedin_outreach.py:128-129; app/workers/outreach_tasks.py:749-751; app/services/sequence_engine.py:389-402 |
| 29 | The prospect has a Premium profile: an InMail. If none of your accounts can send InMail (no Premium, or no InMail credits left), it falls back to a connection request. | S | app/services/linkedin_outreach.py:130-131; app/services/linkedin_limits.py:112-114,131-132; app/workers/outreach_tasks.py:756-762 |
| 30 | Anyone else: a connection request. | S | app/services/linkedin_outreach.py:132 |
| 31 | You can also set a step to connect, message or inmail explicitly. | S | app/api/sequences.py:110 (note: API only — the in-app sequence form creates email-only sequences, frontend/src/lib/api/outreach.ts:30-33) |
| 32 | A "connect" step to someone already connected becomes a message. | S | app/services/linkedin_outreach.py:121-123 |
| 33 | A "message" step to someone who is not connected is skipped. | S | app/services/linkedin_outreach.py:119-120; outreach_tasks.py:749-751 |
| 34 | Before each send, Vectorae re-reads the prospect's profile (connected, pending, Premium) from LinkedIn through Unipile. | S | app/workers/outreach_tasks.py:747; app/services/linkedin_outreach.py:91-111 |
| 35 | When someone accepts your connection request, the incoming webhook marks them as connected. | S | app/api/linkedin.py:287,315-319 |
| 36 | The text is written by AI from the step brief and your messaging playbook | S | app/services/linkedin_outreach.py:143-160 |
| 37 | … and it passes through the same claim check as other channels. | S | app/workers/outreach_tasks.py:780-786 |
| 38 | Length limits in the code: a connection note is cut to at most 300 characters, a message to at most 1,500 characters. | S | app/integrations/unipile_linkedin.py:31; app/services/linkedin_outreach.py:47,164-165 |
| 39 | The writer is told to keep connection notes to 280 characters with no pitch, messages under 120 words, and InMail bodies under 150 words with a short subject. | S | app/services/linkedin_outreach.py:49-59 |
| 40 | Each connected LinkedIn account has two daily ceilings, counted per UTC day | S | app/services/linkedin_limits.py:10-14,49-50 |
| 41 | Connection requests: default 20 per account per day. | S | app/services/system_settings.py:85-86 |
| 42 | Messages (including InMail): default 50 per account per day. An InMail counts against the message ceiling. | S | app/services/system_settings.py:87-88; linkedin_limits.py:13-14,90 |
| 43 | Both numbers are set by your Vectorae administrator in System Settings … | S | app/services/system_settings.py:1-9,85-88 |
| 44 | If a send fails, the slot it reserved is given back. | S | app/workers/outreach_tasks.py:456-461,487-491; linkedin_limits.py:104-109 |
| 45 | … a prospect's first touch goes from the active account with the fewest sends of that kind today. | S | app/services/linkedin_limits.py:117-138 |
| 46 | Every later touch to that prospect comes from the same account … | S | app/services/linkedin_limits.py:22-27; outreach_tasks.py:753-755 |
| 47 | If that account is disconnected, the step fails with a message asking you to reconnect it. | S | app/workers/outreach_tasks.py:741-745 |
| 48 | When every eligible account has reached its ceiling, the message is not dropped. It is moved to the next day's send window. | S | app/workers/outreach_tasks.py:763-768 |
| 49 | LinkedIn messages do not carry an unsubscribe footer, because a link in a connection note can get the account restricted. | S | app/services/linkedin_outreach.py:23-27 |
| 50 | … a reply on LinkedIn goes through the same reply classifier and stop rules as email and WhatsApp. | S | app/workers/outreach_tasks.py:1192-1232 |
| 51 | A reply classified as an unsubscribe request suppresses that person's LinkedIn profile, email address and phone number. | S | app/workers/outreach_tasks.py:1209-1211; app/services/consent.py:219-296 |
| 52 | An unsubscribe on any channel also suppresses the LinkedIn profile. | S | app/services/sequence_engine.py:484-501; consent.py:262-276 (when the lead has a LinkedIn URL) |
| 53 | Vectorae checks the suppression list when a prospect is enrolled, when a message is sent, and once more immediately before the LinkedIn send call. | S | app/services/sequence_engine.py:227-229; app/workers/outreach_tasks.py:187-196; app/integrations/linkedin_channel.py:48-56 |
| 54 | A suppressed prospect is never sent a LinkedIn message. | S | same as #53 |
| 55 | Network in the main menu opens "Your LinkedIn network". | S | nav.ts:50; network/page.tsx:191 |
| 56 | LinkedIn offers no way for Vectorae to read your connections, so you upload them yourself | S | app/services/linkedin_network.py:13-15 |
| 57 | Steps 1–3 (Settings & Privacy → Data privacy → Get a copy of your data; choose Connections; upload Connections.csv) | S | network/page.tsx:214-218 |
| 58 | The file can be up to 5 MB and up to 20,000 rows. | S | app/services/linkedin_network.py:43-44; app/api/linkedin_network.py:72-74 |
| 59 | Only name, job title, company, profile link and connection date are stored. | S | app/services/linkedin_network.py:54-61,137-140 |
| 60 | Email addresses and phone numbers in the file are discarded when it is read. | S | app/services/linkedin_network.py:8-9,136 |
| 61 | Vectorae then scores each connection against each of your products with fixed rules. | S | app/services/linkedin_network.py:239-295 |
| 62 | This scoring does not use AI and does not send your connections to any outside service. | S | app/services/linkedin_network.py:10-11 |
| 63 | Connections scoring 30 or more out of 100 appear as matches, grouped into segments, with the reasons for each match. | S | app/services/linkedin_network.py:45,285-292; app/api/linkedin_network.py:118-128 |
| 64 | Stored connections are re-scored weekly. | S | app/workers/celery_app.py:221-225; linkedin_network.py:358-369 (eligible plans only) |
| 65 | New connections only appear when you upload a fresh export | S | app/services/linkedin_network.py:13-15 |
| 66 | … the page reminds you when your last upload is more than 7 days old. | S | app/services/linkedin_network.py:47,348-355; network/page.tsx:228-231 (note: the on-screen wording says "more than a few weeks old") |
| 67 | Your uploaded connections are private to your account. They are never shown to any other account. | S | app/api/linkedin_network.py:3-4; linkedin_network.py:3-7 |
| 68 | Yes, on eligible plans, and only after you approve the text. | S | app/services/network_messages.py:3-6,139-142 |
| 69 | Draft it in my voice asks AI to write a short message. A draft is never sent. | S | network/page.tsx:68-72; network_messages.py:29-36,141-142 |
| 70 | Edit it if you want (up to 1,500 characters), then click Save. Only saved text can be sent. | S | network_messages.py:25,110-119,141-142; network/page.tsx:85-87 |
| 71 | Copy and open LinkedIn copies the text and opens their profile; you send it yourself, then click I sent it to record it. | S | network/page.tsx:93-105; network_messages.py:122-128 |
| 72 | Send now via LinkedIn sends it through your connected LinkedIn account after you confirm. | S | network/page.tsx:107-113; app/api/linkedin_network.py:212-217 |
| 73 | Bulk send sends up to 25 saved messages per batch, one at a time, about 90 seconds apart. | S | network_messages.py:26-27,179-189; app/api/linkedin_network.py:220-233 |
| 74 | Every Vectorae send to a connection checks again … plan, … do-not-contact list, … daily LinkedIn message limit, … still a 1st-degree connection. | S | app/services/network_messages.py:139-162 |
| 75 | If they are no longer connected, nothing is sent and the message is marked failed. | S | network_messages.py:159-161,173-176 |
| 76 | On the Network page, click Delete my uploaded connections and confirm. | S | network/page.tsx:236-241 (shown only when eligible and connections > 0 — see #78) |
| 77 | This deletes everything you uploaded. | S | app/services/linkedin_network.py:325-335 |
| 78 | (re-check) The button only appears while your plan includes the Network page; after a downgrade the page shows only the upgrade notice and no delete button. | S | network/page.tsx:198-208,210,236-241 (also hidden when 0 connections are stored) |
| 79 | (re-check, new) The delete itself is not tied to your plan, so it can still be done through the Vectorae API (`DELETE /linkedin-network`). | S | app/api/linkedin_network.py:28,134-144 (router prefix `/linkedin-network`, `@router.delete("")`, no plan check) |

Summary (final, after re-check): 79 supported, 0 unsupported, 0 contradicted. (First pass: 77 S / 0 U / 1 C; the old #78 "It works on every plan…" was rewritten as #78–#79.)

---

### 12-send-review-queue.md
| # | Sentence (verbatim, may be shortened with …) | Verdict | Evidence (path:line) / what the code says |
|---|---|---|---|
| 1 | Vectorae sends outreach automatically. | S | app/workers/outreach_tasks.py:99-123,1240-1267 (D1) |
| 2 | … certain messages are held, just before they would go out, until a person approves or rejects them. | S | app/services/send_review.py:21-24; outreach_tasks.py:416-432 |
| 3 | A message is checked after its text has been written and right before it would be sent. | S | app/workers/outreach_tasks.py:402-427 |
| 4 | It is held if any of these four rules applies | S | app/services/send_review.py:69-81,214-242 |
| 5 | Prospect objected before – the prospect's most recent reply was classified as an objection. | S | send_review.py:116-135 |
| 6 | Deal has stalled – … an open deal whose expected close date has passed, or … "cooling". | S | send_review.py:138-154 |
| 7 | Executive / VIP contact – … founder, co-founder, owner, CEO, COO, CFO, CTO, CMO, CRO, "chief …", president, managing director, partner, VP or vice president, "head of", board member, or chair. | S | send_review.py:86-89 |
| 8 | Tone or spam check flagged the copy – … (the same rules used in the pre-launch review). | S | send_review.py:166-183 |
| 9 | The queue covers email, WhatsApp and LinkedIn messages. | S | outreach_tasks.py:423-426 |
| 10 | AI phone calls are not held, because a live call cannot be read and approved in advance. | S | outreach_tasks.py:419-423 |
| 11 | Yes, but not by individual users. The queue as a whole and each of the four rules are switched … by your Vectorae administrator in System Settings. | S | app/services/system_settings.py:108-125; send_review.py:189-211 |
| 12 | All five settings are on by default. | S | system_settings.py:114-125 |
| 13 | If your prospects are mostly founders … the VIP rule would hold nearly every message. The administrator setting … says to turn it off … | S | system_settings.py:108-113,120-122 |
| 14 | If Vectorae cannot read these settings, it treats the queue as on. | S | send_review.py:197-211 |
| 15 | If the review check itself fails with an error, the message is sent rather than held … | S | send_review.py:272-316 |
| 16 | The queue sits on top of the normal compliance checks; it does not replace them. | S | send_review.py:272-274; outreach_tasks.py:170-352 |
| 17 | Go to Campaigns and open the Review tab. | S | frontend/src/app/(app)/campaigns/page.tsx:424,474-483,562 |
| 18 | The queue covers all your campaigns, oldest first. | S | campaigns/page.tsx:560-562; send_review.py:436-446 |
| 19 | (re-check) You can filter by Pending, Approved or Rejected. | S | frontend/src/components/campaigns/ReviewQueuePanel.tsx:42,59-65 |
| 20 | When nothing is waiting, you see "Nothing is waiting for approval." | S | ReviewQueuePanel.tsx:71-73 |
| 21 | When a message is held, the account owner is sent a notification titled "A message to [name] needs approval", linking to the Review tab. | S | send_review.py:250-253,325-340 |
| 22 | (re-check) Each item shows who it is for, their title and company, the step number and channel, how long it has been waiting, and a badge for each rule that applied. | S | ReviewQueuePanel.tsx:116-137 |
| 22a | (re-check, new) The most serious rule is also named in the item's headline. | S | ReviewQueuePanel.tsx:116; frontend/src/lib/sendReview.ts:36-59 |
| 23 | An item still pending after more than 3 days shows a Going stale badge … | S | frontend/src/lib/sendReview.ts:73-78; ReviewQueuePanel.tsx:120 |
| 24 | Read the subject and message. You can edit both before approving. | S | ReviewQueuePanel.tsx:139-150 |
| 25 | Then click Approve & send (or Approve edit & send if you changed anything). | S | ReviewQueuePanel.tsx:179-182 |
| 26 | A note is optional. | S | ReviewQueuePanel.tsx:170-172; send_reviews.py:31-32 |
| 27 | What you approve is exactly what is sent. | S | send_review.py:26-39,281-288; outreach_tasks.py:438-445 |
| 28 | Vectorae saves the text at the moment the message is held and, after approval, sends that saved text (or your edit). | S | send_review.py:301-305,319-322,286-288 |
| 29 | It does not rewrite the message after you approve it. | S | send_review.py:281-288 |
| 30 | Approval puts the message back in the normal send queue, and it goes out on the next send run ("Approved — it will send on the next tick"). | S | send_review.py:371-378; ReviewQueuePanel.tsx:99 |
| 31 | Click Reject, type a note, then click Confirm reject. | S | ReviewQueuePanel.tsx:183-190 |
| 32 | The note must be at least 5 characters … | S | app/api/send_reviews.py:39-43; sendReview.ts:34,84-88 |
| 33 | A rejected message is never sent. | S | send_review.py:290-292,382-403 |
| 34 | Only that one message is cancelled. | S | send_review.py:398-402 |
| 35 | (re-check) The prospect stays enrolled, but rejecting does not schedule the next step. | S | send_review.py:382-403 (enrollment left ACTIVE, no scheduling); sequence_engine.py:352-402 |
| 35a | (re-check, new) If automatic follow-up is on for the previous step (it is by default), Vectorae later tries that same step again as a new message, by default 72 hours after the previous step was sent, and the new message is checked by the review queue again. | S | app/api/sequences.py:103-108 (followup_enabled default True, followup_delay_hours default 72); outreach_tasks.py:1440-1470 (next step = last sent + 1 = the rejected step), 1515-1564 (new Message row sent through send_message_impl); send_review.py:278-308 (a new message id has no review, so the rules are evaluated afresh). Applies only when the rejected step had a previously sent step before it. |
| 36 | (re-check) To stop contacting the person, stop or pause them separately. | S | send_reviews.py:104-107 (enrollment keeps running) |
| 37 | A review can be decided only once. Trying to approve or reject an item that was already decided returns an error … | S | app/api/send_reviews.py:92-94,110-112 |
| 38 | An approved message goes back through the full send process. | S | outreach_tasks.py:131-352 |
| 39 | the campaign is still active (not paused) | S | outreach_tasks.py:171-172 |
| 40 | the prospect is still enrolled and not stopped or paused | S | outreach_tasks.py:173-179 |
| 41 | the prospect is not on the suppression (do-not-contact) list | S | outreach_tasks.py:185-196 |
| 42 | channel rules still allow it (for example WhatsApp opt-in and template approval) | S | outreach_tasks.py:222-255 |
| 43 | the current compliance rules and the send window allow it | S | outreach_tasks.py:257-280 |
| 44 | the daily sending limits allow it. | S | outreach_tasks.py:282-352 |
| 45 | If any of these fails, the approved message is not sent at that time … | S | same as #39-#44 |
| 46 | Pausing a campaign stops everything in it from sending, including messages you have already approved. | S | outreach_tasks.py:118-120,171-172 |
| 47 | The send run skips paused campaigns entirely, and the send step checks the campaign state again before sending. | S | outreach_tasks.py:118-120,171-172 |
| 48 | When you resume the campaign, approved messages are sent through the normal checks. | S | send_review.py:371-377 (SCHEDULED); outreach_tasks.py:108-123 |
| 49 | Held messages stay in the queue while a campaign is paused. | S | send_review.py:294-295 (a pending review stays pending; pausing does not touch reviews) |
| 50 | Approving one while the campaign is paused does not send it until the campaign is active again. | S | outreach_tasks.py:118-120,171-172 |
| 51 | Vectorae has three separate checks with similar names | S | app/api/send_reviews.py:9-11; app/api/sequences.py:258-268,330-337 |
| 52 | Send-review queue: checks one message, at send time, for the four rules above. | S | send_review.py:3-6 |
| 53 | Pre-send review on a sequence: checks the sequence's content before it can be launched. | S | app/api/sequences.py:258-268,301-303; app/services/adversarial_review.py:1-20 |
| 54 | It looks for spam and tone problems, compliance problems (…unsubscribe footer or a misleading "Re:" subject), and claims about prospects. | S | adversarial_review.py:127-174 |
| 55 | "Block" findings stop the launch until the content is fixed or an owner or manager overrides it with a written reason of at least 10 characters. | S | adversarial_review.py:16-17,57,323-329; app/api/sequence_reviews.py:31,52-60 |
| 56 | Changing the content after an override brings the check back. | S | adversarial_review.py:22-24,105-117,310-316 |
| 57 | Team approvals: in a workspace that requires approval, an SDR's first launch … waits for an owner or manager to approve it under Team, Approvals. | S | app/api/sequences.py:330-337,365-367; frontend/src/app/(app)/team/page.tsx:56,61 |

Summary (final, after re-check): 59 supported, 0 unsupported, 0 contradicted. (First pass: 54 S / 0 U / 3 C.)

---

### 13-replies-and-unified-inbox.md
| # | Sentence (verbatim, may be shortened with …) | Verdict | Evidence (path:line) / what the code says |
|---|---|---|---|
| 1 | When a prospect replies by email, WhatsApp or LinkedIn, Vectorae stores the reply, classifies it, and changes what happens next in their sequence. | S | app/workers/outreach_tasks.py:996-1232 |
| 2 | Vectorae never replies to a person automatically. | S | outreach_tasks.py:997-998,1131,1197; reply_classification.py:12 |
| 3 | The Inbox gathers every reply into one conversation per prospect … | S | app/services/inbox.py:3-13 |
| 4 | Email: … checks your connected Gmail accounts … on a schedule. The default is every 300 seconds (5 minutes); your deployment can change this. | S | app/config.py:115; app/workers/celery_app.py:230-233 |
| 5 | WhatsApp and LinkedIn: replies arrive through the providers' webhooks. | S | app/api/webhooks_whatsapp.py:447; app/api/linkedin.py:11,285-347 |
| 6 | An email reply is matched to a prospect first by the email thread, then by the sender's address. | S | outreach_tasks.py:1015-1035 |
| 7 | Matching only looks at prospects that belong to the account whose Gmail received the reply … | S | outreach_tasks.py:999-1013 |
| 8 | Each reply is classified by AI into one of these routing classes … | S | app/services/reply_classification.py:22-45 |
| 9 | Interested, question, objection or not interested: the prospect's sequence stops, on every channel, and the lead is marked Replied. The lead's owner is notified. | S | outreach_tasks.py:1104-1117 |
| 10 | Unsubscribe request …: treated exactly like clicking the unsubscribe link. … suppressed straight away and every sequence … stops. | S | outreach_tasks.py:1084-1088; sequence_engine.py:484-508 |
| 11 | Out of office: the sequence is paused, not stopped, and picks up again after 7 days by default (configurable …). | S | outreach_tasks.py:1095-1102; app/config.py:117; sequence_engine.py:282-312 |
| 12 | Bounce …: recorded as a bounce, the sequence stops, the lead is dropped, and the campaign's bounce rate is checked. | S | sequence_engine.py:511-524 |
| 13 | On LinkedIn a bounce has no meaning and is only recorded. | S | outreach_tasks.py:1221-1222 |
| 14 | Automated response …: stored, but treated as not a reply. The sequence neither stops nor moves on. | S | outreach_tasks.py:1073-1076,1136-1137,1202-1203 |
| 15 | If the AI's answer cannot be read, the reply is treated as a question. | S | reply_classification.py:60-63,91-97 |
| 16 | That stops the sequence and leaves it for you to look at … | S | reply_classification.py:62-63; outreach_tasks.py:1104-1108 |
| 17 | A reply on one channel stops the whole sequence, including steps on other channels … | S | outreach_tasks.py:1122-1128; sequence_engine.py:252-279 |
| 18 | No. Replies are classified and routed; a person writes the answer. | S | outreach_tasks.py:997-998 |
| 19 | Vectorae does not send anything back to a prospect who replied. | S | outreach_tasks.py:1104-1107 (stop); follow-up sweep skips repliers :1458 |
| 20 | A second AI pass reads each reply and decides what you should do next, in one of four categories | S | app/services/reply_intelligence.py:7-14,50; enqueued on every channel: outreach_tasks.py:1069, webhooks_whatsapp.py:447, linkedin.py:347 |
| 21 | Buying signal – interest, a question about how it works, or a request for a call or pricing. | S | reply_intelligence.py:109-110 |
| 22 | Objection – a specific concern such as price or an existing supplier. | S | reply_intelligence.py:110-111 |
| 23 | Not now – a timing issue, not a rejection. | S | reply_intelligence.py:111-112 |
| 24 | Wrong person – they are not the buyer or name someone else. | S | reply_intelligence.py:13-14,112 |
| 25 | It writes a suggested draft of under 150 words onto the reply. | S | reply_intelligence.py:56,204,355 (capped at 150 words) |
| 26 | The draft is never sent by Vectorae … | S | reply_intelligence.py:18-21 |
| 27 | For a buying signal, the sequence is lined up so that the next step would be step 3, but its status is not changed … | S | reply_intelligence.py:18-21,64-67,246-271 |
| 28 | Every reply also gets a label …: interested, objection, not now, unsubscribe or neutral, with a confidence score and a one-line reason. | S | app/services/reply_intent.py:17-24,53-59,78 |
| 29 | Unsubscribe requests and machine mail … are labelled by fixed rules. | S | reply_intent.py:26-31,129-138 |
| 30 | Everything else is labelled by AI, reading the reply together with the message it answers. | S | reply_intent.py:141-154,191-207 |
| 31 | If the AI call fails, the reply is left unclassified instead of being guessed. | S | reply_intent.py:34-35,212-229 |
| 32 | This label feeds the positive reply rate … The ordinary reply rate is still shown next to it. | S | reply_intent.py:11-15,293-295; frontend/src/components/analytics/ReplyQualityPanel.tsx:41-53 |
| 33 | A reply labelled not now creates a re-engagement plan that records their reason in their own words and a return date. | S | app/services/reengagement_memory.py:287-343 |
| 34 | If they named a date, that date is used. | S | reengagement_memory.py:259-267 |
| 35 | Otherwise … 60 days for timing or a project, 90 for budget or headcount, 120 for priority, 180 for a contract, and the configured default (90 days) when no reason is given. | S | reengagement_memory.py:86-94,268-273; system_settings.py:129-131 |
| 36 | When the date arrives, Vectorae first re-checks …; dropped, disqualified, closed won or lost, meeting, opportunity or proposal, or suppression list → the plan is cancelled with the reason recorded. | S | reengagement_memory.py:377-399,524-528 (the suppression check here looks at the email address only) |
| 37 | Otherwise you are notified. | S | reengagement_memory.py:529-538,549-568 |
| 38 | Sending a message automatically at that point is off by default. | S | app/services/system_settings.py:132-137 (the module docstring at reengagement_memory.py:20 says "the default" is on; that docstring is stale) |
| 39 | (re-check) If your administrator turns it on, a return message is scheduled on the prospect's earlier sequence. | S | reengagement_memory.py:467-509,532-537 (message on the sequence of the last sent message) |
| 39a | (re-check, new) In the current version that message is cancelled when it is due to send, because the prospect's "not now" reply already stopped that sequence. | S | outreach_tasks.py:1104-1107,1170-1173,1224-1226 (human replies stop enrollments); outreach_tasks.py:173-177 (stopped enrollment → message CANCELLED). Inferred from code paths; not covered by a test (tests/test_reengagement_memory.py:292-309 stops at SCHEDULED). |
| 40 | Open Inbox in the main menu. | S | nav.ts:33 |
| 41 | Each row is one prospect, not one channel … | S | inbox.py:3-13,160-164 |
| 42 | Opening a row shows the full timeline … on every channel, the same timeline as on the lead's page. | S | inbox.py:206-225; frontend/src/app/(app)/inbox/page.tsx:205-207 |
| 43 | There are three filters | S | inbox/page.tsx:44-48 |
| 44 | (re-check) Needs reply – threads with at least one reply from a person that has not been marked handled. These are listed oldest first … | S | inbox.py:93-100,119,187-190 |
| 45 | All – every thread, newest first. | S | inbox.py:191-194 |
| 46 | Cleared – threads you have marked handled, newest first. | S | inbox.py:192-194; inbox/page.tsx:47 |
| 47 | Machine mail … is filed in the conversation but never shows as needing a reply. | S | inbox.py:46-49,64-67,93-100 |
| 48 | A thread shows an Overdue badge when its reply has waited more than two days | S | frontend/src/lib/inbox.ts:84-91; inbox/page.tsx:147 |
| 49 | … and a "waiting" count when a prospect sent more than one unanswered message. | S | inbox/page.tsx:144-146 |
| 50 | (re-check) The Inbox menu item does not show a count. | S | nav.ts:33; no badge code in frontend/src/components/shell; `countInbox` (frontend/src/lib/api/inbox.ts:25) has no caller |
| 50a | (re-check, new) The Needs reply list shows each waiting person once, however many messages they sent. | S | inbox.py:160-164,180-190 (one thread per lead) |
| 51 | Mark handled clears a thread from "Needs reply". | S | inbox/page.tsx:189-193; inbox.py:233-254 |
| 52 | It sends nothing. | S | inbox/page.tsx:208-211 |
| 53 | It only records that someone has dealt with the conversation, including when you answered from Gmail directly or by phone, or decided no answer was needed. | S | inbox.py:19-22 |
| 54 | If you cleared a thread by mistake, open it under Cleared and click Put back. | S | inbox/page.tsx:194-198,211 |
| 55 | Sending the next sequence step does not clear a thread. Only a person marking it handled does. | S | inbox.py:19-22 |
| 56 | If a prospect replies again after you cleared their thread, the new reply needs a reply of its own. | S | inbox.py:100,119 (a new reply has handled_at = None) |

Summary (final, after re-check): 58 supported, 0 unsupported, 0 contradicted. (First pass: 53 S / 0 U / 3 C.) "Treat the reminder as your cue to write to them yourself." is advice and is not scored.

---

### 14-booking-and-calendar.md
| # | Sentence (verbatim, may be shortened with …) | Verdict | Evidence (path:line) / what the code says |
|---|---|---|---|
| 1 | Prospects can book a meeting with you in two ways: … a booking page on Vectorae's own calendar, or … a Calendly link. | S | app/api/calendar.py:452-528; app/api/webhooks.py:1-5,75 |
| 2 | Vectorae's own calendar: you set your weekly availability and create booking pages inside Vectorae. | S | frontend/src/app/(app)/calendar/page.tsx:157; calendar/booking-pages/page.tsx:110 |
| 3 | Each booking is tied to your page, so Vectorae always knows whose booking it is. | S | app/db/models.py:2459-2461 |
| 4 | When a booking is cancelled, the prospect goes back into their sequence. | S | app/workers/calendar_tasks.py:262-287; sequence_engine.py:652-685 |
| 5 | Calendly: a scheduling link can be attached to a sequence, and Vectorae asks the writer to include it in the call to action …, tagged with your account. | S | app/api/sequences.py:119; app/services/message_personalization.py:129; outreach_tasks.py:556-571; app/integrations/calendly.py:177-196 |
| 6 | Calendly reports bookings back to Vectorae through a webhook. | S | app/api/webhooks.py:75-99 |
| 7 | A Calendly booking stops the prospect's sequences for good. | S | webhooks.py:153-165; sequence_engine.py:252-262 |
| 8 | In the current app, the sequence form does not have a field for this link; it can be set when a sequence is created through the Vectorae API. | S | frontend/src/components/strategy/OutreachPanel.tsx:68-71 (no bookingUrl passed); frontend/src/lib/api/outreach.ts:28,35 |
| 9 | The Calendly connection uses one API token for the whole deployment, set by whoever runs your Vectorae. | S | app/config.py:119-120 |
| 10 | In Settings, on the Integrations tab, the Calendly card shows either "API token configured" or "Not configured". | S | settings/page.tsx:396-403 (full text: "Not configured — set CALENDLY_API_TOKEN env var") |
| 11 | Several parts of the Calendly code are marked as not yet checked … (the sign-in method, the webhook signature header and the booking data it reads), so treat … as not yet verified … | S | app/integrations/calendly.py:4,8,21-22,44,53; webhooks.py:55,116 |
| 12 | Open Calendar in the main menu and set your Weekly availability. | S | nav.ts:45; calendar/page.tsx:157 |
| 13 | Each block is a day of the week, a start time, an end time and a time zone. | S | app/api/calendar.py:71-76 |
| 14 | The end time must be after the start time; overnight blocks are not supported. | S | app/api/calendar.py:78-88; calendar_service.py:279-283 |
| 15 | (re-check) If you have no availability, your booking pages offer no times. | S | calendar_service.py:253-254 |
| 15a | (re-check, new) Your Calendar page warns you: "No availability set — nobody can book you yet." | S | frontend/src/app/(app)/calendar/page.tsx:157,180 |
| 16 | Your availability is shared by all your booking pages … | S | calendar_service.py:247-252; models.py:2393-2395 |
| 17 | Go to Calendar, then Booking pages, and click Create booking page. | S | calendar/page.tsx:129-133; booking-pages/page.tsx:110,235 |
| 18 | Title (for example "Intro call") | S | booking-pages/page.tsx:238 |
| 19 | Link – the part after /book/, using lowercase letters, digits and single hyphens | S | booking-pages/page.tsx:251-253; app/api/calendar.py:131-139; calendar_service.py:72-75 |
| 20 | Length – 15, 30, 45 or 60 minutes | S | booking-pages/page.tsx:37,270; app/api/calendar.py:141-148; models.py:2403 |
| 21 | Description – optional | S | booking-pages/page.tsx:286; calendar.py:124 |
| 22 | Questions – up to 10 custom questions, each optional or required. | S | app/api/calendar.py:128; booking-pages/page.tsx:298-335 |
| 23 | You can pause and resume a page, and copy its link to share it. | S | booking-pages/page.tsx:156-175 |
| 24 | Booking pages also support a gap between meetings (0 to 120 minutes) and a maximum number of bookings per day (1 to 50). | S | app/api/calendar.py:126-127 |
| 25 | These two settings are not in the booking-page form; they can be set through the Vectorae API. | S | booking-pages/page.tsx:206-335 (form has no buffer or daily-max fields) |
| 26 | The public page shows the page title, description, length and your questions. | S | app/api/calendar.py:420-430; book/page.tsx:235-239,406-425 |
| 27 | The prospect picks a time zone (their browser's zone is pre-selected), picks a date and time, and enters Your name, Email and optionally Phone, then clicks Confirm booking. | S | book/page.tsx:112,249-252,377-435 |
| 28 | Times are offered from your availability for the next 30 days, and no sooner than 60 minutes from now. | S | app/config.py:288,292; calendar_service.py:243-245 |
| 29 | Both numbers are deployment settings … | S | app/config.py:283-292 |
| 30 | The page does not reveal anything about whether the prospect is already in your CRM. | S | app/api/calendar.py:241-258,507-508 |
| 31 | Public bookings are limited to 30 per IP address per hour. | S | app/core/config.py:209-225; app/api/calendar.py:472-473 |
| 32 | A time is not offered if it overlaps … a live booking on any of your booking pages, or any meeting that is not cancelled. | S | calendar_service.py:174-205,294-295 |
| 33 | Times in the past, inside the minimum notice period, or on a day that has reached the page's daily cap are also hidden. | S | calendar_service.py:288-298 |
| 34 | (re-check) If two people try to book the same time on the same booking page at the same moment, the database allows only one of them; the second gets an error. | S | models.py:2453-2454; app/api/calendar.py:510-518 |
| 35 | A cancelled booking frees its time so it can be booked again. | S | app/api/calendar.py:630-640,674-676; models.py:2444-2448 |
| 36 | Vectorae's calendar does not read your Google Calendar or any other external calendar. | S | calendar_service.py:174-205 (only Vectorae bookings and meetings) |
| 37 | Your availability is stored as your local clock time plus its time zone, not converted to UTC … "9am" stays 9am … through daylight-saving changes. | S | models.py:2359-2363 |
| 38 | Each day is converted on its own date. | S | calendar_service.py:28-33,266-283 |
| 39 | The prospect sees and books times in the zone they choose. | S | book/page.tsx:112,131-132,209 |
| 40 | Confirmation emails show the time in the invitee's zone to the invitee and in your zone to you. | S | calendar_tasks.py:104-134 |
| 41 | The booking appears on your calendar immediately. | S | app/api/calendar.py:510-520,549-556 |
| 42 | If the invitee's email matches one of your leads, that lead is marked Meeting booked, a "booked" outcome is recorded …, and the booking is noted in the CRM. | S | calendar_tasks.py:179-197; calendar_service.py:396-419 |
| 43 | The lead's sequence is paused, not stopped, until one day after the meeting ends. | S | calendar_tasks.py:199-205; sequence_engine.py:611-649 |
| 44 | You are notified, and a meeting prep brief is requested for that lead. | S | calendar_tasks.py:206-218 (only when the invitee matched a lead) |
| 45 | Confirmation emails are sent to the invitee and to you. | S | calendar_tasks.py:104-134,222 |
| 46 | If sending the emails fails, the booking still exists and stays on your calendar. | S | calendar_tasks.py:80-101,163-170; calendar.py:549-556 |
| 47 | When a booking comes in through Calendly, the matching lead is marked Meeting booked, a "booked" outcome is recorded, and all the lead's sequences are stopped. | S | webhooks.py:153-165 |
| 48 | If the Calendly link did not carry your account's tag …, Vectorae does not guess … and matches no lead. | S | webhooks.py:122-140; calendly.py:201-206 |
| 49 | On Vectorae's calendar you can cancel a booking from the calendar ("Cancel booking"). | S | frontend/src/components/calendar/BookingDrawer.tsx:193 |
| 50 | The time is freed, a cancellation email goes to the invitee and to you, any meeting prep reminders … are cancelled, a lead marked Meeting booked goes back to Replied, and the sequence pause made by the booking is lifted. | S | app/api/calendar.py:674-677; calendar_tasks.py:279-317 |
| 51 | Cancelling a meeting never lifts a different pause, such as an out-of-office hold. | S | sequence_engine.py:652-667 |
| 52 | When a Calendly booking is cancelled, the lead goes back to Replied. Its sequences were already stopped and are not restarted. | S | webhooks.py:210-221 |

Summary (final, after re-check): 53 supported, 0 unsupported, 0 contradicted. (First pass: 50 S / 0 U / 2 C.)

---

### 15-meetings-prep-room-transcripts.md
| # | Sentence (verbatim, may be shortened with …) | Verdict | Evidence (path:line) / what the code says |
|---|---|---|---|
| 1 | When a meeting is booked (through Calendly or a Vectorae booking page), Vectorae writes a prep brief for that lead. | S | calendar_tasks.py:208-218; webhooks.py:194-206 (only when the booking matches a lead) |
| 2 | You can also start one yourself from the lead's Meeting Prep tab with Generate prep brief. | S | frontend/src/components/leads/MeetingPrepPanel.tsx:3,79 |
| 3 | Writing one takes about a minute. | S | MeetingPrepPanel.tsx:53,172 |
| 4 | When it is ready, the owner gets a notification, and a Slack message if Slack is connected. | S | app/services/meeting_prep.py:609-640; docs/features/meeting-prep.md:20-22 |
| 5 | Your opening 60 seconds – a short script for the start of the call. | S | MeetingPrepPanel.tsx:188 |
| 6 | Why they booked – the message and reply that led to the booking, quoted. | S | MeetingPrepPanel.tsx:207; meeting-prep.md:13 |
| 7 | Lead profile – copied from your records, not written by AI. | S | MeetingPrepPanel.tsx:210; meeting_prep.py:146; meeting-prep.md:9-10 |
| 8 | Company overview, Company news and Recent LinkedIn activity (their last three posts …). | S | MeetingPrepPanel.tsx:237-275; meeting_prep.py:173-201 |
| 9 | Likely pain points – labelled as hypotheses to confirm on the call. | S | MeetingPrepPanel.tsx:277-281 |
| 10 | Likely objections, Talking points, Discovery questions, Competitive landscape, Recommended next steps and Deal structure. | S | MeetingPrepPanel.tsx:284-303 |
| 11 | You can copy the brief as Markdown. | S | MeetingPrepPanel.tsx:95-97,159-160 |
| 12 | Your Vectorae administrator can turn automatic briefs off in System Settings; they are on by default. | S | app/services/system_settings.py:29-30 |
| 13 | Yes, by default. Vectorae sends a day-before reminder once the call is within 24 hours, and a 1-hour reminder whose text is your opening script. | S | system_settings.py:31-34; meeting-prep.md:24-26 |
| 14 | Each is sent at most once. | S | meeting-prep.md:26-27; celery_app.py:285-291 |
| 15 | Cancelling the booking stops both, and a reschedule sets them up again. | S | meeting_prep.py:463-520 |
| 16 | Your administrator can switch either reminder off. | S | system_settings.py:31-34 |
| 17 | Under the brief you get Your call script: an opening, discovery questions, objection answers, a close and notes. | S | frontend/src/components/leads/CallScriptPanel.tsx:130-223; app/services/meeting_practice.py:35 |
| 18 | It is built from the brief and labelled Suggested until you edit it. | S | CallScriptPanel.tsx:134,143-147; meeting_practice.py:56,159-161 |
| 19 | … regenerating the brief never overwrites the script. | S | meeting_practice.py:127-139 |
| 20 | The Pre-meeting checklist has four items: brief generated, script reviewed, at least 3 objections prepared, and practised. | S | meeting_practice.py:199-216; CallScriptPanel.tsx:81 |
| 21 | It is worked out fresh each time from what exists. | S | meeting_practice.py:180-186 |
| 22 | Practice only blocks the checklist if you choose Require a rehearsal before this call …; it is off by default. | S | meeting_practice.py:212-215; models.py:2812-2817; CallScriptPanel.tsx:118 |
| 23 | Practice a call starts a roleplay where the AI plays the prospect, using the pains from the brief and the objections they have actually raised. | S | app/services/roleplay.py:1-11,144-178; RoleplayPanel.tsx:102 |
| 24 | Choose how hard they should be (easy, realistic or hostile), click Start the call, and type your lines. | S | roleplay.py:49-50; RoleplayPanel.tsx:55,128 |
| 25 | A rehearsal is limited to 40 turns. | S | roleplay.py:65,321 |
| 26 | Click End and get feedback to get five scores (overall, discovery, objection handling, tone, close), what worked, what to improve, and the objections you did not handle. | S | RoleplayPanel.tsx:188,262-303; roleplay.py:66,96-103 |
| 27 | A session with fewer than two of your own lines is not scored. | S | roleplay.py:411 |
| 28 | The practice panel is available even when a lead has no prep brief yet … | S | MeetingPrepPanel.tsx:86 |
| 29 | Open Meetings in the main menu to see upcoming and past meetings, then Open room. | S | nav.ts:46; frontend/src/app/(app)/meetings/page.tsx:150 |
| 30 | (re-check) Click Open in Google Meet, Open in Zoom or Open in Microsoft Teams (or Open in the meeting link for any other link). It opens in the meeting tool; it is not embedded. | S | frontend/src/components/meetings/PlatformLauncher.tsx:5-11,24-29,66-74 (`Open in {label}`; shown when the meeting has a link) |
| 30a | (re-check, new) You can also use the copy button next to the link. | S | PlatformLauncher.tsx:76-92 |
| 31 | Click Start meeting to start the timer, and End meeting when you finish. | S | MeetingRoom.tsx:186-205 |
| 32 | (re-check) Type Live notes, which save as you go. | S | MeetingRoom.tsx:32,73-88,143-170 |
| 32a | (re-check, new) After you end the meeting, you can review and add action items under the AI summary. | S | frontend/src/app/(app)/meetings/detail/page.tsx:142-156; AISummaryPanel.tsx:123-131; ActionItemsList.tsx:150 |
| 33 | A meeting can be on Google Meet, Zoom, Microsoft Teams, or any other link you paste. | S | PlatformLauncher.tsx:24-29 |
| 34 | Vectorae can create Google Meet and Zoom links for you, but these two integrations have never been tested against the live Google and Zoom services. | S | app/integrations/google_meet.py:27-37; app/integrations/zoom.py:26,56,162-170; docs/features/engagement-hub.md:5,308 |
| 35 | If creating the link fails, the meeting is still created and you can paste a link yourself. | S | app/api/meetings.py:22-27,266-283,315-349 |
| 36 | Teams has no integration; you paste the link. | S | app/api/meetings.py:343-344 |
| 37 | Pasting your own link is the only verified path today. | S | follows from #34-#36 |
| 38 | A meeting nobody ended is closed automatically 6 hours after its scheduled end, without a summary. | S | calendar_tasks.py:420-468; celery_app.py:270-278 (a meeting that was never started is closed as cancelled / no-show) |
| 39 | When you click End meeting, Vectorae writes a summary from what exists, usually your notes: a summary, key points, next steps, action items and sentiment. | S | app/api/meetings.py:454-491; calendar_tasks.py:326-361; app/services/meeting_recording.py:9-15 |
| 40 | Your own notes are never changed by the AI. | S | MeetingRoom.tsx:167-170; calendar_tasks.py:349-357 (separate fields) |
| 41 | If you regenerate the summary, action items you already ticked stay ticked. | S | calendar_tasks.py:353-356,381-402 |
| 42 | When the meeting is completed, the summary is filed as a note on the lead in the CRM. | S | calendar_tasks.py:363-367; app/services/crm_events.py:370-376 |
| 43 | Action items that are yours (not the client's) can move the lead's "next action" date earlier, never later. | S | calendar_tasks.py:368-376; crm_events.py:401-447 |
| 44 | There is a Record & transcribe button in the meeting room, which sends a recording bot from … Recall.ai … | S | frontend/src/components/meetings/RecordingControl.tsx:57; app/api/recording.py:3 |
| 45 | Not verified against the live service. No Recall.ai credentials exist …, and parts of the integration (how it signs in and how the bot is created) are marked as not yet checked … | S | app/integrations/recall.py:10-21,150,163,187 |
| 46 | Your administrator must set it up under Admin › Integrations › Recall.ai. Until it is, sending a bot fails, and the transcript webhook is closed. | S | recall.py:200-207; app/api/recording.py:6-8,60-66,87-93 |
| 47 | The meeting needs a join link. Without one the button is disabled ("Add a join link to send a recording bot."). | S | RecordingControl.tsx:57-62 |
| 48 | When a transcript arrives, it replaces the notes-only summary with one built from the transcript and your notes. | S | meeting_recording.py:9-15,188-220 |
| 49 | Vectorae waits up to 60 minutes after the meeting for it by default (an administrator setting); a late transcript is still accepted. | S | system_settings.py:211-217; meeting_recording.py:68-69,127-131,227-232 |
| 50 | Transcripts are capped at 250,000 characters. | S | app/api/meetings.py:75; meeting_recording.py:55 |
| 51 | You can search a transcript and export it as PDF or TXT. | S | frontend/src/components/meetings/TranscriptViewer.tsx:3,75-121 |
| 52 | Vectorae does not collect recording consent. The bot records everyone on the call. | S | RecordingControl.tsx:57-62; app/api/recording.py (no consent capture) |
| 53 | The app reminds you: "Tell everyone on the call that it is being recorded." | S | RecordingControl.tsx:61 |
| 54 | … Vectorae does not enforce it. | S | app/api/recording.py:1-66 |
| 55 | On the lead's page, use Log meeting outcome. | S | frontend/src/components/leads/LogOutcomeDialog.tsx:73 |
| 56 | Pick an outcome, add notes, and for a closed-won outcome optionally a deal value. | S | LogOutcomeDialog.tsx:43-50,127-131 |
| 57 | Vectorae records the outcome first: … lead's status, … CRM activity and note, … result for reporting, … won deal for closed-won, and stops every live sequence … | S | app/services/meeting_followup.py:1-17,140,163-217 (the CRM note is written only when notes were entered) |
| 58 | It then writes a follow-up email and saves it as a Gmail draft. | S | meeting_followup.py:17-19 |
| 59 | It is never sent automatically. You edit it and send it yourself, from Vectorae or from Gmail. | S | meeting-prep.md:33-36; meeting_followup.py:17-19 |
| 60 | The suppression list is checked both when drafting and when sending. | S | meeting_followup.py:26-27 |
| 61 | Saving drafts needs Gmail's compose permission; if you connected Gmail before this feature existed, reconnect it. Until then the draft text is kept so you can copy it. | S | meeting-prep.md:48-51; meeting_followup.py:21-22 |

Summary (final, after re-check): 63 supported, 0 unsupported, 0 contradicted. (First pass: 59 S / 0 U / 2 C.)

---

### 16-crm-and-integrations.md
| # | Sentence (verbatim, may be shortened with …) | Verdict | Evidence (path:line) / what the code says |
|---|---|---|---|
| 1 | Vectorae has its own CRM, and it can also connect to HubSpot, Salesforce, Slack, and tools like Zapier or Make. | S | app/api/crm.py:1-2; app/integrations/hubspot.py, salesforce.py, slack.py; app/services/webhook_delivery.py |
| 2 | … none of the HubSpot, Salesforce or Slack connections has a recorded test against the live vendor yet. | S | docs/FULL_PRODUCT_AUDIT.md:119 ("Any live third-party API — no credentials; all integrations are mock-tested") |
| 3 | CRM in the main menu opens a CRM over the same leads your campaigns use, with dashboards and a spreadsheet-style table you edit directly. | S | nav.ts:34-38; frontend/src/app/(app)/crm/page.tsx:18 |
| 4 | You can edit cells inline, bulk-edit up to 500 rows, add notes, tags, saved views and custom fields, and see each lead's activity and meetings. | S | app/api/crm.py:1-2,103-104,369-376; frontend/src/components/crm/grid/LeadNotesPanel.tsx:3,50-51 |
| 5 | Pipeline shows the same leads as a kanban board. | S | nav.ts:34-37 |
| 6 | You can download your leads with Export CSV. | S | frontend/src/components/crm/grid/GridToolbar.tsx:106 |
| 7 | Export is one-way: there is no CSV import back into the table. | S | no import route in app/api/crm.py; the only `/import` routes are WhatsApp opt-ins and the LinkedIn network (whatsapp_optin.py:257; linkedin_network.py:68) |
| 8 | HubSpot: several parts of the code (the sign-in token exchange, the contact search, and linking deals to contacts) are marked as not yet checked … | S | app/integrations/hubspot.py:74,131,157 |
| 9 | Salesforce: there is no record of a test against a live Salesforce account. | S | docs/FULL_PRODUCT_AUDIT.md:119 |
| 10 | Slack: there is no record of a test against a live Slack workspace. | S | docs/FULL_PRODUCT_AUDIT.md:119 |
| 11 | Outbound webhooks and API keys are Vectorae's own features and do not depend on a vendor. | S | app/services/webhook_delivery.py; app/services/api_keys.py |
| 12 | All three vendor connections also need your Vectorae administrator to register the app first …; the card shows "An admin must add the … app under Admin › Integrations first." and Connect is disabled. | S | frontend/src/components/settings/CrmCards.tsx:104-109; SlackCard.tsx:76-81 |
| 13 | Go to Settings, open the Integrations tab, and click Connect on the HubSpot or Salesforce card. You sign in on the vendor's site. | S | CrmCards.tsx:104; settings/page.tsx:392-394; docs/features/crm-ecosystem.md:21-24 |
| 14 | Once connected, the card shows the account, how many leads and deals are linked, when data was last pushed and pulled, Sync now and Disconnect buttons, and the last error … ("reconnect to restore the sync"). | S | CrmCards.tsx:87-115 (the "reconnect…" phrase shows only when the connection status is "error") |
| 15 | Leads that engaged (replied, meeting booked, opportunity, closed, or disqualified) become HubSpot contacts or Salesforce leads, matched by email. | S | app/services/crm_sync.py:4-5,67-68; crm-ecosystem.md:26-28 |
| 16 | Tick "Also push every verified lead (by default only leads that replied or further)" to send every verified lead as well. | S | CrmCards.tsx:126; crm_sync.py:69,535 |
| 17 | Deals become HubSpot deals (linked to the contact) or Salesforce opportunities. | S | crm_sync.py:65; crm-ecosystem.md:28-30 |
| 18 | Changes are pushed straight away on key events … and also in a sweep every 15 minutes. | S | crm-ecosystem.md:30-31; celery_app.py:316-321; event_bus.py:104-106 |
| 19 | From your CRM to Vectorae, only for records Vectorae linked, and only forward | S | crm-ecosystem.md:33; crm_sync.py:571 |
| 20 | HubSpot lead status "Unqualified" makes the lead disqualified; an open deal or the "opportunity" lifecycle stage makes it an opportunity; the "customer" lifecycle stage makes it closed won. | S | crm_sync.py:93-94 ("open deal" is the hs_lead_status OPEN_DEAL value) |
| 21 | A deal or opportunity closed won or lost marks the deal and the lead won or lost. Deal amount and close date are copied. | S | crm-ecosystem.md:40-41 |
| 22 | A converted Salesforce lead becomes an opportunity; "Closed - Not Converted" becomes disqualified. | S | crm_sync.py:96-97,664-665 |
| 23 | A HubSpot deal created on a linked contact is imported as a Vectorae deal. | S | crm-ecosystem.md:44 |
| 24 | A CRM change never moves a lead backwards and never reopens a closed lead. | S | crm_sync.py:70-72,571; crm-ecosystem.md:46-47 |
| 25 | Closing a lead in this way stops its sequences. | S | crm-ecosystem.md:47-48 |
| 26 | The 15-minute sweep reads linked records back without any setup in your CRM; your CRM admin can also add webhooks … | S | crm-ecosystem.md:50-62 |
| 27 | On the Slack card …, click Connect, approve the app in Slack, then choose a Channel. You can send a test message. | S | SlackCard.tsx:37-41,66-102 |
| 28 | Vectorae posts meeting bookings, interested replies, campaigns paused automatically for a high bounce rate (manual pauses are not posted), and strategy changes on idle campaigns. | S | crm-ecosystem.md:7-12; sequence_engine.py:573-581; app/api/analytics.py:145-146 (manual pause sends `slack=False`) |
| 29 | It also posts meeting prep briefs, meeting reminders, objection spikes and deals won. | S | crm-ecosystem.md:13; event_bus.py:42-60 |
| 30 | Public channels work straight away. For a private channel, invite the bot to it before choosing it. | S | SlackCard.tsx:102; crm-ecosystem.md:15-16 |
| 31 | If Slack is unavailable, the notification is skipped; it never undoes the booking or event that caused it. | S | event_bus.py:83; notification_tasks.py:46-59 |
| 32 | On the Webhooks (Zapier, Make) card, click Add webhook, enter an HTTPS URL, choose the Events, and click Add. | S | frontend/src/components/settings/WebhooksCard.tsx:77-82,182-209 |
| 33 | The signing secret is shown once: "Copy it now — it will not be shown again." | S | WebhooksCard.tsx:32-38 |
| 34 | Available events include meeting booked, reply received, lead sourced and campaign paused, plus interested reply, deal won, call completed, strategy changed and objection spike. | S | webhook_delivery.py:61-73 |
| 35 | Every delivery carries an X-LeadPilot-Signature header … | S | webhook_delivery.py:21,338-345 |
| 36 | Any 2xx response counts as delivered. | S | webhook_delivery.py:351-357 |
| 37 | (re-check) A failed delivery is tried 5 times in total: once, then again after 30 seconds, 2 minutes, 10 minutes and 30 minutes. | S | webhook_delivery.py:78,327,370-379 (code unchanged; the 2-hour entry is still unreachable — finding F2) |
| 38 | A 410 Gone response turns the webhook off (the Zapier convention for a turned-off Zap). | S | webhook_delivery.py:26-28,358-364 |
| 39 | The URL must be public HTTPS. Private or internal addresses are refused, and redirects are not followed. | S | webhook_delivery.py:30-33,150-167,310,329-334 |
| 40 | The card's Recent deliveries list shows each event, its status, attempts, last response and time. | S | WebhooksCard.tsx:118-136 |
| 41 | On the API keys card, enter a Name and click Create key. | S | WebhooksCard.tsx:238-252 |
| 42 | The key starts with lpk_ and is shown only once; Vectorae stores only a scrambled (hashed) form. | S | app/services/api_keys.py:3-4,21,30-41 |
| 43 | Tools like Zapier and Make use it as Authorization: Bearer lpk_…. | S | WebhooksCard.tsx:240; crm-ecosystem.md:78-79 |
| 44 | You can have up to 10 active keys; revoke one to make another. | S | api_keys.py:22,35-38 |
| 45 | Revoke stops a key from working. | S | api_keys.py:51-52,64-69 |
| 46 | A key acts as you for the normal API, but it can never reach admin pages, even if it belongs to an admin. | S | api_keys.py:3-6 |

Summary (final, after re-check): 46 supported, 0 unsupported, 0 contradicted. (First pass: 45 S / 0 U / 1 C.)

---

### 17-learning-loop-and-ab-tests.md
| # | Sentence (verbatim, may be shortened with …) | Verdict | Evidence (path:line) / what the code says |
|---|---|---|---|
| 1 | Vectorae records what happens to every message it sends (sent, replied, booked and so on) … | S | app/db/models.py:1579-1611; outreach_tasks.py:525-528,1109-1113 |
| 2 | Nothing in the learning loop rewrites a live campaign on its own. | S | app/services/strategy_mutation.py:17-22; learning_tasks.py:259-265 (writes default_variant only, which nothing reads) |
| 3 | Every send, reply, booking and similar event is stored as an outcome record. | S | models.py:1579-1611 |
| 4 | (re-check) Every night (by default at 02:05 UTC, configurable by your deployment), Vectorae rolls these records up into scores for each strategy pattern: reply rate and booking rate, per variant. | S | app/workers/celery_app.py:211-217,235-238; app/core/config.py:151; score_decay.py:142-168 (see finding F1 for the data it actually sees) |
| 5 | Older results count for less. A result from 90 days ago counts half as much as one from today (the default half-life, configurable). | S | score_decay.py:5-16,35-37; app/core/config.py:156-161 |
| 6 | Vectorae also counts how much recent evidence there is, so a pattern with many old results can still count as "not enough data". | S | score_decay.py:15-16,184,222 |
| 7 | … the messaging step and the execution-plan step are given up to 8 of your account's best-scoring patterns that have enough data to be considered reliable. | S | app/pipeline/engine.py:128-139; app/services/playbook_service.py:33,55-64 |
| 8 | Only patterns from your own account's strategies are used. | S | playbook_service.py:42-53 (pattern keys are limited to the account's strategies). Note: the score behind a pattern key aggregates every account's outcomes with that key (score_decay.py:142-168 has no account filter). |
| 9 | On a new account there is no data yet. In that case the pipeline is told plainly that no learned data exists and works from research alone. | S | playbook_service.py:23-28,66-67,84-86 |
| 10 | Each sequence step carries a variant label (the default is "A"). | S | app/api/sequences.py:85 |
| 11 | Within one sequence each step number appears only once, so a step has exactly one variant. | S | app/api/sequences.py:164-167 |
| 12 | To compare variants you run sequences whose steps carry different labels within the same strategy. | S | learning_tasks.py:214-227 (grouped by strategy, then variant) |
| 13 | The sequence form in the app does not set variant labels, so steps created there are all variant "A"; labels can be set … through the Vectorae API. | S | frontend/src/lib/api/outreach.ts:6-10,26-36; app/api/sequences.py:85 |
| 14 | The A/B variants table on the CRM campaigns dashboard shows each variant's sends, reply rate and booking rate, counted from messages actually sent. | S | frontend/src/app/(app)/crm/dashboard/campaigns/page.tsx:67,218-250 |
| 15 | A variant with under 30 sends is flagged as below the sample size the promotion check needs … | S | crm/dashboard/campaigns/page.tsx:257-260 |
| 16 | (re-check) A nightly sweep (30 minutes after the nightly roll-up, at 02:35 UTC by default) checks strategies … | S | celery_app.py:235-243 |
| 17 | … that have at least two variants and at least 30 sends in total. | S | learning_tasks.py:214-227 |
| 18 | The measure is meetings booked per send. | S | app/services/ab_testing.py:171,200; learning_tasks.py:246-250 |
| 19 | Sample size: each variant has at least 30 sends. | S | ab_testing.py:14,178,189-197 |
| 20 | Significance: … p below 0.05. | S | ab_testing.py:15,179,199-209 |
| 21 | Minimum lift: the winner is at least 10% better, relative to the other. | S | ab_testing.py:16,180,211-222 |
| 22 | Harm limit: the winner's rate of bounces, unsubscribes and opt-outs is at most 5% of its sends. | S | ab_testing.py:17-18,137,181,224-232 |
| 23 | These four numbers are deployment settings; the values above are the defaults. | S | app/core/config.py:142-150 |
| 24 | For three or more variants, a different test is used: … differ significantly overall (p below 0.05), the best must beat the second-best after a correction for comparing many pairs, … at least the minimum lift better than the second-best, and its unsubscribe rate must be at most 5%. | S | app/services/multi_variate.py:8-13,245-248,320-366 |
| 25 | The code notes that results with fewer than 5 sends per variant should be treated as inconclusive. | S | multi_variate.py:18 |
| 26 | If any check fails, nothing is promoted. | S | ab_testing.py:189-236; learning_tasks.py:259 |
| 27 | Each strategy is promoted at most once. | S | learning_tasks.py:234-241,268-277 |
| 28 | Messages that have already been sent are never changed. | S | learning_tasks.py:259-279 (only the strategies row and an outcomes row are written) |
| 29 | … promotion records the winning variant on the strategy. In the current version, nothing reads that record when writing or scheduling future messages … | S | learning_tasks.py:260-265; `default_variant` is never read anywhere else (models.py:928) |
| 30 | If a campaign has been sending for 7 days (the default, set by your administrator) with zero replies, counted from its first sent message, Vectorae reviews it. | S | app/services/strategy_mutation.py:3-8,132-143; system_settings.py:45-48 |
| 31 | AI looks at the strategy, the target customer, the step briefs and the numbers, and proposes a diagnosis and three changes: … messaging angle, … channel recommendation, and target refinements, plus rewritten messaging. | S | strategy_mutation.py:10-15,56-66 |
| 32 | This is saved as a proposed new version of the strategy and you are notified. | S | strategy_mutation.py:18-19,264-299,326-335 |
| 33 | It is never applied automatically; applying it is your decision. | S | strategy_mutation.py:17-22 |
| 34 | At most one automatic proposal is made per idle period. | S | strategy_mutation.py:7-8 |
| 35 | Smart send time is a per-campaign switch. | S | frontend/src/components/campaigns/SendTimePanel.tsx; app/services/send_windows.py:1-28 |
| 36 | Vectorae scores each day-and-hour slot in the lead's own time zone by opens plus three times replies. | S | send_windows.py:5,9,76-104 |
| 37 | Once a campaign has 50 opens (the default), it works out its top windows, using only hours inside your allowed send window. | S | send_windows.py:14-18,120-128; system_settings.py:58-59 |
| 38 | … moved to the next of the top 3 windows at or after its normal time, never earlier and never more than 72 hours later (the default). | S | send_windows.py:24-25,56; system_settings.py:72-73 |
| 39 | If no window fits, it sends at its normal time. | S | send_windows.py:162-167 |
| 40 | Turning it on also moves steps already scheduled but not yet sent; turning it off leaves them where they are. | S | send_windows.py:26-28 |
| 41 | The learning-loop insights pages (send-time recommendations, subject-line patterns and playbook scores) need a plan with playbook access, and the multi-variant results page needs a plan with A/B testing. | S | app/api/playbook.py:34-46,68-80,106-121; app/api/strategies_advanced.py:30-42 |
| 42 | Both are included in Starter, Growth, Scale, Pay per meeting, Pro and Enterprise, and not in Free. | S | app/core/plans.py:59-60,76-77,95-96,111-112,130-131,150-151,168-169 |
| 43 | Other accounts get an upgrade message (HTTP 402). | S | app/core/plans.py:8-16,238-257 |

Summary (final, after re-check): 43 supported, 0 unsupported, 0 contradicted. (First pass: 41 S / 0 U / 2 C.)

---

### 18-analytics-health-score-roi.md
| # | Sentence (verbatim, may be shortened with …) | Verdict | Evidence (path:line) / what the code says |
|---|---|---|---|
| 1 | Vectorae reports … in several places: the Analytics page, the Revenue & ROI page, a shareable ROI dashboard, and a Pipeline Health Score. | S | frontend/src/app/(app)/analytics/page.tsx; analytics/revenue/page.tsx:85; ShareLinksCard.tsx; app/api/analytics.py:8-10 |
| 2 | A single number from 0 to 100 for one campaign, made from four parts. Each part is scored 0 to 100, then weighted | S | app/services/pipeline_health.py:7-14,53-61 |
| 3 | Reply rate (35%): replies divided by sends, as a percentage. A 10% reply rate scores 10 on this part. | S | pipeline_health.py:101-109,157-165,195 |
| 4 | Sequence completion (25%): finished enrollments divided by all enrollments. | S | pipeline_health.py:167-178,196 |
| 5 | Lead freshness (20%): full marks if your newest lead is up to 3 days old, zero at 30 days or older, sliding in between. | S | pipeline_health.py:63-66,112-127 |
| 6 | Open conversations (20%): 10 points for each lead sitting at Replied, up to 100. | S | pipeline_health.py:68-71,185-198 |
| 7 | 0–40 critical / 41–60 low / 61–80 moderate / 81–100 strong, with the four messages | S | pipeline_health.py:73-80,88-98 |
| 8 | Because the reply-rate part uses the raw percentage, a campaign with a normal cold-outreach reply rate earns only a few points from it. | S | pipeline_health.py:195 |
| 9 | If the calculation fails, the score shows 0 and "critical" with an error flag … | S | pipeline_health.py:140-150,218-229 |
| 10 | The score is refreshed every six hours for verified and running campaigns, and recalculated live when requested. | S | celery_app.py:352-358; app/workers/health_tasks.py:35,54; app/api/analytics.py:199-220 |
| 11 | It is available on every plan. | S | app/api/analytics.py:8-10,215 |
| 12 | The web app does not currently display it; it is available through the Vectorae API. | S | no frontend call to /strategies/{id}/health (grep). The marketing page still advertises it (frontend/src/app/how-it-works/page.tsx:31); see finding F9. |
| 13 | Choose a campaign on Analytics to see …: reply quality (the raw reply rate next to the positive reply rate), sequence completion, attribution ("What earned the outcomes"), and benchmarks ("How you compare"). | S | components/analytics/ReplyQualityPanel.tsx:41-53; CompletionPanel.tsx:54; AttributionPanel.tsx:70; BenchmarkPanel.tsx:44 |
| 14 | The page also links to Revenue & ROI. | S | analytics/page.tsx:78 |
| 15 | The positive reply rate counts only replies labelled interested. | S | app/services/reply_intent.py:61-65,294 |
| 16 | Replies that could not be classified are counted as unclassified, never guessed. | S | reply_intent.py:288-292,324 |
| 17 | Every booked meeting, won deal and interested reply is credited to a message, and Vectorae always records how it decided and how sure it is | S | app/services/attribution.py:59-69,137-181,257-258 |
| 18 | Direct reply: … Confidence 1.0. | S | attribution.py:13-15,153 |
| 19 | Thread match: … Confidence 0.85. | S | attribution.py:16-17,155-164 |
| 20 | Last touch: … 0.7 within a day, 0.55 within 3 days, 0.4 within a week, 0.25 within a month, 0.1 after that. | S | attribution.py:18-22,82-83,96-104 |
| 21 | None: nothing was sent before the outcome, so nothing is credited. | S | attribution.py:23,181 |
| 22 | The panel groups results by step and by channel, and each group shows how many entries are confirmed. | S | AttributionPanel.tsx:96-120 |
| 23 | When fewer than half are confirmed, a caveat appears above the totals. | S | frontend/src/lib/attribution.ts:97-98; AttributionPanel.tsx:89-92 |
| 24 | Attribution is updated every 15 minutes, and Recompute runs it now. | S | celery_app.py:332-338; AttributionPanel.tsx:82 |
| 25 | A message sent after the outcome is never credited. | S | attribution.py:111-118 |
| 26 | How you compare shows your reply rate, meeting-booked rate and bounce rate per channel next to the spread across other accounts on this Vectorae deployment over the last 90 days. | S | app/services/benchmarks.py:4-5,67-70,248-286; system_settings.py:224-225 |
| 27 | It is not an industry statistic. | S | benchmarks.py:4-6 |
| 28 | An account counts only with at least 30 sends in that group. | S | benchmarks.py:201-203; system_settings.py:222-223 |
| 29 | A group is shown only if at least 10 accounts are in it. This can never be set below 5. Smaller groups are not stored at all. | S | benchmarks.py:74,82-87,205-209,221-223; system_settings.py:220-221 |
| 30 | Only the 25th, 50th (median) and 75th percentiles are shown, rounded to half a percentage point. The number of accounts is shown as a band (10+, 25+, 100+). | S | benchmarks.py:19-21,75,101-118,215-217 ("5+" is also possible if the minimum is lowered to 5–9) |
| 31 | Suspended accounts are excluded. | S | benchmarks.py:182,192-193 |
| 32 | If not enough accounts qualify, you will not see a comparison. | S | benchmarks.py:205-209 |
| 33 | Open Analytics, then Revenue & ROI, and pick a period (30 days, 90 days, 12 months or year to date). | S | analytics/revenue/page.tsx:33-36 |
| 34 | Revenue: deals marked won, dated by close date. | S | app/services/revenue_analytics.py:4-5,122-134 |
| 35 | Meetings: distinct leads with a booked meeting in the period. | S | revenue_analytics.py:6,106-118 |
| 36 | Cost: costs you record with Add cost (data, tools, ads, or hours × rate), metered AI usage …, AI call minutes, and a share of account-wide costs spread by each campaign's sends. | S | revenue_analytics.py:7-13,141-213; analytics/revenue/page.tsx:40-44,340 (pay-per-meeting fees are also included, :180-194) |
| 37 | Cost / meeting, Cost / deal, and ROI = (revenue − cost) ÷ cost. ROI is blank when there is no cost. | S | revenue_analytics.py:25,82-87 |
| 38 | The report uses your most common deal currency (USD if you have no deals). | S | revenue_analytics.py:17-19,75-79 |
| 39 | Amounts in other currencies are left out and counted in a notice, never converted. | S | revenue_analytics.py:19-21,130-131,148-149 |
| 40 | AI costs are in USD, so they are only included in a USD report. | S | revenue_analytics.py:21-23,164-165,177-178 |
| 41 | In Settings you can create a share link with a title, one campaign or All campaigns, and an expiry (default 30 days, up to 365). | S | ShareLinksCard.tsx:26,60-81; app/services/share_links.py:43,87-91; app/api/share_links.py:40 |
| 42 | The link is shown once. | S | ShareLinksCard.tsx:4; share_links.py:7 |
| 43 | Anyone with it can view a read-only page until it expires or you click Revoke. | S | share_links.py:9-10,104-121; ShareLinksCard.tsx:113 |
| 44 | Creating a link requires a verified phone number when your deployment requires phone verification, which is the default. | S | app/api/share_links.py:50; app/services/identity.py:74-77,164-173; app/config.py:465-468 (applies to accounts flagged `identity_required`, i.e. those created after migration 0039) |
| 45 | It shows six numbers | S | app/services/roi_calculator.py:72-73 |
| 46 | Meetings booked: booked meetings from leads whose sequence reached step 3 or later. Meetings booked off steps 1 or 2 are not counted. | S | roi_calculator.py:62-64,161-186 (note: only leads whose current status is still "Meeting booked" are counted; leads that moved on to opportunity or closed drop out) |
| 47 | (re-check) Pipeline value: the estimated deal value of leads currently at Meeting booked, Proposal sent or Closed won (not limited to the date range). | S | roi_calculator.py:15-17,66-68,189-196 |
| 47a | (re-check, new) Leads at Opportunity are not included. | S | roi_calculator.py:67-68 |
| 48 | Messages sent, and reply rate (unique leads who replied ÷ leads contacted). | S | roi_calculator.py:140-159 |
| 49 | Time saved: an estimate of 15 minutes per message plus 90 minutes per meeting. | S | roi_calculator.py:56-60,213-215 |
| 50 | Revenue attributed: value from leads that closed won. | S | roi_calculator.py:198-206 |
| 51 | These are based on lead statuses, so they can differ from the deal-based Revenue & ROI page. | S | roi_calculator.py:21-25 |

Summary (final, after re-check): 52 supported, 0 unsupported, 0 contradicted. (First pass: 50 S / 0 U / 1 C.)

---

### 19-deliverability-and-mailbox-health.md
| # | Sentence (verbatim, may be shortened with …) | Verdict | Evidence (path:line) / what the code says |
|---|---|---|---|
| 1 | Vectorae checks two things: the health of each sending domain … and the health of each mailbox you send from. | S | app/services/deliverability.py:1-26; app/services/mailbox_health.py:1-9 |
| 2 | A mailbox in trouble is slowed down or paused automatically, and paused messages wait rather than being dropped. | S | mailbox_health.py:29-37; outreach_tasks.py:310-352 |
| 3 | You find both under Settings, on the Deliverability tab. | S | settings/page.tsx:533-543; settings-tabs.ts:17 |
| 4 | You or whoever manages your domain adds them at your DNS provider. Vectorae only reads them; it cannot change them. | S | deliverability.py:68-86,108-120 (DNS lookups only) |
| 5 | The Email health card checks the domain of each connected Gmail address. | S | deliverability.py:96-105; components/settings/DeliverabilityCard.tsx:110 |
| 6 | Shared consumer domains such as gmail.com are skipped … | S | deliverability.py:4,54,103 |
| 7 | no SPF record: −25 | S | deliverability.py:168-170 |
| 8 | no DMARC record: −25 (or −10 if DMARC is p=none) | S | deliverability.py:171-176 |
| 9 | DKIM not found under Google's selector (google._domainkey): −15 | S | deliverability.py:117-118,177-179 |
| 10 | a bounce rate over 2% for your sends in the last 30 days: up to −30 | S | deliverability.py:150-163,180-183 |
| 11 | the domain being on a blocklist: −40 | S | deliverability.py:184-186 |
| 12 | If the deployment has a Mailreach key configured, its inbox-placement reputation is also read and the lower of the two scores is used. | S | deliverability.py:17,232-242 |
| 13 | The Mailreach connection is marked … not yet checked …, so treat it as not yet verified … | S | app/integrations/mailreach.py:8 |
| 14 | Below 70 (the default threshold), you get a one-time warning, and launching a campaign returns a warning too. | S | deliverability.py:263-269,320-328; system_settings.py:100-101; app/api/sequences.py:307-313 (the warning fires again each time the score drops back below the threshold) |
| 15 | Click Run check now to check immediately. | S | DeliverabilityCard.tsx:118 |
| 16 | Domains are checked against blocklists daily at 06:10 UTC and on demand. | S | celery_app.py:339-342; DeliverabilityCard.tsx:118 |
| 17 | Without an MXToolbox key, Vectorae queries Spamhaus DBL, SURBL and URIBL directly. | S | deliverability.py:13-14,53,123-147 |
| 18 | Spamhaus refuses queries from public DNS servers; when that happens the list is shown as "could not be queried", never as listed. | S | deliverability.py:15-16,140-146; DeliverabilityCard.tsx:75 |
| 19 | When a domain is newly listed, every active campaign on your account is paused … | S | deliverability.py:197-207,252-254 |
| 20 | (re-check) … and an urgent alert goes out by push notification and Slack. | S | deliverability.py:255-262; app/services/event_bus.py:80-81,98-101 |
| 21 | Being removed from the list does not restart anything; you resume campaigns yourself. | S | deliverability.py:25-26 |
| 22 | Two mailboxes on the same domain can have very different reputations, so Vectorae also scores each mailbox and acts only on the one in trouble. | S | mailbox_health.py:3-9 |
| 23 | The Mailbox health card shows each mailbox's score out of 100, its state, the reasons, its complaint and bounce rates, and how much it sent today. | S | mailbox_health.py:468-493; components/settings/MailboxHealthCard.tsx:125-142 |
| 24 | Scores refresh every 4 hours; Check now refreshes them immediately. | S | celery_app.py:343-351; MailboxHealthCard.tsx:76 |
| 25 | A mailbox that has not been checked yet is shown as unchecked. | S | mailbox_health.py:458-460,496-518 |
| 26 | no SPF: −25; no DMARC: −20 (−10 for p=none); no DKIM: −10 | S | mailbox_health.py:230-243 |
| 27 | complaint rate of 0.1% or more: −35; 0.3% or more: −65 | S | mailbox_health.py:89-90,248-253 |
| 28 | bounce rate of 2% or more: −35; 5% or more: −65 | S | mailbox_health.py:91-92,255-260 |
| 29 | a volume spike (3 times or more the 7-day average, with at least 20 sends today): −10 | S | mailbox_health.py:94-96,203-213,262-265 |
| 30 | A brand-new mailbox with no history is not penalised for missing rates. | S | mailbox_health.py:154-160,179-182 (rates are None, so no deduction) |
| 31 | A mailbox missing all three DNS records lands at 45: slowed down, not stopped. | S | mailbox_health.py:71-76 |
| 32 | Vectorae has no connection to Gmail's spam-report data (a feedback loop or Google Postmaster Tools) … | S | mailbox_health.py:21-27 |
| 33 | … the complaint rate counts unsubscribes plus replies asking you to stop, divided by sends. | S | mailbox_health.py:170-200 (opt-outs are counted too) |
| 34 | The card labels it "(proxy)". | S | MailboxHealthCard.tsx:142 |
| 35 | 70 or more healthy / 40 to 69 throttled (25% of the normal warm-up allowance, never below 2 a day) / under 40 paused (sends nothing) | S | mailbox_health.py:29-37,77-82,270-281 |
| 36 | When a mailbox is paused, its messages are moved to the next day's send window with the reason recorded. They are deferred, never cancelled. | S | outreach_tasks.py:339-350 |
| 37 | When a throttle and a compliance rule both set a limit, the smaller one applies; a throttle can never raise a limit. | S | outreach_tasks.py:311-338 |
| 38 | A paused mailbox is never resumed automatically, even if a later check scores higher. | S | mailbox_health.py:39-41,345-352 |
| 39 | Click Resume on the mailbox. If its score is still under 70, it comes back throttled, not at full speed. | S | mailbox_health.py:438-450; MailboxHealthCard.tsx:125-128 |
| 40 | These limits are applied to email sends from your connected Gmail mailboxes. | S | mailbox_health.py:112-120; outreach_tasks.py:309-352 |
| 41 | If the health check itself fails, the mailbox is treated as healthy … | S | mailbox_health.py:417-435 |
| 42 | A whole campaign is paused if its bounce rate goes over 3% once at least 10 messages have been sent (deployment defaults; a workspace compliance rule can set a lower threshold, never a higher one). | S | app/config.py:113-114; sequence_engine.py:527-555; compliance_rules.py:128-135,229-230,245-249 |
| 43 | It stays paused until a person resumes it. | S | sequence_engine.py:559-561 |

Summary (final, after re-check): 43 supported, 0 unsupported, 0 contradicted. (First pass: 42 S / 0 U / 1 C.) New source `app/services/webhook_delivery.py` exists.

---

### 20-compliance.md
| # | Sentence (verbatim, may be shortened with …) | Verdict | Evidence (path:line) / what the code says |
|---|---|---|---|
| 1 | Vectorae builds several compliance safeguards into how it sends: an unsubscribe route in every email, a suppression list checked right before every send, rules that depend on where the recipient is, and a record of what was checked. | S | app/services/sequence_engine.py:8-15; app/services/compliance_audit.py:1-7 |
| 2 | … a footer with the sender identity (your business name and postal address, set by whoever runs your deployment) and an unsubscribe link: "Don't want these emails? Unsubscribe instantly" | S | sequence_engine.py:439-444; app/config.py:105 |
| 3 | List-Unsubscribe headers that support one-click unsubscribe in mail apps that offer it. | S | sequence_engine.py:447-455 |
| 4 | A production deployment refuses to start if the sender identity is missing or still the placeholder address, or if the public address used to build unsubscribe links is not set. | S | app/core/production_guard.py:18-22,148-175,220-245,317-336 |
| 5 | Depending on the recipient's region, an extra notice is added above the footer | S | sequence_engine.py:456-463 |
| 6 | EU and UK: a statement that the email is sent because their professional role matches your offer (legitimate interest), and that they can object at any time by replying "stop" or using the link. | S | compliance_audit.py:49-55 |
| 7 | Canada: "Sent by [your sender identity]", plus how to unsubscribe by link or by replying "stop". | S | compliance_audit.py:56-57,61-64 |
| 8 | Clicking the unsubscribe link takes effect immediately; no login is needed. | S | app/api/unsubscribe.py:1-4,50 |
| 9 | The person sees "You're unsubscribed." | S | unsubscribe.py:27 |
| 10 | … adds them to the suppression list on every channel at once: email, phone, LinkedIn, and WhatsApp (their WhatsApp opt-in is revoked) | S | app/services/consent.py:219-296 |
| 11 | stops every sequence they are in | S | sequence_engine.py:505-508 |
| 12 | records the instruction in the consent ledger. | S | consent.py:298-302 |
| 13 | A reply asking to stop ("remove me", "stop emailing me", "take me off your list") is treated exactly like clicking the link. | S | reply_classification.py:39-40; outreach_tasks.py:1084-1088 |
| 14 | A WhatsApp STOP also suppresses email. | S | app/services/whatsapp_optin.py:208-221; app/api/webhooks_whatsapp.py:459-468 |
| 15 | (re-check) You can do the same yourself on a lead's page: in the Can we contact them? panel, choose They asked us to stop, then Confirm — suppress everywhere. | S | frontend/src/components/leads/ConsentPanel.tsx:63,110 |
| 16 | A suppressed person is never contacted again from any campaign on your deployment. | S | app/workers/lead_tasks.py:113-120 (one deployment-wide list); outreach_tasks.py:187-196 |
| 17 | … when leads are sourced, so suppressed people are not imported | S | lead_tasks.py:221-223,283-285,340-341 (sourcing checks email and phone; LinkedIn is checked at enrolment and send) |
| 18 | … at the moment each message is sent, for email address, phone number and LinkedIn profile together | S | outreach_tasks.py:185-188 |
| 19 | … again inside the LinkedIn and WhatsApp senders, right before the provider is called. | S | app/integrations/linkedin_channel.py:48-56; app/integrations/whatsapp.py:146-147 |
| 20 | If a match is found at send time, the message is cancelled and the person's sequence is stopped. | S | outreach_tasks.py:189-196 |
| 21 | Viewing and adding entries to the full suppression list in Settings is limited to administrators. | S | frontend/src/lib/settings-tabs.ts:4-7,26; settings/page.tsx:499-506 |
| 22 | It uses the country on the lead's enrichment record. If there is none, it uses the lead's time zone. | S | app/services/compliance_region.py:9-15,124-131 |
| 23 | If neither is known, the region is "unknown" and a baseline of sender identification and a working unsubscribe applies. | S | compliance_audit.py:25-26,70-73 |
| 24 | US – CAN-SPAM – opt-out regime | S | compliance_region.py:54; compliance_audit.py:40 |
| 25 | Canada – CASL – implied consent assumed – Vectorae cannot verify it | S | compliance_region.py:55; compliance_audit.py:12-16,41 |
| 26 | EU/EEA – GDPR – legitimate interest (B2B); right to object stated | S | compliance_region.py:56; compliance_audit.py:42 |
| 27 | UK – UK GDPR / PECR – legitimate interest (B2B); corporate subscriber | S | compliance_region.py:57; compliance_audit.py:43 |
| 28 | Singapore – PDPA – business contact information; Do-Not-Call registry not checked | S | compliance_region.py:58; compliance_audit.py:44 |
| 29 | Australia / New Zealand – Spam Act 2003 / UEMA 2007 – inferred consent | S | compliance_region.py:59-60; compliance_audit.py:45-46 |
| 30 | Vectorae does not check any national Do-Not-Call registry and cannot verify implied consent. The records say so. | S | compliance_audit.py:41,44,81-83; system_settings.py:91-94 |
| 31 | Outreach emails can carry a tracking pixel to count opens, but never for EU, EEA or UK leads, because a tracking pixel needs consent under ePrivacy and PECR rules. | S | app/services/open_tracking.py:76-80; compliance_region.py:134-137 |
| 32 | Your administrator can turn open tracking off entirely. | S | system_settings.py:66-68 |
| 33 | Opens are approximate; replies are the reliable signal. | S | system_settings.py:69-71 (prefetch filter) |
| 34 | Send window: by default messages go out between 09:00 and 17:00 in the lead's time zone, weekdays only. | S | app/config.py:109-112; sequence_engine.py:64-107 (falls back to UTC when the lead has no time zone) |
| 35 | WhatsApp: cold messages need an approved Meta template and a recorded opt-in, in every country. | S | outreach_tasks.py:222-255; consent.py:105-110 |
| 36 | AI phone calls are off by default (an administrator setting). | S | system_settings.py:90-94 |
| 37 | When they are on, by default a lead is only called if their phone consent has been recorded; otherwise the call step is skipped and the sequence continues. | S | system_settings.py:95-97; outreach_tasks.py:842-844 |
| 38 | AI-voice calls are regulated in the US under the TCPA. | S | system_settings.py:91-92 |
| 39 | Pre-launch review: a sequence is checked before launch for compliance problems, such as briefs that remove the unsubscribe footer, misleading "Re:" subject lines, or a placeholder postal address. | S | app/services/adversarial_review.py:154-164,217-223 (the placeholder address blocks only in production; elsewhere it is a warning) |
| 40 | Blocking findings stop the launch unless an owner or manager overrides them with a written reason. | S | adversarial_review.py:16-17,323-329; app/api/sequence_reviews.py:52-60 |
| 41 | (re-check) Your administrator can set rules per workspace, region and channel (Admin › Compliance Rules) | S | app/services/compliance_rules.py:1-9,177-178 |
| 42 | (re-check) … a different send window anywhere between 07:00 and 20:00, weekend sending on or off, lower daily caps, a lower bounce-pause threshold, or requiring recorded consent. | S | compliance_rules.py:61-68,118-138,219-230 |
| 43 | (re-check) Daily caps and the bounce-pause threshold can only be lowered, never raised past the deployment defaults. | S | compliance_rules.py:14-15,125-135,226-230 |
| 43a | (re-check, new) The send window can be set anywhere between 07:00 and 20:00, which can be wider than the default 09:00–17:00. | S | compliance_rules.py:64-68,118-124,219-225; app/config.py:109-110 |
| 44 | (re-check) If a matching rule is invalid, Vectorae uses the strictest combination of the defaults and the valid rules. | S | compliance_rules.py:23-30,197-217 |
| 44a | (re-check, new) If the rules cannot be read at all, it falls back to the deployment defaults. | S | compliance_rules.py:21-22,184-189 |
| 45 | Because Vectorae records no consent for email or LinkedIn, a "consent required" rule on those channels stops those sends. | S | compliance_rules.py:32-36,262-263; outreach_tasks.py:261-266 (the step is skipped and the sequence continues) |
| 46 | The compliance audit log has one entry per send, and per send refused on compliance grounds: region, regime, decision, legal basis and the checks made. | S | compliance_audit.py:1-7,89-100; outreach_tasks.py:191-192,224,533 (refusals audited today: suppressed, no address, no WhatsApp consent) |
| 47 | You can see it under Settings, Deliverability, in the Compliance audit log table. | S | DeliverabilityCard.tsx:138,148; settings/page.tsx:533-539 |
| 48 | The consent ledger is an append-only record of consent granted …, withdrawn, suppressed and erased, with the source and who acted. | S | consent.py:58-62,178-182; models.py:4414-4458 |
| 49 | It answers "when did they tell us to stop, and what did we do?". | S | models.py:4416-4420 |
| 50 | Entries survive even if the lead is later deleted. | S | models.py:4422-4426,4437-4439 |
| 51 | Delete the lead. Vectorae erases the lead's personal data, puts their email, phone and LinkedIn profile on the suppression list …, and records the erasure in the consent ledger first. | S | app/api/leads.py:281-323; consent.py:318-323 |

Summary (final, after re-check): 53 supported, 0 unsupported, 0 contradicted. (First pass: 47 S / 0 U / 4 C.)

---

## Totals (articles 11–20) — FINAL, after the re-check of the writer's corrections

| Article | Supported | Unsupported | Contradicted |
|---|---|---|---|
| 11-linkedin | 79 | 0 | 0 |
| 12-send-review-queue | 59 | 0 | 0 |
| 13-replies-and-unified-inbox | 58 | 0 | 0 |
| 14-booking-and-calendar | 53 | 0 | 0 |
| 15-meetings-prep-room-transcripts | 63 | 0 | 0 |
| 16-crm-and-integrations | 46 | 0 | 0 |
| 17-learning-loop-and-ab-tests | 43 | 0 | 0 |
| 18-analytics-health-score-roi | 52 | 0 | 0 |
| 19-deliverability-and-mailbox-health | 43 | 0 | 0 |
| 20-compliance | 53 | 0 | 0 |
| **Total** | **549** | **0** | **0** |

First pass was 518 S / 0 U / 20 C. All 20 flagged sentences were rewritten. The re-check also scored 11 new sentences next to them. Rows marked "(re-check)" changed in this pass.

Front-matter sources: all paths exist in all ten articles. Sources added since the first pass, all present:
- 12: `app/db/models.py`
- 13: `frontend/src/lib/api/inbox.ts`, `app/services/inbox.py`
- 14: `app/db/models.py`
- 15: `frontend/src/app/(app)/meetings/detail/page.tsx`, `frontend/src/components/meetings/PlatformLauncher.tsx`
- 19: `app/services/webhook_delivery.py`

## Corrections the code supports (first pass; all applied by the writer and verified in the re-check)

1. **11 #78** "It works on every plan, so you can remove your data even after a downgrade." Replace with: "The delete button appears only while your plan includes the Network page. After a downgrade the page shows only the upgrade notice, so contact support (or use the API: `DELETE /linkedin-network`, which works on every plan) to remove your data." Alternatively, fix the UI so the button shows on every plan (finding F5).
2. **12 #19** Replace with: "You can filter by Pending, Approved or Rejected."
3. **12 #22** Replace with: "Each item shows who it is for, their title and company, the step number and channel, how long it has been waiting, and a badge for each rule that applied. The most serious rule is also named in the item's headline."
4. **12 #35** Replace with: "The prospect stays enrolled, but rejecting does not schedule the next step. If automatic follow-up is on for the previous step (it is by default), Vectorae later tries that same step again as a new message. By default this happens 72 hours after the previous step was sent, and the new message is checked by the review queue again. To stop contacting the person, stop or pause them." (See finding F3.)
5. **13 #39** Replace with: "If your administrator turns it on, a return message is scheduled. In the current version it is cancelled when it is due to send, because the prospect's 'not now' reply already stopped that sequence. Treat the reminder as your cue to write to them yourself." (See finding F4.)
6. **13 #44** Replace with: "Needs reply – threads with at least one reply from a person that has not been marked handled. These are listed oldest first …"
7. **13 #50** Replace with: "The Inbox menu item does not show a count. The Needs reply list shows each waiting person once, however many messages they sent."
8. **14 #15** Replace with: "If you have no availability, your booking pages offer no times. Your Calendar page warns you: 'No availability set — nobody can book you yet.'"
9. **14 #34** Replace with: "If two people try to book the same time on the same booking page at the same moment, the database allows only one of them; the second gets an error."
10. **15 #30** Replace with: "Click **Open in Google Meet / Zoom / Microsoft Teams** (it opens in the meeting tool; it is not embedded), or use the copy button next to the link."
11. **15 #32** Replace with: "Type **Live notes**, which save as you go. After you end the meeting, you can review and add action items under the AI summary."
12. **16 #37** Replace with: "A failed delivery is tried 5 times in total: once, then again after 30 seconds, 2 minutes, 10 minutes and 30 minutes." (Or fix the code so the 2-hour retry happens; see finding F2.)
13. **17 #4** Change "02:00 UTC" to "02:05 UTC".
14. **17 #16** Replace with: "A nightly sweep (30 minutes after the nightly roll-up, at 02:35 UTC by default) …"
15. **18 #47** Replace with: "Pipeline value: the estimated deal value of leads currently at Meeting booked, Proposal sent or Closed won (not limited to the date range). Leads at Opportunity are not included."
16. **19 #20** Replace with: "… and an urgent alert goes out by push notification and Slack." (Webhook targets cannot subscribe to this event; see finding F6.)
17. **20 #15** Replace with: "You can do the same yourself on a lead's page: in the **Can we contact them?** panel, choose **They asked us to stop**, then **Confirm — suppress everywhere**."
18. **20 #42** Replace with: "… a different send window anywhere between 07:00 and 20:00, weekend sending on or off, lower daily caps, a lower bounce-pause threshold, or requiring recorded consent."
19. **20 #43** Replace with: "Daily caps and the bounce-pause threshold can only be lowered, never raised past the deployment defaults. The send window can be set anywhere between 07:00 and 20:00, which can be wider than the default 09:00–17:00."
20. **20 #44** Replace with: "If a matching rule is invalid, Vectorae uses the strictest combination of the defaults and the valid rules. If the rules cannot be read at all, it falls back to the deployment defaults."

## Out-of-scope discoveries (reported, not fixed)

These were found while checking. They are code or doc issues, not article wording issues. Each needs triage under the CLAUDE.md scope rule.

- **F1. The learning loop and A/B promotion read columns the send path never sets.** The nightly roll-up joins `outcomes.strategy_id` (app/services/score_decay.py:142-154). The promotion sweep and the variant stats filter on `outcomes.strategy_id` and `outcomes.variant` (app/workers/learning_tasks.py:215-227; app/services/ab_testing.py:140-150; multi_variate.py:400-430). But the SENT / REPLIED outcomes written by the send and reply paths set neither column; the variant goes into `meta_json` only (app/workers/outreach_tasks.py:522-528,1109-1113,1175-1177,1228-1229). Only open/click events (open_tracking.py:148-150,233-235) and the calendar BOOKED outcome (calendar_tasks.py:183-185) set them. The only backfill is the one-time migration 0008 (alembic/versions/0008_m8c2_learning_loop.py:56-62). Likely effect: playbook scores and auto-promotion see almost no send data from new sends. Not exercised against a real database; confirm with a query on a seeded DB.
- **F2. Webhook retry off-by-one.** The 2-hour delay in RETRY_DELAYS_SECONDS is unreachable (app/services/webhook_delivery.py:78,327,370-377), while the docstring (:26) and docs/features/crm-ecosystem.md:74 promise "30s → 2h over 5 attempts".
- **F3. Held messages are invisible to the follow-up sweep.** `_has_pending_message` counts only SCHEDULED and SENDING (outreach_tasks.py:1386-1393), so an AWAITING_REVIEW message does not block it. If a held message waits longer than the previous step's follow-up delay (default 72 hours), the sweep creates a second message for the same step number (outreach_tasks.py:1440-1470,1546-1564). If both are approved or pass, the prospect can receive that step twice. After a reject, the same sweep re-creates the rejected step.
- **F4. The re-engagement auto-send is cancelled at send time.** The return message is attached to the prospect's last sequence (reengagement_memory.py:484-501), whose enrollment the "not now" reply already stopped (outreach_tasks.py:1104-1107). send_message_impl then cancels it (outreach_tasks.py:173-177). The test only asserts SCHEDULED (tests/test_reengagement_memory.py:292-309). The module docstring also says auto-send is on by default (reengagement_memory.py:20), but the setting default is False (system_settings.py:132).
- **F5. The Network "Delete my uploaded connections" button is hidden for ineligible plans** (network/page.tsx:210,236-241), even though the API delete is intentionally ungated for downgraded accounts (app/api/linkedin_network.py:134-138).
- **F6. `domain_blacklisted` is passed a webhook payload but is not a subscribable webhook event** (deliverability.py:255-262 vs webhook_delivery.py:61-76,128-130). The same is true for `deliverability_warning`, `mailbox_paused` (mailbox_health.py:383-391) and `send_needs_review` (send_review.py:333-340).
- **F7. The double-booking guard is per page, not per host** (models.py:2453-2454). A concurrent race across two booking pages of one host can double-book.
- **F8. Unused inbox count.** `countInbox` (frontend/src/lib/api/inbox.ts:25) has no caller, so the nav has no Inbox badge.
- **F9. Marketing copy promises a feature the app does not show.** frontend/src/app/how-it-works/page.tsx:31 promises "a Pipeline Health Score updated every 6 hours", but the web app never displays the score.
- **F10. Playbook scores are aggregated across all accounts per pattern_key.** score_decay.py:142-168 has no account filter. Only the choice of pattern keys is account-scoped (playbook_service.py:42-53). This is low impact under single-tenant P0-D, but it contradicts the "learned from this account's real outcomes" label (playbook_service.py:69).

---

# Help-center fact check: articles 21-30

Checker: help-center-fact-checker (read-only). Repository: /home/claude/wt-help (HEAD b045cc6; docs/help-center/ is untracked).
Every `sources:` path in all ten articles was confirmed to exist (none missing).
Verdicts: supported / unsupported / contradicted. Pure navigation and general advice are skipped.

---

### 21-privacy-data-retention-deletion.md
| # | Sentence (verbatim, may be shortened with …) | Verdict | Evidence (path:line) / what the code says |
|---|---|---|---|
| 1 | "your email address, your name if you add one, and a one-way hash of your password (never the password itself)" | supported | app/db/models.py:401,404,408 (email, PBKDF2 password_hash, full_name) |
| 2 | "your plan and billing status" | supported | app/db/models.py:405 (plan); app/db/models.py:3976-3997 (BillingSubscription.status) |
| 3 | "what you enter during identity onboarding: the country you are in, … individual or a company, the company name and country, and your verified phone number" | supported | app/db/models.py:457-463,482-485; app/services/identity.py:136-140 |
| 4 | "the IP address you signed up from and the country that address appears to be in, which is used as a risk signal" | supported | app/api/auth.py:274 (signup_ip); app/db/models.py:467-471; app/services/identity.py:8-14. Nuance: the country is looked up from the IP of the identity-submission request (identity.py:145), not strictly the signup request. |
| 5 | "your theme and writing-voice settings" | supported | app/db/models.py:409 (theme_json), :443-444 (style_profile_json / style_samples_json) |
| 6 | "connections to Gmail, LinkedIn and other services. Their access tokens are stored encrypted." | supported | app/db/models.py:1651-1664 (Gmail Fernet ciphertext), :1906-1933 (IntegrationToken encrypted_value), :3350 (CRM tokens in TokenStore). Nuance: LinkedIn stores only a Unipile account id, no token (models.py:3109). |
| 7 | "Vectorae also keeps security and activity records … sign-ins, refused attempts, data exports and deleted strategies." | supported | app/services/security_audit.py:26-36 (strategy.deleted, account.data_exported, …_denied); auth_sessions table (account_export.py:51); app/services/network_guard.py:18 (refusals) |
| 8 | "For each prospect … name, job title, company, email address, phone number, LinkedIn profile, and research notes such as recent posts or company news." | supported | app/api/leads.py:325-336 lists these Lead columns (full_name, title, company, email, phone, linkedin_url, linkedin_posts_json, company_news_json, enrichment_json) |
| 9 | "It also stores the outreach itself: the subject and body of every message, when it was sent, and the replies … including the reply text." | supported | app/services/account_export.py:114,121 (messages, inbound_replies tables owned per lead) |
| 10 | "Bookings, meetings, meeting notes and transcripts are stored too." | supported | app/db/models.py:2555 (transcript); account_export.py:53,55,80,128 (billable_meetings, calendar_booking_pages, meetings, calendar_bookings) |
| 11 | "Vectorae keeps a consent ledger (opt-ins, opt-outs and erasures) and a do-not-contact (suppression) list of email addresses, phone numbers and LinkedIn profiles." | supported | app/db/models.py:4413-4425 (ConsentEvent), :1672-1687 (suppression_list email/phone), :3134-3144 (LinkedInSuppression) |
| 12 | "Apart from support chat history, Vectorae does not delete your data automatically after a set time." | supported | app/workers/celery_app.py:223-392 beat list: the only retention purge is support-chat-retention-purge (:252-254); app/config.py:269-270 |
| 13 | "A conversation is deleted 30 days after its last message, by a job that runs every night at 03:20 UTC." | supported | app/workers/support_tasks.py:8-13,55-63 (keyed on last_message_at, falls back to created_at); app/workers/celery_app.py:250-254,188-189 |
| 14 | "The number of days is a deployment setting; 30 is the default." | supported | app/config.py:270 (support_chat_retention_days: int = 30) |
| 15 | "Support tickets are not deleted by this job, even if the conversation they came from is." | supported | app/workers/support_tasks.py:15-19 (chat_session_id ON DELETE SET NULL) |
| 16 | "The suppression list is kept without a time limit. You cannot remove an entry yourself; only a platform administrator can remove one, so a person who asked not to be contacted stays protected." (re-checked) | supported | no retention purge (app/workers/celery_app.py:223-392); customer routes are read/add only and admin-gated (app/api/ui_support.py:13-14,275-300); admin removal `DELETE /admin/suppression-list/{email}` (app/api/admin.py:209-218; app/services/admin_service.py:231-236) |
| 17 | "Open Profile. In the Download your data card, type your password in Confirm with your password. Press Download my data." | supported | frontend/src/app/(app)/profile/page.tsx:149,157,168 |
| 18 | "You get one JSON file, named like `leadpilot-account-export-2026-10-10.json`." | supported | frontend/src/lib/profile.ts:41-43 (client names the file by date). Note: the server's own Content-Disposition name is `leadpilot-account-export-<YYYYMMDDTHHMMSSZ>.json` (app/api/account_data.py:84,89); the browser download uses the client name. |
| 19 | "It contains everything your account owns: profile, products, strategies, leads, messages, meetings, settings and the records listed above." | supported | app/services/account_export.py:3-14,41-133 |
| 20 | "Passwords and connection secrets (such as encrypted tokens and API key hashes) are left out on purpose." | supported | app/services/account_export.py:16-21,154-164 (redacted as "[redacted]") |
| 21 | "Shared, deployment-wide lists with no owner, such as the suppression list, are not included." | supported | app/services/account_export.py:139-152 |
| 22 | "You must sign in to export. A personal API key cannot download the whole account." | supported | app/api/account_data.py:43-44,61-62 |
| 23 | "Every export, and every attempt refused for a wrong password, is recorded in the account's security log." (re-checked) | supported | app/api/account_data.py:66-80 |
| 24 | "If you type the wrong password you see "That password is not right." Too many attempts … show "Too many attempts. Wait a while and try again."" | supported | frontend/src/lib/profile.ts:46-49 |
| 25 | "In a workspace, the export always covers the account of the person who is signed in, not the workspace owner's account." | supported | app/api/account_data.py:12-14; app/services/rbac.py:28-31 (/me is personal) |
| 26 | "Open the lead from Pipeline, press Delete (GDPR erasure), then press Delete in the "Permanently delete lead?" confirmation." (re-checked) | supported | frontend/src/app/(app)/pipeline/page.tsx:127-139 |
| 27 | "In a workspace, SDRs and viewers cannot do this; it needs the owner or a manager." | supported | app/services/rbac.py:48-57 (viewer read-only; SDR DELETE refused) |
| 28 | "records the erasure in the consent ledger first … That record keeps the email address or phone number it was about" | supported | app/api/leads.py:306-311; app/services/consent.py:318-326 (identifier=lead.email or lead.phone) |
| 29 | "adds the person's email, phone number and LinkedIn profile to the suppression list, so no strategy will contact or source them again" | supported | app/api/leads.py:283-285,290-324 |
| 30 | "clears the lead's name, job title, email, phone, company, LinkedIn details, research notes and the written explanation of its AI score, and marks the lead as dropped." (re-checked) | supported | app/api/leads.py:326-339 (ai_score_reason, ai_score_factors cleared; status DROPPED) |
| 30a | "The numeric scores (booking likelihood and F-P-T-A scores) stay on the record." (new) | supported | app/api/leads.py:325-339 does not touch ai_booking_likelihood (app/db/models.py:1104) or fpta_* (models.py:1203-1211) |
| 31 | "An empty record without personal details is kept so the same person is not re-added to that strategy" | supported | app/api/leads.py:286-288,330 |
| 32 | "forgets which record in your connected CRM (HubSpot or Salesforce) the lead was linked to" | supported | app/api/leads.py:341-345 (crm_sync.forget_local) |
| 33 | "Messages already sent to the person and replies received from them are not deleted by this action." | supported | app/api/leads.py:275-345 touches no Message/InboundReply rows |
| 34 | "The confirmation says all personal data for the contact is erased; the message history is not." (re-checked) | supported | frontend/src/app/(app)/pipeline/page.tsx:137-138 ("This erases all personal data for this contact…"); app/api/leads.py:275-345 deletes no messages/replies |
| 35 | "Anything already copied into your CRM stays there. Erasing it in the CRM is up to you." | supported | app/api/leads.py:342-343 |
| 36 | "Strategy: open the strategy and press Delete. In the Delete strategy window, confirm with your password." | supported | frontend/src/app/(app)/strategies/detail/page.tsx:125-129; frontend/src/components/strategy/DeleteStrategyDialog.tsx:60,67 ("Enter your password to confirm", button "Delete permanently" :88) |
| 37 | "This permanently deletes the strategy with its research, leads, sequences, messages and campaign history." | supported | app/api/strategies.py:448-453 |
| 38 | "A campaign that is still sending must be paused first." | supported | app/api/strategies.py:469-474 |
| 39 | "The deletion is recorded in the security log, and the tamper-evident activity trail keeps its entries." | supported | app/api/strategies.py:452-458,486-494 |
| 40 | "LinkedIn network: on the Network page, Delete my uploaded connections removes every connection you uploaded, after you confirm "Delete all uploaded connections?"." | supported | frontend/src/app/(app)/network/page.tsx:236-240; app/api/linkedin_network.py:134-144 |
| 41 | "The deletion itself is never limited by plan, but the button only shows on Growth and higher plans. After a downgrade, contact support to delete your uploaded connections." (re-checked) | supported | app/api/linkedin_network.py:134-138 (DELETE not plan-gated); frontend/src/app/(app)/network/page.tsx:198-210,236-240; app/services/linkedin_network.py:343-345; app/core/plans.py:180-186 |
| 42 | "There is no account deletion in the app, and no feature that deletes or anonymises an account automatically." | supported | docs/program/BASELINE.md:38,95; no user-deletion route in app/ |
| 43 | "To ask for your account to be deleted, use the privacy contact on the Privacy page. Such a request is handled manually by the team." | supported | frontend/src/app/privacy/page.tsx:19,144-152; docs/program/BASELINE.md:352 ("can only be met by hand in the database") |
| 44 | "The public Privacy page … is the policy. It lists the email address for privacy requests." | supported | frontend/src/app/privacy/page.tsx:19,144-152 |

Note (not an article error): the Privacy page says "Prospect data collected for a client campaign is deleted when that client's engagement ends or on request" (frontend/src/app/privacy/page.tsx:137-141); no code does that. The article's "ask support if they disagree" covers it, but the policy page itself makes an unsupported promise. Reported, not fixed.

Summary: 45 supported, 0 unsupported, 0 contradicted. (final, after re-check)

---

### 22-plans-limits-billing.md
| # | Sentence (verbatim, may be shortened with …) | Verdict | Evidence (path:line) / what the code says |
|---|---|---|---|
| 1 | Table row free: 3 / 100 / 5 / gmail / 10.0 | supported | app/core/plans.py:53-58 |
| 2 | Table row starter: 10 / 500 / 10 / gmail, whatsapp / 25.0 | supported | app/core/plans.py:70-75 |
| 3 | Table row growth: 25 / 2500 / 15 / gmail, whatsapp, linkedin / 60.0 | supported | app/core/plans.py:89-94 |
| 4 | Table row scale: Unlimited / 10000 / Unlimited / all four / 150.0 (re-checked) | supported | app/core/plans.py:105-110; "Unlimited" steps now qualified by the new 20-step sentence (#7a) |
| 5 | Table row pay_per_meeting: 10 / 1000 / 10 / gmail, whatsapp, linkedin / 60.0 | supported | app/core/plans.py:124-129 |
| 6 | Table row pro: Unlimited / Unlimited / Unlimited / all four / 150.0 (re-checked) | supported | app/core/plans.py:140-149; qualified by #7a |
| 7 | Table row enterprise: Unlimited / Unlimited / Unlimited / all four / 400.0 (re-checked) | supported | app/core/plans.py:162-167; qualified by #7a |
| 7a | "Any single sequence is limited to 20 steps by the sequence form and API, so "Unlimited" sequence steps means up to 20 steps per sequence." (new) | **contradicted** (partly) | The API cap is real: `steps: list[StepIn] = Field(min_length=1, max_length=20)` and `step_no … le=20` (app/api/sequences.py:84,120). "the sequence form": the web app's only create-sequence form (frontend/src/components/strategy/OutreachPanel.tsx:68-70) builds one or two steps, an opening message and an optional follow-up (frontend/src/lib/leadOutreach.ts:43-54); it has no 20-step limit and cannot build more than 2. Correct to: "The Vectorae API accepts at most 20 steps per sequence, so "Unlimited" sequence steps means up to 20. The sequence form in the web app creates an opening message and an optional follow-up (up to 2 steps)." |
| 8 | "In the app these plans are shown as Free, Starter, Growth, Scale, Pay per meeting, Pro and Enterprise." | supported | app/core/plans.py:67,83,102,118,137,157,175 (display_name) |
| 9 | ""gmail" means email sent through your connected Gmail account." | supported | frontend/src/lib/pricing.ts:69-71 (gmail → "Email") |
| 10 | "The Pricing page calls strategies "campaigns"." | supported | frontend/src/lib/pricing.ts:80-81 |
| 11 | "Pro is no longer sold. Accounts already on Pro keep exactly what they have." | supported | app/core/plans.py:86-88; app/core/billing_catalog.py:36-65 (no pro tier) |
| 12 | "The AI phone channel ("phone") is also switched off for the whole deployment by default. An administrator has to turn it on before any plan can use it." | supported | app/services/system_settings.py:90 (phone_calling_enabled default False); app/api/calls.py:160-161 |
| 13 | "Prices are in US dollars." | supported | app/core/billing_catalog.py:28 |
| 14 | "Monthly subscription (marked Recommended on the Pricing page)" | supported | frontend/src/app/pricing/page.tsx:123-129; billing_catalog.py:116-120 |
| 15 | "Starter: $149 … Growth: $349 … Scale: $699 … Enterprise: $1,499 per month" | supported | app/core/billing_catalog.py:40,47,54,61 |
| 16 | "Each monthly tier starts with a 14-day free trial." | supported | app/core/billing_catalog.py:29; app/services/billing.py:142-144,165 |
| 17 | "An account gets the trial only once: if you have had a trial before, a later monthly checkout starts without one." | supported | app/services/billing.py:132,142,165 (had_trial → trial_days=0) |
| 18 | "Pay per meeting: no monthly fee ($0) and $179 for each prospect who books a meeting through Vectorae." | supported | app/core/billing_catalog.py:67-77 |
| 19 | "The Free plan has no price. Free accounts are limited by the table above." | supported | app/core/billing_catalog.py:36-65 (no free tier); plans.py:53-69 |
| 20 | "When a prospect books a meeting, Vectorae records a charge for it, but does not take payment straight away. It waits 48 hours first." | supported | app/services/billing.py:11-18,350-363; billing_catalog.py:72-75 (grace_hours 48) |
| 21 | "If the meeting is no longer booked when the 48 hours are over (for example, it was cancelled), the charge is waived." | supported | app/services/billing.py:59-65,394-399 |
| 22 | "You are charged once per prospect. If the same prospect books again, there is no second charge." | supported | app/services/usage_meter.py:386-388,421-423 |
| 23 | "A background job charges meetings whose 48 hours have passed. It runs every 30 minutes." | supported | app/workers/billing_tasks.py:3; app/workers/celery_app.py:377-378 (1800.0 s) |
| 24 | "If the account has no saved payment method, or the card is declined, the charge is marked as failed." | supported | app/services/billing.py:407-412,418-421,325-327 |
| 25 | "A meeting charge can be disputed only while it is still inside its 48-hour window." | supported | app/services/billing.py:443-449 |
| 26 | "The web app has no dispute button yet; disputes go through the Vectorae API." | supported | frontend/src/lib/api/billing.ts:59-60 defines the call but nothing in frontend/src imports it (grep); app/api/billing.py:114 |
| 27 | "After the 48 hours, contact support instead." | supported | app/services/billing.py:446-447 ("For a charged meeting, contact support.") |
| 28 | "An administrator then decides whether to waive or charge a disputed meeting." | supported | app/api/billing.py:124-134; app/services/billing.py:455-469 |
| 29 | "Go to the Pricing page. You can also reach it from Profile, in the Plan card, with the Upgrade plan button." | supported | frontend/src/app/(app)/profile/page.tsx:109 |
| 30 | "On Pricing you pick a monthly tier and press the trial button, or press Pay per meeting." | supported | frontend/src/app/pricing/page.tsx:177 ("Start {n}-day trial of {tier}"), :208-215 |
| 31 | "You must be signed in. If you are not, the button takes you to sign-up." | supported | frontend/src/app/pricing/page.tsx:80-84 |
| 32 | "Your phone number must be verified first. If it is not, you see "Verify your phone to choose a plan." and you are sent to the verification screen." | supported | app/api/billing.py:77; frontend/src/app/pricing/page.tsx:70-74 |
| 33 | "You finish on a checkout page run by Stripe … For pay per meeting, this step saves your card for later charges. When checkout finishes you return to Settings." | supported | app/services/billing.py:155-170 (setup checkout for PPM; success_url /settings?billing=success) |
| 34 | "Choosing a different plan replaces your current one. The subscription being replaced is cancelled so you are not billed twice." | supported | app/services/billing.py:254-261 |
| 35 | "Leaving checkout without finishing does not change or downgrade your current plan." | supported | app/services/billing.py:176-180 |
| 36 | "If you sign in and your account has no paid plan, Vectorae takes you to the Pricing page once, right after sign-in. You can still go back to the app; the Free limits then apply." | supported | frontend/src/lib/post-login.ts:1-8,40 (after every explicit sign-in, not on session restore); pricing/page.tsx:99-101 ("Back to app") |
| 37 | "…you work under the workspace owner's plan and are not asked to buy your own, as long as the workspace owner has a paid plan." (re-checked) | supported | app/services/billing.py:529-561 (owner plan not free, or owner subscription trialing/active/past_due) |
| 38 | "Only the account owner can buy or cancel a plan for their account." | supported | app/api/billing.py:14-16; app/services/rbac.py:28-32 (/billing is personal) |
| 39 | "The action is refused and you see a message that names the limit, for example "Free plan allows 3 strategies. You have 3."" | supported | app/core/plans.py:225-235 |
| 40 | "Strategies: when you create a new strategy. All strategies across all your products count. Deleting a strategy frees a place." | supported | app/api/strategies.py:154-165 |
| 41 | "Leads per strategy: when you source leads. If the strategy is full, sourcing is refused. If there is some room, Vectorae only asks for as many leads as fit, and checks again lead by lead." | supported | app/api/leads.py:92-104,113-116; app/workers/lead_tasks.py:211 |
| 42 | "Sequence steps and channels: when you create a sequence and again every time you launch it. A sequence built … higher plan cannot be launched after a downgrade…" | supported | app/api/sequences.py:57-62 |
| 43 | "Channels for AI calls: when you start a call." | supported | app/api/calls.py:162-165 |
| 44 | "the learning playbook and A/B test results are not included in Free" | supported | app/core/plans.py:59-60; app/api/playbook.py:46,80,121; app/api/strategies_advanced.py:42 |
| 45 | "the private LinkedIn network needs Growth, Scale, Pro or Enterprise (not Pay per meeting)" | supported | app/core/plans.py:180-186 |
| 46 | "Every plan has a daily dollar limit on AI use for the whole account … since 00:00 UTC, and it resets at 00:00 UTC every day." | supported | app/services/usage_meter.py:187-213; app/core/plans.py:45-51 |
| 47 | "The limit is checked before each AI step in research pipelines, strategy verification and lead scoring. A step is only started if its worst-case cost still fits…" | supported | app/services/usage_meter.py:52,262-306 |
| 48 | "When the limit is reached, a running strategy stops with the status budget exhausted. Nothing already paid for is lost, and you can resume it after the reset. Lead scoring simply skips the score." | supported | app/services/usage_meter.py:45-52,74-79; app/api/strategies.py:322-325 |
| 49 | "Creating a new strategy or resuming one while the limit is used up is refused with: "Your … plan's daily AI limit ($…) is used up. It resets at 00:00 UTC."" | supported | app/api/strategies.py:102-126,167,322. Note: the plan name is the raw key in lower case ("Your free plan's…"). |
| 50 | "Sending messages, meeting briefs and call analysis are not stopped halfway by this limit, but their cost still counts toward the day." | supported | app/services/usage_meter.py:45-52 |
| 51 | "The cost is an estimate calculated from model prices set by your administrator." | supported | app/services/usage_meter.py:23-25,242-250 |
| 52 | "Cancellation exists in the product, but the web app does not currently have a billing screen with a cancel button." | ~~supported~~ **superseded 2026-10-11**: the Profile page's Plan card has a cancel button (`frontend/src/components/billing/PlanCard.tsx`, `billingApi.cancel`); article 22 says "Profile → Plan" | app/api/billing.py:92-98; frontend/src/lib/api/billing.ts:57 had no importer in frontend/src when checked |
| 53 | "Monthly: the plan is cancelled at the end of the current billing period, and you keep access until then." | supported | app/services/billing.py:192-205 |
| 54 | "Pay per meeting: stops immediately. Meetings already booked are still billed." | supported | app/services/billing.py:193-194,206-210; charge sweep still runs on pending rows (:374-379) |
| 55 | "When a subscription ends, the account returns to the Free plan and its limits." | supported | app/services/billing.py:98-104,288-296 |
| 56 | "If a monthly payment fails, the subscription is marked past due. You keep your plan while Stripe retries the card. If Stripe finally cancels the subscription, the account returns to Free." | supported | app/services/billing.py:51-53,337-340,288-296 |
| 57 | "the product does not enforce the analytics history length" | supported | analytics_history_days is read only in app/core/plans.py and app/core/billing_catalog.py:110 (grep over app/) |
| 58 | "multi-variate results are available on any plan that includes A/B testing" | supported | app/api/strategies_advanced.py:36-44 (gated on ab_testing, not multi_variate) |
| 59 | "on a production deployment where Stripe is not set up, choosing a plan fails with "payments are not configured; plans cannot be changed right now"." (re-checked) | supported | app/api/billing.py:82-84; app/config.py:499-500 |

Summary: 59 supported, 0 unsupported, 1 contradicted. (final, after re-check)

---

### 23-account-security.md
| # | Sentence (verbatim, may be shortened with …) | Verdict | Evidence (path:line) / what the code says |
|---|---|---|---|
| 1 | "You sign in with your email address and password. Passwords must be at least 8 characters." | supported | app/api/auth.py:78 (min_length=8), :488 |
| 2 | "Vectorae stores only a one-way hash of your password (PBKDF2-SHA256), never the password itself." | supported | app/services/auth.py:4,56-58 |
| 3 | "If the email or the password is wrong, the message is always "invalid email or password". Vectorae does not say which one was wrong…" | supported | app/api/auth.py:399-402 |
| 4 | "New accounts must confirm their email address before they can use the app." | supported | app/config.py:281 (require_email_verification=True); app/services/auth.py:209-210 |
| 5 | "Accounts created through public sign-up also go through identity onboarding, which includes verifying a mobile phone number." | supported | app/api/auth.py:273 (identity_required=True on signup); frontend/src/lib/identity.ts:95-100 |
| 6 | "You can put the phone step off for the current browser session, but a verified phone number is required before you can choose a paid plan." | supported | frontend/src/lib/identity.ts:78-91 (sessionStorage defer); app/api/billing.py:77; app/services/identity.py:164-173 |
| 7 | "Sign-in attempts are limited to 10 per 15 minutes." | supported | app/core/config.py:320 (RATE_LIMIT_AUTH=10); app/core/rate_limiting.py:211 (900 s) |
| 8 | "The limit is counted in two ways at once: per network address and per email address." | supported | app/api/auth.py:385-392 |
| 9 | "Both successful and failed attempts count." | supported | app/api/auth.py:373-378 |
| 10 | "The number is a deployment setting; 10 is the default." | supported | app/core/config.py:12,320 |
| 11 | "The sign-in page has a Keep me signed in box, which is ticked by default." | supported | frontend/src/app/(auth)/login/page.tsx:19,119-123; app/api/auth.py:84 |
| 12 | "Ticked: you stay signed in for 30 days from your last use. Each time the app refreshes your session, the 30 days start again… An account left unused for 30 days must sign in again." | supported | app/config.py:167-169 (sliding 2592000 s) |
| 13 | "Not ticked: the session ends when you close the browser, or after 12 hours, whichever comes first." | supported | app/config.py:170-172 (43200 s) |
| 14 | "the app uses a short access pass that lasts 15 minutes and renews it automatically" | supported | app/config.py:166 (jwt_access_ttl_seconds=900); app/api/auth.py:380-383 |
| 15 | "Each renewal can be used only once. If an old, already-used session pass shows up again…, Vectorae signs out that whole session and records the event in the security log." | supported | app/services/auth_sessions.py:9-16,188. Nuance: a reuse inside a 30-second grace window (two tabs) is tolerated (app/config.py:187-190). |
| 16 | "These durations are deployment settings; the numbers above are the defaults." | supported | app/config.py:166-172 |
| 17 | "Sign out: use Log out in the app's side menu. This ends the session on the server, not just in your browser." | supported | frontend/src/components/shell/Shell.tsx:139-143; frontend/src/lib/api/auth.ts:70-77; app/api/auth.py:444-455 |
| 18 | "Change password: open Profile, go to Change password, enter your Current password, your New password and Repeat new password, then press Change password." | supported | frontend/src/app/(app)/profile/page.tsx:115-143 |
| 19 | "The new password must be different from the current one." | supported | app/api/auth.py:505-507 |
| 20 | "Changing it signs you out on every device, including the one you are using, and you are taken to the sign-in page." | supported | app/api/auth.py:509 (revoke_all_for_user); frontend/src/app/(app)/profile/page.tsx:49. Nuance: an already-issued 15-minute access pass is a stateless JWT (app/services/auth.py:198-201) and keeps working on another device until it expires. |
| 21 | "Password changes are limited to 10 attempts per 15 minutes…" | supported | app/api/auth.py:501-502 |
| 22 | "There is no screen that lists your active sessions. To sign out everywhere, change your password." | supported | no session-list route in app/api/auth.py; :509 |
| 23 | "Vectorae has no "forgot password" flow and no two-factor authentication." | supported | grep for forgot/reset-password/2fa/totp/mfa over app/api and frontend/src/app: no match |
| 24 | "On production deployments, Vectorae blocks sign-up and sign-in from VPNs, proxies, Tor and hosting or data-centre networks." | supported | app/config.py:413-416,503-507; app/services/network_guard.py:1-12; app/api/auth.py:352 |
| 25 | VPN block message "It looks like you're connecting through a VPN, proxy or hosting network. Please disable…" | supported | app/services/network_guard.py:36-38 |
| 26 | ""We couldn't verify your network just now. Please try again in a minute." … the network check itself was unavailable" | supported | app/services/network_guard.py:41,64-69 (only when fail-closed is set) |
| 27 | "Administrators can turn this blocking off, or allow specific network addresses…" | supported | app/config.py:416 (VPN_BLOCK_ENABLED), :432 (VPN_ALLOWLIST_IPS) |
| 28 | "By default, if the outside service that checks addresses is down, sign-in is allowed rather than blocked." | supported | app/config.py:423-426 (vpn_detection_fail_closed=False) |
| 29 | Sign-up closed message "Sign-up is closed on this Vectorae deployment. Ask your administrator for an account." | supported | app/api/auth.py:207-208,222-223 |
| 30 | Domain-limited message "Sign-up on this Vectorae deployment is limited to approved email domains. Ask your administrator for an account." | supported | app/api/auth.py:209-211,224-228 |
| 31 | "By default sign-up is open to any email domain. Existing accounts can always sign in." | supported | app/config.py:435-448 |
| 32 | "Open Settings and the Integrations tab. In the API keys card, type a Name and press Create key." | supported | frontend/src/app/(app)/settings/page.tsx:409-410,531; frontend/src/components/settings/WebhooksCard.tsx:238,249,252 |
| 33 | "Copy the key straight away. It is shown once and never again ("Copy it now — it will not be shown again.")." | supported | frontend/src/components/settings/WebhooksCard.tsx:38; app/services/api_keys.py:3-4 |
| 34 | "A key starts with `lpk_`. Vectorae stores only a fingerprint (hash) of it…" | supported | app/services/api_keys.py:3,21,39-41 |
| 35 | "A key acts as you on the normal API, but it never works on administrator pages, even if your account is an administrator." | supported | app/api/deps.py:20-23 |
| 36 | "A key cannot download your whole account's data; that needs a signed-in person and a password." | supported | app/api/account_data.py:61-62,66 |
| 37 | "You can have at most 10 active keys. Revoke one before creating another." | supported | app/services/api_keys.py:22,35-38 |
| 38 | "Use Revoke to disable a key immediately." | supported | frontend/src/components/settings/WebhooksCard.tsx:266; app/services/api_keys.py:52-53 |
| 39 | "An administrator can suspend an account. While it is suspended, every request from it is refused with "account suspended", and all of its active campaigns are paused." | supported | app/services/admin_service.py:127-140; app/services/auth.py:207-208 |
| 40 | "You may still get past the sign-in page, but nothing in the app will load." | supported | app/api/auth.py:395-405 (login does not check is_suspended); auth.py:207-208 |
| 41 | "When the administrator lifts the suspension, the campaigns that were paused because of it become active again." | supported | app/services/admin_service.py:143-155 (only `paused_admin`, which only suspension sets) |

Summary: 41 supported, 0 unsupported, 0 contradicted. (final, after re-check)

---

### 24-workspaces-and-agency-mode.md
| # | Sentence (verbatim, may be shortened with …) | Verdict | Evidence (path:line) / what the code says |
|---|---|---|---|
| 1 | "A workspace is its owner's account. Your products, strategies, leads, integrations and deals stay yours; the people you invite work on your records." | supported | app/services/workspaces.py:3-4; app/services/auth.py:213-241 |
| 2 | "Every user owns exactly one workspace, created automatically the first time they use the app…" (re-checked) | supported | app/db/models.py:3468-3469; app/services/workspaces.py:66-84,113-114; frontend/src/components/shell/WorkspaceSwitcher.tsx:13-14; Shell.tsx:158 |
| 3 | "…and can also be a member of other people's workspaces." | supported | app/services/workspaces.py:112-123 |
| 4 | "pick it with the Workspace switcher in the top bar. From then on you see and act on that owner's data, within your role." | supported | frontend/src/components/shell/WorkspaceSwitcher.tsx:22-25; app/services/auth.py:213-241 |
| 5 | "Personal things always stay your own…: your sign-in and password, your profile and theme, your API keys, your support chats, tutorials, onboarding and your own billing." | supported | app/services/rbac.py:28-32 (/auth, /me, /devices, /support, /tutorials, /onboarding, /workspaces, /branding, /billing); app/api/api_keys.py:23 (/me/api-keys) |
| 6 | "A member works under the owner's plan and is not asked to buy a plan of their own, as long as the owner has a paid plan." (re-checked) | supported | app/api/sequences.py:62-63; app/services/billing.py:529-561 |
| 7 | "Owner – everything, including workspace settings, white label and managing managers." | supported | app/services/rbac.py:7; app/services/workspaces.py:157-165,301 |
| 8 | "Manager – everything an owner can do with the data: … launch campaigns, approve or decline SDR launches, manage integrations, webhooks and costs, delete things, and invite or manage SDRs and viewers." | supported | app/services/rbac.py:8-9,48-60; app/api/sequences.py:365-367 |
| 9 | "Managers cannot invite or manage other managers, and cannot change workspace settings or white label." | supported | app/services/workspaces.py:157-165,197-199,301; app/api/workspaces.py:76-81 |
| 10 | "SDR – can read everything and work leads, sequences, deals and meetings. An SDR cannot change integrations, webhooks or costs, and cannot delete anything ("Deleting needs a manager in this workspace.")." | supported | app/services/rbac.py:10-12,35-36,53-60 |
| 11 | "Viewer – read-only ("Viewers have read-only access to this workspace.")." | supported | app/services/rbac.py:50-52 |
| 12 | "These rules are checked by the server on every request…" | supported | app/services/rbac.py:3-5; app/services/auth.py:236 |
| 13 | "Open Team, go to the Members tab, and use the Invite card: enter the Email, choose a Role, and press Send invite." | supported | frontend/src/app/(app)/team/page.tsx:55,160,165,170,176 |
| 14 | "Owners can invite any role. Managers can invite SDRs and viewers only." | supported | app/services/workspaces.py:192-199 (invitable roles: manager, sdr, viewer) |
| 15 | "The invitation is emailed, and the link is also shown to you as Invitation link (also emailed)…" | supported | app/services/workspaces.py:216-235; app/api/workspaces.py:124-131; team/page.tsx:178 |
| 16 | "The link expires after 7 days and works once. It only works for a signed-in person using the invited email address." | supported | app/services/workspaces.py:28,264-278 |
| 17 | "Inviting the same address again replaces the earlier link. You can also Revoke a pending invitation." | supported | app/services/workspaces.py:203-208,250-257; team/page.tsx:189 |
| 18 | "By default, when an SDR launches a sequence for the first time, nothing is sent. The launch is held as "pending approval" and the owner and managers are notified. They see it in Team › Approvals." | supported | app/db/models.py:3471-3474 (default True); app/api/sequences.py:330-365; team/page.tsx:56 |
| 19 | "Approve carries out the SDR's launch exactly as they asked." | supported | app/api/sequences.py:404-408 (stored approval_payload_json) |
| 20 | "Decline lets you write "What should change? (sent to the SDR)" and press Send decline. The sequence goes back to draft and the SDR sees your note." | supported | team/page.tsx:286,290; app/api/sequences.py:433-437,376 |
| 21 | "Either way, the SDR is told the decision." | supported | app/api/sequences.py:370-384 |
| 22 | "Once a sequence has been approved, later launches of that same sequence do not need approval again." | supported | app/api/sequences.py:333 |
| 23 | "Approval is refused while that sequence's pre-launch review is blocked. The review findings are shown right in the request." | supported | app/api/sequences.py:402; team/page.tsx:280-282 |
| 24 | "The owner can switch this off in Team › Settings by unticking SDR campaign launches need a manager's approval. Owners and managers never need approval." | supported | team/page.tsx:57,330; app/api/sequences.py:333 |
| 25 | "The owner can brand the app under Team › White label: a brand name, a logo (PNG, JPEG or WebP, up to 1 MB; SVG is refused), a primary colour, a support email and a custom domain." | supported | team/page.tsx:58,390-416; app/api/workspaces.py:44,184-196 |
| 26 | "A custom domain must be verified with a DNS record shown on that page, and the deployment's operator also has to add the domain to the hosting." | supported | app/services/workspaces.py:313-319,350-371; docs/features/workspaces.md:63-64 |
| 27 | "The deployment's administrator can turn white label off for everyone." | supported | app/services/system_settings.py:139; app/services/workspaces.py:301-302 |
| 28 | "Branding changes what people see in the app and the brand name used in invitation emails. Outreach still goes out from the owner's connected Gmail account." | supported | app/services/workspaces.py:220-223,374-389; docs/features/workspaces.md:99-100 |
| 29 | "a lead can be assigned to a member (the Owner column in the CRM grid), but that only records who works the lead. Messages are still sent from the owner's Gmail and LinkedIn accounts, written in the owner's voice profile." | supported | frontend/src/lib/crm/grid-state.ts:58; docs/features/workspaces.md:67-68,95-98 |
| 30 | "The person a lead is assigned to is not notified, and the grid cannot filter by assignee yet." | supported | frontend/src/lib/crm/grid-state.ts:58 (filterable: false); docs/features/workspaces.md:96-97 |
| 31 | "Open Clients and press Add a client, with a Client name and a Monthly retainer." | supported | frontend/src/app/(app)/clients/page.tsx:82,90,95 |
| 32 | "Separate reporting – sent messages, reply rate, meetings and revenue are counted only over that client's campaigns." | supported | app/services/client_workspaces.py:243-306 |
| 33 | "Reserve a sending domain … Vectorae checks this at the moment of sending. A message that would go out from a domain not on the client's list is not sent; it is marked failed with a reason." | supported | clients/page.tsx:195; app/workers/outreach_tasks.py:319-331 |
| 34 | "A billing view – Show this month's invoice shows the retainer, the per-meeting fee, the number of meetings this month and the lines that add up to the total." | supported | clients/page.tsx:207; app/services/client_workspaces.py:310-360 |
| 35 | "If a client has no sending domain reserved, there is no restriction … and the page warns you about this." | supported | app/services/client_workspaces.py:210-226; frontend/src/lib/clients.ts:109-116 |
| 36 | "A campaign that is not filed under any client is treated as the agency's own work. The page warns that such work "is not on any invoice"." | supported | app/services/client_workspaces.py:24-27; frontend/src/lib/clients.ts:118-125 |
| 37 | "Deleting a client does not delete the outreach done for it." | supported | app/db/models.py:922-925 (ON DELETE SET NULL). Note: there is no delete-client route or button at all (app/api/client_workspaces.py:3-11 lists PATCH archive only), so the sentence describes a situation customers cannot create; consider "Archiving a client…". |
| 38 | "Creating clients, changing their prices and changing their domain lists needs a manager or the owner. Any member can read them." | supported | app/api/client_workspaces.py:88-96,118-122,140-147,177-201 |
| 39 | "Filing a strategy under a client is currently done through the Vectorae API; the web app has no button for it yet." | supported | app/api/client_workspaces.py:206; frontend/src/lib/api/clients.ts:55 has no importer in frontend/src |
| 40 | "An account can connect only one Gmail mailbox…" | supported | app/db/models.py:1660-1662 (user_id unique); docs/features/agency-mode.md:108-115 |
| 41 | "WhatsApp uses one sender number for the whole deployment… Domain isolation applies to email only." | supported | app/config.py:137; docs/program/BASELINE.md:92,164 |
| 42 | "The learning loop's playbook scores are pooled across the whole deployment…" | supported | docs/program/BASELINE.md:163; app/services/account_export.py:142 (playbook_scores: global, no owner) |

Summary: 42 supported, 0 unsupported, 0 contradicted. (final, after re-check)

---

### 25-pause-stop-kill-switch.md
| # | Sentence (verbatim, may be shortened with …) | Verdict | Evidence (path:line) / what the code says |
|---|---|---|---|
| 1 | "Vectorae sends outreach automatically from a server, so closing the app does not stop it." | supported | app/workers/celery_app.py:227 (leadpilot.outreach.dispatch on beat); app/workers/outreach_tasks.py:101-120. Consistent with founder decision D1. |
| 2 | "A pause holds messages. Nothing is deleted, and sending continues from the same place when the pause is lifted." | supported | app/workers/outreach_tasks.py:119-120,171-179 (paused → message left SCHEDULED, not cancelled); app/api/analytics.py:155-165 |
| 3 | "A stop ends a contact's sequence for good. A stopped sequence can never send again to that contact." | supported | app/db/models.py:175; app/workers/outreach_tasks.py:173-177 |
| 4 | "To contact them again, they must be enrolled in a sequence again." | supported | app/services/conversion_probability.py:306-308 ("re-enroll to contact again"). Nuance: not the SAME sequence; enrollment is one per lead per sequence (app/services/sequence_engine.py:199-229). |
| 5 | "Every message is checked against these rules at the moment it is about to be sent… So a pause takes effect for messages already in the queue." | supported | app/workers/outreach_tasks.py:170-195 |
| 6 | "Open Campaigns and select the strategy. On the Overview tab, press Pause campaign." | supported | frontend/src/app/(app)/campaigns/page.tsx:424,486,540-542 |
| 7 | "You see "Campaign paused"." | supported | campaigns/page.tsx:443 (toast), :498 (banner) |
| 8 | "While a campaign is paused it sends nothing, including automatic follow-ups." | supported | app/workers/outreach_tasks.py:1461-1466,1512-1513 |
| 9 | "To restart, press Resume in the "Campaign paused" banner on the same page." | supported | campaigns/page.tsx:492-506; app/api/analytics.py:155-165 |
| 10 | "Vectorae also pauses campaigns by itself in some cases, and they stay paused until a person presses Resume" | supported | app/services/sequence_engine.py:548-555; app/services/deliverability.py:203-204; only resume_campaign sets active (analytics.py:162) |
| 11 | "High bounce rate: once a campaign has sent at least 10 messages, it pauses if more than 3% of them bounced." | supported | app/config.py:113-114; app/services/sequence_engine.py:536,549 (`rate > threshold`) |
| 12 | "Both numbers are deployment defaults, and a workspace compliance rule can set a lower bounce limit." | supported | app/config.py:113-114; app/services/compliance_rules.py:245-249; sequence_engine.py:544-548 |
| 13 | "The banner says "Bounce rate auto-pause"." | supported | campaigns/page.tsx:500-502 (the banner text reads "≥ 3%" while the code pauses on "> 3%": a UI copy nit, reported) |
| 14 | "Sending domain on a blocklist: the campaign pauses and the banner shows the reason." | supported | app/services/deliverability.py:57,203-205; campaigns/page.tsx:495,503 |
| 15 | "A strategy whose campaign is still sending cannot be deleted. Pause it first." | supported | app/api/strategies.py:469-474 |
| 16 | "There is no single "stop this contact" button for a normal user today." | supported | no per-lead stop route in app/api (stop_enrollment callers listed by grep are all automatic) |
| 17 | "They reply. A reply stops or pauses their sequence automatically, depending on what kind of reply it is (an out-of-office reply pauses and retries later)." | supported | app/workers/outreach_tasks.py:1085-1108 (OOO pause for ooo_reschedule_days; others stop) |
| 18 | "They unsubscribe. The unsubscribe link in every email works without signing in and takes effect immediately. It adds them to the suppression list and stops every sequence for them." | supported | app/api/unsubscribe.py:1-7 (no auth dependency); app/services/sequence_engine.py:495-509 |
| 19 | "They send STOP on WhatsApp. Words such as "stop", "unsubscribe" and "opt out" are treated as an opt-out, effective immediately, and stop their sequences." | supported | app/api/webhooks_whatsapp.py:60-70,402,455; app/services/whatsapp_optin.py:185,233 |
| 20 | "They book a meeting. A booking stops the sequence (for Calendly) or pauses it (for Vectorae's own calendar, so a cancelled meeting can resume it)." | supported | app/api/webhooks.py:165; app/workers/calendar_tasks.py:201; app/services/sequence_engine.py:622-642 |
| 21 | "You erase them. Delete (GDPR erasure) on the lead in Pipeline adds them to the suppression list, so they are not contacted again, and erases their personal details. This cannot be undone." (re-checked) | supported | frontend/src/app/(app)/pipeline/page.tsx:127-139; app/api/leads.py:290-339 |
| 22 | "Vectorae estimates each lead's chance of converting before every send." | supported | app/services/conversion_probability.py:289 (send_gate); system_settings.py:158 |
| 23 | "After at least 4 unanswered messages, a lead below 5% is marked "cooling" and its sequence is paused for 21 days; below 1.5% it is archived and its sequence is stopped. These are deployment defaults." | supported | app/services/system_settings.py:163-170; app/services/conversion_probability.py:248-283 (kill signals can archive at any time, :256) |
| 24 | "Reactivate lead on the lead's page resumes a cooling lead now, or clears an archived lead (its stopped sequence stays stopped)." | supported | frontend/src/components/leads/ConversionCard.tsx:54-62; frontend/src/app/(app)/leads/detail/page.tsx:42; app/services/conversion_probability.py:305-326 |
| 25 | "Your CRM closes the lead. If a connected HubSpot or Salesforce marks the lead as won, lost or disqualified, the sequence stops." | supported | app/services/crm_sync.py:70,566-581 |
| 26 | "An administrator adds them to the suppression list. In Settings, the Suppression tab is visible to administrators only." | supported | app/api/ui_support.py:275-300 (require_admin); frontend/src/lib/settings-tabs.ts:33-35; settings/page.tsx:499-506 |
| 27 | "Entries cannot be removed from the Settings screen; only a platform administrator can remove one." (re-checked) | supported | app/api/ui_support.py:13-14 (Settings routes: read + add); app/api/admin.py:209-218 |
| 28 | "Changing a lead's status by hand on the Pipeline board does not by itself stop its sequence." | supported | app/api/crm.py:251-290 (status change only; no enrollment change); send gates in outreach_tasks.py:170-195 do not read lead.status |
| 29 | "Gmail mailbox: … Below 70 it slows sending down; below 40 it pauses the mailbox and sends nothing from it. Messages are deferred, not cancelled." | supported | app/services/mailbox_health.py:30-37,77-78; app/workers/outreach_tasks.py:338-350 |
| 30 | "A paused mailbox is resumed only by a person: Settings › Deliverability, then Resume on that mailbox. A later better score never resumes it on its own." | supported | app/services/mailbox_health.py:39-41; frontend/src/components/settings/MailboxHealthCard.tsx:128; settings/page.tsx:533-537 |
| 31 | "LinkedIn account: in Settings › Integrations, each connected LinkedIn account has a Pause button (and Resume to undo it)." | supported | frontend/src/components/settings/LinkedInAccountsCard.tsx:122-129; settings/page.tsx:390; app/services/linkedin_outreach.py:82 |
| 32 | "There is no single "pause everything" switch for an account owner in this version." | supported | only per-strategy pause exists (app/api/analytics.py:131-150) |
| 33 | "An administrator can suspend an account. Suspension pauses all of that account's active campaigns and blocks the account from the app. When the suspension is lifted, those campaigns become active again." | supported | app/services/admin_service.py:127-155; app/services/auth.py:207-208 |
| 34 | "Not as a single setting in the app in this version." (no platform kill switch) | supported | no global send toggle among system settings (app/services/system_settings.py:29-224) or config |
| 35 | "All sending is done by Vectorae's background worker… If the deployment's operator stops that worker, nothing is sent until it runs again. Messages wait; they are not lost." | supported | app/workers/outreach_tasks.py:101-120 (dispatch picks up due SCHEDULED messages on each tick) |
| 36 | "Administrators can switch individual features off in system settings, for example the AI phone channel, which is off by default." | supported | app/services/system_settings.py:90 |

Summary: 36 supported, 0 unsupported, 0 contradicted. (final, after re-check)

---

### 26-mobile-app.md
| # | Sentence (verbatim, may be shortened with …) | Verdict | Evidence (path:line) / what the code says |
|---|---|---|---|
| 1 | "The Android app is built from the same code as the web app, using … Capacitor… Its app ID is `com.clienthunter.app` and its name on the phone is Vectorae." | supported | frontend/capacitor.config.ts:8-10 |
| 2 | "the screens are the same as on the web: Pipeline, Inbox, CRM, Campaigns, Calendar, Meetings, Strategies, Analytics, Network, Learn, Team, Clients, Profile and Settings." | supported | frontend/src/components/shell/nav.ts:27-63 (exact list and order) |
| 3 | "On a phone these appear as a bar of tabs along the bottom of the screen instead of a side menu." | supported | frontend/src/components/shell/Shell.tsx:18,188 |
| 4 | "There is no iPhone (iOS) app." | supported | docs/README_M7_COMPLETE.md:36 |
| 5 | "All the work happens on Vectorae's servers… The app … does not send messages itself and does not run campaign logic on the phone. A phone that is switched off, offline or has the app closed does not pause anything." | supported | docs/README_M7_COMPLETE.md:33-34 |
| 6 | "To actually pause sending, use Pause campaign on the Campaigns page…" | supported | frontend/src/app/(app)/campaigns/page.tsx:540-542 |
| 7 | "Back button – the Android back button goes back one screen. On a main section (such as Strategies, Campaigns, Analytics or Settings) it asks "Exit Vectorae?" before closing the app." | supported | frontend/src/hooks/useBackButton.ts:23-24,45-53 (roots: /, /strategies, /campaigns, /leads, /analytics, /settings) |
| 9 | Offline banner: "No connection" / "Campaigns are still running on the server — you'll be back in sync when connected."; "Server temporarily unreachable" / "Your campaigns are still running. We'll reconnect automatically." | supported | frontend/src/components/ui/OfflineBanner.tsx:32-37; mounted in frontend/src/app/layout.tsx:95 |
| 10 | "Links – tapping a notification opens the matching screen in the app." | supported | frontend/src/hooks/usePushNotifications.ts:16-19; frontend/src/components/providers/NativeProvider.tsx:62; docs/README_M7_COMPLETE.md:24 |
| 11 | "Status bar colour follows your chosen theme." | supported | frontend/src/hooks/useStatusBar.ts:6-8,43; NativeProvider.tsx:15 |
| 12 | "The bottom tab bar … on a narrow phone it scrolls sideways." | supported | frontend/src/components/shell/Shell.tsx:188 (overflow-x-auto); nav.ts:29-32 |
| 13 | "After you sign in, the app asks for permission to show notifications. If you allow it, your phone is registered with Vectorae for push notifications." | supported | frontend/src/hooks/usePushNotifications.ts:7-10,24; NativeProvider.tsx:106 |
| 14 | "a strategy ready, or a strategy that needs your review" | supported | app/verification/loop.py:360-367 |
| 15 | "a new reply from a lead" | supported | app/workers/outreach_tasks.py:954-956 (M7 push sent before the push=False events) |
| 16 | "a meeting booked" | supported | app/api/webhooks.py:182; app/workers/calendar_tasks.py:247 |
| 17 | "a campaign paused automatically because of a high bounce rate" | supported | app/services/sequence_engine.py:570 ("the M7 push above already went") |
| 18 | "a mailbox paused because of poor sending health, or a sending domain found on a blocklist" | supported | app/services/mailbox_health.py:383-390; app/services/deliverability.py:255-262 |
| 19 | "a message held for review" | supported | app/services/send_review.py:333-340 |
| 20 | "a WhatsApp template approved or rejected (sent to administrators only)" (re-checked) | supported | app/services/whatsapp_templates.py:280-296 |
| 21 | "an SDR launch waiting for your approval, or a decision on your own launch" | supported | app/api/sequences.py:355-360,377-383 |
| 22 | "A campaign you pause yourself does not send you a push notification, because you already know." | supported | app/api/analytics.py:142-149 (push=False) |
| 23 | "Push notifications only work if your Vectorae deployment has push notifications (Firebase) set up." | supported | app/services/notifications.py:8,65-71 |
| 24 | "Parts of the push setup in the app are marked in the code as not yet verified…" | supported | frontend/capacitor.config.ts:41; frontend/src/hooks/usePushNotifications.ts:22-30 |
| 25 | "Everything they announce is also visible in the app itself." | supported | events are also stored/shown in-app (app/services/event_bus.py emit; replies in Inbox, approvals in Team, reviews in Campaigns › review) |
| 26 | "You sign in with the same email and password as on the web, and the same rules apply" | supported | app/api/auth.py:380-405 (one login route; native gets refresh token in body, auth_sessions.py:18-20) |
| 27 | "On the phone, your sign-in is kept in the app's private storage on the device, which other apps cannot read." | supported | frontend/src/lib/storage.ts:6-12,35-58 |
| 28 | "Signing out with Log out ends the session on the server too." | supported | frontend/src/lib/api/auth.ts:70-77; app/api/auth.py:444-455 |
| 29 | "You cannot use the app offline to make changes… Some screens you opened recently may still show their last data while offline." | supported | docs/README_M7_COMPLETE.md:35 |
| 30 | "The app does not send outreach from your phone or use your phone's number or SIM. WhatsApp messages go out from the deployment's WhatsApp Business number, through the server." | supported | docs/README_M7_COMPLETE.md:34; app/config.py:137 |
| 31 | "The app is built for distribution through the Google Play Store." | supported | frontend/capacitor.config.ts:3-4; docs/README_M7_COMPLETE.md:13,20,37 |
| 32 | "If your team runs its own Vectorae deployment, the app must be built to point at that deployment's server." | supported | frontend/src/hooks/usePushNotifications.ts:35 (NEXT_PUBLIC_API_URL baked at build) |

Summary: 31 supported, 0 unsupported, 0 contradicted. (final, after re-check)

---

### 27-troubleshooting.md
| # | Sentence (verbatim, may be shortened with …) | Verdict | Evidence (path:line) / what the code says |
|---|---|---|---|
| 1 | "A strategy moves through these statuses: pending, researching, verifying, then verified (or needs human review)." | supported | app/db/models.py:79-90 |
| 2 | "Research for one strategy is long: it runs 72 or 144 steps once per strategy…" | supported | app/db/models.py:93-95; app/config.py:51; app/workers/tasks.py:95-145 (one pipeline task per strategy). Consistent with D1. Nuance: a small budget can plan fewer steps per phase (app/api/strategies.py:190-191). |
| 3 | "If its status is pending, researching, verifying, failed or budget exhausted, a Resume button is shown." | supported | frontend/src/components/strategy/ResumeStrategyButton.tsx:13-14,42,51 |
| 4 | "Press Resume, then Confirm resume. The run continues from the last finished step; finished steps are not repeated and not paid for again." | supported | ResumeStrategyButton.tsx:36,79; app/workers/tasks.py:175-178 |
| 5 | Live-run warning "Only resume if progress has stopped. Resuming a run that is still working can duplicate work." for pending/researching/verifying | supported | ResumeStrategyButton.tsx:19-20,60-61 |
| 6 | "Budget exhausted means the next AI step could have gone over the strategy's budget or your plan's daily AI limit." | supported | app/services/usage_meter.py:63-79,262-306 |
| 7 | "You can enter a larger New budget $ before confirming." | supported | ResumeStrategyButton.tsx:66; app/api/strategies.py:311-321 |
| 8 | "A strategy budget can be between $0.50 and $50.00 (the default is $15); the upper limit is a deployment setting." | supported | app/api/strategies.py:57-69; app/config.py:59-60 |
| 9 | "A single research or verification run has a time limit of 2 hours (a deployment setting). A run that hits it, or hits a temporary error, is retried up to 3 times and resumes where it stopped." | supported | app/config.py:350; app/workers/tasks.py:95-97,174-181,186-188 |
| 10 | "If an error can never succeed on retry …, or retries are used up, the strategy becomes failed with the error saved on it." | supported | app/workers/tasks.py:43-67,158-172 |
| 11 | "A strategy whose campaign is already running cannot be resumed: "pause the campaign before resuming the pipeline"." | supported | app/api/strategies.py:304-308 |
| 12 | "If one of the 10 verification checks keeps failing after its retries, the strategy stops at needs human review." | supported | app/config.py:351-353; app/db/models.py:84 |
| 13 | "Leads cannot be sourced until it passes." | supported | app/api/leads.py:83-90 |
| 14 | "You can press Re-verify to run the checks again, or a person can pass specific failed checks by hand, with a written reason that is recorded." | supported | frontend/src/components/strategy/ReverifyStrategyButton.tsx:13-14,55; app/api/strategies.py:380-426 |
| 15 | "Open Settings › Integrations and find the Gmail card." | supported | frontend/src/app/(app)/settings/page.tsx:298-302,531 |
| 16 | ""Not connected" – press Connect and sign in with Google." | supported | settings/page.tsx:306,321-323 |
| 17 | "Connected but not working – press Test. If the result is unhealthy, press Reconnect." | supported | settings/page.tsx:316-327 |
| 18 | ""Calendar access missing — reconnect to create Google Meet links. Your Gmail access is kept." – press Reconnect for Calendar." | supported | settings/page.tsx:308-312,325-326 |
| 19 | ""Gmail is not configured on the server: …" – the deployment has not set up Google sign-in. Contact your administrator." (re-checked) | supported | app/api/integrations.py:31-36; frontend/src/lib/api/client.ts:57-64; frontend/src/app/(app)/settings/page.tsx:284-290 |
| 20 | "402 – plan limit… "Free plan allows 3 strategies. You have 3." It is used for: number of strategies, leads per strategy, sequence steps, channels, and features such as the playbook, A/B results or the LinkedIn network." | supported | app/core/plans.py:225-235; app/api/strategies.py:163-165; app/api/leads.py:96-104; app/api/sequences.py:57-69; app/api/playbook.py:46; app/api/strategies_advanced.py:42; app/api/linkedin_network.py:37-46 |
| 21 | ""Your … plan's daily AI limit ($…) is used up. It resets at 00:00 UTC." – wait for the reset, or upgrade." | supported | app/api/strategies.py:114-126 |
| 22 | "A plain "429 Too Many Requests" is a rate limit." | supported | app/core/rate_limiting.py:154-162 (object detail with no message); frontend/src/lib/api/client.ts:161-179 (falls back to "status statusText") |
| 23 | "Common defaults: 2 new strategies per hour, 5 lead-sourcing requests per hour, 10 sign-in attempts per 15 minutes, 20 support chat messages per day." | supported | app/core/config.py:7-13,172,200,320,337 |
| 24 | ""Too many attempts. Wait a while and try again." – too many password confirmations (for example when exporting data)." | supported | frontend/src/lib/profile.ts:25-27,46-49; app/api/account_data.py:63-64 |
| 25 | ""payments are not configured; plans cannot be changed right now" – payments are not set up on this deployment." | supported | app/api/billing.py:82-84 (shown on production deployments; see 22 #59) |
| 26 | ""Support chat is temporarily unavailable. Submit a ticket instead." – the chat assistant is switched off; tickets still work." | supported | app/api/support.py:94-99; frontend/src/components/support/ChatWidget.tsx:120-121 |
| 27 | ""We couldn't verify your network just now…" – the VPN check service did not answer." | supported | app/services/network_guard.py:41,64-69 |
| 28 | "Email not verified – confirm your email address…; you are sent to the check-email screen." | supported | app/services/auth.py:209-210; frontend/src/app/page.tsx:25; frontend/src/components/shell/Shell.tsx:73 |
| 29 | "Phone not verified – some actions, such as choosing a plan, need a verified phone. You are sent to the verification screen." | supported | app/services/identity.py:164-173; frontend/src/app/pricing/page.tsx:71-73 |
| 30 | "VPN, proxy or hosting network – turn off your VPN…" | supported | app/services/network_guard.py:36-38,76-77 |
| 31 | ""account suspended" – an administrator suspended the account." | supported | app/services/auth.py:207-208 |
| 32 | "Workspace role – for example "Viewers have read-only access to this workspace." or "Deleting needs a manager in this workspace."" | supported | app/services/rbac.py:50-55 |
| 33 | "Leads can only be sourced for a strategy that passed all 10 verification checks. Otherwise you see "leads can only be sourced for a strategy that passed all 10 verification passes"." | supported | app/api/leads.py:83-90 (full text begins "strategy status is '<status>' - …") |
| 34 | "If the strategy is full for your plan, you get a 402 instead." | supported | app/api/leads.py:96-104 |
| 35 | "Is the campaign paused? On Campaigns, a "Campaign paused" banner shows the reason. Press Resume when ready." | supported | frontend/src/app/(app)/campaigns/page.tsx:492-506 |
| 36 | "By default, messages go out between 09:00 and 17:00 in the lead's time zone (UTC if unknown), on weekdays only." | supported | app/config.py:109-112; app/services/sequence_engine.py:72,86-91 |
| 37 | "By default a Gmail mailbox sends at most 100 messages a day. A newly connected mailbox starts at 10 a day and adds 10 each day until it reaches that limit." | supported | app/config.py:106-108 |
| 38 | "Is the mailbox paused or slowed? Look at Settings › Deliverability. A paused mailbox needs Resume." | supported | frontend/src/components/settings/MailboxHealthCard.tsx:65,128; app/services/mailbox_health.py:39-41 |
| 39 | "Held messages wait in the send-review queue until approved." | supported | app/services/send_review.py:330-340; docs/features/send-review-queue.md |
| 40 | "WhatsApp needs a recorded opt-in and an approved template or an open 24-hour window." | supported | app/workers/outreach_tasks.py:223-248 |
| 41 | "All sending is done by a background worker on the server, which checks for due messages every minute by default." | supported | app/config.py:116; app/workers/celery_app.py:226-229 |
| 42 | "If it is not running, nothing is sent and strategies do not progress, but nothing is lost." | supported | app/workers/outreach_tasks.py:101-120 (due SCHEDULED messages are picked up on the next tick) |
| 43 | "the server's `/health` address reports "degraded" when the worker has not checked in for more than 2 minutes." | supported | app/api/health.py:4-10,33-35,78-90 |
| 44 | "When an email bounces, that lead's sequence stops." | supported | app/services/sequence_engine.py:511-524 |
| 45 | "Once a campaign has sent at least 10 messages, it pauses automatically if more than 3% of them bounced, and stays paused until a person resumes it." | supported | app/config.py:113-114; app/services/sequence_engine.py:527-555 |

Summary: 45 supported, 0 unsupported, 0 contradicted. (final, after re-check)

---

### 28-glossary.md
| # | Sentence (verbatim, may be shortened with …) | Verdict | Evidence (path:line) / what the code says |
|---|---|---|---|
| 1 | "Product – what you sell… Every strategy belongs to a product." | supported | app/api/strategies.py:150-152 (strategy created under a product); account_export.py:94 (strategies → product_id) |
| 2 | "Past client – … industry, company size, buyer role, deal size, acquisition channel, trigger event and sales-cycle length." | supported | app/db/models.py:809-821 |
| 3 | "Flow 1 (with clients) – used when the product has at least one past client." | supported | app/api/strategies.py:168-178 (default flow by has_clients) |
| 4 | "Flow 2 (no clients) – … Vectorae builds the strategy and then a go-to-market plan (144 steps in all)." (re-checked) | supported | app/pipeline/engine.py:37-40; app/db/models.py:76,95 |
| 5 | "Strategy – the research-backed plan… On the Pricing page, strategies are counted as "campaigns"." | supported | frontend/src/lib/pricing.ts:80 |
| 6 | "ICP … including the people it is not for. It is settled in phase 2 of the research." | supported | app/pipeline/registry.py:69-79 (phase 2, incl. "Disqualifiers & anti-ICP") |
| 7 | "GTM (go-to-market) – positioning, pricing, launch order, channel budget and similar groundwork. Built after the strategy, in Flow 2 only." (re-checked) | supported | app/pipeline/registry.py:153-230; app/pipeline/engine.py:37-40 |
| 8 | "Research pipeline – … 72 steps (8 phases of 9 steps) in Flow 1, or 144 steps (72 strategy plus 72 GTM) in Flow 2. It runs once per strategy, not once per prospect." (re-checked) | supported | app/pipeline/registry.py:9-13; app/pipeline/engine.py:37-40; app/workers/tasks.py:95-145. Consistent with D1. |
| 9 | "Verification passes – 10 independent checks…, covering topics such as legal compliance, targets and ICP fit. Nothing is sourced or sent until all 10 pass." | supported | app/verification/passes.py:103-161 (ICP fit #2, Legal & compliance #4, KPI realism #8); app/api/leads.py:83-90; app/api/sequences.py:282-284. Nuance: a human override can mark failed passes as passed (app/api/strategies.py:380-426). |
| 10 | "Needs human review – a check kept failing after its retries. A person must re-verify or decide." | supported | app/db/models.py:84; app/config.py:353; ReverifyStrategyButton.tsx:13-14 |
| 11 | "Strategy budget – the most a single strategy's research and verification may spend on AI. The default is $15; it can be set between $0.50 and $50.00." | supported | app/services/usage_meter.py:45 (BUDGETED_PURPOSES pipeline, verification); app/config.py:59-60; app/api/strategies.py:57-69 |
| 12 | "Budget exhausted – the strategy stopped because the next AI step could have gone over its budget or the plan's daily AI limit. It can be resumed." | supported | app/db/models.py:87-90; app/services/usage_meter.py:63-79 |
| 13 | "Daily AI limit – the most AI spend your whole account may use per UTC day, set by your plan. It resets at 00:00 UTC." | supported | app/core/plans.py:45-51; app/services/usage_meter.py:187-213 |
| 14 | "Lead – one prospect (a person at a company) found for a strategy." | supported | app/db/models.py (Lead.strategy_id); app/api/leads.py:113 |
| 15 | "Lead statuses – sourced, enriched, email found, then verified (email deliverable), flagged (risky) or dropped (undeliverable or suppressed). After outreach: contacted, replied, meeting booked, proposal sent, opportunity, closed won, closed lost or disqualified." | supported | app/db/models.py:98-120 |
| 16 | "Suppression list – the do-not-contact list of email addresses, phone numbers and LinkedIn profiles. Checked before every send and before sourcing." | supported | app/db/models.py:1672-1674,3134-3141; app/workers/outreach_tasks.py:185-195; app/api/leads.py:283-285 |
| 17 | "Entries can't be removed by customers; only a platform administrator can remove one." (re-checked) | supported | app/api/ui_support.py:275-300; app/api/admin.py:209-218 |
| 18 | "F-P-T-A – four scores from 0 to 100 for each lead: Fit…, Problem…, Timing… and Access…. The overall score weights them 30% fit, 30% problem, 20% timing and 20% access." | supported | app/services/fpta_scoring.py:54,80,311; app/db/models.py:1203-1207 |
| 19 | "Cooling / archived – before each send Vectorae estimates a lead's chance of converting. A cooling lead's sequence is paused; an archived lead's sequence is stopped." | supported | app/services/conversion_probability.py:240-283,289 |
| 20 | "Sequence – … A sequence can be draft, active, paused, completed or pending approval." | supported | app/db/models.py:142-149 |
| 21 | "Step – one message in a sequence, on one channel." | supported | app/api/sequences.py:82-90 (StepIn.channel overrides the sequence channel) |
| 22 | "Enrollment – … active, paused (resumes later), stopped (can never send again to that lead) or completed (all steps sent)." | supported | app/db/models.py:172-176 |
| 23 | "Campaign – a strategy's outreach while it is running. It can be paused and resumed as a whole." | supported | app/api/analytics.py:131-165 |
| 24 | "Channel – … email through your connected Gmail (called "gmail" in plans), WhatsApp, LinkedIn, or an AI phone call ("phone")." | supported | app/core/plans.py:58,110; frontend/src/lib/pricing.ts:69-71 |
| 25 | "Send window – … By default 09:00 to 17:00 in the lead's time zone, weekdays only." | supported | app/config.py:109-112 |
| 26 | "Daily cap and warm-up – … (100 by default). A new mailbox starts lower (10) and rises by 10 each day." | supported | app/config.py:106-108 |
| 27 | "Bounce auto-pause – a campaign pauses itself when more than 3% of its emails bounce, once at least 10 have been sent." | supported | app/config.py:113-114; app/services/sequence_engine.py:536,549 |
| 28 | "Mailbox health – a 0 to 100 score per mailbox. Below 70 sending slows down (throttled); below 40 the mailbox is paused." | supported | app/services/mailbox_health.py:30-37,77-78 |
| 29 | "Send-review queue – where high-risk messages wait for a person to approve them before sending." | supported | app/services/send_review.py:330-340 ("This send matched a high-risk rule") |
| 30 | "Opt-in – a recorded permission… to receive WhatsApp messages. Cold WhatsApp needs an opt-in and an approved template." | supported | app/workers/outreach_tasks.py:223-248 |
| 31 | "24-hour window – … free-form messages are allowed only within 24 hours of the prospect's last message. Outside it, only approved templates may be sent." | supported | app/workers/outreach_tasks.py:229-248; app/api/sequences.py:91-94 |
| 32 | "Reply classification – each human reply is labelled interested, neutral, objection, not now or unsubscribe. Machine messages such as bounces and out-of-office replies are recognised separately." | supported | app/services/reply_intent.py:18-30 (machine messages handled by their own classification first; mapped to neutral in the intent metric) |
| 33 | "Re-engagement memory – a "not now" reply is turned into a reminder to come back on the date the prospect gave, or after 90 days by default." | supported | app/services/system_settings.py:126-132 (reengagement_memory_days 90) |
| 34 | "Booking page – Vectorae's own scheduling page… Calendly is supported as an alternative." | supported | app/db/models (calendar_booking_pages, account_export.py:55,128); app/api/webhooks.py:165 (Calendly) |
| 35 | "Playbook – … New strategies consult it during the messaging and execution phases. On a new account it is empty and says so." | supported | app/services/playbook_service.py:7-12,25; app/pipeline/engine.py:128-132 |
| 36 | "A/B test – sending different versions (variants) of a step to compare results." | supported | app/api/sequences.py:85 (StepIn.variant); app/api/strategies_advanced.py:29-60 |
| 37 | "Attribution – … direct reply (… confidence 1.0), thread match (…; 0.85), last touch (… a guess whose confidence falls as time passes), or none (nothing was sent before the outcome)." | supported | app/services/attribution.py:13-23,96,153,164 |
| 38 | "Pipeline Health Score – … reply rate (35%), sequence completion (25%), how recently new leads were added (20%) and open conversations (20%)." | supported | app/services/pipeline_health.py:9-12,53-58 |
| 39 | "Consent ledger – the record of opt-ins, opt-outs and erasures for each prospect: when they told you, and what Vectorae did." | supported | app/db/models.py:4413-4425 |
| 40 | "Unsubscribe – the link in every email. It works without signing in, takes effect immediately and stops contact on every channel." | supported | app/api/unsubscribe.py:1-7; app/services/consent.py:219-230 (email, phone, LinkedIn, WhatsApp opt-in); sequence_engine.py:495-509 |
| 41 | "Erasure (GDPR delete) – clearing a lead's personal details and adding them to the suppression list." (re-checked) | supported | app/api/leads.py:290-339 |
| 42 | "Plan – … limits on strategies, leads, sequence steps, channels and daily AI spend." | supported | app/core/plans.py:52-178 |
| 43 | "Deployment – one installation of Vectorae (its own server and database)…" | supported | app/config.py:435-446 (P0-D: each deployment serves one customer organisation) |
| 44 | "Administrator – a person who runs the deployment, with access to the admin panel." | supported | app/db/models.py:411 (is_admin); app/api/deps.py:18-32 |
| 45 | "Workspace – your account as seen by teammates you invite. Roles are owner, manager, SDR and viewer." | supported | app/services/rbac.py:7-13,24 |
| 46 | "SDR – … a team member who works leads but whose campaign launches may need approval." | supported | app/services/rbac.py:10-11; app/api/sequences.py:330-337 |
| 47 | "Client (agency mode) – a separate book of business inside an agency account, with its own reporting, sending domains and invoice view." | supported | app/services/client_workspaces.py:3-16 |
| 48 | "White label – showing the app under your own brand name, logo and domain." | supported | app/services/workspaces.py:310-332 |
| 49 | "API key – a secret starting with `lpk_` that lets tools such as Zapier act as you through the API." | supported | app/services/api_keys.py:1-6,21 |
| 50 | "Webhook – a message Vectorae sends to another tool when something happens, for example a reply or a booked meeting." | supported | app/workers/outreach_tasks.py:964-967 (reply_received webhook_payload); frontend/src/components/settings/WebhooksCard.tsx:77 |

Summary: 50 supported, 0 unsupported, 0 contradicted. (final, after re-check)

---

### 29-known-limitations.md
| # | Sentence (verbatim, may be shortened with …) | Verdict | Evidence (path:line) / what the code says |
|---|---|---|---|
| 1 | "Delete your account yourself. There is no account deletion in the app and no automatic account erasure. A deletion request is handled by the team by hand. You can download your data (Profile › Download your data)." | supported | docs/program/BASELINE.md:38,95,352; frontend/src/app/(app)/profile/page.tsx:149; app/api/account_data.py:51 |
| 2 | "Reset a forgotten password. There is no "forgot password" flow." | supported | no such route in app/api/auth.py |
| 3 | "Use two-factor sign-in. It is not available." | supported | no 2FA/TOTP code in app/ or frontend/src |
| 4 | "See or end individual sessions. There is no list of signed-in devices. Changing your password signs out everywhere." | supported | app/api/auth.py:494-515 |
| 5 | "Erasing a lead clears its personal details and adds it to the suppression list, but messages already sent… and replies… are not deleted." (re-checked) | supported | app/api/leads.py:275-345 |
| 6 | "The web app has no billing screen for cancelling a plan or disputing a pay-per-meeting charge. These exist in the Vectorae API only…" | supported | app/api/billing.py:92-121; frontend/src/lib/api/billing.ts:57-60 (no importer outside pricing's catalog/checkout) |
| 7 | "The payment connection to Stripe is still marked in the code as waiting for live keys…" | supported | app/services/billing.py:20-22,47; app/config.py:475-479 |
| 8 | "A production deployment without Stripe set up cannot change plans." (re-checked) | supported | app/api/billing.py:82-84 |
| 9 | "The Pricing page shows an analytics history length per plan; the product does not enforce it." | supported | frontend/src/lib/pricing.ts:86-88; analytics_history_days unused outside plans.py / billing_catalog.py |
| 10 | "Multi-variate results are available on every plan that includes A/B testing…" | supported | app/api/strategies_advanced.py:36-44 |
| 11 | "The daily AI limit amounts per plan may still change." | supported | app/core/plans.py:48-50 ("PLACEHOLDERS pending the founders' pricing decision") |
| 12 | "Vectorae's automated tests run against simulated versions of outside services." | supported | CLAUDE.md suite description (offline, FakeClaude); docs/program/BASELINE.md:266-267 |
| 13 | "Parts of these integrations are marked in the code as not yet verified…: Gmail, WhatsApp Business, Apollo, Hunter, Calendly, LinkedIn (through Unipile), HubSpot, Zoom, Recall.ai and the AI phone-call providers." | supported | `TODO: verify` markers in app/integrations/gmail.py (10), whatsapp.py (17), apollo.py (9), hunter.py (7), calendly.py (6), unipile_linkedin.py (8), hubspot.py (3), zoom.py (5), recall.py (4), voice_providers.py (4) |
| 14 | "Google Meet and Zoom meeting creation has not been verified against the live services. Creating a meeting with your own custom link is the only verified path. If Meet or Zoom fails, the meeting is still created, without the video link." | supported | FEATURES.md:1088-1116; app/api/meetings.py:21-28,315-351; app/integrations/google_meet.py:27 |
| 15 | "Recall.ai … has been built and tested with simulations only and has never been called live." | supported | app/integrations/recall.py:11; FEATURES.md:1123-1131 |
| 16 | "Zoom meetings are all hosted by one Zoom account configured for the deployment." | supported | app/integrations/zoom.py:3-11 |
| 17 | "One Gmail mailbox per account. You cannot connect several mailboxes to one account." | supported | app/db/models.py:1660-1662 (user_id UNIQUE); docs/features/agency-mode.md:110 |
| 18 | "One WhatsApp number per deployment. Every account and every agency client … sends WhatsApp from the same business number." | supported | app/config.py:137; docs/program/BASELINE.md:92,164 |
| 19 | "No cold WhatsApp without consent. A cold WhatsApp message needs an approved Meta template and a recorded opt-in. There is no free-form cold path." | supported | app/workers/outreach_tasks.py:223-248 |
| 20 | "Workspace compliance rules apply at the moment of sending. Scheduling still uses the standard send window, and a message a rule forbids is rescheduled when it comes due." | supported | FEATURES.md:1050-1054 |
| 21 | "Rule caps apply to Gmail and WhatsApp; LinkedIn and phone keep their own limits." | supported | FEATURES.md:1055-1056 |
| 22 | "Some dashboards show the standard 3% bounce threshold even when a workspace has set a lower one; the pause itself uses the lower one." | supported | FEATURES.md:1057-1059; frontend/src/app/(app)/campaigns/page.tsx:501,526; app/services/sequence_engine.py:544-549 |
| 23 | "Region detection depends on the country or time zone found for a lead. Leads with neither are treated as "unknown"." | supported | FEATURES.md:1062-1064 |
| 24 | "Re-engagement after a finished sequence is email only, is off until an owner or manager turns it on for a campaign, and is capped." | supported | FEATURES.md:1040-1045,1065 |
| 25 | "Assigning a lead to a teammate does not change who sends… Assignees are not notified." | supported | FEATURES.md:1077-1081; docs/features/workspaces.md:95-97 |
| 26 | "No single "stop this contact" button, and no account-wide or platform-wide pause switch for customers. Pause campaigns one by one." | supported | see article 25 rows 16, 32, 34 |
| 27 | "It does not reply to people automatically. Replies are classified and routed. Approving an AI reply draft saves it as a note for a person to send; it does not send it." | supported | FEATURES.md:369,1027-1028; app/api/crm.py:1383-1387 |
| 28 | "It does not collect consent to record meetings. Sending a recording bot records everyone on the call… The meeting room reminds the host to announce it; nothing enforces that." | supported | FEATURES.md:1132-1135 |
| 29 | "In-app benchmarks show only this deployment's accounts, and nothing is shown for a group with fewer than 10 accounts (never fewer than 5, whatever the setting)." | supported | app/services/system_settings.py:218-221; app/services/benchmarks.py:16-17,74 |
| 30 | "Booking links of the form `/book/<name>` need a rule on the web host. Where it is missing, links use the form `/book/?slug=<name>` instead." | supported | FEATURES.md:1136-1139 |
| 31 | "Google accounts connected before calendar access was added must reconnect to create Meet links." | supported | FEATURES.md:1117-1122; frontend/src/app/(app)/settings/page.tsx:308-312 |
| 32 | "Support tickets are stored and reviewed by the team in an admin queue. Nothing alerts the team automatically when a ticket arrives…" | supported | app/api/support.py:332-359; docs/features/ai-support-chat.md:20,57,293,335 |
| 33 | "…and the app does not show you your tickets or replies to them." | supported | GET /support/tickets exists (app/api/support.py:362-370) but frontend/src/lib/api/support.ts:71 listSupportTickets has no importer; only the admin page lists tickets |
| 34 | "Support chat is limited to 20 messages per person per day (a deployment setting). Tickets are not limited." | supported | app/core/config.py:13,337; app/api/support.py:340-342 |
| 35 | "No public status page yet. A status page at status.calendarharvest.com is planned but not live." | supported | docs/program/STAR_PROMPT.md:1,30,101; no status-page code in app/ or frontend/src |
| 36 | "Tutorials on the Learn page appear only after the team publishes them, so the page can be empty." | supported | app/api/tutorials.py:18,99,173 |
| 37 | "Mobile: there is an Android app but no iPhone app. Parts of the app's push-notification setup are marked as not yet verified…" | supported | docs/README_M7_COMPLETE.md:36; frontend/capacitor.config.ts:41 |
| 38 | "Learning is shared within a deployment. The playbook scores … are pooled across the deployment. In agency mode … different clients' outcomes feed the same scores…" | supported | docs/program/BASELINE.md:163 |
| 39 | "Benchmarks in small groups can reflect one account's rounded rate, and industry comes from the strategy's ICP. A strategy aimed at several industries is grouped as "multiple"." | supported | app/services/benchmarks.py:19-23,36,65 |
| 40 | "Key safety behaviours (separating accounts, GDPR lead deletion, suppression at send, bounce pause, STOP handling, sending exactly once) are proven by the automated test suite on a lightweight test database. The tests that run them on … PostgreSQL were not working…" | supported | docs/program/BASELINE.md:240-267 |

Summary: 40 supported, 0 unsupported, 0 contradicted. (final, after re-check)

---

### 30-contact-support-and-status.md
| # | Sentence (verbatim, may be shortened with …) | Verdict | Evidence (path:line) / what the code says |
|---|---|---|---|
| 1 | "On every page of the app after you sign in, there is a round button with a life-ring icon in the bottom-right corner ("Open support chat")." | supported | frontend/src/components/shell/Shell.tsx:170; frontend/src/components/support/ChatWidget.tsx:199-203 |
| 2 | "It opens a panel called Vectorae support with two modes, switched by the icons at the top of the panel: Chat … Submit a ticket" | supported | ChatWidget.tsx:211-217,226,236 |
| 3 | "The ticket form can be opened at any time. You do not have to chat with the assistant first." | supported | ChatWidget.tsx:236 (mode switch always present); app/api/support.py:332-345 (chat_session_id optional) |
| 4 | "You need a confirmed email address to use the chat." | supported | app/services/auth.py:209-210; docs/features/ai-support-chat.md:288 |
| 5 | "The assistant answers questions about Vectorae: how it works, setting up campaigns, outreach, the learning loop, tutorials, your data and getting support. It answers only from Vectorae's written help content, not from general knowledge." | supported | app/services/support_kb.py:3,169-172; app/services/support_chat.py:81-88 |
| 6 | "If you ask about something unrelated to Vectorae, it replies with a fixed message: "I can only help with questions about Vectorae — …". It does not offer a ticket for off-topic questions." | supported | app/services/support_kb.py:169-172; app/services/support_chat.py:140-151 |
| 7 | "If it cannot find the answer, or is not confident enough, it does not guess. It says so and offers Submit a ticket." | supported | app/services/support_chat.py:154-162,366-369; ChatWidget.tsx:290-300 |
| 8 | "The ticket subject is then filled in for you, starting with "Question not in FAQ:" followed by your question." | supported | frontend/src/lib/support/ticketSubject.ts:14; ChatWidget.tsx:174-178 |
| 9 | "When you open the chat, a few suggested questions are shown to get you started." | supported | ChatWidget.tsx:262-275 (first 4 FAQ questions) |
| 10 | "A question can be up to 2,000 characters long." | supported | app/api/support.py:46,55 |
| 11 | "You can send 20 chat messages per day. This is a deployment setting; 20 is the default." | supported | app/core/config.py:13,337 |
| 12 | "When you reach the limit you see "You've reached today's message limit. You can still submit a ticket." and the panel switches to the ticket form." | supported | ChatWidget.tsx:115-118 |
| 13 | "If the chat has been switched off …, you see "Support chat is temporarily unavailable. Submit a ticket instead." Tickets still work." | supported | app/api/support.py:94-99; ChatWidget.tsx:120-122 |
| 14 | "Fill in Subject (3 to 200 characters)." | supported | ChatWidget.tsx:360-361; app/api/support.py:61 |
| 15 | "Fill in What do you need help with? (at least 10 characters)." | supported | ChatWidget.tsx:366-367; app/api/support.py:62 |
| 16 | "Press Submit ticket. You see "Ticket submitted."" | supported | ChatWidget.tsx:343,375 |
| 17 | "Tickets are not limited by the daily chat limit…" | supported | app/api/support.py:340-342 |
| 18 | "The ticket form says the team responds within 24 hours. That is a commitment written in the app, not something the product enforces." | supported | ChatWidget.tsx:346,357; docs/features/ai-support-chat.md:335 |
| 19 | "It is stored in Vectorae's database and appears in the team's support queue, which shows your account email address." | supported | app/api/support.py:332-359; app/api/admin.py:638-690 (user_email) |
| 20 | "The team is not alerted automatically when a ticket arrives; someone checks the queue." | supported | app/api/support.py:336-338; docs/features/ai-support-chat.md:293,335 |
| 21 | "The team marks a ticket resolved in its queue. Replies are not shown inside the app, and the app has no screen listing your own tickets." | supported | app/api/admin.py:700; frontend/src/lib/api/support.ts:71 (listSupportTickets has no importer) |
| 22 | "Each chat conversation is private to you." | supported | app/api/support.py:140-160 (ownership in WHERE clause) |
| 23 | "You can start a fresh conversation with Start a new chat; earlier conversations are kept." | supported | ChatWidget.tsx:326-331; app/api/support.py:278-312 |
| 24 | "A conversation is deleted 30 days after its last message, by a job that runs every night (a deployment setting; 30 days is the default)." | supported | app/workers/support_tasks.py:3-13,50-63; app/workers/celery_app.py:250-254; app/config.py:270 |
| 25 | "A ticket you raised from a conversation is not deleted when the conversation is…" | supported | app/workers/support_tasks.py:15-19 |
| 26 | "The public Contact page … offers a link to book a call, an email address, the company's LinkedIn page and WhatsApp numbers." | supported | frontend/src/app/contact/page.tsx:19-25,87,102,111,121-125 |
| 27 | "For privacy requests, such as a request to delete your account, use the contact email on the Privacy page." | supported | frontend/src/app/privacy/page.tsx:19,144-152 |
| 28 | "A public status page at status.calendarharvest.com is planned, designed to keep working even when Vectorae itself is down. It is not live…" | supported | docs/program/STAR_PROMPT.md:1,30,101 |
| 29 | "campaigns run on Vectorae's servers, not in your browser or phone, so closing the app does not stop or pause them." | supported | docs/README_M7_COMPLETE.md:33; app/workers/celery_app.py:226-229 |

Summary: 29 supported, 0 unsupported, 0 contradicted. (final, after re-check)

---

## Overall summary (articles 21-30), final state after the writer's corrections

| Article | Supported | Unsupported | Contradicted |
|---|---|---|---|
| 21-privacy-data-retention-deletion.md | 45 | 0 | 0 |
| 22-plans-limits-billing.md | 59 | 0 | 1 |
| 23-account-security.md | 41 | 0 | 0 |
| 24-workspaces-and-agency-mode.md | 42 | 0 | 0 |
| 25-pause-stop-kill-switch.md | 36 | 0 | 0 |
| 26-mobile-app.md | 31 | 0 | 0 |
| 27-troubleshooting.md | 45 | 0 | 0 |
| 28-glossary.md | 50 | 0 | 0 |
| 29-known-limitations.md | 40 | 0 | 0 |
| 30-contact-support-and-status.md | 29 | 0 | 0 |
| **Total** | **418** | **0** | **1** |

First pass: 394 supported, 0 unsupported, 24 contradicted. Re-check: all 24 flagged sentences now supported. Rows rewritten from the corrected text are marked "(re-checked)", and new sentences "(new)". 26 #8 (pull to refresh) was removed from the article, so its row is gone. Two new sentences: 21 #30a is supported; 22 #7a is partly contradicted. All `sources:` paths exist after the edits; new paths include app/api/admin.py, app/services/admin_service.py, app/api/integrations.py and app/pipeline/engine.py.

The original analysis of the 24 first-pass contradictions follows, kept for history.

Founder decision D1: consistent everywhere it appears (outreach sent automatically by the server: 25 #1, 26 #5, 30 #29; research pipeline once per strategy: 27 #2, 28 #8).

Recurring root causes behind the 24 contradictions:
1. "Suppression is permanent / can never be removed" (21 #16, 25 #21, 25 #27, 28 #17, 28 #41, 29 #5): an admin DELETE route exists (app/api/admin.py:209-218).
2. "Delete lead (GDPR)" label and the "messages are removed" dialog (21 #26, 21 #34, 25 #21): both live only in the unused component frontend/src/components/kanban/LeadDrawer.tsx.
3. Stub-mode billing (22 #59, 29 #8): the 503 only fires in production; non-production stub mode grants plans for free.
4. Workspace members "never asked to buy" (22 #37, 24 #6): only when the owner has an active plan.
5. Flow 2 order (28 #4, 28 #7): strategy pipeline runs first, GTM second.

Out-of-scope discoveries (reported, not fixed):
- frontend/src/components/kanban/LeadDrawer.tsx is dead code and its confirm dialog makes a false promise ("removes … their messages, and outcomes").
- frontend/src/components/ui/PullToRefresh.tsx is never mounted.
- The LinkedIn-network delete button is hidden after a downgrade even though the API deliberately allows it (frontend/src/app/(app)/network/page.tsx:210,236 vs app/api/linkedin_network.py:137-138). This is a product bug: a downgraded customer cannot delete their data from the UI.
- GDPR lead erasure leaves numeric scores (ai_booking_likelihood, fpta_*, fpta_reasons_json) on the tombstone (app/api/leads.py:325-339).
- The data-export refusal for API-key and rate-limited attempts is not audited, contrary to the module docstring (app/api/account_data.py:16-17 vs :61-64).
- The Privacy page promises deletion of prospect data "when that client's engagement ends" (frontend/src/app/privacy/page.tsx:137-141); no code does this.
- Campaign banner says "≥ 3%" but the pause rule is "> 3%" (campaigns/page.tsx:501 vs sequence_engine.py:549).
- Sequence API caps steps at 20 (app/api/sequences.py:120) although plans.py advertises "Unlimited" for scale/pro/enterprise, and the Pricing page shows "Unlimited sequence steps".
- WhatsApp template approve/reject push goes to admins only (app/services/whatsapp_templates.py:280-296).
- FEATURES.md:1029 still says "LinkedIn is not implemented", which contradicts the LinkedIn code; stale doc.


---

# Help AI v2, Phase 1 (2026-10-18): articles 31–44 and changed sections

Checked by the same read-only `help-center-fact-checker` agent. New articles
(31–44) and the rewritten parts of 06 and 10 were checked sentence by sentence
in full. For the other changed articles (03, 13, 22, 24, 27, 29, 30) only the
added or edited sentences were checked; their unchanged text keeps the
2026-10-10/11 verdicts above. Every non-supported sentence was fixed and
re-checked. The one sentence still contradicted after the third pass (article
10: which step's follow-up delay is used) was corrected with the checker's
exact wording, the same convention as the 2026-10-11 pass.

| Pass | Scope | Sentences | Supported | Unsupported | Contradicted |
|---|---|---|---|---|---|
| 1 | 31, 32, 24 (new sections), 03 (new section) | 106 | 103 | 0 | 3 |
| 1 | 33, 34, 06 (whole) | 153 | 150 | 0 | 3 |
| 1 | 35, 10 (whole), 13 (edited), 22 (edited) | 140 | 133 | 0 | 7 |
| 1 | 36, 37, 27 (edited) | 135 | 129 | 0 | 6 |
| 1 | 38, 39, 44, 29 (edited), 30 (edited) | 136 | 131 | 0 | 5 |
| 1 | 40, 41 | 84 | 82 | 0 | 2 |
| 1 | 42, 43 | 103 | 96 | 1 | 6 |
| 2 | 43 (whole, rewritten) + every fixed sentence in 31, 32, 36–39, 41, 42, 44, 03 | 84 | 83 | 0 | 1 |
| 2 | fixed sentences in 06, 09, 10, 33, 34, 35 | 24 | 22 | 0 | 2 |
| 3 | last fixes in 10 and 43 | 9 | 8 | 0 | 1 → fixed with the checker's wording |

First pass: 857 sentences, 1 unsupported and 32 contradicted; all 33 fixed.
Final state: 0 unsupported, 0 contradicted.

Cross-article consistency fixed on the way: articles 06, 09 and 10 said
Apollo/Hunter, Gmail and WhatsApp were "not yet verified live"; the founders
confirmed all four as working end to end on 2026-10-13
(`docs/program/ai-visibility/REPORT.md` Q6a/Q6b, `frontend/src/content/product-facts.json`),
so all articles now say that, with the remaining code TODO markers noted.
Article 13 said Vectorae never replies automatically, which Reply Copilot
contradicts; article 22 described online checkout as available although it is
simulated only; articles 27, 29 and 30 gave the code default for the support
chat limit (20) while `render.yaml` sets 30 on the hosted service.

Article 16 said the CRM option pushes "every verified lead"; the code also pushes contacted leads (`app/services/crm_sync.py:67`, `EARLY = {"verified", "contacted"}`), found by the article 36 writer and corrected against that line.

The per-pass reports follow verbatim.


---

## Report: 31-32-24-03

I checked all four articles. Every cited source path exists, including the docs/help-center links. I found no unsupported sentences. Article 32 has three contradictions, all about which refusal message appears, not about what is allowed. Articles 31, 24 and 03 are clean, apart from two wording nuances. No sentence goes against D1: the articles say automatic sending waits for each day's approval (default on), and nothing says research runs per prospect.

Notes:
- UI labels were checked against frontend/src only. I left out frontend/src/content/help-center, which holds copies of these articles.
- Campaigns tab names and Settings tab names are lowercase keys shown through CSS `capitalize` (campaigns/page.tsx:370,423; settings/page.tsx:521). So "Overview", "Review", "Integrations" and "Deliverability" are what users see.
- I had no shell, so I could not diff article 24. I checked its two named sections plus the new Related link.

### 31-guide-solo-founder.md
| # | Sentence | Verdict | Evidence |
|---|---|---|---|
| 1 | Go to **Strategies**, press **New strategy** | supported | frontend/src/app/(app)/strategies/page.tsx:25 |
| 2 | choose **A product** or **A skill / service** | supported | frontend/src/app/(app)/strategies/new/page.tsx:106 |
| 3 | Every time you complete that form, Vectorae creates a new product and a new strategy | supported | strategies/new/page.tsx:54-62 (createProduct then createStrategy) |
| 4 | The Free plan allows 3 strategies | supported | app/core/plans.py:64 |
| 5 | verify your phone (launching outreach needs it) | supported | app/api/sequences.py:441 |
| 6 | connect Gmail under **Settings**, **Integrations** tab | supported | frontend/src/lib/settings-tabs.ts:16; settings/page.tsx:300-326 |
| 7 | wait for `verified`, then **1. Find leads** and **2. Write the email and launch** | supported | frontend/src/components/strategy/OutreachPanel.tsx:93,108,168 |
| 8 | Your own workspace is created for you automatically | supported | app/services/workspaces.py:67-84 |
| 9 | **Workspace** switcher only appears once you belong to a second workspace | supported | frontend/src/components/shell/WorkspaceSwitcher.tsx:15 |
| 10 | Team approvals only apply to people you invite with the SDR role | supported | app/api/sequences.py:491 |
| 11 | As the owner, your own launches never wait for approval | supported | app/api/sequences.py:491 |
| 12 | Vectorae sends nothing automatically until you approve the day | supported | app/services/daily_send_approval.py:1-20; on by default at app/services/system_settings.py:406 |
| 13 | A banner on every page shows today's queued counts | supported, with a caveat | Shell.tsx:167; SendApprovalBanner.tsx:24,34. The banner only shows while automatic messages are waiting, and is hidden on /send-approval itself |
| 14 | tick the channels, **Approve selected channels for today** / **Decline for today** | supported | frontend/src/app/(app)/send-approval/page.tsx:129,181,184 |
| 15 | Inbox **Needs reply**: replies from real people, oldest first | supported | app/services/inbox.py:48,143-148 |
| 16 | press **Mark handled** | supported | frontend/src/app/(app)/inbox/page.tsx:193 |
| 17 | **Overdue** badge after more than two days | supported | frontend/src/lib/inbox.ts:87-90; inbox/page.tsx:148 |
| 18 | Review tab holds objections, stalled deals, executive titles, flagged copy | supported | frontend/src/lib/sendReview.ts:4; campaigns/page.tsx:370,516 |
| 19 | Filter on **Pending**, then approve, edit or reject | supported | ReviewQueuePanel.tsx:60-64,140-194 |
| 20 | Pending for more than 3 days shows **Going stale** | supported | sendReview.ts:84-87; ReviewQueuePanel.tsx:121 |
| 21 | **Mailbox health** card shows throttled or paused mailboxes | supported | MailboxHealthCard.tsx:67-70; settings/page.tsx:545 |
| 22 | A paused mailbox stays paused until you press **Resume** | supported | app/services/mailbox_health.py:377; MailboxHealthCard.tsx:127-130 |
| 23 | Each card on **Strategies** shows the strategy's status | supported | strategies/page.tsx:39 |
| 24 | `researching`/`verifying` = still working; `needs_human_review`, `budget_exhausted`, `failed` = waiting for you | supported | frontend/src/lib/api/types.ts:267-273; lib/api/hooks.ts:26. `pending` is not mentioned |
| 25 | **Overview** tab shows "Campaign paused" if Vectorae paused it (e.g. high bounce rate) | supported | campaigns/page.tsx:438-448 |
| 26 | Vectorae does not measure how long the daily check takes | supported (no such metric found) | — |
| 27 | Research and verification run on the servers, so you can close the tab | supported | app/api/strategies.py:1,145 (pipeline enqueued) |
| 28 | Sending, follow-ups and reply checks run on a server schedule | supported | app/workers/celery_app.py:271,275,304 |
| 29 | Automatic messages stay queued until approved; not failed or deleted | supported | daily_send_approval.py:9-13 |
| 30 | Held messages stay under **Pending**; replies stay under **Needs reply** until marked handled | supported | sendReview.ts:84-90; inbox.py:143,187 |
| 31 | **Pipeline health** card: score out of 100, band, message, four parts | supported | PipelineHealthCard.tsx:12-41; strategies/detail/page.tsx:138-142 |
| 32 | Lead freshness falls as your newest lead gets older | supported | app/services/pipeline_health.py:11,63,112 |
| 33 | Analytics: reply quality (raw next to positive), "What earned the outcomes", "How you compare" | supported | ReplyQualityPanel.tsx:41-53; AttributionPanel.tsx:70; BenchmarkPanel.tsx:44 |
| 34 | **Revenue & ROI** shows what the campaign brought in | supported | analytics/revenue/page.tsx:3-8,86 |
| 35 | **Email health** card: SPF/DKIM/DMARC/blocklisting; **Run check now** | supported | DeliverabilityCard.tsx:56,70-73,110-118 |
| 36 | Inbox **Cleared** filter; **Put back** returns a thread | supported | inbox/page.tsx:48,198,216 |
| 37 | plan's daily AI limit and strategy count | supported | plans.py:64-65; app/api/strategies.py:122 |

Summary: 37 supported, 0 unsupported, 0 contradicted.

### 32-guide-sdr-team-member.md
| # | Sentence | Verdict | Evidence |
|---|---|---|---|
| 1 | Open the link while signed in with the invited address | supported | app/services/workspaces.py:275-277 |
| 2 | **Workspace invitation** page says "You joined [workspace] as sdr." and switches you in | supported | frontend/src/app/(app)/invite/page.tsx:28-29,37 |
| 3 | Error texts "This invitation was sent to a different email address." / "invitation expired -- ask for a new one" / "invitation already used" | supported | workspaces.py:272,274,277; shown via ApiError.message (lib/api/client.ts:64) |
| 4 | Switcher in the top bar lists every workspace with your role, including your own | supported | workspaces.py:113-124; WorkspaceSwitcher.tsx:34-37; Shell.tsx:162; workspace.ts:47-52 |
| 5 | Choosing one reloads the page | supported | WorkspaceSwitcher.tsx:31 |
| 6 | Remembered in that browser only; elsewhere you start in your own workspace | supported | frontend/src/lib/workspace.ts:3-26; WorkspaceSwitcher.tsx:18 |
| 7 | **Team** page shows "you are SDR" | supported | team/page.tsx:47 |
| 8 | The menu is the same for every role; you can read every screen | supported | nav.ts:26-64; Shell.tsx:120 (no role filter); rbac.py:54 (GET always allowed) |
| 9 | The server checks each change against your role | supported | app/services/auth.py:338; rbac.py:52-67 |
| 10 | SDR can work leads, sequences, deals, meetings and launch campaigns | supported | rbac.py:10-12,38-41 |
| 11 | SDR can approve/edit/reject held messages and Mark handled | supported | no role check in app/api/send_reviews.py or app/api/inbox.py:74,94; not in SDR_BLOCKED_PREFIXES |
| 12 | SDR sees member list and **Approvals**, but not **Invite** card or **Approve**/**Decline** | supported | team/page.tsx:55-56,158,269 |
| 13 | **Settings** and **White label** tabs are owner-only | supported | team/page.tsx:57-58 |
| 14 | Delete row: "Deleting needs a manager in this workspace." | supported | rbac.py:60-62; pipeline/page.tsx:129 |
| 15 | Integrations row: connecting, pausing **or removing** a LinkedIn account gives "Integrations, webhooks, costs and pilots need a manager." | contradicted (in part) | Removing is `DELETE /integrations/linkedin/accounts/{id}` (linkedin.py:208). rbac.py:60 checks DELETE before the blocked-prefix check (rbac.py:63-65), so removal returns "Deleting needs a manager in this workspace." Connecting and pausing do get the integrations message |
| 16 | "Approving automatic sending needs an owner or manager in this workspace." | supported | app/api/send_approval.py:55-56 |
| 17 | Autopilot on **or off**: "Turning on Autopilot needs the account owner or a workspace manager: …" | supported | app/api/autopilot.py:34-35,111-112 |
| 18 | "Overriding a review needs a manager." | supported | app/api/sequence_reviews.py:62 |
| 19 | "Approving a launch needs a manager." | supported | app/api/sequences.py:530 |
| 20 | **Distribute to SDRs**: "Distributing leads needs a manager in this workspace." | supported | GridToolbar.tsx:473; app/api/crm.py:525 |
| 21 | Clients **and their domains**: "Managing clients needs a manager in this workspace." | contradicted (in part) | True for add/edit/add-domain (client_workspaces.py:96,122,145,186). Removing a domain is `DELETE /clients/{id}/domains/{domain}` (client_workspaces.py:195), which rbac.py:60-62 refuses first with "Deleting needs a manager in this workspace." |
| 22 | "Changing the spend cap needs an owner or manager." | supported | app/api/spend_guard.py:146 |
| 23 | "Inviting people needs a manager or above." | supported | built from the f-string at app/services/workspaces.py:147 and :200 |
| 24 | On **Pipeline**, a refused delete only says "Could not delete lead" | supported | pipeline/page.tsx:80-81 |
| 25 | Send-approval page: "Only a workspace owner or manager can approve or decline automatic sending." | supported | send-approval/page.tsx:190 |
| 26 | Approval is required unless the owner switched it off | supported | app/db/models.py:3598-3599 (default True) |
| 27 | Launch shows "Sent to a manager for approval. Nothing is sent until they approve." | supported | OutreachPanel.tsx:84-85 |
| 28 | Nothing is enrolled or scheduled yet | supported | sequences.py:432-434,525 |
| 29 | Owner and managers get "Campaign awaiting approval" | supported | sequences.py:517-520; workspaces.py:139-142 |
| 30 | A blocked pre-send review refuses the request itself; only owner/manager can override | supported | sequences.py:445-448; sequence_reviews.py:61-62 |
| 31 | Phone check at launch is on the owner's account | supported | sequences.py:441 + auth.py:339-342 (current_user is the owner) |
| 32 | Decision notice "Campaign approved"/"Campaign declined" with the note | supported | sequences.py:538-543 |
| 33 | Declined goes back to draft and is listed as "Declined" with the note under Approvals | supported | sequences.py:623-624,654; team/page.tsx:263,267 |
| 34 | Once approved, later launches don't ask again; with approval off they go straight out | supported | sequences.py:491,495 |
| 35 | Viewer: **every change** is refused with "Viewers have read-only access to this workspace." | contradicted (minor) | rbac.py:56-58 covers data routes. But `/workspaces` and `/branding` are personal prefixes (rbac.py:30-31), so rbac never runs on them. A viewer can leave the workspace (workspaces.py:180-185), and invite attempts get "Inviting people needs a manager or above." |
| 36 | Viewer cannot approve a held message, mark a thread handled or edit a lead | supported | rbac.py:56-58 |
| 37 | Personal pages always use your own account (profile/password, devices, support, tutorials, onboarding, billing) | supported | rbac.py:30-36; auth.py:331; lib/api/profile.ts:10-28 |
| 38 | Owner can change any member's role; a manager can change SDRs and viewers | supported | workspaces.py:150-156 |

Summary: 35 supported, 0 unsupported, 3 contradicted.

### 24-workspaces-and-agency-mode.md (only the two sections and the new Related link)
| # | Sentence | Verdict | Evidence |
|---|---|---|---|
| 1 | A client is a record, not a login; no role limits someone to one client | supported | app/db/models.py:3618-3631; rbac.py:24 |
| 2 | Invite the client as a Viewer (**Team** › **Members** › **Invite**) | supported | team/page.tsx:55,160 |
| 3 | A viewer reads everything, including other clients, but changes nothing | supported | rbac.py:54-58; app/api/client_workspaces.py:99-115 (no role check on GET) |
| 4 | Client creates own account (workspace automatic) and invites you, e.g. as Manager | supported | workspaces.py:67-84,194-202 |
| 5 | You then pick their workspace with the switcher; their data, Gmail and plan are theirs | supported | auth.py:333-342; WorkspaceSwitcher.tsx |
| 6 | **Clients** page features belong to your workspace and do not follow you | supported | client_workspaces.py:16-19,77-78; services/client_workspaces.py:129-142 |
| 7 | No per-client plans or limits | supported | models.py:3638-3666 (no limit columns) |
| 8 | Plan limits are counted over the whole account | supported | plans.py:45-47,225-238 |
| 9 | Retainer and per-meeting fee are what you charge; Vectorae does not bill them | supported | services/client_workspaces.py:310-354 (view only); no client billing in app/services/billing.py |
| 10 | Row shows **Sent**, **Reply rate**, **Meetings**, **Revenue** (won deals) | supported | clients/page.tsx:170-174; services/client_workspaces.py:286-289 |
| 11 | All time, no date filter | supported | services/client_workspaces.py:396 (report called with no dates) |
| 12 | Reply rate shows "—" until something is sent | supported | services/client_workspaces.py:303; lib/clients.ts:82-83 |
| 13 | Invoice counts meetings from the first day of the current month | supported | services/client_workspaces.py:319,328 |
| 14 | No export or share link for a client report in the web app | supported (by absence) | clients/page.tsx (none present) |
| 15 | Web form sets only name and monthly retainer | supported | clients/page.tsx:58-61,90-97 |
| 16 | Per-meeting fee, currency (USD default), contact/billing, pause/archive are API-only | supported | api/client_workspaces.py:40-63; models.py:3660-3661 |
| 17 | Marking a client paused does not pause its campaigns; use **Pause campaign** | supported | client status is not read in app/workers/outreach_tasks.py:708-710; campaigns/page.tsx:495 |
| 18 | Related: link to 32-guide-sdr-team-member.md | supported (file exists) | docs/help-center/32-guide-sdr-team-member.md |

Summary: 18 supported, 0 unsupported, 0 contradicted.

### 03-getting-started.md (only "What should I do in my first week?")
| # | Sentence | Verdict | Evidence |
|---|---|---|---|
| 1 | Verify email from the **Check your email** screen | supported | frontend/src/app/(auth)/check-email/page.tsx:74 |
| 2 | **Do this later**; phone needed before launching outreach | supported | onboarding/verify/page.tsx:274; app/api/sequences.py:441 |
| 3 | Choose a plan on **Pricing**, or stay within Free limits | supported | pricing/PricingClient.tsx:178; plans.py:63-77 |
| 4 | Connect Gmail: **Settings**, **Integrations** tab | supported | settings-tabs.ts:16; settings/page.tsx:300-326 |
| 5 | **Settings**, **Deliverability** tab, **Email health** card | supported | settings-tabs.ts:17; DeliverabilityCard.tsx:110 |
| 6 | **Calendar** › **Weekly availability**, then **Booking pages** | supported | calendar/page.tsx:133,157; calendar/booking-pages/page.tsx:102 |
| 7 | **Strategies**, **New strategy** | supported | strategies/page.tsx:25 |
| 8 | If `needs_human_review`, use **Re-verify** or pass failed checks manually | supported | ReverifyStrategyButton.tsx:55; strategies/detail/page.tsx:114-128 |
| 9 | **1. Find leads** card; start small | supported | OutreachPanel.tsx:108,113 |
| 10 | Launch from **2. Write the email and launch** | supported | OutreachPanel.tsx:168 |
| 11 | Approve on **Today's automatic sending**; held messages in **Campaigns**, **Review** tab | supported | send-approval/page.tsx:49; campaigns/page.tsx:370,516 |
| 12 | **Inbox** (**Needs reply**) | supported | inbox/page.tsx:46 |
| 13 | When they book, the lead becomes **Meeting booked** | supported, with a caveat | app/workers/calendar_tasks.py:179-182 sets status `meeting_booked`, but only if the booking is linked to a lead. The label "Meeting booked" exists (conversation.ts:76, attribution.ts:41), but the Pipeline column says "Booked" (pipeline/page.tsx:29) |

Summary: 13 supported, 0 unsupported, 0 contradicted.

### Fixes needed in /home/user/LeadPilot/docs/help-center/32-guide-sdr-team-member.md
1. Integrations row (line 68): say that removing a LinkedIn account gets "Deleting needs a manager in this workspace.", or drop "removing" from the example.
2. Clients row (line 74): say that removing (releasing) a reserved domain gets the "Deleting needs a manager…" message.
3. Viewer section (line 90): soften "every change is refused with …". Workspace-membership actions (`/workspaces`, `/branding`) skip that check: a viewer can still leave the workspace, and invite attempts get a different message.

Optional wording tweaks: in 31-guide-solo-founder.md line 63, say the banner only appears while automatic messages are waiting. In 03-getting-started.md line 144, mention that Pipeline labels the stage "Booked".

---

## Report: 33-34-06

I checked all three help-center articles against the code. Every cited `sources` path exists: 24 files for article 33, 27 for article 34 and 35 for article 06, with none missing. Out of 154 product claims, 151 are supported, none are unsupported and 3 are contradicted. No UI label or number was wrong. Each contradiction is an edge case or a feature behind a flag, but each would give a customer a wrong answer.

The 3 contradictions:
1. **33, #11**: the article says past clients can't be changed after a strategy is created. In fact `POST /products/{id}/past-clients` can still add more, and later research steps read them.
2. **34, #10**: the article says the tactic half is empty when classification fails. The flow type is still added, so it is not empty.
3. **06, #58**: the article says leads come only from sourcing. A local business with win-back turned on can import its own customers as leads through the API.

Abbreviations in the tables: `s/` = `app/services/`, `api/` = `app/api/`, `w/` = `app/workers/`, `fe/` = `frontend/src/`.

### 33-product-profile-and-icp.md
| # | Sentence (verbatim, may be shortened with …) | Verdict | Evidence (path:line) / what the code says |
|---|---|---|---|
| 1 | Everything Vectorae researches … starts from what you type into the **New strategy** form | supported | app/pipeline/engine.py:77-83, 170-173 |
| 2 | The first step of **New strategy**, **What do you want clients for?** | supported | fe/app/(app)/strategies/new/page.tsx:84, 88 |
| 3 | **Name**: required, up to 200 characters | supported | api/schemas.py:20; fe/components/intake/wizard.ts:71 (the 200 limit is server-side only; the Input has no maxLength) |
| 4 | **Describe the product or skill**: required, no length limit; hint "What it does, who it's for, what it costs…" | supported | api/schemas.py:21; new/page.tsx:96-98 |
| 5 | **A product** or **A skill / service** | supported | new/page.tsx:106 |
| 6 | **Is this a local business?**: **No** by default; business type adds City or neighbourhood, Postcode (optional), Country (2 letters), Radius, What you offer business buyers (optional) | supported | new/page.tsx:111-165; fe/lib/localBusiness.ts:51-52 |
| 7 | **Yes — build on proven patterns** … **Client details** ("Industry, size…") and **How were they acquired?** ("Referral?…") | supported | new/page.tsx:180-226 (card title is "Past client #N") |
| 8 | Both are required for every client you add | supported | wizard.ts:77-82; api/schemas.py:44-45 |
| 9 | Through the API, up to 50 past clients in one request | supported | api/schemas.py:49 |
| 10 | There is no form for typing an ICP directly | supported | No ICP input anywhere in fe/; the API accepts `icp_criteria` only per sourcing request (api/schemas.py:189) |
| 11 | Once a strategy is created, its name, description and past clients cannot be edited, in the app or through the API | **contradicted (partly)** | Name and description: there is no update route, so that part is true. Past clients: `POST /products/{id}/past-clients` (api/products.py:118-155) has no strategy check and can add clients at any time. Research steps read past clients when each step runs (engine.py:89-94), so a resumed run would include them. |
| 12 | With no past clients, your description is the only thing Vectorae knows about your offer | supported | engine.py:82, 87-88 |
| 13 | Every one of the research steps receives the same three lines: name, type, description | supported | engine.py:82 (for a local business a LOCAL BUSINESS CONTEXT block is added, :83) |
| 14 | AI turns each client's two boxes into seven fields (industry … sales cycle length) | supported | s/pattern_recognition.py:16-24, 32-53 |
| 15 | Anything not stated or safely inferable is left empty | supported | s/pattern_recognition.py:33 |
| 16 | The research steps see only these seven fields, not your original text | supported | engine.py:94 (the stored dict can also hold a `confidence` map, s/pattern_recognition.py:75-76) |
| 17 | If extraction fails, clients still saved, fields unknown, strategy still launches | supported | s/pattern_recognition.py:59-72; api/products.py:131-134 |
| 18 | First two phases cover core offering, problem/cost of inaction, pricing logic, firmographics, personas, decision-makers, pain points, triggers, disqualifiers | supported | app/pipeline/registry.py:57-79 |
| 19 | What you say about yourself is not checked by Vectorae's claim check | supported (caveat) | s/claim_verification.py:26-30. When F05 Guardrails Studio is on, proof claims about the sender are checked against the approved-claims library (s/claim_verification.py:497-529) |
| 20 | Phase 2 is ICP definition, phase 3 market sizing and segmentation | supported | registry.py:69-89 |
| 21 | AI extracts five lists of search criteria | supported | s/icp_extraction.py:26, 73-85, 88-115 |
| 22 | Table: titles / industries / locations / size ranges "such as 11 to 50" / keywords "3 to 8" | supported | s/icp_extraction.py:77-81 |
| 23 | For a local business locations replaced by service area (radius not sent) | supported | s/local_business.py:430-460 (explicit API criteria that include locations keep them, :447) |
| 24 | The app does not show these lists for a normal strategy | supported | No `icp_criteria` rendering in fe/; only Quickstart shows "Looking for:" |
| 25 | **View documents**; ICP definition is one of the phase summaries | supported | fe/app/(app)/strategies/detail/page.tsx:97; engine.py:256-258; registry.py:78 |
| 26 | API lead-sourcing request can pass its own `icp_criteria` with these five keys | supported | api/schemas.py:189-192; api/leads.py:109-113 |
| 27 | Each **Find leads** extracts criteria again from phase 2 and 3 research | supported | api/leads.py:114-115; s/icp_extraction.py:88-98 |
| 28 | This is an AI call that counts toward your daily AI limit | supported | api/leads.py:107-108 |
| 29 | Criteria become the people search sent to the lead provider | supported | app/integrations/apollo.py:24-49 |
| 30 | First time criteria exist (research finish, or first Find leads) they are fixed as pattern key | supported | w/tasks.py:126-148; api/leads.py:117-120; s/icp_extraction.py:269-270 (Autopilot can also set it: s/autopilot.py:463-464) |
| 31 | That key does not change afterwards | supported (caveat) | s/icp_extraction.py:269-270. The operator script scripts/backfill_pattern_key.py:110 can rewrite it |
| 32 | AI booking likelihood: Role seniority 25%, Industry fit 25%, Email verification 20%, Company signals 15%, Past campaign results 15% | supported | s/lead_scoring.py:42-43; fe/lib/lead-score.ts:24-28; leads/detail/page.tsx:173 |
| 33 | AI reviews against product name, description and ICP, moves score at most 20 points | supported | s/lead_scoring.py:40, 191, 218, 238-239 |
| 34 | F-P-T-A (Fit, Problem, Timing, Access); AI sees same product and ICP; at most 15 points per dimension | supported | s/fpta_scoring.py:1, 50, 57, 362, 393-403 |
| 35 | Known limitation: baseline does not read the ICP's industries, keywords or size ranges | supported | s/lead_scoring.py:215 and s/fpta_scoring.py:393 pass `pattern_inputs_json`, which is nested `{"icp":…, "tactics":…}` (s/icp_extraction.py:214-222), so `icp.get("industries")` etc. return None |
| 36 | **Industry fit** therefore shows 50% for every lead | supported | s/lead_scoring.py:87-88; lead-score.ts:38 |
| 37 | F-P-T-A Fit never reports a company-size match | supported | s/fpta_scoring.py:169-179 |
| 38 | Your ICP reaches these scores only through the AI review step | supported | s/lead_scoring.py:191; s/fpta_scoring.py:403 |
| 39 | Quickstart off by default; **Strategies** page shows a **Quickstart** button | supported | s/system_settings.py:306; fe/app/(app)/strategies/page.tsx:14-23 |
| 40 | **Website**, **Your offer, in one line** (10 to 300 characters), optional **Product name** | supported | quickstart/page.tsx:129-146; fe/lib/quickstart.ts:57-58 (actual label is "Product name (optional)". The minimum of 10 is UI-only; api/quickstart.py:47 accepts min 1, and the service caps at 300, s/quickstart.py:44, 124) |
| 41 | Reads website, works out who buys, up to 25 verified leads by default, first draft to each, while full research runs | supported | s/system_settings.py:306-311; quickstart/page.tsx:115; s/quickstart.py:371-376 (25 is the sourcing target, capped by plan) |
| 42 | The run shows the ICP as "Looking for:" | supported | quickstart/page.tsx:240 |
| 43 | Drafts review only: copy or discard, nothing is sent | supported | quickstart/page.tsx:175-177, 260-268; s/system_settings.py:304-305 |
| 44 | Outreach still goes through the verified strategy | supported | quickstart/page.tsx:176 |

Summary: 43 supported, 0 unsupported, 1 contradicted.

### 34-strategy-patterns-and-playbooks.md
| # | Sentence | Verdict | Evidence |
|---|---|---|---|
| 1 | Vectorae groups strategies aiming at same buyer with same outreach, keeps running score | supported | s/icp_extraction.py:28-41, 236-249 |
| 2 | 64-character code (a SHA-256 hash) built from two halves | supported | s/icp_extraction.py:214-233 |
| 3 | ICP half = five lists; lower-cased, de-duplicated, sorted | supported | s/icp_extraction.py:199-215 |
| 4 | Tactic half classified by AI from phase 5 and phase 8, fixed values | supported | s/icp_extraction.py:134-149 |
| 5 | Channels: email, whatsapp, linkedin, phone, referral, inbound | supported | s/icp_extraction.py:42 |
| 6 | Sales motion: cold_outbound … partner_led | supported | s/icp_extraction.py:43 |
| 7 | Cadence: light (≤3), standard (4-6), aggressive (7+) | supported | s/icp_extraction.py:44, 60-61 (the touch counts are prompt guidance to the AI) |
| 8 | Flow type: past clients vs from scratch | supported | s/icp_extraction.py:201-203, 273-274 |
| 9 | An answer outside these lists is dropped | supported | s/icp_extraction.py:172-187 |
| 10 | If the classification fails, the tactic half is simply empty | **contradicted** | Channels, motion and cadence come back empty (s/icp_extraction.py:167-170), but `flow_type` is still added (:273-274). The tactic half still holds the flow type. |
| 11 | Identical values share a key; results pooled | supported | s/score_decay.py:142-166 |
| 12 | Key set once, at research finish or first **Find leads** if that failed | supported | w/tasks.py:132-148; api/leads.py:117-120 (Autopilot path too: s/autopilot.py:463-464) |
| 13 | Never changes afterwards, even if later sourcing uses different criteria | supported (caveat) | s/icp_extraction.py:269-270; scripts/backfill_pattern_key.py:110 can rewrite |
| 14 | Exact inputs stored with the strategy, can be audited | supported | s/icp_extraction.py:276-283; app/db/models.py:971-976 |
| 15 | One row per pattern key and variant; no variant = "control" | supported | s/score_decay.py:163-166; models.py:1724 |
| 16 | Recalculated every night from outcomes of every strategy with that key | supported | app/workers/celery_app.py:280-281; s/score_decay.py:142-154 |
| 17 | Reply rate: share of sends to a lead who replied | supported | s/score_decay.py:195-203 |
| 18 | Booking rate: share of sends to a lead who booked | supported | s/score_decay.py:196, 205-210 |
| 19 | Sample size: number of sends counted | supported | s/score_decay.py:221; w/learning_tasks.py:159 |
| 20 | Effective sample size: sends weighted by age | supported | s/score_decay.py:184, 220 |
| 21 | Reliable: effective sample size reached 30 | supported | s/score_decay.py:222; app/core/config.py:142 |
| 22 | Trend: how reply rate moved since previous nightly run | supported | w/learning_tasks.py:158, 171-176 (score = reply_rate) |
| 23 | 90-day half-life; 90 days ago counts half | supported | s/score_decay.py:11, 32; app/core/config.py:156-159 |
| 24 | Matched by lead; 3 emails + 1 reply → all three count | supported | s/score_decay.py:195-201 |
| 25 | Score can include other accounts' strategies with the same key | supported | s/score_decay.py:142-154 (no owner filter); api/admin.py:283-287 |
| 26 | Many old sends can still be unreliable (decayed weight) | supported | s/score_decay.py:14-16 |
| 27 | "new" = first; rising/falling > 0.005; else stable | supported | w/learning_tasks.py:161, 171-176 |
| 28 | Playbook scores not shown on a customer screen yet | supported | Only fe/lib/api/admin.ts:136 calls the scores endpoint |
| 29 | **Analytics** page has **Learning insights** card marked **Coming in M8** | supported (caveat) | analytics/page.tsx:188-200. It sits inside AsyncState (:91-92), so it may not render when there is no analytics data |
| 30 | Plans with playbook access: `GET /playbook/scores` (optional `strategy_id`) | supported | api/playbook.py:106-145; app/core/plans.py:70, 86 |
| 31 | `GET /playbook/subject-patterns` best subject-line styles | supported | api/playbook.py:68-99 |
| 32 | Admins see every score on admin **Playbook Scores** page | supported | fe/app/(admin)/admin/layout.tsx:20; admin/playbook/page.tsx:36; api/admin.py:272-288 (paginated, default 100) |
| 33 | Only two things read them | supported | s/lead_scoring.py:148-158; s/playbook_service.py:33-64 |
| 34 | Phases 6 and 8 get up to 8 reliable scores from your strategies' keys, best booking rate first | supported | engine.py:133-144; s/playbook_service.py:33-64 (falls back to all users' patterns if the owner lookup fails, engine.py:139-143) |
| 35 | Research sees pattern code with rates, sample size, trend, not ICP/tactics | supported | s/playbook_service.py:69-78 |
| 36 | **Past campaign results**: best reliable booking rate; ≥5% full; none = 50%; 15% of score | supported | s/lead_scoring.py:42-43, 148-163 |
| 37 | Nothing in the learning loop changes a running campaign | supported | `default_variant` is read only by s/crm_service.py:545-552. The docstring at s/ab_testing.py:24 says it "affects future message rendering", but no code does this |
| 38 | `ab_auto_promotion_enabled` off by default; founder decision 2026-10-11 keeps it off | supported | s/system_settings.py:224; docs/program/DECISIONS.md:23 |
| 39 | Promotion is permanent; variants are labels, not random groups | supported | w/learning_tasks.py:201-202; DECISIONS.md:23 |
| 40 | When on, only records winner on strategy; CRM campaigns dashboard marks "promoted winner"; sequences unchanged | supported | w/learning_tasks.py:256-260; fe/app/(app)/crm/dashboard/campaigns/page.tsx:244-247 |
| 41 | Does not change step briefs, messages, variant assignment, pattern key | supported | w/learning_tasks.py:192-271 writes only `default_variant` and the marker |
| 42 | The learning loop does not choose or reuse opening lines | supported (caveat) | No direct path. Playbook insights do feed phase 6, which includes "Subject lines & openers bank" (registry.py:117; engine.py:136) |
| 43 | Opener replaced with "I wanted to reach out to you at {company} directly." / "…to you directly." | supported | s/claim_verification.py:308-311, 374-380 |
| 44 | Unsupported subject becomes "Quick question" | supported | s/claim_verification.py:62, 477, 510-516 |
| 45 | **Claim checks** tab shows verdict "rewritten" | supported | leads/detail/page.tsx:61; fe/components/leads/ClaimChecksPanel.tsx:55; s/claim_verification.py:61 |
| 46 | First line references posts only when stored, news only when recent | supported | s/personalization_context.py:19-22, 139-148 |
| 47 | **Personalization** tab | supported | leads/detail/page.tsx:56 |
| 48 | Every email in a step uses the same brief | supported | fe/lib/leadOutreach.ts:43-53 |

(Skipped: "Prefer booking rate over reply rate…", which is advice.)

Summary: 47 supported, 0 unsupported, 1 contradicted.

### 06-lead-sourcing-and-email-verification.md
| # | Sentence | Verdict | Evidence |
|---|---|---|---|
| 1 | Once verified, finds people, looks up emails, checks them | supported | api/leads.py:76-92; w/lead_tasks.py:3-4 |
| 2 | **1. Find leads** card, **How many leads** (1 to 25; starts at 5), **Find leads** | supported | fe/components/strategy/OutreachPanel.tsx:108, 117, 127; leadOutreach.ts:10-11 (label is "How many leads (1 to 25)") |
| 3 | Shows "Finding leads. This takes a few minutes."; list fills in | supported | OutreachPanel.tsx:45-48, 55 |
| 4 | Refused if status not `verified` | supported | api/leads.py:85-92 |
| 5 | Search from titles, industries, locations, size ranges, keywords | supported | api/leads.py:115; apollo.py:24-49 |
| 6 | Local: location is city or postcode; radius not sent | supported | s/local_business.py:346-351, 447-459 |
| 7 | API up to 1,000; one run capped at 200 by default | supported | api/schemas.py:187; app/config.py:88; api/leads.py:122-124; apollo.py:77 |
| 8 | 5 sourcing requests per hour by default | supported | app/core/config.py:200; api/leads.py:82; app/core/rate_limiting.py:235 |
| 9 | Paid Apollo/Hunter credits; screen suggests starting small | supported | OutreachPanel.tsx:113 |
| 10 | Keys set by admin on the server; not entered in app | supported | apollo.py:59; app/integrations/hunter.py:41; app/core/config.py:83 |
| 11 | Settings → **Integrations**: **Apollo.io**/**Hunter.io** cards masked or "Key not set"; **Test** | supported | settings/page.tsx:359-385, 519-521; fe/lib/settings-tabs.ts:16 |
| 12 | Paid: Apollo search (1 credit per person requested), each enrichment, each Hunter search and check | supported | apollo.py:88-94, 122-127; hunter.py:58-73; app/integrations/plumbing.py:195, 208-212 |
| 13 | Search cached 1 day; enrichment/email-finding/check 30 days; cached repeat free | supported | app/config.py:80-81; plumbing.py:200-205 |
| 14 | Spend Guard → **Usage & spend** (from **Analytics**) shows **Data credits**, dollars once price set | supported | analytics/page.tsx:85-88; fe/components/analytics/SpendGuardPanel.tsx:77-86, 132-133, 158-164; s/system_settings.py:345 |
| 15 | Owner or manager sets **Monthly spend cap**; refused before start; stops before next paid call | supported | SpendGuardPanel.tsx:170, 187-190; w/lead_tasks.py:663-678 |
| 16 | Five stages in order | supported | w/lead_tasks.py:716-724 |
| 17 | Sourcing: Apollo searched | supported | apollo.py:75-106 |
| 18 | Enriching: name, title, company, domain, email, phone, LinkedIn; keeps existing; locked email = missing | supported | apollo.py:19-21, 128-139, 157-159; w/lead_tasks.py:305-334 |
| 19 | Finding emails: Hunter from name + domain; none → dropped | supported | w/lead_tasks.py:385-402; hunter.py:53-64 |
| 20 | Verifying: Hunter checks every address | supported | w/lead_tasks.py:440-478 |
| 21 | Finalizing: counts recorded, AI booking-likelihood score | supported | w/lead_tasks.py:599-619 |
| 22 | Saved per stage; resumes without duplicates | supported | w/lead_tasks.py:6-10, 260, 350, 471 |
| 23 | Never same person twice (email or provider record); DB enforces; can be in two strategies | supported | app/db/models.py:1147-1148; w/lead_tasks.py:157-170 |
| 24 | `sourced` found by search | supported | models.py:100 |
| 25 | `enriched` details added | supported | models.py:101 |
| 26 | `email_found` has unchecked address | supported | models.py:102; w/lead_tasks.py:387, 417 |
| 27 | `verified` = deliverable | supported | app/integrations/base.py:73 |
| 28 | `flagged` = risky or could not tell | supported | base.py:74-76 |
| 29 | `dropped` = undeliverable, suppressed, no email, duplicate, removed, erased | supported (incomplete) | w/lead_tasks.py:317-322, 396-433; api/leads.py:399. Also dropped when on an exclusion list (lead_tasks.py:319-322, 406-411), which the table does not mention |
| 30 | `contacted` at least one message sent | supported | w/outreach_tasks.py:1039-1040 |
| 31 | `replied` | supported | models.py:108 |
| 32 | `meeting_booked` | supported | models.py:109 |
| 33 | "verified" = Hunter returned deliverable at the time of the check | supported | hunter.py:66-83 |
| 34 | Apollo's label never the verdict; every address goes through Hunter | supported | w/lead_tasks.py:440-458; s/waterfall_enrichment.py:1-9 |
| 35 | Risky and could-not-judge → `flagged` | supported | base.py:71-77 |
| 36 | Stores verdict and confidence score, not the reason | supported (caveat) | w/lead_tasks.py:460-463. With the waterfall on, a `catch_all` verdict is stored (s/waterfall_enrichment.py:360-372), which partly explains a flag |
| 37 | Waterfall on: catch-all → `flagged` even if Hunter said valid | supported | s/waterfall_enrichment.py:54, 67, 132-157 |
| 38 | Move flagged↔verified on **Pipeline** board | supported | api/ui_support.py:53-54; fe/lib/api/leads.ts:42-43; pipeline/page.tsx:25-26 |
| 39 | Undeliverable dropped, never enrolled; only `verified` enrollable; API other status refused | supported | s/sequence_engine.py:90; api/sequences.py:151-168 |
| 40 | Hunter-built address recorded as found that way | supported | w/lead_tasks.py:418-425 |
| 41 | Launch enrolls only verified leads with email; form says how many | supported | s/sequence_engine.py:90, 325; OutreachPanel.tsx:177-178, 210 |
| 42 | Added on unsubscribe, stop reply, WhatsApp STOP, erase | supported | api/unsubscribe.py:52; s/sequence_engine.py:712-729; api/webhooks_whatsapp.py:372; api/leads.py:337-373 |
| 43 | Covers email, phone, LinkedIn; one channel stops all | supported | w/lead_tasks.py:115-125; s/sequence_engine.py:718-721 |
| 44 | Checked at first found, new email/phone, enrollment, before every send | supported | w/lead_tasks.py:233, 315, 395; s/sequence_engine.py:365; w/outreach_tasks.py:253 |
| 45 | Suppressed lead skipped or dropped, never contacted | supported | same lines |
| 46 | Deployment-wide; admins see **Suppression** tab; others don't | supported | w/lead_tasks.py:126-131; settings-tabs.ts:4-7, 26 |
| 47 | Plan limits leads per strategy; dropped don't count | supported | w/lead_tasks.py:181-187 |
| 48 | Free 100 / Starter 500 / Growth 2,500 / Pay per meeting 1,000 / Scale 10,000 / Pro, Enterprise no limit | supported | app/core/plans.py:66, 82, 100, 115, 133, 148, 169 |
| 49 | Full → refused with upgrade message; nearly full → room left, rechecked per lead | supported | api/leads.py:94-105, 122-124; w/lead_tasks.py:213-229 |
| 50 | **Remove** (verified/flagged) → `dropped`; stops sequences; queued cancelled; due re-checked; cannot move back | supported | OutreachPanel.tsx:61-63, 150-155; api/ui_support.py:55, 135-139; w/outreach_tasks.py:253 |
| 51 | **Delete (GDPR erasure)** on Pipeline: erases data, messages, replies; suppresses email/phone/LinkedIn; never contacted/sourced; record kept; confirm **Delete** | supported | pipeline/page.tsx:128-140; api/leads.py:296-446 (record: :356) |
| 52 | Apollo returns no one: stops at first empty page, no new leads | supported | apollo.py:95-97 |
| 53 | No message says so; list doesn't grow | supported | OutreachPanel.tsx:131-161 |
| 54 | Search uses all criteria; narrow profile → few people | supported | apollo.py:36-49 |
| 55 | Skipped: already in strategy, suppressed, exclusion lists (if admin on), beyond plan limit | supported | w/lead_tasks.py:226-244; s/system_settings.py:270 |
| 56 | Stage errors retried up to 3 times, 30 seconds apart, resume | supported | w/lead_tasks.py:686, 691-712 |
| 57 | Error recorded but not shown in the app | supported (caveat) | w/lead_tasks.py:681-684; LeadBatchOut has no error field (api/schemas.py:195-204). The Quickstart page does show it: quickstart/page.tsx:239 |
| 58 | Not as leads: leads come only from the sourcing process above | **contradicted** | `POST /strategies/{id}/customers/import` (api/local_business.py:88-89; s/local_business.py:63, 790-798) imports a local business's opted-in customers into a strategy as lead rows (`source="customer_import"`). It is API-only and needs `customer_winback_enabled`, default off (s/system_settings.py:458). |
| 59 | Growth/Scale/Pro/Enterprise upload LinkedIn connections on **Network**; they don't become leads | supported | plans.py:183-189; api/linkedin_network.py:35, 70; fe/components/shell/nav.ts:50 |
| 60 | Apollo and Hunter not yet verified against live services | supported | docs/VERIFICATION_REPORT.md:579 |
| 61 | Built from docs, simulated tests, request details marked as needing confirmation, never run end to end | supported | apollo.py:6-8, 42, 45, 55, 64, 90, 113, 124, 145; hunter.py:7-9, 26, 37, 46, 60, 70, 89; VERIFICATION_REPORT.md:579 |

Summary: 60 supported, 0 unsupported, 1 contradicted.

On D1: nothing in the three articles contradicts it. Quickstart drafts are correctly described as review-only, and no article implies that research runs per prospect.

### Other things I found (outside the articles' text)
1. **Product bug behind the 33 #35 limitation.** `s/lead_scoring.py:215` and `s/fpta_scoring.py:393` use `strategy.pattern_inputs_json` as a flat ICP. It is actually nested (`s/icp_extraction.py:214-222`), so Industry fit is always 0.5 and the company-size and keyword signals never fire. I found nothing about this in `docs/program/` (searched for `pattern_inputs_json`/`industry_match`). It should be triaged.
2. **Stale docstring.** `s/ab_testing.py:24` says `default_variant` "affects future message rendering". No code reads it for rendering.
3. **Help Center copies are out of sync.** `/home/user/LeadPilot/frontend/src/content/help-center/06-lead-sourcing-and-email-verification.md` differs from the docs version (for example, its line 51 still has the old caching paragraph), and there is no 33 or 34 copy under `frontend/src/content/help-center/`. If the in-app Help AI reads the frontend copies, it is not using these checked articles.
4. **Weak citation.** `docs/program/BASELINE.md` is cited by article 06 but says nothing about Apollo or Hunter.

Files:
- /home/user/LeadPilot/docs/help-center/33-product-profile-and-icp.md
- /home/user/LeadPilot/docs/help-center/34-strategy-patterns-and-playbooks.md
- /home/user/LeadPilot/docs/help-center/06-lead-sourcing-and-email-verification.md

---

## Report: 35-10-13-22

I checked all four articles. All 70 cited `sources` paths exist. I edited no files.

Totals: 35 has 1 contradicted sentence, 10 has 6, and 13 and 22 have none. Nothing was unsupported.

### 35-google-workspace-dns-setup.md
| # | Sentence (verbatim, may be shortened with …) | Verdict | Evidence (path:line) / what the code says |
|---|---|---|---|
| 1 | If you send from a Gmail address on your own Google Workspace domain, Vectorae checks that domain's SPF, DKIM and DMARC records. | supported | app/services/deliverability.py:3-11,108-120 |
| 2 | Vectorae checks the domain of each connected Gmail address. | supported | deliverability.py:96-105 |
| 3 | Shared domains such as gmail.com are skipped, because their reputation belongs to Google. | supported | deliverability.py:54-56,103 |
| 4 | It reads public DNS TXT records only; it never changes your DNS. | supported (caveat) | deliverability.py:68-75,108-120. Caveat: the same card's blocklist check also does DNS A lookups of `<domain>.dbl.spamhaus.org` etc. and may call MXToolbox (:78-85,126-147). Those are not records on the customer's domain. |
| 5 | SPF row: TXT on the domain, starting `v=spf1` | supported | deliverability.py:109 |
| 6 | DKIM row: `google._domainkey.<domain>`, containing `v=DKIM1` or `p=` | supported | deliverability.py:117-118 |
| 7 | DMARC row: `_dmarc.<domain>`, starting `v=DMARC1`; `p=` read as policy | supported | deliverability.py:110-116 |
| 8 | `google` is the DKIM selector Google Workspace uses by default, and it is the only one the **Email health** card checks. | supported | deliverability.py:117,120; app/services/system_settings.py:130-132 |
| 9 | A DNS lookup that fails, or takes longer than 5 seconds, is treated as "no record". | supported | deliverability.py:72-74 (`lifetime=5`, any exception → `[]`) |
| 10 | You add the records at whoever hosts your domain's DNS; Vectorae cannot do it for you. | supported | Read-only resolver, no DNS write path: deliverability.py:68-85 |
| 11 | Vectorae sends through the Gmail API, so your mail leaves from Google's servers. | supported | app/services/deliverability_autopilot.py:66-68 |
| 12 | Suggestion when SPF is missing: `v=spf1 include:_spf.google.com ~all` | supported | deliverability_autopilot.py:163-166 |
| 13 | If you already have an SPF record … add `include:_spf.google.com` to it instead of creating a second one. | supported | deliverability_autopilot.py:167-170,177-180 |
| 14 | The preflight fails more than one SPF record, SPF not reaching `_spf.google.com`, or more than 10 DNS lookups. | supported | deliverability_autopilot.py:69-70,147-149,167-180 |
| 15 | The **Email health** card … only checks that a `v=spf1` record exists. | supported | deliverability.py:109 |
| 16 | Vectorae's own messages say "Turn on DKIM signing in Google Admin". | supported | deliverability_autopilot.py:206 |
| 17 | Publish the key … at `google._domainkey` … That is where Vectorae looks. | supported | deliverability.py:117; deliverability_autopilot.py:184-186,192 |
| 18 | Another selector → card shows DKIM missing; line reads "DKIM not found under the Google selector" | supported | deliverability.py:177-179; frontend/src/components/settings/DeliverabilityCard.tsx:73,84-87 |
| 19 | An administrator can add your selector to `deliverability_dkim_selectors`, but only the launch preflight reads it. | supported | system_settings.py:130-132; deliverability_autopilot.py:64,396 (the only reader) |
| 20 | An empty `p=` → preflight reports the key as revoked and asks for a new key in Google Admin. | supported | deliverability_autopilot.py:194-203 |
| 21 | Publish `_dmarc` … starting `v=DMARC1` and containing a `p=` policy. | supported | deliverability_autopilot.py:216-237 |
| 22 | Minimum `v=DMARC1; p=none` | supported | deliverability_autopilot.py:227 |
| 23 | `p=none` … domain score still loses 10 points and card shows "DMARC policy is p=none (monitoring only)". | supported | deliverability.py:174-176; DeliverabilityCard.tsx:84-87 |
| 24 | `p=quarantine` or `p=reject` removes that deduction. | supported | deliverability.py:174 |
| 25 | Preflight fails two DMARC records (receivers ignore all) and a `p=` not none/quarantine/reject. | supported | deliverability_autopilot.py:72,228-237 |
| 26 | Card looks only at `_dmarc` on your exact sending domain. | supported | deliverability.py:110 |
| 27 | Preflight also accepts DMARC on the parent domain (last two parts). | supported | deliverability_autopilot.py:210-223 |
| 28 | **Settings** → **Deliverability** tab → **Email health** card; a panel per sending domain. | supported | frontend/src/app/(app)/settings/page.tsx:519-527 (tab name capitalised by CSS),541-546; DeliverabilityCard.tsx:110,125 |
| 29 | "OK" / "missing" / "unknown" (not checked yet); DMARC shows its policy. | supported | DeliverabilityCard.tsx:20-29,70-73 |
| 30 | **Blocklists**: "OK"; red notice names lists and says campaigns were paused; "1 could not be queried" never counted as listed. | supported | DeliverabilityCard.tsx:52-59,74-75; deliverability.py:142-145 |
| 31 | **Health**: score out of 100, "above threshold" / "below 70" (default threshold) / "not checked yet". | supported | DeliverabilityCard.tsx:62-66; system_settings.py:115 |
| 32 | Press **Run check now**; toast "Checks complete". | supported | DeliverabilityCard.tsx:102,118 |
| 33 | If the card says "Connect a Gmail account on your own domain to monitor it", your address is on a shared domain. | supported (caveat) | DeliverabilityCard.tsx:122-123; deliverability.py:103. Caveat: the same empty state also shows when no Gmail is connected at all. |
| 34 | Deliverability Autopilot (`deliverability_autopilot_enabled`, off by default) | supported | system_settings.py:124 |
| 35 | Launching, approving or resuming a campaign that sends email runs a preflight on every connected mailbox. | supported | app/api/sequences.py:443,573; app/services/campaign_control.py:49; deliverability_autopilot.py:376-397 |
| 36 | Blocks on SPF/DKIM/DMARC failure, failed alignment, or no Gmail mailbox connected. | supported | deliverability_autopilot.py:246-259,394-419 |
| 37 | It also checks the one-click unsubscribe headers. | supported | deliverability_autopilot.py:275-338,422-424 |
| 38 | Refusal starts "Deliverability preflight failed:" … ends "Fix these, then launch again (Settings > Deliverability)." | supported | deliverability_autopilot.py:463-464 |
| 39 | A `p=none` policy passes, with a warning. | supported | deliverability_autopilot.py:240-242,415-416 |
| 40 | If the preflight itself cannot run, the launch is blocked. | supported | deliverability_autopilot.py:451-457 |
| 41 | Autopilot off: low score only warns: "Email health for … is …/100 (below 70). Sending now risks the spam folder" | supported | deliverability.py:320-330; sequences.py:465-471; frontend/src/components/strategy/OutreachPanel.tsx:86 |
| 42 | Consent asked on every connect so Google always returns the long-lived permission. | supported | app/integrations/gmail.py:108-109 |
| 43 | **Connect** or **Reconnect** always shows Google's approval screen. | supported | gmail.py:109; settings/page.tsx:324-330 |
| 44 | Renews automatically within 120 seconds of expiring, and stores it encrypted. | supported | gmail.py:194,205-227; app/config.py:102 |
| 45 | Access removed → renewal fails, **Test** shows "gmail: unhealthy ✗" | supported | gmail.py:397-405; settings/page.tsx:277 |
| 46 | … email messages go back to the queue and are retried; nothing goes out until you reconnect. | supported | app/workers/outreach_tasks.py:985-988,1991-1994 |
| 47 | Vectorae shows no separate alert for this, so use **Test** if sending stops. | **contradicted** | When the last email failed on Google's token endpoint, the strategy page's "Why isn't this sending?" panel shows "Google refused your Gmail connection (revoked or expired)." with the fix "Reconnect Gmail.": app/services/send_diagnostics.py:131-148,169-172; panel mounted at frontend/src/app/(app)/strategies/detail/page.tsx:141 |
| 48 | Reconnect if connected before calendar or draft access was added. | supported | gmail.py:44-59; settings/page.tsx:310-315,328 |
| 49 | Connecting ends with "Google did not return a refresh_token — re-run the auth flow (prompt=consent) …" | supported | gmail.py:188-192; app/api/integrations.py:94-95; frontend/src/lib/api/ecosystem.ts:139-141 (shown as "Gmail connection failed: …") |
| 50 | Reconnecting keeps the permissions you granted before and updates the same connection. | supported | gmail.py:110-113,175-178,186-187 |

Summary: 49 supported, 0 unsupported, 1 contradicted.

### 10-whatsapp-outreach.md
| # | Sentence (verbatim, may be shortened with …) | Verdict | Evidence (path:line) / what the code says |
|---|---|---|---|
| 1 | Vectorae can send outreach on WhatsApp through Meta's WhatsApp Business Cloud API. | supported | app/integrations/whatsapp.py:101-105 |
| 2 | Enforced at sending: recorded opt-in, approved template for the first message, free-form only inside the 24-hour window. | supported | whatsapp.py:131-212; outreach_tasks.py:462-512; sequences.py:253-261 |
| 3 | Free is email only. Starter, Growth, Pay per meeting, Scale, Pro and Enterprise include WhatsApp. | supported | app/core/plans.py:68,84,102,117,135,154,171 |
| 4 | Number configured by your administrator in the server settings, not in the app. | supported | config.py:136-151; settings/page.tsx:343 |
| 5 | Sending needs `WHATSAPP_ACCESS_TOKEN` and `WHATSAPP_PHONE_NUMBER_ID`. | supported | whatsapp.py:109-112 |
| 6 | Templates also need `WHATSAPP_BUSINESS_ACCOUNT_ID`. | supported | whatsapp.py:338-341,365 |
| 7 | Webhook needs `WHATSAPP_VERIFY_TOKEN` and `WHATSAPP_APP_SECRET`; without the secret every delivery is rejected. | supported | app/api/webhooks_whatsapp.py:83-85,110-116,127-128; config.py:149-151 |
| 8 | **Settings** → **Integrations** → **WhatsApp Business** card shows the phone number ID or "Not configured — set WHATSAPP_* env vars on the server"; **Test**. | supported | settings/page.tsx:336-352; app/api/ui_support.py:218-221,245-247 |
| 9 | One WhatsApp Business number per deployment; every user sends from it. | supported | config.py:138; sequence_engine.py:257-260 |
| 10 | Meant for one organization; sign-up open by default; admin can close it or limit it to domains. | supported | docs/program/DECISIONS.md (P0-D); config.py:476,545; app/api/auth.py:224-245 |
| 11 | Agencies: same number for every client; no per-client number. | supported | as #9 |
| 12 | Templates shared: anyone signed in can see, create, edit and submit them. | supported | app/api/whatsapp_templates.py:99-106 |
| 13 | Cap: 10 on the first-send day, +10 a day, up to 100 a day, across all users. | supported | config.py:157-159; sequence_engine.py:245-275 |
| 14 | Over-cap messages wait for the next day's send window; not dropped. | supported | outreach_tasks.py:684-692 |
| 15 | **Campaigns** → choose a strategy → **Templates** tab. | supported | frontend/src/app/(app)/campaigns/page.tsx:404-429,511-513 |
| 16 | **+ New draft**; name rules (example `intro_offer`); body. | supported | campaigns/page.tsx:135; TemplateEditor.tsx:59-70; app/services/whatsapp_templates.py:86-88 |
| 17 | Templates created here use `en_US` and "marketing". | supported | frontend/src/components/campaigns/TemplateEditor.tsx:45 |
| 18 | A "What goes in {{1}}?" field per placeholder. | supported | TemplateEditor.tsx:83-90 |
| 19 | **Generate with AI** drafts 2 or 3 candidates … each with its placeholders described. | **contradicted** (number) | The model is asked for 2–3, but invalid candidates are dropped, so 1 can come back (whatsapp_templates.py:381-387,442-473; also noted in docs/program/help-center-factcheck.md:596). Every valid candidate is also saved as a draft right away, not just the one you pick (:457-465). |
| 20 | Choose one and press **Edit & save this draft** | supported | campaigns/page.tsx:141-152 |
| 21 | Drafts are never submitted automatically. | supported | whatsapp_templates.py:16-20; api/whatsapp_templates.py:11-14 |
| 22 | **Submit** sends a draft or rejected template; review "takes minutes to days". | supported | campaigns/page.tsx:112-117,180-186; whatsapp_templates.py:265-273 |
| 23 | Sends name, language, category, body; no example values; not checked against Meta docs. | supported | whatsapp.py:332-352 (TODO at :348-350) |
| 24 | **Sync status**; a rejected template shows Meta's reason; edit and resubmit. | supported | campaigns/page.tsx:173-191; whatsapp_templates.py:240-262,342-360 |
| 25 | Checked before saving and again before submitting. | supported | whatsapp_templates.py:184-190,241-251,274-277 |
| 26 | Body not empty, at most 1,024 characters by default, placeholders `{{1}}`,`{{2}}` in order, no gaps or repeats. | supported | whatsapp_templates.py:108-125; config.py:155 |
| 27 | Marketing must have an opt-out instruction with STOP in capitals ("Reply STOP to opt out.", "Text STOP anytime", "STOP to unsubscribe"). | supported | whatsapp_templates.py:50-63,75-85 |
| 28 | The word alone does not count ("NON-STOP deals" or a link ending in /STOP is refused). | supported | whatsapp_templates.py:55-56,60-63 |
| 29 | Only English is recognised. | supported | whatsapp_templates.py:60-63 (English words only) |
| 30 | Utility templates are exempt. | supported | whatsapp_templates.py:77-78 |
| 31 | **Generate with AI** adds "Reply STOP to opt out." to a marketing draft that lacks it; in the editor you add it yourself. | supported | whatsapp_templates.py:450-455; TemplateEditor.tsx:75-81 |
| 32 | Editing an approved template creates a new draft version. | supported (caveat) | whatsapp_templates.py:224-238. Caveat: the Templates tab only shows **Edit** for draft or rejected templates (campaigns/page.tsx:180-187), so this only happens through the API. |
| 33 | Only approved templates are sent; approval and the opt-out instruction are re-checked at send. | supported | outreach_tasks.py:483-512; whatsapp.py:184-199 |
| 34 | … the message stops with the status "needs template" and the reason. | **contradicted** (UI label) | Behaviour is right (outreach_tasks.py:486-512 sets an error). But the status is `needs_template` (app/db/models.py:162), the timeline shows "WhatsApp not sent" (frontend/src/lib/conversation.ts:69), and the campaign card says "N need template" (campaigns/page.tsx:79). The text "needs template" does not exist in frontend/src outside the help-center content. |
| 35 | **Save draft** stays disabled until descriptions are filled, body non-empty, a new template has a name, and marketing has an opt-out; message "A marketing message must tell the recipient how to opt out…" | supported | TemplateEditor.tsx:31-35,75-81,93; frontend/src/lib/whatsappTemplate.ts:42-57 |
| 36 | Server reasons: "variable placeholders must be sequential starting at {{1}}", "duplicate variable placeholders (each {{n}} once)", name rule | supported | whatsapp_templates.py:119-123,131-134; TemplateEditor.tsx:50-51 |
| 37 | An earlier editor could not save templates with placeholders; fixed; edits start from saved descriptions. | supported | TemplateEditor.tsx:14-17,26-28,83-90; history in docs/program/help-center-factcheck.md:592 |
| 38 | The launch form on the strategy page creates email sequences only | supported | OutreachPanel.tsx:21,73-75,168-193 |
| 39 | … WhatsApp steps are added through the Vectorae API. | **contradicted** | Autopilot is on by default (`autopilot_launch_enabled` True, system_settings.py:424). It builds WhatsApp template steps from the app (app/services/autopilot.py:633-649,975), and the user picks the template in the app (frontend/src/components/strategy/AutopilotCard.tsx:111-124). |
| 40 | Template step names any non-rejected template and maps each variable. | supported | sequences.py:263-293 |
| 41 | It only sends once the template is approved. | **contradicted** | Nothing waits for approval. If the template is not approved when the step comes due, the message becomes `needs_template` and is not retried later (outreach_tasks.py:486-495; :2030-2032 says "currently terminal for that lead"). |
| 42 | Each variable comes from the lead's record (full name, first name, title, company, email) or an AI-filled brief without invented facts. | supported | app/services/message_personalization.py:195-201,222-263 |
| 43 | A message is never sent with an empty slot. | supported | message_personalization.py:280-288 |
| 44 | Free-form step only inside an open window, and never the first step. | supported | sequences.py:253-261; outreach_tasks.py:468-481 |
| 45 | A WhatsApp-first sequence enrolls verified leads with a phone, including leads with no email. | supported | sequence_engine.py:303,313-325 |
| 46 | No address for a later step's channel → cancelled; reason "no address for the step's channel". | supported | outreach_tasks.py:251-265; app/services/sequence_completion.py:89 ("No address for the step's channel") |
| 47 | Never sends a WhatsApp message without a recorded opt-in. | supported | whatsapp.py:156-183; outreach_tasks.py:463-466 |
| 48 | Step **skipped**, sequence carries on; all skipped → flagged. | supported | outreach_tasks.py:458-466; sequence_engine.py:565-595 |
| 49 | Contact messages first: unknown status → opt-in with message ID as evidence. | supported | app/services/whatsapp_optin.py:247-267; webhooks_whatsapp.py:483-488 |
| 50 | Record through the API one contact at a time; evidence recommended, required for manual import. | supported | app/api/whatsapp_optin.py:57-66,103-133; whatsapp_optin.py:130-141 |
| 51 | CSV import through the API; every row needs evidence; rejected rows get a reason. | supported | api/whatsapp_optin.py:17-25,256-321 |
| 52 | Hosted opt-in page exists, but the app gives no way to get the link. | supported | api/whatsapp_optin.py:216-246; `make_optin_token` has no caller (whatsapp_optin.py:275) |
| 53 | Opt-ins and opt-outs are an add-only history. | supported | whatsapp_optin.py:107; api/whatsapp_optin.py:7 |
| 54 | Status shows as **WhatsApp opt-in** on a lead in **Pipeline**. | supported | frontend/src/app/(app)/pipeline/page.tsx:96-108 |
| 55 | A suppressed number cannot be opted in again; suppression cannot be lifted from the app. | supported | whatsapp_optin.py:144-152. Admin removal works by email only (app/api/admin.py:209-218; app/services/admin_service.py:231-236), so phone suppressions cannot be lifted. |
| 56 | Contact message opens 24h, each new one restarts it; templates do not open it. | supported | whatsapp.py:121-129; webhooks_whatsapp.py:435-437 |
| 57 | Inside the window free-form can send; outside only templates. | supported | whatsapp.py:200-212 |
| 58 | … Free-form messages wait until they reply. | **contradicted** | They do not wait. A free-form message due while the window is closed becomes `needs_template` and stays that way (outreach_tasks.py:468-481,2030-2032). The article's own next paragraph says this. |
| 59 | Window checked at send; due after close → not sent, marked "needs template". | **contradicted** (UI label) | Behaviour supported (outreach_tasks.py:468-481); label issue is the same as #34. |
| 60 | **Campaigns** → **Overview** tab → **WhatsApp** card shows open windows and messages needing a template. | supported | campaigns/page.tsx:71-81,432,467 ("Windows open"; "N need template" badge only when >0) |
| 61 | The 24-hour length follows Meta's policy as understood at build time; not re-checked. | supported | app/services/whatsapp_window.py:3,25 (TODO) |
| 62 | STOP keyword list, immediate, no AI, starts with stop/unsubscribe, case-insensitive. | supported | webhooks_whatsapp.py:57-70,467-482 |
| 63 | Records the contact as opted out. | supported | whatsapp_optin.py:182-209 |
| 64 | Suppresses their phone number, email address and LinkedIn profile. | supported | whatsapp_optin.py:214-227; app/services/consent.py:219-239 |
| 65 | Stops all of their sequences on every channel. | supported | webhooks_whatsapp.py:480-481; whatsapp_optin.py:230-240 |
| 66 | AI later reads another reply as a stop request → same effect. | supported | outreach_tasks.py:1835-1858 |
| 67 | A STOP from an unmatched number still suppresses that number. | supported | webhooks_whatsapp.py:361-406 |
| 68 | An opted-out contact who messages again is not opted back in. | supported | whatsapp_optin.py:247-257 |
| 69 | Replies classified like email; a real reply stops all sequences incl. email; out-of-office pauses. | supported | outreach_tasks.py:1835-1858 |
| 70 | Vectorae never replies automatically. | supported | outreach_tasks.py:1844; app/services/reply_copilot.py:85,321-323 (WhatsApp excluded from Reply Copilot) |
| 71 | Matching: most recently messaged lead, else the only holder, else unattached. | supported | webhooks_whatsapp.py:321-358 |
| 72 | Undelivered → handled like an email bounce. | supported | webhooks_whatsapp.py:290-296 |
| 73 | Not verified against Meta's live service; simulated tests; many details marked unconfirmed. | supported | TODOs throughout whatsapp.py (e.g. :24,57,236,335) and webhooks_whatsapp.py; docs/VERIFICATION_REPORT.md:579 |

Summary: 67 supported, 0 unsupported, 6 contradicted (#19, #34, #39, #41, #58, #59).

### 13-replies-and-unified-inbox.md (opening paragraph and "Does Vectorae answer replies for me?" only)
| # | Sentence (verbatim, may be shortened with …) | Verdict | Evidence (path:line) / what the code says |
|---|---|---|---|
| 1 | When a prospect replies by email, WhatsApp or LinkedIn, Vectorae stores the reply, classifies it, and changes what happens next in their sequence. | supported | webhooks_whatsapp.py:421-453; app/api/linkedin.py:336; outreach_tasks.py:1835-1858 |
| 2 | By default Vectorae does not reply to a person automatically; the optional Reply Copilot is the exception. | supported | system_settings.py:318-326 (both default False); reply_copilot.py:18 |
| 3 | The **Inbox** gathers every reply into one conversation per prospect … who is waiting for an answer. | supported | app/services/inbox.py:3-18 |
| 4 | Not by default. Replies are classified and routed, and a person writes the answer. | supported | app/services/reply_intelligence.py:16-21 |
| 5 | Reply Copilot is off unless your administrator turns it on: it drafts an answer that a person approves before it is sent | supported | system_settings.py:318-322; reply_copilot.py:13-17. Small caveat: LinkedIn drafts are copied, not sent by Vectorae. |
| 6 | … only if automatic sending is also allowed can an answer go out without a person. | supported | reply_copilot.py:829-863; system_settings.py:323-326. This is a necessary condition only: auto-send also needs the account's opt-in, email, a "send me a time" reply and a booking link. |
| 7 | A second AI pass reads each reply and decides what you should do next, in one of four categories | supported | reply_intelligence.py:3-14,50 |
| 8 | **Buying signal** – interest, a question about how it works, or a request for a call or pricing. | supported | reply_intelligence.py:109-111 |
| 9 | **Objection** – a specific concern such as price or an existing supplier. | supported | reply_intelligence.py:110-111 |
| 10 | **Not now** – a timing issue, not a rejection. | supported | reply_intelligence.py:111-112 |
| 11 | **Wrong person** – not the buyer or name someone else. | supported | reply_intelligence.py:112-113 |
| 12 | It writes a suggested draft of under 150 words onto the reply. | supported | reply_intelligence.py:56,114,154-156,352-355 |
| 13 | The draft is never sent by Vectorae; you read it, edit it, and send your answer yourself. | supported | reply_intelligence.py:16-21 |
| 14 | Buying signal → next step would be step 3; status unchanged; nothing sends until a person acts. | supported | reply_intelligence.py:17-21,64-67,246-283 |

Summary: 14 supported, 0 unsupported, 0 contradicted.

### 22-plans-limits-billing.md (new paragraph at the start of "How do I choose or change a plan?" only)
| # | Sentence (verbatim, may be shortened with …) | Verdict | Evidence (path:line) / what the code says |
|---|---|---|---|
| 1 | Online checkout is not open yet | supported | frontend/src/content/product-facts.json:72; frontend/src/lib/productFacts.ts:42 (`CHECKOUT_LIVE` false unless status is "live") |
| 2 | Stripe checkout has so far been built and tested only against simulated services | supported | product-facts.json:72 (`"status": "simulated_only"`) |
| 3 | the **Pricing** page says "Online checkout opens soon" and offers a call instead of a checkout button. | supported | frontend/src/app/pricing/PricingClient.tsx:209-211,280-302,332-343,365-372 ("Online checkout opens soon. To start now, book a call." plus a **Book a call** link); frontend/src/app/pricing/page.tsx:35 |
| – | "The steps below describe how choosing a plan works once checkout opens." | skipped | navigation |

Summary: 3 supported, 0 unsupported, 0 contradicted.

### Founder decision D1
None of the checked sentences contradicts D1. No sentence says outreach needs manual sending, and none says research runs per prospect.

### Out of scope (reported, not fixed)
- `frontend/src/content/help-center/10-whatsapp-outreach.md` is an older, different copy of article 10 (for example its line 65 wording). If the in-app Help AI reads `frontend/src/content/help-center/`, today's edits to `docs/help-center/10-whatsapp-outreach.md` will not reach customers until the two are synced. The same may apply to 13, 22 and 35; I did not compare those.
- Fixing #41 and #58 needs more than an article edit. The code records that WhatsApp steps ending in `needs_template` are "currently terminal for that lead" (outreach_tasks.py:2030-2032). The article should say a step due before approval, or after the window closes, is not sent and does not wait.

---

## Report: 36-37-27

Fact-check of three help-center articles in /home/user/LeadPilot. Every `sources` path listed in the front matter of articles 36 and 37 exists (checked with Glob). For article 27, only the 429 bullet was checked (line 87). Results: article 36 has 4 contradicted sentences, article 37 has 2, and the article 27 bullet is fully supported. Nothing was edited.

### 36-crm-sync-field-mapping.md
| # | Sentence (verbatim, may be shortened with …) | Verdict | Evidence (path:line) / what the code says |
|---|---|---|---|
| 1 | Each synced lead becomes a HubSpot contact, found by email or created… | supported | app/services/crm_sync.py:369-382 (it checks an existing link first, then email) |
| 2 | HubSpot field table (email, lastname = last word, firstname = rest, company, jobtitle, phone, hs_lead_status, lifecyclestage) | supported | crm_sync.py:339-355. Detail: a one-word name goes to `firstname` and `lastname` is left empty (crm_sync.py:343-344) |
| 3 | Lead status is sent as: verified → NEW … disqualified → UNQUALIFIED | supported | crm_sync.py:75-79 |
| 4 | Lifecycle stage is `opportunity` for an opportunity and `customer` for closed won | supported | crm_sync.py:81 |
| 5 | HubSpot does not let a lifecycle stage move backwards; … sends the rest without it | supported | crm_sync.py:358-366 (on a 400 it retries once without lifecyclestage) |
| 6 | Each deal → HubSpot deal with dealname, amount (two decimals), dealstage map, pipeline default, deal_currency_code, closedate | supported | crm_sync.py:82, 424-431 |
| 7 | A new deal is linked to the lead's contact | supported | crm_sync.py:441-450. The association call is marked TODO-unverified at app/integrations/hubspot.py:157 |
| 8 | Empty Vectorae fields are left out… | supported | crm_sync.py:355, 395 |
| 9 | Leads become Salesforce Leads, not Contacts; converting stays your users' decision | supported | app/integrations/salesforce.py:9-11 |
| 10 | Looks for an existing Lead with the same email (does not search Contacts) | supported | salesforce.py:132-135 |
| 11 | Salesforce field table, including LastName/Company `Unknown` and LeadSource=Vectorae on new Leads | supported | crm_sync.py:388-395, 414 |
| 12 | `Status` is sent as: verified → Open - Not Contacted … | supported | crm_sync.py:83-88 |
| 13 | Once a Lead is converted… read-only, and Vectorae stops updating it | supported | crm_sync.py:409-412 (the update is still attempted; the CONVERTED 400 error is swallowed) |
| 14 | Opportunity with Name (up to 120), StageName map, Amount, CloseDate | supported | crm_sync.py:89, 459-465 |
| 15 | …and a `Description` naming the Vectorae deal and the lead's email | contradicted (minor) | crm_sync.py:466-467: the Description is `"Vectorae deal <deal UUID> for <email>"`. It uses the deal's internal ID, not its name |
| 16 | An open deal without a close date gets a date 30 days out | supported | crm_sync.py:462-464 |
| 17 | The Opportunity is not linked to the Lead record | supported | crm_sync.py:456-482 (no association call) |
| 18 | By default Vectorae sends leads that replied or went further… | contradicted (partial) | This is true for the sweep only (crm_sync.py:65, 533). Immediate pushes (`push_lead`, crm_sync.py:495-509) apply no status filter, so a manual Pipeline move to any status (e.g. contacted, proposal_sent) is pushed straight away (app/api/ui_support.py:145-151) |
| 19 | Checkbox "Also push every verified lead (by default only leads that replied or further)" … adds verified and contacted | supported | Label matches exactly: frontend/src/components/settings/CrmCards.tsx:126. crm_sync.py:67, 533 |
| 20 | A lead without an email is never sent | supported | crm_sync.py:497, 536 |
| 21 | Proposal-sent has no status mapping and the sweep does not send those leads | supported | app/db/models.py:112. crm_sync.py:65-67, 75-88 |
| 22 | Every deal is sent | supported | crm_sync.py:538 |
| 23 | Straight away when a meeting is booked … you change a lead's status by hand (e.g. kanban) … or create/edit a deal | contradicted (partial) | Events: crm_sync.py:72-73 and app/services/event_bus.py:123. Pipeline/kanban: ui_support.py:150-151. Deals: app/api/deals.py:148, 199. Hand edits from the CRM table (inline or bulk, app/api/crm.py:252-374 and 384+) do not queue a push; only the 15-minute sweep picks them up |
| 24 | Every 15 minutes … up to 500 leads and 500 deals per run | supported | app/workers/celery_app.py:362-365 (900 s). crm_sync.py:71, 545. See discovery 1 below |
| 25 | This catches changes no event announces, such as a logged meeting outcome | supported | crm_sync.py:20-22. Detail: a closed-won outcome does send `deal_won` (app/services/meeting_followup.py:219-239) |
| 26 | **Sync now** … sends every eligible record, not only the changed ones, and then reads linked records back | contradicted (partial) | It does a full push then a pull (app/api/crm_integrations.py:195; crm_sync.py:529-545, 845), but the full push is still capped at 500 leads and 500 deals (crm_sync.py:545) |
| 27 | The same person in two campaigns is one CRM record; the first lead keeps the link | supported | crm_sync.py:321-325 |
| 28 | Only records Vectorae created or linked come back; CRM-only records not imported | supported | crm_sync.py:13-14, 695-799 |
| 29 | A HubSpot deal created on a linked contact is imported | supported | crm_sync.py:720-724, 737-771. Detail: this happens only through the HubSpot `deal.creation` webhook; polling (`pull`, 802-837) never imports |
| 30 | Salesforce Opportunities created in Salesforce are not imported | supported | crm_sync.py:774-799 (linked records only; there is no import path) |
| 31 | HubSpot contact read-back mapping | supported | crm_sync.py:91-92, 633-644 |
| 32 | HubSpot deal read-back (closedwon/closedlost, amount, closedate copied, lead closed) | supported | crm_sync.py:93, 597-601, 647-657 |
| 33 | Salesforce Lead read-back (converted / Closed - Converted → opportunity; Closed - Not Converted → disqualified) | supported | crm_sync.py:94-95, 660-663 |
| 34 | Salesforce Opportunity read-back (won / closed-not-won, Amount, CloseDate) | supported | crm_sync.py:666-671, 684-692 |
| 35 | Name, email, company, title and phone are never read back | supported | crm_sync.py:814; salesforce.py:26 |
| 36 | Polling without setup; the same 15-minute sweep reads every linked record back | supported | crm_sync.py:802-837, 845 |
| 37 | HubSpot sends signed webhooks once your admin subscribes the app | supported | docs/features/crm-ecosystem.md:52-56; crm_integrations.py:245-261 |
| 38 | Salesforce needs a Flow or Apex callout with a signature | supported | crm-ecosystem.md:57-62; crm_integrations.py:264-295 |
| 39 | If guardrails are on, a daily job reads customer and open-deal companies into exclusion lists, checked before sending | supported | crm_tasks.py:81-90; celery_app.py:366-373; app/services/guardrails.py:726-778 (it also reads churned) |
| 40 | Fixed rules, not timestamps | supported | crm_sync.py:564-602 (no timestamp comparison) |
| 41 | Contact details belong to Vectorae; each push overwrites; CRM edits never reach Vectorae | supported | crm_sync.py:348-355, 376, 405, 814 |
| 42 | Lead status only moves forward; a closed lead is never reopened | supported | crm_sync.py:564-570 |
| 43 | Vectorae keeps sending its own status; this stops the loop | supported | crm_sync.py:26-29 |
| 44 | During the sweep Vectorae pushes before it reads back, so Vectorae's deal values win | supported | crm_sync.py:845 |
| 45 | A CRM webhook change is applied when it arrives | supported | crm_integrations.py:261, 295 |
| 46 | A deal reopened in the CRM is not reopened in Vectorae by default | supported | crm_sync.py:626-630, 666-671 (only closed stages map inbound by default) |
| 47 | Deleted in the CRM → created again on the next push | supported | crm_sync.py:377-382, 406-414, 438-442, 475-479, 725-730 |
| 48 | When the CRM closes a lead, its sequences stop | supported | crm_sync.py:572-577 |
| 49 | Status mapping only through the API; the settings screen has no editor | supported | CrmCards.tsx:56-60, 118-128; crm_integrations.py:197-228 |
| 50 | `lead_status_map` … up to 20 entries; keys must be the listed statuses | supported | crm_integrations.py:172, 177, 202-207 |
| 51 | `deal_stage_map`: open/won/lost, up to 5 entries | supported | crm_integrations.py:173, 178 |
| 52 | `pipeline` (HubSpot), up to 100 characters | supported | crm_integrations.py:174; crm_sync.py:428 |
| 53 | Your values replace defaults for the keys you give | supported | crm_sync.py:166-167 |
| 54 | For incoming changes only a HubSpot `deal_stage_map` is used | supported | crm_sync.py:91-95, 626-630, 660-671 |
| 55 | Tests run against simulated CRMs; no record of a live test | supported | docs/FULL_PRODUCT_AUDIT.md:119-120 |
| 56 | Several HubSpot calls (token exchange, contact search, deal↔contact link, search paging) are marked as not yet checked | supported | hubspot.py:74, 131, 157, 171-172 |
| 57 | The daily guardrails read from both CRMs is also marked unverified | supported | guardrails.py:728, 755; salesforce.py:120 |
| 58 | The CRM card shows the last error; a rejected sign-in marks the connection as needing reconnection | supported | CrmCards.tsx:81, 112-116 ("needs attention", "Last error:", "reconnect to restore the sync."); crm_sync.py:175-179 |

Summary: 54 supported, 0 unsupported, 4 contradicted.

### 37-webhooks-and-slack-events.md
| # | Sentence (verbatim, may be shortened with …) | Verdict | Evidence (path:line) / what the code says |
|---|---|---|---|
| 1 | Events offered under **Events** when you click **Add webhook** | supported | frontend/src/components/settings/WebhooksCard.tsx:82, 182, 190-200; app/api/webhook_targets.py:80-84; app/services/webhook_delivery.py:63-83 |
| 2 | meeting_booked: Calendly or Vectorae calendar | supported | app/api/webhooks.py:182-189; app/workers/calendar_tasks.py:247-254 |
| 3 | reply_received: a lead replies on any channel | supported | webhook_delivery.py:65. Detail: it fires for email, WhatsApp and LinkedIn only (app/workers/outreach_tasks.py:1813, 1894, 1951); AI phone calls do not send reply_received |
| 4 | reply_interested: a reply or AI call classified interested | supported | outreach_tasks.py:1649-1654; app/services/phone_calls.py:404-412 |
| 5 | lead_sourced: a sourcing batch finishes | contradicted (partial) | app/workers/lead_tasks.py:639-644: no event is sent when the batch has no verified leads |
| 6 | campaign_paused: automatic (bounce) or by you | supported | app/services/sequence_engine.py:806-814; app/services/campaign_control.py:34-39 |
| 7 | strategy_mutated | supported | app/services/strategy_mutation.py:331-342 |
| 8 | deal_won: you log a meeting outcome as closed won | supported | meeting_followup.py:219-239 (the only place it is sent) |
| 9 | call_completed | supported | phone_calls.py:417-423 |
| 10 | objection_spike: week over week | supported | app/services/reply_sentiment.py:120-142 |
| 11 | domain_blacklisted: newly listed | supported | app/services/deliverability.py:253-262 |
| 12 | deliverability_warning: domain health below threshold, or mailbox spam-rate brake | supported | deliverability.py:263-269; app/services/mailbox_health.py:416-428 |
| 13 | mailbox_paused | supported | mailbox_health.py:433-445 |
| 14 | send_needs_review | supported | app/services/send_review.py:325-340 |
| 15 | reengagement_due | supported | app/services/reengagement_memory.py:783-800 |
| 16 | reply_draft_approved | supported | app/api/crm.py:1450-1463 |
| 17 | The last six used to be impossible to subscribe to, or never fired; fixed | supported | webhook_delivery.py:73-83; event_bus.py:60-66; docs/program/fixes/send-path-gaps.md:189-208 |
| 18 | `lead_replied` treated as `reply_received` | supported | webhook_delivery.py:86, 159, 319 |
| 19 | Up to 20 events per webhook; up to 25 active webhooks | supported | webhook_targets.py:41; webhook_delivery.py:95, 224-229 |
| 20 | Every delivery is a POST with the JSON body shown | supported | webhook_delivery.py:300-309, 380 |
| 21 | Headers X-LeadPilot-Event, X-LeadPilot-Delivery (same on retry), X-LeadPilot-Signature, legacy X-ClientHunter-Signature | supported | webhook_delivery.py:369-376 |
| 22 | Lead object fields | supported | event_bus.py:127-138 |
| 23 | meeting_booked data: lead, source, calendly_event or booking_id | supported | webhooks.py:187-188; calendar_tasks.py:252-253 |
| 24 | reply data: lead, channel, classification; phone variant lead_id, call_id, channel, classification | supported | outreach_tasks.py:1642-1643; phone_calls.py:410-411 |
| 25 | lead_sourced data: batch_id, strategy_id, counts, leads (up to 200) | supported | lead_tasks.py:639-652 |
| 26 | campaign_paused data incl. bounce_rate on auto | supported | sequence_engine.py:811-813; campaign_control.py:37-38 |
| 27 | strategy_mutated data | supported | strategy_mutation.py:339-341 |
| 28 | deal_won data: lead_id, deal_id, value_cents, currency | supported | meeting_followup.py:234-237 |
| 29 | call_completed data | supported | phone_calls.py:421-423 |
| 30 | objection_spike data | supported | reply_sentiment.py:138-141 |
| 31 | domain_blacklisted data | supported | deliverability.py:261-262 |
| 32 | deliverability_warning data (+ mailbox_ref, complaint_source from brake) | supported | deliverability.py:269; mailbox_health.py:426-428 |
| 33 | mailbox_paused data | supported | mailbox_health.py:444-445 |
| 34 | send_needs_review data | supported | send_review.py:339-340 |
| 35 | reengagement_due data | supported | reengagement_memory.py:798-800 |
| 36 | reply_draft_approved data | supported | crm.py:1459-1462 |
| 37 | **Send test** queues a sample of one of the webhook's events with `"test": true` | supported | webhook_delivery.py:333-336; label at WebhooksCard.tsx:104 |
| 38 | The samples for `meeting_booked` and `deal_won` do not match the live payloads… | contradicted (incomplete) | Those two do differ (webhook_delivery.py:105-106, 119-120). The `strategy_mutated` sample also differs: it has no `version_id` or `changes` (webhook_delivery.py:117-118), while the live payload has them (strategy_mutation.py:339-341) |
| 39 | Signing secret shown once; starts with `whsec_` | supported | webhook_delivery.py:216-217; WebhooksCard.tsx:33-38, 85-87 |
| 40 | Header format `t=<unix timestamp>,v1=<hex signature>` | supported | webhook_delivery.py:256-258 |
| 41 | Verification steps 1-5 (raw body, split, HMAC over `"<t>.<body>"`, constant-time compare, 300 s) | supported | webhook_delivery.py:94, 261-273, 280-282 |
| 42 | Python sample (header names, `f"{ts}."+body`, sha256 hex, compare_digest, 300 s) | supported | Matches `sign`/`verify_signature`, webhook_delivery.py:256-273 |
| 43 | Timestamp signed fresh on every attempt | supported | webhook_delivery.py:347, 374 |
| 44 | Legacy header is `sha256=` + HMAC of the body alone | supported | webhook_delivery.py:276-277 |
| 45 | Any 2xx counts as delivered | supported | webhook_delivery.py:382-388 |
| 46 | Waits up to 10 seconds | supported | webhook_delivery.py:93, 341 |
| 47 | Timeout, connection error or other status (apart from 410) is a failure and is retried | supported | webhook_delivery.py:396-411 |
| 48 | Retry table 30 s / 2 min / 10 min / 30 min / 2 h; 6 attempts | supported | webhook_delivery.py:90-92, 407-410 |
| 49 | After the sixth failure: `exhausted`, recorded for your administrator | supported | webhook_delivery.py:401-406, 414-434 |
| 50 | No button to resend | supported | Not present in WebhooksCard.tsx or webhook_targets.py |
| 51 | An earlier version stopped after five attempts; fixed | supported | webhook_delivery.py:26-28; send-path-gaps.md:211-216 |
| 52 | 410 Gone turns the webhook off with reason "the receiver answered 410 Gone" | supported | webhook_delivery.py:389-395; shown at WebhooksCard.tsx:98 |
| 53 | To start again, add the webhook again | supported | There is no reactivate route (webhook_targets.py) |
| 54 | Non-public host fails at once without retries | supported | webhook_delivery.py:360-365 |
| 55 | Redirects are not followed | supported | webhook_delivery.py:341 |
| 56 | Deleting a webhook, or a 410, cancels its pending deliveries | supported | webhook_delivery.py:352-356; app/db/models.py:2103 (ON DELETE CASCADE) |
| 57 | **Recent deliveries** shows status, attempt count, last response | supported | WebhooksCard.tsx:118-136 |
| 58 | Slack: no per-event settings; once connected with a **Channel**, posts to that one channel | supported | frontend/src/components/settings/SlackCard.tsx:86; app/integrations/slack.py:150-158; event_bus.py:117-118 |
| 59 | Meeting booked, prep brief ready, reminders a day and an hour before | supported | webhooks.py:182; calendar_tasks.py:247; app/services/meeting_prep.py:643; app/workers/meeting_prep_tasks.py:179-211 |
| 60 | Interested reply (email, other channels, AI calls) | supported | outreach_tasks.py:1649-1654; phone_calls.py:405-412 |
| 61 | Auto-pause posted; a pause you make yourself is not | supported | sequence_engine.py:806-807; campaign_control.py:35 (slack=False) |
| 62 | Strategy rewritten; awaiting approval; approval decision | supported | strategy_mutation.py:331; app/api/sequences.py:520, 541 |
| 63 | Objection spike, deal won, AI call completed | supported | reply_sentiment.py:132; meeting_followup.py:238; phone_calls.py:417 |
| 64 | Domain blacklisted, email health warning, mailbox paused | supported | deliverability.py:255, 265; mailbox_health.py:419, 437 |
| 65 | Held for review, re-engagement due, reply draft approved | supported | send_review.py:333; reengagement_memory.py:792; crm.py:1454 |
| 66 | Daily send approval needed, Autopilot updates, personal video suggested | supported | app/services/daily_send_approval.py:761; app/services/autopilot.py:396; app/services/loom_video.py:153 |
| 67 | AI call in progress, paused for disclosure incident, message taken | supported | app/services/voice_twin.py:596, 629-634, 1522, 1552 |
| 68 | reply_received and lead_sourced go to webhooks only, never Slack | supported | outreach_tasks.py:1646; lead_tasks.py:646 |
| 69 | Each post has a title, short text and an "Open in Vectorae" button when there is a screen | supported | slack.py:164-176; event_bus.py:176 |
| 70 | Not connected, no channel, or Slack fails → skipped, nothing else affected | supported | slack.py:150-161; event_bus.py:13-18, 181-183 |
| 71 | The Slack connection has not been tested against a live Slack workspace | supported | FULL_PRODUCT_AUDIT.md:119-120 (a general "all integrations mock-tested" statement, nothing Slack-specific) |

Summary: 69 supported, 0 unsupported, 2 contradicted.

### 27-troubleshooting.md (only the 429 bullet, line 87)
| # | Sentence (verbatim, may be shortened with …) | Verdict | Evidence (path:line) / what the code says |
|---|---|---|---|
| 1 | Common defaults: 2 new strategies per hour | supported | app/core/config.py:7, 172 |
| 2 | 5 lead-sourcing requests per hour | supported | app/core/config.py:8, 200 |
| 3 | 10 sign-in attempts per 15 minutes | supported | app/core/config.py:12, 335; app/core/rate_limiting.py:211 (900 s) |
| 4 | 20 support chat messages per day | supported | app/core/config.py:13, 358; app/api/support.py:42, 244-245 (86,400 s window) |
| 5 | (Vectorae's hosted service raises this to 30) | supported | render.yaml:133-135 and 233-235 (`RATE_LIMIT_SUPPORT_CHAT: "30"` on both services). This conflicts with app/core/config.py:340 ("20, lowered from 30 on 2026-08-30 at the product owner's instruction"). render.yaml was apparently never lowered, so ask the founder whether 30 is intended or stale before relying on it |
| 6 | These are deployment settings | supported | app/core/config.py:1-13 (env-overridable) |

Summary: 6 supported, 0 unsupported, 0 contradicted.

### Other problems found (reported, not fixed)
1. **CRM sweep can drop records for good.** `push_changed` takes the first 500 changed leads and 500 changed deals, then moves `conn.last_push_at` forward to the sweep's start time (crm_sync.py:539-554). Anything past the 500 cap is left out of later incremental sweeps until it changes again. Article 36 row 24 implies the overflow goes out on the next run; it does not.
2. **Immediate CRM pushes ignore the status rule.** `push_lead` (crm_sync.py:495-509) pushes whatever status the lead has. A Pipeline move to `contacted` or `proposal_sent` is pushed even when "Also push every verified lead" is off, and a `proposal_sent` lead goes out with no status value.
3. **Support-chat limit mismatch.** render.yaml (30) does not match the documented product-owner decision of 20 (app/core/config.py:340-358).
4. **Rate limit on "Sync now".** It uses the `RATE_LIMIT_AI_ACTION` limit (crm_integrations.py:191). Article 36 does not mention this.

None of the three items touches founder decision D1.

---

## Report: 38-39-44-29-30

## Fact-check report: help-center articles 38, 39, 44, 29 (one bullet) and 30 (one sentence)

I checked every cited source path in all five front-matter lists with Glob, and every path exists. Paths in the tables are relative to /home/user/LeadPilot. "dsa" means app/services/daily_send_approval.py.

**Overall:** 5 contradicted sentences, all in articles 38, 39 and 44. No unsupported sentences. The single chat-limit claim in articles 29 and 30 is correct. The two worst errors are the 5-minute wait claim in article 38 and the blocked-script fallback claim in article 44.

### 38-reply-copilot-and-classification.md
| # | Sentence (verbatim, may be shortened with …) | Verdict | Evidence (path:line) / what the code says |
|---|---|---|---|
| 1 | Every reply is read by AI, which must pick exactly one routing class: `interested` … `automated_response`. | supported | app/services/reply_classification.py:22-45 |
| 2 | The AI sees the sender's address, the subject and the first 4000 characters of the body. | supported | reply_classification.py:51-55, :88 (`[:4000]`) |
| 3 | The reply text is passed to it as untrusted data, so instructions written inside a reply are not followed. | supported (caveat) | reply_classification.py:47-49, :85-88 (prompt_safety NOTICE/block). This is a mitigation, not a guarantee; "are not followed" is stronger than the code can promise. |
| 4 | The AI is told that any request to stop … `unsubscribe_request`, … `bounce`, … `out_of_office`. | supported | reply_classification.py:39-43 |
| 5 | If its answer is unreadable or not one of the classes, or the call fails, the reply becomes `question`. | supported | reply_classification.py:91-97 |
| 6 | That stops the sequence and leaves the reply for a person… | supported | reply_classification.py:62-63; app/workers/outreach_tasks.py:1800-1804 |
| 7 | When the class is `interested`, `question`, `objection` or `not_interested`, a second check asks whether a machine wrote it (no-reply sender, auto-reply subject, ticket or "we received your message" wording). | supported | app/services/reply_fraud.py:31-48, :126-164 |
| 8 | A reply judged automated is stored as `automated_response`: it stays visible, but it does not count as a reply. | supported | reply_fraud.py:16-19; outreach_tasks.py:1769-1772 |
| 9 | Your administrator can switch this check off (`reply_fraud_detection_enabled`, on by default). | supported | app/services/system_settings.py:120; reply_classification.py:70-74 |
| 10 | On WhatsApp, a STOP message is handled by a fixed rule … stored as `unsubscribe_request` and the person is suppressed. | supported | app/api/webhooks_whatsapp.py:12-13, :61-69, :469-480 |
| 11 | …each reply also gets a positive-reply label … and a suggested next step with a draft … two further AI readings; they do not change the routing class. | supported (caveat) | app/workers/reply_tasks.py:61-67, :100-105. The positive label is rule-based (no AI) for unsubscribe_request, bounce, out_of_office and automated_response (app/services/reply_intent.py:26-31). |
| 12 | the sequence stops, pauses or carries on, according to the class; | supported | outreach_tasks.py:1769-1810 |
| 13 | an `unsubscribe_request` suppresses the person on every channel; | supported | app/services/sequence_engine.py:712-735 (`consent.suppress_everywhere`) |
| 14 | a `bounce` is recorded and the campaign's bounce rate is checked; | supported | reply_classification.py:10; outreach_tasks.py:1786-1788 |
| 15 | the positive-reply label is set. | supported | reply_tasks.py:61-67. It runs as an async task and can stay unlabeled on failure (reply_intent.py:34-35). |
| 16 | Approving that draft adds a note with the text and an entry on the lead's timeline; it does not send anything; | supported | app/api/crm.py:1200-1204, :1403-1446 |
| 17 | Reply Copilot drafts … A person approves each one, with one narrow exception: auto-send for "send me a time" … off unless both your administrator and you switch it on. | supported | app/services/reply_copilot.py:787-790, :829-845; system_settings.py:323 |
| 18 | Reply Copilot writes a draft … using only your campaign's objection research, the approved claims in your library and your booking link. | supported | reply_copilot.py:491-510, :603-612 (claims only when F05 guardrails are on) |
| 19 | It is off by default: your administrator turns it on in System Settings (`reply_copilot_enabled`). | supported | system_settings.py:318 |
| 20 | the reply came by email or LinkedIn (WhatsApp and phone replies never get one); | supported | reply_copilot.py:84-85, :321-323 |
| 21 | it is matched to one of your leads and was written by a person; | supported | reply_copilot.py:319-320, :333-334 |
| 22 | its class is `interested`, `question` or `objection`; | supported | reply_copilot.py:90, :95-96 (falls back to the intent label while routing is not stored yet, :91-93) |
| 23 | it contains no opt-out wording … checked with fixed rules on the prospect's new text, whatever the AI decided; | supported | reply_copilot.py:156-170, :229-265, :331-332 |
| 24 | the lead is not suppressed or excluded, and its status is still Replied, Contacted, Verified or Flagged. A lead that booked a meeting, was closed or disqualified gets no draft. | supported | reply_copilot.py:350-379 |
| 25 | Each reply gets at most one draft, of at most 140 words. | supported | reply_copilot.py:691-694, :108, :560-564 |
| 26 | When the same lead writes again, any older draft still waiting is marked superseded. | supported | reply_copilot.py:731-740 |
| 27 | If the AI writes a draft containing a link other than your booking link or your own sending domain, a placeholder such as `[Name]`, or a forbidden phrase, Vectorae asks once more; if the second try fails, no draft is made… | supported | reply_copilot.py:204-206, :567-587, :636-650 |
| 28 | Claims Vectorae cannot back are removed and listed on the draft. | supported | reply_copilot.py:720-729, :665-670; frontend/src/components/inbox/ReplyCopilotPanel.tsx:147-153 |
| 29 | Open the prospect's conversation in **Inbox**. Waiting drafts appear in the **Reply Copilot** card above the conversation. | supported | frontend/src/app/(app)/inbox/page.tsx:206-212; ReplyCopilotPanel.tsx:66-70; frontend/src/components/shell/nav.ts:33 |
| 30 | **Approve & send** (email), or **Send edited** once you changed it; | supported | frontend/src/lib/replyCopilot.ts:114 |
| 31 | **Copy** or **Copy edited** (LinkedIn): … clipboard … Vectorae never sends LinkedIn drafts; | supported | replyCopilot.ts:113; ReplyCopilotPanel.tsx:112-117; reply_copilot.py:1047-1050 |
| 32 | **Discard**: the reply stays in "Needs reply"; | supported | reply_copilot.py:1062-1065; inbox/page.tsx:46; ReplyCopilotPanel.tsx:164 |
| 33 | **Undo edits** puts the original draft back. | supported | ReplyCopilotPanel.tsx:166-169 |
| 34 | An answer longer than 5000 characters, one containing a forbidden phrase, or one with a claim it cannot back is refused, with the reason shown. | supported | reply_copilot.py:109, :915-967; ReplyCopilotPanel.tsx:126 |
| 35 | An approved email waits 5 minutes, then goes through the normal send path… | **contradicted** | `approve()` sets `scheduled_at = now + 5 min` (reply_copilot.py:1029) but immediately calls `reply_tasks.enqueue_send(message.id)` (reply_copilot.py:1043). That publishes `send_reply_draft` with no countdown (reply_tasks.py:204-209), and `send_message_impl` never checks `scheduled_at` (outreach_tasks.py:145-169). The 5 minutes only keeps the beat dispatcher off the row (reply_copilot.py:102-105); it acts as a delay only when the broker is down. In practice the send is attempted right away. |
| 36 | …unsubscribe footer and headers, send window, daily cap and the send-review queue all apply, so it can wait. | supported | reply_tasks.py:165-170; docs/features/f04-reply-copilot.md:189-196 |
| 37 | It is cancelled if, before it goes out, the prospect writes again, opts out, books a meeting, or the lead is closed. | supported | reply_copilot.py:1154-1213 |
| 38 | The card shows … "sent", "queued (waits for the send window and daily cap)" or "held in the send-review queue". | supported | replyCopilot.ts:128-130 |
| 39 | When your administrator allows it (`reply_copilot_auto_send_allowed`, off by default), the card shows the option **Auto-send answers to "send me a time" email replies**, which you also have to turn on. | **contradicted** (partly) | The toggle is always shown, whether or not the admin allows auto-send. When not allowed, it is disabled with the text "An administrator has not allowed auto-send on this deployment." (ReplyCopilotPanel.tsx:203-224; replyCopilot.ts:154-158). The setting name and default are right (system_settings.py:323), and the label exists, with " (off by default)." appended (ReplyCopilotPanel.tsx:221). |
| 40 | A draft is then sent without you only if it is an email, the prospect asked for a time, the draft contains your booking link, claim checking changed nothing, and every approval check passes. | supported | reply_copilot.py:829-863. The code has more conditions (intent positive/question, routing finished, not a local-business customer); "Anything else stays waiting" covers them. |
| 41 | Auto-sent answers are automatic sends, so they also wait for that day's send approval… | supported | dsa:199-214 |
| 42 | …their first reply is what stopped the sequence. By default, an answer you approve to their second reply is still sent. | supported | reply_copilot.py:801-805, :1130-1151 |
| 43 | The founders made this a per-account choice: the option **When a prospect wrote twice, still send an approved answer to the later reply**… | supported | docs/program/DECISIONS.md:27; ReplyCopilotPanel.tsx:196 |
| 44 | Turn it off and only answers to the reply that stopped the sequence are sent; an answer to the later reply is cancelled and the reply returns to "Needs reply". | supported | reply_copilot.py:1091-1127, :1256-1274; f04-reply-copilot.md:235-236 |
| 45 | The off setting only ever cancels more. | supported | reply_copilot.py:810-811 |
| 46 | The card, and so this option, appears only in a conversation that has at least one draft. | supported | ReplyCopilotPanel.tsx:59-63 (and only while `reply_copilot_enabled` is on) |
| 47 | There is no control to change a reply's routing class by hand, and correcting a label does not restart a stopped sequence. | supported | Only webhooks_whatsapp.py:473 writes `classification` in app/api; crm.py:1356-1371 changes only the intent label |
| 48 | …then use **Mark handled** in the **Inbox**. | supported | inbox/page.tsx:193 |
| 49 | On the **Replies** tab of the CRM, a reply without a label shows a **Classify** button … updates the reporting label only… | supported | frontend/src/components/crm/CrmChrome.tsx:29; frontend/src/app/(app)/crm/replies/page.tsx:138-142; crm.py:1356-1371 |
| 50 | Only an administrator can remove an entry, on the **Suppression List** page of the admin area. | supported | frontend/src/app/(admin)/admin/layout.tsx:19; app/api/admin.py:209-218 (removal is by email only) |
| 51 | …they can switch off the automated-reply check described above. | supported | system_settings.py:120 |

Summary: 49 supported, 0 unsupported, 2 contradicted.

### 39-daily-send-approval-and-notifications.md
| # | Sentence (verbatim, may be shortened with …) | Verdict | Evidence (path:line) / what the code says |
|---|---|---|---|
| 1 | Before Vectorae sends anything on its own on a given day, a person has to say yes for that channel. | supported | dsa:3-7; outreach_tasks.py:586-597 |
| 2 | The founders decided that nothing Vectorae sends automatically should go out on a day when nobody chose to let it. | supported | DECISIONS.md:25 (LINKEDIN-AUTO), :9 (D1 2026-10-13 addendum) |
| 3 | Daily approval is a safety guard built into the point every message passes … on by default. | supported | outreach_tasks.py:586-611; system_settings.py:406 |
| 4 | One decision covers one channel for one day: email, LinkedIn, WhatsApp or AI phone calls. | **contradicted** (wording) | One decision can approve several channels at once. `approve(channels=[…])` stores them all on one row (dsa:559-601), and the button is "Approve selected channels for today". Approval is per channel per local day. The channel names and labels are right (dsa:63-65). |
| 5 | sequence steps and automatic follow-ups; | supported | dsa:16-20 |
| 6 | re-engagement messages and "not now" return messages; | supported | dsa:19 |
| 7 | Reply Copilot answers sent by auto-send; | supported | dsa:19-20, :208-213 |
| 8 | LinkedIn network messages you queued with a bulk send… | supported | dsa:371-380; app/workers/network_tasks.py:74-82 |
| 9 | a message approved in the send-review queue; | supported | dsa:203-207 |
| 10 | a Reply Copilot answer you approved yourself; | supported | dsa:208-213 |
| 11 | a single LinkedIn network message you send now, an AI call you start with "Call now", and a meeting follow-up email you send yourself. | supported | docs/features/daily-send-approval.md:98-101; dsa:375-376; frontend/src/components/calls/CallHistory.tsx:192 |
| 12 | Anything Vectorae cannot positively identify as a person's decision is treated as automatic. | supported | dsa:20, :212-213 |
| 13 | Open the **Today's automatic sending** page. | supported | frontend/src/app/(app)/send-approval/page.tsx:49 |
| 14 | You reach it from the banner's **Review and decide** button, the link in the notification email, or by tapping the push notification; it has no entry in the main menu. | supported | SendApprovalBanner.tsx:41; dsa:692; frontend/src/lib/deeplinks.ts:139; not in nav.ts. Not a complete list: AutopilotCard.tsx:85,129 also links to it, and non-deciders see the button as "View". |
| 15 | The page shows the date, which time zone your day is counted in, and how many messages are queued today on each channel. | supported | send-approval/page.tsx:103, :112, :144 |
| 16 | Tick the channels you approve and click **Approve selected channels for today**. | supported | send-approval/page.tsx:180-182 |
| 17 | Messages already waiting on those channels are released straight away and the page tells you how many. | supported | dsa:495-512, :626; send-approval/page.tsx:76 |
| 18 | You can add another channel later the same day; earlier approvals stay. | supported | dsa:595-601 |
| 19 | Or click **Decline for today**: nothing automatic is sent today, and you can still approve later the same day. | supported | send-approval/page.tsx:184; dsa:638-642 |
| 20 | Only a workspace owner or manager can decide … a request made with a personal API key is refused. | supported | app/api/send_approval.py:52-68, :88-89 |
| 21 | Other members see … "Only a workspace owner or manager can approve or decline automatic sending." | supported | send-approval/page.tsx:189-191 |
| 22 | Every decision is recorded with who made it and when. | supported | dsa:600-603, :625, :653-664 |
| 23 | LinkedIn is a separate, explicit choice. Its checkbox is never ticked for you… | supported | frontend/src/lib/sendApproval.ts:60-66 |
| 24 | "LinkedIn's User Agreement does not allow automated tools … today?" | supported | dsa:91-97 (exact match) |
| 25 | When you tick LinkedIn, a second checkbox appears: "I understand LinkedIn may restrict … today." You cannot approve LinkedIn without it. | supported | send-approval/page.tsx:159-171; sendApproval.ts:79-84; dsa:578-581 |
| 26 | The warning has a version number … if the warning changed … refused … reload … | supported | dsa:88-90, :584-586, :611, :622-623 |
| 27 | Declining clears the acknowledgement, so approving LinkedIn again later that day asks again. | supported | dsa:658-659; send-approval/page.tsx:65-68 |
| 28 | LinkedIn sending itself has not yet been checked against the live LinkedIn provider… | supported | app/integrations/unipile_linkedin.py:15-16, :71-129 (TODO: verify); DECISIONS.md:9 |
| 29 | They wait. Nothing is failed, cancelled or deleted… | supported | dsa:12-13; outreach_tasks.py:593-594 |
| 30 | Without a decision, or after a decline, each automatic message stays scheduled and moves to the next midnight in your account's time zone. Next day, Vectorae asks again. | supported | dsa:183-191, :316-325, :693-694. "Account's time zone" means the owner's earliest active calendar-availability zone, else UTC (dsa:22-24, :161-180). |
| 31 | If you approved some channels but not this one, the same happens for that channel only. | supported | dsa:309-315 |
| 32 | If Vectorae cannot check the approval … holds the message and tries again in 1 hour. | supported | dsa:79; outreach_tasks.py:600-611 |
| 33 | A held LinkedIn network message stays queued and nothing reaches LinkedIn. | supported | network_tasks.py:79-82; dsa:515-525 |
| 34 | …waiting messages build up, so the queued counts can grow from day to day. | supported | dsa:398-431 (counts include gate-deferred messages, :427-428) |
| 35 | When you approve, released messages go through every normal check again: send window, daily cap, mailbox health, the send-review queue and suppression. | supported | dsa:497-498, :509; outreach_tasks.py:665-743 |
| 36 | Messages over the daily cap wait for the next day. | supported | outreach_tasks.py:729-743 |
| 37 | The approval is only asked for when a message could actually go out now. A message that is still outside the prospect's sending hours does not trigger the request. | supported | outreach_tasks.py:551-573, :590-591 |
| 38 | Autopilot needs daily approval to stay on… | supported | app/services/autopilot.py:31-34 |
| 39 | The first time on a given day that an automatic message is due and nobody has decided, Vectorae notifies the account owner, once that day | supported | dsa:708-727, :316-325 |
| 40 | **Email** … subject "Approve today's automatic sending in Vectorae", with the queued counts per channel and, when LinkedIn is included, the LinkedIn warning. | supported | dsa:685-705, :744-750 |
| 41 | It is sent from Vectorae's own mail service, never from your Gmail. | supported | dsa:746-750 (email_sender, Resend); daily-send-approval.md:41 |
| 42 | **Push notification** to the owner's phones … titled "Approve today's automatic sending". Tapping it opens the approval page. | supported | dsa:761-768; app/services/event_bus.py:152-168; deeplinks.ts:139 |
| 43 | **Slack**, if your account has Slack connected: the same message is also posted to Slack. | supported | event_bus.py:97-98, :117-118. Slack gets the push title and body, not the full email text. |
| 44 | **Banner** at the top of every app page, in the browser and in the Android app, while messages are waiting. It refreshes every 5 minutes. | supported | frontend/src/components/shell/Shell.tsx:167; SendApprovalBanner.tsx:3-6, :21; sendApproval.ts:110-113. It is hidden on /send-approval itself. |
| 45 | Workspace managers can decide, but the email and push go to the account owner only. | supported | dsa:348, :744, :761-762 |
| 46 | There are no browser or desktop notifications and no notification bell… | supported | daily-send-approval.md:49-50; no Notification/PushManager use in frontend/src |
| 47 | …push only works if your deployment has Firebase push set up, and neither push to a real phone nor delivery of this email from the production mail service has been verified yet. | supported | app/services/notifications.py:7-12, :93-112; daily-send-approval.md:373-378 |
| 48 | `daily_send_approval_enabled` (on by default) and `daily_send_approval_channels` … default `email,linkedin,whatsapp,phone`. | supported | system_settings.py:406-416 |
| 49 | If that list contains no valid channel name, every channel is gated. | supported | dsa:150-158 |
| 50 | When approval is off, the page shows "Not required (turned off by an admin)" and messages are not held for approval. | supported | sendApproval.ts:131; dsa:338-339 |
| 51 | Autopilot … cannot be turned on without daily approval, and if approval is switched off later, Autopilot pauses and its messages wait until approval is back. | supported | autopilot.py:31-34, :233-241, :838-848; outreach_tasks.py:641-661 |

I skipped one sentence with no product claim ("The warning is a risk disclosure, not legal advice."). D1 check: consistent with DECISIONS.md:9 (email sends automatically after daily approval; LinkedIn automation not live).

Summary: 50 supported, 0 unsupported, 1 contradicted.

### 44-learn-tab-and-tutorials.md
| # | Sentence (verbatim, may be shortened with …) | Verdict | Evidence (path:line) / what the code says |
|---|---|---|---|
| 1 | Vectorae has a built-in tutorial section with short video lessons. | supported | frontend/src/app/(app)/learn/page.tsx:3-14 |
| 2 | Click **Learn** in the main menu. | supported | nav.ts:55 |
| 3 | The page is called **Learn Vectorae** and lists the tutorials in three levels: **Beginner**, **Intermediate** and **Advanced**. | supported | learn/page.tsx:106; app/services/tutorials.py:58-64 |
| 4 | Each tutorial shows its title, a short description, its length, a progress bar and a **Watch** button (**Resume** …, **Close** …). | supported | learn/page.tsx:297-336 |
| 5 | **Your progress** shows how many tutorials you have finished out of the total, as a number and a percentage, with a count per level. | supported | learn/page.tsx:119-151 |
| 6 | Under it are your badges. | supported | learn/page.tsx:156 |
| 7 | You can type in **Search tutorials** to search titles and descriptions… | supported | learn/page.tsx:161; tutorials.py:261-280 |
| 8 | …or use the level buttons (**All** or one level) to narrow the list. | supported | learn/page.tsx:183-203 |
| 9 | Searching and filtering do not change your overall progress figures. | supported | app/api/tutorials.py:157-170, :304 |
| 10 | The standard set that Vectorae's setup script adds has nine tutorials, three per level, on topics such as … | supported | scripts/seed_tutorials.py:44-152 |
| 11 | Your Vectorae administrator can add, edit and remove tutorials on the **Tutorials** page of the admin area… | **contradicted** (partly) | The admin Tutorials page (frontend/src/app/(admin)/admin/tutorials/page.tsx) offers edit, publish/unpublish and delete, but has no add/create form. Creating exists only as API `POST /admin/tutorials` (app/api/admin.py:435) and `adminApi.createTutorial` (frontend/src/lib/api/admin.ts:93), which no page calls. |
| 12 | Your progress is saved per video as you watch: where you stopped, and how much you have seen. | supported | api/tutorials.py:348-371 |
| 13 | **Resume** starts from where you stopped; a tutorial you have finished plays from the beginning. | supported | frontend/src/components/tutorials/VideoPlayer.tsx:187-192 |
| 14 | Going back in a video moves your resume point but never reduces how much you have watched. | supported | api/tutorials.py:348-349, :367 |
| 15 | A tutorial counts as finished once you have watched 90% of it. | supported | api/tutorials.py:43-50, :370-371 |
| 16 | You can also click **Mark complete** … and **Reset progress** to start a tutorial again. | supported | learn/page.tsx:344-361; api/tutorials.py:377-414 |
| 17 | There are four badges: **Beginner Complete**, **Intermediate Complete**, **Advanced Complete** … **Vectorae Certified**… | supported | tutorials.py:209-218 |
| 18 | Badges are worked out from your progress each time, so resetting a tutorial removes the badge it earned. | supported | tutorials.py:194-197; api/tutorials.py:397 |
| 19 | Your progress is private … Administrators can see only totals (how many people finished or started each video)… | supported | api/tutorials.py:10-14; admin.py:576-635 |
| 20 | Your tutorial progress is included in your account export and deleted when your account is erased. | supported | app/services/account_export.py:111; app/services/account_erasure.py:157, :168 |
| 21 | The videos are on YouTube and are played … through YouTube's privacy-enhanced embed (youtube-nocookie.com). | supported | VideoPlayer.tsx:165-171. The IFrame API script itself loads from www.youtube.com (:45). |
| 22 | Vectorae stores only each video's YouTube ID, not the video itself. | supported | seed_tutorials.py:16-21; tutorials.py:313 |
| 23 | An administrator adds or changes a video by setting that ID on the **Tutorials** admin page; no new release … is needed. | supported | admin/tutorials/page.tsx:7, :50-61, :98-105 |
| 24 | The videos can be Unlisted … but they cannot be Private… | supported | scripts/TUTORIAL_VIDEO_URLS.md:18-19; docs/features/tutorial-section.md:121-122 |
| 25 | …it plays only where your browser and network can reach YouTube. | supported | VideoPlayer.tsx:45, :171 |
| 26 | **"Coming soon" and "This video is not published yet".** The tutorial is listed but no video has been added yet. | supported | learn/page.tsx:304-306; VideoPlayer.tsx:220-233 |
| 27 | The tutorials in the standard set were published without videos… | supported | seed_tutorials.py:183, :186 |
| 28 | You can still click **Mark complete**. | supported | learn/page.tsx:344-349; VideoPlayer.tsx:228-230 |
| 29 | **"Progress tracking is unavailable"**, with the video still playing. Your browser blocked YouTube's player script … click **Mark complete** when you finish. | **contradicted** | `loadYouTubeApi()` (VideoPlayer.tsx:76-95) only ever resolves: no `script.onerror`, no timeout. If an ad blocker or filter blocks the script, the promise stays pending, `.catch` (:200-202) never runs and `apiFailed` stays false. The user gets no fallback iframe (:244-259), no "Progress tracking is unavailable" message (:261-267), and an empty black player box (:238-243). The fallback is reached only if `new YT.Player` throws. The spec claims the fallback works (tutorial-section.md:195), but the code says otherwise and no test exercises it. |
| 30 | **YouTube's own error, such as "Video unavailable"** … The video ID is wrong or the video is set to Private… | supported | tutorial-section.md:36, :194; VideoPlayer.tsx:9-12 |

Summary: 28 supported, 0 unsupported, 2 contradicted.

### 29-known-limitations.md (Support chat bullet only, line 106)
| # | Sentence (verbatim, may be shortened with …) | Verdict | Evidence (path:line) / what the code says |
|---|---|---|---|
| 1 | **Support chat** is limited to 30 messages per person per day on Vectorae's hosted service (a deployment setting; the built-in default is 20). | supported | render.yaml:133-135 (api) and :233-235 (worker) `RATE_LIMIT_SUPPORT_CHAT: "30"`; app/core/config.py:13, :358 (default 20); app/api/support.py:42, :231-245 (per user id, 86,400 s window). The window is a 24 h counter from the first message (app/core/rate_limiting.py:45-60), not a calendar day. |
| 2 | Tickets are not limited. | supported | app/api/support.py:364-376 (no rate limit on POST /tickets) |

Summary: 2 supported, 0 unsupported, 0 contradicted.

### 30-contact-support-and-status.md (chat-messages-per-day sentence only, line 65)
| # | Sentence (verbatim, may be shortened with …) | Verdict | Evidence (path:line) / what the code says |
|---|---|---|---|
| 1 | You can send 30 chat messages per day on Vectorae's hosted service. | supported | render.yaml:133-135, :233-235; app/api/support.py:231-245 |
| 2 | This is a deployment setting: the hosted service sets 30, and the built-in default is 20. | supported | app/core/config.py:13, :358; render.yaml:135 |

Summary: 2 supported, 0 unsupported, 0 contradicted.

### Outside the requested scope (not fixed, just reported)
- **Stale in-app copies of articles 29 and 30:** frontend/src/content/help-center/29-known-limitations.md:105 and frontend/src/content/help-center/30-contact-support-and-status.md:64 still say 20 chat messages per day. The Help AI reads docs/help-center (app/services/help_center.py:51-54, :361-369), but these frontend copies will now disagree with docs/help-center.
- **Blocked-script fallback (article 44, row 29):** the spec docs/features/tutorial-section.md:195 says the plain-iframe fallback works, but the code does not deliver it. This is a real UX bug: users with an ad blocker get a blank player and no message.
- **Reply Copilot spec (article 38, row 35):** the f04 spec (docs/features/f04-reply-copilot.md:166-169) correctly calls the 5 minutes a "dispatch guard". The article misreads it as a wait.

---

## Report: 40-41

## Fact-check report: help-center articles 40 and 41

All 17 source paths cited by article 40 and all 19 cited by article 41 exist (checked with Glob).

Verdicts: article 40 has no wrong or unsupported sentences. Article 41 has two minor wording errors (rows 3 and 34a). Both are fixable by changing a few words.

### 40-annual-billing-and-plan-changes.md
File: /home/user/LeadPilot/docs/help-center/40-annual-billing-and-plan-changes.md

| # | Sentence (verbatim, may be shortened with …) | Verdict | Evidence (path:line) / what the code says |
|---|---|---|---|
| 1 | "The annual option is switched off by default (… `annual_billing_enabled` starts off), and an administrator turns it on." | supported | app/services/system_settings.py:375 (default `False`); app/core/billing_catalog.py:15 |
| 2 | "When it is off, the **Pricing** page shows no **Monthly** / **Annual** toggle" | supported | app/core/billing_catalog.py:219 (the `annual` block is only added when the flag is on); frontend/src/app/pricing/PricingClient.tsx:140,213 |
| 3 | "…an annual checkout is refused with "Annual billing is not offered right now."" | supported | app/services/billing.py:292 (exact text, HTTP 409) |
| 4 | "An annual plan costs 10 times the monthly price, billed once a year…" | supported | app/core/billing_catalog.py:49 (`ANNUAL_MONTHS_CHARGED = 10`), :136, :151 (interval "year") |
| 5 | "The toggle says **Annual · 2 months free**." | supported | frontend/src/app/pricing/PricingClient.tsx:222 (worked out as 12 - months_charged = 2) |
| 6 | Savings table: Starter $298, Growth $698, Scale $1,398, Enterprise $2,998 | supported | app/core/billing_catalog.py:81,88,95,102 (14 900 / 34 900 / 69 900 / 149 900 cents); :167 savings = monthly×12 − monthly×10, so 2×$149=$298, 2×$349=$698, 2×$699=$1,398, 2×$1,499=$2,998. Matches docs/features/annual-billing.md:56-59 |
| 7 | "An annual plan has exactly the same limits as the monthly plan of the same tier" | supported | app/core/billing_catalog.py:173-183 (`plan_for` gives the same PLANS key) |
| 8 | "…gets the same once-per-account 14-day free trial" | supported | app/core/billing_catalog.py:35 (`TRIAL_DAYS = 14`); app/services/billing.py:183,194-198,363 |
| 9 | "…renews automatically every year until you cancel." | supported | app/core/billing_catalog.py:17,151 |
| 10 | "There is no annual version of Pay per meeting or Free." | supported | app/core/billing_catalog.py:128-131 (annual only for priced monthly tiers), :77-106 (no Free tier) |
| 11 | "Vectorae never moves you to annual by itself; only you can choose it, at checkout." | supported | docs/features/annual-billing.md:138-145; app/services/billing.py:504-509 (the billing model only changes for subscriptions with checkout metadata) |
| 12 | "Before an annual plan renews, the account owner gets an email 30 days ahead with the amount and the date." | supported | app/core/billing_catalog.py:64 (`RENEWAL_NOTICE_DAYS = 30`); docs/features/annual-billing.md:177-216. Note: no notice for stub-mode subscriptions, and email delivery depends on the unverified Resend/SPF/DKIM setup (GAP-007) |
| 13 | "Online payment through Stripe is marked "simulated only"…" | supported | frontend/src/content/product-facts.json:72 (`stripe_checkout` status `simulated_only`), :54 |
| 14 | "…the **Pricing** page shows the prices but … says "Online checkout opens soon. To start now, book a call." with a **Book a call** button." | supported | frontend/src/lib/productFacts.ts:42-43; frontend/src/app/pricing/PricingClient.tsx:280-302,365-373; frontend/src/app/pricing/page.tsx:45-49 |
| 15 | "So today, starting a paid plan, switching … goes through a conversation with the Vectorae team" | supported | Follows from row 14 (no checkout button while `CHECKOUT_LIVE` is false) |
| 16 | "On a production deployment where payments are not set up at all, choosing a plan fails with a message saying payments are not configured." | supported | app/api/billing.py:98-100 ("payments are not configured; plans cannot be changed right now", 503) |
| 17 | "Moving up and moving down work the same way … change happens as soon as that checkout is completed. There is no option to schedule a change…" | supported | app/services/billing.py:286-388 (one checkout path, no scheduling parameter), :585-623 (the switch is applied when the checkout completes) |
| 18 | "Your account gets the new plan's limits straight away." | supported | app/services/billing.py:621 (`_sync_plan` runs when the checkout completes) |
| 19 | "The subscription being replaced is cancelled at once, so you are never billed for two plans." | supported | app/services/billing.py:585-591 (`cancel_subscription_now(previous)`) |
| 20 | "If you leave the checkout page without finishing, nothing changes…" | supported | app/services/billing.py:376-379 |
| 21 | "The free trial is once per account. If you are in a trial and switch, the trial of the old plan ends … and the new plan does not get a second 14-day trial." | supported | app/services/billing.py:194-198,363 (`trial_days=0 if used_trial`); frontend/src/lib/pricing.ts:323-325. Small gap: during an active pilot, a pilot-extended trial is still given (billing.py:180-187) |
| 22 | "If you choose the plan you are already on, you see "You are already on this plan."" | supported | app/services/billing.py:300 |
| 23 | "…cancel instead (**Profile**, **Plan** card, **Cancel plan**). You keep the current plan until that date, then the account returns to Free" | supported | frontend/src/components/billing/PlanCard.tsx:47,62-65; app/services/billing.py:424-430; frontend/src/lib/pricing.ts:305. Small gap: a past-due plan is cancelled immediately (billing.py:413-423) |
| 24 | "Vectorae does not refund or credit the unused part of a period when you switch." | supported | app/services/billing.py:227-230,585-591 |
| 25 | "The Pricing page warns you of this before checkout: "The unused part … (prorated changes are not available online yet)."" | supported | frontend/src/lib/pricing.ts:327-329; frontend/src/app/pricing/PricingClient.tsx:183-188. Only shown when there is a non-stub monthly or annual subscription that is active or past due |
| 26 | "No refunds are issued by the product itself." | supported | docs/features/annual-billing.md:246 |
| 27 | "Once an annual year has been paid, you cannot start a checkout … "Your annual plan is paid until (date). Changing it before then needs a prorated refund…"" | supported | app/services/billing.py:227-239,295-297 (exact text, uses " - ") |
| 28 | "During the free trial of an annual plan nothing has been paid, so you can switch like a monthly customer." | supported | app/services/billing.py:76 (`PAID = active, past_due`), :231 |
| 29 | "If a checkout you opened earlier is completed after the year was paid, both are kept … the **Plan** card says the team will contact you…" | supported | app/services/billing.py:562-583; frontend/src/components/billing/PlanCard.tsx:51-56 |
| 30 | "Cancelling a paid year stops the next renewal, and you keep the plan until the year ends. A year already paid is not refunded." | supported | app/services/billing.py:424-430; frontend/src/lib/pricing.ts:212-213 |
| 31 | "Nothing you built is deleted or cancelled. The lower plan's limits apply from the moment the plan changes…" | supported | app/services/plan_holds.py:25-31,43-46 |
| 32 | "**Strategies:** … Creating a new one is refused while you have as many as the new plan allows or more." | supported | app/api/strategies.py:194-202; app/core/plans.py:238 (`current_count >= limit`) |
| 33 | "**Leads:** … Sourcing more for a strategy that is at or over the new limit is refused." | supported | app/api/leads.py:94-105 |
| 34 | "**Sequences:** a sequence is not stopped, but one that has more steps or uses a channel the new plan does not include cannot be launched again." | supported | app/api/sequences.py:61-83,444,574; app/services/plan_holds.py:30 |
| 35 | "**Scheduled messages:** each one is checked again when it comes due … held, not sent and not deleted. Its reason starts with "plan_limit:". Steps your plan still covers keep sending." | supported | app/services/plan_holds.py:13-31,101-122; app/services/send_holds.py:35 (`"plan_limit: "`) |
| 36 | "**After an upgrade:** a background check runs every 15 minutes and releases held messages … They then go through all the usual checks" | supported | app/workers/celery_app.py:489-495 (`crontab(minute="11,26,41,56")`); app/services/plan_holds.py:48-53 |
| 37 | "Messages in sequences enrolled before 12 October 2026 are not held this way." | supported | app/services/plan_holds.py:89 (2026-10-12 00:00 UTC), :147-149. Admin accounts and person-approved Reply Copilot answers are also exempt (:33-41); the article does not mention this |
| 38 | "Your daily AI limit also changes to the new plan's." | supported | app/core/plans.py:45,65,81,99,114 (`max_ai_spend_usd_per_day` is set per plan) |

Summary: 38 supported, 0 unsupported, 0 contradicted.

Founder decision D1 does not apply to this article: it makes no claims about outreach.

### 41-benchmarks-what-good-looks-like.md
File: /home/user/LeadPilot/docs/help-center/41-benchmarks-what-good-looks-like.md

| # | Sentence (verbatim, may be shortened with …) | Verdict | Evidence (path:line) / what the code says |
|---|---|---|---|
| 1 | "Vectorae has no fixed target reply rate and never labels your reply rate as good or bad on its own." | supported | No reply-rate target or label found anywhere in app/ (grep). frontend/src/components/analytics/BenchmarkPanel.tsx:20-24 shows numbers only |
| 2 | "On **Analytics**, **How you compare** shows your reply rate next to the median and the "Middle half" (25th to 75th percentile)…" | supported | frontend/src/app/(app)/analytics/page.tsx:186; BenchmarkPanel.tsx:44,82-99; app/services/benchmarks.py:215-217 |
| 3 | "…of other accounts on your Vectorae deployment…" (repeated in the meeting-rate bullet) | contradicted (minor) | app/services/benchmarks.py:190-203: the snapshot includes every account that is not suspended, including the viewer's own. It is "accounts on your deployment", not "other accounts" |
| 4 | "…over the last 90 days." | supported | app/services/system_settings.py:263 (default 90; an admin can set 7-365, benchmarks.py:86) |
| 5 | "Your own rate is shown only once you have at least 30 sends on that channel." | supported | app/services/system_settings.py:261; app/services/benchmarks.py:268; BenchmarkPanel.tsx:95 |
| 6 | "Vectorae treats this as an observation about its own customers, not an industry statistic." | supported | app/services/benchmarks.py:3-8,292-293 |
| 7 | "On **Campaigns**, the **Funnel** tab names your **Best converting step**: the step with the highest reply rate, counted only once a step has been sent to at least 20 leads." | supported | app/services/funnel.py:41,163-166; frontend/src/components/campaigns/FunnelHeatmap.tsx:54,60-61; frontend/src/app/(app)/campaigns/page.tsx:522 |
| 8 | "Reply rate is 35% of the score and counts as its raw percentage, so a 10% reply rate earns 10 of 100 points on that part." | supported | app/services/pipeline_health.py:54,195,200. Note: the part score is 10/100, but it adds only 3.5 points to the total (10 × 0.35). The sentence is correct but could be misread |
| 9 | "A reply rate also counts replies such as "remove me"." | supported | app/services/reply_intent.py:293,325 (`reply_rate` = all replies / sent) |
| 10 | "The **Positive reply rate** on **Analytics** counts only replies labelled interested" | supported | app/services/reply_intent.py:294,326; frontend/src/components/analytics/ReplyQualityPanel.tsx:53; analytics/page.tsx:96 |
| 11 | "**A whole campaign** is paused when its bounce rate goes over 3%, judged only once at least 10 messages have been sent." | supported | app/config.py:114-115; app/services/sequence_engine.py:769,782 (`rate > threshold`) |
| 12 | "The rate is bounces divided by all messages the campaign has sent." | supported | app/services/sequence_engine.py:763-776 (bounced outcomes / messages SENT or BOUNCED, all time) |
| 13 | "A compliance rule in your workspace can set a lower limit, never a higher one." | supported | app/services/compliance_rules.py:134,229-230,245-249 |
| 14 | "On **Campaigns** the **Bounce rate** turns red when it is over the limit" | supported | frontend/src/app/(app)/campaigns/page.tsx:478-480; frontend/src/lib/campaignBounce.ts:20-22 |
| 15 | "…a paused campaign shows "Bounce rate auto-pause: … is above the …% limit. Fix deliverability issues, then resume."" | supported | frontend/src/lib/campaignBounce.ts:24-27; campaigns/page.tsx:446-447 |
| 16 | "You also get a notification." | supported | app/services/sequence_engine.py:795-814 |
| 17 | "The campaign stays paused until a person resumes it." | supported | app/services/sequence_engine.py:782,792-794; campaigns/page.tsx:451 |
| 18 | "**A single mailbox** is judged on its own bounces over the last 30 days" | supported | app/services/mailbox_health.py:90,160-173 |
| 19 | "2% or more takes 35 points off … leaves 65, which is **throttled** (sending slowed to a quarter of its normal allowance)." | supported | app/services/mailbox_health.py:97,265-267,83-84,87,285-288. The throttled cap is never below 2 (`MIN_THROTTLE_CAP`) |
| 20 | "5% or more takes 65 points off … leaves 35, which is **paused**: that mailbox sends nothing until you click **Resume**." | supported | app/services/mailbox_health.py:98,262-264,84,376-382,492-504; frontend/src/components/settings/MailboxHealthCard.tsx:127-130 |
| 21 | "Missing DNS records or a high complaint rate take further points off, so a mailbox can be paused at a lower bounce rate." | supported | app/services/mailbox_health.py:237-260 (a volume spike also costs 10 points, :269-272) |
| 22 | "The mailbox check has no minimum number of sends…" | supported | app/services/mailbox_health.py:164-166 (returns None only when there are 0 sends) |
| 23 | "…complaint rate (its proxy: unsubscribes plus stop requests) of 0.1% as a warning and 0.3% as the danger line." | supported | app/services/mailbox_health.py:21-27,95-96,176-206,255-260 |
| 24 | "Vectorae has three scores out of 100" | supported | pipeline_health.py:202; mailbox_health.py:274; deliverability.py:187 |
| 25 | Pipeline Health: "**Pipeline health** card on a verified strategy's page", "0–40 critical, 41–60 low, 61–80 moderate, 81–100 strong" | supported | app/services/pipeline_health.py:75-80,88-98; frontend/src/app/(app)/strategies/detail/page.tsx:138-142 (shown for verified and executing strategies); PipelineHealthCard.tsx:32 |
| 26 | Mailbox health: "**Mailbox health** card under **Settings**", "70 or more healthy, 40–69 throttled, under 40 paused" | supported | app/services/mailbox_health.py:83-84,277-282; frontend/src/app/(app)/settings/page.tsx:545; MailboxHealthCard.tsx:67 |
| 27 | Email health: "**Email health** card under **Settings**", "under 70 gives a warning, also when you launch a campaign" | supported | app/services/system_settings.py:115 (default 70); app/services/deliverability.py:263-269,320-330; app/api/sequences.py:469; frontend/src/components/settings/DeliverabilityCard.tsx:110; settings/page.tsx:546 |
| 28 | "…treats 61 and up as healthy ("Pipeline healthy. Maintain your cadence.") and 81 and up as strong." | supported | app/services/pipeline_health.py:78-79 |
| 29 | "Because the reply part uses the raw percentage, a normal cold-outreach campaign earns few points there, so a score in the moderate band is not a bad result." | supported (derived) | app/services/pipeline_health.py:53-58,195. The other three parts can give at most 65 points, so a perfect pipeline with a 5% reply rate scores about 67 (moderate) |
| 30 | "Look at the four parts on the card, not only the total." | supported | frontend/src/components/strategy/PipelineHealthCard.tsx:12-17,39-42 |
| 31 | "For a mailbox, 70 is the line between full speed and slowed down." | supported | app/services/mailbox_health.py:36-40,83 |
| 32 | "A mailbox missing SPF, DKIM and DMARC but with no bounce or complaint problems scores 45: throttled, not paused." | supported | app/services/mailbox_health.py:237-250: −25 SPF, −20 DMARC, −10 DKIM = 55, so the score is 45 (also stated at :77-82,253-254). Assumes no volume spike (−10 would give 35, which is paused). Consumer domains such as gmail.com are not DNS-scored (:324-328) |
| 33 | "For the domain, 70 is the threshold for a warning" | supported | app/services/system_settings.py:115 (admin-configurable) |
| 34a | "…once a domain's bounce rate over the last 30 days…" | contradicted (minor) | app/services/deliverability.py:150-163,220,231: the bounce rate is the whole account's (all the user's sends), and that one figure is applied to every sending domain. It is not measured per domain |
| 34b | "…is above 2%, it costs one point for every 0.1 percentage point of the whole rate (2.5% costs 25 points), up to 30 points." | supported | app/services/deliverability.py:180-182: `bounces > 0.02`, `penalty = min(30, int(round(bounces*1000)))`, and round(0.025×1000) = 25 |
| 35 | "Vectorae does not set a target for meetings booked, and nothing pauses or alerts on a low meeting rate." | supported | No meeting-rate threshold, pause or alert found (grep of `meeting_rate`/`booking_rate` in app/ finds only reporting code) |
| 36 | "**Meeting-booked rate** (meetings booked divided by messages sent or bounced) … the last 90 days, at least 30 sends from you, and enough other accounts to publish a comparison." | supported | app/services/benchmarks.py:30-32,68-71; BenchmarkPanel.tsx:22; system_settings.py:259-263 (publishing needs at least 10 accounts by default and never fewer than 5, benchmarks.py:74,84). The "other accounts" wording has the same problem as row 3 |
| 37 | "If too few accounts qualify, you see "Not enough accounts yet to publish a benchmark for this channel."" | supported | frontend/src/components/analytics/BenchmarkPanel.tsx:66-69 |
| 38 | "The **Funnel** tab on **Campaigns** shows a booking rate for each step of each sequence" | supported | app/services/funnel.py:159; FunnelHeatmap.tsx:24 (the column is labelled "Booked") |
| 39 | "Bounce rate is the one metric in **How you compare** where lower is better." | supported | BenchmarkPanel.tsx:20-24 (`lowerIsBetter` set only on bounce_rate) |
| 40 | "the **Sentiment** tab shows the share of human replies by week (out-of-office, bounces and automated responses are left out)." | supported | app/services/reply_sentiment.py:3-12,34-41,86-89; campaigns/page.tsx:525-526 |
| 41 | "**Objection spike** alert … both weeks have at least 10 human replies, … rose by more than 20% (relative), and … at least 5 percentage points." | supported | app/services/reply_sentiment.py:14-18,42,93-102; system_settings.py:60-65; SentimentTrend.tsx:47 |
| 42 | "If the earlier week had no objections, the 5-point rise alone is enough." | supported | app/services/reply_sentiment.py:102 (`p == 0 or …`) |
| 43 | "Each campaign week alerts once." | supported | app/services/reply_sentiment.py:21-22,166-171 |
| 44 | "Vectorae treats a smaller change as normal week-to-week noise, so no alert means the change was below these lines…" | supported | app/services/reply_sentiment.py:19-21 |
| 45 | "Your administrator can change the 20% and the 10-reply minimum for the whole deployment." | supported | app/services/system_settings.py:60-65 |

Summary: 44 supported, 0 unsupported, 2 contradicted.

Suggested fixes for article 41 (the article was not edited):
- **Rows 3 and 36:** change "other accounts" to "accounts on your deployment (yours included)".
- **Row 34a:** change "a domain's bounce rate" to "your account's bounce rate across all your sends".
- **Row 8 (optional):** add that the 10 part-points add 3.5 to the total score.

Founder decision D1 does not apply to this article: it makes no claims about the research pipeline or about sending outreach automatically.

---

## Report: 42-43

## Fact-check: help-center articles 42 and 43

All front-matter `sources` paths in both articles exist (checked with Glob). I did not edit any files.

Founder decision D1 (outreach sends automatically; research runs once per strategy) is not mentioned in either article, so neither conflicts with it.

### 42-security-faq-for-buyers.md
| # | Sentence (verbatim, may be shortened with …) | Verdict | Evidence (path:line) / what the code says |
|---|---|---|---|
| 1 | Vectorae never stores your password … PBKDF2-HMAC-SHA256 at 600,000 iterations, with a random 16-byte salt | supported | app/services/auth.py:32, :55-57 |
| 2 | …compared in constant time | supported | app/services/auth.py:74 (`hmac.compare_digest`) |
| 3 | Passwords must be at least 8 characters. | supported | app/services/auth.py:53; app/api/auth.py:92, :505, :570 |
| 4 | Sign-in uses signed tokens (JWT, HS256). | supported | app/services/auth.py:5, :90, :160 |
| 5 | A short-lived access token … a longer-lived refresh token renews it. | supported | app/config.py:167 (900 s), :171 (30 days), :174 (12 h when not persistent) |
| 6 | Refresh tokens are tied to a session record on the server, so signing out really ends the session | supported | app/services/auth_sessions.py:3-7; app/api/auth.py:463-468 |
| 7 | …each refresh token can be used only once. | supported | auth_sessions.py:9-11. One detail: within a short grace window (AUTH_REFRESH_REUSE_GRACE_SECONDS, line 12-16) a second use gets an access token but no new refresh token. |
| 8 | If an already-used refresh token turns up again … the whole session is signed out and the event is written to the security log. | supported | auth_sessions.py:11-15; security_audit.py:64 (`auth.refresh_reuse_detected`). This only happens after the grace window. |
| 9 | In the web app the refresh token is kept in an HttpOnly cookie | supported | app/api/auth.py:13, :144, :154 |
| 10 | Vectorae keeps only a SHA-256 fingerprint of each key, plus its first few characters | supported | app/services/api_keys.py:31, :41 (`prefix=plaintext[:12]`) |
| 11 | The full key is shown once … cannot be shown again | supported | app/services/api_keys.py:4 |
| 12 | Access tokens for connected services (… Gmail, WhatsApp, Calendly, … Apollo or Hunter keys) are encrypted … Fernet … key set on the server, never in the code | supported | app/core/crypto.py:2-16, :47-57; app/integrations/gmail.py:194; app/integrations/token_store.py:107; render.yaml:94 (`sync: false`) |
| 13 | The encryption key can be rotated: … previous key used only to read old values, and can be removed afterwards. | supported | app/core/crypto.py:10-11, :40-45, :123-127 |
| 14 | Webhook signing secrets are stored encrypted the same way. | supported | app/services/webhook_delivery.py:58, :231 |
| 15 | A secret starts with `whsec_` and is shown once, when you create the webhook. | supported (in-app) | webhook_delivery.py:216-217, :230; WebhooksCard.tsx:32, :86. Note: an API caller can supply its own secret (app/api/webhook_targets.py:43, :120), and that secret need not start with `whsec_`. |
| 16 | Your data export leaves all of these out … no password hash, no key fingerprints, no encrypted tokens and no webhook secrets. | supported | app/services/account_export.py:16-17, :191-194 |
| 17 | Every webhook delivery is signed with the webhook's own signing secret. | supported | webhook_delivery.py:368-375 |
| 18 | `X-LeadPilot-Event` … `X-LeadPilot-Delivery` … use it to ignore a retry | supported | webhook_delivery.py:19-20, :372-373 |
| 19 | `X-LeadPilot-Signature`: `t=<unix time>,v1=<signature>`, HMAC-SHA256 of the time, a dot, and the raw body | supported | webhook_delivery.py:21, :256-258 |
| 20 | …reject a timestamp more than 300 seconds (five minutes) old | supported | webhook_delivery.py:94, :271 |
| 21 | An older `X-ClientHunter-Signature` header (HMAC-SHA256 of the body alone) is still sent | supported | webhook_delivery.py:22, :276-277, :375 |
| 22 | A delivery that fails is retried, up to 6 attempts in all. | supported | webhook_delivery.py:26-27, :90-92. A 410 response and a blocked (non-public) host stop retries early (:360-365, :389-395). |
| 23 | **Settings**, **Integrations** tab, **Webhooks (Zapier, Make)** card | supported | frontend/src/lib/settings-tabs.ts:16; settings/page.tsx:411, :526 (label is the tab id, shown capitalised), :539; WebhooksCard.tsx:77 |
| 24 | Two features make Vectorae call an address you give it: outgoing webhooks, and **Quickstart** | supported | app/services/safe_fetch.py:4-12. Note: admin-set hosts for AegisAudit and SIGNALFORGE (default 127.0.0.1, app/services/tool_integrations.py:95, :145) are a deployment-admin setting, not a customer input. |
| 25 | the address must use `https` | supported | webhook_delivery.py:181 |
| 26 | it may not contain a user name or password | supported | webhook_delivery.py:186 |
| 27 | `localhost` and names ending in `.localhost`, `.local` or `.internal` are refused | supported | webhook_delivery.py:188 |
| 28 | a raw IP address is refused unless it is a public internet address … (including the cloud metadata address) | supported | webhook_delivery.py:32-35, :193-198 (`is_global`) |
| 29 | at every delivery the host name is looked up again … refused if it points to any non-public address | supported | webhook_delivery.py:207-213, :360-365 |
| 30 | redirects are not followed | supported | webhook_delivery.py:34-35, :341 |
| 31 | Quickstart: same rules, plus only port 443, at most 3 redirects (each checked), 8-second limit, at most 512,000 bytes; `http://` upgraded | supported | safe_fetch.py:53-56, :105-120, :196-210 |
| 32 | One gap remains … DNS rebinding … needs an outbound proxy, which is not in place. | supported | webhook_delivery.py:36-37; safe_fetch.py:28-30 |
| 33 | The activity audit trail covers … every send, open, click, reply and booked meeting | supported | app/services/audit_trail.py:3-5, :53 |
| 34 | Each record holds ids, step, variant, classification, never an email, name or text … survives a GDPR erasure | supported | audit_trail.py:9-11, :56-57 |
| 35 | Records are hash-chained … SHA-256 … editing, deleting or inserting breaks the chain | supported | audit_trail.py:13-21, :99-104 |
| 36 | The application refuses edits and deletes, and in PostgreSQL a database trigger refuses them even for direct SQL. | supported | audit_trail.py:23-25 |
| 37 | **Settings**, **Deliverability** tab, **Activity audit trail** card has **Verify chain**, **Signed JSON**, **PDF report** | supported | settings/page.tsx:541-551; AuditTrailCard.tsx:38, :50, :54, :58 |
| 38 | JSON report signed with Ed25519; public key published by the API; checkable offline or through the API without an account | supported | audit_trail.py:29-32; app/api/audit.py:7-8, :78-83 |
| 39 | The security log records … sign-outs, password changes and resets, reuse, exports and refused exports, deleted strategies, network imports/deletions, account deletion | supported | app/services/security_audit.py:27, :52-64, :73-78 |
| 40 | There is no screen for it in the app; it is included in your account data export. | supported | account_export.py:104; no frontend reference to security_audit_events. The admin route /admin/security-events (app/api/admin.py:800) reads a different table (account_security_events). |
| 41 | Neither record logs every field edit … | supported (nothing found) | No field-edit action in security_audit.py:27-78; audit trail events are limited to audit_trail.py:53 |
| 42 | … API and worker on Render (Oregon), database on Neon, queue/cache on Upstash, web app on Vercel | supported | render.yaml:6-12, :40, :152 |
| 43 | `sslmode=require` for the database and `rediss://` (TLS) for Redis | supported | render.yaml:77, :86, :88 (comments on secret env vars; the values are pasted in by hand) |
| 44 | The founders' design decision is that one deployment serves one customer organisation. | supported | docs/program/DECISIONS.md:19, :47-51 |
| 45 | The production deployment keeps public sign-up open, so … accounts from different customers share one database | supported | DECISIONS.md:67 |
| 46 | …ownership checks … the automated tests check … not yet proven on PostgreSQL | supported (docs only) | docs/help-center/29-known-limitations.md:115; CLAUDE.md (offline suite runs on SQLite) |
| 47 | No security certification … SOC 2, ISO 27001 | supported (nothing found) | No such claim in app/ or frontend/src |
| 48 | No two-factor sign-in, and no single sign-on. | supported (nothing found) | No TOTP/MFA/SAML/SSO code in app/ or frontend/src |
| 49 | No list of active sessions. | supported (nothing found) | No session-listing route in app/ |
| 50 | Changing or resetting the password signs out everywhere and revokes API keys. | supported | app/api/auth.py:540-554; app/services/password_reset.py:18-20 |

Summary: 50 supported, 0 unsupported, 0 contradicted. The notes in rows 7, 8, 15 and 22 are wording details, not errors.

### 43-data-processing-and-subprocessors.md
| # | Sentence (verbatim, may be shortened with …) | Verdict | Evidence (path:line) / what the code says |
|---|---|---|---|
| 1 | This article lists the outside companies that store or process data for Vectorae … | contradicted (list incomplete) | The code also sends data to providers this article never names: NewsAPI (prospect company name; app/integrations/newsapi.py:24, app/services/personalization_context.py:6, app/services/credentials.py:80); Vapi.ai and ElevenLabs (prospect phone numbers, call prompts, voicemail audio, voice-clone samples; app/integrations/voice_providers.py:1-31, credentials.py:100-104); Mailreach (app/integrations/mailreach.py:18, credentials.py:125); Google Postmaster Tools, Calendar/Meet and Firebase Cloud Messaging (app/integrations/google_postmaster.py:13, app/integrations/google_meet.py, app/services/notifications.py); RapidAPI (app/integrations/linkedin_posts.py); AegisAudit, PostIQ (script.google.com) and SIGNALFORGE (app/services/tool_integrations.py:22). frontend/src/app/privacy/page.tsx:130-141 lists all of them. |
| 2 | Neon … the main database. Everything Vectorae stores lives here … | supported (minor caveat) | render.yaml:10, :77. Caveat: voicemail audio is written to a local `voicemails` directory (app/services/phone_calls.py:104; app/services/account_erasure.py:375), not to Neon. |
| 3 | Upstash … job queue … short-term cache … holds answers from the contact-finding providers | supported | render.yaml:11, :86-90; app/integrations/apollo.py:92, :126; app/integrations/hunter.py:62, :72 |
| 4 | Render: runs the Vectorae API and the background worker | supported | render.yaml:8-9, :36-40, :148-152 |
| 5 | Render's request logs record IP addresses. | supported (docs only) | privacy/page.tsx:75, :217 |
| 6 | Vercel: hosts the web app | supported | render.yaml:12 |
| 7 | Anthropic: writes research, strategies and message drafts, and classifies replies | supported | app/services/message_personalization.py:164; app/services/reply_classification.py:81; render.yaml:96 |
| 8 | Resend: sends … sign-up verification and password-reset links … receives your email address and the content | supported | render.yaml:113-122; app/services/password_reset.py:63, :235 |
| 9 | The public **Privacy** page lists the same providers. | contradicted (minor) | privacy/page.tsx:124-127 lists Stripe under "Always in use" as well. This article puts Stripe in the feature-only list (row 33). |
| 10 | …API and the worker on Render in the Oregon region, in the United States … | supported | render.yaml:40, :152 |
| 11 | The code does not record which Neon or Upstash region … Privacy page states … EU and the United States | supported | render.yaml:77-90 (no region set); privacy/page.tsx:113-115 |
| 12 | The **Privacy** page says that transfers … rely on … Standard Contractual Clauses. | supported | privacy/page.tsx:145-147 |
| 13 | There is no option today to choose the region | supported (nothing found) | No region setting in app/config.py or the frontend |
| 14 | one deployment serves one customer organisation … sign-up open … kept apart by ownership checks | supported | DECISIONS.md:47-51, :67 |
| 15 | …done by Anthropic's Claude models through Anthropic's API, using the deployment's own API key | supported | app/config.py:45; render.yaml:96 |
| 16 | **Research and strategy:** … name, job title, company, research notes such as recent posts or company news | supported, but see row 1 | The company news comes from NewsAPI (personalization_context.py:1-6) and the posts from Unipile/RapidAPI (linkedin_posts.py). NewsAPI and RapidAPI are not named anywhere in the article. |
| 17 | **Personalised messages:** the prospect's details and research | supported | message_personalization.py:164, :267, :415, :505 |
| 18 | **Reply handling:** the text of replies … classified and a draft answer suggested | supported | reply_classification.py:81; webhook_delivery.py:81-82 (reply_draft_approved) |
| 19 | **Meetings:** meeting transcripts and notes … | supported | app/services/meeting_ai.py:3, :195 |
| 20 | **Support chat:** … your question, the recent messages in that chat and the matching help-center text | supported | app/services/support_chat.py:251, :367-381, :428 |
| 21 | If an administrator turns it on, **OpenAI** also receives the same research brief … off unless an administrator adds an OpenAI key. | supported (incomplete) | app/integrations/openai_client.py:3-10. app/services/consensus.py:80-88 needs both the `consensus_enabled` system setting (default False, app/services/system_settings.py:36) and a key, so a key alone does not turn it on. |
| 22 | The code does not set or change how long Anthropic or OpenAI keep the requests | supported (nothing found) | No retention setting in app/services/anthropic_client.py or openai_client.py |
| 23 | **Apollo**: receives your ideal-customer search criteria … also used to enrich | supported | apollo.py:90, :113-126 |
| 24 | (Apollo) Not yet verified live. | contradicted | The founder-confirmed status is live: frontend/src/content/product-facts.json:59 (`contact_finding` = live); docs/program/ai-visibility/REPORT.md:15 (Q6a "Contact find + verify" live end to end). The `# TODO: verify` markers (apollo.py:6-8) only say the API details are unchecked against Apollo's docs. Suggested wording, matching article 29:72: "parts are marked in the code as not yet verified against the live service". |
| 25 | **Hunter**: receives a prospect's name and company domain … and email addresses to verify | supported | hunter.py:60, :70 |
| 26 | (Hunter) Not yet verified live. | contradicted | product-facts.json:59; REPORT.md:15 (same as row 24) |
| 27 | **Google (Gmail)**: messages are sent from, and replies read in, the Gmail mailbox you connect | supported | gmail.py:299, :320 |
| 28 | (Gmail) Not yet verified live. | contradicted | product-facts.json:61 (`email_sending` = live); REPORT.md:15 ("Email sending (Gmail)" live end to end) |
| 29 | **Meta (WhatsApp Business)**: receives the prospect's phone number and the message. | supported | whatsapp.py:236-265 |
| 30 | (WhatsApp) Not yet run end to end against the live service. | contradicted | product-facts.json:62 (`whatsapp_steps` = live); REPORT.md:16 (Q6b "WhatsApp" live end to end). The 2026-09 auditor note at docs/VERIFICATION_REPORT.md:579 only says that auditor had no credentials. |
| 31 | **Unipile (LinkedIn)**: holds your connected LinkedIn session … profiles … messages. Not yet verified live. | supported | unipile_linkedin.py:15-16, :71-133; product-facts.json:71 (simulated_only); DECISIONS.md:9 (D1, 2026-10-13) |
| 32 | **Recall.ai**: receives the meeting link, joins … returns the transcript. Never called live so far. | supported | recall.py:4-12, :163 |
| 33 | **Twilio**: receives your mobile number … when the … text-message provider is set to Twilio. | supported | app/integrations/sms.py:3-6, :61-69. Context: DECISIONS.md:24 (PHONE-VERIFY) says Twilio is not configured in production. |
| 34 | **Stripe**: receives your email address and account id … card details on Stripe's own checkout page … waiting for live keys | supported | app/integrations/stripe_billing.py:11, :109, :149-154 |
| 35 | **IP checking services** (ipapi.co or ipinfo.io, and proxycheck.io or IPQualityScore) | supported | app/integrations/geolocation.py:11-12; app/integrations/ip_intelligence.py:6-7; app/config.py:436, :449 |
| 36 | The **Privacy** page also lists … Calendly, Zoom, HubSpot, Salesforce and Slack. | supported | privacy/page.tsx:137-138 |
| 37 | (Is Voyage AI a provider?) Not yet. | supported | No reference to Voyage anywhere outside docs/; no VOYAGE_API_KEY in render.yaml or app/config.py |
| 38 | On 2026-10-18 the founders approved Voyage AI to power search in the in-app help assistant … search vectors and ranks results | supported | DECISIONS.md:42 (HELPAI-VENDOR: `voyage-context-4` embeddings + `rerank-2.5-lite`, 2026-10-18) |
| 39 | When that change ships, Voyage AI will receive the help-center article text and the support questions you type | supported (inferred) | DECISIONS.md:42 approves embedding and rerank for the Help AI, which requires the article chunks and the query. The decision does not name the data explicitly. |
| 40 | Your prospects, messages and other account data are not part of what was approved for it. | unsupported | DECISIONS.md:42 states no data exclusion; it only scopes the vendor to "the Help AI". Also, a question a user types could itself contain prospect data. |
| 41 | Until that change ships, Voyage AI is not in use and receives nothing | supported | Same as row 37 |
| 42 | Support questions today go only to Anthropic | supported | support_chat.py:24, :251, :428 |
| 43 | Your account data … stays in the database until you delete it or delete your account. | supported | privacy/page.tsx:181-182 |
| 44 | Support chat history is deleted 30 days after a conversation's last message. | supported | app/config.py:299; app/workers/support_tasks.py:8, :40-60; render.yaml:136 |
| 45 | Cached contact-finding answers … expire after 30 days; search results after 1 day. | supported | app/config.py:80-81 |
| 46 | Billing records are kept for 7 years … without your name or email address. | supported | account_erasure.py:25, :86, :194 |
| 47 | Consent and suppression records are kept without a time limit | supported | account_erasure.py:27-33, :117; privacy/page.tsx:205-209 |
| 48 | When you delete your account, Vectorae disconnects … Unipile, but does not ask Stripe to delete … does not revoke … Google, HubSpot, Salesforce or Slack | supported | account_erasure.py:6, :328-368 |
| 49 | No data processing agreement (DPA) or downloadable subprocessor list is published | supported (nothing found) | No DPA or subprocessor text in frontend/src outside help content |
| 50 | The public **Privacy** page … lists the email address for privacy requests. | supported | privacy/page.tsx:38, :225-230 |
| 51 | you can erase one prospect's data, which also puts their email, phone number and LinkedIn profile on the do-not-contact list | supported | app/api/leads.py:345-373 |
| 52 | you can download everything your account holds as one file, and delete your whole account | supported | account_export.py:303; privacy/page.tsx:196-200 |
| 53 | a consent ledger records every opt-in, opt-out and erasure | supported | app/db/models.py:4628-4638; app/api/leads.py:356 (`consent.record_erasure`) |

Summary: 46 supported, 1 unsupported, 6 contradicted.

### What to fix first (article 43)
1. **Live status of four integrations (rows 24, 26, 28, 30).** The article says Apollo, Hunter, Gmail and WhatsApp are not verified live. The founders recorded them as working end to end on 2026-10-13 (product-facts.json:59-62, REPORT.md:15-16). The code's TODO markers only concern API details. Use the wording from article 29:72 instead.
2. **Missing providers (row 1).** NewsAPI, Vapi.ai, ElevenLabs, Mailreach, Google Postmaster/Calendar/Meet/FCM, RapidAPI and AegisAudit/PostIQ/SIGNALFORGE all receive data in code, and the Privacy page lists them, but this article does not. NewsAPI matters most because the research bullet (row 16) already describes the data it supplies. Vapi and ElevenLabs receive prospect phone numbers and voice data.
3. **Stripe placement (row 9).** "The Privacy page lists the same providers" is wrong, because Privacy lists Stripe as always in use. Either move Stripe or reword the sentence.
4. **Voyage exclusion (row 40).** HELPAI-VENDOR does not say prospect or account data is excluded. Either get that recorded in DECISIONS.md or soften the sentence. The rest of the Voyage section matches the decision.
5. **Minor.** Row 21: OpenAI also needs the `consensus_enabled` setting, not only a key. Row 2: voicemail audio is stored on local disk, not in Neon.

Article 42 has no factual errors. Optional precision: row 15 (an API-created webhook can have a custom secret without `whsec_`) and rows 7-8 (the refresh-token grace window).

Files: /home/user/LeadPilot/docs/help-center/42-security-faq-for-buyers.md, /home/user/LeadPilot/docs/help-center/43-data-processing-and-subprocessors.md

---

## Report: recheck-1

## Second-pass fact-check results

I edited no files. All 36 `sources` paths in the front matter of article 43 exist (checked with Glob), including the new aegisaudit/postiq/signalforge/plumbing/voice_providers files.

**Result:** of the 6 contradictions and 1 unsupported sentence from the first pass, all are fixed except the new tools sentence. One new problem appeared in article 43: the sentence about AegisAudit, PostIQ and SIGNALFORGE (row 40). Every edited sentence in the other articles checks out.

### 43-data-processing-and-subprocessors.md (whole article)
| # | Sentence (verbatim, may be shortened with …) | Verdict | Evidence (path:line) / what the code says |
|---|---|---|---|
| 1 | This article lists the outside companies … what each one receives … which are live and which are only built | supported | The list now covers every provider in frontend/src/app/privacy/page.tsx:124-141 (NewsAPI, RapidAPI, Vapi, ElevenLabs, Mailreach, Google Calendar/Meet/Postmaster/FCM, AegisAudit/PostIQ/SIGNALFORGE, Calendly, Zoom, HubSpot, Salesforce, Slack) |
| 2 | **Neon** … the main database. It holds your account, products, strategies, prospects, messages … consent and suppression records. | supported | render.yaml:10, :77 |
| 3 | (Voicemail audio files are the exception: they are stored on the server's own disk.) | supported | app/services/phone_calls.py:104, :273-283 (`write_bytes` under `settings.media_dir/voicemails`) |
| 4 | **Upstash** … job queue … short-term cache of answers from the contact-finding providers | supported | render.yaml:11, :86-90; app/integrations/apollo.py:92, :126; hunter.py:62, :72 |
| 5 | **Render** runs the API and worker … request logs record IP addresses | supported | render.yaml:8-9, :40, :152; privacy/page.tsx:75, :217 |
| 6 | **Vercel** hosts the web app | supported | render.yaml:12 |
| 7 | **Anthropic** writes research, strategies and message drafts, and classifies replies | supported | message_personalization.py:164; reply_classification.py:81 |
| 8 | **Resend** sends account emails … receives your email address and the email's content | supported | render.yaml:113-122; password_reset.py:63, :235 |
| 9 | The public **Privacy** page lists these providers as always in use, and also lists **Stripe** there. | supported | privacy/page.tsx:124-127 |
| 10 | In the code, Stripe receives data only when you take a paid plan | supported | app/integrations/stripe_billing.py:109, :149-154 |
| 11 | …API and the worker on Render in the Oregon region … database on Neon, queue/cache on Upstash, web app on Vercel | supported | render.yaml:6-12, :40, :152 |
| 12 | The code does not record which Neon or Upstash region … Privacy page states … EU and the United States | supported | render.yaml:77-90; privacy/page.tsx:113-115 |
| 13 | …expect … processed in the United States. The **Privacy** page says transfers … rely on … Standard Contractual Clauses. | supported | privacy/page.tsx:145-147 |
| 14 | There is no option today to choose the region | supported (nothing found) | No region setting in app/config.py or frontend |
| 15 | one deployment serves one customer organisation … sign-up open … kept apart by ownership checks | supported | docs/program/DECISIONS.md:19, :47-51, :67 |
| 16 | …Anthropic's Claude models through Anthropic's API, using the deployment's own API key | supported | app/config.py:45; render.yaml:96 |
| 17 | **Research and strategy:** product description, ICP, prospect data … recent posts or company news | supported | personalization_context.py:1-6; linkedin_posts.py:1-4 |
| 18 | **Personalised messages:** the prospect's details and research | supported | message_personalization.py:164, :267 |
| 19 | **Reply handling:** the text of replies … | supported | reply_classification.py:81 |
| 20 | **Meetings:** transcripts and notes … | supported | meeting_ai.py:3, :195 |
| 21 | **Support chat:** … your question, recent messages, matching help-center text | supported | support_chat.py:251, :367-381, :428 |
| 22 | **OpenAI** can also receive the same research brief … off by default: needs both `consensus_enabled` and an OpenAI key | supported | app/services/consensus.py:79-88; system_settings.py:36 (default False). Detail: it runs only on synthesis steps (consensus.py:75-76, `step_no % 9 == 0`). |
| 23 | The code does not set how long Anthropic or OpenAI keep the requests | supported (nothing found) | No retention parameter in anthropic_client.py / openai_client.py |
| 24 | **Live, with parts of the API handling marked in the code as not yet checked against the vendor's documentation** (Apollo, Hunter, Gmail, WhatsApp) | supported | product-facts.json:59, :61, :62 (live); apollo.py:8, hunter.py:9, gmail.py:9, whatsapp.py:24 (`# TODO: verify against current … docs`) |
| 25 | **Apollo**: ICP search criteria; returns prospects and enriches | supported | apollo.py:90, :113-126 |
| 26 | **Hunter**: name and company domain …, and email addresses to verify | supported | hunter.py:60, :70 |
| 27 | **Google (Gmail)**: sent from, and replies read in, the mailbox you connect | supported | gmail.py:299, :320 |
| 28 | **Meta (WhatsApp Business)**: phone number and message | supported | whatsapp.py:236-265 |
| 29 | **Unipile (LinkedIn)** … Tested only against simulated services. | supported | product-facts.json:71; unipile_linkedin.py:71-133 |
| 30 | **Recall.ai** … Never called live. | supported | app/integrations/recall.py:10-12 |
| 31 | **Stripe** … card details on Stripe's checkout page. Online checkout is tested only against simulated services. | supported | stripe_billing.py:149-154; product-facts.json:72 |
| 32 | **Twilio**: your mobile number … Not configured in production. | supported | app/integrations/sms.py:61-69; DECISIONS.md:24 |
| 33 | **NewsAPI**: a prospect's company name, to find recent news | supported | app/integrations/newsapi.py:43-58 |
| 34 | **RapidAPI**: a prospect's LinkedIn profile address, as a fallback for reading recent posts | supported | linkedin_posts.py:114-121, :167-171 |
| 35 | **Vapi.ai and ElevenLabs**: phone number, call prompt and voicemail text; ElevenLabs also voice samples for a clone | supported | voice_providers.py:4-14, :238-250, :298, :335-338 |
| 36 | **Mailreach**: your sending email address, to check inbox placement | supported | mailreach.py:5, :34-39. Detail: the key can also be the user's own, not only an admin's (:6). |
| 37 | **Google Calendar and Meet**: meeting details and attendee emails, through your connected Google account | supported | google_meet.py:133-165 |
| 38 | **Google Postmaster Tools** is asked for your sending domain's spam rate; built but switched off | supported | google_postmaster.py:3-7, :13-15; system_settings.py:133 (`postmaster_import_enabled` False) |
| 39 | **Firebase Cloud Messaging**: notification titles and text sent to the Android app | supported | app/services/notifications.py:153-192 (a deep-link `data` map is also sent) |
| 40 | **AegisAudit, PostIQ and SIGNALFORGE**: separate tools that receive drafts, captured posts or research requests when connected. | **contradicted** | PostIQ receives only the connection token and the client name, and Vectorae deliberately sends no capture (app/integrations/postiq.py:96-111; app/workers/tool_integration_tasks.py:14-15 "There is no PostIQ task"). Captured posts come from PostIQ's own Chrome extension (postiq.py:7-12). The AegisAudit draft-audit and SIGNALFORGE research tasks exist (tool_integration_tasks.py:41, :77), but nothing in app/ calls them; only tests/test_tool_integrations.py does. In product code these tools only get health and key checks (app/api/tool_integrations.py:88, :131-136, :199). Suggested wording: "connection checks only; Vectorae sends them no drafts or prospect data today". |
| 41 | **At sign-up and sign-in on production deployments:** IP checking services … receive your IP address to find its country and spot VPNs. | supported (minor imprecision) | The VPN check runs at sign-up and login and is on by default only in production (app/config.py:440-449; app/services/network_guard.py:59-63). The country lookup runs at the onboarding identity step, not at sign-in, and in every environment unless set to `disabled` (config.py:428-436; app/services/identity.py:242). |
| 42 | The **Privacy** page also lists Calendly, Zoom, HubSpot, Salesforce and Slack | supported | privacy/page.tsx:137-138 |
| 43 | Not yet. On 2026-10-18 the founders approved Voyage AI … turns text into search vectors and ranks results | supported | DECISIONS.md:42 |
| 44 | When that change ships, Voyage AI will receive the help-center article text and your support questions exactly as you type them. | supported (inferred) | DECISIONS.md:42; docs/program/plans/help-ai-v2-00-recon.md:158 ("Per question: one query embedding, one rerank"). No source says "exactly as you type", but support_chat.py has no redaction today, so this is the honest reading. The first-pass unsupported exclusion claim is gone. |
| 45 | Until that change ships, Voyage AI is not in use and receives nothing | supported | No Voyage reference or VOYAGE_API_KEY in app/, render.yaml, config.py |
| 46 | Support questions today go only to Anthropic | supported | support_chat.py:24, :251, :428 |
| 47 | Account data stays until you delete it or your account | supported | privacy/page.tsx:181-182 |
| 48 | Support chat history deleted 30 days after last message | supported | app/config.py:299; app/workers/support_tasks.py:40-60 |
| 49 | Cached contact-finding answers expire after 30 days; search results after 1 day | supported | app/config.py:80-81 |
| 50 | Billing records kept 7 years … without name or email | supported | account_erasure.py:25, :86, :194 |
| 51 | Consent and suppression records kept without a time limit | supported | account_erasure.py:27-33, :117 |
| 52 | On account deletion Vectorae disconnects Unipile, not Stripe/Google/HubSpot/Salesforce/Slack | supported | account_erasure.py:6, :328-368 |
| 53 | No DPA or downloadable subprocessor list … Privacy page lists the privacy email | supported | privacy/page.tsx:38, :225-230 |
| 54 | erase one prospect … email, phone and LinkedIn on the do-not-contact list | supported | app/api/leads.py:345-373 |
| 55 | download everything … and delete your whole account | supported | account_export.py:303 |
| 56 | consent ledger records every opt-in, opt-out and erasure | supported | app/db/models.py:4628-4638; app/api/leads.py:356 |

Summary: 55 supported, 0 unsupported, 1 contradicted.

### 36-crm-sync-field-mapping.md (edited sentences)
| # | Sentence | Verdict | Evidence |
|---|---|---|---|
| 1 | …a `Description` with Vectorae's internal deal ID and the lead's email | supported | app/services/crm_sync.py:466-467 (the email is added only when the lead has one) |
| 2 | The 15-minute sweep sends leads that replied or went further: replied, meeting booked, opportunity, closed won, closed lost and disqualified. | supported | crm_sync.py:65-66 (ENGAGED), :533 |
| 3 | The checkbox "Also push every verified lead …" adds verified and contacted leads. | supported | crm_sync.py:67, :533; CrmCards.tsx:126 |
| 4 | The proposal-sent stage has no status mapping and is not in either list. A lead without an email is never sent. Every deal is sent. | supported | models.py:112; crm_sync.py:65-67, :76-87, :497, :536, :538 |
| 5 | **Straight away**, when a meeting is booked, a reply arrives, a reply is interested, a call completes, a deal is won, you move a lead on **Pipeline**, or you create or edit a deal. | supported | crm_sync.py:72-73, :862-880; app/api/ui_support.py:145-151 (PATCH /leads, used by pipeline/page.tsx:204); app/api/deals.py:95-101, :148, :199 |
| 6 | These pushes send the lead whatever its status, even one the sweep would skip. | supported | crm_sync.py:495-498 (email and owner check only, no status filter) |
| 7 | Edits you make in the CRM table, inline or in bulk, are not pushed straight away; the sweep picks them up. | supported | The CRM grid uses /crm/leads/{id} and /crm/leads/bulk (frontend/src/lib/api/crm.ts:113, :134). The only enqueue_push callers in app/api are ui_support.py:151 and deals.py:101. |
| 8 | **Sync now** … sends every eligible record, not only changed ones, up to the same 500 leads and 500 deals, then reads linked records back. | supported | app/api/crm_integrations.py:195 (`full=True`); crm_sync.py:71, :539-545, :845 |
| 9 | It is rate limited: by default 60 times per hour for each CRM. | supported | crm_integrations.py:191 (scope `crm_sync_{provider}`); app/core/config.py:253 (RATE_LIMIT_AI_ACTION 60); app/core/rate_limiting.py:234-235 (window 3600 s) |
| 10 | Known limitation: if more than 500 … changed between sweeps, the ones past the cap are not sent by later sweeps until they change again. | supported | crm_sync.py:532, :539-545, :554 (`last_push_at = started` after a `limit(500)` batch) |

Summary: 10 supported, 0 unsupported, 0 contradicted.

### 37-webhooks-and-slack-events.md (edited sentences)
| # | Sentence | Verdict | Evidence |
|---|---|---|---|
| 1 | `lead_sourced` — A sourcing batch finishes with at least one verified lead | supported | app/workers/lead_tasks.py:622, :639-644 |
| 2 | **Send test** queues a sample … with `"test": true` in `data`. | supported | app/services/webhook_delivery.py:336 |
| 3 | The samples for `meeting_booked`, `deal_won` and `strategy_mutated` (no `version_id` or `changes`) do not match the live payloads exactly | supported | Samples at webhook_delivery.py:105-120 vs live: calendar_tasks.py:252-253 / api/webhooks.py:187-188 (booking_id or calendly_event, no start_time); meeting_followup.py:234-237 (value_cents, not value); strategy_mutation.py:339-341. Detail: the samples for `reply_interested` (phone variant), `campaign_paused` (auto, adds `bounce_rate`) and `deliverability_warning` (mailbox brake) each match only one live variant. The article's field list already documents those variants, so this is not an error. |

Summary: 3 supported, 0 unsupported, 0 contradicted.

### 38-reply-copilot-and-classification.md (edited sentences)
| # | Sentence | Verdict | Evidence |
|---|---|---|---|
| 1 | An approved email is handed to the normal send path straight away: unsubscribe footer and headers, send window, daily cap and the send-review queue all apply, so it can wait. | supported | app/services/reply_copilot.py:1025-1043 (SCHEDULED message, `enqueue_send` at once; 5-minute DISPATCH_GUARD only as a broker fallback, :102-105); :1251-1260, :1304-1305; frontend/src/lib/replyCopilot.ts:129-130 |
| 2 | The card always shows the option **Auto-send answers to "send me a time" email replies**, but … disabled with "An administrator has not allowed auto-send on this deployment." | supported | ReplyCopilotPanel.tsx:78, :203-224; replyCopilot.ts:154-158. Details: the label also ends "(off by default)", and if a user already has it on, the box stays enabled so it can be switched off (replyCopilot.ts:156). |

Summary: 2 supported, 0 unsupported, 0 contradicted.

### 39-daily-send-approval-and-notifications.md
| # | Sentence | Verdict | Evidence |
|---|---|---|---|
| 1 | Approval is given per channel for one day (email, LinkedIn, WhatsApp or AI phone calls), and one decision can approve several channels at once. | supported | app/services/daily_send_approval.py:25, :63-65, :296-299 (one row, `channels_json` list), :306-313 |

Summary: 1 supported, 0 unsupported, 0 contradicted.

### 44-learn-tab-and-tutorials.md
| # | Sentence | Verdict | Evidence |
|---|---|---|---|
| 1 | Your administrator can edit, publish, unpublish and remove tutorials on the **Tutorials** page … (adding a new one is possible only through the admin API) | supported | frontend/src/app/(admin)/admin/tutorials/page.tsx:99, :116, :122; admin/layout.tsx:22. `createTutorial` exists (lib/api/admin.ts:93-94; app/api/admin.py:435) but no page calls it. |
| 2 | **An empty player.** If your browser blocks YouTube's player script … the player area can stay empty with no message. … click **Mark complete** | supported | VideoPlayer.tsx:81-93: the load promise never rejects (no script onerror), so the `apiFailed` fallback iframe and message (:200-202, :244-266) never show when the script is blocked |

Summary: 2 supported, 0 unsupported, 0 contradicted.

### 41-benchmarks-what-good-looks-like.md
| # | Sentence | Verdict | Evidence |
|---|---|---|---|
| 1 | **How you compare** shows your reply rate next to the median and "Middle half" … of the accounts on your deployment (yours included) over the last 90 days … at least 30 sends | supported | app/services/benchmarks.py:180-219 (only suspended accounts are excluded, :192); system_settings.py:261, :263 |
| 2 | **Meeting-booked rate** … next to the median and middle half of the accounts on your deployment (yours included) … same rules | supported | benchmarks.py:31-32, :67-70, :180-219 |
| 3 | once your account's bounce rate across all your sends over the last 30 days is above 2% (the same figure counts against each of your sending domains), it costs one point per 0.1 pp … (2.5% costs 25), up to 30 points | supported | app/services/deliverability.py:150-163 (per user, not per domain), :180-181, :220-231; system_settings.py:115 (threshold 70) |

Summary: 3 supported, 0 unsupported, 0 contradicted.

### 32-guide-sdr-team-member.md
| # | Sentence | Verdict | Evidence |
|---|---|---|---|
| 1 | Integrations row (connecting or pausing a LinkedIn account; removing gets the deleting message), webhooks, costs or pilots → "Integrations, webhooks, costs and pilots need a manager." | supported | app/services/rbac.py:40-41, :59-65 (DELETE is checked first); app/api/linkedin.py:156, :173, :191-195, :208; app/api/webhook_targets.py:36, :64, :125 |
| 2 | Clients row: adding or changing clients and their domains (removing a domain gets the deleting message) → "Managing clients needs a manager in this workspace." | supported | app/api/client_workspaces.py:96, :118-122, :140-145, :177-186, :195; rbac.py:60-62 |
| 3 | Viewer: can open every screen, every change refused with "Viewers have read-only access to this workspace." | supported | rbac.py:54-58; app/services/auth.py:331-338 (personal routes exempt) |
| 4 | A viewer can still leave the workspace, and an attempt to invite gets "Inviting people needs a manager or above." | supported | rbac.py:30-31 (/workspaces is personal); app/services/workspaces.py:145-147, :180-185, :200 |

Summary: 4 supported, 0 unsupported, 0 contradicted.

### 31-guide-solo-founder.md
| # | Sentence | Verdict | Evidence |
|---|---|---|---|
| 1 | While automatic messages are waiting, a banner at the top of the app shows today's queued counts. | supported | components/shell/Shell.tsx:167; SendApprovalBanner.tsx:24-34; lib/sendApproval.ts:110-128. The banner is hidden on /send-approval itself. The labels **Approve selected channels for today** and **Decline for today** are at send-approval/page.tsx:181, :184. |

Summary: 1 supported, 0 unsupported, 0 contradicted.

### 03-getting-started.md
| # | Sentence | Verdict | Evidence |
|---|---|---|---|
| 1 | When they book through your booking page, the lead moves to the meeting-booked stage (**Booked** on the **Pipeline** page). | supported | app/workers/calendar_tasks.py:179-182 (when the booking is tied to a lead); frontend/src/app/(app)/pipeline/page.tsx:29 |

Summary: 1 supported, 0 unsupported, 0 contradicted.

### 42-security-faq-for-buyers.md
| # | Sentence | Verdict | Evidence |
|---|---|---|---|
| 1 | …and **Quickstart** (off by default), which reads your company's website | supported | app/services/system_settings.py:302-306 (`quickstart_enabled` False); product-facts.json:78 |

Summary: 1 supported, 0 unsupported, 0 contradicted.

### What to fix
1. **Article 43, row 40 (the only remaining error).** PostIQ receives only a token check from Vectorae. The AegisAudit and SIGNALFORGE send tasks are never called outside tests. Reword to say these tools currently get connection and key checks only.
2. **Optional, row 41.** The country lookup runs at the onboarding identity step in every environment. Only the VPN check is tied to sign-up/sign-in and to production.

D1: none of the checked sentences conflicts with it (outreach sends automatically after daily approval; research runs once per strategy).

Files checked: /home/user/LeadPilot/docs/help-center/43-data-processing-and-subprocessors.md, /home/user/LeadPilot/docs/help-center/36-crm-sync-field-mapping.md, /home/user/LeadPilot/docs/help-center/37-webhooks-and-slack-events.md, /home/user/LeadPilot/docs/help-center/38-reply-copilot-and-classification.md, /home/user/LeadPilot/docs/help-center/39-daily-send-approval-and-notifications.md, /home/user/LeadPilot/docs/help-center/44-learn-tab-and-tutorials.md, /home/user/LeadPilot/docs/help-center/41-benchmarks-what-good-looks-like.md, /home/user/LeadPilot/docs/help-center/32-guide-sdr-team-member.md, /home/user/LeadPilot/docs/help-center/31-guide-solo-founder.md, /home/user/LeadPilot/docs/help-center/03-getting-started.md, /home/user/LeadPilot/docs/help-center/42-security-faq-for-buyers.md

---

## Report: recheck-2

Second-pass fact-check of the edited sentences. All paths are under /home/user/LeadPilot. I found 2 contradictions, both in article 10. Everything else checked is supported, though three verdicts carry caveats.

### 06-lead-sourcing-and-email-verification.md
| # | Sentence (verbatim, may be shortened with …) | Verdict | Evidence (path:line) / what the code says |
|---|---|---|---|
| 1 | "Not in the app: leads come from the sourcing process above." | supported | No upload or import UI anywhere in frontend/src (no call to `customers/import`). The only importer is API-only: app/api/local_business.py:88 |
| 2 | "(Through the API, a local business with customer win-back switched on, which is off by default, can import its own opted-in customers into a strategy.)" | supported | app/services/local_business.py:14-16 (flag `customer_winback_enabled`, default OFF, "imports its OWN customers, each with a recorded opt-in"); :704-705 refuses with 409 when the flag is off; app/api/local_business.py:88,96 (`POST /strategies/{id}/customers/import`). Not stated in the article: healthcare businesses are refused outright (local_business.py:18-19). |
| 3 | "On the Growth, Scale, Pro and Enterprise plans you can upload your LinkedIn connections on the **Network** page and message them there, but they do not become leads" | supported | app/core/plans.py:187 (`{"growth","scale","pro","enterprise"}`); app/api/linkedin_network.py:38-45; frontend/src/app/(app)/network/page.tsx (import, draft and send messages). Connections are stored as `LinkedInConnection`/`LinkedInConnectionMatch`; app/services/linkedin_network.py never creates a `Lead` (it reads `LeadBatch` only for the ICP, :216-224). |
| 4 | "The founders confirmed finding and verifying contacts as working end to end in production on 2026-10-13." | supported | docs/program/ai-visibility/REPORT.md:1,9,15 (Q6a, 2026-10-13: "Contact find + verify"); frontend/src/content/product-facts.json:59 (`contact_finding` status "live") |
| 5 | "Both integrations were built from the providers' documentation and are tested automatically against simulated responses" | supported (weak on "built from documentation") | app/integrations/apollo.py:6-8 and app/integrations/hunter.py:7-9 say details not verified against the docs are marked TODO, which implies the rest came from the docs. Simulated tests: tests/test_apollo.py, tests/test_hunter.py, tests/integration/mocks/apollo_mock.py, tests/integration/mocks/hunter_mock.py |
| 6 | "…several request details are still marked in the code as needing confirmation against the providers' current documentation." | supported | apollo.py:42,45,55,64,90,113,124,145; hunter.py:26,37,46,60,70,89 (`# TODO: verify against current … docs`) |

Summary: 6 supported, 0 unsupported, 0 contradicted.

### 09-email-sending-gmail.md
| # | Sentence | Verdict | Evidence |
|---|---|---|---|
| 1 | "The founders confirmed email sending through Gmail as working end to end in production on 2026-10-13." | supported | docs/program/ai-visibility/REPORT.md:15 (Q6a "Email sending (Gmail)"); frontend/src/content/product-facts.json:61 (`email_sending` "live") |
| 2 | "The automated tests still run against simulated responses, and some request details are still marked in the code as needing confirmation against Google's current documentation." | supported | tests/integration/mocks/gmail_mock.py; app/integrations/gmail.py:9,40,64,141,296,299,320,324,401,456 (TODO verify markers) |

Summary: 2 supported, 0 unsupported, 0 contradicted.

### 10-whatsapp-outreach.md
| # | Sentence | Verdict | Evidence |
|---|---|---|---|
| 1 | "**Generate with AI** asks the AI for 2 or 3 candidates from the strategy's research (any that fail the checks are dropped, so you may get only one), each with its placeholders described." | supported | app/services/whatsapp_templates.py:384,387,395,409 (2 or 3 items, `variable_descriptions` required); :433-434 (research phases 2 and 6); :442,466-468 (invalid candidates dropped). If none pass, it raises "no generated candidate passed validation…" (:469-473). |
| 2 | "Every valid candidate is saved as a draft straight away." | supported | whatsapp_templates.py:457-465; `create_draft` commits with status DRAFT (:197,203) |
| 3 | "Choose one and press **Edit & save this draft**, keeping the same placeholders." | contradicted (only "keeping the same placeholders") | The button exists (frontend/src/app/(app)/campaigns/page.tsx:149-152). But the editor does not require the same placeholders. It shows a "What goes in {{n}}?" field for every placeholder in the current body and sends `variable_descriptions` with the update (frontend/src/components/campaigns/TemplateEditor.tsx:26-35,39-42,83-90). The server re-validates descriptions against the new body (whatsapp_templates.py:243-251). You can change placeholders as long as each one is described. The earlier fact-check's evidence for this clause ("edit sends body only", help-center-factcheck.md:598) is now stale. |
| 4 | "Drafts are never submitted automatically." | supported | whatsapp_templates.py:19,378,427-428 |
| 5 | "Only **approved** templates are sent, and approval and the opt-out instruction are checked again at the moment of sending." | supported | app/workers/outreach_tasks.py:483-495 (status must be APPROVED); :496-512 (`validate_opt_out` at send time) |
| 6 | "A template that fails either (for example one approved before the opt-out rule) is not sent; the message is not sent and stops with the reason recorded (the timeline shows "WhatsApp not sent", and the campaign's WhatsApp card counts it under "need template")." | supported with caveat | Status NEEDS_TEMPLATE plus `message.error` (outreach_tasks.py:489-495,504-512); "WhatsApp not sent" label (frontend/src/lib/conversation.ts:69, frontend/src/tests/conversation.test.ts:24); "need template" badge (campaigns/page.tsx:79, count from app/api/strategies.py:630-632). Caveat: "stops" is not final when an earlier message in the sequence was sent (see row 9). |
| 7 | "The launch form on the strategy page creates email sequences only. WhatsApp steps come from Autopilot (where you pick the template on the strategy page) or through the Vectorae API." | supported | frontend/src/components/strategy/OutreachPanel.tsx:21,73-75,168 (email only); frontend/src/components/strategy/AutopilotCard.tsx:111-120 ("WhatsApp template Autopilot uses:"); app/services/autopilot.py:633-649; app/api/autopilot.py:202; API steps validated in app/api/sequences.py:263-283 |
| 8 | "**Template step:** names any template that has not been rejected (draft, submitted or approved) and says how each variable is filled." | supported | app/api/sequences.py:263-283 (REJECTED refused with 422; a template under review may be referenced; variable mapping checked) |
| 9 | "The template must be approved by the time the step is due: if it is not, the message is not sent and does not wait for a later approval." | contradicted in part | The first half is right (outreach_tasks.py:483-495). The "does not wait" part is wrong in a common case. The follow-up sweep runs every 30 minutes (app/workers/celery_app.py:303-306, app/config.py:355). It only skips enrollments with a SCHEDULED, SENDING or AWAITING_REVIEW message (app/services/send_holds.py:91-92,103-106). A NEEDS_TEMPLATE message is none of these, so the sweep re-queues step last_sent+1, which is the same failed step (outreach_tasks.py:2147-2161,2208-2247). It then rebuilds the message from the step's template and sends it through every check again (:2295-2302,2326-2344). This happens once `followup_delay_hours` (default 72) has passed since the last sent message with no reply, and only if `followup_enabled` (default True) is on (app/db/models.py:1524-1529). The code comments say this is intended to recover a "WhatsApp step stuck on needs_template" (outreach_tasks.py:2030-2036; tests/test_followup.py:10). So if the template is approved by then, the message goes out. It only truly stops when no earlier message in the sequence was sent (`no_prior_send`, :2284-2285), for example a WhatsApp template first step. |
| 10 | "A free-form message can only go out while their window is open." | supported | outreach_tasks.py:468-481 (window re-checked at send, fails closed); app/services/whatsapp_window.py:25 |
| 11 | "The window is checked at the moment of sending: a free-form message due after the window closed is not sent and does not wait; it is counted under "need template"." | supported (in practice) | outreach_tasks.py:469-481 (NEEDS_TEMPLATE, "window closed before send"); counted at strategies.py:630-632 and shown at campaigns/page.tsx:79. The follow-up sweep could in theory re-queue this step too. In practice it does not: the window only reopens when the contact messages you, which records a REPLIED outcome (app/api/webhooks_whatsapp.py:437-439,491), and the sweep skips anyone who replied after the last send (outreach_tasks.py:2226-2227,2286-2287). |
| 12 | "The founders confirmed WhatsApp steps as working end to end in production on 2026-10-13." | supported | REPORT.md:16 (Q6b "WhatsApp"); product-facts.json:62 (`whatsapp_steps` "live") |
| 13 | "The automated tests still run against simulated responses, and many request details are still marked in the code as unconfirmed against Meta's current documentation…" | supported | tests/integration/mocks/whatsapp_mock.py; app/integrations/whatsapp.py:24,57,77,92,236,256,262,265,281,298,311,335,345,348,362,376,388; app/api/webhooks_whatsapp.py:20,80,103,133,143,264,307 |

Summary: 11 supported, 0 unsupported, 2 contradicted (rows 3 and 9; row 6 carries the same caveat as row 9).

Suggested fixes:
- Row 3: drop "keeping the same placeholders", or reword it to "describe every placeholder".
- Row 9: say the message is not sent then, but if an earlier message in the sequence went out and the lead has not replied, Vectorae retries that step automatically about 72 hours (by default) after the last message sent, and sends it if the template has been approved by then.

### 33-product-profile-and-icp.md
| # | Sentence | Verdict | Evidence |
|---|---|---|---|
| 1 | "Once a strategy is created, its name and description cannot be edited, in the app or through the API, and the app has no screen for changing past clients (the API can still add more, and research steps that run later read them)." | supported with caveat | app/api/products.py has only POST "" (:26), GET (:66), PUT local-business (:86) and POST past-clients (:118-154); nothing anywhere in app/ assigns `product.name` or `product.description`, and there is no PATCH/PUT for strategies. Past clients are only added from the New strategy wizard (frontend/src/app/(app)/strategies/new/page.tsx:58). The pipeline reads them at prompt time (app/pipeline/engine.py:86-95). Caveat: only for strategies with flow_type WITH_CLIENTS (:87-88); a strategy created with "No" past clients ignores clients added later. |

Summary: 1 supported, 0 unsupported, 0 contradicted.

### 34-strategy-patterns-and-playbooks.md
| # | Sentence | Verdict | Evidence |
|---|---|---|---|
| 1 | "If the classification fails, the channels, sales motion and cadence are left empty; the flow type is still recorded." | supported | app/services/icp_extraction.py:154-155,167-170 (returns `channels: []`, `sales_motion: None`, `cadence: None`); :273-274 (flow_type always added from `strategy.flow_type`) |

Summary: 1 supported, 0 unsupported, 0 contradicted.

### 35-google-workspace-dns-setup.md
| # | Sentence | Verdict | Evidence |
|---|---|---|---|
| 1 | "The strategy page's sending diagnosis then shows "Google refused your Gmail connection (revoked or expired)." with the fix "Reconnect Gmail.", and **Test** shows the same problem" | supported with caveat | Exact text at app/services/send_diagnostics.py:169-172, reached through `diagnose` (:254), app/api/autopilot.py:225-228, and the SendDiagnosticsPanel on the strategy detail page (frontend/src/app/(app)/strategies/detail/page.tsx:141). Caveat: it appears only after an email send has been attempted and failed. It fires when the mailbox's latest email attempt is not SENT and its error matches the token-failure pattern (send_diagnostics.py:131-148). This happens naturally: `sender_ref` is set before transmit (outreach_tasks.py:787-791), and the re-queued message stores the httpx error, which includes the oauth2.googleapis.com/token URL (gmail.py:63,129-136; outreach_tasks.py:985-986). Before any failed send, the diagnosis will not show this. |

Summary: 1 supported, 0 unsupported, 0 contradicted.

---

## Report: recheck-3

## Third-pass fact-check: four edited passages (articles 43 and 10)

Of the 9 sentences, 8 are supported and 1 is contradicted. The contradiction is in the WhatsApp retry sentence: the follow-up delay that is used belongs to the earlier step that was sent, not to the WhatsApp step. I edited nothing.

### 43-data-processing-and-subprocessors.md
All 5 paths I relied on exist (Glob): `app/integrations/{aegisaudit,postiq,signalforge,geolocation,ip_intelligence}.py`.

| # | Sentence (verbatim, may be shortened with …) | Verdict | Evidence (path:line) / what the code says |
|---|---|---|---|
| 1 | "AegisAudit, PostIQ and SIGNALFORGE: separate tools that can be connected; today Vectorae only checks the connection and key…" | supported | Config and test endpoints are at `/home/user/LeadPilot/app/api/tool_integrations.py:4-18`. The only live calls are health and key checks: `:84-90` (aegisaudit.health_check), `:124-140` (postiq.health_check + verify_token), `:193-201` (signalforge.health_check). Nit: AegisAudit has no key ("No auth", `/home/user/LeadPilot/app/integrations/aegisaudit.py:20`), so for AegisAudit only the connection is checked. Better wording: "checks the connection (and, for PostIQ and SIGNALFORGE, the key)". |
| 2 | "…and sends them no drafts or prospect data." | supported | The two Celery tasks that would send drafts or prospect IDs are `audit_draft_with_aegisaudit` and `signalforge_research_lead` (`/home/user/LeadPilot/app/workers/tool_integration_tasks.py:41,77`). They are registered (`/home/user/LeadPilot/app/workers/celery_app.py:51-53`), but a repo-wide search outside tests finds no caller, no `.delay`/`apply_async`, no API route and no beat entry. There is no PostIQ task at all (`tool_integration_tasks.py:14-15`). `postiq.verify_token` sends only the token (`/home/user/LeadPilot/app/integrations/postiq.py:96-110`). Risk: the code to send exists and is merely unwired. If someone wires it up, this sentence becomes false (AegisAudit would get prompt and draft, SIGNALFORGE a prospect_id). |
| 3 | "ipapi.co or ipinfo.io receive your IP address at the onboarding identity step to find its country" | supported | `/home/user/LeadPilot/app/services/identity.py:242` calls `geolocation.lookup_country(ip)`. Providers are at `/home/user/LeadPilot/app/integrations/geolocation.py:66-109`; the default is `ipapi_co` (`/home/user/LeadPilot/app/config.py:436`). Both provider classes carry "TODO: verify against current … docs" (`geolocation.py:68,86`). That doesn't affect this sentence, since it only says the IP is sent. |
| 4 | "proxycheck.io or IPQualityScore receive it at sign-up and sign-in on production deployments to spot VPNs." | supported | `enforce_clean_network` is called at `/home/user/LeadPilot/app/api/auth.py:267` (signup) and `:413` (login), and calls `ip_intelligence.assess(ip)` (`/home/user/LeadPilot/app/services/network_guard.py:63`). Blocking is on in production by default (`config.py:539-542`, app_env in {production, prod, live}), and an env var can override it either way (`config.py:441-445`). The default provider is `proxycheck` (`config.py:449`). Non-public and allow-listed IPs are not sent (`network_guard.py:59`). Both provider classes have "TODO: verify" markers (`/home/user/LeadPilot/app/integrations/ip_intelligence.py:67,99`). |

Summary: 4 supported, 0 unsupported, 0 contradicted.

### 10-whatsapp-outreach.md
All 5 paths I relied on exist (Glob): `app/workers/outreach_tasks.py`, `app/services/whatsapp_templates.py`, `app/api/sequences.py`, `app/db/models.py`, `frontend/src/app/(app)/campaigns/page.tsx`.

| # | Sentence (verbatim, may be shortened with …) | Verdict | Evidence (path:line) / what the code says |
|---|---|---|---|
| 1 | "Choose one and press **Edit & save this draft**; you can change the placeholders as long as each one is described." | supported (with caveat) | The label matches exactly at `/home/user/LeadPilot/frontend/src/app/(app)/campaigns/page.tsx:151`. That button only opens the editor; the actual save is the "Save draft" button (`/home/user/LeadPilot/frontend/src/components/campaigns/TemplateEditor.tsx:93-94`). Save is disabled until every placeholder has a description (`TemplateEditor.tsx:32-35`), and the server requires one per placeholder (`/home/user/LeadPilot/app services/whatsapp_templates.py:138-154`). Caveat: "as long as each one is described" is not the only rule. Placeholders must also run in order from {{1}} with no gaps or repeats (`whatsapp_templates.py:116-124`), and a marketing body needs the STOP opt-out (`TemplateEditor.tsx:33`). If line 66 of the article doesn't already say this, the sentence oversimplifies. |
| 2 | "The template must be approved by the time the step is due; if it is not, the message is not sent then." | supported | At send time a template that is not APPROVED moves the message to NEEDS_TEMPLATE and it is not sent: `/home/user/LeadPilot/app/workers/outreach_tasks.py:483-495`. |
| 3 | "If an earlier message in the sequence went out and the lead has not replied, Vectorae retries that step automatically…" | supported | NEEDS_TEMPLATE is not a pending status (`/home/user/LeadPilot/app/services/send_holds.py:91-106`), so the sweep does not skip the enrollment. The sweep takes the last SENT message (`outreach_tasks.py:2214`), checks for no reply (`:2226`), and re-sends step last+1 (`:2156`, `:2243-2246`). The code comment names this case explicitly (`:2030-2032`). Further conditions the article leaves out: the enrollment must still be ACTIVE (`:2203`), the campaign must not be paused (`:2234`), the earlier step must have `followup_enabled` (`:2219`), and the lead must not be a local-business customer (`:2240`). |
| 4 | "…once the step's follow-up delay has passed (72 hours by default)…" | contradicted (detail) | 72 is correct as a default (`outreach_tasks.py:2221`, `/home/user/LeadPilot/app/db/models.py:1527-1528`, `/home/user/LeadPilot/app/api/sequences.py:110-112`). But the delay is read from the earlier step that was sent (`_step_for(..., last.step_no)`, `outreach_tasks.py:2218-2221`), not from the WhatsApp template step. It is counted from when that earlier message was sent (`:2223-2224`), and the sweep runs every 30 minutes (`/home/user/LeadPilot/app/config.py:355`). The API describes the field as "Hours of silence after this step before the automatic follow-up fires" (`sequences.py:111`). Suggested wording: "once the previous step's follow-up delay (72 hours by default) has passed since that message went out". |
| 5 | "…and sends it if the template has been approved by then." | supported | The retry creates a new message with the step's `whatsapp_template_id` (`outreach_tasks.py:2295-2301`, `:2326-2339`) and runs it through `send_message_impl` (`:2343`). That repeats the approval check (`:488`), so the message sends only if the template is approved. If it is still unapproved, it falls back to NEEDS_TEMPLATE and the sweep can try again on later runs. |
| 6 | "A WhatsApp template that is the first step is not retried." | supported | With nothing sent yet, `_last_sent_message` returns None and the sweep skips the enrollment (`outreach_tasks.py:2214-2216`). `send_followup_impl` returns "no_prior_send" (`:2283-2285`). |

Summary: 4 supported, 0 unsupported, 1 contradicted (the delay detail in row 4). Row 1 is supported but oversimplified, and row 3 leaves out conditions.

**Overall: 8 supported, 0 unsupported, 1 contradicted.**