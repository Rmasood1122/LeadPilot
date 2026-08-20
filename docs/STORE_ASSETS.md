# STORE_ASSETS.md — ClientHunter Enterprise Play Store Assets

Complete this before publishing. All assets go into the Play Console store listing editor.
TODO: verify all dimensions and limits against current Play Console asset specs —
Google periodically updates requirements.

---

## Required assets

### 1. High-resolution icon
- **Dimensions:** 512 × 512 px
- **Format:** 32-bit PNG (with alpha)
- **Max size:** 1,024 KB
- **Requirements:** No rounding, no shadows applied by you — the Play Console adds the shape mask. Keep the logo centered and clear.
- **Source:** Run `npm run mobile:assets` from `frontend/` after placing `assets/icon-1024.png` — it generates all icon sizes including this one.
- **Upload location:** Store listing → Graphics → App icon

### 2. Feature graphic
- **Dimensions:** 1,024 × 500 px
- **Format:** JPEG or 24-bit PNG (no alpha), max 1,024 KB
- **Requirements:** No rounded corners, no device frame, no Play Store badges. If the graphic includes text, keep it above 12sp equivalent.
- **Content:** A compelling image of the product. Suggestion: a screenshot of the ClientHunter dashboard with a headline overlay — "AI-powered client acquisition, running 24/7".
- **Upload location:** Store listing → Graphics → Feature graphic

### 3. Screenshots — Phone
- **Minimum:** 2 screenshots required (8 max)
- **Dimensions:** 1,080 × 1,920 px (portrait) or 1,920 × 1,080 px (landscape). Min 320 × 568 px, max 3,840 × 3,840 px.
- **Format:** JPEG or PNG, max 8 MB each
- **How to capture:** On a physical device or emulator: `adb exec-out screencap -p > screenshot.png` or use Android Studio's emulator screenshot button.
- **Suggested screens to capture:**
  1. Dashboard / kanban pipeline view (shows the core product value)
  2. Strategy detail — live pipeline progress (72 steps running)
  3. Campaign stats (reply rates, meeting booked badge)
  4. Analytics chart
  5. Settings / theme customizer (differentiator)

### 4. Screenshots — 7-inch tablet (optional but recommended)
- **Dimensions:** 1,080 × 1,920 px or 1,920 × 1,080 px. Min 1,080 × 1,920 px.
- Our M5 responsive layout already handles this breakpoint — take screenshots from an emulator at "Nexus 7" size.

### 5. Screenshots — 10-inch tablet (optional but recommended)
- **Dimensions:** Same as 7-inch. Min 1,200 × 1,920 px.

---

## Text assets

### App title
- **Limit:** 30 characters (including spaces)
- **Value:** `ClientHunter Enterprise`  ← 23 chars ✅

### Short description
- **Limit:** 80 characters
- **Draft (76 chars):**
  > AI-powered client acquisition — strategy to booked meetings, 24/7.

  TODO: personalise and verify this copy resonates with your target audience (B2B founders, agencies, consultants).

### Full description
- **Limit:** 4,000 characters
- **Draft:**

---

**ClientHunter Enterprise** is an AI-powered end-to-end client acquisition system for B2B businesses. Describe what you sell — the system does the rest.

**What ClientHunter does:**
✦ Researches your market in 72 structured steps across 8 phases
✦ Identifies your Ideal Customer Profile with firmographic precision
✦ Sources and verifies leads from Apollo and Hunter
✦ Runs multi-channel outreach via email and WhatsApp
✦ Books meetings directly into your Calendly calendar
✦ Learns from every campaign to improve the next one

**Runs 24/7 — even when your phone is off**
All campaigns run on the cloud backend. The app is your real-time window into what's happening: watch outreach send, replies arrive, and meetings book — without needing to touch anything.

**If you have past clients:**
Tell the system how you won them. It extracts the pattern — industry, decision-maker role, deal size, channel, trigger event — and builds your next strategy anchored on what actually works for you.

**If you're starting fresh:**
ClientHunter runs a 144-step research pipeline: 72 steps to build your strategy, 72 steps to build your go-to-market plan. Both are verified 10 times before a single message is sent.

**Compliance built in**
Every campaign respects CAN-SPAM, GDPR, and WhatsApp Business API policies. Bounce monitoring, instant suppression lists, and per-country outreach law checks are not optional — they are enforced.

**Push notifications for what matters**
Know the moment your strategy is ready, a lead replies, or a meeting is booked — without polling the dashboard.

**Customisable interface**
Five preset themes plus a full custom builder. Your colour palette, your fonts, your density. White-label ready.

---

*ClientHunter Enterprise is designed for founders, sales teams, and agencies doing B2B outreach. It is not a consumer product.*

---

TODO: have a copywriter review before publishing. The current draft is functional but not polished for a public listing.

---

## App category
- **Primary:** Business
- **Secondary:** Productivity

## Content rating
- Run the content rating questionnaire in the Play Console.
- For a B2B outreach tool with no user-generated content, no violence, no adult content: the rating will be **Everyone** or **Everyone 10+**.
- TODO: verify by completing the questionnaire — do not assume the rating.

## Contact details
- **Email:** Your support email address (required)
- **Website:** Your product website or https://app.clienthunter.com
- **Phone:** Optional
- **Privacy policy URL:** https://app.clienthunter.com/privacy (the `/privacy` route in Next.js)

---

## Checklist before submitting

- [ ] App icon uploaded (512×512 PNG)
- [ ] Feature graphic uploaded (1024×500)
- [ ] At least 2 phone screenshots uploaded
- [ ] App title entered (≤30 chars)
- [ ] Short description entered (≤80 chars)
- [ ] Full description reviewed and personalised
- [ ] Privacy policy URL live and accessible
- [ ] Content rating questionnaire completed
- [ ] Contact email entered
- [ ] Category set to Business
