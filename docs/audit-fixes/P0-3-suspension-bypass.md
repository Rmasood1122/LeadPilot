# P0-3 — Account Suspension Bypass: Fix Report

- **Status:** FIXED
- **Date:** 2026-09-24
- **Commit:** 6e11abe on feature/8-new-features
- **Audit reference:** RED FLAG 3 (RF-3) in audit_findings.md

## The bug
`get_current_user` — the single auth chokepoint every protected route
resolves through, API keys included — never checked `User.is_suspended`.
Only `require_admin` and `_workspace_principal` did. A suspended user kept
full API access with existing tokens and could mint fresh ones through
/auth/login and /auth/refresh.

## The fix
A suspension check inside `get_current_user` in `app/services/auth.py`,
placed before the email-verification gate, raising the same
`HTTPException(status_code=403, detail="account suspended")` style the
file already uses. Six lines. Every protected route now refuses suspended
accounts at the chokepoint.

## Correction to the audit documents
`get_current_user` is defined in `app/services/auth.py`. The audit's
`app/core/dependencies.py` does not exist — the third wrong path found in
the audit docs.

## Verification
- Red: tests/test_account_suspension.py — 4 suspended-user tests
  (access token, API key, token from login, token from refresh) each
  failed with `assert 200 == 403` before the fix; 2 unsuspended-user
  tests passed throughout.
- Green: 6/6 in the new file; 24-module auth/admin sweep = 693 passed,
  0 failed. Remaining skips/errors are PostgreSQL-only and identical
  without the change.

## Bypass-path inventory (checked, not changed)
- /auth/login and /auth/refresh still ISSUE tokens to suspended accounts;
  the tokens are refused at every protected route. Tightening issuance is
  a logged P1 follow-up (touches app/api/auth.py + auth_sessions).
- SSE stream (/crm/stream) is covered via its ticket-minting endpoint.
- No websocket auth exists; API keys go through get_current_user.

## Follow-ups logged (not fixed here)
- Admin resume endpoint: any active admin can unsuspend anyone; no role
  hierarchy exists (only is_admin) — scoping is a product decision.
- AdminService.suspend_user/unsuspend_user: deprecated datetime.utcnow(),
  legacy User import path, no record of who resumed an account.
- app/core/admin_bootstrap.py hard-codes a personal email looked up at
  startup — move to config.
