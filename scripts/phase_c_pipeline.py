"""Phase C — report on a real pipeline run and exercise what the run does not.

`leadpilot.run_pipeline` already chains through the parts of Phase C that
need accumulated research: the 72/144 steps, ICP extraction, the tactic
classifier, pattern_key derivation, and the 10 verification passes. This
script REPORTS on that chain from the database (so a claim of "verified"
is backed by rows, not by a log line), then exercises the two Claude-backed
services the chain never reaches: message personalization (send time) and
WhatsApp template drafting (user-initiated).

Usage:
    python scripts/phase_c_pipeline.py [<strategy_id>]

With no argument it picks the most recently updated strategy.
Exit code 0 = the run reached VERIFIED and every extra check passed.
"""

import sys
import traceback
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from sqlalchemy import select  # noqa: E402

from app.db.base import SessionLocal  # noqa: E402
from app.db.models import (  # noqa: E402
    Lead,
    PipelineKind,
    ResearchStep,
    SequenceStep,
    Strategy,
    StrategyStatus,
    WhatsAppTemplateStatus,
)
from app.pipeline.engine import pipelines_for_flow  # noqa: E402
from app.services.message_personalization import render_message  # noqa: E402
from app.services.whatsapp_templates import generate_drafts  # noqa: E402

_results: list[tuple[str, bool, str]] = []


def check(name: str, fn) -> None:
    try:
        detail = fn()
        _results.append((name, True, detail or ""))
        print(f"  PASS  {name}  {detail or ''}")
    except Exception as exc:  # noqa: BLE001 - harness reports, never masks
        _results.append((name, False, f"{type(exc).__name__}: {exc}"))
        print(f"  FAIL  {name}  {type(exc).__name__}: {exc}")
        traceback.print_exc()


def _pick_strategy(session, strategy_id: str | None) -> Strategy:
    if strategy_id:
        strategy = session.get(Strategy, strategy_id)
        if strategy is None:
            raise SystemExit(f"no strategy with id {strategy_id}")
        return strategy
    strategy = session.execute(
        select(Strategy).order_by(Strategy.updated_at.desc()).limit(1)
    ).scalars().first()
    if strategy is None:
        raise SystemExit("no strategies in the database")
    return strategy


def main() -> int:
    strategy_id = sys.argv[1] if len(sys.argv) > 1 else None
    session = SessionLocal()
    strategy = _pick_strategy(session, strategy_id)

    print("Phase C - real pipeline run report")
    print("=" * 62)
    print(f"strategy   {strategy.id}")
    print(f"flow_type  {strategy.flow_type}")
    print(f"status     {strategy.status}")
    if getattr(strategy, "error", None):
        print(f"error      {strategy.error}")

    expected_pipelines = pipelines_for_flow(strategy.flow_type)

    # ---- 1. every pipeline step persisted -------------------------------
    def _steps() -> str:
        parts = []
        for kind in expected_pipelines:
            rows = session.execute(
                select(ResearchStep).where(
                    ResearchStep.strategy_id == strategy.id,
                    ResearchStep.pipeline == kind,
                )
            ).scalars().all()
            empty = [r.step_no for r in rows if not (r.output or "").strip()]
            assert len(rows) == 72, f"{kind.value}: {len(rows)}/72 steps persisted"
            assert not empty, f"{kind.value}: empty output at steps {empty}"
            parts.append(f"{kind.value}=72/72")
        return "-> " + ", ".join(parts)

    print(f"[1] Pipeline steps ({len(expected_pipelines) * 72} expected)")
    check("pipeline.steps_persisted", _steps)

    # ---- 2. ICP extraction + tactic classifier + pattern_key ------------
    def _pattern() -> str:
        assert strategy.pattern_key, "pattern_key is NULL - the learning loop stays inert"
        payload = strategy.pattern_inputs_json
        assert isinstance(payload, dict) and payload, f"pattern_inputs_json not stored: {payload!r}"
        criteria = payload.get("criteria") or {}
        tactics = payload.get("tactics") or {}
        populated = [k for k, v in criteria.items() if v]
        assert populated, f"ICP extraction returned nothing usable: {criteria}"
        return (f"-> key={strategy.pattern_key[:16]}... "
                f"criteria={len(populated)} populated, "
                f"channels={tactics.get('channels')}, "
                f"motion={tactics.get('sales_motion')!r}, "
                f"cadence={tactics.get('cadence')!r}")

    print("[2] ICP extraction / tactic classifier / pattern_key")
    check("icp.pattern_key_derived", _pattern)

    # ---- 3. the 10 verification passes ----------------------------------
    def _verification() -> str:
        entries = strategy.verified_passes_json or []
        assert entries, "verified_passes_json is empty - the loop never ran"
        by_pass: dict[int, list[dict]] = {}
        for entry in entries:
            by_pass.setdefault(entry["pass_no"], []).append(entry)
        missing = [n for n in range(1, 11) if n not in by_pass]
        assert not missing, f"passes never ran: {missing}"
        # Attempts are appended in order, so the last entry per pass is final.
        failed = [n for n, a in by_pass.items() if a[-1]["result"] != "PASS"]
        retried = {n: len(a) for n, a in sorted(by_pass.items()) if len(a) > 1}
        fixes = sum(1 for e in entries if e.get("fix_applied"))
        detail = f"-> 10/10 passes ran, {10 - len(failed)} passing on final attempt"
        if retried:
            detail += f", retried={retried}, fixes_applied={fixes}"
        assert not failed, f"passes still failing at final attempt: {failed} ({detail})"
        return detail

    print("[3] Verification passes")
    check("verification.all_ten_pass", _verification)

    def _status() -> str:
        assert strategy.status is StrategyStatus.VERIFIED, (
            f"status is {strategy.status}, expected VERIFIED")
        return "-> VERIFIED"

    check("verification.status_verified", _status)

    # ---- 4. personalization (never reached by the pipeline chain) -------
    def _personalization() -> str:
        lead = Lead(
            strategy_id=strategy.id,
            source="phase_c_harness",
            full_name="Dana Whitfield",
            title="VP of Operations",
            company="Northwind Logistics",
            email="dana@northwind-logistics.example",
            status="new",
            enrichment_json={"company_domain": "northwind-logistics.example",
                             "enrichment": "40-person regional freight brokerage; "
                                           "failed a DOT audit last quarter"},
        )
        step = SequenceStep(
            step_no=1,
            variant="A",
            template=("Open with the DOT audit angle, name the specific "
                      "compliance risk, and ask for a 15-minute call."),
            delay_days=0,
        )
        subject, body = render_message(
            session, strategy, lead, step,
            booking_url="https://calendly.example/leadpilot/15min",
        )
        assert subject.strip(), "empty subject"
        assert body.strip(), "empty body"
        assert len(body) > 80, f"body suspiciously short: {body!r}"
        # The booking URL was explicitly requested - it must survive into the copy.
        assert "calendly.example" in body, f"booking link dropped from body: {body!r}"
        print(f"        subject: {subject}")
        print("        body:")
        for line in body.splitlines():
            print(f"          {line}")
        return f"-> subject={len(subject)} chars, body={len(body)} chars, booking link present"

    print("[4] Message personalization (send-time path)")
    check("personalization.render_message", _personalization)

    # ---- 5. WhatsApp template drafting (Claude-drafted from research) ---
    def _whatsapp_drafts() -> str:
        created = generate_drafts(session, strategy)
        try:
            assert created, "no drafts created"
            for row in created:
                assert row.status is WhatsAppTemplateStatus.DRAFT, (
                    f"{row.name}: created as {row.status}, expected DRAFT")
                assert row.body.strip(), f"{row.name}: empty body"
            names = ", ".join(r.name for r in created)
            return f"-> {len(created)} draft(s) passed validation: {names}"
        finally:
            # The harness must not leave template rows behind in the dev DB.
            for row in created:
                session.delete(row)
            session.commit()

    print("[5] WhatsApp template drafting")
    check("whatsapp_templates.generate_drafts", _whatsapp_drafts)

    session.rollback()  # the harness Lead/SequenceStep are transient - never persisted
    session.close()

    passed = sum(1 for _, ok, _ in _results if ok)
    total = len(_results)
    print("=" * 62)
    print(f"RESULT: {passed}/{total} passed")
    for name, ok, detail in _results:
        if not ok:
            print(f"  FAILED: {name}: {detail}")
    return 0 if passed == total else 1



if __name__ == "__main__":
    sys.exit(main())
