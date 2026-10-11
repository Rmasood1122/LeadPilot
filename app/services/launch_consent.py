"""Manual launch lawful basis -- LEGAL GUARD.

Spec: docs/features/autopilot-launch.md section 3.5.

Launching a sequence (POST /sequences/{id}/enroll, and a manager approving an
SDR's launch) requires the person to confirm, server-side, that they may
lawfully contact the leads being enrolled -- the same mechanism as the
Autopilot opt-in (app/services/autopilot.py): `lawful_basis_confirmed: true`
plus the CURRENT text version, else 422 with a plain reason and nothing is
enrolled. Every confirmation that leads to a launch (or a launch request) is
recorded -- who, when, the text version and the exact text -- in
compliance_audit_log (kept as proof on account erasure) and
security_audit_events, in the same transaction as the launch.

Before this, the confirmation was a browser checkbox only and the server
recorded nothing.

`enforced()` is always True in production. It exists so suites that test
other launch gates -- including sealed suites that launch with an empty body
-- can run with this gate off (tests/conftest.py `launch_lawful_basis_off`,
the same pattern as `daily_send_approval_off`); tests/test_launch_lawful_basis.py
turns it back on and asserts the default.
"""

from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy.orm import Session

from app.db.models import ComplianceAuditLog, Sequence

#: Bump the VERSION whenever the TEXT changes; the version and the exact text a
#: person confirmed are recorded with each launch.
VERSION = "launch-lawful-basis-2026-10-11"
TEXT = (
    "I have read the list of leads and I confirm I may lawfully contact each of these "
    "people on this sequence's channels (CAN-SPAM, GDPR, CASL, PDPA as they apply). "
    "This sends real messages from my connected accounts."
)

AUDIT_CHANNEL = "launch"
AUDIT_DECISION = "launch_lawful_basis"
SECURITY_ACTION = "sequence.launch_lawful_basis"


class LaunchConsentError(ValueError):
    """422: the confirmation is missing or for an old text."""


def enforced() -> bool:
    return True


def text() -> dict:
    return {"version": VERSION, "text": TEXT}


def check(confirmed: bool | None, text_version: str | None) -> None:
    if not enforced():
        return
    if confirmed is not True or text_version != VERSION:
        raise LaunchConsentError(
            "Launching needs your confirmation that you have a lawful basis to contact "
            "these leads: send lawful_basis_confirmed=true and lawful_basis_text_version="
            f"\"{VERSION}\" (the text is at GET /launch/lawful-basis).")


def is_confirmed(payload: dict | None) -> bool:
    payload = payload if isinstance(payload, dict) else {}
    return payload.get("lawful_basis_confirmed") is True and \
        payload.get("lawful_basis_text_version") == VERSION


def record(db: Session, *, sequence: Sequence, owner_id, actor_id, request=None,
           lead_statuses=None, outcome: str, enrolled: int | None = None) -> None:
    """Add the audit rows (the caller commits, with the launch)."""
    if not enforced():
        return
    from app.services import security_audit  # noqa: PLC0415

    db.add(ComplianceAuditLog(
        user_id=owner_id, lead_id=None, message_id=None, channel=AUDIT_CHANNEL,
        region=None, regime=None, decision=AUDIT_DECISION,
        checks_json={"sequence_id": str(sequence.id), "strategy_id": str(sequence.strategy_id),
                     "actor_user_id": str(actor_id), "text_version": VERSION, "text": TEXT,
                     "lead_statuses": [getattr(s, "value", s) for s in (lead_statuses or [])],
                     "outcome": outcome, "enrolled": enrolled,
                     "at": datetime.now(timezone.utc).isoformat()}))
    security_audit.record(db, action=SECURITY_ACTION, request=request, user_id=actor_id,
                          owner_user_id=owner_id, target_type="sequence",
                          target_id=sequence.id,
                          details={"text_version": VERSION, "outcome": outcome})
