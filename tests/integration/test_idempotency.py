"""
1D — Load and idempotency tests.

Verifies that the system is safe to retry/replay without producing duplicates:
  - Pipeline resume (crash at step 37 → resume → no re-run of completed steps)
  - Lead dedupe (same Apollo response twice → no duplicate rows)
  - Exactly-once send on Celery retry
  - Duplicate Calendly webhook → processed once
  - Duplicate WhatsApp status webhook → processed once
  - Device token upsert (3 registrations → 1 row, last_seen_at updated)
  - Nightly aggregation idempotency (3 runs → scores unchanged after first)
  - A/B promotion double-run guard
"""
from __future__ import annotations

import asyncio
import uuid

import pytest
import pytest_asyncio
from httpx import AsyncClient

from tests.integration.conftest import (
    _auth_headers,
    create_past_clients,
    create_product,
    create_strategy,
    lead_outcome_events,
    research_steps,
    seed_outcomes,
    set_plan,
    strategy_outcomes,
)
from tests.integration.mocks import calendly_mock, gmail_mock, whatsapp_mock

pytestmark = pytest.mark.asyncio


class TestPipelineResume:
    async def test_pipeline_resume_does_not_rerun_completed_steps(
        self, api_client: AsyncClient, user_a_tokens, all_mocks, db_session
    ):
        """
        Simulating a crash at step 37 and then resuming must result in exactly 72 total
        research_steps rows — not 72 + 37 (the pre-crash steps replayed).
        """
        headers = _auth_headers(user_a_tokens)
        product = await create_product(api_client, headers)
        await create_past_clients(api_client, headers, product["id"])
        strategy = await create_strategy(api_client, headers, product["id"])
        strategy_id = strategy["id"]

        # Simulate partial completion at step 37 then resume
        resp = await api_client.post(
            f"/debug/simulate-pipeline-crash",
            headers=headers,
            json={"strategy_id": strategy_id, "crash_at_step": 37},
        )
        assert resp.status_code == 200

        # Resume the pipeline
        resp = await api_client.post(
            f"/strategies/{strategy_id}/resume",
            headers=headers,
        )
        assert resp.status_code in (200, 202)

        # Must have exactly 72 steps, no more
        steps = research_steps(db_session, strategy_id)
        step_numbers = sorted(st.step_no for st in steps)

        assert len(steps) == 72, (
            f"Pipeline resume produced {len(steps)} steps — "
            "steps 1–37 may have been re-run (idempotency failure)"
        )
        assert step_numbers == list(range(1, 73))


class TestLeadDedupe:
    async def test_same_apollo_response_twice_produces_no_duplicates(
        self, api_client: AsyncClient, user_a_tokens, all_mocks, db_session
    ):
        """
        Running lead sourcing twice with the same Apollo response must not
        produce duplicate rows in the leads table (dedupe on apollo_person_id + email).
        """
        headers = _auth_headers(user_a_tokens)
        product = await create_product(api_client, headers)
        await create_past_clients(api_client, headers, product["id"])
        strategy = await create_strategy(api_client, headers, product["id"])
        strategy_id = strategy["id"]

        # Source leads twice
        await api_client.post(f"/strategies/{strategy_id}/leads/source", headers=headers, json={})
        await api_client.post(f"/strategies/{strategy_id}/leads/source", headers=headers, json={})

        resp = await api_client.get(f"/strategies/{strategy_id}/leads", headers=headers)
        leads = resp.json()["items"]
        emails = [l["email"] for l in leads]

        # No duplicate emails
        assert len(emails) == len(set(emails)), (
            f"Duplicate leads found after double-sourcing: {emails}"
        )

        # Stable person IDs from Apollo mock — each person appears once
        apollo_ids = [l.get("apollo_person_id") for l in leads if l.get("apollo_person_id")]
        assert len(apollo_ids) == len(set(apollo_ids)), "Duplicate Apollo person IDs in leads table"


class TestExactlyOnceSend:
    async def test_celery_retry_sends_email_exactly_once(
        self, api_client: AsyncClient, user_a_tokens, all_mocks, db_session
    ):
        """
        If the Celery send task fails and retries, the email must be sent exactly once.
        The idempotency key in the message header prevents double-sending.
        """
        headers = _auth_headers(user_a_tokens)
        email = f"once_{uuid.uuid4().hex[:6]}@example.com"

        gmail_mock.reset_capture()

        # Schedule an idempotent send
        idempotency_key = f"send_{uuid.uuid4().hex}"
        await api_client.post("/debug/schedule-send", headers=headers, json={
            "to": email,
            "subject": "Exactly once test",
            "body": "Body with unsubscribe",
            "include_unsubscribe": True,
            "idempotency_key": idempotency_key,
        })

        # Trigger the send task twice (simulate retry)
        await api_client.post("/debug/flush-scheduled-sends", headers=headers)
        await api_client.post("/debug/flush-scheduled-sends", headers=headers)

        send_calls = gmail_mock.get_capture().send_calls
        # Filter to sends with this idempotency key
        relevant = [c for c in send_calls if c.get("idempotency_key") == idempotency_key
                    or email in str(c)]
        assert len(relevant) == 1, (
            f"Email was sent {len(relevant)} times — expected exactly 1 (idempotency failure)"
        )


class TestWebhookIdempotency:
    async def test_duplicate_calendly_webhook_processed_once(
        self, api_client: AsyncClient, user_a_tokens, all_mocks, db_session
    ):
        """
        Delivering the same Calendly booking webhook twice (same event_id)
        must result in exactly one 'booked' outcome event.
        """
        headers = _auth_headers(user_a_tokens)
        product = await create_product(api_client, headers)
        await create_past_clients(api_client, headers, product["id"])
        strategy = await create_strategy(api_client, headers, product["id"])
        await api_client.post(f"/strategies/{strategy['id']}/leads/source", headers=headers, json={})

        resp = await api_client.get(f"/strategies/{strategy['id']}/leads", headers=headers)
        leads = resp.json()["items"]
        lead_id = leads[0]["id"]

        # Use FIXED_EVENT_ID for idempotency test
        payload = calendly_mock.build_booking_webhook(
            event_id=calendly_mock.FIXED_EVENT_ID,
            invitee_email=leads[0]["email"],
            lead_id=lead_id,
            tenant_id=user_a_tokens["user"]["id"],
        )


        # Deliver twice
        for _ in range(2):
            resp = await api_client.post(
                "/webhooks/calendly", **calendly_mock.signed_request(payload)
            )
            assert resp.status_code == 200

        # Only one 'booked' outcome
        booked_events = [e for e in lead_outcome_events(db_session, lead_id)
                         if e == "booked"]
        assert len(booked_events) == 1, (
            f"Expected 1 booked outcome, got {len(booked_events)} — Calendly dedup failed"
        )

    async def test_duplicate_whatsapp_status_webhook_processed_once(
        self, api_client: AsyncClient, user_a_tokens, all_mocks, db_session
    ):
        """
        Delivering the same WhatsApp message-status webhook twice (same message_id)
        must result in exactly one status-update record.
        """
        fixed_msg_id = "wamid.idempotency_test_001"
        payload = whatsapp_mock.build_status_webhook(msg_id=fixed_msg_id, status="delivered")


        for _ in range(2):
            resp = await api_client.post(
                "/webhooks/whatsapp", **whatsapp_mock.signed_request(payload)
            )
            assert resp.status_code == 200

        # Verify only one delivery record for this message_id.
        # (The old `headers = _auth_headers({})` line here raised KeyError on
        # the empty dict before the assertion below could ever run, and its
        # result was never used - the request is deliberately unauthenticated.)
        resp = await api_client.get(
            f"/debug/whatsapp-status?message_id={fixed_msg_id}",
        )
        if resp.status_code == 200:
            records = resp.json()
            assert len(records) == 1, (
                f"Expected 1 status record for {fixed_msg_id}, got {len(records)}"
            )


class TestDeviceTokenUpsert:
    async def test_same_device_token_registered_three_times_results_in_one_row(
        self, api_client: AsyncClient, user_a_tokens, all_mocks, db_session
    ):
        """
        Registering the same FCM token 3 times must result in a single row
        with last_seen_at updated, not 3 rows.
        """
        headers = _auth_headers(user_a_tokens)
        token = f"fcm_upsert_test_{uuid.uuid4().hex}"

        for _ in range(3):
            resp = await api_client.post("/devices/register", headers=headers, json={
                "token": token,
                "platform": "android",
            })
            assert resp.status_code in (200, 201), resp.text

        # There is no GET /devices -- the router is register + delete only
        # (see app/api/devices.py). The upsert guarantee is a row count.
        from app.db.models import DeviceToken

        db_session.expire_all()
        count = (
            db_session.query(DeviceToken)
            .filter(DeviceToken.token == token)
            .count()
        )
        assert count == 1, f"Token registered 3 times but found {count} rows - upsert failed"


class TestAggregationIdempotency:
    async def test_nightly_aggregation_idempotent_after_three_runs(
        self, api_client: AsyncClient, admin_tokens, user_a_tokens, all_mocks, db_session
    ):
        """
        Running nightly aggregation 3 times on the same outcome data must produce
        the same scores each time (idempotent upsert).
        """
        headers = _auth_headers(user_a_tokens)
        product = await create_product(api_client, headers)
        await create_past_clients(api_client, headers, product["id"])
        strategy = await create_strategy(api_client, headers, product["id"])
        strategy_id = strategy["id"]
        await seed_outcomes(db_session, strategy_id, "control", 50, 10, 3)

        # Admins are made out of band (app/cli/create_admin.py);
        # signing up with "is_admin": True yields an ordinary user.
        admin_headers = _auth_headers(admin_tokens)
        # /playbook/* is plan-gated; a free user gets 402.
        set_plan(db_session, user_a_tokens, "pro")

        # Run aggregation 3 times
        scores_after_each = []
        for _ in range(3):
            await api_client.post("/playbook/aggregate", headers=admin_headers)
            resp = await api_client.get(
                f"/playbook/scores?strategy_id={strategy_id}",
                headers=headers,
            )
            scores_after_each.append(resp.json())

        # Scores after run 1, 2, 3 must be identical
        def extract_scores(scores: list) -> dict:
            return {s.get("variant", s.get("pattern_key", "")): s.get("reply_rate") for s in scores}

        assert extract_scores(scores_after_each[0]) == extract_scores(scores_after_each[1]) == extract_scores(scores_after_each[2]), (
            "Aggregation is not idempotent — scores changed between runs on the same data"
        )


class TestABPromotionIdempotency:
    async def test_double_promotion_produces_no_duplicate_events(
        self, api_client: AsyncClient, admin_tokens, user_a_tokens, all_mocks, db_session
    ):
        """
        Running auto_promote_winners twice on an already-promoted strategy must NOT
        produce a second promotion event.
        """
        headers = _auth_headers(user_a_tokens)
        product = await create_product(api_client, headers)
        await create_past_clients(api_client, headers, product["id"])
        strategy = await create_strategy(api_client, headers, product["id"])
        strategy_id = strategy["id"]

        # Promotion compares the BOOKING rate through a two-proportion
        # z-test at alpha=0.05, so the seeded gap has to be genuinely
        # significant: 2/50 vs 6/50 gives p=0.14 and is correctly
        # refused. 4/200 vs 30/200 gives p<0.0001.
        await seed_outcomes(db_session, strategy_id, "variant_a", 200, 20, 4)
        await seed_outcomes(db_session, strategy_id, "variant_b", 200, 90, 30)

        # Admins are made out of band (app/cli/create_admin.py);
        # signing up with "is_admin": True yields an ordinary user.
        admin_headers = _auth_headers(admin_tokens)
        # /playbook/* is plan-gated; a free user gets 402.
        set_plan(db_session, user_a_tokens, "pro")

        # Run aggregation + promotion twice
        for _ in range(2):
            await api_client.post("/playbook/aggregate", headers=admin_headers)
            await api_client.post("/playbook/promote-winners", headers=admin_headers)

        # Only one promotion event must exist
        promoted_events = strategy_outcomes(db_session, strategy_id, "ab_promoted")
        assert len(promoted_events) == 1, (
            f"Expected 1 promotion event, got {len(promoted_events)} — double-promotion not guarded"
        )
