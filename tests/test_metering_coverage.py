"""P0-5b -- every model call is metered to an account, not only the pipeline's.

BEFORE (P0-5, #55): the daily cap held for pipelines, verification and lead
scoring, but usage_meter.note() is a no-op outside a scope, and 30+ call sites
had none: support chat, intake, sequence review, style profile, roleplay,
strategy mutation, meeting summaries, the website builder, every inbound
reply. Their spend wrote no api_usage row -- neither counted nor capped. The
consensus OpenAI call lost its scope in a worker thread, and GPT-4o had no
pre-call gate at all. And owner_scope() armed the STRATEGY budget for sends,
briefs and scoring, so a strategy whose pipeline finished near its budget had
every send render refused.

NOW, pinned here:
  * representative routes, webhooks-path impls and tasks write api_usage rows
    with the account's id and the right purpose;
  * capped purposes answer 429 once the day is used up, before any work, and
    when the gateway refuses mid-request (even where the handler maps model
    failures to 502);
  * counted-only purposes (support chat, reply handling) keep working past
    the limit;
  * the strategy budget binds pipeline and verification only;
  * the consensus thread records into the caller's scope.

Offline: FakeClaude behind a stand-in gateway that does exactly what the real
ClaudeClient does around a call (check_budget before, note() after).
"""

from __future__ import annotations

import uuid

import pytest
from sqlalchemy import select

from app.db import models as m
from app.services import usage_meter

FREE_CAP = 10_000_000  # $10.00, app/core/plans.py "free"


@pytest.fixture()
def gateway(fake_claude, monkeypatch):
    """FakeClaude with the real gateway's metering around every call."""
    def _metered(fn):
        def call(system, prompt, max_tokens=None, temperature=None, schema=None):
            usage_meter.warn_if_unscoped("anthropic")
            usage_meter.check_budget(input_chars=len(system) + len(prompt),
                                     max_output_tokens=max_tokens or 4096)
            out = fn(system, prompt, max_tokens=max_tokens, temperature=temperature)
            usage_meter.note("anthropic", "fake-model", 1000, 500)
            return out
        return call

    monkeypatch.setattr(fake_claude, "complete", _metered(fake_claude.complete))
    monkeypatch.setattr(fake_claude, "complete_json", _metered(fake_claude.complete_json))
    return fake_claude


def _usage(db, user_id, purpose=None):
    q = select(m.ApiUsage).where(m.ApiUsage.user_id == user_id)
    if purpose is not None:
        q = q.where(m.ApiUsage.purpose == purpose)
    return db.execute(q).scalars().all()


def _spend(db, user_id, micros):
    db.add(m.ApiUsage(user_id=user_id, strategy_id=None, provider="anthropic", model="x",
                      purpose="pipeline", calls=1, input_tokens=0, output_tokens=0,
                      cost_micros=micros))
    db.commit()


SAMPLE = ("Hey Sam, quick one - did the new rota land okay with the team? "
          "Happy to jump on a call if it's easier. Cheers, Rehan")
CLIENTS = {"clients": [{"details": "Texas fire ITM company, 30 staff",
                        "acquisition_story": "Referral after a failed audit"}]}


# --------------------------------------------------------------------------
# Counted, with the account and the purpose
# --------------------------------------------------------------------------

class TestRoutesAreMetered:
    def test_style_profile(self, client, db_session, test_user, gateway):
        assert client.put("/me/style-profile", json={"samples": [SAMPLE]}).status_code == 200
        assert _usage(db_session, test_user.id, "drafting")

    def test_past_client_intake(self, client, db_session, test_user, gateway,
                                product_with_strategy):
        product, _ = product_with_strategy(m.FlowType.WITH_CLIENTS, with_past_client=False)
        resp = client.post(f"/products/{product.id}/past-clients", json=CLIENTS)
        assert resp.status_code == 201, resp.text
        assert _usage(db_session, test_user.id, "intake")

    def test_support_chat(self, client, db_session, test_user, gateway):
        resp = client.post("/support/chat", json={"message": "How do I connect Gmail?"})
        assert resp.status_code == 200, resp.text
        assert _usage(db_session, test_user.id, "support_chat")

    def test_lead_sourcing_icp_extraction(self, leads_client, db_session, test_user,
                                          verified_strategy, fake_claude, monkeypatch):
        # leads_client builds its own FakeClaude wiring; meter it the same way.
        rows_before = len(_usage(db_session, test_user.id, "icp"))
        from app.services import icp_extraction  # noqa: PLC0415

        real = icp_extraction.get_client

        class _Wrap:
            def __getattr__(self, name):
                return getattr(real(), name)

            def complete_json(self, system, prompt, **kw):
                usage_meter.note("anthropic", "fake-model", 1000, 500)
                return real().complete_json(system, prompt, **kw)

        monkeypatch.setattr(icp_extraction, "get_client", lambda: _Wrap())
        resp = leads_client.post(f"/strategies/{verified_strategy.id}/leads/source", json={})
        assert resp.status_code == 202, resp.text
        assert len(_usage(db_session, test_user.id, "icp")) > rows_before


class TestWorkersAreMetered:
    def test_inbound_reply_processing(self, db_session, test_user, gateway,
                                      verified_strategy):
        from app.workers import reply_tasks  # noqa: PLC0415

        lead = m.Lead(strategy_id=verified_strategy.id, source="seed", external_id="r1",
                      full_name="Pat", email="pat@acme.example", status=m.LeadStatus.CONTACTED)
        db_session.add(lead)
        db_session.flush()
        reply = m.InboundReply(lead_id=lead.id, from_address="pat@acme.example",
                               subject="Re: hi", body="Sounds good, can we talk Thursday?",
                               account_ref="x", channel=m.ChannelType.EMAIL)
        db_session.add(reply)
        db_session.commit()
        reply_tasks.process_inbound_reply_impl(db_session, reply.id)
        assert _usage(db_session, test_user.id, "reply_handling")

    def test_website_page(self, db_session, test_user, monkeypatch):
        from app.services import website_builder  # noqa: PLC0415
        from app.workers import site_tasks  # noqa: PLC0415

        def _gen(**kw):
            usage_meter.note("anthropic", "fake-model", 4000, 8000)
            return {"html_content": "<h1>x</h1>", "word_count": 1, "reading_time_mins": 1,
                    "internal_links": [], "schema_markup": {}}

        monkeypatch.setattr(website_builder, "generate_page_html", _gen)
        page = m.SitePage(title="T", slug=f"t-{uuid.uuid4().hex[:6]}", target_keyword="k",
                          meta_title="T", meta_description="d",
                          page_type=m.PageType.BLOG, status=m.PageStatus.DRAFT)
        db_session.add(page)
        db_session.commit()
        out = site_tasks.generate_page_impl(db_session, page.id, test_user.id)
        assert out["status"] == "generated"
        rows = _usage(db_session, test_user.id, "website")
        assert rows and rows[0].output_tokens == 8000


# --------------------------------------------------------------------------
# The cap on the request side
# --------------------------------------------------------------------------

class TestCap:
    def test_capped_route_is_refused_before_any_work(self, client, db_session, test_user,
                                                     gateway):
        _spend(db_session, test_user.id, FREE_CAP)
        before = gateway.completions
        resp = client.put("/me/style-profile", json={"samples": [SAMPLE]})
        assert resp.status_code == 429, resp.text
        assert resp.json()["detail"]["error"] == "daily_ai_limit_reached"
        assert gateway.completions == before, "no model call once the day is used up"

    def test_refusal_mid_request_is_429_not_502(self, client, db_session, test_user, gateway):
        # $0.01 left: the pre-check passes, the gateway's worst-case reserve
        # for a 1,500-token reply ($0.0225) does not. The handler maps model
        # failures to 502; the account cap is the real cause, so 429.
        _spend(db_session, test_user.id, FREE_CAP - 10_000)
        resp = client.put("/me/style-profile", json={"samples": [SAMPLE]})
        assert resp.status_code == 429, resp.text
        assert resp.json()["detail"]["error"] == "daily_ai_limit_reached"

    def test_intake_degrades_instead_of_failing(self, client, db_session, test_user,
                                                gateway, product_with_strategy):
        product, _ = product_with_strategy(m.FlowType.WITH_CLIENTS, with_past_client=False)
        _spend(db_session, test_user.id, FREE_CAP - 10_000)
        resp = client.post(f"/products/{product.id}/past-clients", json=CLIENTS)
        assert resp.status_code == 201, resp.text  # what the user typed is never lost
        patterns = resp.json()[0]["extracted_patterns_json"]
        # the null-pattern record, carrying the reason
        assert patterns["industry"] is None
        assert any("daily AI limit" in str(v) for v in patterns.values())

    def test_counted_only_purposes_keep_working(self, client, db_session, test_user, gateway):
        _spend(db_session, test_user.id, FREE_CAP * 2)
        resp = client.post("/support/chat", json={"message": "How do I connect Gmail?"})
        assert resp.status_code == 200, resp.text
        assert _usage(db_session, test_user.id, "support_chat")

    def test_every_purpose_is_classified(self):
        assert not (set(usage_meter.ACCOUNT_CAPPED_PURPOSES)
                    & set(usage_meter.COUNTED_ONLY_PURPOSES))


# --------------------------------------------------------------------------
# The strategy budget binds the pipeline only (bug fixed with P0-5b)
# --------------------------------------------------------------------------

class TestStrategyBudgetScope:
    @pytest.fixture()
    def spent_strategy(self, db_session, product_with_strategy):
        _, strategy = product_with_strategy(m.FlowType.WITH_CLIENTS)
        strategy.budget_micros = 1_000_000
        db_session.add(m.ApiUsage(user_id=None, strategy_id=strategy.id, provider="anthropic",
                                  model="x", purpose="pipeline", calls=1, input_tokens=0,
                                  output_tokens=0, cost_micros=999_000))
        db_session.commit()
        return strategy

    @pytest.mark.parametrize("purpose", ["outreach", "meeting_prep", "lead_scoring"])
    def test_sends_briefs_and_scoring_are_not_bound_by_it(self, db_session, spent_strategy,
                                                          purpose):
        with usage_meter.owner_scope(db_session, spent_strategy, purpose):
            usage_meter.check_budget(input_chars=3000, max_output_tokens=4096)  # no raise

    @pytest.mark.parametrize("purpose", ["pipeline", "verification"])
    def test_pipeline_and_verification_still_are(self, db_session, spent_strategy, purpose):
        with usage_meter.owner_scope(db_session, spent_strategy, purpose):
            with pytest.raises(usage_meter.BudgetExceededError):
                usage_meter.check_budget(input_chars=3000, max_output_tokens=4096)


# --------------------------------------------------------------------------
# Consensus: the OpenAI half records into the caller's scope
# --------------------------------------------------------------------------

class TestConsensusThread:
    def test_openai_spend_lands_in_the_pipeline_scope(self, db_session, verified_strategy,
                                                      fake_claude, monkeypatch):
        from app.pipeline.registry import get_steps  # noqa: PLC0415
        from app.services import consensus, credentials, system_settings  # noqa: PLC0415

        system_settings.set(db_session, "consensus_enabled", True)
        credentials.set_system_secret(db_session, "openai", "api_key", "sk-test")

        class _OpenAI:
            model = "gpt-4o"

            def complete(self, system, prompt, max_tokens=4096, temperature=None):
                usage_meter.note("openai", self.model, 700, 300)
                return "Lead with LinkedIn, then email."

        monkeypatch.setattr("app.integrations.openai_client.get_openai_client",
                            lambda db: _OpenAI())
        spec = next(s for s in get_steps(m.PipelineKind.STRATEGY) if s.step_no == 9)
        with usage_meter.owner_scope(db_session, verified_strategy, "pipeline") as active:
            consensus.run_step(db_session, verified_strategy, spec, system="s",
                               prompt="p", claude=fake_claude)
            providers = [note[0] for note in active.notes]
        assert "openai" in providers
