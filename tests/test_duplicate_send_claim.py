"""P0-4 (audit: DUPLICATE SEND BUG) — the scheduled->sending claim must be atomic.

Two Celery workers can both read the same SCHEDULED message, both pass the
status guards at the top of send_message_impl, and — before this fix — both
set status=SENDING and both transmit. The fix replaces the naive ORM
attribute write with a conditional UPDATE (the meeting_prep_tasks._claim
pattern): only the worker whose UPDATE actually changed the row may send;
the loser sees rowcount == 0 and returns "lost_claim_race" without
transmitting.
"""

from sqlalchemy import select
from sqlalchemy.orm import sessionmaker

from app.db import models as m
from app.workers.outreach_tasks import send_message_impl
from tests.conftest import NOW, FakeChannel


class TestAtomicClaim:
    def test_two_workers_racing_for_one_scheduled_message_send_it_once(
            self, db_session, enrolled, verified_leads):
        # ------------------------------------------------------------------
        # WHY THIS TEST CANNOT PROVE THE FIX WORKS, AND WHAT IT PROVES INSTEAD
        #
        # This suite runs on in-memory SQLite (tests/conftest.py). SQLite has
        # a single writer and no row-level locks, and the StaticPool fixture
        # shares ONE connection, so genuinely concurrent UPDATEs — the thing
        # the bug is about — are physically impossible here. Nothing on
        # SQLite can demonstrate PostgreSQL's actual behaviour: two
        # simultaneous `UPDATE ... WHERE status = 'SCHEDULED'` statements,
        # one taking the row lock, the other BLOCKING until the first
        # commits and then re-evaluating its WHERE clause against the new
        # row version under READ COMMITTED, matching 0 rows.
        #
        # What we CAN reproduce deterministically is the race's essential
        # shape: worker B holds a STALE in-memory copy of the message
        # (status still SCHEDULED, read before worker A committed) — which
        # is exactly the state a losing worker is in at the moment it tries
        # to claim. We pre-load the message into worker B's session identity
        # map, let worker A complete a full send, then run worker B. B's
        # status guards all pass against its stale copy, so B reaches the
        # claim — and only the conditional UPDATE stands between B and a
        # second transmission. Under the old code (`message.status =
        # SENDING; commit()`) B overwrites SENT, renders, and transmits:
        # this test then fails with two sends. Under the fix, B's UPDATE
        # matches 0 rows and B backs off.
        #
        # A REAL PostgreSQL integration test (tests/integration/, once the
        # P1 "real PG test suite" item is built) would need to differ in
        # every mechanical respect:
        #   * run against a real PostgreSQL database, with a SEPARATE
        #     engine/connection per worker — never a shared StaticPool
        #     connection, or the race disappears;
        #   * run the two send_message_impl calls in two threads (or
        #     processes), synchronized with a threading.Barrier placed so
        #     both workers have loaded the message as SCHEDULED before
        #     either reaches the claim — otherwise the scheduler may
        #     serialize them and the test silently tests nothing;
        #   * assert the OUTCOME across both workers: exactly one returns
        #     "sent", the other returns one of "lost_claim_race" /
        #     "already_sent" / "in_flight_needs_review" (which one depends
        #     on where the loser's snapshot was taken), and the two fake
        #     channels together recorded exactly ONE transmission;
        #   * repeat the race many times (e.g. 50 iterations) — a
        #     concurrency test that passes once proves little, because
        #     thread scheduling decides whether the window was ever hit.
        # ------------------------------------------------------------------

        msg = db_session.execute(
            select(m.Message).where(m.Message.status == m.MessageStatus.SCHEDULED)
        ).scalars().first()
        assert msg is not None

        # Worker B: a second session on the same database, simulating a
        # second Celery worker. Loading the message NOW (before worker A
        # runs) plants the stale SCHEDULED copy in B's identity map —
        # session.get() inside send_message_impl will return this object
        # without re-querying, exactly like a worker whose read predates
        # the other worker's commit.
        worker_b_session = sessionmaker(
            bind=db_session.get_bind(), expire_on_commit=False)()
        try:
            stale = worker_b_session.get(m.Message, msg.id)
            assert stale.status is m.MessageStatus.SCHEDULED

            channel_a, channel_b = FakeChannel(), FakeChannel()

            # Worker A wins: full send completes and commits.
            assert send_message_impl(db_session, msg.id,
                                     channel=channel_a, now=NOW) == "sent"
            assert len(channel_a.sent) == 1

            # Worker B, still believing the message is SCHEDULED, passes
            # every status guard and reaches the claim. It must lose there
            # and must NOT transmit.
            out = send_message_impl(worker_b_session, msg.id,
                                    channel=channel_b, now=NOW)
            assert out == "lost_claim_race"
            assert channel_b.sent == [], "the losing worker transmitted — duplicate send"
        finally:
            worker_b_session.close()

        # The winner's result stands untouched in the database: still SENT,
        # still carrying worker A's provider ids, and exactly one SENT
        # outcome row (the learning loop counts these).
        db_session.expire_all()
        final = db_session.get(m.Message, msg.id)
        assert final.status is m.MessageStatus.SENT
        assert final.provider_message_id == "pm1"
        sent_outcomes = db_session.execute(
            select(m.Outcome).where(m.Outcome.message_id == msg.id,
                                    m.Outcome.event == m.OutcomeEvent.SENT)
        ).scalars().all()
        assert len(sent_outcomes) == 1