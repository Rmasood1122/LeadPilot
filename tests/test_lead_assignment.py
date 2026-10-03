"""Lead assignment inside a workspace (team accounts, Feature 1).

What must hold:
  * an assignee must be a member of the workspace that owns the lead;
  * managers assign freely; an SDR may only claim an unassigned lead or
    release their own; a viewer cannot write at all;
  * the activity row records the person who ACTED, not the workspace owner the
    request runs as;
  * round-robin is least-loaded, managers only, and idempotent -- a second run
    moves nothing;
  * a lead from another account anywhere in a batch 404s the whole request
    and assigns nothing (the cross-tenant rule from FEATURES.md 4.4).
"""

from __future__ import annotations

import uuid

import pytest
from sqlalchemy import select

from app.db import models as m
from app.services import workspaces

from .conftest import auth_headers


def _user(db, email):
    user = m.User(email=email, email_verified=True)
    db.add(user)
    db.commit()
    return user


def _as(user, ws=None):
    headers = auth_headers(user)
    if ws is not None:
        headers["X-Workspace-Id"] = str(ws.id)
    return headers


@pytest.fixture()
def team(db_session, test_user):
    ws = workspaces.personal_workspace(db_session, test_user)
    people = {}
    for key, role in (("manager", "manager"), ("sdr", "sdr"), ("sdr2", "sdr"),
                      ("viewer", "viewer")):
        user = _user(db_session, f"{key}@assign.dev")
        db_session.add(m.WorkspaceMember(workspace_id=ws.id, user_id=user.id, role=role))
        people[key] = user
    db_session.commit()
    return ws, people


def _leads(db, strategy, n, status=m.LeadStatus.VERIFIED, prefix="a"):
    rows = []
    for i in range(n):
        lead = m.Lead(strategy_id=strategy.id, source="apollo",
                      external_id=f"{prefix}{i}", full_name=f"Lead {prefix}{i}",
                      email=f"{prefix}{i}@assign.test", status=status)
        db.add(lead)
        rows.append(lead)
    db.commit()
    return rows


@pytest.fixture()
def leads(db_session, verified_strategy):
    return _leads(db_session, verified_strategy, 4)


def _owner_of(db, lead):
    db.expire_all()
    return db.execute(select(m.CrmLeadMeta.owner_user_id)
                      .where(m.CrmLeadMeta.lead_id == lead.id)).scalar_one_or_none()


@pytest.fixture()
def foreign_lead(db_session):
    user = _user(db_session, "elsewhere@other.test")
    product = m.Product(user_id=user.id, name="Other", description="Other",
                        type=m.ProductType.PRODUCT)
    db_session.add(product)
    db_session.flush()
    strategy = m.Strategy(product_id=product.id, flow_type=m.FlowType.NO_CLIENTS,
                          status=m.StrategyStatus.VERIFIED)
    db_session.add(strategy)
    db_session.flush()
    return _leads(db_session, strategy, 1, prefix="foreign")[0]


# --------------------------------------------------------------------------
# Single-lead PATCH
# --------------------------------------------------------------------------


def test_manager_assigns_to_a_member_and_the_actor_is_recorded(client, db_session, team, leads):
    ws, people = team
    r = client.patch(f"/crm/leads/{leads[0].id}",
                     json={"owner_user_id": str(people["sdr"].id)},
                     headers=_as(people["manager"], ws))
    assert r.status_code == 200, r.text
    assert _owner_of(db_session, leads[0]) == people["sdr"].id

    activity = db_session.execute(
        select(m.CrmActivity).where(m.CrmActivity.lead_id == leads[0].id,
                                    m.CrmActivity.kind == m.CrmActivityKind.OWNER_CHANGED)
    ).scalar_one()
    # The manager clicked. Not the workspace owner the request ran as.
    assert activity.actor_user_id == people["manager"].id


def test_owner_can_assign_to_their_members_without_the_header(client, db_session, team, leads):
    _, people = team
    r = client.patch(f"/crm/leads/{leads[0].id}",
                     json={"owner_user_id": str(people["sdr2"].id)})
    assert r.status_code == 200, r.text
    assert _owner_of(db_session, leads[0]) == people["sdr2"].id


def test_non_member_cannot_be_assigned(client, db_session, team, leads):
    ws, people = team
    outsider = _user(db_session, "outsider@assign.dev")
    r = client.patch(f"/crm/leads/{leads[0].id}",
                     json={"owner_user_id": str(outsider.id)},
                     headers=_as(people["manager"], ws))
    assert r.status_code == 422
    # A made-up id gets the same answer, so existence cannot be probed.
    r = client.patch(f"/crm/leads/{leads[0].id}",
                     json={"owner_user_id": str(uuid.uuid4())},
                     headers=_as(people["manager"], ws))
    assert r.status_code == 422
    assert _owner_of(db_session, leads[0]) is None


def test_sdr_claims_and_releases_but_cannot_reassign(client, db_session, team, leads):
    ws, people = team
    sdr, sdr2 = people["sdr"], people["sdr2"]
    path = f"/crm/leads/{leads[0].id}"

    assert client.patch(path, json={"owner_user_id": str(sdr.id)},
                        headers=_as(sdr, ws)).status_code == 200
    # Taking a colleague's lead, or handing one to a colleague, is a manager call.
    assert client.patch(path, json={"owner_user_id": str(sdr2.id)},
                        headers=_as(sdr2, ws)).status_code == 403
    assert client.patch(path, json={"owner_user_id": str(sdr2.id)},
                        headers=_as(sdr, ws)).status_code == 403
    assert client.patch(path, json={"owner_user_id": None},
                        headers=_as(sdr2, ws)).status_code == 403
    assert _owner_of(db_session, leads[0]) == sdr.id

    assert client.patch(path, json={"owner_user_id": None},
                        headers=_as(sdr, ws)).status_code == 200
    assert _owner_of(db_session, leads[0]) is None


def test_viewer_cannot_assign(client, db_session, team, leads):
    ws, people = team
    r = client.patch(f"/crm/leads/{leads[0].id}",
                     json={"owner_user_id": str(people["viewer"].id)},
                     headers=_as(people["viewer"], ws))
    assert r.status_code == 403
    assert _owner_of(db_session, leads[0]) is None


def test_foreign_lead_is_404_even_with_a_valid_assignee(client, team, foreign_lead):
    ws, people = team
    r = client.patch(f"/crm/leads/{foreign_lead.id}",
                     json={"owner_user_id": str(people["sdr"].id)},
                     headers=_as(people["manager"], ws))
    assert r.status_code == 404


# --------------------------------------------------------------------------
# Bulk
# --------------------------------------------------------------------------


def test_bulk_assignment_by_a_manager(client, db_session, team, leads):
    ws, people = team
    r = client.post("/crm/leads/bulk",
                    json={"lead_ids": [str(l.id) for l in leads[:2]],
                          "owner_user_id": str(people["sdr"].id)},
                    headers=_as(people["manager"], ws))
    assert r.status_code == 200, r.text
    assert r.json()["updated_count"] == 2
    assert {_owner_of(db_session, l) for l in leads[:2]} == {people["sdr"].id}


def test_bulk_reassignment_by_an_sdr_is_skipped_per_row(client, db_session, team, leads):
    ws, people = team
    client.patch(f"/crm/leads/{leads[0].id}", json={"owner_user_id": str(people["sdr2"].id)})
    r = client.post("/crm/leads/bulk",
                    json={"lead_ids": [str(leads[0].id), str(leads[1].id)],
                          "owner_user_id": str(people["sdr"].id)},
                    headers=_as(people["sdr"], ws))
    body = r.json()
    assert r.status_code == 200, r.text
    # leads[1] was unassigned: a legal claim. leads[0] belongs to sdr2.
    assert body["updated"] == [str(leads[1].id)]
    assert [s["lead_id"] for s in body["skipped"]] == [str(leads[0].id)]
    assert _owner_of(db_session, leads[0]) == people["sdr2"].id


def test_bulk_with_non_member_fails_the_whole_request(client, db_session, team, leads):
    ws, people = team
    outsider = _user(db_session, "bulk-outsider@assign.dev")
    r = client.post("/crm/leads/bulk",
                    json={"lead_ids": [str(leads[0].id)], "owner_user_id": str(outsider.id)},
                    headers=_as(people["manager"], ws))
    assert r.status_code == 422
    assert _owner_of(db_session, leads[0]) is None


# --------------------------------------------------------------------------
# Round-robin
# --------------------------------------------------------------------------


def test_round_robin_spreads_evenly_and_is_idempotent(client, db_session, team, leads,
                                                      verified_strategy):
    ws, people = team
    body = {"strategy_id": str(verified_strategy.id)}
    first = client.post("/crm/leads/assign-round-robin", json=body,
                        headers=_as(people["manager"], ws))
    assert first.status_code == 200, first.text
    result = first.json()
    assert result["assigned_count"] == 4
    assert sorted(result["per_member"].values()) == [2, 2]
    assert set(result["per_member"]) == {str(people["sdr"].id), str(people["sdr2"].id)}

    # A retry (or a double click) finds nothing unassigned and moves nothing.
    owners_before = {l.id: _owner_of(db_session, l) for l in leads}
    again = client.post("/crm/leads/assign-round-robin", json=body,
                        headers=_as(people["manager"], ws)).json()
    assert again["assigned_count"] == 0
    assert {l.id: _owner_of(db_session, l) for l in leads} == owners_before

    # The explicit-selection form reports them as skipped instead.
    explicit = client.post("/crm/leads/assign-round-robin",
                           json={"lead_ids": [str(l.id) for l in leads]},
                           headers=_as(people["manager"], ws)).json()
    assert explicit["assigned_count"] == 0 and explicit["skipped_count"] == 4


def test_round_robin_levels_an_uneven_team(client, db_session, team, verified_strategy):
    ws, people = team
    held = _leads(db_session, verified_strategy, 2, prefix="held")
    for lead in held:
        client.patch(f"/crm/leads/{lead.id}", json={"owner_user_id": str(people["sdr"].id)})
    fresh = _leads(db_session, verified_strategy, 2, prefix="fresh")

    r = client.post("/crm/leads/assign-round-robin",
                    json={"lead_ids": [str(l.id) for l in fresh]},
                    headers=_as(people["manager"], ws))
    assert r.status_code == 200, r.text
    # sdr already holds two open leads, so both new ones go to sdr2.
    assert {_owner_of(db_session, l) for l in fresh} == {people["sdr2"].id}


def test_round_robin_skips_closed_leads_and_ignores_their_load(client, db_session, team,
                                                               verified_strategy):
    ws, people = team
    closed = _leads(db_session, verified_strategy, 3, status=m.LeadStatus.CLOSED_WON,
                    prefix="closed")
    for lead in closed:
        client.patch(f"/crm/leads/{lead.id}", json={"owner_user_id": str(people["sdr"].id)})
    open_leads = _leads(db_session, verified_strategy, 2, prefix="open")
    unassigned_closed = _leads(db_session, verified_strategy, 1,
                               status=m.LeadStatus.DROPPED, prefix="dropped")

    r = client.post("/crm/leads/assign-round-robin",
                    json={"strategy_id": str(verified_strategy.id)},
                    headers=_as(people["manager"], ws)).json()
    assert r["assigned_count"] == 2
    # Finished leads are not workload: the split stays one each.
    assert sorted(r["per_member"].values()) == [1, 1]
    assert _owner_of(db_session, unassigned_closed[0]) is None


def test_round_robin_needs_a_manager(client, team, leads, verified_strategy):
    ws, people = team
    for who in ("sdr", "viewer"):
        r = client.post("/crm/leads/assign-round-robin",
                        json={"strategy_id": str(verified_strategy.id)},
                        headers=_as(people[who], ws))
        assert r.status_code == 403


def test_round_robin_with_a_foreign_lead_assigns_nothing(client, db_session, team, leads,
                                                         foreign_lead):
    ws, people = team
    r = client.post("/crm/leads/assign-round-robin",
                    json={"lead_ids": [str(leads[0].id), str(foreign_lead.id)]},
                    headers=_as(people["manager"], ws))
    assert r.status_code == 404
    assert _owner_of(db_session, leads[0]) is None
    assert _owner_of(db_session, foreign_lead) is None


def test_round_robin_validates_its_input(client, db_session, test_user, leads,
                                         verified_strategy):
    # Solo account: nobody with the SDR role to receive leads.
    r = client.post("/crm/leads/assign-round-robin",
                    json={"strategy_id": str(verified_strategy.id)})
    assert r.status_code == 422
    r = client.post("/crm/leads/assign-round-robin",
                    json={"strategy_id": str(verified_strategy.id),
                          "lead_ids": [str(leads[0].id)]})
    assert r.status_code == 422
    r = client.post("/crm/leads/assign-round-robin",
                    json={"strategy_id": str(verified_strategy.id), "roles": ["admin"]})
    assert r.status_code == 422
