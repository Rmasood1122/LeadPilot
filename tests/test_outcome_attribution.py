"""Product defect #2: the learning loop and A/B promotion read
`outcomes.strategy_id` / `outcomes.variant`, but the send and reply paths wrote
the variant only into meta_json and never set strategy_id. The nightly
roll-up (score_decay JOINs strategies ON outcomes.strategy_id) and the A/B
statistics (WHERE strategy_id = :sid AND variant = :variant) therefore saw
none of the real sends and replies.

Fix: app/db/outcome_attribution.py fills both columns on every new Outcome at
flush time (from the lead, meta_json, the message, or the lead's latest sent
message), so every write path -- present and future -- is covered.
"""

import uuid
from datetime import timedelta

from sqlalchemy import select

from app.db import models as m
from app.db import outcome_attribution
from app.integrations.outreach_base import InboundMessage
from app.services import ab_testing, score_decay
from app.workers.outreach_tasks import route_inbound_impl, send_message_impl
from tests.conftest import NOW


def _send_first(db, lead, channel):
    msg = db.execute(select(m.Message).where(m.Message.lead_id == lead.id)).scalar_one()
    assert send_message_impl(db, msg.id, channel=channel, now=NOW) == "sent"
    return msg


def _outcome(db, lead, event):
    return db.execute(select(m.Outcome).where(
        m.Outcome.lead_id == lead.id, m.Outcome.event == event)).scalar_one()


def test_send_and_reply_outcomes_carry_strategy_and_variant(
        db_session, enrolled, verified_leads, verified_strategy,
        fake_channel, fake_claude, gmail_account):
    lead = verified_leads[0]
    msg = _send_first(db_session, lead, fake_channel)
    sent = _outcome(db_session, lead, m.OutcomeEvent.SENT)
    assert sent.strategy_id == verified_strategy.id
    assert sent.variant == msg.variant == "A"

    fake_claude.reply_verdicts["sounds great"] = "interested"
    route_inbound_impl(db_session, InboundMessage(
        provider_message_id="in1", thread_ref=msg.thread_ref,
        from_address=lead.email, to_address="sender@leadpilot.dev",
        subject="Re: hi", body="sounds great, tell me more", received_at=NOW),
        gmail_account)
    replied = _outcome(db_session, lead, m.OutcomeEvent.REPLIED)
    assert replied.strategy_id == verified_strategy.id
    assert replied.variant == "A"


def test_ab_statistics_and_learning_rollup_see_real_sends(
        db_session, enrolled, verified_leads, verified_strategy,
        fake_channel, fake_claude, gmail_account):
    verified_strategy.pattern_key = "pk-attribution"
    db_session.commit()
    for lead in verified_leads:
        _send_first(db_session, lead, fake_channel)

    # SQLite stores UUIDs as 32 hex chars; PostgreSQL (production) accepts the
    # dashed form auto_promote_winners passes. Same query either way.
    stats = ab_testing._load_variant_stats(db_session, verified_strategy.id.hex, "A")
    assert stats.sends == 3

    scores = score_decay.compute_scores_with_decay(db_session)
    assert scores["pk-attribution::A"]["raw_n"] == 3


def _two_sent_messages(db, strategy, external_id):
    """A lead that was sent step 1 (variant A) five days ago and step 2 (B)
    yesterday -- the case where guessing a variant goes wrong."""
    lead = m.Lead(strategy_id=strategy.id, source="apollo", external_id=external_id,
                  full_name="X", email=f"{external_id}@x.co", status=m.LeadStatus.CONTACTED)
    seq = m.Sequence(strategy_id=strategy.id, channel=m.ChannelType.EMAIL,
                     name="s", status=m.SequenceStatus.ACTIVE)
    db.add_all([lead, seq])
    db.flush()
    messages = {}
    for step, variant, age in ((1, "A", 5), (2, "B", 1)):
        msg = m.Message(sequence_id=seq.id, lead_id=lead.id, channel=m.ChannelType.EMAIL,
                        step_no=step, template="t", variant=variant,
                        status=m.MessageStatus.SENT, sent_at=NOW - timedelta(days=age))
        db.add(msg)
        messages[variant] = msg
    db.flush()  # sent earlier, as in production
    return lead, messages


def test_an_event_without_its_message_gets_no_variant(db_session, verified_strategy):
    """Review M5: a bounce or reply that is not linked to its message (e.g. a
    step-1 bounce arriving after step 2 went out) must not be credited to
    whichever variant was sent last. Only the outcome's own message counts."""
    lead, _ = _two_sent_messages(db_session, verified_strategy, "x1")
    db_session.add(m.Outcome(lead_id=lead.id, event=m.OutcomeEvent.BOUNCED,
                             channel="email", meta_json={}))
    db_session.add(m.Outcome(lead_id=lead.id, event=m.OutcomeEvent.REPLIED,
                             channel="whatsapp", meta_json={"classification": "interested"}))
    db_session.commit()
    for event in (m.OutcomeEvent.BOUNCED, m.OutcomeEvent.REPLIED):
        row = _outcome(db_session, lead, event)
        assert (row.strategy_id, row.variant) == (verified_strategy.id, None)


def test_an_event_with_its_message_gets_that_messages_variant(db_session, verified_strategy):
    lead, messages = _two_sent_messages(db_session, verified_strategy, "x2")
    db_session.add(m.Outcome(lead_id=lead.id, message_id=messages["A"].id,
                             event=m.OutcomeEvent.BOUNCED, channel="email",
                             meta_json={"variant": "ignored"}))
    db_session.commit()
    assert _outcome(db_session, lead, m.OutcomeEvent.BOUNCED).variant == "A"


def test_lead_added_in_the_same_flush(db_session, verified_strategy):
    lead = m.Lead(id=uuid.uuid4(), strategy_id=verified_strategy.id, source="apollo",
                  external_id="P", full_name="P", email="p@p.co")
    db_session.add(lead)
    db_session.add(m.Outcome(lead_id=lead.id, event=m.OutcomeEvent.UNSUBSCRIBED,
                             channel="email"))
    db_session.commit()
    row = _outcome(db_session, lead, m.OutcomeEvent.UNSUBSCRIBED)
    assert row.strategy_id == verified_strategy.id


def test_attribution_never_breaks_a_commit(db_session, verified_strategy, monkeypatch, caplog):
    """Review M4: a legacy list-shaped meta_json (or any resolver error) is
    logged and the outcome is still written."""
    lead = m.Lead(strategy_id=verified_strategy.id, source="apollo", external_id="Q",
                  full_name="Q", email="q@q.co")
    db_session.add(lead)
    db_session.flush()
    db_session.add(m.Outcome(lead_id=lead.id, event=m.OutcomeEvent.UNSUBSCRIBED,
                             channel="email", meta_json=["legacy", "list"]))
    db_session.commit()
    assert _outcome(db_session, lead, m.OutcomeEvent.UNSUBSCRIBED).strategy_id \
        == verified_strategy.id

    def _boom(*a, **k):
        raise RuntimeError("resolver exploded")

    monkeypatch.setattr(outcome_attribution, "resolve", _boom)
    db_session.add(m.Outcome(lead_id=lead.id, event=m.OutcomeEvent.OPTED_OUT,
                             channel="whatsapp"))
    with caplog.at_level("ERROR"):
        db_session.commit()
    assert _outcome(db_session, lead, m.OutcomeEvent.OPTED_OUT).variant is None
    assert "outcome attribution failed" in caplog.text


def test_audit_trail_payload_is_what_the_writer_recorded(db_session, verified_strategy):
    """Review M5 (audit trail): the hashed activity record keeps the payload
    the writer supplied; attribution does not add a variant to it."""
    from app.services import audit_trail  # noqa: F401 -- registers its listener
    lead, messages = _two_sent_messages(db_session, verified_strategy, "x3")
    db_session.add(m.Outcome(lead_id=lead.id, message_id=messages["A"].id,
                             event=m.OutcomeEvent.REPLIED, channel="email",
                             meta_json={"classification": "interested"}))
    db_session.commit()
    outcome = _outcome(db_session, lead, m.OutcomeEvent.REPLIED)
    assert outcome.variant == "A"
    record = db_session.execute(select(m.ActivityAuditEvent).where(
        m.ActivityAuditEvent.outcome_ref == outcome.id)).scalar_one()
    assert record.payload_json == {"classification": "interested"}


def test_explicit_values_and_system_events_are_left_alone(db_session, verified_strategy):
    lead = m.Lead(strategy_id=verified_strategy.id, source="apollo", external_id="Y",
                  full_name="Y", email="y@y.co")
    db_session.add(lead)
    db_session.flush()
    db_session.add(m.Outcome(lead_id=lead.id, event=m.OutcomeEvent.SENT,
                             strategy_id=verified_strategy.id, variant="C",
                             meta_json={"variant": "A"}))
    db_session.add(m.Outcome(event=m.OutcomeEvent.CIRCUIT_OPENED, channel="system"))
    db_session.commit()
    sent = _outcome(db_session, lead, m.OutcomeEvent.SENT)
    assert sent.variant == "C"
    system = db_session.execute(select(m.Outcome).where(
        m.Outcome.event == m.OutcomeEvent.CIRCUIT_OPENED)).scalar_one()
    assert system.strategy_id is None and system.variant is None


def test_backfill_fills_old_rows_once(db_session, verified_strategy):
    lead = m.Lead(strategy_id=verified_strategy.id, source="apollo", external_id="Z",
                  full_name="Z", email="z@z.co")
    db_session.add(lead)
    db_session.flush()
    # An old row, written before the listener existed.
    seq = m.Sequence(strategy_id=verified_strategy.id, channel=m.ChannelType.EMAIL,
                     name="s", status=m.SequenceStatus.ACTIVE)
    db_session.add(seq)
    db_session.flush()
    msg = m.Message(sequence_id=seq.id, lead_id=lead.id, channel=m.ChannelType.EMAIL,
                    step_no=1, template="t", variant="B", status=m.MessageStatus.SENT,
                    sent_at=NOW)
    db_session.add(msg)
    db_session.flush()
    with outcome_attribution.disabled():
        db_session.add(m.Outcome(lead_id=lead.id, message_id=msg.id,
                                 event=m.OutcomeEvent.SENT,
                                 meta_json={"step_no": 1, "variant": "B"}))
        # A bounce not linked to its message: strategy filled, variant not guessed.
        db_session.add(m.Outcome(lead_id=lead.id, event=m.OutcomeEvent.BOUNCED,
                                 meta_json={}))
        db_session.commit()
    old = _outcome(db_session, lead, m.OutcomeEvent.SENT)
    assert (old.strategy_id, old.variant) == (None, None)

    assert outcome_attribution.backfill(db_session, dry_run=True) == 2
    db_session.expire_all()
    assert _outcome(db_session, lead, m.OutcomeEvent.SENT).variant is None
    progress = []
    assert outcome_attribution.backfill(db_session, dry_run=False, batch_size=1,
                                        progress=progress.append) == 2
    assert progress  # one line per batch
    db_session.expire_all()
    old = _outcome(db_session, lead, m.OutcomeEvent.SENT)
    assert (old.strategy_id, old.variant) == (verified_strategy.id, "B")
    bounce = _outcome(db_session, lead, m.OutcomeEvent.BOUNCED)
    assert (bounce.strategy_id, bounce.variant) == (verified_strategy.id, None)
    assert outcome_attribution.backfill(db_session, dry_run=False) == 0


def test_promoted_winner_is_read_back_on_the_strategy_dashboard(
        client, db_session, enrolled, verified_leads, verified_strategy,
        fake_channel, fake_claude, gmail_account, test_user):
    """strategies.default_variant (written by auto-promotion) was never read.
    The campaigns dashboard now marks the promoted variant for that strategy."""
    _send_first(db_session, verified_leads[0], fake_channel)
    url = f"/crm/dashboard/campaigns?strategy_id={verified_strategy.id}"
    rows = client.get(url).json()["variants"]
    assert [(r["variant"], r["promoted"]) for r in rows] == [("A", False)]

    verified_strategy.default_variant = "A"
    db_session.commit()
    rows = client.get(url).json()["variants"]
    assert [(r["variant"], r["promoted"]) for r in rows] == [("A", True)]
    # Unfiltered view: a winner is per strategy, so nothing is marked.
    rows = client.get("/crm/dashboard/campaigns").json()["variants"]
    assert all(r["promoted"] is False for r in rows)


def test_backfill_script_is_a_dry_run_by_default(db_session, verified_strategy, monkeypatch,
                                                 capsys):
    from app.db import base
    from scripts import backfill_outcome_attribution as script

    lead = m.Lead(strategy_id=verified_strategy.id, source="apollo", external_id="S",
                  full_name="S", email="s@s.co")
    db_session.add(lead)
    db_session.flush()
    with outcome_attribution.disabled():
        db_session.add(m.Outcome(lead_id=lead.id, event=m.OutcomeEvent.BOUNCED, meta_json={}))
        db_session.commit()
    monkeypatch.setattr(base, "SessionLocal", lambda: db_session)
    monkeypatch.setattr(db_session, "close", lambda: None)

    assert script.main(["--batch-size", "1"]) == 0
    out = capsys.readouterr().out
    assert out.startswith("WARNING")
    assert "DRY RUN" in out and "scanned 1 outcomes" in out and "would update: 1" in out
    db_session.expire_all()
    assert _outcome(db_session, lead, m.OutcomeEvent.BOUNCED).strategy_id is None

    assert script.main(["--apply"]) == 0
    db_session.expire_all()
    assert _outcome(db_session, lead, m.OutcomeEvent.BOUNCED).strategy_id == verified_strategy.id
