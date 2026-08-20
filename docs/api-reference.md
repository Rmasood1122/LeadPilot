# API Reference — ClientHunter Enterprise

Base URL (production): `https://api.yourdomain.com/api/v1`
Base URL (local dev): `http://localhost:8000/api/v1`

All endpoints except `/health` and `/auth/register` + `/auth/login` require:
```
Authorization: Bearer <access_token>
```

---

## Authentication

### POST /auth/register
Create a new account.
```json
Request:  { "email": "you@example.com", "password": "Str0ng!Pass" }
Response: { "access_token": "...", "refresh_token": "..." }
```

### POST /auth/login
```json
Request:  { "email": "you@example.com", "password": "Str0ng!Pass" }
Response: { "access_token": "...", "refresh_token": "..." }
```

### POST /auth/refresh
```json
Request:  { "refresh_token": "..." }
Response: { "access_token": "..." }
```

---

## Products

### POST /products
Create a product or skill to acquire clients for.
```json
Request: {
  "name": "LeadPilot",
  "description": "AI-powered client acquisition automation",
  "type": "product"   // "product" | "service" | "skill"
}
Response: { "id": "...", "name": "...", "user_id": "..." }
```

### GET /products
List all products for the current user.

### GET /products/{id}
Get a single product. Includes `extracted_patterns_json` after past clients are submitted.

### POST /products/{id}/past-clients
Add a past client for pattern extraction.
```json
Request: {
  "details": "Acme Corp, 50 employees",
  "acquisition_story": "LinkedIn + email, closed in 2 weeks",
  "industry": "SaaS",
  "company_size": "11-50",
  "deal_size_usd": 12000,
  "acquisition_channel": "email",
  "trigger_event": "Series A announcement",
  "decision_maker_role": "VP Sales",
  "sales_cycle_days": 14
}
```

---

## Strategies

### POST /products/{product_id}/strategies
Create and run a strategy. Triggers the pipeline immediately.
```json
Request: { "flow_type": "with_clients" }   // "with_clients" | "no_clients"
Response: { "id": "...", "status": "pipeline_running", ... }
```

### GET /strategies/{id}
Get strategy status, documents, and verification results.
Key fields: `status`, `strategy_document`, `gtm_document`, `verified_passes_json`, `default_variant`.

### GET /strategies/{id}/steps
Get all research steps (72 or 144). Each step has `step_no`, `status`, `output`.

### POST /strategies/{id}/resume
Resume a stalled or partially-completed pipeline.

### GET /strategies/{id}/steps
Full step list. Filter by `?status=complete`.

---

## Leads

### POST /strategies/{id}/leads/source
Trigger Apollo sourcing + Hunter verification for the strategy's ICP.
Returns 422 if any verification pass has `result=FAIL`.

### GET /strategies/{id}/leads
List all verified leads for this strategy.

### GET /leads/{id}
Single lead detail including status, sequence status, outcomes.

### POST /leads/{id}/reply
Record/classify an inbound reply.
```json
Request: { "classification": "auto", "message": "Stop emailing me" }
Response: { "classification": "unsubscribe_request", ... }
```

### DELETE /leads/{id}
GDPR right-to-erasure. Wipes PII, creates tombstone. Returns 204.

### GET /leads/{id}/tombstone
Read the tombstone record for a deleted lead.

### GET /leads/{id}/outcomes
List all outcome events for this lead.

---

## Campaigns & Sequences

### GET /strategies/{id}/campaigns
List campaigns for this strategy.

### GET /strategies/{id}/sequences
List outreach sequences.

### POST /strategies/{id}/campaigns/{campaign_id}/pause
Pause a running campaign.

### POST /strategies/{id}/campaigns/{campaign_id}/resume
Resume a paused campaign.

---

## Playbook

### GET /playbook/scores
List playbook scores for the current user's strategies.
Query: `?strategy_id=...`

### GET /playbook/similar-strategies
Find strategies with similar ICPs.
Query: `?query=<product description>`

### POST /playbook/aggregate *(admin)*
Trigger nightly aggregation now.

### POST /playbook/promote-winners *(admin)*
Run A/B winner promotion.

---

## Webhooks (no auth — signed)

### POST /webhooks/whatsapp
Receive WhatsApp messages and status updates. Requires `X-Hub-Signature-256` header.

### POST /webhooks/calendly
Receive Calendly booking events. Requires `Calendly-Webhook-Signature` header.

---

## Health

### GET /health *(public)*
```json
{ "status": "ok", "components": { "database": {...}, "redis": {...}, "celery": {...} } }
```

### GET /health/learning-loop *(admin)*
Last aggregation run status.

### GET /health/channels *(auth required)*
Gmail, WhatsApp, Calendly integration health.

---

## Admin *(all require is_admin=True)*

See [app/api/admin.py](../app/api/admin.py) for full schema.

| Method | Path | Purpose |
|---|---|---|
| GET | /admin/users | List all users |
| POST | /admin/users/{id}/suspend | Suspend user |
| POST | /admin/users/{id}/unsuspend | Unsuspend user |
| GET | /admin/suppression-list | Global suppression list |
| POST | /admin/suppression-list | Add entry |
| DELETE | /admin/suppression-list/{email} | Remove entry |
| GET | /admin/task-errors | Celery task error log |
| POST | /admin/task-errors/{id}/resolve | Mark resolved |
| GET | /admin/circuit-breakers | Circuit breaker states |
| POST | /admin/circuit-breakers/{name}/reset | Reset to CLOSED |
| GET | /admin/playbook/scores | All playbook scores |
| POST | /admin/playbook/recompute | Trigger aggregation |
| GET | /admin/celery-stats | Queue depths + workers |
| POST | /admin/rotate-encryption-key | Re-encrypt all tokens |

---

## Error Response Format

```json
{
  "error": "compliance_error",
  "compliance_code": "MISSING_UNSUBSCRIBE",
  "message": "Email body must include a valid unsubscribe link",
  "request_id": "a1b2c3d4..."
}
```

All error responses include `request_id` for log correlation.

HTTP status codes:
- `200/201` — success
- `204` — success (no body, e.g. GDPR delete)
- `400` — bad request
- `401` — missing or invalid JWT
- `403` — forbidden (insufficient permissions or wrong owner)
- `404` — not found
- `422` — validation error or compliance error
- `500` — internal server error (details in logs, not in response)
- `503` — service unavailable (DB or Redis down)
