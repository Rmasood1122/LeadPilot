# PLAY_STORE_CHECKLIST.md — ClientHunter Enterprise

Follow these steps in order inside the Google Play Console.
Complete them ONCE per app lifetime, except where noted as "per release."
TODO: verify against current Play Console layout — Google reorganises it periodically.

---

## Prerequisites (complete before opening Play Console)

- [ ] Signed AAB built and downloaded from GitHub Actions artifact
- [ ] Privacy policy live at `https://app.clienthunter.com/privacy`
- [ ] `assetlinks.json` deployed with correct SHA-256 fingerprint (see SIGNING.md Step 6)
- [ ] All store assets prepared (see STORE_ASSETS.md)
- [ ] Google Play Developer account ($25 one-time fee) at https://play.google.com/console

---

## Step 1 — Create the app

1. Play Console → **All apps** → **Create app**
2. App name: `ClientHunter Enterprise`
3. Default language: English (United States)
4. App or game: **App**
5. Free or paid: **Free** (you can monetise via in-app subscriptions later; you cannot change Free→Paid after launch)
6. Declarations: check both boxes (comply with Developer Programme Policies, US export laws)
7. Click **Create app**

---

## Step 2 — Set up the store listing

**Main store listing** (Dashboard → Store presence → Main store listing):

- [ ] App name: `ClientHunter Enterprise`
- [ ] Short description: (see STORE_ASSETS.md — ≤80 chars)
- [ ] Full description: (see STORE_ASSETS.md — ≤4000 chars)
- [ ] App icon: upload 512×512 PNG
- [ ] Feature graphic: upload 1024×500 JPG/PNG
- [ ] Phone screenshots: upload at least 2 (see STORE_ASSETS.md)
- [ ] Category: **Business**
- [ ] Tags: (optional) outreach, CRM, sales, B2B, automation
- [ ] Contact details: email, website, privacy policy URL

---

## Step 3 — Content rating

Dashboard → Policy → App content → **Content rating**:

1. Click **Start questionnaire**
2. Category: **Utility** or **Business** (choose Business)
3. Answer all questions truthfully for a B2B outreach tool:
   - Violence: No
   - Sexual content: No
   - Profanity: No
   - Controlled substances: No
   - User-generated content: No
   - Personal/sensitive information: Yes — the app stores contact information for outreach purposes (covered in data safety, next step)
4. Submit and note the assigned rating (expected: Everyone or Everyone 10+)

---

## Step 4 — Data safety form

Dashboard → Policy → App content → **Data safety**:

This section requires accurate disclosure. Map each data type to its source in the codebase:

| Data type | Collected? | Purpose | Shared with 3rd parties? | Encrypted in transit? | User deletion? |
|---|---|---|---|---|---|
| Email address | Yes | Outreach automation | Yes (Gmail API, Apollo, Hunter) | Yes (HTTPS) | Yes (GDPR endpoint) |
| Name | Yes | Outreach personalisation | Yes (Apollo, Hunter, WhatsApp) | Yes | Yes |
| Company name | Yes | Lead enrichment | Yes (Apollo) | Yes | Yes |
| Job title | Yes | ICP targeting | Yes (Apollo) | Yes | Yes |
| Device identifier (FCM token) | Yes | Push notifications | Yes (Firebase) | Yes | Yes (DELETE /devices/{token}) |
| App interactions | Yes | Pipeline learning loop (M8) | No | Yes | Yes |

**Third parties to declare:**
- Anthropic — AI processing (strategy research, message generation)
- Apollo.io — lead sourcing and enrichment
- Hunter.io — email finding and verification
- Google (Gmail API) — email sending
- Google (Firebase Cloud Messaging) — push notifications
- Meta (WhatsApp Business Cloud API) — WhatsApp outreach
- Calendly — meeting booking

TODO: verify each third party's current data sharing classification in Play Console — the form asks specific questions about each data type shared.

**Key answers:**
- "Is all of the user data collected by your app encrypted in transit?" → **Yes** (all API calls use HTTPS)
- "Do you provide a way for users to request that their data is deleted?" → **Yes** (GDPR deletion endpoint at `DELETE /users/me` — ensure this is implemented and accessible from the app settings)

---

## Step 5 — Target audience

Dashboard → Policy → App content → **Target audience and content**:

- Target age group: **18 and over** (this is a professional B2B tool, not for children)
- "Does your app appeal to children?" → **No**

This prevents COPPA restrictions and keeps the listing accurate.

---

## Step 6 — App access

Dashboard → Policy → App content → **App access**:

If the reviewer needs to log in to test the app, provide test credentials:
- Create a test account in your deployed backend (`POST /auth/signup`)
- Provide the email and password here so the reviewer can see the full app

If you have a demo mode that doesn't require login, note that instead.

---

## Step 7 — Set up internal testing track

Dashboard → Testing → **Internal testing**:

1. Click **Create new release**
2. Upload the signed AAB from your CI build artifact
3. Add internal testers (your own email + any team members)
4. Provide release notes: `M7 initial release — Capacitor Android wrapper of ClientHunter Enterprise web app`
5. Click **Save and publish to internal testing**

Internal testing is instant — no review required. Use it to verify the signed AAB installs correctly on a real device before proceeding to production.

**Verify on device:**
- [ ] App installs from Play Store internal testing link
- [ ] Login works against the production backend
- [ ] Deep links work (`clienthunter:///strategies/1` opens the app)
- [ ] Push notification received (trigger one from the backend)
- [ ] Back button behaviour correct (exit dialog on root, navigate on nested)

---

## Step 8 — Closed / open testing (optional but recommended)

After internal testing passes, create a **Closed testing** track and invite a small group of real users (10–50 people) before full production release. This catches issues that don't appear in internal testing.

---

## Step 9 — Production release

Dashboard → Testing → **Production** → Create new release:

1. Upload the same AAB (or a newer build if internal testing found issues)
2. Write release notes (what's new in this version)
3. Set rollout percentage: **20%** for first release (gradual rollout lets you catch crashes before full exposure)
4. Submit for review

**Play review timeline:** New apps typically take 1–7 business days for review. Your first submission is more likely to be reviewed manually than subsequent updates.

---

## Top 5 rejection reasons for apps like ClientHunter — and the fixes

### 1. Missing or inaccessible privacy policy
**Fix:** Ensure `https://app.clienthunter.com/privacy` returns HTTP 200 from any network (not just your local machine). The Next.js `/privacy` route is static-exported and served at this path — verify it is live on your CDN/hosting before submission.

### 2. App Links (deep links) not verifiable
**Fix:** Ensure `https://app.clienthunter.com/.well-known/assetlinks.json` is accessible, returns the correct JSON structure, and contains the SHA-256 fingerprint of your production signing certificate (from `keytool -list -v`). Test with: `adb shell pm get-app-links com.clienthunter.app`

### 3. Notification permission not adequately explained
**Fix:** Already handled in Chunk 3 — the app only requests notification permission via a deferred in-app prompt (after first strategy completes), not on cold start. If rejected: add a screen explaining WHY notifications are requested before the system dialog appears. TODO: verify current Play policy on notification permission timing.

### 4. App crashes on cold start (before login)
**Fix:** The Playwright E2E test `mobile.spec.ts` covers this — "cold start → login screen renders without crash." Ensure the test passes before submitting. Common causes: environment variable not baked in (NEXT_PUBLIC_API_URL empty), Capacitor plugin not initialised before use (covered by NativeProvider useEffect guard).

### 5. Permissions declared but not used / permissions not justified
**Fix:** The AndroidManifest.xml audit in Chunk 4 ensures only `INTERNET`, `POST_NOTIFICATIONS`, and `VIBRATE` are declared. All three are actively used and justified in the manifest comments. If rejected for a permission: check the merged manifest via `./gradlew processDebugManifest` — a Capacitor plugin dependency may be adding permissions you didn't declare directly.
