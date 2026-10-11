"""Product defect #11: a GDPR lead erasure kept the lead's scores --
ai_booking_likelihood (with its factor values) and every fpta_* sub-score,
reason and timestamp -- on the tombstone row. Scores and their reasons are
derived from the erased personal data (job title, company, posts, signals), so
they are personal data about the person (GDPR Art. 4(1)) and go with the rest
(Art. 17). Basis needs founder/legal confirmation.
"""

from datetime import datetime, timezone

from app.db import models as m
from tests.test_leads_api import seed_leads

SCORE_FIELDS = (
    "ai_booking_likelihood", "conversion_factors_json",
    "fpta_fit", "fpta_problem", "fpta_timing", "fpta_access", "fpta_overall",
    "fpta_reasons_json", "fpta_method", "fpta_scored_at",
)


def test_erasure_clears_every_score(leads_client, db_session, verified_strategy):
    lead = seed_leads(db_session, verified_strategy, n=1)[0]
    lead.ai_booking_likelihood = 82
    lead.conversion_factors_json = [{"factor": "seniority", "value": "Owner"}]
    lead.fpta_fit, lead.fpta_problem, lead.fpta_timing = 90, 70, 40
    lead.fpta_access, lead.fpta_overall = 60, 68
    lead.fpta_reasons_json = {"fit": {"score": 90, "reason": "Owner at Acme Fire"}}
    lead.fpta_method = "model"
    lead.fpta_scored_at = datetime(2026, 10, 1, tzinfo=timezone.utc)
    db_session.commit()

    assert leads_client.delete(f"/leads/{lead.id}").status_code == 204

    db_session.refresh(lead)
    assert {f: getattr(lead, f) for f in SCORE_FIELDS} == {f: None for f in SCORE_FIELDS}
    assert lead.status is m.LeadStatus.DROPPED
