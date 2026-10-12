# Voice twin — "Your voice on calls"

Status: built behind `voice_clone_calls_enabled` (default **off**; also needs
`phone_calling_enabled`, default off). Migration `0089_voice_twin`.
Founder request 2026-10-12 (verbatim): *"I want to add one more Feature IT can
attend calls with users permission Use ElevanLabs or something else IT fully
copy voice of The user and talk on Calls and Talks like a Human not like a AI"*.
Founder answers: calls BOTH ways (answer prospects who call back; place
outbound calls with recorded call consent); permission = the existing daily
send approval plus live takeover; clone quality = an ElevenLabs Professional
Voice Clone (PVC) of the account owner's OWN voice.

**What we built and what we refused to build.** It talks like a person in
*delivery* (short turns, barge-in, endpointing, low latency, the owner's
voice). It never talks like a person in *identity*: every call says it is an
AI assistant and that the call is recorded, it never claims to be the owner
or a human, and a breach pauses the account. The founder was told this and
accepted it. Concealment is not configurable anywhere.

## 1. Recon — this is "extend AI calling", not a new channel

| Exists | Where | Used for |
|---|---|---|
| AI calls (Vapi primary, ElevenLabs ConvAI fallback), script, voicemail, consent gate, daily cap, results, analysis | `app/services/phone_calls.py`, `app/integrations/voice_providers.py`, `app/integrations/phone_channel.py`, `app/api/calls.py`, `app/workers/call_tasks.py`, `calls` table | Outbound clone calls go through the SAME `prepare_call` → `send_message_impl` → `PhoneChannel.send` path; inbound calls are stored as `Call` rows and analysed by the same `analyze` |
| AI disclosure prefix (outbound) | `phone_calls.write_script` | Kept; now superseded by the canonical opening (below) |
| Send chokepoint and every gate | `app/workers/outreach_tasks.py::send_message_impl`, `_prepare_phone` | Untouched except one new gate (pause) and re-enforcing the disclosure after the claim check |
| Daily send approval (phone already in `ALL_CHANNELS`) | `app/services/daily_send_approval.py` | Unchanged: automatic clone calls wait for it like any phone send |
| Notifications | `event_bus.emit`, `notification_tasks.enqueue_event` | New events `ai_call_live`, `voice_twin_incident`, `ai_call_message` |
| Booking with the host-level lock | `calendar_service.lock_host_calendar`, `slot_is_offered`, `app/api/calendar.py::public_book` | Inbound `book_meeting` tool uses the same lock + offered-slot check + unique slot constraint |
| Stop handling | `sequence_engine.unsubscribe_lead`, `consent.suppress_everywhere`, `suppression_list` | Inbound "stop calling me" |
| Audit | `compliance_audit_log` (kept, E2), `security_audit_events` | Disclosure incidents, consent, revoke, switches, pause/resume, takeover |
| GDPR | `account_export.OWNERSHIP`, `account_erasure.DELETED`, `disconnect_providers`, `LEAD_SCRUB` | New tables + provider delete + lead-less inbound calls |

## 2. Behaviour

### A. Voice clone setup (Settings › Voice › "Your voice on calls")
1. **Consent first** (`POST /me/voice-clone/consent`): versioned text
   (`voice_twin.CONSENT_VERSION = "1"`), "This is my own voice" tick, typed
   full-name signature. The page renders `CONSENT_TEXT` with the signature as
   it is typed and sends that exact text back; the server rebuilds it and
   refuses a mismatch (409), so the stored text is exactly the text shown
   (review L4). Stored on `voice_clones` with the signature and the time;
   audited (`voice_clone.consented`). No recording is accepted before this
   (409), and the flag/consent/status checks run before the request body is
   read (review L3).
2. **Recordings** (`POST /me/voice-clone/samples`, one file per request, RAW
   body): uploaded files or browser recordings (MediaRecorder; feature-detected,
   upload-only fallback). Validated: audio MIME type, magic bytes, ≥ 4 KB,
   ≤ 25 MB each, ≤ 25 files, ≤ 250 MB total. Read into memory, sent to
   ElevenLabs (`POST /v1/voices/pvc` on the first one, then
   `POST /v1/voices/pvc/{id}/samples`), dropped. **Nothing is written to our
   disk or DB except counts.** A raw body is used precisely because Starlette's
   multipart parser spools files over 1 MB to a temp file on disk.
3. **Verification** — ElevenLabs' own "voice captcha": `GET .../captcha` is
   shown (image or text); the person records their reading
   (`POST .../captcha`, multipart `recording`). If the text cannot be shown,
   the page gives exact instructions to verify on elevenlabs.io and the person
   presses "Check status".
4. **Training** — once verified, `POST .../train {"model_id":
   "eleven_flash_v2_5"}`; `POST /me/voice-clone/refresh` reads
   `GET /v1/voices/{id}` (`fine_tuning.state[model]`, `voice_verification`)
   and moves the row honestly: verifying → training → ready | failed.
5. **Preview** — `GET /me/voice-clone/preview`: the opening line in the
   clone (TTS with `eleven_flash_v2_5`, the same model calls use — review L5),
   returned as audio, never stored.
6. **Use my voice** — `PUT /me/voice-clone/use` (needs `ready` and the flag).
7. **Revoke** — `DELETE /me/voice-clone`: status → `revoke_pending` and
   committed FIRST (unusable from that instant), then
   `DELETE /v1/voices/{id}` with 3 inline attempts; success → `revoked`;
   failure stays `revoke_pending` and the hourly beat task
   `voice_clone_housekeeping` retries. Always allowed, even with the flag off.

### B. Natural conversation (Vapi assistant)
`voice_providers.vapi_assistant()` builds every transient assistant
(outbound and inbound): `startSpeakingPlan` (waitSeconds 0.4, LiveKit smart
endpointing), `stopSpeakingPlan` (numWords 0 = barge-in on voice activity,
voiceSeconds 0.2, backoffSeconds 1, acknowledgement phrases), 11labs voice
`eleven_flash_v2_5` at `optimizeStreamingLatency` 3 with the clone `voiceId`
(stability 0.5, similarityBoost 0.85), `artifactPlan.recordingEnabled`,
`monitorPlan.controlEnabled`, `server.url` + `server.headers` (our
`x-vapi-secret`), `endCall` and `transferCall` tools. The prompt's
`STYLE_RULES` ask for short turns, contractions, sparing natural
acknowledgements, no lists read aloud. Backchanneling and filler injection
are **not sent** (unverified, see §9).

### C. Outbound
`phone_calls.prepare_call` asks `voice_twin.call_identity(owner)`: the clone is
used only when the flag is on, the owner turned "Use my voice" on, the clone is
`ready` and the account is not paused; otherwise the configured stock voice.
The disclosure applies either way. A voicemail in the clone's voice is NOT
rendered to a hosted mp3 (data minimisation; the provider speaks it).

### D. Inbound answering
Owner switch "Answer my calls with my AI assistant" (`PUT /voice-twin/settings`,
owner or manager, audited, off by default). Turning it on copies the account's
OWN number (`voice_twin.own_number`: a user-scoped `vapi.phone_number_id`,
assigned by a deployment admin with `PUT /admin/voice-twin/numbers/{user_id}`,
audited) into `voice_twin_settings.inbound_phone_number_id` (UNIQUE — one
number answers for one account; 409 if taken). The deployment's shared number
is NOT used as a fallback (review fix M4) — except for a deployment
administrator's own account, because the operator owns that number and the
UNIQUE mapping still lets only one account hold it. Anyone else gets a 409
asking their administrator to assign a number.
`POST /webhooks/vapi/inbound` (the phone number's server URL in Vapi):
signed (`x-vapi-secret`, fail closed); `assistant-request` → account found ONLY
by `message.call.phoneNumberId`, and only if it is still the account's
configured number; unknown number → 404. Caller matched by E.164 against the
account's OWN leads (`account_export.owner_clause("leads")`). Refusals
(flag off, switch off, paused, plan without phone, suspended): transfer to the
owner's number if set (`{"destination": ...}`), else an automated "nobody can
take your call" message. The assistant: clone voice if allowed, disclosure
first message + "How can I help?", identity rules, receptionist role, business
products, the owner's notes (delimited as data), the known caller's context
(delimited), tools `take_message`, `find_times`/`book_meeting` (when the
owner has an active booking page), `transferCall` to the owner. Stored as a
`Call` with `direction='inbound'` (lead_id NULL for an unknown caller); the
end-of-call report goes to `/webhooks/vapi` and the existing analysis.

### E. Live takeover
On the first `status-update` `in-progress` of ANY AI call: push + Slack via
`ai_call_live` (deduped per call) and the in-app banner (polls
`GET /voice-twin/live-calls`: every 15 s during a call, 60 s otherwise, never with AI calling off). **Take over**
(`POST /calls/{id}/takeover`, owner or manager, audited) posts
`{"type":"transfer","destination":{"type":"number","number":<owner>},"content":...}`
to the call's `monitor.controlUrl` (stored from the create-call response or the
webhook's `call.monitor`; only `https://*.vapi.ai` is ever driven; never
returned by the API; redacted from exports). The AI also transfers by itself
when the caller asks for the owner (transferCall tool + identity rules).
The banner endpoint returns `{calling_enabled, calls}`: it lists calls started
in the last 20 minutes and the page stops polling while AI calling is off.
**Listen live is not built** (needs a websocket audio client; see §10).

### F. UI
Settings › Voice: `VoiceTwinCard` (consent, upload/record, verify, status,
preview, use-my-voice, revoke; answering switch, transfer number, notes,
pause/resume, inbound call list). App-wide `LiveCallBanner` with Take over.
Calls tab: direction badge and "Your voice (AI)" badge; lead-less inbound
calls show the number.

### G. Flags / plans
`voice_clone_calls_enabled` (False). `phone_calling_enabled` must also be on.
Plan: inbound answering requires a plan with `phone` (Scale+); outbound clone
calls keep the existing plan hold. Account toggles: use my voice, answer my
calls.

## 3. The guards, enforced in code

| # | Guard | Where |
|---|---|---|
| 1 | Every call and voicemail OPENS with the disclosure + "This call is recorded." (`opening_line`, `voicemail_opening`, `enforce_opening`) | `prepare_call`, again after the claim check in `_render_phone_outbound`, again in `PhoneChannel.send` (invalid/missing metadata → generic disclosure), inbound `firstMessage` |
| 2 | Identity rules lead every system prompt (`IDENTITY_MARKER`); concealment in user-editable text refused with 422 (`concealment_problems`) | `phone_calls.system_prompt`, `PhoneChannel._disclosed` (`ensure_identity_rules`), inbound prompt; 422 on `/voice-twin/settings` notes, `POST /leads/{id}/call` brief, phone steps of `POST /strategies/{id}/sequences`; a stored concealing brief → `ComplianceError` (`blocked_compliance`) |
| 3 | Post-call check (fixed regex list, no model call): assistant turns claiming to be human/the owner → `compliance_audit_log` decision `ai_claimed_human` (pattern labels + call id only), `voice_twin_incident` notification, `security_audit` `voice_twin.paused`, account paused | `voice_twin.post_call_check` from both provider webhooks; pause gate in `_prepare_phone` (`deferred_ai_calls_paused`, never dropped), `call_now` (409), inbound (no AI answer); resume = `POST /voice-twin/resume` with acknowledgement, owner/manager, audited |
| 4 | A clone is used only by its owner's account | every lookup by `user_id`; clone routes are under `/me` (rbac personal prefix: a workspace member always acts as themself); consent says "this is my own voice"; ElevenLabs verification done by the person |
| 5 | Written consent before any upload; revoke blocks use at once, deletes at the provider (retried); erasure deletes it; export lists metadata, no audio | `record_consent`, `revoke`, `retry_pending`, `account_erasure.disconnect_providers` → `provider_deletions_for_erasure`, `voice_clones` in OWNERSHIP + DELETED |
| 6 | No audio stored; type/size/total validated | raw-body streaming, `check_sample`, no audio column (migration test asserts) |
| 7 | Clone calls keep every gate | no new send path; flag, consent, DSA, window, cap, suppression, plan, local-business H2, closed-lead all still run first |
| 8 | Inbound: separate switch, off, owner/manager, audited, own number only, signed, unknown → 404, stop → suppressed | `put_settings`, `inbound_account`, `vapi_inbound_webhook`, `suppress_caller` |

**Flag-independent change (intentional):** the canonical opening — with the
recording notice — now applies to ALL AI calls, flag on or off, because the
recording announcement (two-party-consent states) and the AI disclosure are
legal duties that do not depend on the voice twin. Existing outbound calls
therefore open "Hi Sara, this is an AI assistant calling for Rehan. This call is
recorded." `tests/test_phone_calls.py` was updated for this contract change
(the voicemail now starts with the disclosure).

## 4. Data model — migration `0089_voice_twin`
- `voice_clones` (user_id FK CASCADE): provider, provider_voice_id, status,
  consent_version, consent_text, consent_signature, consented_at,
  sample_count, sample_bytes, provider_state_json (status subset only), error,
  ready_at, last_used_at, revoke_requested_at, revoked_at, revoke_attempts.
  **No audio column.**
- `voice_twin_settings` (user_id UNIQUE, FK CASCADE): use_clone_for_calls,
  answer_inbound, inbound_phone_number_id (UNIQUE), transfer_number,
  assistant_notes, paused_at, paused_reason.
- `calls`: + direction ('outbound' default), voice_clone_used, from_number,
  control_url; lead_id → nullable.
- `voice_clone_deletions` (review fix M3): provider, provider_voice_id,
  attempts, last_error, last_attempt_at, created_at. **No owner column,
  nothing personal.** A provider delete that fails during an account erasure
  is queued here; the row survives the erasure (it is not an OWNERSHIP table,
  so it is in `account_export.EXCLUDED` and is documented as
  `account_erasure.PROVIDER_DELETION_QUEUE`; it cannot be added to `KEPT`,
  whose exact contents a sealed test pins). The hourly task retries it,
  raises an operator alert (`task_errors` `VoiceCloneNotDeleted` +
  `security_audit_events` `voice_clone.delete_pending`, again every 24 failed
  attempts) and deletes the row once ElevenLabs confirms. Legal reason
  (needs founder/legal confirmation): it is the only way to finish deleting
  the person's biometric voice model at the processor (GDPR Art. 17, BIPA
  §15(a)).
- Downgrade is lossy and documented: drops the three tables and the columns
  and DELETES lead-less inbound calls. Revoke clones (and clear the deletion
  queue) before downgrading.

## 5. API
See the module docstrings of `app/api/voice_twin.py` and `app/api/calls.py`.
Personal: `/me/voice-clone`, `/consent`, `/samples`, `/submit`,
`/verification` (GET/POST), `/refresh`, `/preview`, `/use`, `DELETE`.
Account: `/voice-twin/settings` (GET/PUT), `/voice-twin/resume`,
`/voice-twin/live-calls`, `/voice-twin/inbound-calls`,
`POST /calls/{id}/takeover`. Public, signed: `POST /webhooks/vapi/inbound`.

### Workspace exposure (review L9)
- `GET /voice-twin/settings` is account-level: workspace members (any role)
  see the switches, the receptionist notes and the transfer number **masked**
  (`********1111`). Only the owner sees the full number.
- Changing the transfer number is **owner only** (403 for managers): it is
  where takeovers and "put me through to the owner" calls are sent, so a
  manager must not be able to redirect the owner's calls to their own phone.
  Managers can still change answering on/off and the notes (audited).
- A manager may press **Take over**; the call goes to the OWNER's saved
  number, never to the manager (documented so nobody expects otherwise).
- The clone itself is personal (`/me/...`): no member ever reaches it.

## 6. Tenancy
Clone and settings rows by `user_id`; calls via `account_export.owner_clause`
(lead path, or lead-less inbound via `user_id` — `DIRECT_OWNER_FALLBACK`);
inbound account by provider number id only; caller by the account's own leads;
tools only run for an inbound call's own account; live calls / takeover /
`GET /calls/{id}` 404 for other accounts (tested).

## 7. Compliance review — **needs founder/legal confirmation**
I am not a lawyer. These are the readings the code implements; none is
presented as settled law.
- **Maine 10 MRSA §1500-Y** (2025, AI chatbot disclosure in trade): disclose
  that the consumer is talking to AI → opening disclosure + answer on request.
- **EU AI Act Art. 50(1)** (applies from 2 Aug 2026): people must be informed
  they are interacting with an AI system → opening disclosure, every call.
- **Utah AI Policy Act as amended by SB 226**: never claim to be human; disclose
  on request → identity rules + post-call check + pause.
- **California Pub. Util. Code §2874 (AB 2905)**: artificial voice in a
  prerecorded message must be disclosed → voicemail opening.
- **FCC Declaratory Ruling, Feb 2024, CG Docket 23-362 (TCPA)**: AI voices are
  "artificial voice" → prior express (written, for telemarketing) consent; the
  per-lead phone consent gate stays mandatory and unchanged. National DNC
  registries are still NOT checked (pre-existing; operator's duty).
- **Two-party recording consent states (e.g. Cal. Penal Code §632)**: "This
  call is recorded." on every call, outbound and inbound.
- **BIPA (740 ILCS 14) and GDPR Art. 9**: the owner's voiceprint is biometric
  → written informed consent (versioned text, signature, time) before
  collection; publicly-stated retention (3 years after last use, or on revoke,
  or on account deletion — the hourly task enforces it); deletion at the
  provider on revoke/erasure; no recordings kept by us. **Open for legal:**
  whether the PRIVACY_POLICY needs a biometric section (not edited here — the
  policy is legal text), whether BIPA §15(b)'s "written release" is satisfied
  by a typed-name e-signature, and whether ElevenLabs as processor needs a
  DPA entry.
- **ElevenLabs usage policy**: consent to clone and no deceptive impersonation
  → own-voice attestation, ElevenLabs' own verification, disclosure.
- **CAN-SPAM / CASL / PDPA**: not email/SMS; the phone channel's existing
  per-lead consent and suppression apply. PDPA (Singapore) DNC not checked
  (pre-existing).
- Inbound callers are recorded and told so; a caller who says stop is
  suppressed; an inbound caller's number is erased with the lead
  (`LEAD_SCRUB.calls.from_number`). **Gap:** a lead-less inbound caller cannot
  be erased by a lead-level GDPR request (there is no lead); only account
  erasure removes that row. Needs a decision.

## 8. AI cost and budget
- Our Claude spend: **no new model call on a request path.** The inbound
  `assistant-request` is answered from the DB only (Vapi's 7.5 s limit). Each
  answered inbound conversation adds ONE transcript analysis (existing
  `analyze_call`, inside `usage_meter.scope(... purpose="call_analysis")`,
  ~1.5k output tokens max). The post-call check is regex-only.
- Provider spend (not metered by `usage_meter`, pre-existing for outbound
  too): Vapi per-minute (telephony + the model Vapi runs + ElevenLabs TTS),
  covered by the existing `voice_cost_per_minute` estimate (0.15 USD). Inbound
  answering adds minutes the owner does not choose call-by-call; the daily call
  limit does NOT cap inbound calls (it caps outbound). ElevenLabs PVC needs a
  paid ElevenLabs plan that includes Professional Voice Cloning — check
  current pricing; not verified here. Preview TTS: one short TTS per press,
  rate-limited (`RATE_LIMIT_AI_ACTION`).

## 9. Unverified (not proven against live Vapi / ElevenLabs)
Checked against the public docs on 2026-10-12 with WebFetch (docs.vapi.ai,
elevenlabs.io/docs); **never called live**.

Verified field names (docs): Vapi `firstMessage`, `firstMessageMode`,
`startSpeakingPlan.waitSeconds`, `startSpeakingPlan.smartEndpointingPlan.provider`,
`stopSpeakingPlan.numWords/voiceSeconds/backoffSeconds`, `monitorPlan.listenEnabled/controlEnabled`,
`server.url/headers`, `artifactPlan.recordingEnabled`, `voicemailDetection`,
`voicemailMessage`, `maxDurationSeconds`, `metadata`, `model.tools`
(`endCall`, `transferCall.destinations`, `function`), 11labs voice
`provider/voiceId/model/stability/similarityBoost/optimizeStreamingLatency`;
server messages `assistant-request` (response `assistant` | `destination` |
`error`, 7.5 s), `tool-calls` (`toolCallList[].id/name/parameters` → `results[].toolCallId/result`),
`status-update`, `end-of-call-report` (`artifact.messages[].role/message`);
Call object `phoneNumberId`, `customer.number`, `type` (`inboundPhoneCall`),
`monitor.controlUrl`; live control `{"type":"transfer","destination":{"type":"number","number"},"content"}`.
ElevenLabs `POST /v1/voices/pvc` (name, language, description) → `voice_id`;
`POST /v1/voices/pvc/{id}/samples` (multipart `files`, `remove_background_noise`);
`GET|POST /v1/voices/pvc/{id}/captcha` (POST multipart `recording`);
`POST /v1/voices/pvc/{id}/train` (`model_id`); `GET /v1/voices/{id}`
(`fine_tuning.state` values, `voice_verification`); `DELETE /v1/voices/{id}`;
TTS path/`text`/`model_id`.

**UNVERIFIED (behind constants / marked in code):**
- `SEND_UNVERIFIED_VAPI_FIELDS = False`: `backchannelingEnabled`,
  `voice.fillerInjectionEnabled`, `backgroundSpeechDenoisingPlan.smartDenoisingPlan`
  — not in the create-assistant schema we could read; NOT SENT.
- `stopSpeakingPlan.acknowledgementPhrases` — shown only in Deepgram Flux examples.
- `transferCall.destinations[]` item fields `type/number/message/description`
  — partially documented across two pages.
- `voicemailDetection.provider = "twilio"` (pre-existing TODO).
- `CONTROL_SENDS_API_KEY`: whether `controlUrl` needs/accepts a bearer key
  (docs show only content-type; `controlAuthenticationEnabled` left off).
- Top-level `metadata` on `POST /call` (pre-existing).
- `PVC_TRAIN_MODEL_ID = "eleven_flash_v2_5"`: that a PVC can be fine-tuned for
  Flash v2.5 (Vapi lists the model; ElevenLabs PVC-model support not confirmed).
- Captcha GET response body (docs example is `{}`): we accept an image
  content-type or JSON `text|captcha|phrase|sentence`; otherwise we send the
  person to elevenlabs.io.
- Accepted sample formats/sizes at ElevenLabs (docs list none); browser
  recordings are WEBM/OGG/MP4.
- That Vapi resolves a PVC `voiceId` from the deployment's ElevenLabs account:
  the ElevenLabs key must be connected in Vapi (Integrations) with voices read
  access — a founder setup step.
- ElevenLabs ConvAI fallback with a clone: `conversation_config_override.tts.voice_id`
  (and the agent must allow the override); takeover is Vapi-only.
- Whether a phone number's own `server` config forwards the whole call's
  events or only `assistant-request` (we set the assistant's `server.url` to
  `/webhooks/vapi` and handle everything on both endpoints).
- The `x-vapi-secret` header from a phone number's server credential (docs:
  a Bearer-type credential named `X-Vapi-Secret` with prefix off).

## 10. Limitations
- Listen live: not built (needs a websocket audio client in a static export).
- A lead-less inbound caller cannot be erased by a lead-level request (§7).
- Inbound calls are not capped by `phone_daily_call_limit`.
- Provider deletes that fail during ACCOUNT erasure are queued in
  `voice_clone_deletions` and retried hourly with an operator alert (review
  M3); until ElevenLabs confirms, the voice model exists at the provider.
- The concealment and human-claim lists are regexes: deterministic and
  testable, but a determined paraphrase can slip past; the identity rules and
  the opening disclosure are the primary control. After the review they cover
  owner impersonation ("this is/it's/I'm <owner>", "<owner> here/speaking")
  through ONE shared list (`voice_twin.owner_claim_patterns`) used by the
  opening filter, the post-call check and the save-time check. Owner names are
  the profile name, every consent signature and the name calls use. A
  nickname the owner never entered anywhere is not known.
- The live banner shows only calls started in the last 20 minutes (a call
  lasts at most 15) and stops polling while AI calling is off (review L7).
- The pause is per account and blocks ALL its AI calls (stock voice too), not
  only clone calls — stricter than the brief, on purpose.

## 11. Test plan
- `tests/test_voice_twin_guards.py` — guards 1–8 (**report for sealing**).
- `tests/test_voice_twin.py` — lifecycle with a fake ElevenLabs, provider
  request shapes with a fake httpx, live notify/banner/takeover, inbound tools
  (booking through the host lock, messages), GDPR for lead-less calls, flag.
- `tests/test_voice_twin_migration.py` — model match, outbound default,
  name lengths, no audio column, lossy downgrade.
- `tests/test_phone_migration.py` / `tests/test_phone_calls.py` — updated for
  the contract change (0027+0089 build `calls`; voicemail opens with the
  disclosure).
- `frontend/src/tests/voiceTwin.test.ts` — API body shapes (raw audio body,
  consent object, verbs), consent-required state, revoke states, sample checks.

## 12. Success metric (measured, never promised)
Share of AI calls with a ready clone used (`calls.voice_clone_used`), inbound
calls answered and their outcomes (`direction='inbound'`, `outcome`),
meetings booked by the inbound tool (`calendar_bookings.notes`), and
**disclosure incidents = 0** (`compliance_audit_log.decision='ai_claimed_human'`).

## 13. Review round (2026-10-12)

An independent review found 1 HIGH, 6 MEDIUM and 9 LOW issues and 5
surviving mutations. Each probe was ported into
`tests/test_voice_twin_guards.py` (or the vitest file) as a test of the FIXED
behaviour. "Pre-fix" is that test run against the code as first delivered
(snapshot of the worktree before this round): **51 of the new guard tests
failed** there (`voice-twin_review_prefix.txt`); the 4 mutation-kill tests
(M7, M9, M11, M16) passed there because they pin behaviour that already
existed and only lacked a test. Frontend: 4 of 13 vitest cases failed pre-fix.

| Finding | Fix (file:line) | Test | Pre-fix |
|---|---|---|---|
| H1 owner impersonation spoken in the clone voice, not detected | `app/services/voice_twin.py:290` `enforce_opening(..., owner_names)` drops any sentence claiming to be human or the owner; `:371` `owner_claim_patterns` (one shared list); `:308` `strip_identity_claims` for script fields in `app/services/phone_calls.py:246`; names passed at `phone_calls.py:443`, `app/workers/outreach_tasks.py:1450`, `app/integrations/phone_channel.py:66/99` (names also read from the DB) | `TestReviewH1OwnerImpersonation` (4 tests, 11 cases) | 10 failed ("I am Rehan Masood." was already caught) |
| M1 concealment bypasses on save; send-time check without names | `voice_twin.py:389` new rules (deny_on_ask, deflect_on_ask, act_human, keep-secret/hide, more verbs), `:429` owner patterns; `:220` `owner_names` used at every save point and in `prepare_call` | `TestReviewM1ConcealmentOnSave` (10) | 10 failed |
| M2 transport errors 500 on revoke, stop the beat, abort erasure | `app/integrations/voice_providers.py:70` `_transport()` wraps httpx errors; `voice_twin.py:988` `_delete_at_provider` never raises; per-clone try in `retry_pending` `:1111` and erasure `:1143` | `TestReviewM2NetworkErrors` (3) | 3 failed |
| M3 erasure leaves the voiceprint with no retry | `app/db/models.py:5898` `VoiceCloneDeletion`; migration 0089; `voice_twin.py:1050/1078`; `account_erasure.PROVIDER_DELETION_QUEUE` (`account_erasure.py:172`); `account_export.EXCLUDED` | `TestReviewM3ErasureTombstone` | failed |
| M4 first account takes the shared number | `voice_twin.py:1235` `own_number` (user-scoped, admin exception); `app/api/voice_twin.py:324`; admin assignment `:433` | `TestReviewM4OwnNumberOnly` (3) | 2 failed (the admin case passed: same as before) |
| M5 revoke undone by a concurrent upload/refresh | `voice_twin.py:778` `_transition` (conditional UPDATE … WHERE status IN …, re-read); used by upload, submit, refresh; an id created for a clone revoked meanwhile is deleted/queued | `TestReviewM5RevokeIsFinal` (2) | 2 failed |
| M6 ElevenLabs multi-line turns flattened | `app/api/calls.py:521` passes structured turns; `voice_twin.py:500` continuation lines stay with their speaker | `TestReviewM6ElevenLabsTurns` (2) | 2 failed |
| L1 detector misses and false positives | `voice_twin.py:467` `_HUMAN_CLAIMS` rewritten ("recording" removed; "human resources" excluded; A.I., real live person, "not a bot", talking to a human, real person here) | `TestReviewL1DetectorPrecision` (12) | 8 failed |
| L2 non-Latin-1 `X-Filename` throws in fetch | `frontend/src/lib/api/client.ts:275` `encodeURIComponent`; server `unquote` `app/api/voice_twin.py:154` | `test_l2_…` + vitest "percent-encoded" | failed |
| L3 25 MB body read before the checks | `assert_can_upload` / `assert_can_verify` before `_read_audio` (`app/api/voice_twin.py:147`) | `test_l3_…` | failed |
| L4 stored consent text ≠ shown | `voice_twin.py:703` `record_consent(text_shown=…)`; API `consent_text`; frontend `consentTextFor` | `test_l4_…` + vitest | failed |
| L5 preview model ≠ call model | `voice_twin.py:1178` passes `ELEVEN_VOICE_MODEL` | `test_l5_…` | failed |
| L6 `control_url_ok` raises / accepts escaped hosts | `voice_providers.py:207` parsed with httpx, strict DNS-name regex, no userinfo/port, never raises | `test_l6_…` (14 cases) | 5 failed |
| L7 mic not released; banner polls with calling off; stale banner | `VoiceTwinCard.tsx:60` cleanup; `/voice-twin/live-calls` → `{calling_enabled, calls}`, `liveCallsPollMs`; `LIVE_WINDOW` 20 min (`voice_twin.py:1563`) | `test_l7_…`, vitest "never polls" | failed |
| L8 post-call check exception 500s after the dedupe commit | `app/api/calls.py:402` `_safe_post_call_check` (log, continue to `enqueue_analysis`) | `test_l8_…` | failed |
| L9 workspace exposure; who may change the transfer number | owner-only change (403) `app/api/voice_twin.py:297`; masked for members `voice_twin.py:1212`; documented in §2 "Workspace exposure" | `test_l9_…` | failed |
| Mutation M7 | (kept) | `test_m7_…` | passed (killer test) |
| Mutation M9 | (kept) | `test_m9_…` | passed (killer test) |
| Mutation M11 | (kept) | `test_m11_…` | passed (killer test) |
| Mutation M13 | see M6 | `TestReviewM6ElevenLabsTurns` | failed |
| Mutation M16 | (kept; checks now also run before the body is read) | `test_m16_…` (3) | passed (killer test) |
| Guard 7 assertions | exact results `deferred_awaiting_send_approval`, `held_plan_limit` | `TestGuard7ExistingGates` | — |
| Moved tests | control-URL allowlist → `test_l6_control_allowlist_on_the_transfer_itself`; export redaction → `TestGdprExportRedaction` | guard file | — |

**Mutation run** (the reviewer's `mutate.py`, adapted only where this round
changed the mutated line: M3, M5, M6, M12, M13, M14), on a copy of the tree:
all 16 mutations are killed (every run exits 1 with ≥ 1 failing test).

Not possible as asked: putting the deletion queue in `account_erasure.KEPT`.
That dict is pinned exactly by the sealed `tests/test_account_erasure.py`, and
KEPT holds OWNERSHIP tables only; an ownerless queue is the honest model
(EXCLUDED from the export with its reason, documented in `account_erasure`).
