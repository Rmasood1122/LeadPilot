"""GDPR erasure against REAL PostgreSQL (migrated to head, so FKs, RESTRICT on
billing (0081) and the activity-trail trigger (0042) are all live).

tests/test_account_erasure.py proves the same on SQLite, once with foreign
keys ON as the closest stand-in. This is the dialect that ships: ~100 nested
IN (SELECT ...) deletes in FK order, SET NULL emulation, the tombstone UPDATE,
and the lead-level scrub of every table in account_erasure.LEAD_SCRUB.
(Review fix 8: promoted from the reviewer's probe.)
"""

from __future__ import annotations

import uuid

import pytest
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError

from app.db import models as m
from app.db.base import Base
from app.services import account_erasure as ae
from tests.test_account_erasure import NOW, _count, _populate, _user


def _u(db, tag):
    return _user(db, f"{tag}-{uuid.uuid4().hex[:6]}@erasure-pg.test")


def test_every_table_erased_for_one_account_and_untouched_for_another(db_session):
    alice, bob = _u(db_session, "alice"), _u(db_session, "bob")
    alice_id, bob_id = alice.id, bob.id
    _populate(db_session, alice_id)
    _populate(db_session, bob_id)
    ae.erase_account(db_session, alice, now=NOW)
    db_session.commit()
    bad = []
    for name, decision in ae.ERASURE.items():
        if _count(db_session, name, bob_id) != 1:
            bad.append(("bob touched", name))
        if decision == ae.DELETE and _count(db_session, name, alice_id) != 0:
            bad.append(("alice kept", name))
    assert bad == []
    # E1: the database itself refuses to cascade the kept billing rows away.
    users = Base.metadata.tables["users"]
    with pytest.raises(IntegrityError):
        db_session.execute(users.delete().where(users.c.id == alice_id))
    db_session.rollback()


def test_a_member_then_the_owner_of_a_shared_workspace(db_session):
    owner, member = _u(db_session, "owner"), _u(db_session, "member")
    owner_id, member_id = owner.id, member.id
    ids_owner = _populate(db_session, owner_id)
    _populate(db_session, member_id)
    db_session.add(m.WorkspaceMember(workspace_id=ids_owner["workspaces"], user_id=member_id,
                                     role="manager"))
    db_session.add(m.CrmNote(lead_id=ids_owner["leads"], author_user_id=member_id,
                             body="written by the member"))
    db_session.commit()

    ae.erase_account(db_session, member, now=NOW)
    db_session.commit()
    for name in ae.ERASURE:
        assert _count(db_session, name, owner_id) >= 1, name
    note = db_session.execute(select(m.CrmNote).where(
        m.CrmNote.body == "written by the member")).scalar_one()
    assert note.author_user_id is None

    ae.erase_account(db_session, db_session.get(m.User, owner_id), now=NOW)
    db_session.commit()
    for name, decision in ae.ERASURE.items():
        if decision == ae.DELETE:
            assert _count(db_session, name, owner_id) == 0, name


def test_the_lead_level_scrub_runs_on_postgres(db_session):
    alice = _u(db_session, "lead")
    ids = _populate(db_session, alice.id)   # a row in every table, all linked to one lead
    counts = ae.erase_lead_correspondence(db_session, ids["leads"], now=NOW)
    db_session.commit()
    assert counts["messages"] == 1 and counts["replies"] == 1
    call = db_session.get(m.Call, ids["calls"])
    assert call.to_number == ae.ERASED_TEXT and call.transcript is None
    booking = db_session.get(m.CalendarBooking, ids["calendar_bookings"])
    assert booking.invitee_email == ae.ERASED_EMAIL
    assert db_session.get(m.CrmNote, ids["crm_notes"]) is None
    message = db_session.get(m.Message, ids["messages"])
    assert message.body is None and message.unsubscribe_token is None
