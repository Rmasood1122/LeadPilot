"""Adapters for T30-T32 and T34: the verification judge and fixer, the
Autopilot sequence briefs / send-time plan, and the sequence red-team review.

Every adapter calls the function production calls, with get_client() pointed
at the replay (or live) client, and returns what the app is left with after
its own parsing and guards. Nothing is sent: push notifications from the
verification loop are swallowed (_no_notifications), and the learned-rate
Redis read of send-time placement is a cache miss (_placement_seams).
"""

from __future__ import annotations

from contextlib import contextmanager
from datetime import datetime, timedelta, timezone
from unittest import mock
from zoneinfo import ZoneInfo

from evals.ai.adapters._registry import adapter
from evals.ai.context import fresh_session, seed_account, seed_lead, use_client


@contextmanager
def _bound(module, client):
    """Point `module.get_client` (bound by name at import) at `client`.

    use_client() patches every binding that IS the gateway's current
    get_client. Under the offline suite, tests/conftest.py no_real_anthropic
    swaps that function per test but skips loop.py (its import of get_client
    is a multi-line parenthesised one its top-level regex does not see), so
    loop.get_client can hold a previous test's refusing stub. Binding it here
    keeps the adapter on the client it was given whatever ran before."""
    original = module.get_client
    module.get_client = lambda: client
    try:
        yield
    finally:
        module.get_client = original


@contextmanager
def _no_notifications():
    """The loop ends with notifications.dispatch(notify_*(...)), a push to the
    owner's devices. Close the coroutine unrun: an eval never sends."""
    from app.services import notifications  # noqa: PLC0415

    with mock.patch.object(notifications, "dispatch", lambda coro: coro.close()):
        yield


def _seed_research(db, strategy, research: dict | None) -> None:
    """research: {phase_no: synthesis text}. Phase syntheses are the steps
    whose step_no is a multiple of 9 (phase n -> step 9n), as the pipeline
    stores them."""
    from app.db import models as m  # noqa: PLC0415

    for phase, text in sorted((research or {}).items(), key=lambda kv: int(kv[0])):
        phase = int(phase)
        db.add(m.ResearchStep(strategy_id=strategy.id, pipeline=m.PipelineKind.STRATEGY,
                              phase=phase, step_no=9 * phase, step_id=f"s{phase}.09",
                              name=f"Phase {phase} synthesis", output=str(text),
                              model="eval-replay"))
    db.flush()


# --- T30 verification judge / T31 verification fixer ---------------------

def _run_loop(inp: dict, client, default_attempts: int) -> dict:
    """run_verification_loop on a seeded strategy, as the Celery task runs it.

    A model answer the app cannot use raises out of the loop; the task
    (app/workers/tasks.py run_verification) then rolls back and retries or
    fails the strategy. The adapter does the same rollback and reports the
    status the strategy is left in -- the thing that decides whether it ships.
    """
    from app.db import models as m  # noqa: PLC0415
    from app.verification import loop  # noqa: PLC0415

    db = fresh_session()
    try:
        _user, _product, strategy = seed_account(db)
        strategy.strategy_document = inp.get("document", "")
        strategy.gtm_document = inp.get("gtm")
        _seed_research(db, strategy, inp.get("research"))
        db.commit()
        raised = None
        with use_client(client), _bound(loop, client), _no_notifications():
            try:
                loop.run_verification_loop(db, strategy,
                                           max_attempts=int(inp.get("max_attempts", default_attempts)))
            except Exception as exc:  # noqa: BLE001 -- what the task sees
                raised = f"{type(exc).__name__}: {exc}"[:300]
                db.rollback()
        db.refresh(strategy)
        log = strategy.verified_passes_json or []
        final: dict[int, dict] = {}
        for entry in log:
            final[entry["pass_no"]] = entry  # last attempt of each pass wins
        ships = strategy.status in (m.StrategyStatus.VERIFIED, m.StrategyStatus.EXECUTING)
        legal = final.get(4)
        document = strategy.strategy_document or ""
        return {
            "status": strategy.status.value,
            "ships": ships,
            "raised": raised,
            "legal": legal["result"] if legal else None,
            "legal_outcome": (legal or {}).get("outcome"),
            "failed_passes": sorted(e["key"] for e in final.values() if e["result"] != "PASS"),
            "fixes_applied": sum(1 for e in log if e.get("fix_applied")),
            "document": document,
            # What a send would be built from: nothing unless the strategy ships.
            "shipped_document": document if ships else "",
        }
    finally:
        db.close()


@adapter("verification_judge")
def verification_judge(inp: dict, client) -> dict:
    """T30. Default one attempt per pass (a legal reverify value, 1-5), so
    each recorded output is one judgement of passes 1..10 in order."""
    return _run_loop(inp, client, default_attempts=1)


@adapter("verification_fixer")
def verification_fixer(inp: dict, client) -> dict:
    """T31. Default two attempts per pass: judge, fix (full rewrite), re-judge."""
    return _run_loop(inp, client, default_attempts=2)


# --- T32 Autopilot sequence briefs / send-time plan -----------------------

@contextmanager
def _placement_seams():
    """Two seams around send_time.place, neither touching its logic:

    * learned reply rates come from Redis; a miss (None) is the real state of
      an account below best_time_min_sends, so no socket is opened;
    * `enabled` reads the best_time_scheduling_enabled setting, exactly as
      send_time.enabled does in production. tests/conftest.py
      best_time_scheduling_off replaces it with `False` for every test, which
      would turn placement into a no-op here."""
    from app.services import send_time, system_settings  # noqa: PLC0415

    def _enabled(db):
        return bool(system_settings.get(db, send_time.FLAG))

    with mock.patch.object(send_time, "cached_learned", lambda *_a, **_k: None), \
            mock.patch.object(send_time, "enabled", _enabled):
        yield


def _briefs(inp: dict, client) -> dict:
    from app.services import adversarial_review, autopilot  # noqa: PLC0415

    db = fresh_session()
    try:
        user, _product, strategy = seed_account(
            db, product_name=inp.get("product_name", "Brightline Bookkeeping"),
            description=inp.get("product_description",
                                "Monthly bookkeeping and payroll for small UK agencies."))
        _seed_research(db, strategy, inp.get("research"))
        db.commit()
        channel = inp.get("channel", "email")
        with use_client(client):
            steps, source = autopilot.plan_steps(db, strategy, channel)
        # What Autopilot does next: a DRAFT sequence whose step templates are
        # these briefs, then the launch review. Its deterministic rules are
        # what can block; they run here with no model call.
        sequence = autopilot.create_sequence(db, strategy, user, channel, steps)
        db.commit()
        codes = sorted({f["code"] for f in adversarial_review.rule_findings(db, sequence)
                        if f["severity"] == adversarial_review.BLOCK})
        return {
            "source": source,
            "step_count": len(steps),
            "delays": [s["delay_days"] for s in steps],
            "briefs": "\n".join(s["brief"] for s in steps),
            "review_blocks": codes,
            "review_blocked": bool(codes),
        }
    finally:
        db.close()


def _send_time(inp: dict, client) -> dict:
    from app.services import send_time  # noqa: PLC0415

    db = fresh_session()
    try:
        _user, _product, strategy = seed_account(db)
        strategy.pattern_inputs_json = {"icp": inp.get("icp") or {}}
        lead = seed_lead(db, strategy, enrichment_json={"timezone": inp.get("tz", "America/New_York")})
        db.commit()
        now = datetime.fromisoformat(inp.get("now", "2026-10-19T12:00:00+00:00"))
        with use_client(client):
            plan = send_time.ensure_plan(db, strategy, now=now)
        channel = inp.get("place_channel", "email")
        with _placement_seams():
            slot = send_time.place(db, strategy, lead, channel, now, spread_key=str(lead.id))
        local = slot.astimezone(ZoneInfo(inp.get("tz", "America/New_York")))
        chans = plan.get("channels") or {}
        return {
            "source": plan.get("source"),
            "email_basis": (chans.get("email") or {}).get("basis"),
            "linkedin_basis": (chans.get("linkedin") or {}).get("basis"),
            "whatsapp_basis": (chans.get("whatsapp") or {}).get("basis"),
            "plan": plan,
            "slot_day": local.strftime("%a"),
            "slot_hour": local.hour,
            "slot_delay_hours": round((slot - now) / timedelta(hours=1), 2),
        }
    finally:
        db.close()


@adapter("autopilot_plan")
def autopilot_plan(inp: dict, client) -> dict:
    """T32. inp.call = "briefs" (autopilot.plan_steps, then the draft sequence
    and the launch review's rules) or "send_time" (send_time.ensure_plan,
    then send_time.place for one lead)."""
    if inp.get("call") == "send_time":
        return _send_time(inp, client)
    return _briefs(inp, client)


# --- T34 sequence red-team review ------------------------------------------

@adapter("sequence_red_team")
def sequence_red_team(inp: dict, client) -> dict:
    """adversarial_review.run_review on a seeded sequence: the deterministic
    rules plus the model pass (WARN only)."""
    from app.db import models as m  # noqa: PLC0415
    from app.services import adversarial_review as ar  # noqa: PLC0415
    from app.services import system_settings  # noqa: PLC0415

    db = fresh_session()
    try:
        _user, _product, strategy = seed_account(db)
        system_settings.set(db, "sequence_review_model_enabled",
                            bool(inp.get("model_enabled", True)))
        channel = m.ChannelType(inp.get("channel", "email"))
        sequence = m.Sequence(strategy_id=strategy.id, name=inp.get("name", "Agency intro"),
                              channel=channel, status=m.SequenceStatus.DRAFT)
        db.add(sequence)
        db.flush()
        for i, template in enumerate(inp.get("steps") or [], start=1):
            # A WhatsApp step is a TEMPLATE step with no template chosen: the
            # case where the rules must demand an approved template.
            db.add(m.SequenceStep(
                sequence_id=sequence.id, step_no=i, template=template, variant="A",
                delay_days=0 if i == 1 else 3,
                whatsapp_kind=m.WhatsAppStepKind.TEMPLATE
                if channel is m.ChannelType.WHATSAPP else None))
        db.commit()
        db.refresh(sequence)
        with use_client(client):
            review = ar.run_review(db, sequence)
        findings = review.findings_json or []
        model = [f for f in findings if f["source"] == "model"]
        return {
            "status": review.status,
            "blocking_count": review.blocking_count,
            "codes": sorted({f["code"] for f in findings}),
            "block_codes": sorted({f["code"] for f in findings if f["severity"] == ar.BLOCK}),
            "model_findings": len([f for f in model if f["code"] != "system:model_unavailable"]),
            "model_block_count": sum(1 for f in model if f["severity"] == ar.BLOCK),
            "model_unavailable": any(f["code"] == "system:model_unavailable" for f in model),
            "model_text": " ".join(f["message"] for f in model),
        }
    finally:
        db.close()
