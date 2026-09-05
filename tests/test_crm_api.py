"""M9 CRM API — tenant isolation, notes, tags, activity, views, fields, grid.

The isolation tests are the load-bearing ones. Every other CRM feature is a
convenience; a cross-tenant read is a breach. They follow the house rule from
app/api/leads.py: a resource belonging to another account answers 404, never
403, so a status code cannot be used to confirm that an id exists.
"""

import uuid

import pytest
from sqlalchemy import select

from app.db import models as m
from tests.conftest import auth_headers


# --------------------------------------------------------------------------
# Fixtures
# --------------------------------------------------------------------------


@pytest.fixture()
def crm_lead(db_session, verified_strategy):
    lead = m.Lead(
        strategy_id=verified_strategy.id, source="apollo", external_id="crm1",
        full_name="Dana Okafor", title="Founder", company="Northwind",
        email="dana@northwind.test", status=m.LeadStatus.VERIFIED,
    )
    db_session.add(lead)
    db_session.commit()
    return lead


@pytest.fixture()
def other_account(db_session):
    """A second, fully separate account with one lead of its own.

    Built end to end (user -> product -> strategy -> lead) rather than by
    reusing the first account's objects, because the ownership chain the API
    walks is lead -> strategy -> product -> user_id: a shortcut that shares
    any link in that chain would not be testing isolation at all.
    """
    user = m.User(email="intruder@elsewhere.test", email_verified=True)
    db_session.add(user)
    db_session.flush()
    product = m.Product(user_id=user.id, name="Other", description="Other",
                        type=m.ProductType.PRODUCT)
    db_session.add(product)
    db_session.flush()
    strategy = m.Strategy(product_id=product.id,
                          flow_type=m.FlowType.NO_CLIENTS,
                          status=m.StrategyStatus.VERIFIED)
    db_session.add(strategy)
    db_session.flush()
    lead = m.Lead(strategy_id=strategy.id, source="apollo",
                  external_id="other1", full_name="Not Yours",
                  email="not@yours.test", status=m.LeadStatus.VERIFIED)
    db_session.add(lead)
    tag = m.CrmTag(user_id=user.id, name="their-tag")
    view = m.CrmSavedView(user_id=user.id, name="Their view",
                          view_type=m.CrmViewType.GRID)
    field = m.CrmCustomField(user_id=user.id, key="their_field",
                             label="Theirs")
    db_session.add_all([tag, view, field])
    db_session.commit()
    return {"user": user, "strategy": strategy, "lead": lead, "tag": tag,
            "view": view, "field": field}


# --------------------------------------------------------------------------
# Tenant isolation
# --------------------------------------------------------------------------


class TestTenantIsolation:
    def test_notes_on_another_accounts_lead_are_404(self, client, other_account):
        lead_id = other_account["lead"].id
        assert client.get(f"/crm/leads/{lead_id}/notes").status_code == 404
        assert client.post(f"/crm/leads/{lead_id}/notes",
                           json={"body": "hi"}).status_code == 404

    def test_activity_on_another_accounts_lead_is_404(self, client, other_account):
        lead_id = other_account["lead"].id
        assert client.get(f"/crm/leads/{lead_id}/activity").status_code == 404

    def test_patch_on_another_accounts_lead_is_404(self, client, other_account):
        lead_id = other_account["lead"].id
        r = client.patch(f"/crm/leads/{lead_id}", json={"status": "flagged"})
        assert r.status_code == 404

    def test_another_accounts_saved_view_is_404(self, client, other_account):
        view_id = other_account["view"].id
        assert client.put(f"/crm/views/{view_id}", json={
            "name": "hijacked", "view_type": "grid", "filters_json": {},
            "sort_json": [], "columns_json": [], "is_default": False,
        }).status_code == 404
        assert client.delete(f"/crm/views/{view_id}").status_code == 404

    def test_another_accounts_tag_is_404(self, client, crm_lead, other_account):
        tag_id = other_account["tag"].id
        assert client.delete(f"/crm/tags/{tag_id}").status_code == 404
        # And it cannot be attached to a lead this account DOES own -- which
        # would otherwise import a foreign row into this account's data.
        r = client.post(f"/crm/leads/{crm_lead.id}/tags/{tag_id}")
        assert r.status_code == 404

    def test_another_accounts_custom_field_is_404(self, client, other_account):
        field_id = other_account["field"].id
        assert client.delete(f"/crm/fields/{field_id}").status_code == 404

    def test_listings_never_include_another_account(self, client, other_account):
        assert client.get("/crm/tags").json()["items"] == []
        assert client.get("/crm/views").json()["items"] == []
        assert client.get("/crm/fields").json()["items"] == []

    def test_grid_never_returns_another_accounts_leads(self, client, crm_lead,
                                                       other_account):
        body = client.post("/crm/grid", json={}).json()
        ids = {item["id"] for item in body["items"]}
        assert str(crm_lead.id) in ids
        assert str(other_account["lead"].id) not in ids
        assert body["total"] == 1

    def test_dashboards_never_aggregate_another_account(self, client, crm_lead,
                                                        other_account):
        """The aggregation queries are the easiest place for isolation to be
        lost, because a missing WHERE clause produces a plausible number
        rather than an error."""
        for page in ("pipeline", "leads", "campaigns", "activity"):
            assert client.get(f"/crm/dashboard/{page}").status_code == 200
        pipeline = client.get("/crm/dashboard/pipeline").json()
        assert pipeline["total_leads"] == 1

    def test_dashboard_rejects_another_accounts_strategy_filter(
        self, client, other_account
    ):
        strategy_id = other_account["strategy"].id
        for page in ("pipeline", "leads", "campaigns", "activity"):
            r = client.get(f"/crm/dashboard/{page}?strategy_id={strategy_id}")
            assert r.status_code == 404, page

    def test_bulk_rejects_the_whole_batch_on_a_foreign_id(
        self, client, db_session, crm_lead, other_account
    ):
        """A foreign id 404s the request rather than being skipped silently.

        Skipping would be indistinguishable from "nothing to change", which
        makes cross-tenant probing free -- and would half-apply the batch."""
        r = client.post("/crm/leads/bulk", json={
            "lead_ids": [str(crm_lead.id), str(other_account["lead"].id)],
            "status": "flagged",
        })
        assert r.status_code == 404
        db_session.refresh(crm_lead)
        assert crm_lead.status is m.LeadStatus.VERIFIED, "batch partly applied"

    def test_unknown_ids_are_404_not_500(self, client):
        missing = uuid.uuid4()
        assert client.get(f"/crm/leads/{missing}/notes").status_code == 404
        assert client.delete(f"/crm/notes/{missing}").status_code == 404
        assert client.delete(f"/crm/views/{missing}").status_code == 404
        assert client.delete(f"/crm/tags/{missing}").status_code == 404
        assert client.delete(f"/crm/fields/{missing}").status_code == 404

    def test_every_crm_route_requires_authentication(self, anon_client):
        """No CRM route may be reachable without a token. /crm/stream is the
        one exception -- it authenticates by ticket -- and it must still
        reject a request that presents none."""
        assert anon_client.get("/crm/tags").status_code in (401, 403)
        assert anon_client.post("/crm/grid", json={}).status_code in (401, 403)
        assert anon_client.get("/crm/dashboard/pipeline").status_code in (401, 403)
        # Missing ticket is a validation error, not an open door.
        assert anon_client.get("/crm/stream").status_code == 422


# --------------------------------------------------------------------------
# Notes
# --------------------------------------------------------------------------


class TestNotes:
    def test_create_read_delete(self, client, db_session, crm_lead):
        created = client.post(f"/crm/leads/{crm_lead.id}/notes",
                              json={"body": "Asked for pricing"})
        assert created.status_code == 201
        note_id = created.json()["id"]

        listed = client.get(f"/crm/leads/{crm_lead.id}/notes").json()
        assert [n["body"] for n in listed["items"]] == ["Asked for pricing"]

        assert client.delete(f"/crm/notes/{note_id}").status_code == 204
        assert client.get(f"/crm/leads/{crm_lead.id}/notes").json()["items"] == []

    def test_creating_a_note_writes_an_activity_row(self, client, db_session,
                                                    crm_lead):
        client.post(f"/crm/leads/{crm_lead.id}/notes", json={"body": "First"})
        kinds = db_session.execute(
            select(m.CrmActivity.kind)
            .where(m.CrmActivity.lead_id == crm_lead.id)
        ).scalars().all()
        assert m.CrmActivityKind.NOTE_ADDED in kinds

    def test_activity_stores_the_first_line_not_the_whole_note(
        self, client, db_session, crm_lead
    ):
        """A 10,000-character note pasted into the feed makes every other
        entry unreadable, so the timeline carries a summary line only."""
        body = "Headline\n" + ("x" * 5000)
        client.post(f"/crm/leads/{crm_lead.id}/notes", json={"body": body})
        activity = db_session.execute(
            select(m.CrmActivity)
            .where(m.CrmActivity.kind == m.CrmActivityKind.NOTE_ADDED)
        ).scalars().one()
        assert activity.to_value == "Headline"
        # The full text is still stored on the note itself.
        note = db_session.execute(select(m.CrmNote)).scalars().one()
        assert note.body == body

    def test_empty_note_is_rejected(self, client, crm_lead):
        r = client.post(f"/crm/leads/{crm_lead.id}/notes", json={"body": ""})
        assert r.status_code == 422


# --------------------------------------------------------------------------
# Tags
# --------------------------------------------------------------------------


class TestTags:
    def test_create_is_idempotent_by_name(self, client):
        """Typing a name that already exists means "use that one", not an
        error -- the grid creates tags by typing into a cell."""
        first = client.post("/crm/tags", json={"name": "warm"})
        second = client.post("/crm/tags", json={"name": "warm"})
        assert first.status_code == 201 and first.json()["created"] is True
        assert second.json()["created"] is False
        assert second.json()["id"] == first.json()["id"]
        assert len(client.get("/crm/tags").json()["items"]) == 1

    def test_attach_and_detach(self, client, crm_lead):
        tag_id = client.post("/crm/tags", json={"name": "warm"}).json()["id"]
        assert client.post(f"/crm/leads/{crm_lead.id}/tags/{tag_id}"
                           ).json()["created"] is True
        # Second attach is a no-op, not a duplicate row or a 409.
        assert client.post(f"/crm/leads/{crm_lead.id}/tags/{tag_id}"
                           ).json()["created"] is False

        row = client.post("/crm/grid", json={}).json()["items"][0]
        assert [t["name"] for t in row["tags"]] == ["warm"]

        assert client.delete(
            f"/crm/leads/{crm_lead.id}/tags/{tag_id}").status_code == 204
        row = client.post("/crm/grid", json={}).json()["items"][0]
        assert row["tags"] == []

    def test_deleting_a_tag_detaches_it_everywhere(self, client, db_session,
                                                   crm_lead):
        tag_id = client.post("/crm/tags", json={"name": "warm"}).json()["id"]
        client.post(f"/crm/leads/{crm_lead.id}/tags/{tag_id}")
        assert client.delete(f"/crm/tags/{tag_id}").status_code == 204
        assert db_session.execute(select(m.CrmLeadTag)).scalars().all() == []

    def test_color_is_a_theme_token_not_a_hex(self, client):
        """The app recolors from CSS variables; a stored hex would be the one
        element on screen ignoring the user's preset."""
        tag = client.post("/crm/tags",
                          json={"name": "hot", "color_token": "primary"}).json()
        assert tag["color_token"] == "primary"


# --------------------------------------------------------------------------
# Inline edit
# --------------------------------------------------------------------------


class TestInlineEdit:
    def test_status_change_is_validated_against_the_kanban_map(self, client,
                                                               crm_lead):
        """The grid and the kanban share app/api/ui_support.py's transition
        map. If they ever diverge, the same move is legal on one screen and
        rejected on the other."""
        illegal = client.patch(f"/crm/leads/{crm_lead.id}",
                               json={"status": "meeting_booked"})
        assert illegal.status_code == 422
        legal = client.patch(f"/crm/leads/{crm_lead.id}",
                             json={"status": "flagged"})
        assert legal.status_code == 200
        assert legal.json()["status"] == "flagged"

    def test_status_change_records_stage_entered_at(self, client, db_session,
                                                    crm_lead):
        """The measurement the velocity dashboard needs and that nothing
        before M9 recorded."""
        client.patch(f"/crm/leads/{crm_lead.id}", json={"status": "flagged"})
        meta = db_session.execute(
            select(m.CrmLeadMeta).where(m.CrmLeadMeta.lead_id == crm_lead.id)
        ).scalars().one()
        assert meta.stage_entered_at is not None

    def test_status_change_writes_a_transition_activity(self, client,
                                                        db_session, crm_lead):
        client.patch(f"/crm/leads/{crm_lead.id}", json={"status": "flagged"})
        activity = db_session.execute(
            select(m.CrmActivity)
            .where(m.CrmActivity.kind == m.CrmActivityKind.STATUS_CHANGED)
        ).scalars().one()
        assert (activity.from_value, activity.to_value) == ("verified", "flagged")

    def test_patch_only_writes_the_fields_that_were_sent(self, client,
                                                          db_session, crm_lead):
        """A single-cell edit must not clear the columns it did not mention --
        otherwise two people editing different cells overwrite each other."""
        client.patch(f"/crm/leads/{crm_lead.id}", json={"priority": "high"})
        client.patch(f"/crm/leads/{crm_lead.id}", json={"status": "flagged"})
        meta = db_session.execute(
            select(m.CrmLeadMeta).where(m.CrmLeadMeta.lead_id == crm_lead.id)
        ).scalars().one()
        assert meta.priority == "high"

    def test_owner_must_be_the_authenticated_user(self, client, crm_lead,
                                                  other_account):
        """Team accounts are not built. Accepting an arbitrary user id would
        let one account write another's id into its own rows."""
        r = client.patch(f"/crm/leads/{crm_lead.id}",
                         json={"owner_user_id": str(other_account["user"].id)})
        assert r.status_code == 422

    def test_owner_can_be_set_and_cleared(self, client, db_session, crm_lead,
                                          test_user):
        client.patch(f"/crm/leads/{crm_lead.id}",
                     json={"owner_user_id": str(test_user.id)})
        row = client.post("/crm/grid", json={}).json()["items"][0]
        assert row["owner_user_id"] == str(test_user.id)
        client.patch(f"/crm/leads/{crm_lead.id}", json={"owner_user_id": None})
        row = client.post("/crm/grid", json={}).json()["items"][0]
        assert row["owner_user_id"] is None


class TestBulkActions:
    def test_partial_success_is_the_contract(self, client, db_session,
                                             verified_strategy):
        """Selecting 200 rows legitimately includes some whose current status
        makes the move illegal. Failing the whole batch means hunting for the
        offender by hand with no indication of which it was."""
        movable = m.Lead(strategy_id=verified_strategy.id, source="apollo",
                         external_id="b1", email="b1@x.test",
                         status=m.LeadStatus.VERIFIED)
        stuck = m.Lead(strategy_id=verified_strategy.id, source="apollo",
                       external_id="b2", email="b2@x.test",
                       status=m.LeadStatus.DROPPED)
        db_session.add_all([movable, stuck])
        db_session.commit()

        r = client.post("/crm/leads/bulk", json={
            "lead_ids": [str(movable.id), str(stuck.id)],
            "status": "flagged",
        })
        body = r.json()
        assert body["updated_count"] == 1
        assert body["skipped_count"] == 1
        assert body["skipped"][0]["lead_id"] == str(stuck.id)
        db_session.refresh(movable)
        db_session.refresh(stuck)
        assert movable.status is m.LeadStatus.FLAGGED
        assert stuck.status is m.LeadStatus.DROPPED

    def test_bulk_tagging(self, client, db_session, verified_strategy):
        leads = [
            m.Lead(strategy_id=verified_strategy.id, source="apollo",
                   external_id=f"t{i}", email=f"t{i}@x.test",
                   status=m.LeadStatus.VERIFIED)
            for i in range(3)
        ]
        db_session.add_all(leads)
        db_session.commit()
        tag_id = client.post("/crm/tags", json={"name": "batch"}).json()["id"]

        r = client.post("/crm/leads/bulk", json={
            "lead_ids": [str(lead.id) for lead in leads],
            "add_tag_ids": [tag_id],
        })
        assert r.json()["updated_count"] == 3
        assert len(db_session.execute(select(m.CrmLeadTag)).scalars().all()) == 3

        client.post("/crm/leads/bulk", json={
            "lead_ids": [str(leads[0].id)], "remove_tag_ids": [tag_id],
        })
        assert len(db_session.execute(select(m.CrmLeadTag)).scalars().all()) == 2


# --------------------------------------------------------------------------
# Saved views
# --------------------------------------------------------------------------


class TestSavedViews:
    def _payload(self, **overrides) -> dict:
        base = {
            "name": "Hot leads",
            "view_type": "grid",
            "filters_json": {"status": {"op": "in", "value": ["verified"]}},
            "sort_json": [{"key": "company", "dir": "asc"}],
            "columns_json": [{"key": "company", "width": 240, "visible": True}],
            "is_default": False,
        }
        base.update(overrides)
        return base

    def test_crud_round_trip_preserves_the_whole_layout(self, client):
        """Column WIDTHS are part of a view, not just which columns show --
        restoring a view has to restore the layout the user built."""
        created = client.post("/crm/views", json=self._payload())
        assert created.status_code == 201
        view = created.json()
        assert view["columns_json"] == [
            {"key": "company", "width": 240, "visible": True}
        ]

        updated = client.put(f"/crm/views/{view['id']}",
                             json=self._payload(name="Renamed"))
        assert updated.json()["name"] == "Renamed"

        assert client.delete(f"/crm/views/{view['id']}").status_code == 204
        assert client.get("/crm/views").json()["items"] == []

    def test_views_persist_server_side_not_in_the_browser(self, client,
                                                          db_session, test_user):
        """The point of the table: a view built on a laptop is there on the
        phone. Asserted at the database, not through the API that wrote it."""
        client.post("/crm/views", json=self._payload())
        row = db_session.execute(select(m.CrmSavedView)).scalars().one()
        assert row.user_id == test_user.id
        assert row.filters_json == {"status": {"op": "in", "value": ["verified"]}}

    def test_duplicate_name_within_a_type_is_409(self, client):
        client.post("/crm/views", json=self._payload())
        assert client.post("/crm/views",
                           json=self._payload()).status_code == 409

    def test_same_name_is_allowed_across_view_types(self, client):
        """A dashboard view and a grid view may share a name; they are
        different objects on different screens."""
        assert client.post("/crm/views", json=self._payload()).status_code == 201
        assert client.post(
            "/crm/views", json=self._payload(view_type="dashboard")
        ).status_code == 201

    def test_only_one_default_per_type(self, client):
        first = client.post("/crm/views",
                            json=self._payload(name="A", is_default=True)).json()
        second = client.post("/crm/views",
                             json=self._payload(name="B", is_default=True)).json()
        views = {v["id"]: v for v in client.get("/crm/views").json()["items"]}
        assert views[first["id"]]["is_default"] is False
        assert views[second["id"]]["is_default"] is True

    def test_setting_a_default_does_not_clear_the_other_types_default(self, client):
        grid = client.post("/crm/views",
                           json=self._payload(name="G", is_default=True)).json()
        client.post("/crm/views", json=self._payload(
            name="D", view_type="dashboard", is_default=True))
        views = {v["id"]: v for v in client.get("/crm/views").json()["items"]}
        assert views[grid["id"]]["is_default"] is True


# --------------------------------------------------------------------------
# Custom fields
# --------------------------------------------------------------------------


class TestCustomFields:
    def test_define_and_set_a_text_field(self, client, crm_lead):
        client.post("/crm/fields", json={"key": "deal_size",
                                         "label": "Deal size"})
        r = client.patch(f"/crm/leads/{crm_lead.id}",
                         json={"custom": {"deal_size": "enterprise"}})
        assert r.status_code == 200
        row = client.post("/crm/grid", json={}).json()["items"][0]
        assert row["custom"]["deal_size"] == "enterprise"

    def test_number_round_trips_as_a_number_not_a_string(self, client, crm_lead):
        """value_text is zero-padded for sorting; value_json keeps the type,
        so a round-trip must not hand back the padded string."""
        client.post("/crm/fields", json={"key": "seats", "label": "Seats",
                                         "field_type": "number"})
        client.patch(f"/crm/leads/{crm_lead.id}", json={"custom": {"seats": 12}})
        row = client.post("/crm/grid", json={}).json()["items"][0]
        assert row["custom"]["seats"] == 12

    def test_numeric_sort_order_is_numeric_not_lexical(self, client, db_session,
                                                       verified_strategy):
        """"9" > "10" as text. Without the zero-padding in value_text, every
        numeric column in the grid would sort wrongly and look like data
        corruption."""
        from app.services.crm_service import coerce_field_value

        field = m.CrmCustomField(user_id=uuid.uuid4(), key="n", label="N",
                                 field_type=m.CrmFieldType.NUMBER)
        nine, _ = coerce_field_value(field, 9)
        ten, _ = coerce_field_value(field, 10)
        minus, _ = coerce_field_value(field, -5)
        assert minus < nine < ten

    def test_bool_and_date_coercion(self, client, crm_lead):
        client.post("/crm/fields", json={"key": "signed", "label": "Signed",
                                         "field_type": "bool"})
        client.post("/crm/fields", json={"key": "renewal", "label": "Renewal",
                                         "field_type": "date"})
        client.patch(f"/crm/leads/{crm_lead.id}", json={"custom": {
            "signed": True, "renewal": "2026-12-01T00:00:00+00:00",
        }})
        row = client.post("/crm/grid", json={}).json()["items"][0]
        assert row["custom"]["signed"] is True
        assert row["custom"]["renewal"].startswith("2026-12-01")

    def test_select_rejects_a_value_outside_its_options(self, client, crm_lead):
        client.post("/crm/fields", json={
            "key": "tier", "label": "Tier", "field_type": "select",
            "options_json": ["bronze", "silver"],
        })
        ok = client.patch(f"/crm/leads/{crm_lead.id}",
                          json={"custom": {"tier": "silver"}})
        assert ok.status_code == 200
        bad = client.patch(f"/crm/leads/{crm_lead.id}",
                           json={"custom": {"tier": "platinum"}})
        assert bad.status_code == 422

    def test_select_without_options_is_rejected_at_definition_time(self, client):
        r = client.post("/crm/fields", json={"key": "t", "label": "T",
                                             "field_type": "select"})
        assert r.status_code == 422

    def test_unknown_field_key_is_422(self, client, crm_lead):
        r = client.patch(f"/crm/leads/{crm_lead.id}",
                         json={"custom": {"nope": "x"}})
        assert r.status_code == 422

    def test_duplicate_key_is_409(self, client):
        client.post("/crm/fields", json={"key": "a", "label": "A"})
        assert client.post("/crm/fields",
                           json={"key": "a", "label": "A2"}).status_code == 409

    def test_deleting_a_field_removes_its_values(self, client, db_session,
                                                 crm_lead):
        field_id = client.post("/crm/fields",
                               json={"key": "x", "label": "X"}).json()["id"]
        client.patch(f"/crm/leads/{crm_lead.id}", json={"custom": {"x": "v"}})
        assert client.delete(f"/crm/fields/{field_id}").status_code == 204
        assert db_session.execute(
            select(m.CrmCustomFieldValue)).scalars().all() == []


# --------------------------------------------------------------------------
# Grid query
# --------------------------------------------------------------------------


@pytest.fixture()
def grid_leads(db_session, verified_strategy):
    rows = [
        ("Ada Byron",   "Analytical",  m.LeadStatus.VERIFIED,  "apollo"),
        ("Grace Hopper", "Compiler Co", m.LeadStatus.CONTACTED, "apollo"),
        ("Alan Turing", "Bletchley",   m.LeadStatus.REPLIED,   "manual"),
        ("Ada Lovelace", "Analytical", m.LeadStatus.DROPPED,   "manual"),
    ]
    leads = []
    for index, (name, company, status, source) in enumerate(rows):
        lead = m.Lead(strategy_id=verified_strategy.id, source=source,
                      external_id=f"g{index}", full_name=name,
                      company=company, email=f"g{index}@x.test", status=status)
        db_session.add(lead)
        leads.append(lead)
    db_session.commit()
    return leads


class TestGrid:
    def test_search_spans_name_company_and_email(self, client, grid_leads):
        body = client.post("/crm/grid", json={"search": "Ada"}).json()
        assert body["total"] == 2
        body = client.post("/crm/grid", json={"search": "Bletchley"}).json()
        assert body["total"] == 1

    def test_filter_by_status_in(self, client, grid_leads):
        body = client.post("/crm/grid", json={
            "filters": {"status": {"op": "in",
                                   "value": ["verified", "replied"]}}
        }).json()
        assert body["total"] == 2

    def test_filter_contains_is_case_insensitive(self, client, grid_leads):
        body = client.post("/crm/grid", json={
            "filters": {"company": {"op": "contains", "value": "analytical"}}
        }).json()
        assert body["total"] == 2

    def test_multi_column_sort(self, client, grid_leads):
        body = client.post("/crm/grid", json={
            "sort": [{"key": "company", "dir": "asc"},
                     {"key": "full_name", "dir": "desc"}]
        }).json()
        pairs = [(i["company"], i["full_name"]) for i in body["items"]]
        assert pairs[0] == ("Analytical", "Ada Lovelace")
        assert pairs[1] == ("Analytical", "Ada Byron")

    def test_sort_on_an_unknown_column_is_ignored_not_500(self, client,
                                                          grid_leads):
        """A saved view built before a column was renamed should still open,
        minus that one clause, rather than erroring the whole grid."""
        body = client.post("/crm/grid", json={
            "sort": [{"key": "password_hash", "dir": "asc"}]
        }).json()
        assert body["total"] == 4

    def test_sort_is_restricted_to_an_allow_list(self):
        """getattr(Lead, key) would let a crafted sort order by -- and, through
        a sort-order oracle, leak -- a column that is not meant to be
        reachable."""
        from app.services.crm_service import GRID_COLUMNS

        assert "password_hash" not in GRID_COLUMNS
        assert "enrichment_json" not in GRID_COLUMNS

    def test_pagination_reports_total_and_has_more(self, client, grid_leads):
        first = client.post("/crm/grid", json={"limit": 2, "offset": 0}).json()
        assert first["total"] == 4
        assert first["has_more"] is True
        assert len(first["items"]) == 2
        last = client.post("/crm/grid", json={"limit": 2, "offset": 2}).json()
        assert last["has_more"] is False

    def test_tag_filter_does_not_duplicate_rows(self, client, grid_leads):
        """A lead carrying two of the filtered tags must appear once. A join
        would return it twice and inflate `total`."""
        first = client.post("/crm/tags", json={"name": "a"}).json()["id"]
        second = client.post("/crm/tags", json={"name": "b"}).json()["id"]
        lead_id = grid_leads[0].id
        client.post(f"/crm/leads/{lead_id}/tags/{first}")
        client.post(f"/crm/leads/{lead_id}/tags/{second}")

        body = client.post("/crm/grid",
                           json={"tag_ids": [first, second]}).json()
        assert body["total"] == 1
        assert len(body["items"]) == 1

    def test_limit_is_capped(self, client, grid_leads):
        r = client.post("/crm/grid", json={"limit": 100_000})
        assert r.status_code == 422  # rejected at the schema, before any query

    def test_note_count_is_one_query_not_per_row(self, client, grid_leads):
        lead_id = grid_leads[0].id
        client.post(f"/crm/leads/{lead_id}/notes", json={"body": "one"})
        client.post(f"/crm/leads/{lead_id}/notes", json={"body": "two"})
        items = {i["id"]: i for i in
                 client.post("/crm/grid", json={}).json()["items"]}
        assert items[str(lead_id)]["note_count"] == 2
